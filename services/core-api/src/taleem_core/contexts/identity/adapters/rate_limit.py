"""Per-client rate limiting for the unauthenticated identity routes.

Two implementations sit behind one interface (``Limiter.check``):

- ``RateLimiter`` — **process-local**, a sliding log per client. Correct only while a single
  process serves traffic, so it is used for local/dev/tests (in-memory SQLite).
- ``SharedRateLimiter`` — a sliding-window *counter* held in PostgreSQL
  (``identity.rate_limit_bucket``, alembic ``0006``). Every instance — replicas, or the many short
  lived serverless invocations Vercel runs — increments the same row with one atomic upsert, so the
  budget is the platform's budget rather than a per-instance one. It is wired whenever a real
  database is configured (see ``main.py``).

What this limiter is for: blunting distributed guessing against *many* accounts, which the durable
per-account lockout (five wrong PINs, wherever they were served) cannot see, and keeping a public
endpoint from being a free PBKDF2 amplifier. The lockout remains the per-account control.

Client identifiers never reach the database raw: the shared store keys on a domain-separated
SHA-256 digest of the identifier (the same reduction the consent evidence applies to an IP), and a
row lives for at most two windows before it is purged.
"""

from __future__ import annotations

import hashlib
import math
from collections import deque
from collections.abc import Callable
from typing import Protocol

from ....platform import observability
from ....platform.errors import Problem

# Bound on distinct client keys tracked at once, so the limiter cannot itself become a memory leak
# under a spray of forged X-Forwarded-For values.
MAX_TRACKED_CLIENTS = 10_000

# How often (in checks per instance) the shared limiter deletes expired buckets. The first check on
# a fresh instance also purges, so short-lived serverless instances still clean up.
DEFAULT_PURGE_EVERY = 500


def rate_limited(retry_after_seconds: int) -> Problem:
    return Problem(
        429,
        "RATE_LIMITED",
        "Too many requests",
        f"too many attempts; try again in {retry_after_seconds} seconds",
    )


class Limiter(Protocol):
    """What the identity router needs: record an attempt, or raise a 429."""

    def check(self, key: str) -> None: ...


class RateLimiter:
    """Process-local sliding-log limiter (local/dev/tests, and the shared limiter's fallback)."""

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


InMemoryRateLimiter = RateLimiter


class RateLimitStore(Protocol):
    """Shared counter storage. ``hit`` must be atomic across processes."""

    def hit(
        self, scope: str, key_digest: str, window_start: int, window_seconds: int
    ) -> tuple[int, int]:
        """Increment the bucket for ``window_start`` and return ``(current, previous)`` hit counts,
        where ``previous`` is the bucket for the window immediately before it (0 if absent)."""
        ...

    def purge_expired(self, now: float) -> int:
        """Delete buckets that can no longer influence a decision; return how many went."""
        ...


def client_key_digest(scope: str, key: str) -> str:
    """Reduce a client identifier to a non-reversible, scope-bound digest before it is stored."""
    return hashlib.sha256(f"taleem.rate_limit:{scope}:{key}".encode()).hexdigest()


class SharedRateLimiter:
    """Sliding-window counter over a shared store.

    The estimate is the classic two-bucket approximation: ``previous * (1 - elapsed) + current``,
    where ``elapsed`` is the fraction of the current fixed window already gone. Unlike a bare fixed
    window it does not admit a double burst across a window boundary, and it needs one atomic upsert
    per attempt rather than a row per hit.

    Every attempt is counted, including refused ones, so a client that keeps hammering stays
    refused instead of earning a fresh allowance as old hits age out.

    If the shared store fails, the limiter degrades to its process-local fallback rather than to no
    limit at all: an outage of the store is then a speed bump per instance, which is the guarantee
    the platform had before, and the durable per-account lockout is unaffected.
    """

    def __init__(
        self,
        scope: str,
        limit: int,
        window_seconds: float,
        clock: Callable[[], float],
        store: RateLimitStore,
        *,
        purge_every: int = DEFAULT_PURGE_EVERY,
    ) -> None:
        if window_seconds < 1:
            raise ValueError("shared rate-limit windows are whole seconds (>= 1)")
        self._scope = scope
        self._limit = limit
        self._window = int(window_seconds)
        self._now = clock
        self._store = store
        self._purge_every = max(1, purge_every)
        self._checks = 0
        self._fallback = RateLimiter(limit, float(self._window), clock)

    def check(self, key: str) -> None:
        now = self._now()
        self._maybe_purge(now)
        window_start = int(now // self._window) * self._window
        try:
            current, previous = self._store.hit(
                self._scope, client_key_digest(self._scope, key), window_start, self._window
            )
        except Exception as exc:  # noqa: BLE001 — any store failure degrades, never disables
            observability.record_event("taleem_rate_limit_store_errors_total", scope=self._scope)
            observability.log_event(
                "rate_limit_store_unavailable", scope=self._scope, error=type(exc).__name__
            )
            self._fallback.check(key)
            return
        elapsed = (now - window_start) / self._window
        estimate = previous * (1.0 - elapsed) + current
        if estimate > self._limit:
            observability.record_event("taleem_rate_limited_total", scope=self._scope)
            raise rate_limited(max(1, math.ceil(window_start + self._window - now)))

    def _maybe_purge(self, now: float) -> None:
        self._checks += 1
        if (self._checks - 1) % self._purge_every:
            return  # purge on the first check of an instance, then every ``purge_every`` checks
        try:
            self._store.purge_expired(now)
        except Exception as exc:  # noqa: BLE001 — cleanup is best-effort, never a request failure
            observability.log_event(
                "rate_limit_purge_failed", scope=self._scope, error=type(exc).__name__
            )
