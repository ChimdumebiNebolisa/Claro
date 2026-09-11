"""Checksum and behavioral gates for the twelve-case synthetic corpus."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pikepdf
import pytest
from pypdf import PdfReader

from backend.document import (
    ConfirmedAnswerForExport,
    DocumentEngineError,
    PreflightLimits,
    QuestionEvidence,
    build_export,
    extract_physical_ir,
    preflight_pdf,
    resolve_placement,
)
from backend.document_execution import ground_questions

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"


def _manifest() -> dict[str, object]:
    return json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))


def _fixtures() -> list[dict[str, object]]:
    fixtures = _manifest()["fixtures"]
    assert isinstance(fixtures, list)
    return fixtures  # type: ignore[return-value]


def test_gold_corpus_has_exact_required_categories_and_pinned_bytes() -> None:
    manifest = _manifest()
    assert manifest["schema_version"] == 1
    assert manifest["generator_version"] == "claros-gold-corpus-v1"
    fixtures = _fixtures()
    assert [fixture["fixture_id"] for fixture in fixtures] == [
        "biology-polished",
        "middle-school-science",
        "non-science-short-answer",
        "blank-answer-lines",
        "rectangular-answer-boxes",
        "multi-page-order",
        "long-answer-appendix",
        "unicode-punctuation-names",
        "rotated-crop-box",
        "no-safe-inline-region",
        "controlled-scan-rejection",
        "ambiguous-question-boundary",
    ]
    for fixture in fixtures:
        payload = (CORPUS_DIR / str(fixture["file"])).read_bytes()
        assert payload.startswith(b"%PDF-")
        assert len(payload) == fixture["size_bytes"]
        assert hashlib.sha256(payload).hexdigest() == fixture["sha256"]


@pytest.mark.parametrize(
    "fixture",
    [item for item in _fixtures() if item["expected"]["outcome"] == "accept"],
    ids=lambda item: item["fixture_id"],
)
def test_accepted_gold_corpus_preserves_exact_prompts_and_placement(
    fixture: dict[str, object],
) -> None:
    payload = (CORPUS_DIR / str(fixture["file"])).read_bytes()
    first = extract_physical_ir(payload)
    second = extract_physical_ir(payload)
    assert first.canonical_bytes() == second.canonical_bytes()

    expected = fixture["expected"]
    assert isinstance(expected, dict)
    expected_questions = expected["question_text"]
    assert isinstance(expected_questions, list)
    grounded = ground_questions(first, limits=PreflightLimits())
    assert [question.exact_prompt for question in grounded] == expected_questions
    assert len(grounded) == len(expected_questions)
    text_blocks = [block for page in first.pages for block in page.blocks if block.kind == "text"]
    located = []
    for index, exact_question in enumerate(expected_questions, start=1):
        matching = [block for block in text_blocks if block.text == exact_question]
        assert len(matching) == 1, (fixture["fixture_id"], exact_question)
        located.append(matching[0])
        evidence = QuestionEvidence(
            question_id=f"question-{index}",
            display_identifier=f"Question {index}",
            prompt_block_ids=(matching[0].id,),
        )
        exact_answer = str(expected.get("sample_answer", "A grounded exact answer."))
        plan = resolve_placement(first, evidence, exact_answer)
        assert plan.outcome == expected["placement"]
    assert [(block.page_index, block.reading_order) for block in located] == sorted(
        (block.page_index, block.reading_order) for block in located
    )

    expected_flags = expected.get("ambiguity_flags", [])
    actual_flags = {flag for page in first.pages for flag in page.ambiguity_flags}
    assert set(expected_flags).issubset(actual_flags)


@pytest.mark.parametrize(
    "fixture",
    [item for item in _fixtures() if item["expected"]["outcome"] == "accept"],
    ids=lambda item: item["fixture_id"],
)
def test_accepted_gold_corpus_runs_the_full_deterministic_export(
    fixture: dict[str, object],
) -> None:
    payload = (CORPUS_DIR / str(fixture["file"])).read_bytes()
    source_before = bytes(payload)
    physical = extract_physical_ir(payload)
    questions = ground_questions(physical, limits=PreflightLimits())
    expected = fixture["expected"]
    assert isinstance(expected, dict)
    plans = []
    answers = []

    for index, question in enumerate(questions, start=1):
        exact_answer = str(expected.get("sample_answer", f"Exact Café — response {index}."))
        evidence = QuestionEvidence(
            question_id=question.question_id,
            display_identifier=question.display_identifier,
            prompt_block_ids=question.prompt_block_ids,
            context_block_ids=question.context_block_ids,
        )
        plan = resolve_placement(
            physical,
            evidence,
            exact_answer,
            occupied_plans=tuple(plans),
        )
        assert plan.outcome == expected["placement"]
        if plan.outcome == "inline":
            assert plan.region is not None
            assert plan.fit is not None
            assert plan.fit.font_size_mpt >= 10_000
            assert plan.fit.reconstructed_text() == exact_answer
            page = physical.pages[plan.region.page_index]
            assert plan.fit.rendered_bounds_mpt.within(page.width_mpt, page.height_mpt)
            expected_region = expected.get("region_kind")
            if expected_region is not None:
                assert (
                    plan.region.kind
                    == {
                        "answer_line_group": "line_group",
                        "safe_box": "rect",
                    }[str(expected_region)]
                )
            for prior in plans:
                if prior.region is not None and prior.region.page_index == plan.region.page_index:
                    assert prior.fit is not None
                    assert not prior.fit.rendered_bounds_mpt.intersects(
                        plan.fit.rendered_bounds_mpt
                    )
        plans.append(plan)
        answers.append(
            ConfirmedAnswerForExport(
                question_id=question.question_id,
                display_identifier=question.display_identifier,
                prompt_block_ids=question.prompt_block_ids,
                context_block_ids=question.context_block_ids,
                exact_text=exact_answer,
                reviewed_placement_hash=plan.placement_hash,
            )
        )

    first = build_export(
        payload,
        physical,
        str(fixture["fixture_id"]),
        tuple(answers),
    )
    second = build_export(
        payload,
        physical,
        str(fixture["fixture_id"]),
        tuple(answers),
    )
    assert payload == source_before
    assert first.pdf_bytes == second.pdf_bytes
    assert first.manifest.canonical_bytes() == second.manifest.canonical_bytes()
    assert [plan.placement_hash for plan in first.placement_plans] == [
        plan.placement_hash for plan in plans
    ]
    assert len(first.manifest.answers) == len(questions)

    with pikepdf.Pdf.open(io.BytesIO(first.pdf_bytes), attempt_recovery=False) as checked:
        assert len(checked.pages) == first.manifest.output_page_count
        assert checked.is_encrypted is False
    source_reader = PdfReader(io.BytesIO(payload), strict=True)
    output_reader = PdfReader(io.BytesIO(first.pdf_bytes), strict=True)
    for page_index, source_page in enumerate(source_reader.pages):
        output_page = output_reader.pages[page_index]
        assert list(output_page.mediabox) == list(source_page.mediabox)
        assert list(output_page.cropbox) == list(source_page.cropbox)
        assert (source_page.extract_text() or "") in (output_page.extract_text() or "")

    for answer, plan in zip(answers, first.placement_plans, strict=True):
        if plan.fit is not None:
            assert plan.fit.reconstructed_text() == answer.exact_text
        else:
            appendix_entry = next(
                item for item in first.appendix.entries if item.question_id == answer.question_id
            )
            assert " ".join(appendix_entry.rendered_answer_lines) == answer.exact_text


def test_controlled_scan_has_the_pinned_rejection_code() -> None:
    fixture = next(
        item for item in _fixtures() if item["fixture_id"] == "controlled-scan-rejection"
    )
    payload = (CORPUS_DIR / str(fixture["file"])).read_bytes()
    with pytest.raises(DocumentEngineError) as raised:
        preflight_pdf(payload)
    assert raised.value.code == fixture["expected"]["error_code"]


def test_ambiguous_boundary_is_valid_physical_input_reserved_for_semantic_rejection() -> None:
    fixture = next(
        item for item in _fixtures() if item["fixture_id"] == "ambiguous-question-boundary"
    )
    payload = (CORPUS_DIR / str(fixture["file"])).read_bytes()
    physical = extract_physical_ir(payload)
    assert physical.pages
    with pytest.raises(DocumentEngineError) as raised:
        ground_questions(physical, limits=PreflightLimits())
    assert raised.value.code == "ambiguous_question_boundaries"
    assert fixture["expected"] == {
        "outcome": "reject",
        "error_code": "ambiguous_question_boundaries",
    }
