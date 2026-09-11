from __future__ import annotations

from datetime import timedelta

import pytest

from backend.security import (
    AssignmentAccessDenied,
    OriginDenied,
    OwnerSessionError,
    OwnerSessionExpired,
    create_owner_session,
    exact_text_hash,
    owner_hash,
    require_assignment_owner,
    require_same_origin,
    review_token_digest,
    verify_owner_session,
)
from backend.tests.domain.conftest import NOW

COOKIE_SECRET = bytes.fromhex("22" * 32)


def test_signed_owner_session_round_trip_and_absolute_expiry() -> None:
    issued, cookie = create_owner_session(
        COOKIE_SECRET,
        now=NOW,
        owner_id_factory=lambda: "own_student_a",
    )

    restored = verify_owner_session(cookie, COOKIE_SECRET, now=NOW + timedelta(hours=23))

    assert restored == issued
    with pytest.raises(OwnerSessionExpired):
        verify_owner_session(cookie, COOKIE_SECRET, now=NOW + timedelta(hours=24))


def test_owner_cookie_rejects_tampering_wrong_secret_and_excessive_lifetime() -> None:
    _, cookie = create_owner_session(
        COOKIE_SECRET,
        now=NOW,
        owner_id_factory=lambda: "own_student_a",
    )
    with pytest.raises(OwnerSessionError):
        verify_owner_session(cookie + "tampered", COOKIE_SECRET, now=NOW)
    with pytest.raises(OwnerSessionError):
        verify_owner_session(cookie, "another-secret", now=NOW)
    with pytest.raises(ValueError):
        create_owner_session(COOKIE_SECRET, now=NOW, ttl_seconds=86_401)


def test_cross_owner_missing_and_expired_access_are_indistinguishable() -> None:
    _, owner_cookie = create_owner_session(
        COOKIE_SECRET,
        now=NOW,
        owner_id_factory=lambda: "own_student_a",
    )
    stored_hash = owner_hash("own_student_b", COOKIE_SECRET)
    failures = []
    for cookie, at in [
        (owner_cookie, NOW),
        (None, NOW),
        (owner_cookie, NOW + timedelta(hours=25)),
    ]:
        with pytest.raises(AssignmentAccessDenied) as caught:
            require_assignment_owner(
                cookie=cookie,
                stored_owner_hash=stored_hash,
                secret=COOKIE_SECRET,
                assignment_expires_at=NOW + timedelta(hours=24),
                now=at,
            )
        failures.append((caught.value.code, str(caught.value)))

    assert failures == [failures[0]] * 3
    assert failures[0][0] == "assignment_not_found"


def test_owner_binding_uses_constant_shape_hmac_not_raw_identifier() -> None:
    digest = owner_hash("own_student_a", COOKIE_SECRET)
    assert len(digest) == 64
    assert "own_student_a" not in digest
    _, cookie = create_owner_session(
        COOKIE_SECRET,
        now=NOW,
        owner_id_factory=lambda: "own_student_a",
    )
    restored = require_assignment_owner(
        cookie=cookie,
        stored_owner_hash=digest,
        secret=COOKIE_SECRET,
        assignment_expires_at=NOW + timedelta(hours=24),
        now=NOW,
    )
    assert restored.owner_id == "own_student_a"


@pytest.mark.parametrize(
    "origin",
    [
        "https://claros.example",
        "https://CLAROS.EXAMPLE:443",
    ],
)
def test_same_origin_accepts_only_equivalent_configured_origin(origin: str) -> None:
    require_same_origin(origin, "https://claros.example")


@pytest.mark.parametrize(
    "origin",
    [
        None,
        "null",
        "https://evil.example",
        "https://claros.example.evil.test",
        "https://claros.example:444",
        "https://claros.example/",
        "https://user@claros.example",
        "https://claros.example/path",
        "javascript:alert(1)",
    ],
)
def test_same_origin_rejects_missing_or_cross_site_mutation(origin: str | None) -> None:
    with pytest.raises(OriginDenied):
        require_same_origin(origin, "https://claros.example")


def test_review_hashes_preserve_exact_unicode_and_are_secret_scoped() -> None:
    text = "  José\N{RIGHT SINGLE QUOTATION MARK}s Δ answer — unchanged.  "
    assert exact_text_hash(text) != exact_text_hash(text.strip())
    token = "rvw_" + "a" * 40
    first = review_token_digest(token, "secret-one")
    assert first != review_token_digest(token, "secret-two")
    assert first != review_token_digest("rvw_" + "b" * 40, "secret-one")
    assert token not in first
