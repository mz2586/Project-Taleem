"""Minimal JWT structural verification (pure-stdlib, HS256).

WALKING-SKELETON ONLY. Demonstrates the verification seam so services can be resource servers
that validate a token before delegating the *authorization* decision to the PDP (docs/11 §12,
docs/12). Production replaces HS256+shared-secret with asymmetric JWKS + rotating keys + KMS
(FOUNDER_DECISIONS FD-14). Never carries child PII in claims (docs/11 §7).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass

from ..platform.errors import unauthorized


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class Claims:
    sub: str
    role: str
    aal: int = 1
    exp: int = 0
    device_id: str | None = None


def sign_hs256(claims: dict[str, object], secret: str) -> str:
    """Helper for tests/local only — mint a token. Not used in production."""
    header = {"alg": "HS256", "typ": "JWT"}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def verify_hs256(token: str, secret: str, *, now: int | None = None) -> Claims:
    """Verify signature + expiry; return Claims or raise a Problem (401)."""
    parts = token.split(".")
    if len(parts) != 3:
        raise unauthorized("Malformed token")
    h, p, s = parts
    signing_input = f"{h}.{p}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        provided = _b64url_decode(s)
    except (ValueError, binascii.Error):
        raise unauthorized("Malformed signature") from None
    if not hmac.compare_digest(expected, provided):  # constant-time
        raise unauthorized("Bad signature")
    try:
        payload = json.loads(_b64url_decode(p))
    except (ValueError, json.JSONDecodeError):
        raise unauthorized("Malformed claims") from None
    exp = int(payload.get("exp", 0))
    current = now if now is not None else int(time.time())
    if exp and current >= exp:
        raise unauthorized("Token expired")
    if "sub" not in payload or "role" not in payload:
        raise unauthorized("Missing required claims")
    return Claims(
        sub=str(payload["sub"]),
        role=str(payload["role"]),
        aal=int(payload.get("aal", 1)),
        exp=exp,
        device_id=payload.get("device_id"),
    )
