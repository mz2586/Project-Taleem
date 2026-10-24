"""Ports the reporting context depends on. Adapters implement them; nothing here imports another
context. School, identity, learning and the curriculum read model are reached only through these
protocols, wired in the composition root (``main.py``)."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

from ..domain.report_card import (
    EvidenceRecord,
    HomeworkOutcome,
    LessonPin,
    MasteryEvent,
    ReportCard,
    ReportingAuditEvent,
)

# ------------------------------------------------------------------------------- persistence


class ReportCardRepository(Protocol):
    """Issued cards. A stored card is never updated except its one-time acknowledgement."""

    def add(self, card: ReportCard) -> None: ...
    def get(self, card_id: str) -> ReportCard | None: ...
    def for_student(self, student_ref: str) -> list[ReportCard]: ...
    def for_class(self, organization_id: str, class_id: str) -> list[ReportCard]: ...
    def for_slot(
        self, student_ref: str, class_id: str, period_start: int, period_end: int
    ) -> list[ReportCard]: ...
    def successors(self, card_ids: list[str]) -> dict[str, str]:
        """``{card_id: id of the card that supersedes it}`` for those that have one."""

    def acknowledge(self, card_id: str, guardian_ref: str, at: float) -> bool:
        """Set the acknowledgement once; False (and nothing changes) if it is already set."""


class ReportingAudit(Protocol):
    def add(self, event: ReportingAuditEvent) -> None: ...


class ReportingOutbox(Protocol):
    def add(
        self, *, event_type: str, aggregate_id: str, student_ref: str, payload: dict[str, Any]
    ) -> None: ...


class ReportingUnitOfWork(Protocol):
    @property
    def cards(self) -> ReportCardRepository: ...
    @property
    def audit(self) -> ReportingAudit: ...
    @property
    def outbox(self) -> ReportingOutbox: ...

    def commit(self) -> None: ...
    def __enter__(self) -> ReportingUnitOfWork: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


# ------------------------------------------------------------------------- other contexts


@dataclass(frozen=True)
class ClassRoster:
    """A teacher's own class with its current members (school context)."""

    class_id: str
    organization_id: str
    class_name: str
    organization_name: str
    curriculum_pack_id: str
    student_refs: tuple[str, ...]
    teacher_name: str = ""


class SchoolDirectory(Protocol):
    def teacher_class(self, *, teacher_ref: str, class_id: str) -> ClassRoster:
        """The teacher's own class. Raises a 404 Problem for any other class (another teacher's,
        another organization's, or none) and a 403 Problem for a locked or suspended teacher."""

    def teacher_classes(self, teacher_ref: str) -> list[ClassRoster]:
        """Every class the teacher owns, with members (403 Problem for an inactive teacher)."""

    def marked_homework(self, student_ref: str) -> list[HomeworkOutcome]:
        """Every marked submission of the learner, across their classes."""


@dataclass(frozen=True)
class LearnerVisibility:
    display_name: str | None  # None while hidden: a hidden learner's name is never shown
    reason: str | None = None  # None = visible; else ``consent_withdrawn`` | ``inactive``

    @property
    def visible(self) -> bool:
        return self.reason is None


class LearnerDirectory(Protocol):
    """Identity, read live (never cached)."""

    def guardian_of(self, student_ref: str) -> str | None: ...

    def display_name(self, student_ref: str) -> str | None: ...

    def learning_refusal(self, student_ref: str) -> str | None:
        """None while the learner has an active account and live learning consent; otherwise
        ``inactive`` or ``consent_withdrawn``. (System issuance needs no ``progress_sharing``:
        no teacher sees the card.)"""

    def teacher_visibility(self, student_refs: list[str]) -> dict[str, LearnerVisibility]:
        """For every ref: whether a teacher may see the learner right now (live learning consent,
        an active account and the guardian's ``progress_sharing``) and, if not, why."""


class LearningRecords(Protocol):
    """The learning context's immutable evidence and its mastery events, for one learner."""

    def evidence(self, student_ref: str) -> list[EvidenceRecord]: ...
    def mastery_events(self, student_ref: str) -> list[MasteryEvent]: ...


class PublishedLessons(Protocol):
    def pins(self) -> dict[str, LessonPin]:
        """The published lesson (id, version, pack, subject, title) of each objective code."""
