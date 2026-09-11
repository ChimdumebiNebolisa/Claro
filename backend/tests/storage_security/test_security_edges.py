from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from itsdangerous import URLSafeSerializer

from backend.domain.models import Placement
from backend.security import (
    _OWNER_COOKIE_SALT,
    AssignmentAccessDenied,
    OriginDenied,
    OwnerSessionError,
    confirmation_request_digest,
    create_owner_session,
    exact_text_hash,
    issue_review_token,
    owner_hash,
    require_assignment_owner,
    require_same_origin,
    review_token_digest,
    verify_owner_session,
)
from backend.tests.domain.conftest import NOW

COOKIE_SECRET = bytes.fromhex("22" * 32)
REVIEW_SECRET = bytes.fromhex("33" * 32)
NOW_SECONDS = int(NOW.timestamp())
BASE_PAYLOAD = {
    "expires_at": NOW_SECONDS + 3_600,
    "issued_at": NOW_SECONDS,
    "owner_id": "own_student_a",
    "version": 1,
}


def _signed(payload: Any) -> str:
    return URLSafeSerializer(COOKIE_SECRET, salt=_OWNER_COOKIE_SALT).dumps(payload)


def test_owner_session_default_identifier_is_opaque_and_verifiable() -> None:
    issued, cookie = create_owner_session(COOKIE_SECRET, now=NOW, ttl_seconds=60)

    assert issued.owner_id.startswith("own_")
    assert verify_owner_session(cookie, COOKIE_SECRET, now=NOW) == issued


@pytest.mark.parametrize("ttl_seconds", [True, 0, 86_401])
def test_owner_session_rejects_invalid_ttl(ttl_seconds: int) -> None:
    with pytest.raises(ValueError, match="owner session TTL"):
        create_owner_session(COOKIE_SECRET, now=NOW, ttl_seconds=ttl_seconds)


def test_owner_session_rejects_naive_time_and_invalid_secrets() -> None:
    with pytest.raises(ValueError, match="timezone"):
        create_owner_session(COOKIE_SECRET, now=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="cannot be empty"):
        create_owner_session(b"", now=NOW)
    with pytest.raises(ValueError, match="cannot be empty"):
        create_owner_session(object(), now=NOW)  # type: ignore[arg-type]


@pytest.mark.parametrize("cookie", [None, "", "x" * 2_049])
def test_owner_session_rejects_malformed_cookie_boundaries(cookie: str | None) -> None:
    with pytest.raises(OwnerSessionError, match="invalid"):
        verify_owner_session(cookie, COOKIE_SECRET, now=NOW)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        ["not", "an", "object"],
        {"owner_id": "own_student_a"},
        {**BASE_PAYLOAD, "version": 2},
        {**BASE_PAYLOAD, "owner_id": "../student"},
        {**BASE_PAYLOAD, "issued_at": True},
        {**BASE_PAYLOAD, "expires_at": 10**30},
        {
            **BASE_PAYLOAD,
            "issued_at": NOW_SECONDS + 61,
            "expires_at": NOW_SECONDS + 121,
        },
        {**BASE_PAYLOAD, "expires_at": NOW_SECONDS},
        {**BASE_PAYLOAD, "expires_at": NOW_SECONDS + 86_401},
    ],
)
def test_owner_session_rejects_signed_but_invalid_payloads(payload: Any) -> None:
    with pytest.raises(OwnerSessionError):
        verify_owner_session(_signed(payload), COOKIE_SECRET, now=NOW)


def test_assignment_authorization_hides_invalid_expiry_metadata() -> None:
    _, cookie = create_owner_session(
        COOKIE_SECRET,
        now=NOW,
        owner_id_factory=lambda: "own_student_a",
    )

    with pytest.raises(AssignmentAccessDenied, match="could not be found"):
        require_assignment_owner(
            cookie=cookie,
            stored_owner_hash=owner_hash("own_student_a", COOKIE_SECRET),
            secret=COOKIE_SECRET,
            assignment_expires_at=datetime(2026, 1, 1),
            now=NOW,
        )


