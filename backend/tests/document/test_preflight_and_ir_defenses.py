"""Fail-closed PDF admission and persisted-IR defensive paths."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import replace
from decimal import Decimal
from typing import Any

import pikepdf
import pytest
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from backend.document import (
    DocumentEngineError,
    extract_physical_ir,
    parse_physical_ir,
    preflight_pdf,
)
from backend.document.models import canonical_json_bytes, sha256_hex
from backend.document.physical_ir import _canonical_box_from_plumber
from backend.document.preflight import (
    PreflightLimits,
    _page_box,
    finite_number,
    validate_question_count,
)
from backend.tests.document.conftest import ExtractedWorksheet
from backend.tests.document.factories import worksheet_pdf


def _assert_code(expected: str, action: Any) -> None:
    with pytest.raises(DocumentEngineError) as raised:
        action()
    assert raised.value.code == expected


def _rewrite_pdf(source: bytes, mutate: Any) -> bytes:
    output = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(source)) as pdf:
        mutate(pdf.pages[0])
        pdf.save(output, deterministic_id=True)
    return output.getvalue()


def _rehash_ir(raw: dict[str, Any]) -> bytes:
    body = {key: value for key, value in raw.items() if key != "ir_sha256"}
    raw["ir_sha256"] = sha256_hex(canonical_json_bytes(body))
    return canonical_json_bytes(raw)


def _rich_source() -> bytes:
    one_pixel_png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
        "AScY42YAAAAASUVORK5CYII="
    )
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1, pageCompression=1)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(54, 740, "1. Which evidence belongs here?")
    pdf.bezier(54, 600, 160, 660, 300, 540, 558, 600)
    pdf.drawImage(ImageReader(io.BytesIO(one_pixel_png)), 500, 700, 20, 20)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def _mixed_annotation_source() -> bytes:
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter, invariant=1, pageCompression=1)
    pdf.setFont("Helvetica", 12)
    pdf.drawString(54, 740, "1. Which field is writable?")
    pdf.acroForm.textfield(
        name="limited-answer",
        x=54,
        y=620,
        width=300,
        height=70,
        maxlen=12,
        fieldFlags="readOnly multiline",
        forceBorder=True,
    )
    pdf.acroForm.checkbox(name="not-text", x=380, y=630, buttonStyle="check")
    pdf.linkURL("https://example.invalid", (54, 570, 200, 590), relative=0)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def test_preflight_limit_configuration_and_scalar_inputs_fail_closed() -> None:
    with pytest.raises(ValueError, match="positive"):
        PreflightLimits(max_pages=0)
    with pytest.raises(TypeError, match="must be bytes"):
        preflight_pdf(bytearray(b"%PDF-"))  # type: ignore[arg-type]
    _assert_code("invalid_physical_evidence", lambda: finite_number(object()))
    assert finite_number("1.25") == 1.25
    validate_question_count(1)
    validate_question_count(40)


def test_preflight_rejects_invalid_page_dictionary_values() -> None:
    source = worksheet_pdf(questions=("A grounded question?",))
    mutations = (
        ("zero-user-unit", lambda page: page.obj.__setitem__("/UserUnit", 0)),
        (
            "crop-outside-media",
            lambda page: page.obj.__setitem__("/CropBox", pikepdf.Array([0, 0, 700, 792])),
        ),
        ("non-quarter-rotation", lambda page: page.obj.__setitem__("/Rotate", 45)),
        (
            "nonnumeric-rotation",
            lambda page: page.obj.__setitem__("/Rotate", pikepdf.String("quarter-turn")),
        ),
    )
    for label, mutate in mutations:
        malformed = _rewrite_pdf(source, mutate)
        try:
            preflight_pdf(malformed)
        except DocumentEngineError as error:
            assert error.code == "invalid_physical_evidence", label
        else:
            pytest.fail(f"preflight accepted malformed {label}")


def test_preflight_scales_nonunit_user_space_and_flags_it() -> None:
    source = _rewrite_pdf(
        worksheet_pdf(questions=("A grounded question?",)),
        lambda page: page.obj.__setitem__("/UserUnit", 1.5),
    )
    result = preflight_pdf(source)

    assert result.pages[0].user_unit == "1.5"
    assert result.pages[0].media_box_mpt.to_list() == [0, 0, 918_000, 1_188_000]
    assert result.pages[0].has_identity_inline_transform is False
    assert "non_unit_user_unit" in result.ambiguity_flags


def test_preflight_detects_encryption_even_with_empty_user_password() -> None:
    output = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(worksheet_pdf())) as pdf:
        pdf.save(
            output,
            encryption=pikepdf.Encryption(owner="owner-secret", user="", R=6),
        )

    _assert_code("encrypted_pdf", lambda: preflight_pdf(output.getvalue()))


def test_preflight_maps_normalization_and_text_parser_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = worksheet_pdf()

    def fail_save(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic write failure")

    monkeypatch.setattr(pikepdf.Pdf, "save", fail_save)
    _assert_code("malformed_pdf", lambda: preflight_pdf(source))
    monkeypatch.undo()

    monkeypatch.setattr("backend.document.preflight._normalize", lambda _pdf: b"not-a-pdf")
    _assert_code("malformed_pdf", lambda: preflight_pdf(source))
    monkeypatch.undo()

    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic text parser failure")

    monkeypatch.setattr("backend.document.preflight.pdfplumber.open", fail_open)
    _assert_code("malformed_pdf", lambda: preflight_pdf(source))


def test_coordinate_adapter_rejects_missing_nonfinite_and_out_of_bounds_values() -> None:
    page = preflight_pdf(worksheet_pdf()).pages[0]
    _assert_code(
        "invalid_physical_evidence",
        lambda: _page_box(object(), Decimal(1)),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: _page_box([0, 0, 612], Decimal(1)),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: _canonical_box_from_plumber(
            {"x1": 1, "top": 1, "bottom": 2},
            page,
            allow_zero_axis=False,
        ),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: _canonical_box_from_plumber(
            {"x0": "NaN", "x1": 1, "top": 1, "bottom": 2},
            page,
            allow_zero_axis=False,
        ),
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: _canonical_box_from_plumber(
            {"x0": 0, "x1": 700, "top": 1, "bottom": 2},
            page,
            allow_zero_axis=False,
        ),
    )
    expanded = _canonical_box_from_plumber(
        {"x0": 10, "x1": 10, "top": 20, "bottom": 20},
        page,
        allow_zero_axis=False,
    )
    assert (expanded.width, expanded.height) == (1, 1)


def test_extractor_records_curves_and_image_dimensions() -> None:
    document = extract_physical_ir(_rich_source())
    page = document.pages[0]
    curve = next(block for block in page.blocks if block.kind == "shape")
    image = next(block for block in page.blocks if block.kind == "image")

    assert curve.ambiguity_flags == ("curve_bbox_only",)
    assert "curves_present" in page.ambiguity_flags
    assert image.image_width == 1
    assert image.image_height == 1


def test_extractor_skips_nontext_annotations_and_reads_text_field_flags() -> None:
    document = extract_physical_ir(_mixed_annotation_source())
    fields = [block for block in document.pages[0].blocks if block.kind == "form_field"]

    assert len(fields) == 1
    assert fields[0].field_name == "limited-answer"
    assert fields[0].writable is False
    assert fields[0].multiline is True
    assert fields[0].max_length == 12


def test_extractor_rejects_malformed_widget_rectangle() -> None:
    source = _mixed_annotation_source()

    def break_widget(page: pikepdf.Page) -> None:
        annotations = page.obj["/Annots"]
        text_widget = next(item for item in annotations if str(item.get("/FT", "")) == "/Tx")
        text_widget["/Rect"] = pikepdf.Array([1, 2, 3])

    malformed = _rewrite_pdf(source, break_widget)
    _assert_code("invalid_physical_evidence", lambda: extract_physical_ir(malformed))


@pytest.mark.parametrize("rotation", [180, 270])
def test_extractor_preserves_text_order_for_inverted_pages(rotation: int) -> None:
    source = _rewrite_pdf(
        worksheet_pdf(questions=("A rotated grounded question?",)),
        lambda page: page.obj.__setitem__("/Rotate", rotation),
    )
    document = extract_physical_ir(source)

    texts = [block.text for block in document.pages[0].blocks if block.kind == "text"]
    assert texts == ["A rotated grounded question?"]
    assert "non_identity_rotation" in document.pages[0].ambiguity_flags


def test_extractor_rejects_preflight_page_mismatch_and_parser_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    two_page_source = worksheet_pdf(page_count=2)
    two_page_preflight = preflight_pdf(two_page_source)
    one_page_preflight = preflight_pdf(worksheet_pdf(page_count=1))
    mismatched = replace(
        two_page_preflight,
        normalized_pdf=one_page_preflight.normalized_pdf,
        normalization_sha256=one_page_preflight.normalization_sha256,
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: extract_physical_ir(two_page_source, preflight=mismatched),
    )

    def fail_open(*_args: object, **_kwargs: object) -> None:
        raise OSError("synthetic physical parser failure")

    monkeypatch.setattr("backend.document.physical_ir.pdfplumber.open", fail_open)
    _assert_code(
        "invalid_physical_evidence",
        lambda: extract_physical_ir(two_page_source, preflight=two_page_preflight),
    )


def test_persisted_ir_rejects_invalid_root_shapes_and_types(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    parser_cases: tuple[object, ...] = (
        bytearray(extracted_worksheet.document.canonical_bytes()),
        b"\xff",
        b"{broken",
        b"[]",
        b'{"value":NaN}',
    )
    for payload in parser_cases:
        if isinstance(payload, bytearray):
            with pytest.raises(TypeError, match="must be bytes"):
                parse_physical_ir(payload)  # type: ignore[arg-type]
        else:
            _assert_code("stale_physical_ir", lambda payload=payload: parse_physical_ir(payload))

    for key, value in (
        ("document_id", 7),
        ("source_sha256", []),
        ("normalization_sha256", None),
        ("ir_sha256", False),
        ("ambiguity_flags", "not-a-list"),
        ("pages", "not-a-list"),
    ):
        raw = json.loads(extracted_worksheet.document.canonical_bytes())
        raw[key] = value
        payload = canonical_json_bytes(raw) if key == "ir_sha256" else _rehash_ir(raw)
        _assert_code("stale_physical_ir", lambda payload=payload: parse_physical_ir(payload))


def test_persisted_ir_rejects_invalid_page_and_block_members(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    base = json.loads(extracted_worksheet.document.canonical_bytes())

    def rejected(mutator: Any) -> None:
        raw = json.loads(canonical_json_bytes(base))
        mutator(raw)
        _assert_code("stale_physical_ir", lambda: parse_physical_ir(_rehash_ir(raw)))

    rejected(lambda raw: raw["pages"].__setitem__(0, "not-a-page"))
    rejected(lambda raw: raw["pages"][0].__setitem__("page_number", 9))
    rejected(lambda raw: raw["pages"][0].__setitem__("canonical_to_pdf_mpt", [1, 0]))
    rejected(lambda raw: raw["pages"][0].__setitem__("ambiguity_flags", "bad"))
    rejected(lambda raw: raw["pages"][0].__setitem__("blocks", "bad"))
    rejected(lambda raw: raw["pages"][0].__setitem__("user_unit", 1))

    rejected(lambda raw: raw["pages"][0]["blocks"].__setitem__(0, "not-a-block"))
    rejected(lambda raw: raw["pages"][0]["blocks"][0].pop("id"))
    rejected(lambda raw: raw["pages"][0]["blocks"][0].__setitem__("ambiguity_flags", "bad"))
    rejected(lambda raw: raw["pages"][0]["blocks"][0].__setitem__("writable", 1))
    rejected(lambda raw: raw["pages"][0]["blocks"][0].__setitem__("field_name", 7))
    rejected(lambda raw: raw["pages"][0]["blocks"][0].__setitem__("max_length", True))
    rejected(lambda raw: raw["pages"][0]["blocks"][0].__setitem__("bbox_mpt", [1, 2, 3]))
