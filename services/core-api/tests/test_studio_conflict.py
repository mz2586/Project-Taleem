"""Curriculum Studio optimistic-lock conflict → 409 (adversarial validation).

A concurrent double-submit of the same valid studio review made the losing writer's version-guarded
UPDATE match 0 rows → ``StaleDataError`` → an unhandled **500**. The conflict now maps to a
retryable 409 (the standard optimistic-concurrency response for staff tooling). It can surface in a
flush inside ``save()`` (not only at commit), so app-level handlers catch it wherever it fires.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.main import create_app
from taleem_core.platform.concurrency import ConcurrencyConflictError
from taleem_core.platform.config import Settings

_SECRET = "dev-only-not-secret"  # noqa: S105 (dev stub)


def _client() -> TestClient:
    # raise_server_exceptions=False so an unmapped exception would show as 500 (a test failure),
    # not bubble out — proving the handler maps conflicts to 409.
    return TestClient(create_app(Settings(database_url="")), raise_server_exceptions=False)


def test_studio_hierarchy_reachable() -> None:
    c = _client()
    tok = sign_hs256(
        {"sub": "a", "role": "curriculum_architect", "exp": int(time.time()) + 3600}, _SECRET
    )
    r = c.get("/v1/studio/hierarchy", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200


def _install_raising_route(exc: Exception) -> TestClient:
    app = create_app(Settings(database_url=""))

    @app.get("/v1/studio/_boom")  # a probe route that raises the given DB exception
    def boom() -> None:
        raise exc

    return TestClient(app, raise_server_exceptions=False)


def test_stale_data_error_maps_to_409() -> None:
    c = _install_raising_route(StaleDataError("UPDATE ... 0 rows", None, None, None))
    r = c.get("/v1/studio/_boom")
    assert r.status_code == 409
    assert r.json()["code"] == "CONFLICT"


def test_concurrency_conflict_error_maps_to_409() -> None:
    c = _install_raising_route(ConcurrencyConflictError("conflict"))
    r = c.get("/v1/studio/_boom")
    assert r.status_code == 409


def test_sqlite_locked_maps_to_409() -> None:
    c = _install_raising_route(OperationalError("database is locked", None, Exception("locked")))
    r = c.get("/v1/studio/_boom")
    assert r.status_code == 409


def test_other_operational_error_is_not_masked_as_409() -> None:
    c = _install_raising_route(OperationalError("syntax error", None, Exception("boom")))
    r = c.get("/v1/studio/_boom")
    assert r.status_code == 500  # a real DB error is NOT silently turned into a retryable 409
