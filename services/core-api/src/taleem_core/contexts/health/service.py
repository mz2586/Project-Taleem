"""Health & readiness aggregation (pure-stdlib).

Liveness = the process is up. Readiness = declared dependencies report healthy
(docs/35-deployment-architecture.md §3, docs/38-monitoring.md).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    probe: Callable[[], bool]


class HealthService:
    def __init__(self, version: str, checks: list[Check] | None = None) -> None:
        self._version = version
        self._checks = checks or []

    def live(self) -> dict[str, object]:
        return {"status": "ok", "version": self._version}

    def ready(self) -> tuple[bool, dict[str, object]]:
        results = {c.name: bool(c.probe()) for c in self._checks}
        ok = all(results.values()) if results else True
        return ok, {
            "status": "ok" if ok else "degraded",
            "checks": results,
            "version": self._version,
        }
