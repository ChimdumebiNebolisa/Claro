from __future__ import annotations

from dataclasses import dataclass

import pytest

from backend.rate_limit import RateLimitExceeded, SlidingWindowRateLimiter


@dataclass
class Clock:
    value: float = 0

    def __call__(self) -> float:
        return self.value


def test_sliding_window_rejects_only_the_bounded_subject() -> None:
    clock = Clock()
    limiter = SlidingWindowRateLimiter(secret="test-secret", clock=clock)  # noqa: S106

    limiter.check(scope="upload", subject="owner-a", limit=2, window_seconds=60)
    limiter.check(scope="upload", subject="owner-a", limit=2, window_seconds=60)
    limiter.check(scope="upload", subject="owner-b", limit=2, window_seconds=60)

    with pytest.raises(RateLimitExceeded):
        limiter.check(scope="upload", subject="owner-a", limit=2, window_seconds=60)

    clock.value = 61
    limiter.check(scope="upload", subject="owner-a", limit=2, window_seconds=60)


def test_scope_is_part_of_the_private_rate_limit_key() -> None:
    limiter = SlidingWindowRateLimiter(secret="test-secret")  # noqa: S106

    limiter.check(scope="upload", subject="same", limit=1, window_seconds=60)
    limiter.check(scope="realtime", subject="same", limit=1, window_seconds=60)
