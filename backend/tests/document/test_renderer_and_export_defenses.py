"""Renderer and final-export validation defense tests."""

from __future__ import annotations

import io
from dataclasses import dataclass, replace
from types import SimpleNamespace
from typing import Any

import pikepdf
import pytest

from backend.document import (
    ConfirmedAnswerForExport,
    DocumentEngineError,
    build_export,
    publish_validated_export,
    resolve_placement,
)
from backend.document.exporter import _text_runs_present_in_order, _validate_output
from backend.document.renderer import (
    AppendixEntry,
    AppendixRenderResult,
    assemble_derivative,
    render_appendix,
    render_inline_overlay,
)
from backend.tests.document.conftest import ExtractedWorksheet
from backend.tests.document.factories import worksheet_pdf


def _assert_code(expected: str, action: Any) -> None:
    with pytest.raises(DocumentEngineError) as raised:
        action()
    assert raised.value.code == expected


@dataclass(frozen=True, slots=True)
class ExportCase:
    worksheet: ExtractedWorksheet
    answer: ConfirmedAnswerForExport
    artifact: Any


@pytest.fixture(scope="module")
def inline_export(extracted_worksheet: ExtractedWorksheet) -> ExportCase:
    question = extracted_worksheet.questions[0]
    text = "A validated inline answer."
    plan = resolve_placement(extracted_worksheet.document, question, text)
    assert plan.outcome == "inline"
    answer = ConfirmedAnswerForExport(
        question_id=question.question_id,
        display_identifier=question.display_identifier,
        prompt_block_ids=question.prompt_block_ids,
        context_block_ids=question.context_block_ids,
        exact_text=text,
        reviewed_placement_hash=plan.placement_hash,
    )
    artifact = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Worksheet",
        (answer,),
    )
    return ExportCase(extracted_worksheet, answer, artifact)


@pytest.fixture(scope="module")
def appendix_export(extracted_worksheet: ExtractedWorksheet) -> ExportCase:
    question = extracted_worksheet.questions[0]
    text = ("A long attached answer with exact evidence. " * 100).strip()
    plan = resolve_placement(extracted_worksheet.document, question, text)
    assert plan.outcome == "appendix"
    answer = ConfirmedAnswerForExport(
        question_id=question.question_id,
        display_identifier=question.display_identifier,
        prompt_block_ids=question.prompt_block_ids,
        context_block_ids=question.context_block_ids,
        exact_text=text,
        reviewed_placement_hash=plan.placement_hash,
    )
    artifact = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Worksheet",
        (answer,),
    )
    return ExportCase(extracted_worksheet, answer, artifact)


def _appendix_entry(case: ExportCase) -> AppendixEntry:
    question = case.worksheet.questions[0]
    prompt = case.worksheet.document.block_by_id(question.prompt_block_ids[0])
    return AppendixEntry(
        question_id=question.question_id,
        display_identifier=question.display_identifier,
        exact_question=case.worksheet.document.reconstruct_text(question.prompt_block_ids),
        source_page_number=prompt.page_index + 1,
        exact_answer=case.answer.exact_text,
        placement_hash=case.artifact.placement_plans[0].placement_hash,
    )


def test_inline_overlay_rejects_nonidentity_pages_and_invalid_plan_bindings(
    inline_export: ExportCase,
) -> None:
    page = inline_export.worksheet.document.pages[0]
    plan = inline_export.artifact.placement_plans[0]
    rotated = replace(page, rotation=90)
    _assert_code(
        "invalid_physical_evidence",
        lambda: render_inline_overlay(rotated, (plan,)),
    )

    appendix = resolve_placement(
        inline_export.worksheet.document,
        inline_export.worksheet.questions[0],
        inline_export.answer.exact_text,
        force_appendix=True,
    )
    _assert_code(
        "invalid_physical_evidence",
        lambda: render_inline_overlay(page, (appendix,)),
    )
    assert plan.region is not None
    wrong_page_plan = replace(plan, region=replace(plan.region, page_index=1))
    _assert_code(
        "invalid_physical_evidence",
        lambda: render_inline_overlay(page, (wrong_page_plan,)),
    )


