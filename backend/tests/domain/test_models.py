from __future__ import annotations

import pytest
from pydantic import ValidationError


def test_question_requires_unique_restart_safe_source_evidence(manifest_factory) -> None:
    manifest = manifest_factory()
    question = manifest.questions[0]
    with pytest.raises(ValidationError, match="must be unique"):
        question.model_copy(
            update={"context_block_ids": question.prompt_block_ids}
        ).__class__.model_validate(
            {
                **question.model_dump(),
                "context_block_ids": question.prompt_block_ids,
            }
        )


@pytest.mark.parametrize(
    "filename",
    ["", "   ", ".", "..", "../worksheet.pdf", "folder/worksheet.pdf", "bad\x00.pdf"],
)
def test_source_filename_is_display_only_and_path_unsafe_names_are_rejected(
    manifest_factory, filename: str
) -> None:
    manifest = manifest_factory()
    with pytest.raises(ValidationError):
        manifest.__class__.model_validate({**manifest.model_dump(), "source_filename": filename})


def test_question_source_order_is_invariant(manifest_factory) -> None:
    manifest = manifest_factory(question_count=2)
    with pytest.raises(ValidationError, match="source order"):
        manifest.__class__.model_validate(
            {**manifest.model_dump(), "questions": tuple(reversed(manifest.questions))}
        )
