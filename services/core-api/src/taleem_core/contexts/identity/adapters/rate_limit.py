"""A small fixed-window rate limiter for the unauthenticated identity routes.

Honest about what it is: **process-local**. On a single instance it bounds sign-in attempts per
client; across several instances or serverless invocations an attacker gets that budget per
instance, so it is a speed bump rather than the control.

The control is the *durable* one next to it — the per-account attempt counter in the database, which
locks a learner after five wrong PINs no matter which instance served them. This limiter exists to
blunt distributed guessing against *many* accounts, which the per-account counter cannot see, and to
keep an unauthenticated endpoint from being a free PBKDF2 amplifier.

If the platform later runs behind a shared cache, replacing the store here with that cache upgrades
the guarantee without touching the router.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable

from ....platform.errors import Problem

# Bound on distinct client keys tracked at once, so the limiter cannot itself become a memory leak
# under a spray of forged X-Forwarded-For values.
MAX_TRACKED_CLIENTS = 10_000


def rate_limited(retry_after_seconds: int) -> Problem:
    return Problem(
        429,
        "RATE_LIMITED",
        "Too many requests",
        f"too many attempts; try again in {retry_after_seconds} seconds",
    )


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float]) -> None:
        self._limit = limit
        self._window = window_seconds
        self._now = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        """Record an attempt for ``key``; raise a 429 once the window's budget is spent."""
        now = self._now()
        window_start = now - self._window
        hits = self._hits.get(key)
        if hits is None:
            if len(self._hits) >= MAX_TRACKED_CLIENTS:
                self._evict_expired(window_start)
            hits = deque()
            self._hits[key] = hits
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= self._limit:
            raise rate_limited(int(self._window - (now - hits[0])) + 1)
        hits.append(now)

    def _evict_expired(self, window_start: float) -> None:
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < window_start]
        for key in stale:
            del self._hits[key]
        if len(self._hits) >= MAX_TRACKED_CLIENTS:
            # Every tracked client is currently active. Drop the oldest half rather than refuse
            # service: forgetting a hit is a smaller failure than a self-inflicted outage, and the
            # durable per-account lockout still holds.
            for key in list(self._hits)[: MAX_TRACKED_CLIENTS // 2]:
                del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()