@pytest.mark.parametrize(
    "origin",
    [
        "https://[",
        "ftp://claros.example",
        "https://claros.example/?query=1",
        "https://claros.example/#fragment",
        "https://user:password@claros.example",
    ],
)
def test_same_origin_rejects_malformed_and_credentialed_origins(origin: str) -> None:
    with pytest.raises(OriginDenied):
        require_same_origin(origin, "https://claros.example")


def test_exact_text_hash_rejects_non_utf8_surrogate() -> None:
    with pytest.raises(ValueError, match="valid UTF-8"):
        exact_text_hash("answer\ud800")


def test_malformed_review_tokens_share_one_secret_scoped_lookup_digest() -> None:
    malformed = ["", "not-a-token", "rvw_" + "x" * 253, None]
    digests = {
        review_token_digest(token, REVIEW_SECRET)  # type: ignore[arg-type]
        for token in malformed
    }

    assert len(digests) == 1
    assert review_token_digest("rvw_" + "x" * 40, REVIEW_SECRET) not in digests


def test_review_token_binds_exact_text_placement_and_absolute_expiry() -> None:
    token, record = issue_review_token(
        secret=REVIEW_SECRET,
        owner_hash_value="a" * 64,
        assignment_id="asg_test_01",
        question_id="q_1",
        candidate_id="cand_1",
        candidate_version=2,
        text="  José\N{RIGHT SINGLE QUOTATION MARK}s Δ answer.  ",
        placement=Placement.APPENDIX,
        placement_hash="b" * 64,
        assignment_version=7,
        now=NOW,
        ttl_seconds=120,
    )

    assert token.startswith("rvw_")
    assert token not in record.token_digest
    assert record.exact_text_hash == exact_text_hash(
        "  José\N{RIGHT SINGLE QUOTATION MARK}s Δ answer.  "
    )
    assert record.placement is Placement.APPENDIX
    assert record.expires_at == NOW + timedelta(seconds=120)


@pytest.mark.parametrize("ttl_seconds", [True, 0, 601])
def test_review_token_rejects_invalid_ttl(ttl_seconds: int) -> None:
    with pytest.raises(ValueError, match="review token TTL"):
        issue_review_token(
            secret=REVIEW_SECRET,
            owner_hash_value="a" * 64,
            assignment_id="asg_test_01",
            question_id="q_1",
            candidate_id="cand_1",
            candidate_version=1,
            text="answer",
            placement=Placement.INLINE,
            placement_hash="b" * 64,
            assignment_version=1,
            now=NOW,
            ttl_seconds=ttl_seconds,
        )


@pytest.mark.parametrize("token", ["bad", "rvw_short", "rvw_" + "x" * 253])
def test_review_token_rejects_invalid_factory_output(token: str) -> None:
    with pytest.raises(ValueError, match="factory returned an invalid token"):
        issue_review_token(
            secret=REVIEW_SECRET,
            owner_hash_value="a" * 64,
            assignment_id="asg_test_01",
            question_id="q_1",
            candidate_id="cand_1",
            candidate_version=1,
            text="answer",
            placement=Placement.INLINE,
            placement_hash="b" * 64,
            assignment_version=1,
            now=NOW,
            token_factory=lambda: token,
        )


def test_confirmation_request_digest_is_deterministic_and_field_bound() -> None:
    arguments = {
        "token_digest": "a" * 64,
        "assignment_id": "asg_test_01",
        "question_id": "q_1",
        "candidate_id": "cand_1",
        "candidate_version": 2,
        "assignment_version": 7,
    }

    first = confirmation_request_digest(**arguments)
    assert first == confirmation_request_digest(**dict(reversed(arguments.items())))
    assert first != confirmation_request_digest(**{**arguments, "assignment_version": 8})
