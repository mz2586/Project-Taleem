"""Immutable version snapshots (pure-stdlib).

A Version is a frozen snapshot of a lesson at publish time. Snapshotting is done by
the application service to keep this module free of a Lesson dependency (no import cycle).
See docs/10-curriculum-studio/AUTHORING_WORKFLOW.md §4
and docs/05-education/21-curriculum-engine.md §5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Version:
    version: int
    created_at: float
    author_role: str
    content_hash: str
    change_summary: str
    snapshot: dict[str, Any] = field(default_factory=dict)  # serialized lesson at this version


@dataclass
class VersionHistory:
    """Append-only history of published versions."""

    versions: list[Version] = field(default_factory=list)

    def add(self, version: Version) -> None:
        self.versions.append(version)

    def latest(self) -> Version | None:
        return self.versions[-1] if self.versions else None

    def get(self, version: int) -> Version | None:
        for v in self.versions:
            if v.version == version:
                return v
        return None

    def next_version_number(self) -> int:
        latest = self.latest()
        return latest.version + 1 if latest is not None else 1
