"""Guardian recovery codes — passphrase recovery without email (pure domain).

A guardian who forgets their passphrase would otherwise lose their children's accounts, consent
controls and safeguarding reporting, and email delivery is not available. A set of one-time
**recovery codes** closes that gap without adding a knowledge factor:

- They are a *look-up secret* (NIST SP 800-63B §5.1.2): something the guardian **has** — printed or
  written down at registration — not something they know or that can be socially discovered.
- Each code is 12 symbols from the 31-symbol family-code alphabet (no ``0/O``, ``1/I/L``), shown as
  ``XXXX-XXXX-XXXX`` so it can be read aloud and typed on a phone: about 59.4 bits of entropy.
- Only a KDF digest is stored. Because the secret has real entropy, the work factor is lower than a
  passphrase's (``RECOVERY_CODE_ITERATIONS``): one recovery attempt checks every slot of a set, and
  ``RECOVERY_CODE_COUNT × RECOVERY_CODE_ITERATIONS`` is chosen to cost about one passphrase check,
  so the public recovery route is no more of a PBKDF2 amplifier than sign-in. Offline, a stolen
  digest still costs ~2^59 guesses × 60 000 iterations.
- A code works once. Generating a new set deletes the old one, so a lost sheet is invalidated by
  making a new one.
- They are shown **once**: the plaintext exists only in the response that created it.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

from ....platform.ids import uuid7
from .accounts import _CODE_ALPHABET
from .credentials import MAX_PASSPHRASE_ATTEMPTS

RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_GROUPS = 3
RECOVERY_CODE_GROUP_SIZE = 4
RECOVERY_CODE_LENGTH = RECOVERY_CODE_GROUPS * RECOVERY_CODE_GROUP_SIZE
RECOVERY_CODE_ALPHABET = _CODE_ALPHABET
RECOVERY_CODE_PATTERN = re.compile(
    rf"^[{RECOVERY_CODE_ALPHABET}]{{4}}-[{RECOVERY_CODE_ALPHABET}]{{4}}-[{RECOVERY_CODE_ALPHABET}]{{4}}$"
)
# See the module docstring: a full set costs about one passphrase verification (8 × 60k ≈ 600k).
RECOVERY_CODE_ITERATIONS = 60_000
# Wrong recovery attempts before recovery locks (and an active account with it). The same bound as
# the passphrase lockout, kept on its own counter: a guardian locked out by wrong passphrases is
# exactly the person recovery exists for, so passphrase failures must not use up recovery.
MAX_RECOVERY_ATTEMPTS = MAX_PASSPHRASE_ATTEMPTS


class InvalidRecoveryCodeError(ValueError):
    """Raised when typed text cannot be a recovery code. Never carries the text itself."""


def _grouped(compact: str) -> str:
    size = RECOVERY_CODE_GROUP_SIZE
    return "-".join(compact[i : i + size] for i in range(0, RECOVERY_CODE_LENGTH, size))


def new_recovery_code() -> str:
    return _grouped(
        "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH))
    )


def new_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """A fresh set of distinct codes (a collision at 59 bits is a theoretical, not practical, event,
    but a set must never contain one code twice — it would silently be worth one use)."""
    codes: list[str] = []
    while len(codes) < count:
        code = new_recovery_code()
        if code not in codes:
            codes.append(code)
    return codes


def normalise_recovery_code(raw: str) -> str:
    """Accept what a guardian types (lower case, spaces, missing dashes) and canonicalise it."""
    compact = re.sub(r"[\s\-_.]", "", raw or "").upper()
    if len(compact) != RECOVERY_CODE_LENGTH or any(
        ch not in RECOVERY_CODE_ALPHABET for ch in compact
    ):
        raise InvalidRecoveryCodeError("not a recovery code")
    return _grouped(compact)


@dataclass
class RecoveryCode:
    """One stored code: its digest and whether it has been used. Never the code itself."""

    code_id: str
    guardian_ref: str
    code_hash: str
    created_at: float
    consumed_at: float | None = None

    @staticmethod
    def create(*, guardian_ref: str, code_hash: str, now: float) -> RecoveryCode:
        return RecoveryCode(
            code_id=f"rcv_{uuid7()}",
            guardian_ref=guardian_ref,
            code_hash=code_hash,
            created_at=now,
        )

    @property
    def usable(self) -> bool:
        return self.consumed_at is None

    def consume(self, now: float) -> None:
        self.consumed_at = now


def recovery_status(codes: list[RecoveryCode]) -> dict[str, Any]:
    """What a guardian (or an export) may see about their codes: counts and times, never digests."""
    used = [c.consumed_at for c in codes if c.consumed_at is not None]
    return {
        "total": len(codes),
        "remaining": sum(1 for c in codes if c.usable),
        "generated_at": min((c.created_at for c in codes), default=None),
        "last_used_at": max(used, default=None),
    }
