"""Two-step erasure (pure stdlib): a signed, expiring confirmation — no server-side state.

Step 1 (request) returns a confirmation token: an HMAC-SHA256 over the request id, the learner,
the requesting guardian and an expiry. Step 2 (confirm) must present it. Because the token is
self-verifying, the two-step flow needs no table (and so no migration); a replayed token after a
completed erasure finds no learner and is a 404.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass


class ConfirmationError(ValueError):
    """The confirmation token is malformed, forged, expired, or for someone else."""


@dataclass(frozen=True)
class ErasureRequest:
    request_id: str
    student_ref: str
    guardian_ref: str
    requested_at: float
    expires_at: float


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def new_request(student_ref: str, guardian_ref: str, now: float, ttl_s: float) -> ErasureRequest:
    return ErasureRequest(uuid.uuid4().hex, student_ref, guardian_ref, now, now + ttl_s)


def sign(request: ErasureRequest, key: bytes) -> str:
    payload = json.dumps(
        {
            "rid": request.request_id,
            "sub": request.student_ref,
            "g": request.guardian_ref,
            "iat": request.requested_at,
            "exp": request.expires_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    mac = hmac.new(key, b"taleem.erasure.v1\x00" + payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(mac)}"


def verify(
    token: str, key: bytes, *, student_ref: str, guardian_ref: str, now: float
) -> ErasureRequest:
    try:
        payload_b64, mac_b64 = token.split(".", 1)
        payload = _unb64(payload_b64)
        mac = _unb64(mac_b64)
    except (ValueError, TypeError) as exc:
        raise ConfirmationError("malformed confirmation token") from exc
    expected = hmac.new(key, b"taleem.erasure.v1\x00" + payload, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ConfirmationError("confirmation token is not valid")
    data = json.loads(payload)
    if data.get("sub") != student_ref or data.get("g") != guardian_ref:
        raise ConfirmationError("confirmation token is for a different request")
    if float(data.get("exp", 0)) <= now:
        raise ConfirmationError("confirmation token has expired; request erasure again")
    return ErasureRequest(
        str(data["rid"]), student_ref, guardian_ref, float(data["iat"]), float(data["exp"])
    )
