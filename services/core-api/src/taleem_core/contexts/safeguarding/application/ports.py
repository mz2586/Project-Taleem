"""Ports the safeguarding service depends on (implemented by the SQL adapters and by fakes)."""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol

from ..domain.model import AuditEntry, Concern, ConcernEvidence, Note, Priority, Status


class ConcernRepository(Protocol):
    def add(self, concern: Concern) -> None: ...

    def get(self, concern_id: str) -> Concern | None: ...

    def save(self, concern: Concern) -> None: ...

    def queue(self, statuses: frozenset[Status], limit: int) -> list[Concern]:
        """Concerns in ``statuses``, highest priority first, oldest first within a priority."""
        ...

    def raised_by(self, raised_by_ref: str, limit: int) -> list[Concern]: ...

    def system_concern_for(self, submission_id: str) -> Concern | None:
        """The disclosure screen's concern about this homework submission, if one was raised."""
        ...

    def open_counts(self) -> dict[Priority, list[float]]:
        """Creation times of every concern still ``open`` (unacknowledged), per priority."""
        ...


class NoteRepository(Protocol):
    def add(self, note: Note) -> None: ...

    def for_concern(self, concern_id: str) -> list[Note]: ...


class EvidenceRepository(Protocol):
    """Immutable snapshots of the flagged homework text, at most one per concern (alembic 0018)."""

    def add(self, evidence: ConcernEvidence) -> None: ...

    def for_concern(self, concern_id: str) -> ConcernEvidence | None: ...


class AuditRepository(Protocol):
    def append(self, entry: AuditEntry) -> None: ...

    def for_concern(self, concern_id: str) -> list[AuditEntry]: ...


class SafeguardingUnitOfWork(Protocol):
    @property
    def concerns(self) -> ConcernRepository: ...
    @property
    def notes(self) -> NoteRepository: ...
    @property
    def audit(self) -> AuditRepository: ...
    @property
    def evidence(self) -> EvidenceRepository: ...

    def __enter__(self) -> SafeguardingUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


class LearnerDirectory(Protocol):
    """The identity facts the service needs, and nothing more."""

    def guardian_of(self, student_ref: str) -> str | None:
        """The guardian responsible for this learner, or ``None`` if there is no such learner."""
        ...


class TeacherRoster(Protocol):
    """The school facts a teacher's concern needs (the school context, through a port)."""

    def may_raise_about(
        self, *, teacher_ref: str, student_ref: str, submission_id: str | None
    ) -> bool:
        """True only for an active teacher and a learner enrolled in one of that teacher's own
        classes; a named submission must be that learner's, in one of those classes."""
        ...


class SubmissionReader(Protocol):
    """The homework submission behind a concern (the school context, through a port)."""

    def submission_for_safeguarding(
        self, *, submission_id: str, student_ref: str
    ) -> dict[str, Any] | None:
        """``{"submission_id", "source", "objective_code", "item_ref", "text", "attempt",
        "submitted_at", "lesson_title", "item_prompt"}`` for this learner's submission, or None
        (unknown, erased, or another learner's). Independent of consent and progress sharing."""
        ...
