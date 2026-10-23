"""Ports the school context depends on. Adapters implement them; nothing here imports another
context. Identity, learning, and curriculum are reached only through these protocols, wired in the
composition root (``main.py``)."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Protocol

from ..domain.model import (
    Assignment,
    Classroom,
    Enrolment,
    Organization,
    SchoolAuditEvent,
    Teacher,
)

# ------------------------------------------------------------------------------- persistence


class OrganizationRepository(Protocol):
    def add(self, org: Organization) -> None: ...
    def get(self, organization_id: str) -> Organization | None: ...


class TeacherRepository(Protocol):
    def add(self, teacher: Teacher) -> None: ...
    def get(self, teacher_ref: str) -> Teacher | None: ...
    def by_email(self, email: str) -> Teacher | None: ...
    def save(self, teacher: Teacher) -> None: ...


class ClassroomRepository(Protocol):
    """Every read is scoped by organization; ``by_join_code`` is the one cross-tenant lookup, used
    only by a guardian joining with a code they were given."""

    def add(self, classroom: Classroom) -> None: ...
    def get(self, organization_id: str, class_id: str) -> Classroom | None: ...
    def for_teacher(self, organization_id: str, teacher_ref: str) -> list[Classroom]: ...
    def by_join_code(self, join_code: str) -> Classroom | None: ...


class EnrolmentRepository(Protocol):
    def add(self, enrolment: Enrolment) -> None: ...
    def get(self, organization_id: str, class_id: str, student_ref: str) -> Enrolment | None: ...
    def for_class(self, organization_id: str, class_id: str) -> list[Enrolment]: ...
    def for_student(self, student_ref: str) -> list[Enrolment]:
        """Every class one learner is in, across organizations — for that learner's guardian."""

    def remove(self, organization_id: str, class_id: str, student_ref: str) -> bool: ...


class AssignmentRepository(Protocol):
    def add(self, assignment: Assignment) -> None: ...
    def get(self, organization_id: str, assignment_id: str) -> Assignment | None: ...
    def for_class(self, organization_id: str, class_id: str) -> list[Assignment]: ...


class SchoolUnitOfWork(Protocol):
    @property
    def organizations(self) -> OrganizationRepository: ...
    @property
    def teachers(self) -> TeacherRepository: ...
    @property
    def classrooms(self) -> ClassroomRepository: ...
    @property
    def enrolments(self) -> EnrolmentRepository: ...
    @property
    def assignments(self) -> AssignmentRepository: ...

    def commit(self) -> None: ...
    def __enter__(self) -> SchoolUnitOfWork: ...
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...


# ------------------------------------------------------------------------- other contexts


class SecretHasher(Protocol):
    def hash(self, secret: str) -> str: ...
    def verify(self, secret: str, encoded: str) -> bool: ...
    def equalising_hash(self) -> str: ...


class TeacherTokenIssuer(Protocol):
    """Mints a ``teacher`` access token (the identity context's token issuer)."""

    def __call__(self, *, teacher_ref: str, now: float) -> dict[str, object]: ...


class TeacherSessions(Protocol):
    """Opens a rotating refresh chain for a teacher (identity's generic session machinery; the
    chain is refreshed and ended at /v1/identity/sessions:refresh and :signout)."""

    def open(self, *, teacher_ref: str, device_id: str) -> str: ...


class LearnerDirectory(Protocol):
    """Identity, read for the school context. All checks are LIVE — never cached."""

    def guardian_of(self, student_ref: str) -> str | None:
        """The learner's guardian ref, or None if there is no such learner."""

    def display_name(self, student_ref: str) -> str | None: ...

    def shares_with_teacher(self, student_ref: str) -> bool:
        """True only while the learner may use learning data AND the guardian's consent covers
        ``progress_sharing``. A withdrawal makes this False on the very next call."""

    def may_learn(self, student_ref: str) -> bool:
        """True while the learner holds live learning consent and an active account."""

    def visible_to_teacher(self, student_refs: list[str]) -> dict[str, str]:
        """``shares_with_teacher`` for many learners in one live read: the learners a teacher may
        see right now, each with their display name (absent = hidden). Never cached."""


class GuardianSharingConsent(Protocol):
    """Records the guardian's consent to share a learner's progress with a class teacher (identity's
    consent service; raises a 404 Problem if the learner is not this guardian's)."""

    def grant(self, *, guardian_ref: str, student_ref: str, attestation: str) -> None: ...


@dataclass(frozen=True)
class ObjectiveProgress:
    mastery: float | None  # None: the learner has never practised this objective
    state: str  # learning-context mastery state, e.g. "not_started" / "mastered"
    attempts_since: int  # evidence on this objective at or after the given time


class LearnerProgressReader(Protocol):
    """The learning context's knowledge, read through a port (no learning domain imports)."""

    def objective_progress(
        self, student_ref: str, objective_code: str, *, since: float
    ) -> ObjectiveProgress: ...

    def objective_progress_many(
        self, student_refs: list[str], objective_code: str, *, since: float
    ) -> dict[str, ObjectiveProgress]:
        """``objective_progress`` for many learners (one batched read; every ref is a key)."""


class LearnerExplanationReader(Protocol):
    """The learning context's explained recommendations for one learner, through a port.

    Returns the learning context's JSON-shaped view (stable reason codes + parameters, confidence,
    uncertainty, evidence counts). The school context never interprets learning's domain; it only
    decides whether the teacher may see the learner, live, before asking.
    """

    def explain(self, student_ref: str) -> dict[str, object]: ...


@dataclass(frozen=True)
class PublishedLesson:
    """A titles-only catalog entry (no items, answers or other content)."""

    objective_code: str
    curriculum_pack: str
    title: dict[str, str]


class PublishedCurriculum(Protocol):
    def is_published(self, objective_code: str) -> bool: ...
    def catalog(self) -> list[PublishedLesson]: ...


class SchoolAuditLog(Protocol):
    """Records changes to class membership (see SchoolAuditEvent)."""

    def record(self, event: SchoolAuditEvent) -> None: ...
