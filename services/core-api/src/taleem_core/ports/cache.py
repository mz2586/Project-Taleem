"""Cache abstraction (pure-stdlib) with an in-memory TTL adapter.

Cache-aside; the cache is never a source of truth (docs/08 §9.3). Redis is the production
adapter behind this port. A `Clock` is injected so TTL is testable without sleeping.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from .clock import Clock, SystemClock


@runtime_checkable
class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_s: float | None = None) -> None: ...
    def delete(self, key: str) -> None: ...


@dataclass
class _Entry:
    value: Any
    expires_at: float | None


class InMemoryCache:
    def __init__(self, clock: Clock | None = None) -> None:
        self._clock: Clock = clock or SystemClock()
        self._store: dict[str, _Entry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and self._clock.now() >= entry.expires_at:
            del self._store[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        expires = None if ttl_s is None else self._clock.now() + ttl_s
        self._store[key] = _Entry(value=value, expires_at=expires)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
