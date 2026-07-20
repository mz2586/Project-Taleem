"""Feature-flag framework (pure-stdlib).

Decouples deploy from release and enables gradual per-cohort rollout
(docs/03-functional-requirements.md FR-ADM-001, docs/35-deployment-architecture.md §4).

A `FlagProvider` port abstracts the source (env now; a management service later).
Deny-by-default: an unknown flag is OFF.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class FlagProvider(Protocol):
    def is_enabled(self, key: str, *, context: str | None = None) -> bool: ...


class StaticFlagProvider:
    """In-memory provider seeded from a set of enabled keys (e.g. from env)."""

    def __init__(self, enabled: frozenset[str] | set[str] | None = None) -> None:
        self._enabled: set[str] = set(enabled or set())
        # Optional per-context overrides: {"flag_key": {"cohort:123"}}
        self._context_overrides: dict[str, set[str]] = {}

    def enable(self, key: str) -> None:
        self._enabled.add(key)

    def disable(self, key: str) -> None:
        self._enabled.discard(key)

    def enable_for(self, key: str, context: str) -> None:
        self._context_overrides.setdefault(key, set()).add(context)

    def is_enabled(self, key: str, *, context: str | None = None) -> bool:
        if context is not None and context in self._context_overrides.get(key, set()):
            return True
        return key in self._enabled
