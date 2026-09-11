from __future__ import annotations

from datetime import timedelta

from backend.domain.models import (
    AssignmentManifest,
    AssignmentStatus,
    ObjectReference,
    PlacementCapability,
    QuestionState,
)
from backend.tests.domain.conftest import NOW, OWNER_HASH


def make_manifest(
    *,
    owner_hash: str = OWNER_HASH,
    question_count: int = 1,
    version: int = 1,
    status: AssignmentStatus = AssignmentStatus.READY,
) -> AssignmentManifest:
    questions = tuple(
        QuestionState(
            question_id=f"q_{index}",
            index=index,
            display_identifier=str(index),
            exact_prompt=("Why do plants need sunlight?" if index == 1 else f"Question {index}?"),
            prompt_block_ids=(f"p1_b{index}",),
            context_block_ids=(),
            page_number=1,
            placement_capability=(
                PlacementCapability.INLINE_POSSIBLE
                if index == 1
                else PlacementCapability.APPENDIX_ONLY
            ),
        )
        for index in range(1, question_count + 1)
    )
    return AssignmentManifest(
        assignment_id="asg_test_01",
        owner_hash=owner_hash,
        version=version,
        status=status,
        title="Biology — cells & energy",
        source_filename="biology-worksheet.pdf",
        source=ObjectReference(
            key="assignments/asg_test_01/source/original.pdf",
            generation=7,
            sha256="c" * 64,
            size_bytes=1024,
            content_type="application/pdf",
        ),
        questions=questions,
        created_at=NOW,
        expires_at=NOW + timedelta(hours=24),
    )
