"""Canonical physical-IR extraction and strict persistence tests."""

from __future__ import annotations

import io
import json

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from backend.document import (
    DocumentEngineError,
    extract_physical_ir,
    parse_physical_ir,
    preflight_pdf,
)
from backend.document.fonts import REGULAR_FONT_NAME, register_fonts
from backend.document.models import canonical_json_bytes, sha256_hex
from backend.tests.document.factories import BlockSpec, make_document, worksheet_pdf


def _error_code(callable_: object, *args: object, **kwargs: object) -> str:
    with pytest.raises(DocumentEngineError) as raised:
        callable_(*args, **kwargs)  # type: ignore[operator]
    return raised.value.code


def _rehash_ir(raw: dict[str, object]) -> bytes:
    body = {key: value for key, value in raw.items() if key != "ir_sha256"}
    raw["ir_sha256"] = sha256_hex(canonical_json_bytes(body))
    return canonical_json_bytes(raw)


def _unicode_source() -> bytes:
    register_fonts()
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1, pageCompression=1)
    pdf.setFont(REGULAR_FONT_NAME, 12)
    pdf.drawString(54, 740, "¿Por qué conservamos café, CO₂, H₂O, and naïve exactly?")
    pdf.rect(54, 620, 504, 70, stroke=1, fill=0)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _form_source() -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1, pageCompression=1)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(54, 740, "1. What belongs in this writable field?")
    pdf.acroForm.textfield(
        name="answer-1",
        x=54,
        y=620,
        width=504,
        height=70,
        borderWidth=1,
        forceBorder=True,
        fieldFlags="multiline",
    )
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def test_extraction_is_byte_deterministic_with_stable_block_ids() -> None:
    source = worksheet_pdf(answer_regions="lines")
    first = extract_physical_ir(source)
    second = extract_physical_ir(source)

    assert first == second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.ir_sha256 == second.ir_sha256
    assert first.document_id == f"doc_{sha256_hex(source)[:24]}"
    assert [block.id for block in first.pages[0].blocks] == [
        block.id for block in second.pages[0].blocks
    ]
    assert {block.kind for block in first.pages[0].blocks} >= {"text", "line"}
    assert [block.reading_order for block in first.pages[0].blocks] == list(
        range(len(first.pages[0].blocks))
    )


def test_extraction_preserves_exact_utf8_text() -> None:
    source = _unicode_source()
    document = extract_physical_ir(source)
    prompt = next(block for block in document.pages[0].blocks if block.kind == "text")

    assert prompt.text == "¿Por qué conservamos café, CO₂, H₂O, and naïve exactly?"
    assert document.reconstruct_text((prompt.id,)) == prompt.text
    assert prompt.text.encode("utf-8") in document.canonical_bytes()


def test_extracts_writable_form_field_metadata() -> None:
    document = extract_physical_ir(_form_source())
    fields = [block for block in document.pages[0].blocks if block.kind == "form_field"]

    assert len(fields) == 1
    field = fields[0]
    assert field.field_name == "answer-1"
    assert field.writable is True
    assert field.multiline is True
    assert field.bbox.width == 504_000
    assert field.bbox.height == 70_000


def test_canonical_ir_round_trips_only_as_exact_canonical_bytes() -> None:
    document = extract_physical_ir(worksheet_pdf())
    payload = document.canonical_bytes()

    assert parse_physical_ir(payload) == document
    assert _error_code(parse_physical_ir, b" " + payload) == "stale_physical_ir"

    with_unknown = json.loads(payload)
    with_unknown["invented_geometry"] = []
    assert _error_code(parse_physical_ir, canonical_json_bytes(with_unknown)) == "stale_physical_ir"

    duplicate_key = payload.replace(
        b'"schema_version":1',
        b'"schema_version":1,"schema_version":1',
        1,
    )
    assert _error_code(parse_physical_ir, duplicate_key) == "stale_physical_ir"


def test_ir_hash_version_and_bounds_tampering_are_rejected() -> None:
    document = extract_physical_ir(worksheet_pdf())

    bad_hash = json.loads(document.canonical_bytes())
    bad_hash["ir_sha256"] = "0" * 64
    assert _error_code(parse_physical_ir, canonical_json_bytes(bad_hash)) == "stale_physical_ir"

    stale_version = json.loads(document.canonical_bytes())
    stale_version["parser_version"] = "future-parser"
    assert _error_code(parse_physical_ir, _rehash_ir(stale_version)) == "stale_physical_ir"

    out_of_bounds = json.loads(document.canonical_bytes())
    page = out_of_bounds["pages"][0]
    page["blocks"][0]["bbox_mpt"][2] = page["width_mpt"] + 1
    assert _error_code(parse_physical_ir, _rehash_ir(out_of_bounds)) == "stale_physical_ir"


def test_ir_rejects_duplicate_ids_and_non_integral_coordinates() -> None:
    document = extract_physical_ir(worksheet_pdf())

    duplicate = json.loads(document.canonical_bytes())
    blocks = duplicate["pages"][0]["blocks"]
    blocks[1]["id"] = blocks[0]["id"]
    assert _error_code(parse_physical_ir, _rehash_ir(duplicate)) == "stale_physical_ir"

    fractional = json.loads(document.canonical_bytes())
    fractional["pages"][0]["blocks"][0]["bbox_mpt"][0] = 1.5
    assert _error_code(parse_physical_ir, _rehash_ir(fractional)) == "stale_physical_ir"


def test_exact_reconstruction_obeys_explicit_joiners() -> None:
    document, blocks = make_document(
        (
            BlockSpec("a", "text", (40_000, 40_000, 180_000, 60_000), "Why do", "space"),
            BlockSpec("b", "text", (180_000, 40_000, 360_000, 60_000), "plants grow?", "newline"),
            BlockSpec("c", "text", (40_000, 70_000, 300_000, 90_000), "Context: café & CO₂"),
        )
    )

    assert document.reconstruct_text((blocks["a"].id, blocks["b"].id, blocks["c"].id)) == (
        "Why do plants grow?\nContext: café & CO₂"
    )
    assert (
        _error_code(
            document.reconstruct_text,
            (blocks["b"].id, blocks["a"].id),
        )
        == "unsafe_question_evidence"
    )
    assert (
        _error_code(
            document.reconstruct_text,
            (blocks["a"].id, blocks["a"].id),
        )
        == "unsafe_question_evidence"
    )


def test_reusing_preflight_for_different_source_fails_closed() -> None:
    first = worksheet_pdf(questions=("A first grounded question?",))
    second = worksheet_pdf(questions=("A different grounded question?",))
    stale = preflight_pdf(first)

    assert _error_code(extract_physical_ir, second, preflight=stale) == "stale_source"
