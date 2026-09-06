"""Refresh tokens — session continuity without weakening the consent gate (pure domain).

An access token deliberately lives ten minutes for a learner, because that window is the blast
radius of a consent withdrawal. Ten minutes is also shorter than a lesson, so without a refresh path
a child would be ejected mid-question — and the obvious shortcut, keeping the PIN on the device to
re-submit silently, would turn a four-digit secret into a permanently stored credential.

A refresh token solves it without that trade:

- It is **opaque and high-entropy** (256 random bits), so it needs no slow KDF — only a SHA-256
  digest, compared in constant time. It is never a JWT: nothing about it is self-describing, so it
  cannot be verified without the database, which is precisely the property that makes revocation
  work.
- Refreshing **re-runs every gate**: account status, and the derived consent state. A guardian who
  withdraws consent stops the child at the next refresh at the latest, so the ten-minute bound
  survives.
- It is **single-use with rotation**. Each refresh consumes the presented token and issues a
  successor in the same family. Presenting a consumed token means either a race or a stolen token,
  and since the two are indistinguishable the whole family is revoked (OAuth 2.0 BCP §4.14.2). On a
  shared family phone, that is the behaviour you want.
- It is **device-bound**. A token minted for one device is refused from another, so lifting the
  string alone is not enough.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from ....platform.ids import uuid7

# Long enough that a child using the app most days is never asked to sign in again; short enough
# that an abandoned device stops working within a term.
REFRESH_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60

_SECRET_BYTES = 32


class RefreshTokenError(ValueError):
    """Raised when a presented refresh token is malformed."""


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(_SECRET_BYTES)


def encode(token_id: str, secret: str) -> str:
    """The wire form: an addressable id plus the secret, so lookup is a primary-key read."""
    return f"{token_id}.{secret}"


def split(presented: str) -> tuple[str, str]:
    token_id, _, secret = presented.partition(".")
    if not token_id or not secret:
        raise RefreshTokenError("malformed refresh token")
    return token_id, secret


@dataclass
class RefreshToken:
    """One issued refresh token. Consumed once, then superseded by its successor."""

    token_id: str
    token_hash: str
    subject_ref: str
    role: str
    device_id: str
    # Every token descended from one sign-in shares a family id. Reuse revokes the family, not just
    # the token, because a thief and the legitimate holder both hold members of the same chain.
    family_id: str
    issued_at: float
    expires_at: float
    consumed_at: float | None = None
    revoked_at: float | None = None

    @staticmethod
    def issue(
        *,
        subject_ref: str,
        role: str,
        device_id: str,
        now: float,
        family_id: str | None = None,
        ttl_seconds: int = REFRESH_TOKEN_TTL_SECONDS,
    ) -> tuple[RefreshToken, str]:
        """Mint a token: the record to store, and the wire form handed to the client once."""
        token_id = f"rft_{uuid7()}"
        secret = new_secret()
        record = RefreshToken(
            token_id=token_id,
            token_hash=_digest(secret),
            subject_ref=subject_ref,
            role=role,
            device_id=device_id,
            family_id=family_id or f"rfm_{uuid7()}",
            issued_at=now,
            expires_at=now + ttl_seconds,
        )
        return record, encode(token_id, secret)

    def matches(self, secret: str) -> bool:
        return hmac.compare_digest(self.token_hash, _digest(secret))

    def is_usable(self, now: float, device_id: str) -> bool:
        """A token is usable only if it is live, unconsumed, unrevoked, and on its own device."""
        if self.revoked_at is not None or self.consumed_at is not None:
            return False
        if now >= self.expires_at:
            return False
        # An empty device_id on the record means the client did not identify a device at sign-in;
        # binding then degrades to "any device", which is the honest behaviour rather than a
        # silent lock-out. A bound token, though, is bound.
        return not self.device_id or self.device_id == device_id

    def consume(self, now: float) -> None:
        self.consumed_at = now

    def revoke(self, now: float) -> None:
        self.revoked_at = now
