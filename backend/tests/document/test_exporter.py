"""Derivative-only export, appendix pagination, and publication tests."""

from __future__ import annotations

import io
from dataclasses import replace

import pikepdf
import pytest
from pypdf import PdfReader

from backend.document import (
    ConfirmedAnswerForExport,
    DocumentEngineError,
    QuestionEvidence,
    build_export,
    publish_validated_export,
    resolve_placement,
)
from backend.document.models import sha256_hex
from backend.tests.document.conftest import ExtractedWorksheet

SHORT_EXACT_ANSWER = "Chlorophyll captures sunlight—keeping CO₂ and H₂O exact."
LONG_EXACT_ANSWER = (
    "Café evidence stays naïve—CO₂ and H₂O remain exact through every attached page. " * 150
).strip()


def _confirmed(
    question: QuestionEvidence,
    exact_text: str,
    placement_hash: str,
) -> ConfirmedAnswerForExport:
    return ConfirmedAnswerForExport(
        question_id=question.question_id,
        display_identifier=question.display_identifier,
        prompt_block_ids=question.prompt_block_ids,
        context_block_ids=question.context_block_ids,
        exact_text=exact_text,
        reviewed_placement_hash=placement_hash,
    )


def _answer(
    worksheet: ExtractedWorksheet,
    question_index: int,
    exact_text: str,
) -> ConfirmedAnswerForExport:
    question = worksheet.questions[question_index]
    plan = resolve_placement(worksheet.document, question, exact_text)
    return _confirmed(question, exact_text, plan.placement_hash)


def _error_code(callable_: object, *args: object, **kwargs: object) -> str:
    with pytest.raises(DocumentEngineError) as raised:
        callable_(*args, **kwargs)  # type: ignore[operator]
    return raised.value.code


def test_inline_and_multipage_appendix_export_is_byte_deterministic(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    source_before = bytes(extracted_worksheet.source)
    inline = _answer(extracted_worksheet, 0, SHORT_EXACT_ANSWER)
    appendix = _answer(extracted_worksheet, 1, LONG_EXACT_ANSWER)

    # Reverse input order to prove physical reading order owns the manifest.
    first = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Biology worksheet",
        (appendix, inline),
    )
    second = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Biology worksheet",
        (appendix, inline),
    )

    assert extracted_worksheet.source == source_before
    assert first.pdf_bytes == second.pdf_bytes
    assert first.pdf_sha256 == second.pdf_sha256 == sha256_hex(first.pdf_bytes)
    assert first.manifest.canonical_bytes() == second.manifest.canonical_bytes()
    assert [plan.outcome for plan in first.placement_plans] == ["inline", "appendix"]
    assert first.appendix.page_count >= 2
    assert len(first.appendix.entries) == 1
    assert first.appendix.entries[0].page_count == first.appendix.page_count
    assert first.appendix.entries[0].exact_answer_sha256 == sha256_hex(
        LONG_EXACT_ANSWER.encode("utf-8")
    )
    assert " ".join(first.appendix.entries[0].rendered_answer_lines) == LONG_EXACT_ANSWER
    assert first.placement_plans[0].fit is not None
    assert first.placement_plans[0].fit.reconstructed_text() == SHORT_EXACT_ANSWER
    assert [answer.question_id for answer in first.manifest.answers] == [
        extracted_worksheet.questions[0].question_id,
        extracted_worksheet.questions[1].question_id,
    ]
    assert first.manifest.output_page_count == (
        first.manifest.source_page_count + first.manifest.appendix_page_count
    )

    with pikepdf.Pdf.open(io.BytesIO(first.pdf_bytes), attempt_recovery=False) as checked:
        assert len(checked.pages) == first.manifest.output_page_count
        assert checked.is_encrypted is False
    reader = PdfReader(io.BytesIO(first.pdf_bytes), strict=True)
    source_reader = PdfReader(io.BytesIO(extracted_worksheet.source), strict=True)
    assert list(reader.pages[0].mediabox) == list(source_reader.pages[0].mediabox)
    assert list(reader.pages[0].cropbox) == list(source_reader.pages[0].cropbox)
    first_page_text = reader.pages[0].extract_text() or ""
    assert "Why do plants need sunlight?" in first_page_text
    assert "How does sunlight help a plant make food?" in first_page_text
    assert SHORT_EXACT_ANSWER in first_page_text
    appendix_text = "\n".join(page.extract_text() or "" for page in reader.pages[1:])
    assert "Claros attached answer page" in appendix_text
    assert "Café evidence stays naïve—CO₂ and H₂O" in appendix_text


