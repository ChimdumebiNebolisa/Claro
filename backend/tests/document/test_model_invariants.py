"""Public value-object and font-safety invariants."""

from __future__ import annotations

from typing import Any

import pytest

from backend.document.errors import DocumentEngineError, document_error
from backend.document.fonts import ensure_supported_text
from backend.document.models import (
    AffineTransformMpt,
    CanonicalBox,
    PdfBoxMpt,
    PhysicalBlock,
    PhysicalDocumentIR,
    PhysicalPage,
)


def _assert_code(expected: str, factory: Any) -> None:
    with pytest.raises(DocumentEngineError) as raised:
        factory()
    assert raised.value.code == expected


def _text_block(
    *,
    block_id: str = "blk_" + "1" * 32,
    page_index: int = 0,
    reading_order: int = 0,
    bbox: CanonicalBox | None = None,
    text: str | None = "Question?",
    join_after: str = "none",
    ambiguity_flags: tuple[str, ...] = (),
) -> PhysicalBlock:
    return PhysicalBlock(
        id=block_id,
        kind="text",
        page_index=page_index,
        reading_order=reading_order,
        bbox=bbox or CanonicalBox(10_000, 10_000, 120_000, 30_000),
        text=text,
        join_after=join_after,  # type: ignore[arg-type]
        ambiguity_flags=ambiguity_flags,
    )


def _page(
    *,
    page_index: int = 0,
    blocks: tuple[PhysicalBlock, ...] = (),
    width_mpt: int = 612_000,
    height_mpt: int = 792_000,
    rotation: int = 0,
    user_unit: str = "1",
    ambiguity_flags: tuple[str, ...] = (),
) -> PhysicalPage:
    return PhysicalPage(
        page_index=page_index,
        media_box_mpt=PdfBoxMpt(0, 0, 612_000, 792_000),
        crop_box_mpt=PdfBoxMpt(0, 0, 612_000, 792_000),
        width_mpt=width_mpt,
        height_mpt=height_mpt,
        rotation=rotation,
        user_unit=user_unit,
        canonical_to_pdf_mpt=AffineTransformMpt(1, 0, 0, -1, 0, 792_000),
        blocks=blocks,
        ambiguity_flags=ambiguity_flags,
    )


def _document(
    *,
    pages: tuple[PhysicalPage, ...] | None = None,
    document_id: str = "doc_" + "1" * 24,
    source_sha256: str = "a" * 64,
    normalization_sha256: str = "b" * 64,
    source_size_bytes: int = 100,
    ambiguity_flags: tuple[str, ...] = (),
) -> PhysicalDocumentIR:
    return PhysicalDocumentIR(
        document_id=document_id,
        source_sha256=source_sha256,
        normalization_sha256=normalization_sha256,
        source_size_bytes=source_size_bytes,
        pages=pages if pages is not None else (_page(),),
        ambiguity_flags=ambiguity_flags,
    )


def test_pdf_and_canonical_boxes_reject_non_integral_or_degenerate_geometry() -> None:
    _assert_code("invalid_physical_evidence", lambda: PdfBoxMpt(True, 0, 1, 1))
    _assert_code("invalid_physical_evidence", lambda: PdfBoxMpt(0, 0, 0, 1))
    _assert_code("invalid_physical_evidence", lambda: PdfBoxMpt(0, 2, 1, 1))
    _assert_code("invalid_physical_evidence", lambda: CanonicalBox(False, 0, 1, 1))
    _assert_code("invalid_physical_evidence", lambda: CanonicalBox(-1, 0, 1, 1))
    _assert_code("invalid_physical_evidence", lambda: CanonicalBox(2, 0, 1, 1))
    _assert_code("invalid_physical_evidence", lambda: CanonicalBox(1, 1, 1, 1))
    _assert_code("invalid_physical_evidence", lambda: CanonicalBox.union(()))

    box = CanonicalBox(10, 20, 30, 50)
    assert (box.width, box.height, box.area) == (20, 30, 600)
    assert not box.intersects(CanonicalBox(30, 20, 40, 50))
    assert not box.intersects(CanonicalBox(0, 20, 10, 50))
    assert not box.intersects(CanonicalBox(10, 50, 30, 60))
    assert not box.intersects(CanonicalBox(10, 0, 30, 20))
    assert box.intersects(CanonicalBox(30, 20, 40, 50), clearance_mpt=1)


def test_affine_transform_requires_integer_unit_determinant() -> None:
    _assert_code(
        "invalid_physical_evidence",
        lambda: AffineTransformMpt(True, 0, 0, 1, 0, 0),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: AffineTransformMpt(2, 0, 0, 1, 0, 0),
    )
    transform = AffineTransformMpt(0, 1, 1, 0, 18_000, 18_000)
    assert transform.inverse_apply(*transform.apply(12_000, 34_000)) == (12_000, 34_000)


