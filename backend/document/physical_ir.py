"""Deterministic pdfplumber extraction into canonical physical IR."""

from __future__ import annotations

import io
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, cast

import pdfplumber
import pikepdf

from backend.document.errors import DocumentEngineError, document_error
from backend.document.models import (
    IR_SCHEMA_VERSION,
    PARSER_VERSION,
    AffineTransformMpt,
    CanonicalBox,
    PdfBoxMpt,
    PhysicalBlock,
    PhysicalDocumentIR,
    PhysicalPage,
    canonical_json_bytes,
    sha256_hex,
)
from backend.document.preflight import (
    PreflightLimits,
    PreflightPage,
    PreflightResult,
    preflight_pdf,
)


@dataclass(frozen=True, slots=True)
class _DraftBlock:
    kind: str
    bbox: CanonicalBox
    source_sequence: int
    text: str | None = None
    join_after: str = "none"
    field_name: str | None = None
    writable: bool | None = None
    multiline: bool | None = None
    max_length: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    stroke_width_mpt: int | None = None
    filled: bool | None = None
    stroked: bool | None = None
    ambiguity_flags: tuple[str, ...] = ()


def _scaled_mpt(value: object, user_unit: str) -> int:
    try:
        result = Decimal(str(value)) * Decimal(user_unit) * Decimal(1000)
    except Exception as error:
        raise document_error("invalid_physical_evidence") from error
    if not result.is_finite():
        raise document_error("invalid_physical_evidence")
    return int(result.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def _canonical_box_from_plumber(
    raw: Mapping[str, Any],
    page: PreflightPage,
    *,
    allow_zero_axis: bool,
) -> CanonicalBox:
    try:
        display_x0, display_y0 = _plumber_display_origin(page)
        left = _scaled_mpt(raw["x0"], page.user_unit) + display_x0
        right = _scaled_mpt(raw["x1"], page.user_unit) + display_x0
        top = _scaled_mpt(raw["top"], page.user_unit) + display_y0
        bottom = _scaled_mpt(raw["bottom"], page.user_unit) + display_y0
    except (KeyError, TypeError) as error:
        raise document_error("invalid_physical_evidence") from error
    x0, x1 = sorted((left, right))
    y0, y1 = sorted((top, bottom))
    if not allow_zero_axis:
        if x0 == x1:
            x1 += 1
        if y0 == y1:
            y1 += 1
    box = CanonicalBox(x0=x0, y0=y0, x1=x1, y1=y1)
    if not box.within(page.width_mpt, page.height_mpt):
        raise document_error("invalid_physical_evidence")
    return box


def _plumber_display_origin(page: PreflightPage) -> tuple[int, int]:
    """Map pdfplumber's media-relative display axes into crop-relative axes."""

    media = page.media_box_mpt
    canonical_corners = (
        page.canonical_to_pdf_mpt.inverse_apply(media.x0, media.y0),
        page.canonical_to_pdf_mpt.inverse_apply(media.x0, media.y1),
        page.canonical_to_pdf_mpt.inverse_apply(media.x1, media.y0),
        page.canonical_to_pdf_mpt.inverse_apply(media.x1, media.y1),
    )
    return (
        min(point[0] for point in canonical_corners),
        min(point[1] for point in canonical_corners),
    )


def _canonical_box_from_pdf_rect(raw_rect: Sequence[object], page: PreflightPage) -> CanonicalBox:
    if len(raw_rect) != 4:
        raise document_error("invalid_physical_evidence")
    x0 = _scaled_mpt(raw_rect[0], page.user_unit)
    y0 = _scaled_mpt(raw_rect[1], page.user_unit)
    x1 = _scaled_mpt(raw_rect[2], page.user_unit)
    y1 = _scaled_mpt(raw_rect[3], page.user_unit)
    corners = (
        page.canonical_to_pdf_mpt.inverse_apply(x0, y0),
        page.canonical_to_pdf_mpt.inverse_apply(x0, y1),
        page.canonical_to_pdf_mpt.inverse_apply(x1, y0),
        page.canonical_to_pdf_mpt.inverse_apply(x1, y1),
    )
    box = CanonicalBox(
        x0=min(point[0] for point in corners),
        y0=min(point[1] for point in corners),
        x1=max(point[0] for point in corners),
        y1=max(point[1] for point in corners),
    )
    if box.width <= 0 or box.height <= 0 or not box.within(page.width_mpt, page.height_mpt):
        raise document_error("invalid_physical_evidence")
    return box


def _text_lines(page: pdfplumber.page.Page, metadata: PreflightPage) -> list[_DraftBlock]:
    try:
        # Keeping blank characters preserves authored spacing inside a text
        # run while still separating independently positioned labels such as a
        # question number from the prompt beside it.  The text-line renderer
        # would merge those two source objects and make block-only prompt
        # reconstruction impossible.  Rotation-specific direction overrides
        # restore the original character order for 180/270-degree pages.
        direction: dict[str, str] = {}
        if metadata.rotation == 180:
            direction["char_dir"] = "rtl"
        elif metadata.rotation == 270:
            direction["char_dir_rotated"] = "btt"
        raw_lines = page.extract_words(keep_blank_chars=True, **direction)
    except Exception as error:
        raise document_error("invalid_physical_evidence") from error
    result: list[_DraftBlock] = []
    for sequence, raw in enumerate(raw_lines):
        text = raw.get("text")
        if not isinstance(text, str) or not text:
            continue
        result.append(
            _DraftBlock(
                kind="text",
                bbox=_canonical_box_from_plumber(raw, metadata, allow_zero_axis=False),
                source_sequence=sequence,
                text=text,
                join_after="newline",
            )
        )
    joined: list[_DraftBlock] = []
    for index, current in enumerate(result):
        join_after = "none" if index == len(result) - 1 else "newline"
        if index < len(result) - 1:
            following = result[index + 1]
            center_delta = (
                abs((current.bbox.y0 + current.bbox.y1) - (following.bbox.y0 + following.bbox.y1))
                // 2
            )
            horizontal_gap = following.bbox.x0 - current.bbox.x1
            if center_delta <= 8_000 and 0 <= horizontal_gap <= 90_000:
                join_after = "space"
        joined.append(
            _DraftBlock(
                kind=current.kind,
                bbox=current.bbox,
                source_sequence=current.source_sequence,
                text=current.text,
                join_after=join_after,
            )
        )
    return joined


def _shape_blocks(page: pdfplumber.page.Page, metadata: PreflightPage) -> list[_DraftBlock]:
    result: list[_DraftBlock] = []
    sequence = 0
    for raw in page.lines:
        result.append(
            _DraftBlock(
                kind="line",
                bbox=_canonical_box_from_plumber(raw, metadata, allow_zero_axis=True),
                source_sequence=sequence,
                stroke_width_mpt=max(0, _scaled_mpt(raw.get("linewidth", 0), metadata.user_unit)),
                stroked=True,
            )
        )
        sequence += 1
    for raw in page.rects:
        result.append(
            _DraftBlock(
                kind="rect",
                bbox=_canonical_box_from_plumber(raw, metadata, allow_zero_axis=False),
                source_sequence=sequence,
                stroke_width_mpt=max(0, _scaled_mpt(raw.get("linewidth", 0), metadata.user_unit)),
                filled=raw.get("fill") is not False and raw.get("non_stroking_color") is not None,
                stroked=raw.get("stroke") is not False,
            )
        )
        sequence += 1
    for raw in page.curves:
        result.append(
            _DraftBlock(
                kind="shape",
                bbox=_canonical_box_from_plumber(raw, metadata, allow_zero_axis=True),
                source_sequence=sequence,
                stroke_width_mpt=max(0, _scaled_mpt(raw.get("linewidth", 0), metadata.user_unit)),
                filled=raw.get("fill") is not False and raw.get("non_stroking_color") is not None,
                stroked=raw.get("stroke") is not False,
                ambiguity_flags=("curve_bbox_only",),
            )
        )
        sequence += 1
    return result


def _image_blocks(page: pdfplumber.page.Page, metadata: PreflightPage) -> list[_DraftBlock]:
    result: list[_DraftBlock] = []
    for sequence, raw in enumerate(page.images):
        source_size = raw.get("srcsize")
        image_width: int | None = None
        image_height: int | None = None
        if (
            isinstance(source_size, (tuple, list))
            and len(source_size) == 2
            and all(isinstance(value, int) and value > 0 for value in source_size)
        ):
            image_width, image_height = int(source_size[0]), int(source_size[1])
        result.append(
            _DraftBlock(
                kind="image",
                bbox=_canonical_box_from_plumber(raw, metadata, allow_zero_axis=False),
                source_sequence=sequence,
                image_width=image_width,
                image_height=image_height,
            )
        )
    return result


def _inherited(annotation: pikepdf.Object, key: str) -> object | None:
    current: pikepdf.Object | None = annotation
    visited: set[tuple[int, int] | int] = set()
    while current is not None:
        identity: tuple[int, int] | int
        try:
            identity = cast(tuple[int, int], current.objgen)
        except Exception:
            identity = id(current)
        if identity in visited:
            raise document_error("invalid_physical_evidence")
        visited.add(identity)
        value = current.get(key)
        if value is not None:
            return value
        parent = current.get("/Parent")
        current = cast(pikepdf.Object | None, parent)
    return None


def _form_field_blocks(pdf_page: pikepdf.Page, metadata: PreflightPage) -> list[_DraftBlock]:
    annotations = pdf_page.obj.get("/Annots", [])
    result: list[_DraftBlock] = []
    for sequence, annotation_ref in enumerate(annotations):
        try:
            annotation = cast(pikepdf.Object, annotation_ref)
            if str(annotation.get("/Subtype", "")) != "/Widget":
                continue
            if str(_inherited(annotation, "/FT") or "") != "/Tx":
                continue
            raw_rect = list(annotation.get("/Rect", []))
            flags = int(_inherited(annotation, "/Ff") or 0)
            field_name_raw = _inherited(annotation, "/T")
            field_name = str(field_name_raw) if field_name_raw is not None else None
            max_length_raw = _inherited(annotation, "/MaxLen")
            max_length = int(max_length_raw) if max_length_raw is not None else None
            read_only = bool(flags & 1)
            multiline = bool(flags & (1 << 12))
            result.append(
                _DraftBlock(
                    kind="form_field",
                    bbox=_canonical_box_from_pdf_rect(raw_rect, metadata),
                    source_sequence=sequence,
                    field_name=field_name,
                    writable=not read_only,
                    multiline=multiline,
                    max_length=max_length,
                )
            )
        except DocumentEngineError:
            raise
        except Exception as error:
            raise document_error("invalid_physical_evidence") from error
    return result


def _block_id(
    source_sha256: str,
    page_index: int,
    reading_order: int,
    draft: _DraftBlock,
) -> str:
    seed = {
        "parser_version": PARSER_VERSION,
        "source_sha256": source_sha256,
        "page_index": page_index,
        "kind": draft.kind,
        "reading_order": reading_order,
        "bbox_mpt": draft.bbox.to_list(),
        "text": draft.text,
        "join_after": draft.join_after,
        "field_name": draft.field_name,
        "writable": draft.writable,
        "multiline": draft.multiline,
        "max_length": draft.max_length,
        "image_width": draft.image_width,
        "image_height": draft.image_height,
        "stroke_width_mpt": draft.stroke_width_mpt,
        "filled": draft.filled,
        "stroked": draft.stroked,
        "ambiguity_flags": list(draft.ambiguity_flags),
    }
    return "blk_" + sha256_hex(canonical_json_bytes(seed))[:32]


def _materialize_blocks(
    drafts: Iterable[_DraftBlock],
    *,
    source_sha256: str,
    page_index: int,
) -> tuple[PhysicalBlock, ...]:
    kind_priority = {
        "text": 0,
        "form_field": 1,
        "rect": 2,
        "line": 3,
        "shape": 4,
        "image": 5,
    }
    ordered = sorted(
        drafts,
        key=lambda item: (
            item.bbox.y0,
            item.bbox.x0,
            kind_priority[item.kind],
            item.source_sequence,
            item.bbox.y1,
            item.bbox.x1,
        ),
    )
    return tuple(
        PhysicalBlock(
            id=_block_id(source_sha256, page_index, order, draft),
            kind=cast(Any, draft.kind),
            page_index=page_index,
            reading_order=order,
            bbox=draft.bbox,
            text=draft.text,
            join_after=cast(Any, draft.join_after),
            field_name=draft.field_name,
            writable=draft.writable,
            multiline=draft.multiline,
            max_length=draft.max_length,
            image_width=draft.image_width,
            image_height=draft.image_height,
            stroke_width_mpt=draft.stroke_width_mpt,
            filled=draft.filled,
            stroked=draft.stroked,
            ambiguity_flags=draft.ambiguity_flags,
        )
        for order, draft in enumerate(ordered)
    )


def _extract_pages(preflight: PreflightResult) -> tuple[PhysicalPage, ...]:
    result: list[PhysicalPage] = []
    try:
        with (
            pdfplumber.open(io.BytesIO(preflight.normalized_pdf)) as plumber_document,
            pikepdf.Pdf.open(io.BytesIO(preflight.normalized_pdf)) as pike_document,
        ):
            if len(plumber_document.pages) != len(preflight.pages) or len(
                pike_document.pages
            ) != len(preflight.pages):
                raise document_error("invalid_physical_evidence")
            for metadata, plumber_page, pike_page in zip(
                preflight.pages,
                plumber_document.pages,
                pike_document.pages,
                strict=True,
            ):
                drafts = [
                    *_text_lines(plumber_page, metadata),
                    *_form_field_blocks(pike_page, metadata),
                    *_shape_blocks(plumber_page, metadata),
                    *_image_blocks(plumber_page, metadata),
                ]
                page_flags = set(metadata.ambiguity_flags)
                if plumber_page.curves:
                    page_flags.add("curves_present")
                result.append(
                    PhysicalPage(
                        page_index=metadata.page_index,
                        media_box_mpt=metadata.media_box_mpt,
                        crop_box_mpt=metadata.crop_box_mpt,
                        width_mpt=metadata.width_mpt,
                        height_mpt=metadata.height_mpt,
                        rotation=metadata.rotation,
                        user_unit=metadata.user_unit,
                        canonical_to_pdf_mpt=metadata.canonical_to_pdf_mpt,
                        blocks=_materialize_blocks(
                            drafts,
                            source_sha256=preflight.source_sha256,
                            page_index=metadata.page_index,
                        ),
                        ambiguity_flags=tuple(sorted(page_flags)),
                    )
                )
    except DocumentEngineError:
        raise
    except Exception as error:
        raise document_error("invalid_physical_evidence") from error
    return tuple(result)


def extract_physical_ir(
    pdf_bytes: bytes,
    *,
    preflight: PreflightResult | None = None,
    limits: PreflightLimits | None = None,
) -> PhysicalDocumentIR:
    resolved = preflight or preflight_pdf(pdf_bytes, limits=limits)
    if resolved.source_sha256 != sha256_hex(pdf_bytes) or resolved.source_size_bytes != len(
        pdf_bytes
    ):
        raise document_error("stale_source")
    pages = _extract_pages(resolved)
    return PhysicalDocumentIR(
        document_id="doc_" + resolved.source_sha256[:24],
        source_sha256=resolved.source_sha256,
        normalization_sha256=resolved.normalization_sha256,
        source_size_bytes=resolved.source_size_bytes,
        pages=pages,
        ambiguity_flags=resolved.ambiguity_flags,
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise document_error("stale_physical_ir")
        result[key] = value
    return result


def _require_keys(value: Mapping[str, Any], expected: set[str]) -> None:
    if set(value) != expected:
        raise document_error("stale_physical_ir")


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise document_error("stale_physical_ir")
    return value


def _optional_int(value: object | None) -> int | None:
    return None if value is None else _int(value)


def _box(value: object, *, absolute: bool) -> PdfBoxMpt | CanonicalBox:
    if not isinstance(value, list) or len(value) != 4:
        raise document_error("stale_physical_ir")
    numbers = [_int(item) for item in value]
    constructor = PdfBoxMpt if absolute else CanonicalBox
    return constructor(*numbers)


def _parse_block(value: object) -> PhysicalBlock:
    if not isinstance(value, dict):
        raise document_error("stale_physical_ir")
    required = {
        "id",
        "kind",
        "page_index",
        "reading_order",
        "bbox_mpt",
        "join_after",
        "ambiguity_flags",
    }
    optional = {
        "text",
        "field_name",
        "writable",
        "multiline",
        "max_length",
        "image_width",
        "image_height",
        "stroke_width_mpt",
        "filled",
        "stroked",
    }
    if not required.issubset(value) or not set(value).issubset(required | optional):
        raise document_error("stale_physical_ir")
    flags = value["ambiguity_flags"]
    if not isinstance(flags, list) or not all(isinstance(item, str) for item in flags):
        raise document_error("stale_physical_ir")
    boolean_fields = ("writable", "multiline", "filled", "stroked")
    for field_name in boolean_fields:
        if field_name in value and not isinstance(value[field_name], bool):
            raise document_error("stale_physical_ir")
    for field_name in ("text", "field_name"):
        if field_name in value and not isinstance(value[field_name], str):
            raise document_error("stale_physical_ir")
    return PhysicalBlock(
        id=cast(str, value["id"]),
        kind=cast(Any, value["kind"]),
        page_index=_int(value["page_index"]),
        reading_order=_int(value["reading_order"]),
        bbox=cast(CanonicalBox, _box(value["bbox_mpt"], absolute=False)),
        text=cast(str | None, value.get("text")),
        join_after=cast(Any, value["join_after"]),
        field_name=cast(str | None, value.get("field_name")),
        writable=cast(bool | None, value.get("writable")),
        multiline=cast(bool | None, value.get("multiline")),
        max_length=_optional_int(value.get("max_length")),
        image_width=_optional_int(value.get("image_width")),
        image_height=_optional_int(value.get("image_height")),
        stroke_width_mpt=_optional_int(value.get("stroke_width_mpt")),
        filled=cast(bool | None, value.get("filled")),
        stroked=cast(bool | None, value.get("stroked")),
        ambiguity_flags=tuple(flags),
    )


def _parse_page(value: object) -> PhysicalPage:
    if not isinstance(value, dict):
        raise document_error("stale_physical_ir")
    _require_keys(
        value,
        {
            "page_index",
            "page_number",
            "media_box_mpt",
            "crop_box_mpt",
            "width_mpt",
            "height_mpt",
            "rotation",
            "user_unit",
            "canonical_to_pdf_mpt",
            "ambiguity_flags",
            "blocks",
        },
    )
    page_index = _int(value["page_index"])
    if _int(value["page_number"]) != page_index + 1:
        raise document_error("stale_physical_ir")
    transform = value["canonical_to_pdf_mpt"]
    flags = value["ambiguity_flags"]
    blocks = value["blocks"]
    if not isinstance(transform, list) or len(transform) != 6:
        raise document_error("stale_physical_ir")
    if not isinstance(flags, list) or not all(isinstance(item, str) for item in flags):
        raise document_error("stale_physical_ir")
    if not isinstance(blocks, list) or not isinstance(value["user_unit"], str):
        raise document_error("stale_physical_ir")
    return PhysicalPage(
        page_index=page_index,
        media_box_mpt=cast(PdfBoxMpt, _box(value["media_box_mpt"], absolute=True)),
        crop_box_mpt=cast(PdfBoxMpt, _box(value["crop_box_mpt"], absolute=True)),
        width_mpt=_int(value["width_mpt"]),
        height_mpt=_int(value["height_mpt"]),
        rotation=_int(value["rotation"]),
        user_unit=value["user_unit"],
        canonical_to_pdf_mpt=AffineTransformMpt(*[_int(item) for item in transform]),
        blocks=tuple(_parse_block(item) for item in blocks),
        ambiguity_flags=tuple(flags),
    )


def parse_physical_ir(payload: bytes) -> PhysicalDocumentIR:
    """Strictly load a separately persisted canonical IR object.

    Duplicate keys, unknown fields, noncanonical bytes, a bad content hash, and
    invalid/duplicate/out-of-bounds geometry are all rejected before use.
    """

    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    try:
        raw = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                document_error("stale_physical_ir")
            ),
        )
    except DocumentEngineError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise document_error("stale_physical_ir") from error
    if not isinstance(raw, dict):
        raise document_error("stale_physical_ir")
    _require_keys(
        raw,
        {
            "schema_version",
            "parser_version",
            "document_id",
            "source_sha256",
            "normalization_sha256",
            "source_size_bytes",
            "ambiguity_flags",
            "pages",
            "ir_sha256",
        },
    )
    if raw["schema_version"] != IR_SCHEMA_VERSION or raw["parser_version"] != PARSER_VERSION:
        raise document_error("stale_physical_ir")
    for key in ("document_id", "source_sha256", "normalization_sha256", "ir_sha256"):
        if not isinstance(raw[key], str):
            raise document_error("stale_physical_ir")
    flags = raw["ambiguity_flags"]
    pages = raw["pages"]
    if not isinstance(flags, list) or not all(isinstance(item, str) for item in flags):
        raise document_error("stale_physical_ir")
    if not isinstance(pages, list):
        raise document_error("stale_physical_ir")
    try:
        document = PhysicalDocumentIR(
            document_id=raw["document_id"],
            source_sha256=raw["source_sha256"],
            normalization_sha256=raw["normalization_sha256"],
            source_size_bytes=_int(raw["source_size_bytes"]),
            pages=tuple(_parse_page(item) for item in pages),
            parser_version=raw["parser_version"],
            schema_version=_int(raw["schema_version"]),
            ambiguity_flags=tuple(flags),
        )
    except DocumentEngineError as error:
        # Geometry failures raised while initially analysing a PDF describe an
        # unsupported source.  The same failures while reopening a persisted
        # canonical object instead prove that the stored evidence is stale or
        # corrupt, so callers must require a fresh analysis/review.
        raise document_error("stale_physical_ir") from error
    if raw["ir_sha256"] != document.ir_sha256 or payload != document.canonical_bytes():
        raise document_error("stale_physical_ir")
    return document