def test_inline_overlay_requires_a_real_pdf_from_renderer(
    inline_export: ExportCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EmptyCanvas:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def setFillColor(self, *_args: object) -> None:
            pass

        def setFont(self, *_args: object) -> None:
            pass

        def drawString(self, *_args: object) -> None:
            pass

        def showPage(self) -> None:
            pass

        def save(self) -> None:
            pass

    monkeypatch.setattr("backend.document.renderer.canvas.Canvas", EmptyCanvas)
    _assert_code(
        "invalid_export",
        lambda: render_inline_overlay(
            inline_export.worksheet.document.pages[0],
            inline_export.artifact.placement_plans,
        ),
    )


def test_appendix_wraps_bold_headings_and_rejects_unbreakable_content() -> None:
    entry = AppendixEntry(
        question_id="q1",
        display_identifier="Question 1 with a descriptive identifier",
        exact_question="Why is this grounded?",
        source_page_number=1,
        exact_answer="A concise exact answer.",
        placement_hash="a" * 64,
    )
    wrapped = render_appendix(
        (entry,),
        "A deliberately long worksheet title with enough words to wrap across lines " * 3,
    )
    assert wrapped.page_count >= 1
    assert wrapped.pdf_bytes.startswith(b"%PDF-")

    _assert_code(
        "invalid_export",
        lambda: render_appendix((entry,), "W" * 1_000),
    )
    _assert_code(
        "invalid_export",
        lambda: render_appendix((replace(entry, exact_answer="W" * 1_000),), "Worksheet"),
    )


def test_long_source_question_uses_continuation_page_without_losing_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = AppendixEntry(
        question_id="q1",
        display_identifier="Question 1",
        exact_question="synthetic-long-question",
        source_page_number=1,
        exact_answer="The exact answer survives question pagination.",
        placement_hash="a" * 64,
    )
    from backend.document import renderer

    original = renderer._wrapped_lines
    question_calls = 0

    def controlled_wrap(text: str, width: float, font: str, size: float) -> list[str]:
        nonlocal question_calls
        if text == entry.exact_question:
            question_calls += 1
            if question_calls == 1:
                return [f"Grounded source line {index}" for index in range(42)]
            return ["Grounded source question continued"]
        return original(text, width, font, size)

    monkeypatch.setattr(renderer, "_wrapped_lines", controlled_wrap)
    result = render_appendix((entry,), "Worksheet")

    assert result.page_count == 2
    assert result.entries[0].rendered_answer_lines == (
        "The exact answer survives question pagination.",
    )


def test_derivative_assembly_rejects_page_mismatch_missing_region_and_bad_appendix(
    inline_export: ExportCase,
) -> None:
    worksheet = inline_export.worksheet
    page = worksheet.document.pages[0]
    second_page = replace(page, page_index=1, blocks=())
    two_page_evidence = replace(worksheet.document, pages=(page, second_page))
    _assert_code(
        "stale_source",
        lambda: assemble_derivative(
            worksheet.source,
            two_page_evidence,
            (),
            AppendixRenderResult(b"", 0, ()),
        ),
    )

    _assert_code(
        "invalid_export",
        lambda: assemble_derivative(
            worksheet.source,
            worksheet.document,
            (SimpleNamespace(region=None),),
            AppendixRenderResult(b"", 0, ()),
        ),
    )

    mismatched_appendix = AppendixRenderResult(
        pdf_bytes=worksheet_pdf(questions=("Appendix page text?",)),
        page_count=2,
        entries=(),
    )
    _assert_code(
        "invalid_export",
        lambda: assemble_derivative(
            worksheet.source,
            worksheet.document,
            (),
            mismatched_appendix,
        ),
    )
    _assert_code(
        "invalid_export",
        lambda: assemble_derivative(
            b"not-a-pdf",
            worksheet.document,
            (),
            AppendixRenderResult(b"", 0, ()),
        ),
    )
    _assert_code(
        "invalid_export",
        lambda: assemble_derivative(
            worksheet.source,
            replace(worksheet.document, source_sha256="0" * 64),
            (),
            AppendixRenderResult(b"", 0, ()),
        ),
    )


def test_export_validator_rejects_unreadable_encrypted_shape_and_source_loss(
    inline_export: ExportCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    case = inline_export
    empty = AppendixRenderResult(b"", 0, ())
    _assert_code(
        "invalid_export",
        lambda: _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=b"not-a-pdf",
            document=case.worksheet.document,
            plans=case.artifact.placement_plans,
            appendix=empty,
            appendix_entries=(),
        ),
    )

    encrypted_output = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(case.artifact.pdf_bytes)) as pdf:
        pdf.save(
            encrypted_output,
            encryption=pikepdf.Encryption(owner="owner", user="", R=6),
        )
    _assert_code(
        "invalid_export",
        lambda: _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=encrypted_output.getvalue(),
            document=case.worksheet.document,
            plans=case.artifact.placement_plans,
            appendix=empty,
            appendix_entries=(),
        ),
    )

    changed_shape = io.BytesIO()
    with pikepdf.Pdf.open(io.BytesIO(case.artifact.pdf_bytes)) as pdf:
        pdf.pages[0].obj["/CropBox"] = pikepdf.Array([0, 0, 500, 700])
        pdf.save(changed_shape, deterministic_id=True)
    _assert_code(
        "invalid_export",
        lambda: _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=changed_shape.getvalue(),
            document=case.worksheet.document,
            plans=case.artifact.placement_plans,
            appendix=empty,
            appendix_entries=(),
        ),
    )

    blank_page = worksheet_pdf(questions=(), answer_regions="none")
    _assert_code(
        "invalid_export",
        lambda: _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=blank_page,
            document=case.worksheet.document,
            plans=case.artifact.placement_plans,
            appendix=empty,
            appendix_entries=(),
        ),
    )

    monkeypatch.setattr("backend.document.exporter._source_page_objects_preserved", lambda *_: True)
    _assert_code(
        "invalid_export",
        lambda: _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=blank_page,
            document=case.worksheet.document,
            plans=case.artifact.placement_plans,
            appendix=empty,
            appendix_entries=(),
        ),
    )