def test_physical_block_rejects_invalid_identity_kind_order_text_and_flags() -> None:
    _assert_code("invalid_physical_evidence", lambda: _text_block(block_id="bad"))
    _assert_code(
        "invalid_physical_evidence",
        lambda: PhysicalBlock(
            id="blk_" + "1" * 32,
            kind="video",  # type: ignore[arg-type]
            page_index=0,
            reading_order=0,
            bbox=CanonicalBox(0, 0, 1, 1),
        ),
    )
    _assert_code("invalid_physical_evidence", lambda: _text_block(page_index=-1))
    _assert_code("invalid_physical_evidence", lambda: _text_block(reading_order=-1))
    _assert_code("invalid_physical_evidence", lambda: _text_block(text=None))
    _assert_code("invalid_physical_evidence", lambda: _text_block(join_after="invalid"))
    _assert_code(
        "invalid_physical_evidence",
        lambda: PhysicalBlock(
            id="blk_" + "1" * 32,
            kind="line",
            page_index=0,
            reading_order=0,
            bbox=CanonicalBox(0, 0, 10, 0),
            text="not allowed",
        ),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: PhysicalBlock(
            id="blk_" + "1" * 32,
            kind="line",
            page_index=0,
            reading_order=0,
            bbox=CanonicalBox(0, 0, 10, 0),
            join_after="space",
        ),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: _text_block(ambiguity_flags=("z", "a", "z")),
    )


def test_physical_page_rejects_invalid_metadata_order_ids_and_bounds() -> None:
    _assert_code("invalid_physical_evidence", lambda: _page(page_index=-1))
    _assert_code("invalid_physical_evidence", lambda: _page(width_mpt=0))
    _assert_code("invalid_physical_evidence", lambda: _page(height_mpt=0))
    _assert_code("invalid_physical_evidence", lambda: _page(rotation=45))
    _assert_code("invalid_physical_evidence", lambda: _page(user_unit=""))
    _assert_code("invalid_physical_evidence", lambda: _page(ambiguity_flags=("z", "a")))
    _assert_code(
        "invalid_physical_evidence",
        lambda: _page(blocks=(_text_block(reading_order=1),)),
    )
    duplicate = (_text_block(), _text_block(reading_order=1))
    _assert_code("invalid_physical_evidence", lambda: _page(blocks=duplicate))
    _assert_code(
        "invalid_physical_evidence",
        lambda: _page(blocks=(_text_block(page_index=1),)),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: _page(blocks=(_text_block(bbox=CanonicalBox(10_000, 10_000, 700_000, 30_000)),)),
    )


def test_physical_document_rejects_invalid_identity_hashes_pages_and_flags() -> None:
    _assert_code("invalid_physical_evidence", lambda: _document(document_id="bad"))
    _assert_code("invalid_physical_evidence", lambda: _document(source_sha256="a" * 63))
    _assert_code("invalid_physical_evidence", lambda: _document(source_sha256="g" * 64))
    _assert_code("invalid_physical_evidence", lambda: _document(source_size_bytes=0))
    _assert_code("invalid_physical_evidence", lambda: _document(pages=()))
    _assert_code(
        "invalid_physical_evidence",
        lambda: _document(pages=(_page(), _page(page_index=2))),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: _document(ambiguity_flags=("z", "a", "z")),
    )

    first = _page(blocks=(_text_block(),))
    second_block = _text_block(page_index=1)
    second = _page(page_index=1, blocks=(second_block,))
    _assert_code("invalid_physical_evidence", lambda: _document(pages=(first, second)))


def test_document_lookup_and_reconstruction_reject_missing_or_nontext_blocks() -> None:
    line = PhysicalBlock(
        id="blk_" + "2" * 32,
        kind="line",
        page_index=0,
        reading_order=1,
        bbox=CanonicalBox(10_000, 40_000, 120_000, 40_000),
        stroked=True,
    )
    document = _document(pages=(_page(blocks=(_text_block(), line)),))

    _assert_code("unsafe_question_evidence", lambda: document.block_by_id("blk_" + "f" * 32))
    _assert_code("unsafe_question_evidence", lambda: document.reconstruct_text((line.id,)))
    assert document.block_by_id(line.id) == line


def test_document_errors_are_content_free_and_preserve_recoverability() -> None:
    failure = document_error("unknown_internal_reason", recoverable=False)

    assert failure.code == "unknown_internal_reason"
    assert failure.safe_message == "Claros could not process this PDF safely."
    assert failure.recoverable is False
    assert str(failure) == "unknown_internal_reason"


def test_font_validation_accepts_line_breaks_and_rejects_control_characters() -> None:
    ensure_supported_text("Café\nCO₂\rH₂O", bold=True)
    _assert_code("unsupported_glyph", lambda: ensure_supported_text("answer\x00text"))
