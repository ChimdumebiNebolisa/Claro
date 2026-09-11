"""Content-based PDF admission and deterministic normalization."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

import pdfplumber
import pikepdf

from backend.document.errors import DocumentEngineError, document_error
from backend.document.models import AffineTransformMpt, PdfBoxMpt, sha256_hex

PDF_HEADER = b"%PDF-"
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_PAGES = 8
DEFAULT_MAX_QUESTIONS = 40
DEFAULT_MAX_EXTRACTED_TEXT_BYTES = 2 * 1024 * 1024
NORMALIZATION_VERSION = "pikepdf-v1"


@dataclass(frozen=True, slots=True)
class PreflightLimits:
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES
    max_pages: int = DEFAULT_MAX_PAGES
    max_questions: int = DEFAULT_MAX_QUESTIONS
    max_extracted_text_bytes: int = DEFAULT_MAX_EXTRACTED_TEXT_BYTES
    min_selectable_characters: int = 8

    def __post_init__(self) -> None:
        if (
            min(
                self.max_upload_bytes,
                self.max_pages,
                self.max_questions,
                self.max_extracted_text_bytes,
                self.min_selectable_characters,
            )
            <= 0
        ):
            raise ValueError("preflight limits must be positive")


@dataclass(frozen=True, slots=True)
class PreflightPage:
    page_index: int
    media_box_mpt: PdfBoxMpt
    crop_box_mpt: PdfBoxMpt
    width_mpt: int
    height_mpt: int
    rotation: int
    user_unit: str
    canonical_to_pdf_mpt: AffineTransformMpt
    ambiguity_flags: tuple[str, ...]

    @property
    def has_identity_inline_transform(self) -> bool:
        return (
            self.rotation == 0
            and self.user_unit == "1"
            and self.media_box_mpt == self.crop_box_mpt
            and self.media_box_mpt.x0 == 0
            and self.media_box_mpt.y0 == 0
        )


@dataclass(frozen=True, slots=True)
class PreflightResult:
    source_sha256: str
    source_size_bytes: int
    page_count: int
    extracted_text_bytes: int
    normalized_pdf: bytes
    normalization_sha256: str
    normalization_version: str
    pages: tuple[PreflightPage, ...]
    ambiguity_flags: tuple[str, ...]


def _decimal(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise document_error("invalid_physical_evidence") from error
    if not result.is_finite():
        raise document_error("invalid_physical_evidence")
    return result


def _decimal_string(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f").rstrip("0").rstrip(".")


def _mpt(value: object, user_unit: Decimal) -> int:
    scaled = _decimal(value) * user_unit * Decimal(1000)
    return int(scaled.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _page_box(raw_box: object, user_unit: Decimal) -> PdfBoxMpt:
    try:
        values = list(raw_box)  # type: ignore[arg-type]
    except TypeError as error:
        raise document_error("invalid_physical_evidence") from error
    if len(values) != 4:
        raise document_error("invalid_physical_evidence")
    x0, y0, x1, y1 = (_mpt(value, user_unit) for value in values)
    return PdfBoxMpt(x0=x0, y0=y0, x1=x1, y1=y1)


def _transform_for_page(
    crop_box: PdfBoxMpt,
    rotation: int,
) -> tuple[int, int, AffineTransformMpt]:
    width = crop_box.width
    height = crop_box.height
    if rotation == 0:
        return (
            width,
            height,
            AffineTransformMpt(1, 0, 0, -1, crop_box.x0, crop_box.y1),
        )
    if rotation == 90:
        return (
            height,
            width,
            AffineTransformMpt(0, 1, 1, 0, crop_box.x0, crop_box.y0),
        )
    if rotation == 180:
        return (
            width,
            height,
            AffineTransformMpt(-1, 0, 0, 1, crop_box.x1, crop_box.y0),
        )
    if rotation == 270:
        return (
            height,
            width,
            AffineTransformMpt(0, -1, -1, 0, crop_box.x1, crop_box.y1),
        )
    raise document_error("invalid_physical_evidence")


def _inspect_pages(pdf: pikepdf.Pdf, limits: PreflightLimits) -> tuple[PreflightPage, ...]:
    page_count = len(pdf.pages)
    if page_count == 0:
        raise document_error("empty_pdf")
    if page_count > limits.max_pages:
        raise document_error("page_limit_exceeded")

    pages: list[PreflightPage] = []
    for page_index, page in enumerate(pdf.pages):
        try:
            user_unit_decimal = _decimal(page.obj.get("/UserUnit", 1))
            if user_unit_decimal <= 0:
                raise document_error("invalid_physical_evidence")
            media_box = _page_box(page.mediabox, user_unit_decimal)
            crop_box = _page_box(page.cropbox, user_unit_decimal)
            if (
                crop_box.x0 < media_box.x0
                or crop_box.y0 < media_box.y0
                or crop_box.x1 > media_box.x1
                or crop_box.y1 > media_box.y1
            ):
                raise document_error("invalid_physical_evidence")
            raw_rotation = int(page.obj.get("/Rotate", 0))
        except DocumentEngineError:
            raise
        except Exception as error:
            raise document_error("invalid_physical_evidence") from error
        rotation = raw_rotation % 360
        if rotation not in {0, 90, 180, 270}:
            raise document_error("invalid_physical_evidence")
        width, height, transform = _transform_for_page(crop_box, rotation)
        flags: set[str] = set()
        if rotation:
            flags.add("non_identity_rotation")
        if crop_box != media_box:
            flags.add("non_default_crop_box")
        user_unit = _decimal_string(user_unit_decimal)
        if user_unit != "1":
            flags.add("non_unit_user_unit")
        pages.append(
            PreflightPage(
                page_index=page_index,
                media_box_mpt=media_box,
                crop_box_mpt=crop_box,
                width_mpt=width,
                height_mpt=height,
                rotation=rotation,
                user_unit=user_unit,
                canonical_to_pdf_mpt=transform,
                ambiguity_flags=tuple(sorted(flags)),
            )
        )
    return tuple(pages)


def _normalize(pdf: pikepdf.Pdf) -> bytes:
    output = io.BytesIO()
    try:
        pdf.save(
            output,
            compress_streams=True,
            deterministic_id=True,
            linearize=False,
            normalize_content=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            preserve_pdfa=True,
        )
    except Exception as error:
        raise document_error("malformed_pdf") from error
    return output.getvalue()


def _count_selectable_text(normalized_pdf: bytes, limits: PreflightLimits) -> int:
    extracted_bytes = 0
    selectable_characters = 0
    try:
        with pdfplumber.open(io.BytesIO(normalized_pdf)) as document:
            for page in document.pages:
                for character in page.chars:
                    text = str(character.get("text", ""))
                    extracted_bytes += len(text.encode("utf-8"))
                    selectable_characters += sum(not item.isspace() for item in text)
                    if extracted_bytes > limits.max_extracted_text_bytes:
                        raise document_error("extracted_text_limit_exceeded")
    except DocumentEngineError:
        raise
    except Exception as error:
        raise document_error("malformed_pdf") from error
    if selectable_characters < limits.min_selectable_characters:
        raise document_error("requires_ocr")
    return extracted_bytes


def preflight_pdf(
    pdf_bytes: bytes,
    *,
    limits: PreflightLimits | None = None,
) -> PreflightResult:
    """Validate and normalize untrusted source bytes without mutating the source."""

    resolved_limits = limits or PreflightLimits()
    if not isinstance(pdf_bytes, bytes):
        raise TypeError("pdf_bytes must be bytes")
    if len(pdf_bytes) > resolved_limits.max_upload_bytes:
        raise document_error("file_too_large")
    header_offset = pdf_bytes.find(PDF_HEADER, 0, min(len(pdf_bytes), 1024))
    if header_offset < 0:
        raise document_error("invalid_pdf_signature")
    if not pdf_bytes:
        raise document_error("invalid_pdf_signature")

    try:
        with pikepdf.Pdf.open(io.BytesIO(pdf_bytes), attempt_recovery=True) as pdf:
            if pdf.is_encrypted:
                raise document_error("encrypted_pdf")
            pages = _inspect_pages(pdf, resolved_limits)
            normalized_pdf = _normalize(pdf)
    except DocumentEngineError:
        raise
    except pikepdf.PasswordError as error:
        raise document_error("encrypted_pdf") from error
    except (pikepdf.PdfError, ValueError, OSError) as error:
        raise document_error("malformed_pdf") from error

    if not normalized_pdf.startswith(PDF_HEADER):
        raise document_error("malformed_pdf")
    extracted_text_bytes = _count_selectable_text(normalized_pdf, resolved_limits)
    flags = tuple(sorted({flag for page in pages for flag in page.ambiguity_flags}))
    return PreflightResult(
        source_sha256=sha256_hex(pdf_bytes),
        source_size_bytes=len(pdf_bytes),
        page_count=len(pages),
        extracted_text_bytes=extracted_text_bytes,
        normalized_pdf=normalized_pdf,
        normalization_sha256=sha256_hex(normalized_pdf),
        normalization_version=NORMALIZATION_VERSION,
        pages=pages,
        ambiguity_flags=flags,
    )


def validate_question_count(question_count: int, limits: PreflightLimits | None = None) -> None:
    resolved_limits = limits or PreflightLimits()
    if question_count < 1 or question_count > resolved_limits.max_questions:
        raise document_error("question_limit_exceeded")


def finite_number(value: object) -> float:
    """Convert a parser number only when it is finite."""

    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise document_error("invalid_physical_evidence") from error
    if not math.isfinite(result):
        raise document_error("invalid_physical_evidence")
    return result
