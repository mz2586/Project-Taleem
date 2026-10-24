"""School aggregates: organization (tenant), teacher, classroom, enrolment, assignment.

Each record carries its ``organization_id`` — including the ones reachable through a parent — so a
repository can scope every query by tenant without a join it might forget. The rules a record must
satisfy on creation live in its factory, not in the HTTP layer.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from ....platform.ids import uuid7


class InvalidSchoolDataError(ValueError):
    """Proposed school data violates a domain rule."""


_COUNTRY = re.compile(r"^[A-Z]{2}$")  # ISO 3166-1 alpha-2
_LOCALE = re.compile(r"^[a-z]{2,3}(-[A-Z]{2})?$")
_PACK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")  # e.g. "PK-NCP"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OBJECTIVE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$")
MIN_PASSPHRASE_LENGTH = 10
MAX_FAILED_SIGN_INS = 10

# Join codes avoid look-alike characters (0/O, 1/I/L) — a guardian types this from a note.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _name(raw: str, *, field_name: str, limit: int = 80) -> str:
    value = " ".join(unicodedata.normalize("NFKC", raw).split())
    if not value or len(value) > limit:
        raise InvalidSchoolDataError(f"{field_name} must be 1-{limit} characters")
    return value


def normalise_email(raw: str) -> str:
    email = unicodedata.normalize("NFKC", raw).strip().lower()
    if not _EMAIL.match(email) or len(email) > 254:
        raise InvalidSchoolDataError("email address is not valid")
    return email


def assert_passphrase_policy(passphrase: str) -> None:
    """Length-led (NIST SP 800-63B), matching the guardian policy."""
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise InvalidSchoolDataError(
            f"passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters"
        )


def new_join_code() -> str:
    """``ABCD-EFGH``: 8 symbols from a 31-character alphabet (~40 bits)."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalise_join_code(raw: str) -> str:
    code = re.sub(r"[\s-]", "", raw).upper()
    if len(code) != 8 or any(c not in _CODE_ALPHABET for c in code):
        raise InvalidSchoolDataError("class code is not valid")
    return f"{code[:4]}-{code[4:]}"


class TeacherStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"  # too many failed sign-ins; an operator must reset
    SUSPENDED = "suspended"


@dataclass(frozen=True)
class Organization:
    organization_id: str
    name: str
    country: str
    curriculum_pack_id: str
    default_locale: str
    created_at: float

    @staticmethod
    def create(
        *, name: str, country: str, curriculum_pack_id: str, default_locale: str, now: float
    ) -> Organization:
        country = country.strip().upper()
        if not _COUNTRY.match(country):
            raise InvalidSchoolDataError("country must be an ISO 3166-1 alpha-2 code")
        if not _PACK.match(curriculum_pack_id):
            raise InvalidSchoolDataError("curriculum pack id is not valid")
        if not _LOCALE.match(default_locale):
            raise InvalidSchoolDataError("default locale is not valid")
        return Organization(
            organization_id=f"org_{uuid7()}",
            name=_name(name, field_name="organization name", limit=120),
            country=country,
            curriculum_pack_id=curriculum_pack_id,
            default_locale=default_locale,
            created_at=now,
        )


@dataclass
class Teacher:
    teacher_ref: str
    organization_id: str
    email: str
    display_name: str
    passphrase_hash: str
    status: TeacherStatus = TeacherStatus.ACTIVE
    failed_attempts: int = 0
    created_at: float = 0.0
    # "" (real) or "demo" (DEMO_COHORT_CONTRACT). Set only by the demo seeder through
    # ``SchoolService.assign_teacher_cohort``; no HTTP route sets it.
    cohort: str = ""

    @staticmethod
    def create(
        *, organization_id: str, email: str, display_name: str, passphrase_hash: str, now: float
    ) -> Teacher:
        return Teacher(
            teacher_ref=f"tch_{uuid7()}",
            organization_id=organization_id,
            email=normalise_email(email),
            display_name=_name(display_name, field_name="display name", limit=60),
            passphrase_hash=passphrase_hash,
            created_at=now,
        )

    @property
    def can_sign_in(self) -> bool:
        return self.status is TeacherStatus.ACTIVE

    def record_failure(self) -> None:
        self.failed_attempts += 1
        if self.failed_attempts >= MAX_FAILED_SIGN_INS:
            self.status = TeacherStatus.LOCKED


