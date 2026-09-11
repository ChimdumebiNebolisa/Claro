from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import ValidationError

from backend.config import Settings
from backend.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter

COOKIE_SIGNING_MATERIAL = "owner-v2-9f14d6c2-A7xQ4mZ8pL3sK5wN"
REVIEW_SIGNING_MATERIAL = "review-v2-6b83e1a9-R2tY7uI4oP8dF5hJ"
RATE_LIMIT_SIGNING_MATERIAL = "l" * 32


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"storage_backend": "local"}, "production requires GCS storage"),
        (
            {"storage_backend": "gcs"},
            "production requires CLAROS_GCS_BUCKET",
        ),
        (
            {"storage_backend": "gcs", "gcs_bucket": "private-bucket"},
            "production cookie secret must be at least 32 UTF-8 bytes",
        ),
        (
            {
                "storage_backend": "gcs",
                "gcs_bucket": "private-bucket",
                "cookie_secret": COOKIE_SIGNING_MATERIAL,
            },
            "production review token secret must be at least 32 UTF-8 bytes",
        ),
        (
            {
                "storage_backend": "gcs",
                "gcs_bucket": "private-bucket",
                "cookie_secret": COOKIE_SIGNING_MATERIAL,
                "review_token_secret": REVIEW_SIGNING_MATERIAL,
            },
            "production requires an HTTPS public origin",
        ),
    ],
)
def test_production_configuration_fails_closed_at_each_boundary(
    overrides: Mapping[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(environment="production", **overrides)


def test_only_valid_production_configuration_enables_secure_cookies() -> None:
    production = Settings(
        environment="production",
        storage_backend="gcs",
        gcs_bucket="private-bucket",
        cookie_secret=COOKIE_SIGNING_MATERIAL,
        review_token_secret=REVIEW_SIGNING_MATERIAL,
        public_origin="https://claros.example",
    )

    assert production.secure_cookie is True
    assert production.trusted_hosts == ("claros.example",)
    assert Settings(environment="test").secure_cookie is False
    assert Settings(environment="test").trusted_hosts == (
        "127.0.0.1",
        "testserver",
        "localhost",
    )


def test_application_request_budget_keeps_cloud_run_headroom() -> None:
    assert Settings(environment="test").request_timeout_seconds == 270
    with pytest.raises(ValidationError):
        Settings(environment="test", request_timeout_seconds=300)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {
                "cookie_secret": "short-owner-secret",
                "review_token_secret": REVIEW_SIGNING_MATERIAL,
            },
            "cookie secret must be at least 32 UTF-8 bytes",
        ),
        (
            {
                "cookie_secret": "x" * 32,
                "review_token_secret": REVIEW_SIGNING_MATERIAL,
            },
            "cookie secret must use high-entropy signing material",
        ),
        (
            {
                "cookie_secret": COOKIE_SIGNING_MATERIAL,
                "review_token_secret": "y" * 32,
            },
            "review token secret must use high-entropy signing material",
        ),
        (
            {
                "cookie_secret": COOKIE_SIGNING_MATERIAL,
                "review_token_secret": COOKIE_SIGNING_MATERIAL,
            },
            "cookie and review token secrets must be distinct",
        ),
    ],
)
def test_production_rejects_weak_or_reused_signing_material(
    overrides: Mapping[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(
            environment="production",
            storage_backend="gcs",
            gcs_bucket="private-bucket",
            public_origin="https://claros.example",
            **overrides,
        )


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "null",
        "ftp://claros.example",
        "https://claros.example/",
        "https://claros.example/app",
        "https://claros.example?query=1",
        "https://claros.example#fragment",
        "https://user@claros.example",
        "https://claros.example:bad",
        "https://claros.example:65536",
        "https://claros.example:0",
        "https://[2001:db8::1]",
        "https://claros.example\\@attacker.example",
        "https://claros.example,https://attacker.example",
        " https://claros.example",
        "https://claros.example\x00.attacker.example",
        "https://" + ("a" * 506),
    ],
)
def test_public_origin_must_be_one_exact_canonicalizable_origin(origin: str) -> None:
    with pytest.raises(ValidationError, match="origin"):
        Settings(environment="test", public_origin=origin)


@pytest.mark.parametrize(
    "arguments",
    [
        {"secret": ""},
        {"secret": "test-secret", "max_keys": 0},
    ],
)
def test_rate_limiter_rejects_unsafe_configuration(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(**arguments)


@pytest.mark.parametrize(
    "arguments",
    [
        {"scope": "", "subject": "student", "limit": 1, "window_seconds": 10},
        {"scope": "upload", "subject": "", "limit": 1, "window_seconds": 10},
        {"scope": "upload", "subject": "student", "limit": 0, "window_seconds": 10},
        {"scope": "upload", "subject": "student", "limit": 1, "window_seconds": 0},
    ],
)
def test_rate_limiter_rejects_empty_keys_and_nonpositive_bounds(
    arguments: dict[str, Any],
) -> None:
    limiter = SlidingWindowRateLimiter(secret=RATE_LIMIT_SIGNING_MATERIAL)

    with pytest.raises(ValueError):
        limiter.check(**arguments)


def test_rate_limiter_enforces_window_without_retaining_raw_subjects() -> None:
    now = [100.0]
    limiter = SlidingWindowRateLimiter(secret=RATE_LIMIT_SIGNING_MATERIAL, clock=lambda: now[0])

    limiter.check(scope="upload", subject="203.0.113.4", limit=1, window_seconds=10)
    with pytest.raises(RateLimitExceeded, match="request rate exceeded"):
        limiter.check(scope="upload", subject="203.0.113.4", limit=1, window_seconds=10)

    assert "203.0.113.4" not in repr(limiter._events)
    now[0] = 110.0
    limiter.check(scope="upload", subject="203.0.113.4", limit=1, window_seconds=10)


def test_rate_limiter_prunes_expired_keys_and_evicts_oldest_active_key() -> None:
    now = [0.0]
    limiter = SlidingWindowRateLimiter(
        secret=RATE_LIMIT_SIGNING_MATERIAL,
        clock=lambda: now[0],
        max_keys=2,
    )

    limiter.check(scope="voice", subject="oldest", limit=1, window_seconds=10)
    now[0] = 1.0
    limiter.check(scope="voice", subject="newer", limit=1, window_seconds=10)
    now[0] = 2.0
    limiter.check(scope="voice", subject="third", limit=1, window_seconds=10)
    assert len(limiter._events) == 2

    # The evicted oldest subject can enter again, forcing the other oldest key out.
    now[0] = 3.0
    limiter.check(scope="voice", subject="oldest", limit=1, window_seconds=10)
    assert len(limiter._events) == 2

    # Once all retained timestamps expire, cardinality pruning admits another key.
    now[0] = 20.0
    limiter.check(scope="voice", subject="after-expiry", limit=1, window_seconds=10)
    assert len(limiter._events) <= 2
