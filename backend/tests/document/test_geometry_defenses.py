"""Review-evidence, fitting, and placement fail-closed tests."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import pytest

from backend.document import (
    DocumentEngineError,
    QuestionEvidence,
    extract_physical_ir,
    parse_placement_plan,
    resolve_placement,
)
from backend.document.errors import document_error
from backend.document.geometry import FitLine, fit_text
from backend.document.models import canonical_json_bytes, sha256_hex
from backend.tests.document.factories import BlockSpec, make_document, worksheet_pdf


def _assert_code(expected: str, action: Any) -> None:
    with pytest.raises(DocumentEngineError) as raised:
        action()
    assert raised.value.code == expected


def _inline_case() -> tuple[Any, QuestionEvidence, Any]:
    document, blocks = make_document(
        (
            BlockSpec(
                "prompt",
                "text",
                (50_000, 50_000, 360_000, 70_000),
                "Why do plants need sunlight?",
            ),
            BlockSpec(
                "rect",
                "rect",
                (50_000, 100_000, 550_000, 200_000),
                values={"filled": False, "stroked": True},
            ),
            BlockSpec(
                "next",
                "text",
                (50_000, 320_000, 380_000, 340_000),
                "What happens next?",
            ),
        )
    )
    evidence = QuestionEvidence(
        question_id="question-1",
        display_identifier="Question 1",
        prompt_block_ids=(blocks["prompt"].id,),
    )
    return document, evidence, resolve_placement(document, evidence, "An exact answer.")


def _rehash_plan(raw: dict[str, Any]) -> bytes:
    body = {key: value for key, value in raw.items() if key != "placement_hash"}
    raw["placement_hash"] = sha256_hex(canonical_json_bytes(body))
    return canonical_json_bytes(raw)


def test_question_evidence_rejects_invalid_identity_ids_and_serialized_types() -> None:
    good_id = "blk_" + "1" * 32
    for kwargs in (
        {"question_id": "", "display_identifier": "Question", "prompt_block_ids": (good_id,)},
        {
            "question_id": "q" * 97,
            "display_identifier": "Question",
            "prompt_block_ids": (good_id,),
        },
        {"question_id": "q", "display_identifier": "", "prompt_block_ids": (good_id,)},
        {
            "question_id": "q",
            "display_identifier": "d" * 129,
            "prompt_block_ids": (good_id,),
        },
        {"question_id": "q", "display_identifier": "Question", "prompt_block_ids": ()},
        {
            "question_id": "q",
            "display_identifier": "Question",
            "prompt_block_ids": (good_id, good_id),
        },
        {"question_id": "q", "display_identifier": "Question", "prompt_block_ids": ("bad",)},
    ):
        _assert_code("unsafe_question_evidence", lambda kwargs=kwargs: QuestionEvidence(**kwargs))

    valid = QuestionEvidence("q", "Question", (good_id,))
    raw = json.loads(valid.canonical_bytes())
    raw["grounded"] = 1
    _assert_code(
        "unsafe_question_evidence",
        lambda: QuestionEvidence.from_bytes(canonical_json_bytes(raw)),
    )
    _assert_code("unsafe_question_evidence", lambda: QuestionEvidence.from_bytes(b"\xff"))
    _assert_code("unsafe_question_evidence", lambda: QuestionEvidence.from_bytes(b"[]"))


def test_fit_region_and_plan_value_objects_reject_impossible_states() -> None:
    _document, _evidence, plan = _inline_case()
    assert plan.fit is not None
    assert plan.region is not None

    for change in (
        {"font_name": "OtherFont"},
        {"font_size_mpt": 9_999},
        {"font_size_mpt": 12_001},
        {"leading_mpt": 0},
        {"padding_mpt": -1},
        {"lines": ()},
        {"scratch_pdf_sha256": "short"},
    ):
        _assert_code("invalid_physical_evidence", lambda change=change: replace(plan.fit, **change))

    for change in (
        {"region_id": "bad"},
        {"kind": "client_box"},
        {"page_index": -1},
        {"source_block_ids": ("same", "same")},
    ):
        _assert_code(
            "invalid_physical_evidence", lambda change=change: replace(plan.region, **change)
        )

    impossible_plans = (
        {"algorithm_version": "old"},
        {"outcome": "client_choice"},
        {"region": None},
        {"fit": None},
        {"outcome": "appendix", "region": None, "fit": None, "appendix_entry_id": None},
        {"outcome": "reject", "region": None, "fit": None, "rejection_code": None},
        {"outcome": "appendix", "appendix_entry_id": "appendix_x"},
        {
            "outcome": "appendix",
            "region": None,
            "fit": None,
            "appendix_entry_id": "appendix_x",
            "rejection_code": "not-allowed",
        },
        {"appendix_entry_id": "appendix_x"},
        {"rejection_code": "unsafe_question_evidence"},
        {
            "outcome": "reject",
            "region": None,
            "fit": None,
            "rejection_code": "unsafe_question_evidence",
            "appendix_entry_id": "appendix_x",
        },
        {"source_sha256": "short"},
    )
    for change in impossible_plans:
        expected = (
            "placement_changed" if "algorithm_version" in change else "invalid_physical_evidence"
        )
        _assert_code(expected, lambda change=change: replace(plan, **change))


def test_question_grounding_rejects_nontext_reordered_blank_and_cross_page_evidence() -> None:
    document, blocks = make_document(
        (
            BlockSpec("first", "text", (40_000, 40_000, 180_000, 60_000), "Why do", "space"),
            BlockSpec(
                "second",
                "text",
                (180_000, 40_000, 360_000, 60_000),
                "plants grow?",
            ),
            BlockSpec("blank", "text", (40_000, 80_000, 41_000, 81_000), "   "),
            BlockSpec(
                "line",
                "line",
                (40_000, 120_000, 500_000, 120_000),
                values={"stroked": True},
            ),
        )
    )

    def evidence(
        prompt_ids: tuple[str, ...], context_ids: tuple[str, ...] = ()
    ) -> QuestionEvidence:
        return QuestionEvidence("q", "Question", prompt_ids, context_ids)

    cases = (
        evidence((blocks["line"].id,)),
        evidence((blocks["second"].id, blocks["first"].id)),
        evidence((blocks["blank"].id,)),
        evidence((blocks["first"].id,), (blocks["line"].id,)),
        evidence(
            (blocks["first"].id,),
            (blocks["blank"].id, blocks["second"].id),
        ),
    )
    for unsafe in cases:
        assert resolve_placement(document, unsafe, "Answer").outcome == "reject"

    two_pages = extract_physical_ir(worksheet_pdf(page_count=2))
    first_page_text = next(block for block in two_pages.pages[0].blocks if block.kind == "text")
    second_page_text = next(block for block in two_pages.pages[1].blocks if block.kind == "text")
    cross_page = QuestionEvidence(
        "cross-page",
        "Question",
        (first_page_text.id, second_page_text.id),
    )
    assert resolve_placement(two_pages, cross_page, "Answer").outcome == "reject"


def test_context_blocks_bind_placement_and_unexpected_document_errors_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, blocks = make_document(
        (
            BlockSpec("context", "text", (40_000, 20_000, 250_000, 35_000), "Use evidence."),
            BlockSpec("prompt", "text", (40_000, 50_000, 350_000, 70_000), "Why?"),
        )
    )
    without_context = QuestionEvidence("q", "Question", (blocks["prompt"].id,))
    with_context = QuestionEvidence(
        "q",
        "Question",
        (blocks["prompt"].id,),
        (blocks["context"].id,),
    )
    plain = resolve_placement(document, without_context, "Answer", force_appendix=True)
    contextual = resolve_placement(document, with_context, "Answer", force_appendix=True)
    assert plain.question_evidence_sha256 != contextual.question_evidence_sha256

    def stale_details(*_args: object, **_kwargs: object) -> None:
        raise document_error("stale_source")

    monkeypatch.setattr("backend.document.geometry._question_details", stale_details)
    _assert_code("stale_source", lambda: resolve_placement(document, with_context, "Answer"))


def test_blank_answer_and_mismatched_line_groups_route_safely() -> None:
    document, blocks = make_document(
        (
            BlockSpec("prompt", "text", (50_000, 50_000, 360_000, 70_000), "Why?"),
            BlockSpec(
                "line-1",
                "line",
                (50_000, 115_000, 550_000, 115_000),
                values={"stroked": True},
            ),
            BlockSpec(
                "line-2",
                "line",
                (100_000, 145_000, 550_000, 145_000),
                values={"stroked": True},
            ),
        )
    )
    evidence = QuestionEvidence("q", "Question", (blocks["prompt"].id,))
    _assert_code("invalid_physical_evidence", lambda: resolve_placement(document, evidence, "  "))
    assert resolve_placement(document, evidence, "A grounded answer.").outcome == "appendix"


def test_fit_preserves_leading_spaces_crlf_and_blank_lines_and_rejects_unbreakable_text() -> None:
    _document, _evidence, plan = _inline_case()
    assert plan.region is not None
    exact = (
        " leading words "
        + "that wrap safely " * 10
        + "across the available region\r\nsecond line\n\nthird"
    )
    fit = fit_text(plan.region, exact)
    assert fit is not None
    assert fit.reconstructed_text() == exact
    assert fit_text(plan.region, "x" * 1_000) is None

    tiny_document, tiny_blocks = make_document(
        (
            BlockSpec("prompt", "text", (0, 0, 10, 10), "Q?"),
            BlockSpec(
                "tiny",
                "rect",
                (20, 20, 8_020, 8_020),
                values={"filled": False},
            ),
        )
    )
    del tiny_document
    tiny_region = replace(plan.region, bbox_mpt=tiny_blocks["tiny"].bbox)
    assert fit_text(tiny_region, "answer") is None


def test_scratch_render_must_be_pdf_readable_and_contain_every_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _document, _evidence, plan = _inline_case()
    assert plan.region is not None

    class EmptyCanvas:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def setFont(self, *_args: object) -> None:
            pass

        def drawString(self, *_args: object) -> None:
            pass

        def save(self) -> None:
            pass

    monkeypatch.setattr("backend.document.geometry.canvas.Canvas", EmptyCanvas)
    _assert_code("invalid_physical_evidence", lambda: fit_text(plan.region, "answer"))
    monkeypatch.undo()

    def unreadable(*_args: object, **_kwargs: object) -> None:
        raise ValueError("synthetic unreadable scratch")

    monkeypatch.setattr("pypdf.PdfReader", unreadable)
    _assert_code("invalid_physical_evidence", lambda: fit_text(plan.region, "answer"))
    monkeypatch.undo()

    class EmptyPage:
        def extract_text(self) -> str:
            return ""

    class EmptyReader:
        pages = (EmptyPage(),)

    monkeypatch.setattr("pypdf.PdfReader", lambda *_args, **_kwargs: EmptyReader())
    _assert_code("invalid_physical_evidence", lambda: fit_text(plan.region, "answer"))


def test_fit_rejects_any_internal_text_reconstruction_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _document, _evidence, plan = _inline_case()
    assert plan.region is not None
    monkeypatch.setattr(
        "backend.document.geometry._wrap_exact_text",
        lambda *_args, **_kwargs: (FitLine("different", "", 0, 0),),
    )
    _assert_code("invalid_physical_evidence", lambda: fit_text(plan.region, "expected"))


def test_strict_placement_parser_rejects_every_untrusted_nested_shape() -> None:
    document, evidence, plan = _inline_case()
    appendix = resolve_placement(document, evidence, "An exact answer.", force_appendix=True)
    assert parse_placement_plan(appendix.canonical_bytes()) == appendix
    _assert_code("placement_changed", lambda: parse_placement_plan(b"[]"))

    base = json.loads(plan.canonical_bytes())

    def rejected(mutator: Any) -> None:
        raw = json.loads(canonical_json_bytes(base))
        mutator(raw)
        _assert_code("placement_changed", lambda: parse_placement_plan(_rehash_plan(raw)))

    rejected(lambda raw: raw.__setitem__("question_id", 7))
    rejected(lambda raw: raw.__setitem__("appendix_entry_id", 7))
    rejected(lambda raw: raw.__setitem__("region", []))
    rejected(lambda raw: raw["region"].pop("kind"))
    rejected(lambda raw: raw["region"].__setitem__("page_index", True))
    rejected(lambda raw: raw.__setitem__("fit", []))
    rejected(lambda raw: raw["fit"].pop("font_name"))
    rejected(lambda raw: raw["fit"].__setitem__("font_size_mpt", True))
    rejected(lambda raw: raw["fit"].__setitem__("rendered_bounds_mpt", [1, 2]))
    rejected(lambda raw: raw["fit"].__setitem__("lines", "bad"))
    rejected(lambda raw: raw["fit"]["lines"].__setitem__(0, "bad"))
    rejected(lambda raw: raw["fit"]["lines"][0].pop("text"))
    rejected(lambda raw: raw["fit"]["lines"][0].__setitem__("x_mpt", True))
