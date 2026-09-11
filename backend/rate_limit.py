"""Small bounded rate limiter for expensive application entry points."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import deque
from collections.abc import Callable
from threading import RLock


class RateLimitExceeded(RuntimeError):
    code = "rate_limit_exceeded"


class SlidingWindowRateLimiter:
    """Thread-safe process guard with hashed keys and bounded cardinality.

    This complements platform-level request controls. It never stores a raw IP,
    cookie, owner identifier, or assignment identifier.
    """

    def __init__(
        self,
        *,
        secret: str,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        if not secret:
            raise ValueError("rate-limit secret is required")
        if max_keys < 1:
            raise ValueError("max_keys must be positive")
        self._secret = secret.encode("utf-8")
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = RLock()

    def check(
        self,
        *,
        scope: str,
        subject: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        if not scope or not subject:
            raise ValueError("rate-limit scope and subject are required")
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate-limit bounds must be positive")
        now = self._clock()
        key = hmac.new(
            self._secret,
            f"{scope}\0{subject}".encode(),
            hashlib.sha256,
        ).hexdigest()
        cutoff = now - window_seconds
        with self._lock:
            if key not in self._events and len(self._events) >= self._max_keys:
                self._prune(cutoff)
                if len(self._events) >= self._max_keys:
                    oldest_key = min(
                        self._events,
                        key=lambda item: self._events[item][-1],
                    )
                    self._events.pop(oldest_key)
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                raise RateLimitExceeded("request rate exceeded")
            events.append(now)

    def _prune(self, cutoff: float) -> None:
        empty: list[str] = []
        for key, events in self._events.items():
            while events and events[0] <= cutoff:
                events.popleft()
            if not events:
                empty.append(key)
        for key in empty:
            self._events.pop(key, None)
            if len(self._events) <= self._max_keys:
                break
