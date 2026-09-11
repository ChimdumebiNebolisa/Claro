from __future__ import annotations

from datetime import timedelta

import pytest

from backend.domain.errors import (
    ReviewTokenExpired,
    ReviewTokenInvalid,
    ReviewTokenStale,
)
from backend.domain.models import (
    CandidateOrigin,
    Placement,
    StudentEditInteraction,
)
from backend.domain.workflow import (
    begin_revision,
    confirm_candidate,
    confirmed_answers_for_export,
    issue_review,
    replace_candidate,
)
from backend.tests.domain.conftest import NOW, OWNER_HASH, PLACEMENT_HASH, TOKEN_SECRET


def _confirm(reviewed_manifest, *, at=NOW, owner_hash=OWNER_HASH):
    manifest, candidate, token = reviewed_manifest
    return confirm_candidate(
        manifest,
        owner_hash=owner_hash,
        question_id="q_1",
        review_token=token,
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        assignment_version=manifest.version,
        token_secret=TOKEN_SECRET,
        now=at,
        confirmation_id_factory=lambda: "cnf_one",
    )


def test_review_persists_only_digest_and_all_required_bindings(reviewed_manifest) -> None:
    manifest, candidate, token = reviewed_manifest
    record = manifest.questions[0].review_tokens[0]

    assert token not in record.model_dump_json()
    assert record.owner_hash == OWNER_HASH
    assert record.assignment_id == manifest.assignment_id
    assert record.question_id == "q_1"
    assert record.candidate_id == candidate.candidate_id
    assert record.candidate_version == candidate.candidate_version
    assert record.assignment_version == manifest.version
    assert record.placement_hash == PLACEMENT_HASH
    assert record.expires_at == NOW + timedelta(minutes=10)


def test_first_confirmation_mutates_once_and_exact_replay_returns_receipt(
    reviewed_manifest,
) -> None:
    first = _confirm(reviewed_manifest)
    manifest, candidate, token = reviewed_manifest
    replay = confirm_candidate(
        first.manifest,
        owner_hash=OWNER_HASH,
        question_id="q_1",
        review_token=token,
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        assignment_version=manifest.version,
        token_secret=TOKEN_SECRET,
        now=NOW + timedelta(seconds=1),
    )

    assert first.replayed is False
    assert first.version == manifest.version + 1
    assert len(first.manifest.confirmation_receipts) == 1
    assert first.confirmed_answer.revision == 1
    assert replay.replayed is True
    assert replay.version == first.version
    assert replay.confirmed_answer == first.confirmed_answer
    assert replay.manifest == first.manifest
    assert len(replay.manifest.confirmation_receipts) == 1


def test_altered_expired_invalid_and_cross_owner_confirmation_fail(
    reviewed_manifest,
) -> None:
    manifest, candidate, token = reviewed_manifest
    first = _confirm(reviewed_manifest)
    with pytest.raises(ReviewTokenStale):
        confirm_candidate(
            first.manifest,
            owner_hash=OWNER_HASH,
            question_id="q_1",
            review_token=token,
            candidate_id="cand_altered",
            candidate_version=candidate.candidate_version,
            assignment_version=manifest.version,
            token_secret=TOKEN_SECRET,
            now=NOW + timedelta(seconds=1),
        )
    with pytest.raises(ReviewTokenExpired):
        _confirm(reviewed_manifest, at=NOW + timedelta(minutes=10))
    with pytest.raises(ReviewTokenInvalid):
        confirm_candidate(
            manifest,
            owner_hash=OWNER_HASH,
            question_id="q_1",
            review_token="rvw_" + "x" * 40,
            candidate_id=candidate.candidate_id,
            candidate_version=candidate.candidate_version,
            assignment_version=manifest.version,
            token_secret=TOKEN_SECRET,
            now=NOW,
        )
    with pytest.raises(ReviewTokenStale):
        _confirm(reviewed_manifest, owner_hash="d" * 64)


def test_candidate_change_invalidates_old_review(reviewed_manifest) -> None:
    manifest, candidate, token = reviewed_manifest
    changed, _ = replace_candidate(
        manifest,
        question_id="q_1",
        assignment_version=manifest.version,
        exact_text="Changed after review.",
        origin=CandidateOrigin.STUDENT_EDITED,
        interaction=StudentEditInteraction(
            prior_candidate_id=candidate.candidate_id,
            prior_candidate_version=candidate.candidate_version,
        ),
        now=NOW + timedelta(seconds=1),
        candidate_id_factory=lambda: "cand_changed",
    )
    with pytest.raises(ReviewTokenStale):
        confirm_candidate(
            changed,
            owner_hash=OWNER_HASH,
            question_id="q_1",
            review_token=token,
            candidate_id=candidate.candidate_id,
            candidate_version=candidate.candidate_version,
            assignment_version=manifest.version,
            token_secret=TOKEN_SECRET,
            now=NOW + timedelta(seconds=2),
        )


def test_revision_retains_confirmed_answer_until_replacement_is_confirmed(
    reviewed_manifest,
) -> None:
    confirmed = _confirm(reviewed_manifest)
    previous = confirmed.confirmed_answer
    revising, draft = begin_revision(
        confirmed.manifest,
        question_id="q_1",
        assignment_version=confirmed.manifest.version,
        now=NOW + timedelta(seconds=2),
    )

    assert revising.version == confirmed.manifest.version + 1
    assert draft.edit_seed == previous.exact_text
    assert revising.questions[0].current_candidate is None
    assert revising.questions[0].confirmed_answer == previous
    export_projection = confirmed_answers_for_export(revising)[0]
    assert export_projection.answer == previous
    assert export_projection.display_identifier == "1"
    assert export_projection.prompt_block_ids == ("p1_b1",)

    revised, candidate = replace_candidate(
        revising,
        question_id="q_1",
        assignment_version=revising.version,
        exact_text="Revised exact answer — still mine.",
        origin=CandidateOrigin.STUDENT_EDITED,
        interaction=StudentEditInteraction(
            prior_candidate_id=previous.candidate_id,
            prior_candidate_version=previous.candidate_version,
        ),
        now=NOW + timedelta(seconds=3),
        candidate_id_factory=lambda: "cand_revision",
    )
    assert revised.questions[0].confirmed_answer == previous
    assert confirmed_answers_for_export(revised)[0].answer == previous

    review = issue_review(
        revised,
        owner_hash=OWNER_HASH,
        question_id="q_1",
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        assignment_version=revised.version,
        placement=Placement.APPENDIX,
        placement_hash="e" * 64,
        token_secret=TOKEN_SECRET,
        now=NOW + timedelta(seconds=4),
        token_factory=lambda: "rvw_" + "r" * 40,
    )
    replacement = confirm_candidate(
        review.manifest,
        owner_hash=OWNER_HASH,
        question_id="q_1",
        review_token=review.review_token,
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.candidate_version,
        assignment_version=review.manifest.version,
        token_secret=TOKEN_SECRET,
        now=NOW + timedelta(seconds=5),
        confirmation_id_factory=lambda: "cnf_two",
    )
    assert replacement.confirmed_answer.revision == 2
    assert replacement.confirmed_answer.exact_text == "Revised exact answer — still mine."
    assert replacement.confirmed_answer.placement == Placement.APPENDIX
