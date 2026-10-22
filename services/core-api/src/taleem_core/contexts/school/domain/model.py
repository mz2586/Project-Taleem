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
_PACK = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
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