def test_export_validator_rejects_invalid_plan_shapes_and_missing_inline_text(
    inline_export: ExportCase,
) -> None:
    case = inline_export
    plan = case.artifact.placement_plans[0]
    empty = AppendixRenderResult(b"", 0, ())

    rejected = replace(
        plan,
        outcome="reject",
        region=None,
        fit=None,
        appendix_entry_id=None,
        rejection_code="unsafe_question_evidence",
    )
    for invalid_plan in (
        rejected,
        SimpleNamespace(outcome="inline", region=None, fit=None),
        SimpleNamespace(
            outcome="inline",
            region=plan.region,
            fit=SimpleNamespace(font_size_mpt=9_999, lines=()),
        ),
    ):
        _assert_code(
            "invalid_export",
            lambda invalid_plan=invalid_plan: _validate_output(
                source_pdf=case.worksheet.source,
                output_pdf=case.artifact.pdf_bytes,
                document=case.worksheet.document,
                plans=(invalid_plan,),
                appendix=empty,
                appendix_entries=(),
            ),
        )

    _assert_code(
        "invalid_export",
        lambda: _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=case.worksheet.source,
            document=case.worksheet.document,
            plans=(plan,),
            appendix=empty,
            appendix_entries=(),
        ),
    )
    _assert_code(
        "invalid_export",
        lambda: _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=case.artifact.pdf_bytes,
            document=case.worksheet.document,
            plans=(),
            appendix=empty,
            appendix_entries=(AppendixEntry("q", "Question", "Prompt", 1, "Answer", "a" * 64),),
        ),
    )


