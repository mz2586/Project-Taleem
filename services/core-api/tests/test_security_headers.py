"""Security response headers — Software Completion Mode (hardening).

Every response from the JSON API — success, domain error, and the fail-closed kill-switch 503 — must
carry the hardening header set, so a header can never be dropped on an error path.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.security_headers import SECURITY_HEADERS, apply_security_headers

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)


def _sys() -> dict[str, str]:
    exp = int(time.time()) + 3600
    tok = sign_hs256({"sub": "op", "role": "system", "exp": exp}, _SECRET)
    return {"Authorization": f"Bearer {tok}"}


def test_apply_is_idempotent_and_non_overwriting() -> None:
    headers: dict[str, str] = {"Cache-Control": "max-age=60"}
    apply_security_headers(headers)
    # A route-specific value already present is preserved (setdefault, not overwrite).
    assert headers["Cache-Control"] == "max-age=60"
    # All other headers are added.
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Security-Policy"].startswith("default-src 'none'")


def test_headers_on_success_path() -> None:
    c = TestClient(create_app(Settings(database_url="")))
    r = c.get("/health")
    assert r.status_code == 200
    for name in SECURITY_HEADERS:
        assert name in r.headers, name
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"


def test_headers_on_error_path() -> None:
    c = TestClient(create_app(Settings(database_url="")))
    # Unauthenticated protected read -> 401, still hardened.
    r = c.get("/v1/learning/students/x/today")
    assert r.status_code == 401
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Strict-Transport-Security" in r.headers


def test_headers_on_kill_switch_503() -> None:
    c = TestClient(create_app(Settings(database_url="")))
    c.post("/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=_sys())
    r = c.post("/v1/sync/batch", json={"cursor": 0, "deltas": []})
    assert r.status_code == 503
    assert r.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert r.headers["Referrer-Policy"] == "no-referrer"
