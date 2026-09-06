"""Secret verification: guardian passphrases and child PINs (pure-stdlib).

Two different secrets with two different threat models, deliberately handled by one primitive:

- A **guardian passphrase** is a normal adult credential. It has real entropy, so the defence is a
  slow KDF: PBKDF2-HMAC-SHA256 at the OWASP-recommended work factor, per-secret random salt,
  constant-time comparison.
- A **child PIN** is four to six digits — at most a million possibilities, which no KDF can make
  unguessable. Its defence is therefore *rate*: the same KDF (so a stolen database still does not
  hand over PINs cheaply) plus a hard attempt-lockout enforced above, in the service. A PIN is
  usable only in combination with a family code the attacker must already hold.

Chosen over bcrypt/argon2 because the whole platform core is pure-stdlib by design
(docs/07-engineering/41-coding-standards.md) — adding a native crypto dependency to the domain would
break the "domain runs with no third-party installs" property that the test suite relies on.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import unicodedata
from dataclasses import dataclass

# OWASP Password Storage Cheat Sheet (2023) for PBKDF2-HMAC-SHA256. The platform-wide minimum
# lives in ``platform.config`` (which refuses to start production below it); this is the default the
# domain uses when nobody says otherwise.
PBKDF2_ITERATIONS = 600_000
SALT_BYTES = 16
DERIVED_BYTES = 32

MIN_PASSPHRASE_LENGTH = 10
MAX_PASSPHRASE_LENGTH = 256
PIN_PATTERN = re.compile(r"^\d{4,6}$")

# A child gets this many wrong PINs before the learner account locks and the guardian must reset it.
MAX_PIN_ATTEMPTS = 5
# A guardian gets more attempts (a passphrase is harder to type) but still locks.
MAX_PASSPHRASE_ATTEMPTS = 10


class WeakSecretError(ValueError):
    """Raised when a proposed secret does not meet the minimum policy."""


@dataclass(frozen=True)
class SecretHash:
    """A verifier for one secret. Carries its own parameters so the work factor can be raised."""

    algorithm: str
    iterations: int
    salt: bytes
    derived: bytes

    def encode(self) -> str:
        """Serialize to a single self-describing column value (PHC-like, no external parser)."""
        return f"{self.algorithm}${self.iterations}${self.salt.hex()}${self.derived.hex()}"

    @staticmethod
    def decode(encoded: str) -> SecretHash:
        try:
            algorithm, iterations, salt_hex, derived_hex = encoded.split("$")
            return SecretHash(
                algorithm=algorithm,
                iterations=int(iterations),
                salt=bytes.fromhex(salt_hex),
                derived=bytes.fromhex(derived_hex),
            )
        except (ValueError, AttributeError) as exc:
            raise ValueError("malformed secret hash") from exc


def _derive(secret: str, salt: bytes, iterations: int) -> bytes:
    # NFKC first: an Urdu or Arabic-script passphrase can be typed in more than one normalization
    # form, and the two forms must not be different credentials.
    normalized = unicodedata.normalize("NFKC", secret).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", normalized, salt, iterations, dklen=DERIVED_BYTES)


def hash_secret(secret: str, *, iterations: int = PBKDF2_ITERATIONS) -> SecretHash:
    salt = os.urandom(SALT_BYTES)
    return SecretHash("pbkdf2-sha256", iterations, salt, _derive(secret, salt, iterations))


def verify_secret(secret: str, encoded: str) -> bool:
    """Constant-time verification. A malformed stored hash verifies as False, never as an error."""
    try:
        stored = SecretHash.decode(encoded)
    except ValueError:
        return False
    if stored.algorithm != "pbkdf2-sha256":
        return False
    candidate = _derive(secret, stored.salt, stored.iterations)
    return hmac.compare_digest(candidate, stored.derived)


def assert_passphrase_policy(passphrase: str) -> None:
    """Guardian passphrase policy: length-led, per NIST SP 800-63B — no composition rules."""
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise WeakSecretError(f"passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters")
    if len(passphrase) > MAX_PASSPHRASE_LENGTH:
        raise WeakSecretError(f"passphrase must be at most {MAX_PASSPHRASE_LENGTH} characters")
    if passphrase.strip() != passphrase.strip(" "):
        # Leading/trailing whitespace other than spaces is almost always a paste accident.
        raise WeakSecretError("passphrase must not begin or end with whitespace")


# The most common four-digit PINs, which cover a disproportionate share of real choices. A guardian
# setting one of these for a child is refused; the list is short by design (it is a nudge, not a
# blocklist — the real defence is the attempt lockout).
_BANNED_PINS = frozenset(
    {
        "0000",
        "1111",
        "2222",
        "3333",
        "4444",
        "5555",
        "6666",
        "7777",
        "8888",
        "9999",
        "1234",
        "4321",
        "1212",
        "0123",
        "123456",
        "654321",
        "111111",
        "000000",
    }
)


def assert_pin_policy(pin: str) -> None:
    """Child PIN policy: 4–6 digits, not one of the most-guessed sequences."""
    if not PIN_PATTERN.match(pin):
        raise WeakSecretError("PIN must be 4 to 6 digits")
    if pin in _BANNED_PINS:
        raise WeakSecretError("PIN is too easily guessed; choose another")


@dataclass(frozen=True)
class SecretHasher:
    """The work factor as an injectable collaborator.

    Production uses the default. The test suite injects a low factor, because a suite that runs
    hundreds of sign-ins at 600 000 iterations spends minutes proving arithmetic rather than
    behaviour — and lowering it globally via configuration would risk a production deployment
    inheriting a weak factor from a stray environment variable. Keeping it a constructor argument
    means the weak factor can only ever exist where a test explicitly asks for one.
    """

    iterations: int = PBKDF2_ITERATIONS

    def hash(self, secret: str) -> str:
        return hash_secret(secret, iterations=self.iterations).encode()

    def verify(self, secret: str, encoded: str) -> bool:
        return verify_secret(secret, encoded)

    def equalising_hash(self) -> str:
        """A hash of a value nobody holds, for equalising the timing of unknown-account paths."""
        return self.hash("timing-equalisation-placeholder")
