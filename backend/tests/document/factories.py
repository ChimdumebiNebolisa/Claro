"""Small deterministic PDF and physical-IR fixtures for document tests."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass, field
from typing import Any, Literal

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.document.models import (
    AffineTransformMpt,
    CanonicalBox,
    PdfBoxMpt,
    PhysicalBlock,
    PhysicalDocumentIR,
    PhysicalPage,
    sha256_hex,
)


def worksheet_pdf(
    questions: tuple[str, ...] = (
        "1. Why do plants need sunlight?",
        "2. How does sunlight help a plant make food?",
    ),
    *,
    page_count: int = 1,
    answer_regions: Literal["rect", "lines", "none"] = "rect",
    invariant: bool = True,
) -> bytes:
    """Render a native-text worksheet with predictable answer regions."""

    output = io.BytesIO()
    pdf = canvas.Canvas(
        output,
        pagesize=letter,
        invariant=int(invariant),
        pageCompression=1,
    )
    for page_index in range(page_count):
        pdf.setFont("Helvetica", 12)
        if page_index == 0:
            for index, question in enumerate(questions):
                prompt_y = 740 - index * 240
                pdf.drawString(54, prompt_y, question)
                if answer_regions == "rect":
                    pdf.rect(54, prompt_y - 120, 504, 70, stroke=1, fill=0)
                elif answer_regions == "lines":
                    pdf.line(54, prompt_y - 75, 558, prompt_y - 75)
                    pdf.line(54, prompt_y - 105, 558, prompt_y - 105)
        else:
            pdf.drawString(54, 740, f"Worksheet continuation page {page_index + 1}")
        pdf.showPage()
    pdf.save()
    return output.getvalue()


def blank_pdf() -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1, pageCompression=1)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


@dataclass(frozen=True, slots=True)
class BlockSpec:
    label: str
    kind: Literal["text", "line", "rect", "shape", "form_field", "image"]
    bbox: tuple[int, int, int, int]
    text: str | None = None
    join_after: Literal["none", "space", "newline"] = "none"
    values: dict[str, Any] = field(default_factory=dict)


def _block_id(label: str, index: int) -> str:
    digest = hashlib.sha256(f"{index}:{label}".encode()).hexdigest()
    return f"blk_{digest[:32]}"


def make_document(
    specs: tuple[BlockSpec, ...],
    *,
    source_bytes: bytes = b"manual deterministic source",
    rotation: int = 0,
    user_unit: str = "1",
    media_box: tuple[int, int, int, int] = (0, 0, 612_000, 792_000),
    crop_box: tuple[int, int, int, int] | None = None,
) -> tuple[PhysicalDocumentIR, dict[str, PhysicalBlock]]:
    """Build valid one-page evidence without involving a parser."""

    resolved_crop = crop_box or media_box
    crop = PdfBoxMpt(*resolved_crop)
    media = PdfBoxMpt(*media_box)
    if rotation == 0:
        width, height = crop.width, crop.height
        transform = AffineTransformMpt(1, 0, 0, -1, crop.x0, crop.y1)
    elif rotation == 90:
        width, height = crop.height, crop.width
        transform = AffineTransformMpt(0, 1, 1, 0, crop.x0, crop.y0)
    elif rotation == 180:
        width, height = crop.width, crop.height
        transform = AffineTransformMpt(-1, 0, 0, 1, crop.x1, crop.y0)
    elif rotation == 270:
        width, height = crop.height, crop.width
        transform = AffineTransformMpt(0, -1, -1, 0, crop.x1, crop.y1)
    else:
        raise ValueError("rotation must be a PDF quarter turn")

    blocks: list[PhysicalBlock] = []
    by_label: dict[str, PhysicalBlock] = {}
    for index, spec in enumerate(specs):
        block = PhysicalBlock(
            id=_block_id(spec.label, index),
            kind=spec.kind,
            page_index=0,
            reading_order=index,
            bbox=CanonicalBox(*spec.bbox),
            text=spec.text,
            join_after=spec.join_after,
            **spec.values,
        )
        blocks.append(block)
        by_label[spec.label] = block

    page_flags: set[str] = set()
    if rotation:
        page_flags.add("non_identity_rotation")
    if crop != media:
        page_flags.add("non_default_crop_box")
    if user_unit != "1":
        page_flags.add("non_unit_user_unit")
    source_sha256 = sha256_hex(source_bytes)
    document = PhysicalDocumentIR(
        document_id=f"doc_{source_sha256[:24]}",
        source_sha256=source_sha256,
        normalization_sha256=sha256_hex(b"normalized:" + source_bytes),
        source_size_bytes=len(source_bytes),
        pages=(
            PhysicalPage(
                page_index=0,
                media_box_mpt=media,
                crop_box_mpt=crop,
                width_mpt=width,
                height_mpt=height,
                rotation=rotation,
                user_unit=user_unit,
                canonical_to_pdf_mpt=transform,
                blocks=tuple(blocks),
                ambiguity_flags=tuple(sorted(page_flags)),
            ),
        ),
        ambiguity_flags=tuple(sorted(page_flags)),
    )
    return document, by_label