@dataclass(frozen=True)
class Classroom:
    class_id: str
    organization_id: str
    teacher_ref: str
    name: str
    join_code: str
    created_at: float

    @staticmethod
    def create(
        *, organization_id: str, teacher_ref: str, name: str, join_code: str, now: float
    ) -> Classroom:
        return Classroom(
            class_id=f"cls_{uuid7()}",
            organization_id=organization_id,
            teacher_ref=teacher_ref,
            name=_name(name, field_name="class name"),
            join_code=join_code,
            created_at=now,
        )


@dataclass(frozen=True)
class Enrolment:
    """A learner in a class, approved by their guardian (the approval is also consent evidence)."""

    class_id: str
    organization_id: str
    student_ref: str
    approved_by: str  # guardian_ref
    joined_at: float


@dataclass(frozen=True)
class SchoolAuditEvent:
    """Who changed a learner's class membership or homework, and when. Refs only — no names, and
    never a word of a learner's answer or a teacher's feedback."""

    action: str  # "enrolment.joined" | "enrolment.left" | "submission.submitted|marked|returned"
    actor_ref: str
    actor_role: str
    subject_ref: str  # the learner
    organization_id: str
    class_id: str
    at: float
    object_ref: str = ""  # the submission_id, for submission.* actions


@dataclass(frozen=True)
class Assignment:
    assignment_id: str
    class_id: str
    organization_id: str
    objective_code: str
    due_at: float
    assigned_by: str  # teacher_ref
    created_at: float

    @staticmethod
    def create(
        *,
        classroom: Classroom,
        objective_code: str,
        due_at: float,
        assigned_by: str,
        now: float,
    ) -> Assignment:
        if not _OBJECTIVE.match(objective_code):
            raise InvalidSchoolDataError("objective code is not valid")
        if due_at <= now:
            raise InvalidSchoolDataError("due date must be in the future")
        return Assignment(
            assignment_id=f"asg_{uuid7()}",
            class_id=classroom.class_id,
            organization_id=classroom.organization_id,
            objective_code=objective_code,
            due_at=due_at,
            assigned_by=assigned_by,
            created_at=now,
        )


# ------------------------------------------------------------------------ homework submissions
# HOMEWORK_AND_MARKING_CONTRACT.md §2-§3. A learner's written answer to one item of an assignment.
# One row per (assignment, item, learner): a resubmission replaces the text of the same row (its
# ``attempt`` counts submissions), so the queue always shows the latest answer. Marked is final.

SUBMISSION_PREFIX = "sub_"
MAX_FEEDBACK = 1000
_SUBMISSION_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # keeps \t \n \r


class SubmissionStatus(StrEnum):
    SUBMITTED = "submitted"  # waiting for the teacher
    RETURNED = "returned"  # the teacher asked the child to try again (with feedback)
    MARKED = "marked"  # final: outcome + feedback; recorded as mastery evidence


class MarkOutcome(StrEnum):
    MET = "met"
    NOT_YET = "not_yet"


class SubmissionConflictError(InvalidSchoolDataError):
    """The submission's state does not allow this change (HTTP 409)."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _clean(raw: str) -> str:
    return _SUBMISSION_CONTROL.sub("", unicodedata.normalize("NFC", raw)).strip()


def clean_answer_text(raw: str, *, max_chars: int) -> str:
    """A learner's answer: NFC, control characters removed, trimmed; 1..``max_chars`` chars."""
    text = _clean(raw)
    if not text:
        raise InvalidSchoolDataError("the answer must not be empty")
    if max_chars <= 0 or len(text) > max_chars:
        raise InvalidSchoolDataError(f"the answer must be at most {max_chars} characters")
    return text