def test_appendix_validator_rejects_binding_bounds_text_and_stale_source(
    appendix_export: ExportCase,
) -> None:
    case = appendix_export
    entry = _appendix_entry(case)
    rendered = case.artifact.appendix.entries[0]

    def validate(
        *,
        document: Any = None,
        appendix: AppendixRenderResult | None = None,
        appendix_entry: AppendixEntry = entry,
    ) -> None:
        _validate_output(
            source_pdf=case.worksheet.source,
            output_pdf=case.artifact.pdf_bytes,
            document=document or case.worksheet.document,
            plans=case.artifact.placement_plans,
            appendix=appendix or case.artifact.appendix,
            appendix_entries=(appendix_entry,),
        )

    _assert_code(
        "invalid_export",
        lambda: validate(appendix_entry=replace(entry, question_id="other")),
    )
    _assert_code(
        "invalid_export",
        lambda: validate(
            appendix=replace(
                case.artifact.appendix,
                entries=(replace(rendered, first_page_offset=-2),),
            )
        ),
    )
    _assert_code(
        "invalid_export",
        lambda: validate(
            appendix=replace(
                case.artifact.appendix,
                entries=(replace(rendered, rendered_answer_lines=("missing text",)),),
            )
        ),
    )
    _assert_code(
        "stale_source",
        lambda: validate(document=replace(case.worksheet.document, source_sha256="0" * 64)),
    )


def test_export_accepts_reviewed_forced_appendix_and_rejects_resolver_rejection(
    extracted_worksheet: ExtractedWorksheet,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    question = extracted_worksheet.questions[0]
    exact = "A short answer reviewed for an attached page."
    forced = resolve_placement(
        extracted_worksheet.document,
        question,
        exact,
        force_appendix=True,
    )
    answer = ConfirmedAnswerForExport(
        question.question_id,
        question.display_identifier,
        question.prompt_block_ids,
        question.context_block_ids,
        exact,
        forced.placement_hash,
    )
    artifact = build_export(
        extracted_worksheet.source,
        extracted_worksheet.document,
        "Worksheet",
        (answer,),
    )
    assert artifact.placement_plans[0].outcome == "appendix"

    rejected = resolve_placement(
        extracted_worksheet.document,
        replace(question, grounded=False),
        exact,
    )
    monkeypatch.setattr(
        "backend.document.exporter.resolve_placement", lambda *_args, **_kwargs: rejected
    )
    _assert_code(
        "unsafe_question_evidence",
        lambda: build_export(
            extracted_worksheet.source,
            extracted_worksheet.document,
            "Worksheet",
            (replace(answer, reviewed_placement_hash=rejected.placement_hash),),
        ),
    )


def test_export_answer_and_publication_cleanup_guards(
    inline_export: ExportCase,
) -> None:
    answer = inline_export.answer
    for change in (
        {"question_id": ""},
        {"display_identifier": ""},
        {"exact_text": ""},
        {"reviewed_placement_hash": "short"},
    ):
        _assert_code("invalid_export", lambda change=change: replace(answer, **change))

    def fail_publish(_pdf: bytes, _manifest: bytes) -> None:
        raise OSError("publish failed")

    def fail_cleanup() -> None:
        raise OSError("cleanup also failed")

    _assert_code(
        "publish_failed",
        lambda: publish_validated_export(
            inline_export.artifact,
            publish=fail_publish,
            cleanup=fail_cleanup,
        ),
    )


def test_text_run_validation_requires_nonblank_runs_in_source_order() -> None:
    assert _text_runs_present_in_order("first\n\nsecond", "prefix first then second suffix")
    assert not _text_runs_present_in_order("first\nsecond", "second before first")
