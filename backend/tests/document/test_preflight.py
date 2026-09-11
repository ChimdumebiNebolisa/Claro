"""Admission, normalization, and page-coordinate contract tests."""

from __future__ import annotations

import io

import pikepdf
import pytest
from pypdf import PdfWriter

from backend.document import (
    DocumentEngineError,
    PreflightLimits,
    QuestionEvidence,
    extract_physical_ir,
    preflight_pdf,
    resolve_placement,
)
from backend.document.models import sha256_hex
from backend.document.preflight import finite_number, validate_question_count
from backend.tests.document.factories import blank_pdf, worksheet_pdf


def _failure_code(callable_: object, *args: object, **kwargs: object) -> str:
    with pytest.raises(DocumentEngineError) as raised:
        callable_(*args, **kwargs)  # type: ignore[operator]
    return raised.value.code


def _encrypted_pdf() -> bytes:
    output = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(worksheet_pdf())) as document:
        document.save(
            output,
            encryption=pikepdf.Encryption(owner="owner-secret", user="student-secret", R=6),
        )
    return output.getvalue()


def _transformed_pdf(*, rotation: int = 0, cropped: bool = False) -> bytes:
    output = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(worksheet_pdf(questions=("1. A grounded question?",)))) as pdf:
        page = pdf.pages[0]
        page.obj["/Rotate"] = rotation
        if cropped:
            page.obj["/CropBox"] = pikepdf.Array([18, 18, 594, 774])
        pdf.save(output, deterministic_id=True)
    return output.getvalue()


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"", "invalid_pdf_signature"),
        (b"not a pdf", "invalid_pdf_signature"),
        (b"%PDF-1.7\nbroken", "malformed_pdf"),
    ],
)
def test_rejects_invalid_and_malformed_payloads(payload: bytes, expected: str) -> None:
    assert _failure_code(preflight_pdf, payload) == expected


def test_rejects_oversize_before_parsing() -> None:
    payload = b"%PDF-" + b"x" * 32
    limits = PreflightLimits(max_upload_bytes=16)
    assert _failure_code(preflight_pdf, payload, limits=limits) == "file_too_large"


def test_rejects_encrypted_pdf_without_leaking_parser_details() -> None:
    with pytest.raises(DocumentEngineError) as raised:
        preflight_pdf(_encrypted_pdf())
    assert raised.value.code == "encrypted_pdf"
    assert str(raised.value) == "encrypted_pdf"
    assert "secret" not in raised.value.safe_message.lower()


def test_rejects_zero_pages_page_limit_and_scan_only_pdf() -> None:
    empty_output = io.BytesIO()
    PdfWriter().write(empty_output)

    assert _failure_code(preflight_pdf, empty_output.getvalue()) == "empty_pdf"
    assert (
        _failure_code(
            preflight_pdf,
            worksheet_pdf(page_count=2),
            limits=PreflightLimits(max_pages=1),
        )
        == "page_limit_exceeded"
    )
    assert _failure_code(preflight_pdf, blank_pdf()) == "requires_ocr"


def test_enforces_extracted_native_text_limit() -> None:
    assert (
        _failure_code(
            preflight_pdf,
            worksheet_pdf(questions=("This is selectable worksheet text?",)),
            limits=PreflightLimits(max_extracted_text_bytes=5),
        )
        == "extracted_text_limit_exceeded"
    )


@pytest.mark.parametrize("question_count", [0, 41])
def test_enforces_supported_question_count(question_count: int) -> None:
    assert _failure_code(validate_question_count, question_count) == "question_limit_exceeded"


def test_preflight_is_deterministic_and_source_bytes_are_immutable() -> None:
    source = worksheet_pdf()
    before = bytes(source)
    first = preflight_pdf(source)
    second = preflight_pdf(source)

    assert source == before
    assert first.source_sha256 == sha256_hex(source)
    assert first.normalized_pdf == second.normalized_pdf
    assert first.normalization_sha256 == second.normalization_sha256
    assert first.pages == second.pages
    assert first.extracted_text_bytes > 0


@pytest.mark.parametrize("rotation", [90, 180, 270])
def test_rotation_is_canonicalized_and_flagged(rotation: int) -> None:
    source = _transformed_pdf(rotation=rotation)
    result = preflight_pdf(source)
    page = result.pages[0]

    assert page.rotation == rotation
    assert "non_identity_rotation" in page.ambiguity_flags
    assert page.has_identity_inline_transform is False
    canonical_corners = (
        (0, 0),
        (0, page.height_mpt),
        (page.width_mpt, 0),
        (page.width_mpt, page.height_mpt),
    )
    for canonical in canonical_corners:
        pdf_point = page.canonical_to_pdf_mpt.apply(*canonical)
        assert page.canonical_to_pdf_mpt.inverse_apply(*pdf_point) == canonical


def test_crop_relative_coordinates_are_integer_milli_points() -> None:
    source = _transformed_pdf(cropped=True)
    preflight = preflight_pdf(source)
    page = preflight.pages[0]

    assert page.crop_box_mpt.to_list() == [18_000, 18_000, 594_000, 774_000]
    assert (page.width_mpt, page.height_mpt) == (576_000, 756_000)
    assert page.canonical_to_pdf_mpt.to_list() == [1, 0, 0, -1, 18_000, 774_000]
    assert "non_default_crop_box" in page.ambiguity_flags
    assert page.has_identity_inline_transform is False

    document = extract_physical_ir(source, preflight=preflight)
    assert document.pages[0].width_mpt == 576_000
    assert document.pages[0].height_mpt == 756_000
    assert all(block.bbox.within(576_000, 756_000) for block in document.pages[0].blocks)
    prompt = next(block for block in document.pages[0].blocks if block.kind == "text")
    assert 34_000 <= prompt.bbox.x0 <= 38_000


def test_extracted_rotated_and_cropped_page_is_appendix_only() -> None:
    source = _transformed_pdf(rotation=90, cropped=True)
    document = extract_physical_ir(source)
    prompt = next(block for block in document.pages[0].blocks if block.kind == "text")
    evidence = QuestionEvidence(
        question_id="question-1",
        display_identifier="Question 1",
        prompt_block_ids=(prompt.id,),
    )

    plan = resolve_placement(document, evidence, "A grounded exact answer.")
    assert {"non_identity_rotation", "non_default_crop_box"}.issubset(
        document.pages[0].ambiguity_flags
    )
    assert plan.outcome == "appendix"
    assert plan.region is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), "nan"])
def test_non_finite_parser_numbers_are_rejected(value: object) -> None:
    assert _failure_code(finite_number, value) == "invalid_physical_evidence"
