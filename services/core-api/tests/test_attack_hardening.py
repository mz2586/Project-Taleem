"""Adversarial-validation regression tests — hardening against attacks that broke the app.

Locks in fixes for two defects found by exercising the running app:
  1. ``/v1/sync/batch`` was unauthenticated and accepted durable attempt evidence for an arbitrary
     student_ref — anyone could forge assessment records for any child.
  2. A hostile ``x-correlation-id`` header with CR/LF was echoed verbatim into the response header
     and structured logs (HTTP response splitting / log injection).
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.correlation import ensure_correlation_id
from taleem_core.platform.ids import uuid7

_SECRET = "dev-only-not-secret"  # noqa: S105 (local dev stub)


def _auth(role: str, sub: str) -> dict[str, str]:
    exp = int(time.time()) + 3600
    return {
        "Authorization": f"Bearer {sign_hs256({'sub': sub, 'role': role, 'exp': exp}, _SECRET)}"
    }


def _attempt(student: str) -> dict[str, object]:
    return {
        "clientEventId": uuid7(),
        "type": "attempt.submitted",
        "entityKey": f"student:{student}|item:p1",
        "clientSeq": 1,
        "payload": {
            "student_ref": student,
            "objective_code": "MATH-G4-FR-01",
            "item_ref": "p1-one-of-four",
            "option": 0,
            "evidence_id": uuid7(),
            "session_id": "s",
            "context": "practice",
        },
    }


def _client() -> TestClient:
    return TestClient(create_app(Settings(database_url="")))


# ---------------------------------------------------------------- sync authz / IDOR


def test_sync_requires_authentication() -> None:
    c = _client()
    r = c.post("/v1/sync/batch", json={"cursor": 0, "deltas": [_attempt("anyone")]})
    assert r.status_code == 401, r.text


def test_sync_rejects_cross_student_attempt() -> None:
    # Authenticated as "attacker" but submitting an attempt for "victim" -> IDOR guard denies (403).
    c = _client()
    r = c.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": [_attempt("victim")]},
        headers=_auth("student", "attacker"),
    )
    assert r.status_code == 403, r.text


def test_sync_allows_own_attempt() -> None:
    # Reaching the handler (200) — not 401/403 — is the security assertion. The grading outcome
    # depends on a published lesson (covered by test_sync_evidence); here we assert access.
    c = _client()
    r = c.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": [_attempt("me")]},
        headers=_auth("student", "me"),
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["status"] in {"applied", "ignored", "duplicate", "conflict"}


def test_sync_attempt_missing_student_ref_is_422() -> None:
    c = _client()
    bad = _attempt("me")
    bad["payload"] = {k: v for k, v in bad["payload"].items() if k != "student_ref"}  # type: ignore[union-attr]
    r = c.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": [bad]},
        headers=_auth("student", "me"),
    )
    assert r.status_code == 422, r.text


def test_system_operator_may_sync_any_student() -> None:
    c = _client()
    r = c.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": [_attempt("some-child")]},
        headers=_auth("system", "op"),
    )
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------- correlation-id injection


def test_correlation_id_rejects_crlf() -> None:
    # Unit: a hostile value is discarded and a fresh, safe id minted instead.
    safe = ensure_correlation_id("abc\r\nSet-Cookie: evil=1")
    assert "\r" not in safe and "\n" not in safe
    assert safe != "abc\r\nSet-Cookie: evil=1"


def test_correlation_id_keeps_a_sane_value() -> None:
    assert ensure_correlation_id("trace-123_ABC.def") == "trace-123_ABC.def"


def test_response_header_never_contains_injected_crlf() -> None:
    c = _client()
    r = c.get("/health", headers={"x-correlation-id": "abc\r\nSet-Cookie: evil=1"})
    echoed = r.headers.get("x-correlation-id", "")
    assert "\r" not in echoed and "\n" not in echoed
    assert "Set-Cookie" not in echoed
