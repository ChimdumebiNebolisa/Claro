from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from backend.domain.models import AssignmentManifest, AssignmentStatus, Placement

NOW = datetime(2026, 9, 4, 15, 0, tzinfo=UTC)
OWNER_HASH = "a" * 64
PLACEMENT_HASH = "b" * 64
TOKEN_SECRET = bytes.fromhex("11" * 32)


@pytest.fixture
def manifest_factory() -> Callable[..., AssignmentManifest]:
    def factory(
        *,
        owner_hash: str = OWNER_HASH,
        question_count: int = 1,
        version: int = 1,
        status: AssignmentStatus = AssignmentStatus.READY,
    ) -> AssignmentManifest:
        from backend.tests.domain.factories import make_manifest

        return make_manifest(
            owner_hash=owner_hash,
            question_count=question_count,
            version=version,
            status=status,
        )

    return factory


@pytest.fixture
def reviewed_manifest(manifest_factory):
    from backend.domain.models import CandidateOrigin, DirectTypedInteraction
    from backend.domain.workflow import issue_review, replace_candidate

    manifest, candidate = replace_candidate(
        manifest_factory(),
        question_id="q_1",
        assignment_version=1,
        exact_text="Plants use sunlight to make glucose.",
        origin=CandidateOrigin.STUDENT_VERBATIM,
        interaction=DirectTypedInteraction(),
        now=NOW,
        candidate_id_factory=lambda: "cand_one",
    )
    review = issue_review(
        manifest,
        owner_hash=OWNER_HASH,
        question_id="q_1",
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        assignment_version=manifest.version,
        placement=Placement.INLINE,
        placement_hash=PLACEMENT_HASH,
        token_secret=TOKEN_SECRET,
        now=NOW,
        token_factory=lambda: "rvw_" + "t" * 40,
    )
    return review.manifest, candidate, review.review_token
