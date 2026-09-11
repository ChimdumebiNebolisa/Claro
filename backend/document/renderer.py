"""ReportLab rendering and pypdf derivative assembly."""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

from backend.document.errors import DocumentEngineError, document_error
from backend.document.fonts import (
    BOLD_FONT_NAME,
    REGULAR_FONT_NAME,
    ensure_supported_text,
    register_fonts,
)
from backend.document.geometry import PlacementPlan, _wrap_exact_text
from backend.document.models import PhysicalDocumentIR, PhysicalPage, sha256_hex

APPENDIX_PAGE_SIZE = (612.0, 792.0)
APPENDIX_MARGIN = 54.0
APPENDIX_FONT_SIZE_MPT = 11_000
APPENDIX_LEADING_MPT = 14_000
APPENDIX_TEXT_COLOR = HexColor("#111827")
INLINE_TEXT_COLOR = HexColor("#111827")


@dataclass(frozen=True, slots=True)
class AppendixEntry:
    question_id: str
    display_identifier: str
    exact_question: str
    source_page_number: int
    exact_answer: str
    placement_hash: str


@dataclass(frozen=True, slots=True)
class AppendixRenderEvidence:
    question_id: str
    first_page_offset: int
    page_count: int
    exact_answer_sha256: str
    rendered_answer_lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AppendixRenderResult:
    pdf_bytes: bytes
    page_count: int
    entries: tuple[AppendixRenderEvidence, ...]


def render_inline_overlay(page: PhysicalPage, plans: Sequence[PlacementPlan]) -> bytes:
    """Render only answer glyphs on a transparent source-sized page."""

    if not page.has_identity_inline_transform:
        raise document_error("invalid_physical_evidence")
    if any(
        plan.outcome != "inline"
        or plan.region is None
        or plan.fit is None
        or plan.region.page_index != page.page_index
        for plan in plans
    ):
        raise document_error("invalid_physical_evidence")
    register_fonts()
    output = io.BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=(page.media_box_mpt.width / 1000, page.media_box_mpt.height / 1000),
        invariant=1,
        pageCompression=1,
    )
    pdf.setFillColor(INLINE_TEXT_COLOR)
    for plan in plans:
        fit = plan.fit
        if fit is None:
            raise document_error("invalid_physical_evidence")
        pdf.setFont(REGULAR_FONT_NAME, fit.font_size_mpt / 1000)
        for line in fit.lines:
            pdf_x_mpt, pdf_y_mpt = page.canonical_to_pdf_mpt.apply(
                line.x_mpt,
                line.baseline_y_mpt,
            )
            pdf.drawString(pdf_x_mpt / 1000, pdf_y_mpt / 1000, line.text)
    pdf.showPage()
    pdf.save()
    payload = output.getvalue()
    if not payload.startswith(b"%PDF-"):
        raise document_error("invalid_export")
    return payload


def _wrapped_lines(text: str, width_points: float, font_name: str, font_size: float) -> list[str]:
    ensure_supported_text(text, bold=font_name == BOLD_FONT_NAME)
    if font_name != REGULAR_FONT_NAME:
        # Headings are short; retain their exact text on one line when possible.
        if pdfmetrics.stringWidth(text, font_name, font_size) <= width_points:
            return [text]
        words = text.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            trial = word if not current else f"{current} {word}"
            if pdfmetrics.stringWidth(trial, font_name, font_size) <= width_points:
                current = trial
            elif current:
                lines.append(current)
                current = word
            else:
                raise document_error("invalid_export")
        lines.append(current)
        return lines
    wrapped = _wrap_exact_text(text, round(width_points * 1000), round(font_size * 1000))
    if wrapped is None:
        raise document_error("invalid_export")
    return [line.text for line in wrapped]


