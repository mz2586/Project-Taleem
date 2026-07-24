"""CORS allowlist — end-to-end validation regression.

The browser SPA is served from a different origin than the API, so without CORS every cross-origin
fetch is blocked and the frontend cannot load any data. The API now honours a configured allowlist
(exact origins only, never ``*`` — it is credentialed). These tests lock that in.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from taleem_core.main import create_app
from taleem_core.platform.config import Settings

_ORIGIN = "http://localhost:13000"


def _client(origins: str) -> TestClient:
    return TestClient(create_app(Settings(database_url="", cors_allowed_origins_csv=origins)))


def test_no_cors_headers_when_allowlist_empty() -> None:
    c = _client("")
    r = c.get("/health", headers={"Origin": _ORIGIN})
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


def test_allowed_origin_gets_cors_header_on_simple_request() -> None:
    c = _client(_ORIGIN)
    r = c.get("/health", headers={"Origin": _ORIGIN})
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == _ORIGIN


def test_preflight_options_is_allowed() -> None:
    c = _client(_ORIGIN)
    r = c.options(
        "/v1/learning/students/x/knowledge",
        headers={
            "Origin": _ORIGIN,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == _ORIGIN
    assert "GET" in r.headers.get("access-control-allow-methods", "")


def test_disallowed_origin_gets_no_cors_header() -> None:
    c = _client(_ORIGIN)
    r = c.get("/health", headers={"Origin": "http://evil.example"})
    # Starlette omits the ACAO header for a non-allowlisted origin, so the browser blocks it.
    assert r.headers.get("access-control-allow-origin") != "http://evil.example"


def test_never_wildcards_with_credentials() -> None:
    c = _client(_ORIGIN)
    r = c.get("/health", headers={"Origin": _ORIGIN})
    # A credentialed API must echo an exact origin, never "*".
    assert r.headers.get("access-control-allow-origin") != "*"