def clean_feedback(raw: str | None, *, required: bool) -> str:
    text = _clean(raw or "")
    if required and not text:
        raise InvalidSchoolDataError("feedback is required")
    if len(text) > MAX_FEEDBACK:
        raise InvalidSchoolDataError(f"feedback must be at most {MAX_FEEDBACK} characters")
    return text


@dataclass
class Submission:
    submission_id: str
    organization_id: str
    class_id: str
    assignment_id: str
    objective_code: str
    item_ref: str
    student_ref: str
    text: str
    status: SubmissionStatus
    submitted_at: float
    created_at: float
    attempt: int = 1
    # The item's rubric scale when the answer was (last) submitted; None = no rubric (no score).
    max_score: int | None = None
    outcome: MarkOutcome | None = None
    score: int | None = None
    feedback: str = ""
    returned_at: float | None = None
    marked_at: float | None = None
    reviewed_by: str | None = None  # the teacher who last returned or marked it
    version: int = 1

    @staticmethod
    def start(
        *,
        assignment: Assignment,
        item_ref: str,
        student_ref: str,
        text: str,
        max_chars: int,
        max_score: int | None,
        now: float,
    ) -> Submission:
        return Submission(
            submission_id=f"{SUBMISSION_PREFIX}{uuid7()}",
            organization_id=assignment.organization_id,
            class_id=assignment.class_id,
            assignment_id=assignment.assignment_id,
            objective_code=assignment.objective_code,
            item_ref=item_ref,
            student_ref=student_ref,
            text=clean_answer_text(text, max_chars=max_chars),
            status=SubmissionStatus.SUBMITTED,
            submitted_at=now,
            created_at=now,
            max_score=max_score if max_score and max_score > 0 else None,
        )

    def resubmit(self, *, text: str, max_chars: int, max_score: int | None, now: float) -> None:
        """Replace the answer while it is ``submitted`` or ``returned``; a marked one is final."""
        if self.status is SubmissionStatus.MARKED:
            raise SubmissionConflictError(
                "this answer has been marked; it cannot be changed", code="SUBMISSION_MARKED"
            )
        self.text = clean_answer_text(text, max_chars=max_chars)
        self.status = SubmissionStatus.SUBMITTED
        self.submitted_at = now
        self.attempt += 1
        self.max_score = max_score if max_score and max_score > 0 else None

    def mark(
        self,
        *,
        outcome: str,
        score: int | None,
        feedback: str | None,
        teacher_ref: str,
        now: float,
    ) -> None:
        """Mark once (final). ``score`` is required exactly when the item has a rubric scale."""
        if self.status is SubmissionStatus.MARKED:
            raise SubmissionConflictError("this answer is already marked", code="SUBMISSION_MARKED")
        try:
            result = MarkOutcome(outcome)
        except ValueError:
            raise InvalidSchoolDataError("outcome must be one of: met, not_yet") from None
        if self.max_score is None:
            if score is not None:
                raise InvalidSchoolDataError("this item has no rubric, so it takes no score")
        elif score is None or isinstance(score, bool) or not 0 <= score <= self.max_score:
            raise InvalidSchoolDataError(f"score must be a whole number from 0 to {self.max_score}")
        self.feedback = clean_feedback(feedback, required=False)
        self.outcome = result
        self.score = score
        self.status = SubmissionStatus.MARKED
        self.marked_at = now
        self.reviewed_by = teacher_ref

    def return_for_rework(self, *, feedback: str, teacher_ref: str, now: float) -> None:
        """Ask the child to try again. Only a ``submitted`` answer can be returned."""
        if self.status is SubmissionStatus.MARKED:
            raise SubmissionConflictError("this answer is already marked", code="SUBMISSION_MARKED")
        if self.status is not SubmissionStatus.SUBMITTED:
            raise SubmissionConflictError(
                "this answer is already back with the learner", code="SUBMISSION_RETURNED"
            )
        self.feedback = clean_feedback(feedback, required=True)
        self.status = SubmissionStatus.RETURNED
        self.returned_at = now
        self.reviewed_by = teacher_ref
