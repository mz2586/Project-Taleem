"""Ports the privacy service orchestrates: one ``LearnerDataPort`` per store of learner data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from ..domain.policy import RetainedSet


@dataclass(frozen=True)
class Tombstone:
    """The minimum record an erasure keeps (see ``RetainedSet``). Never carries the student_ref."""

    tombstone_ref: str
    guardian_ref: str
    requested_at: float
    confirmed_at: float
    scope: tuple[str, ...]  # the stores erased
    retained: dict[str, Any]  # RetainedSet.describe()


@runtime_checkable
class LearnerDataPort(Protocol):
    """Everything one store holds about a learner: export it, erase it, prove it is gone."""

    @property
    def name(self) -> str: ...

    def covers(self) -> tuple[str, ...]:
        """Every table / in-process store this port is responsible for (``schema.table``)."""
        ...

    def export(self, student_ref: str) -> dict[str, Any]: ...

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        """Remove or irreversibly anonymize; return affected rows per table."""
        ...

    def remaining(self, student_ref: str) -> dict[str, int]:
        """Rows still referencing ``student_ref`` per table (the verification sweep)."""
        ...

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        """Rows of a retention class older than ``cutoff``; ``None`` if this port has none."""
        ...

    def blockers(self) -> list[str]:
        """Reasons this store cannot be erased right now (checked before anything is touched)."""
        ...


@runtime_checkable
class IdentityDataPort(LearnerDataPort, Protocol):
    """The identity store additionally answers ownership and keeps the tombstone (atomically with
    the deletion of the learner account)."""

    def guardian_of(self, student_ref: str) -> str | None: ...

    def erase_with_tombstone(
        self, student_ref: str, retained: RetainedSet, tombstone: Tombstone | None
    ) -> dict[str, int]: ...
