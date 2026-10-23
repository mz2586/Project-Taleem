"""Operator-provisioned staff accounts (pure domain): Curriculum Studio roles and the safeguarding
lead.

A staff account is an adult an operator provisions for exactly one staff role. It is
deliberately its own aggregate — not a guardian, not a teacher, not a learner — so that the role
set it can ever carry is closed: ``STAFF_ROLES`` and nothing else. The Studio blocks self-approval
by token subject, so one person must be one subject: ``staff_ref`` is that subject, pseudonymous
and stable for the life of the account. A person who needs a second role gets a second account
(and therefore a second subject, which the Studio's segregation-of-duties checks then see).
"""

from __future__ import annotations

from dataclasses import dataclass

from ....platform.ids import uuid7
from .accounts import AccountStatus, InvalidAccountError, normalise_display_name, normalise_email

# Exactly ``auth/pdp.py``'s STAFF_ACCOUNT_ROLES: the Curriculum Studio roles plus the safeguarding
# lead (a test pins the two lists equal). No learner, guardian, teacher, mentor, or system role can
# be held by a staff account.
STAFF_ROLES: tuple[str, ...] = (
    "subject_author",
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
    "curriculum_architect",
    "safeguarding_lead",
)

STAFF_REF_PREFIX = "stf_"


def assert_staff_role(role: str) -> str:
    if role not in STAFF_ROLES:
        raise InvalidAccountError(
            "role must be one staff role: " + ", ".join(STAFF_ROLES),
            code="STAFF_ROLE_INVALID",
            field="role",
        )
    return role


@dataclass
class StaffAccount:
    staff_ref: str
    email: str
    passphrase_hash: str
    display_name: str
    role: str
    status: AccountStatus = AccountStatus.ACTIVE
    failed_attempts: int = 0
    created_at: float = 0.0
    created_by: str = ""
    version: int = 1

    @staticmethod
    def create(
        *,
        email: str,
        passphrase_hash: str,
        display_name: str,
        role: str,
        created_by: str,
        now: float,
        staff_ref: str | None = None,
    ) -> StaffAccount:
        return StaffAccount(
            staff_ref=staff_ref or f"{STAFF_REF_PREFIX}{uuid7()}",
            email=normalise_email(email),
            passphrase_hash=passphrase_hash,
            display_name=normalise_display_name(display_name),
            role=assert_staff_role(role),
            created_by=created_by,
            created_at=now,
        )

    @property
    def can_sign_in(self) -> bool:
        return self.status is AccountStatus.ACTIVE and self.role in STAFF_ROLES