def render_appendix(entries: Sequence[AppendixEntry], worksheet_title: str) -> AppendixRenderResult:
    if not entries:
        return AppendixRenderResult(pdf_bytes=b"", page_count=0, entries=())
    register_fonts()
    ensure_supported_text(worksheet_title, bold=True)
    width, height = APPENDIX_PAGE_SIZE
    content_width = width - 2 * APPENDIX_MARGIN
    output = io.BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=APPENDIX_PAGE_SIZE,
        invariant=1,
        pageCompression=1,
    )
    pdf.setTitle("Claros attached answer pages")
    global_page_count = 0
    evidence: list[AppendixRenderEvidence] = []

    def begin_page(entry: AppendixEntry, *, continued: bool) -> float:
        nonlocal global_page_count
        global_page_count += 1
        pdf.setFillColor(APPENDIX_TEXT_COLOR)
        pdf.setFont(BOLD_FONT_NAME, 10)
        pdf.drawString(APPENDIX_MARGIN, height - 50, "Claros attached answer page")
        pdf.setFont(BOLD_FONT_NAME, 16)
        title_lines = _wrapped_lines(worksheet_title, content_width, BOLD_FONT_NAME, 16)
        cursor = height - 78
        for line in title_lines:
            pdf.drawString(APPENDIX_MARGIN, cursor, line)
            cursor -= 20
        pdf.setFont(BOLD_FONT_NAME, 12)
        suffix = " — continued" if continued else ""
        question_label = f"{entry.display_identifier}{suffix}"
        for line in _wrapped_lines(question_label, content_width, BOLD_FONT_NAME, 12):
            pdf.drawString(APPENDIX_MARGIN, cursor - 4, line)
            cursor -= 17
        pdf.setFont(REGULAR_FONT_NAME, 10)
        pdf.drawString(APPENDIX_MARGIN, cursor - 2, f"Source page {entry.source_page_number}")
        cursor -= 28
        pdf.setFont(BOLD_FONT_NAME, 10)
        pdf.drawString(APPENDIX_MARGIN, cursor, "Exact source question")
        cursor -= 16
        pdf.setFont(REGULAR_FONT_NAME, 11)
        for line in _wrapped_lines(entry.exact_question, content_width, REGULAR_FONT_NAME, 11):
            if cursor < 120:
                pdf.setFont(REGULAR_FONT_NAME, 9)
                pdf.drawRightString(
                    width - APPENDIX_MARGIN,
                    34,
                    f"Attached page {global_page_count}",
                )
                pdf.showPage()
                cursor = begin_page(entry, continued=True)
                pdf.setFont(BOLD_FONT_NAME, 10)
                pdf.drawString(APPENDIX_MARGIN, cursor, "Exact source question (continued)")
                cursor -= 16
                pdf.setFont(REGULAR_FONT_NAME, 11)
            pdf.drawString(APPENDIX_MARGIN, cursor, line)
            cursor -= 14
        cursor -= 10
        pdf.setFont(BOLD_FONT_NAME, 10)
        pdf.drawString(APPENDIX_MARGIN, cursor, "Exact approved answer")
        return cursor - 18

    for entry in entries:
        for value, bold in (
            (entry.display_identifier, True),
            (entry.exact_question, False),
            (entry.exact_answer, False),
        ):
            ensure_supported_text(value, bold=bold)
        first_page = global_page_count
        cursor = begin_page(entry, continued=False)
        answer_lines = _wrapped_lines(
            entry.exact_answer,
            content_width,
            REGULAR_FONT_NAME,
            APPENDIX_FONT_SIZE_MPT / 1000,
        )
        rendered_lines: list[str] = []
        pdf.setFont(REGULAR_FONT_NAME, APPENDIX_FONT_SIZE_MPT / 1000)
        for line in answer_lines:
            if cursor < 58:
                pdf.setFont(REGULAR_FONT_NAME, 9)
                pdf.drawRightString(
                    width - APPENDIX_MARGIN,
                    34,
                    f"Attached page {global_page_count}",
                )
                pdf.showPage()
                cursor = begin_page(entry, continued=True)
                pdf.setFont(BOLD_FONT_NAME, 10)
                pdf.drawString(APPENDIX_MARGIN, cursor, "Exact approved answer (continued)")
                cursor -= 18
                pdf.setFont(REGULAR_FONT_NAME, APPENDIX_FONT_SIZE_MPT / 1000)
            pdf.drawString(APPENDIX_MARGIN, cursor, line)
            rendered_lines.append(line)
            cursor -= APPENDIX_LEADING_MPT / 1000
        pdf.setFont(REGULAR_FONT_NAME, 9)
        pdf.drawRightString(width - APPENDIX_MARGIN, 34, f"Attached page {global_page_count}")
        pdf.showPage()
        evidence.append(
            AppendixRenderEvidence(
                question_id=entry.question_id,
                first_page_offset=first_page,
                page_count=global_page_count - first_page,
                exact_answer_sha256=sha256_hex(entry.exact_answer.encode("utf-8")),
                rendered_answer_lines=tuple(rendered_lines),
            )
        )
    pdf.save()
    payload = output.getvalue()
    if not payload.startswith(b"%PDF-"):
        raise document_error("invalid_export")
    return AppendixRenderResult(
        pdf_bytes=payload,
        page_count=global_page_count,
        entries=tuple(evidence),
    )


def assemble_derivative(
    source_pdf: bytes,
    document: PhysicalDocumentIR,
    inline_plans: Sequence[PlacementPlan],
    appendix: AppendixRenderResult,
) -> bytes:
    """Clone source pages in order, merge transparent overlays, then append pages."""

    try:
        source_reader = PdfReader(io.BytesIO(source_pdf), strict=True)
        if len(source_reader.pages) != len(document.pages):
            raise document_error("stale_source")
        by_page: dict[int, list[PlacementPlan]] = {}
        for plan in inline_plans:
            if plan.region is None:
                raise document_error("invalid_export")
            by_page.setdefault(plan.region.page_index, []).append(plan)
        writer = PdfWriter()
        for page_index, source_page in enumerate(source_reader.pages):
            if page_index in by_page:
                overlay_bytes = render_inline_overlay(
                    document.pages[page_index],
                    by_page[page_index],
                )
                overlay_page = PdfReader(io.BytesIO(overlay_bytes), strict=True).pages[0]
                source_page.merge_page(overlay_page, over=True)
            writer.add_page(source_page)
        if source_reader.metadata:
            metadata = {
                str(key): str(value)
                for key, value in source_reader.metadata.items()
                if value is not None and str(key).startswith("/")
            }
            if metadata:
                writer.add_metadata(metadata)
        if appendix.page_count:
            appendix_reader = PdfReader(io.BytesIO(appendix.pdf_bytes), strict=True)
            if len(appendix_reader.pages) != appendix.page_count:
                raise document_error("invalid_export")
            for page in appendix_reader.pages:
                writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        payload = output.getvalue()
    except Exception as error:
        if isinstance(error, DocumentEngineError):
            raise
        raise document_error("invalid_export") from error
    if not payload.startswith(b"%PDF-") or sha256_hex(source_pdf) != document.source_sha256:
        raise document_error("invalid_export")
    return payload
