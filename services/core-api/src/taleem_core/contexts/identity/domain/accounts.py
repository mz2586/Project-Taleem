"""Guardian and learner accounts (pure domain).

The asymmetry between the two account types is the whole point of this module:

- A **guardian** is an adult with a contact address, a passphrase, and legal standing to consent.
- A **learner** is a child with *no* contact address, *no* recoverable credential, and no way to
  exist at all without a guardian. The only personal datum stored for a learner is a display name
  the guardian chose, which the product treats as a nickname rather than a legal name.

The family code binds the two: it is the guardian-held secret that scopes a learner roster, so a
child never types an identifier and an attacker cannot enumerate children without holding it.
"""

from __future__ import annotations

import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from ....platform.ids import uuid7

# Crockford base32 minus the letters that look like digits, so a family code can be read aloud over
# a phone and typed by a parent without transcription errors.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
FAMILY_CODE_GROUPS = 2
FAMILY_CODE_GROUP_SIZE = 4
# 8 characters of a 31-symbol alphabet is about 39.6 bits — far beyond guessing at the roster
# endpoint's rate limit, yet short enough to write on a card handed to a parent.
FAMILY_CODE_PATTERN = re.compile(r"^[A-Z0-9]{4}-[A-Z0-9]{4}$")

MAX_DISPLAY_NAME = 60
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

GRADE_BANDS = ("early", "middle", "senior")


class AccountStatus(StrEnum):
    ACTIVE = "active"
    LOCKED = "locked"  # too many failed sign-in attempts; a guardian/operator must reset
    SUSPENDED = "suspended"  # an operator halted this account (safeguarding)


class InvalidAccountError(ValueError):
    """Raised when proposed account data violates the domain's rules."""


def new_family_code() -> str:
    """A fresh, human-readable family code such as ``K7QM-3XPZ``."""
    groups = [
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(FAMILY_CODE_GROUP_SIZE))
        for _ in range(FAMILY_CODE_GROUPS)
    ]
    return "-".join(groups)


def normalise_family_code(raw: str) -> str:
    """Accept what a parent types (lower case, spaces, a missing dash) and canonicalise it."""
    compact = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if len(compact) != FAMILY_CODE_GROUPS * FAMILY_CODE_GROUP_SIZE:
        raise InvalidAccountError("family code must be 8 letters and digits")
    return f"{compact[:FAMILY_CODE_GROUP_SIZE]}-{compact[FAMILY_CODE_GROUP_SIZE:]}"


def normalise_email(raw: str) -> str:
    email = unicodedata.normalize("NFKC", raw).strip().lower()
    if not _EMAIL_PATTERN.match(email) or len(email) > 254:
        raise InvalidAccountError("email address is not valid")
    return email


def normalise_display_name(raw: str) -> str:
    """A display name is a nickname, not a legal name: normalise and length-cap, nothing more."""
    name = unicodedata.normalize("NFKC", raw).strip()
    # Collapse internal whitespace so "Ali   Raza" and "Ali Raza" are the same learner to a child
    # trying to sign in.
    name = re.sub(r"\s+", " ", name)
    if not name:
        raise InvalidAccountError("display name must not be empty")
    if len(name) > MAX_DISPLAY_NAME:
        raise InvalidAccountError(f"display name must be at most {MAX_DISPLAY_NAME} characters")
    if any(unicodedata.category(ch) == "Cc" for ch in name):
        raise InvalidAccountError("display name must not contain control characters")
    return name


def roster_key(display_name: str) -> str:
    """Case- and space-insensitive key used to match a typed name against a family's roster."""
    return re.sub(r"\s+", "", normalise_display_name(display_name)).casefold()


@dataclass
class GuardianAccount:
    """An adult account. The only account type that carries a contact address."""

    guardian_ref: str
    email: str
    passphrase_hash: str
    display_name: str
    family_code: str
    locale: str = "ur"
    status: AccountStatus = AccountStatus.ACTIVE
    failed_attempts: int = 0
    created_at: float = 0.0
    version: int = 1

    @staticmethod
    def create(
        *,
        email: str,
        passphrase_hash: str,
        display_name: str,
        locale: str = "ur",
        now: float = 0.0,
        family_code: str | None = None,
        guardian_ref: str | None = None,
    ) -> GuardianAccount:
        return GuardianAccount(
            guardian_ref=guardian_ref or f"gdn_{uuid7()}",
            email=normalise_email(email),
            passphrase_hash=passphrase_hash,
            display_name=normalise_display_name(display_name),
            family_code=family_code or new_family_code(),
            locale=locale,
            created_at=now,
        )

    @property
    def can_sign_in(self) -> bool:
        return self.status is AccountStatus.ACTIVE


@dataclass
class LearnerAccount:
    """A child account. No email, no phone, no recoverable secret — only a guardian.

    ``pin_hash`` is resettable by the owning guardian and by an operator, and by nobody else. There
    is deliberately no self-service recovery path: a child cannot be sent a reset link because a
    child has no address to send one to.
    """

    student_ref: str
    guardian_ref: str
    display_name: str
    pin_hash: str
    grade_band: str = "middle"
    grade_level: int = 4
    locale: str = "ur"
    status: AccountStatus = AccountStatus.ACTIVE
    failed_attempts: int = 0
    created_at: float = 0.0
    version: int = 1
    # Devices this learner has signed in from, newest first. Used to show a guardian where their
    # child is learning and to bind offline packages; never a tracking identifier (opaque, client
    # generated, and rotatable by clearing site data).
    known_devices: list[str] = field(default_factory=list)

    @staticmethod
    def create(
        *,
        guardian_ref: str,
        display_name: str,
        pin_hash: str,
        grade_band: str = "middle",
        grade_level: int = 4,
        locale: str = "ur",
        now: float = 0.0,
        student_ref: str | None = None,
    ) -> LearnerAccount:
        if grade_band not in GRADE_BANDS:
            raise InvalidAccountError(f"grade band must be one of {', '.join(GRADE_BANDS)}")
        if not 0 <= grade_level <= 12:
            raise InvalidAccountError("grade level must be between 0 (KG) and 12")
        return LearnerAccount(
            # Opaque and unguessable: student_ref is the key every learning read model is scoped by,
            # so it must not be derivable from anything a guardian shares (docs/09 §3).
            student_ref=student_ref or f"stu_{uuid7()}",
            guardian_ref=guardian_ref,
            display_name=normalise_display_name(display_name),
            pin_hash=pin_hash,
            grade_band=grade_band,
            grade_level=grade_level,
            locale=locale,
            created_at=now,
        )

    @property
    def roster_key(self) -> str:
        return roster_key(self.display_name)

    @property
    def can_sign_in(self) -> bool:
        return self.status is AccountStatus.ACTIVE

    def remember_device(self, device_id: str, *, limit: int = 5) -> None:
        if not device_id:
            return
        devices = [d for d in self.known_devices if d != device_id]
        self.known_devices = [device_id, *devices][:limit]
