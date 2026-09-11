"""Deterministic placement, collision, and review-metadata tests."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from backend.document import (
    DocumentEngineError,
    QuestionEvidence,
    parse_placement_plan,
    resolve_placement,
    validate_placement_plan,
)
from backend.document.geometry import canonical_box_to_pdf_points
from backend.document.models import CanonicalBox, canonical_json_bytes, sha256_hex
from backend.tests.document.factories import BlockSpec, make_document

PROMPT = BlockSpec(
    "prompt",
    "text",
    (50_000, 50_000, 360_000, 70_000),
    "Why do plants need sunlight?",
)
NEXT_PROMPT = BlockSpec(
    "next",
    "text",
    (50_000, 320_000, 380_000, 340_000),
    "What happens in the next question?",
)


def _question(block_id: str, *, grounded: bool = True) -> QuestionEvidence:
    return QuestionEvidence(
        question_id="question-1",
        display_identifier="Question 1",
        prompt_block_ids=(block_id,),
        grounded=grounded,
    )


def _error_code(callable_: object, *args: object, **kwargs: object) -> str:
    with pytest.raises(DocumentEngineError) as raised:
        callable_(*args, **kwargs)  # type: ignore[operator]
    return raised.value.code


@pytest.mark.parametrize(
    ("region_specs", "expected_kind"),
    [
        (
            (
                BlockSpec(
                    "field",
                    "form_field",
                    (50_000, 100_000, 550_000, 180_000),
                    values={"field_name": "answer", "writable": True, "multiline": True},
                ),
            ),
            "form_field",
        ),
        (
            (
                BlockSpec(
                    "rect",
                    "rect",
                    (50_000, 100_000, 550_000, 180_000),
                    values={"filled": False, "stroked": True},
                ),
            ),
            "rect",
        ),
        (
            (
                BlockSpec(
                    "line-1",
                    "line",
                    (50_000, 115_000, 550_000, 115_000),
                    values={"stroke_width_mpt": 1_000, "stroked": True},
                ),
                BlockSpec(
                    "line-2",
                    "line",
                    (50_000, 145_000, 550_000, 145_000),
                    values={"stroke_width_mpt": 1_000, "stroked": True},
                ),
            ),
            "line_group",
        ),
    ],
)
def test_selects_supported_region_kinds_in_priority_order(
    region_specs: tuple[BlockSpec, ...],
    expected_kind: str,
) -> None:
    document, blocks = make_document((PROMPT, *region_specs, NEXT_PROMPT))
    plan = resolve_placement(document, _question(blocks["prompt"].id), "An exact answer.")

    assert plan.outcome == "inline"
    assert plan.region is not None
    assert plan.region.kind == expected_kind
    assert plan.fit is not None
    assert plan.fit.reconstructed_text() == "An exact answer."
    assert plan.fit.rendered_bounds_mpt.within(
        document.pages[0].width_mpt,
        document.pages[0].height_mpt,
    )


def test_form_field_precedes_other_noncolliding_region_types() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "field",
                "form_field",
                (50_000, 90_000, 550_000, 155_000),
                values={"field_name": "answer", "writable": True, "multiline": True},
            ),
            BlockSpec(
                "rect",
                "rect",
                (50_000, 190_000, 550_000, 270_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )

    plan = resolve_placement(document, _question(blocks["prompt"].id), "Exact wording")
    assert plan.outcome == "inline"
    assert plan.region is not None
    assert plan.region.kind == "form_field"
    assert plan.region.source_block_ids == (blocks["field"].id,)


def test_unsafe_higher_priority_region_does_not_hide_safe_lower_priority_region() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "small-field",
                "form_field",
                (50_000, 90_000, 160_000, 120_000),
                values={"field_name": "answer", "writable": True, "multiline": True},
            ),
            BlockSpec(
                "safe-rect",
                "rect",
                (50_000, 150_000, 550_000, 270_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )

    plan = resolve_placement(
        document,
        _question(blocks["prompt"].id),
        "This exact answer cannot fit in the small writable field but fits in the safe box.",
    )

    assert plan.outcome == "inline"
    assert plan.region is not None
    assert plan.region.kind == "rect"
    assert plan.region.source_block_ids == (blocks["safe-rect"].id,)


def test_colliding_or_occupied_field_falls_through_to_safe_box() -> None:
    colliding, colliding_blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "field",
                "form_field",
                (50_000, 90_000, 550_000, 155_000),
                values={"field_name": "answer", "writable": True, "multiline": True},
            ),
            BlockSpec(
                "field-collider",
                "shape",
                (200_000, 110_000, 300_000, 130_000),
                values={"filled": True, "stroked": False},
            ),
            BlockSpec(
                "safe-rect",
                "rect",
                (50_000, 190_000, 550_000, 270_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    collision_plan = resolve_placement(
        colliding,
        _question(colliding_blocks["prompt"].id),
        "Exact wording",
    )
    assert collision_plan.outcome == "inline"
    assert collision_plan.region is not None
    assert collision_plan.region.kind == "rect"

    clean, clean_blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "field",
                "form_field",
                (50_000, 90_000, 550_000, 155_000),
                values={"field_name": "answer", "writable": True, "multiline": True},
            ),
            BlockSpec(
                "safe-rect",
                "rect",
                (50_000, 190_000, 550_000, 270_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    first = resolve_placement(clean, _question(clean_blocks["prompt"].id), "First answer")
    occupied = resolve_placement(
        clean,
        _question(clean_blocks["prompt"].id),
        "Second answer",
        occupied_plans=(first,),
    )
    assert first.region is not None and first.region.kind == "form_field"
    assert occupied.outcome == "inline"
    assert occupied.region is not None and occupied.region.kind == "rect"


def test_uses_bounded_whitespace_only_when_supported_by_following_text() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "following",
                "text",
                (50_000, 230_000, 400_000, 250_000),
                "A later source block.",
            ),
        )
    )
    plan = resolve_placement(document, _question(blocks["prompt"].id), "Exact wording")

    assert plan.outcome == "inline"
    assert plan.region is not None
    assert plan.region.kind == "whitespace"
    assert plan.region.bbox_mpt == CanonicalBox(50_000, 78_000, 576_000, 222_000)


def test_competing_regions_source_collision_and_occupied_geometry_use_appendix() -> None:
    rectangle = BlockSpec(
        "rect",
        "rect",
        (50_000, 100_000, 550_000, 180_000),
        values={"filled": False, "stroked": True},
    )
    competing, competing_blocks = make_document(
        (
            PROMPT,
            rectangle,
            BlockSpec(
                "rect-2",
                "rect",
                (50_000, 190_000, 550_000, 270_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    assert (
        resolve_placement(
            competing,
            _question(competing_blocks["prompt"].id),
            "Exact wording",
        ).outcome
        == "appendix"
    )

    colliding, collision_blocks = make_document(
        (
            PROMPT,
            rectangle,
            BlockSpec(
                "crossing-line",
                "line",
                (40_000, 140_000, 560_000, 140_000),
                values={"stroke_width_mpt": 1_000, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    assert (
        resolve_placement(
            colliding,
            _question(collision_blocks["prompt"].id),
            "Exact wording",
        ).outcome
        == "appendix"
    )

    clean, clean_blocks = make_document((PROMPT, rectangle, NEXT_PROMPT))
    first = resolve_placement(clean, _question(clean_blocks["prompt"].id), "First answer")
    occupied = resolve_placement(
        clean,
        _question(clean_blocks["prompt"].id),
        "Second answer",
        occupied_plans=(first,),
    )
    assert first.outcome == "inline"
    assert occupied.outcome == "appendix"


@pytest.mark.parametrize(
    "collider",
    [
        BlockSpec(
            "source-line",
            "line",
            (40_000, 140_000, 560_000, 140_000),
            values={"stroke_width_mpt": 1_000, "stroked": True},
        ),
        BlockSpec(
            "source-rect",
            "rect",
            (40_000, 120_000, 560_000, 160_000),
            values={"filled": True, "stroked": True},
        ),
    ],
    ids=("line", "rect"),
)
def test_source_line_or_rectangle_collision_blocks_inline_placement(
    collider: BlockSpec,
) -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "field",
                "form_field",
                (50_000, 100_000, 550_000, 180_000),
                values={"field_name": "answer", "writable": True, "multiline": True},
            ),
            collider,
            NEXT_PROMPT,
        )
    )

    plan = resolve_placement(document, _question(blocks["prompt"].id), "Exact wording")
    assert plan.outcome == "appendix"


def test_overflow_and_missing_inline_space_use_appendix() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "small-rect",
                "rect",
                (50_000, 100_000, 170_000, 126_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    overflow = resolve_placement(
        document,
        _question(blocks["prompt"].id),
        "This exact answer cannot fit inside such a small bounded region.",
    )
    assert overflow.outcome == "appendix"

    no_region, no_region_blocks = make_document((PROMPT,))
    assert (
        resolve_placement(
            no_region,
            _question(no_region_blocks["prompt"].id),
            "Still a grounded answer.",
        ).outcome
        == "appendix"
    )


@pytest.mark.parametrize(
    ("rotation", "crop_box"),
    [
        (90, None),
        (0, (18_000, 18_000, 594_000, 774_000)),
    ],
)
def test_nonidentity_page_geometry_is_appendix_only(
    rotation: int,
    crop_box: tuple[int, int, int, int] | None,
) -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "rect",
                "rect",
                (50_000, 100_000, 550_000, 180_000),
                values={"filled": False, "stroked": True},
            ),
        ),
        rotation=rotation,
        crop_box=crop_box,
    )
    plan = resolve_placement(document, _question(blocks["prompt"].id), "Exact wording")
    assert plan.outcome == "appendix"
    assert plan.region is None


def test_ungrounded_question_rejects_but_forced_appendix_does_not() -> None:
    document, blocks = make_document((PROMPT, NEXT_PROMPT))

    rejected = resolve_placement(
        document,
        _question(blocks["prompt"].id, grounded=False),
        "An answer",
    )
    appendix = resolve_placement(
        document,
        _question(blocks["prompt"].id),
        "An answer",
        force_appendix=True,
    )
    assert rejected.outcome == "reject"
    assert rejected.rejection_code == "unsafe_question_evidence"
    assert appendix.outcome == "appendix"
    assert appendix.appendix_entry_id is not None


def test_unicode_is_preserved_and_unsupported_glyph_fails_explicitly() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "rect",
                "rect",
                (50_000, 100_000, 550_000, 190_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    exact = "Café stays naïve—CO₂ and H₂O remain exact."
    plan = resolve_placement(document, _question(blocks["prompt"].id), exact)

    assert plan.outcome == "inline"
    assert plan.fit is not None
    assert plan.fit.reconstructed_text() == exact
    assert plan.exact_text_sha256 == sha256_hex(exact.encode("utf-8"))
    assert (
        _error_code(
            resolve_placement,
            document,
            _question(blocks["prompt"].id),
            "DNA 🧬",
        )
        == "unsupported_glyph"
    )


def test_placement_and_scratch_fit_are_deterministic() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "rect",
                "rect",
                (50_000, 100_000, 550_000, 190_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    evidence = _question(blocks["prompt"].id)
    first = resolve_placement(document, evidence, "A deterministic exact answer.")
    second = resolve_placement(document, evidence, "A deterministic exact answer.")

    assert first == second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.placement_hash == second.placement_hash
    assert first.fit is not None
    assert first.fit.scratch_pdf_sha256 == second.fit.scratch_pdf_sha256  # type: ignore[union-attr]


def test_question_evidence_and_placement_metadata_parse_strictly() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "rect",
                "rect",
                (50_000, 100_000, 550_000, 190_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    evidence = _question(blocks["prompt"].id)
    plan = resolve_placement(document, evidence, "An exact answer.")

    assert QuestionEvidence.from_bytes(evidence.canonical_bytes()) == evidence
    assert parse_placement_plan(plan.canonical_bytes()) == plan
    assert (
        _error_code(QuestionEvidence.from_bytes, b" " + evidence.canonical_bytes())
        == "unsafe_question_evidence"
    )
    assert _error_code(parse_placement_plan, b" " + plan.canonical_bytes()) == "placement_changed"

    unknown = json.loads(plan.canonical_bytes())
    unknown["client_coordinates"] = [1, 2, 3, 4]
    assert _error_code(parse_placement_plan, canonical_json_bytes(unknown)) == "placement_changed"

    stale_algorithm = json.loads(plan.canonical_bytes())
    stale_algorithm["algorithm_version"] = "future-algorithm"
    body = {key: value for key, value in stale_algorithm.items() if key != "placement_hash"}
    stale_algorithm["placement_hash"] = sha256_hex(canonical_json_bytes(body))
    assert (
        _error_code(parse_placement_plan, canonical_json_bytes(stale_algorithm))
        == "placement_changed"
    )

    invalid_outcome = json.loads(plan.canonical_bytes())
    invalid_outcome["outcome"] = "client_selected_coordinates"
    body = {key: value for key, value in invalid_outcome.items() if key != "placement_hash"}
    invalid_outcome["placement_hash"] = sha256_hex(canonical_json_bytes(body))
    assert (
        _error_code(parse_placement_plan, canonical_json_bytes(invalid_outcome))
        == "placement_changed"
    )

    duplicate_evidence_key = evidence.canonical_bytes().replace(
        b'"grounded":true',
        b'"grounded":true,"grounded":true',
        1,
    )
    assert (
        _error_code(QuestionEvidence.from_bytes, duplicate_evidence_key)
        == "unsafe_question_evidence"
    )


def test_reviewed_placement_detects_stale_source_ir_and_changed_geometry() -> None:
    document, blocks = make_document(
        (
            PROMPT,
            BlockSpec(
                "rect",
                "rect",
                (50_000, 100_000, 550_000, 190_000),
                values={"filled": False, "stroked": True},
            ),
            NEXT_PROMPT,
        )
    )
    evidence = _question(blocks["prompt"].id)
    plan = resolve_placement(document, evidence, "An exact answer.")

    assert validate_placement_plan(document, evidence, "An exact answer.", plan) == plan
    assert (
        _error_code(
            validate_placement_plan,
            document,
            evidence,
            "An exact answer.",
            replace(plan, source_sha256="0" * 64),
        )
        == "stale_source"
    )
    assert (
        _error_code(
            validate_placement_plan,
            document,
            evidence,
            "An exact answer.",
            replace(plan, physical_ir_sha256="0" * 64),
        )
        == "stale_physical_ir"
    )
    assert (
        _error_code(
            validate_placement_plan,
            document,
            evidence,
            "An exact answer.",
            replace(plan, placement_hash="0" * 64),
        )
        == "placement_changed"
    )


def test_canonical_box_conversion_respects_rotation_and_crop_transform() -> None:
    document, _ = make_document(
        (),
        rotation=90,
        crop_box=(18_000, 18_000, 594_000, 774_000),
    )
    box = CanonicalBox(10_000, 20_000, 30_000, 40_000)

    assert canonical_box_to_pdf_points(document.pages[0], box) == (38.0, 28.0, 58.0, 48.0)
    assert (
        _error_code(
            canonical_box_to_pdf_points,
            document.pages[0],
            CanonicalBox(0, 0, document.pages[0].width_mpt + 1, 1),
        )
        == "invalid_physical_evidence"
    )
