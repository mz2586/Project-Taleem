"""JWT verification seam (pure-stdlib) — HS256 (dev) and EdDSA/Ed25519 (production).

Services are resource servers: verify a bearer token, then delegate the *authorization* decision to
the PDP (docs/03 §11–§12). Production signs tokens **asymmetrically** with rotating JWKS keys
(FD-14, docs/03 §11 §7, §13) — resource servers hold only public keys. The HS256 path is retained
for local/dev/tests only and is rejected in production (see ``platform.config`` + ``main``).
Never carries child PII in claims (docs/03 §11 §7).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from ..platform import ed25519
from ..platform.errors import unauthorized
from .keys import KeySet, SigningKey

ALG_HS256 = "HS256"
ALG_EDDSA = "EdDSA"


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


# --------------------------------------------------------------------------- header / payload utils


def _decode_json_segment(segment: str, what: str) -> dict[str, Any]:
    try:
        obj = json.loads(_b64url_decode(segment))
    except (ValueError, json.JSONDecodeError, binascii.Error):
        raise unauthorized(f"Malformed {what}") from None
    if not isinstance(obj, dict):
        raise unauthorized(f"Malformed {what}")
    return obj


def _split(token: str) -> tuple[str, str, str]:
    parts = token.split(".")
    if len(parts) != 3:
        raise unauthorized("Malformed token")
    return parts[0], parts[1], parts[2]


def _validate_and_build(
    payload: dict[str, Any],
    now: int | None,
    *,
    issuer: str | None = None,
    audience: str | None = None,
) -> Claims:
    """Validate the registered claims (exp/nbf/iss/aud + required sub+role) and build ``Claims``."""
    current = now if now is not None else int(time.time())
    exp = int(payload.get("exp", 0) or 0)
    if exp and current >= exp:
        raise unauthorized("Token expired")
    nbf = int(payload.get("nbf", 0) or 0)
    if nbf and current < nbf:
        raise unauthorized("Token not yet valid")
    if issuer is not None and payload.get("iss") != issuer:
        raise unauthorized("Bad issuer")
    if audience is not None:
        aud = payload.get("aud")
        aud_ok = aud == audience or (isinstance(aud, list) and audience in aud)
        if not aud_ok:
            raise unauthorized("Bad audience")
    if "sub" not in payload or "role" not in payload:
        raise unauthorized("Missing required claims")
    return Claims(
        sub=str(payload["sub"]),
        role=str(payload["role"]),
        aal=int(payload.get("aal", 1) or 1),
        exp=exp,
        device_id=payload.get("device_id"),
    )


# --------------------------------------------------------------------------- HS256 (dev/test only)


def sign_hs256(claims: dict[str, object], secret: str) -> str:
    """Helper for tests/local only — mint an HS256 token. Rejected in production."""
    header = {"alg": ALG_HS256, "typ": "JWT"}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url_encode(sig)}"


def verify_hs256(
    token: str,
    secret: str,
    *,
    now: int | None = None,
    issuer: str | None = None,
    audience: str | None = None,
) -> Claims:
    """Verify an HS256 signature + registered claims; return Claims or raise a Problem (401)."""
    h, p, s = _split(token)
    signing_input = f"{h}.{p}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        provided = _b64url_decode(s)
    except (ValueError, binascii.Error):
        raise unauthorized("Malformed signature") from None
    if not hmac.compare_digest(expected, provided):  # constant-time
        raise unauthorized("Bad signature")
    payload = _decode_json_segment(p, "claims")
    return _validate_and_build(payload, now, issuer=issuer, audience=audience)


# --------------------------------------------------------------------------- EdDSA (production)


def sign_eddsa(claims: dict[str, object], signing_key: SigningKey) -> str:
    """Mint an EdDSA (Ed25519) token. The Identity service is the only holder of the seed."""
    header = {"alg": ALG_EDDSA, "typ": "JWT", "kid": signing_key.kid}
    h = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    p = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
    signing_input = f"{h}.{p}".encode()
    sig = ed25519.sign(signing_input, signing_key.seed)
    return f"{h}.{p}.{_b64url_encode(sig)}"


def verify_eddsa(
    token: str,
    keyset: KeySet,
    *,
    now: int | None = None,
    issuer: str | None = None,
    audience: str | None = None,
) -> Claims:
    """Verify an EdDSA signature against the kid-addressed public key set + registered claims."""
    h, p, s = _split(token)
    header = _decode_json_segment(h, "header")
    if header.get("alg") != ALG_EDDSA:
        raise unauthorized("Unexpected token algorithm")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise unauthorized("Missing key id")
    key = keyset.by_kid(kid)
    if key is None:
        raise unauthorized("Unknown signing key")
    try:
        signature = _b64url_decode(s)
    except (ValueError, binascii.Error):
        raise unauthorized("Malformed signature") from None
    signing_input = f"{h}.{p}".encode()
    if not ed25519.verify(signature, signing_input, key.public_key):
        raise unauthorized("Bad signature")
    payload = _decode_json_segment(p, "claims")
    return _validate_and_build(payload, now, issuer=issuer, audience=audience)


# --------------------------------------------------------------------------- unified verifier


@dataclass(frozen=True)
class TokenVerifier:
    """Alg-dispatching bearer-token verifier built from configured key material.

    Production instances carry a ``keyset`` and set ``allow_hs256=False`` (asymmetric only).
    Dev/test instances carry an ``hs256_secret``. A token's ``alg`` header selects the path; a
    disallowed alg is rejected (defends against alg-confusion / "none").
    """

    keyset: KeySet | None = None
    hs256_secret: str | None = None
    issuer: str | None = None
    audience: str | None = None
    allow_hs256: bool = True

    def __post_init__(self) -> None:
        if self.keyset is None and self.hs256_secret is None:
            raise ValueError("TokenVerifier needs a keyset and/or an hs256_secret")

    def verify(self, token: str, *, now: int | None = None) -> Claims:
        header = _decode_json_segment(_split(token)[0], "header")
        alg = header.get("alg")
        if alg == ALG_EDDSA and self.keyset is not None:
            return verify_eddsa(
                token, self.keyset, now=now, issuer=self.issuer, audience=self.audience
            )
        if alg == ALG_HS256 and self.allow_hs256 and self.hs256_secret is not None:
            return verify_hs256(
                token, self.hs256_secret, now=now, issuer=self.issuer, audience=self.audience
            )
        raise unauthorized("Unsupported or disallowed token algorithm")