def test_partial_export_writes_only_confirmed_answer(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    exact = "Only this first response is confirmed."
    artifact = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Partial worksheet",
        (_answer(extracted_worksheet, 0, exact),),
    )

    assert len(artifact.manifest.answers) == 1
    assert artifact.manifest.answers[0].question_id == extracted_worksheet.questions[0].question_id
    assert artifact.manifest.answers[0].exact_text_sha256 == sha256_hex(exact.encode("utf-8"))
    assert artifact.manifest.output_page_count == 1
    output_text = (
        PdfReader(io.BytesIO(artifact.pdf_bytes), strict=True).pages[0].extract_text() or ""
    )
    assert exact in output_text
    assert "UNCONFIRMED-SENTINEL" not in output_text
    assert "How does sunlight help a plant make food?" in output_text


def test_export_revalidates_source_ir_exact_text_and_placement(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    answer = _answer(extracted_worksheet, 0, "Reviewed exact answer.")

    assert (
        _error_code(
            build_export,
            extracted_worksheet.source + b"\n",
            extracted_worksheet.document,
            "Worksheet",
            (answer,),
        )
        == "stale_source"
    )

    stale_ir = replace(extracted_worksheet.document, normalization_sha256="0" * 64)
    assert (
        _error_code(
            build_export,
            extracted_worksheet.source,
            stale_ir,
            "Worksheet",
            (answer,),
        )
        == "stale_physical_ir"
    )

    changed_placement = replace(answer, reviewed_placement_hash="0" * 64)
    assert (
        _error_code(
            build_export,
            extracted_worksheet.source,
            extracted_worksheet.document,
            "Worksheet",
            (changed_placement,),
        )
        == "placement_changed"
    )

    changed_text = replace(answer, exact_text="Text changed after exact review.")
    assert (
        _error_code(
            build_export,
            extracted_worksheet.source,
            extracted_worksheet.document,
            "Worksheet",
            (changed_text,),
        )
        == "placement_changed"
    )


def test_export_rejects_empty_duplicate_and_unsupported_inputs(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    assert (
        _error_code(
            build_export,
            extracted_worksheet.source,
            extracted_worksheet.document,
            "Worksheet",
            (),
        )
        == "no_confirmed_answers"
    )
    answer = _answer(extracted_worksheet, 0, "A valid exact answer.")
    assert (
        _error_code(
            build_export,
            extracted_worksheet.source,
            extracted_worksheet.document,
            "Worksheet",
            (answer, answer),
        )
        == "invalid_export"
    )
    assert (
        _error_code(
            resolve_placement,
            extracted_worksheet.document,
            extracted_worksheet.questions[0],
            "Unsupported answer 🧬",
        )
        == "unsupported_glyph"
    )


def test_publication_is_all_or_cleanup_on_failure(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    artifact = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Worksheet",
        (_answer(extracted_worksheet, 0, "A publishable answer."),),
    )
    published: list[tuple[bytes, bytes]] = []
    cleanup_calls: list[bool] = []

    result = publish_validated_export(
        artifact,
        publish=lambda pdf, manifest: published.append((pdf, manifest)) or "object-generation-7",
        cleanup=lambda: cleanup_calls.append(True),
    )
    assert result.reference == "object-generation-7"
    assert result.pdf_sha256 == artifact.pdf_sha256
    assert result.manifest_sha256 == artifact.manifest.manifest_sha256
    assert published == [(artifact.pdf_bytes, artifact.manifest.canonical_bytes())]
    assert cleanup_calls == []

    def fail_publish(_pdf: bytes, _manifest: bytes) -> None:
        raise OSError("storage unavailable")

    assert (
        _error_code(
            publish_validated_export,
            artifact,
            publish=fail_publish,
            cleanup=lambda: cleanup_calls.append(True),
        )
        == "publish_failed"
    )
    assert cleanup_calls == [True]


def test_export_manifest_binds_every_authoritative_hash(
    extracted_worksheet: ExtractedWorksheet,
) -> None:
    exact = "Hash-bound exact answer."
    answer = _answer(extracted_worksheet, 0, exact)
    artifact = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Bound worksheet title",
        (answer,),
    )
    manifest_answer = artifact.manifest.answers[0]

    assert artifact.manifest.source_sha256 == sha256_hex(extracted_worksheet.source)
    assert artifact.manifest.physical_ir_sha256 == extracted_worksheet.document.ir_sha256
    assert artifact.manifest.worksheet_title_sha256 == sha256_hex(b"Bound worksheet title")
    assert artifact.manifest.output_sha256 == sha256_hex(artifact.pdf_bytes)
    assert manifest_answer.exact_text_sha256 == sha256_hex(exact.encode("utf-8"))
    assert manifest_answer.placement_hash == artifact.placement_plans[0].placement_hash
