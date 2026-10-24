"""Ports the school context depends on. Adapters implement them; nothing here imports another
context. Identity, learning, and curriculum are reached only through these protocols, wired in the
composition root (``main.py``)."""

from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol

from ..domain.model import (
    Assignment,
    Classroom,
    Enrolment,
    Organization,
    SchoolAuditEvent,
    Submission,
    SubmissionStatus,
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
    def set_cohort(self, teacher_ref: str, cohort: str) -> bool: ...


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


class SubmissionRepository(Protocol):
    """Homework submissions. Reads are tenant-scoped except ``for_student`` (the learner's own
    work, for the learner) and ``by_id`` (used only after a tenant check by the caller)."""

    def add(self, submission: Submission) -> None: ...
    def get(self, organization_id: str, submission_id: str) -> Submission | None: ...
    def by_id(self, submission_id: str) -> Submission | None: ...
    def find(self, assignment_id: str, item_ref: str, student_ref: str) -> Submission | None: ...
    def find_self_paced(
        self, objective_code: str, item_ref: str, student_ref: str
    ) -> Submission | None:
        """The learner's self-paced submission for one item of one lesson (contract §6)."""

    def for_student(self, student_ref: str) -> list[Submission]: ...
    def for_class(
        self, organization_id: str, class_id: str, status: SubmissionStatus
    ) -> list[Submission]:
        """One class's submissions in ``status``, oldest first."""

    def save(self, submission: Submission) -> None: ...


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
    @property
    def submissions(self) -> SubmissionRepository: ...

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


@dataclass(frozen=True)
class WrittenItem:
    """One written item of a published lesson (HOMEWORK_AND_MARKING_CONTRACT §1).

    ``prompt``, ``hints`` and ``max_chars`` may be shown to the learner. ``rubric``,
    ``sample_answer`` and ``guidance`` are marking aids: the rubric is for a teacher only; the
    sample answer or guidance is shown to the learner only AFTER they submitted an open
    (``self_check``) answer, labelled "compare your answer" (contract §6). ``auto_markable`` says
    the item has an exact answer key (the key itself never leaves the learning context).
    """

    item_ref: str
    prompt: dict[str, str]
    hints: tuple[str, ...]
    max_chars: int
    rubric: dict[str, object] | None = None  # {"criteria", "max_score", "levels": [...]}
    sample_answer: str | None = None
    guidance: str | None = None
    auto_markable: bool = False

    @property
    def marking(self) -> str:
        """``auto`` (exact key, marked on submit) or ``self_check`` (open answer, never scored)."""
        return "auto" if self.auto_markable else "self_check"

    @property
    def max_score(self) -> int | None:
        """The rubric's scale, when marking takes a score; None = no rubric (no score)."""
        if self.rubric is None:
            return None
        raw = self.rubric.get("max_score")
        value = raw if isinstance(raw, int) and not isinstance(raw, bool) else 0
        return value if value > 0 else None


@dataclass(frozen=True)
class WrittenLesson:
    objective_code: str
    title: dict[str, str]
    items: tuple[WrittenItem, ...]

    def item(self, item_ref: str) -> WrittenItem | None:
        return next((i for i in self.items if i.item_ref == item_ref), None)


class WrittenWork(Protocol):
    """The learning context's written items and mastery evidence, through a port."""

    def lesson(self, objective_code: str) -> WrittenLesson | None:
        """The published lesson of ``objective_code`` with its written items, or None."""

    def record_marked(
        self,
        *,
        submission_id: str,
        student_ref: str,
        objective_code: str,
        item_ref: str,
        met: bool,
    ) -> bool:
        """Record ONE human-graded evidence for this submission. Idempotent by
        ``submission_id``: returns False (and changes nothing) when it is already recorded."""

    def check_answer(self, objective_code: str, item_ref: str, text: str) -> bool | None:
        """Auto-mark: True / False when the item's exact key (``answer`` + ``accepted_variants``,
        compared with the fill ``normalize`` rule) decides it; None when the item has no exact
        key (an open answer — never scored) or is not a written item of the published lesson."""

    def studied_objectives(self, student_ref: str) -> list[str]:
        """Objectives the learner has studied — a live session or a synced offline attempt
        (placement and homework evidence do not count) — most recent first."""


class ConcernChannel(Protocol):
    """The safeguarding context's raise path for a teacher (a receipt only comes back)."""

    def raise_teacher_concern(
        self,
        *,
        teacher_ref: str,
        student_ref: str,
        submission_id: str,
        category: str,
        text: str | None,
    ) -> dict[str, Any]: ...


class DisclosureScreen(Protocol):
    """The safeguarding context's deterministic disclosure screen (contract §6).

    Screens a submitted answer; on a match raises ONE system concern referencing the submission
    (idempotent by ``submission_id``). Returns whether a concern exists for it now. Never blocks,
    never replies, never changes what the child sees."""

    def screen_submission(self, *, student_ref: str, submission_id: str, text: str) -> bool: ...


class SchoolAuditLog(Protocol):
    """Records changes to class membership and homework (see SchoolAuditEvent)."""

    def record(self, event: SchoolAuditEvent) -> None: ...
