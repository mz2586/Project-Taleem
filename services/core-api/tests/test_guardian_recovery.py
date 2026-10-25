"""Guardian passphrase recovery without email: one-time recovery codes (identity context).

Covers generation (entropy, format, uniqueness), hash-only storage, single use, regeneration
invalidating the old set, recovery revoking every session, the uniform 401, the per-client and
per-account rate limits, that wrong codes never lock the account (only audited), audit
entries that never carry a code, the privacy posture of the new table, and the 0021 migration.
"""

from __future__ import annotations

import importlib.util
import math
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select

from taleem_core.contexts.identity.adapters.persistence.models import (
    GuardianRow,
    RecoveryCodeRow,
    RefreshTokenRow,
)
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.contexts.identity.domain import recovery
from taleem_core.contexts.identity.domain.credentials import MAX_PASSPHRASE_ATTEMPTS
from taleem_core.contexts.privacy.adapters.coverage import EXEMPT_TABLES
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.errors import Problem

_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_NEW_PASSPHRASE = "a-brand-new-passphrase"  # noqa: S105 (test fixture)
_WRONG = "wrong-passphrase!"  # noqa: S105 (test fixture)
_FAST_KDF = 1_000
_BASE = Path(__file__).resolve().parents[1]
PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")


@pytest.fixture
def app() -> FastAPI:
    return create_app(
        Settings(database_url="", kdf_iterations=_FAST_KDF, client_ip_header="x-real-ip")
    )


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


_ip_counter = iter(range(1, 10_000))


def _ip() -> dict[str, str]:
    """A fresh client address per call, so the per-client limit does not mask other behaviour."""
    n = next(_ip_counter)
    return {"x-real-ip": f"10.0.{n // 250}.{n % 250}"}


def _register(client: TestClient, email: str = "parent@example.com") -> dict[str, Any]:
    response = client.post(
        "/v1/identity/guardians",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Fatima"},
        headers=_ip(),
    )
    assert response.status_code == 201, response.text
    body: dict[str, Any] = response.json()
    return body


def _bearer(body: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {body['session']['access_token']}"}


def _recover(
    client: TestClient,
    code: str,
    *,
    email: str = "parent@example.com",
    new: str = _NEW_PASSPHRASE,
    headers: dict[str, str] | None = None,
) -> Any:
    return client.post(
        "/v1/identity/guardians:recover",
        json={"email": email, "code": code, "newPassphrase": new},
        headers=headers if headers is not None else _ip(),
    )


def _sign_in(client: TestClient, passphrase: str, email: str = "parent@example.com") -> Any:
    return client.post(
        "/v1/identity/guardians:signin",
        json={"email": email, "passphrase": passphrase},
        headers=_ip(),
    )


def _rows(app: FastAPI, guardian_ref: str) -> list[RecoveryCodeRow]:
    with app.state.identity_session_factory() as s:
        return list(
            s.scalars(select(RecoveryCodeRow).where(RecoveryCodeRow.guardian_ref == guardian_ref))
        )


def _audit(client: TestClient, auth: dict[str, str]) -> list[dict[str, Any]]:
    response = client.get("/v1/identity/audit", headers=auth)
    assert response.status_code == 200, response.text
    events: list[dict[str, Any]] = response.json()["events"]
    return events


# ------------------------------------------------------------------------------------ domain


def test_codes_are_eight_distinct_grouped_high_entropy_codes() -> None:
    codes = recovery.new_recovery_codes()
    assert len(codes) == recovery.RECOVERY_CODE_COUNT == 8
    assert len(set(codes)) == 8
    for code in codes:
        assert recovery.RECOVERY_CODE_PATTERN.match(code), code
    bits = recovery.RECOVERY_CODE_LENGTH * math.log2(len(recovery.RECOVERY_CODE_ALPHABET))
    assert bits > 59  # ~59.4 bits per code
    # No characters that are misread aloud or on paper.
    assert not set("01OIL") & set(recovery.RECOVERY_CODE_ALPHABET)


def test_codes_are_random_not_patterned() -> None:
    seen = {code for _ in range(50) for code in recovery.new_recovery_codes()}
    assert len(seen) == 400  # 50 sets × 8, no repeats
    symbols = "".join(seen).replace("-", "")
    # Every symbol of the alphabet appears across 4 800 draws (each has p ≈ 1/31).
    assert set(symbols) == set(recovery.RECOVERY_CODE_ALPHABET)


def test_normalisation_accepts_what_a_guardian_types() -> None:
    code = recovery.new_recovery_code()
    assert recovery.normalise_recovery_code(code.lower()) == code
    assert recovery.normalise_recovery_code(code.replace("-", " ")) == code
    assert recovery.normalise_recovery_code(code.replace("-", "")) == code
    for bad in ("", "ABCD-EFGH", "ABCD-EFGH-JKL0", "ABCD-EFGH-JKMNP", "ABCD-EFGH-JK!M"):
        with pytest.raises(recovery.InvalidRecoveryCodeError) as info:
            recovery.normalise_recovery_code(bad)
        assert bad not in str(info.value) or not bad


def test_status_is_counts_and_times_only() -> None:
    a = recovery.RecoveryCode.create(guardian_ref="g", code_hash="h1", now=10.0)
    b = recovery.RecoveryCode.create(guardian_ref="g", code_hash="h2", now=10.0)
    b.consume(20.0)
    status = recovery.recovery_status([a, b])
    assert status == {"total": 2, "remaining": 1, "generated_at": 10.0, "last_used_at": 20.0}
    assert recovery.recovery_status([]) == {
        "total": 0,
        "remaining": 0,
        "generated_at": None,
        "last_used_at": None,
    }


# ----------------------------------------------------------------------- generation + storage


def test_registration_returns_codes_once_and_stores_only_kdf_digests(
    app: FastAPI, client: TestClient
) -> None:
    body = _register(client)
    codes = body["recovery_codes"]
    assert len(codes) == 8 and all(recovery.RECOVERY_CODE_PATTERN.match(c) for c in codes)
    assert body["recovery"]["remaining"] == 8 and body["recovery"]["total"] == 8
    rows = _rows(app, body["guardian"]["guardian_ref"])
    assert len(rows) == 8
    for row in rows:
        assert row.code_hash.startswith("pbkdf2-sha256$")
        assert row.consumed_at is None
        for code in codes:
            assert code not in row.code_hash
            assert code.replace("-", "") not in row.code_hash
    # Each digest is salted: no two rows share one.
    assert len({row.code_hash for row in rows}) == 8
    # Shown once: /me and sign-in carry the count, never a code.
    me = client.get("/v1/identity/me", headers=_bearer(body)).json()
    assert me["recovery"] == body["recovery"]
    assert not any(code in str(me) for code in codes)
    signed_in = _sign_in(client, _PASSPHRASE).json()
    assert "recovery_codes" not in signed_in
    assert not any(code in str(signed_in) for code in codes)


def test_code_work_factor_never_exceeds_the_injected_one(app: FastAPI, client: TestClient) -> None:
    body = _register(client)
    iterations = {
        int(r.code_hash.split("$")[1]) for r in _rows(app, body["guardian"]["guardian_ref"])
    }
    assert iterations == {min(_FAST_KDF, recovery.RECOVERY_CODE_ITERATIONS)}
    # In production the set costs about one passphrase verification.
    assert recovery.RECOVERY_CODE_COUNT * recovery.RECOVERY_CODE_ITERATIONS <= 600_000


def test_regeneration_requires_the_current_passphrase(client: TestClient) -> None:
    body = _register(client)
    wrong = client.post(
        "/v1/identity/guardians/me/recovery-codes",
        json={"passphrase": "not-the-passphrase"},
        headers={**_bearer(body), **_ip()},
    )
    assert wrong.status_code == 403
    assert wrong.json()["code"] == "PASSPHRASE_INCORRECT"
    events = _audit(client, _bearer(body))
    assert events[0]["action"] == "guardian.sign_in_failed"  # counts towards the lockout


def test_regeneration_invalidates_the_old_set(app: FastAPI, client: TestClient) -> None:
    body = _register(client)
    old = body["recovery_codes"]
    response = client.post(
        "/v1/identity/guardians/me/recovery-codes",
        json={"passphrase": _PASSPHRASE},
        headers={**_bearer(body), **_ip()},
    )
    assert response.status_code == 200, response.text
    new = response.json()["recovery_codes"]
    assert len(new) == 8 and not set(new) & set(old)
    assert response.json()["recovery"]["remaining"] == 8
    assert len(_rows(app, body["guardian"]["guardian_ref"])) == 8  # the old rows are gone
    assert _recover(client, old[0]).status_code == 401
    assert _recover(client, new[0]).status_code == 200


def test_regeneration_needs_a_guardian_token(client: TestClient) -> None:
    assert (
        client.post(
            "/v1/identity/guardians/me/recovery-codes", json={"passphrase": _PASSPHRASE}
        ).status_code
        == 401
    )


# ---------------------------------------------------------------------------------- recovery


def test_recovery_sets_the_passphrase_and_consumes_the_code(
    app: FastAPI, client: TestClient
) -> None:
    body = _register(client)
    code = body["recovery_codes"][3]
    response = _recover(client, code.lower().replace("-", " "))
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["guardian"]["guardian_ref"] == body["guardian"]["guardian_ref"]
    assert out["session"]["role"] == "guardian" and out["refresh_token"]
    assert out["recovery"]["remaining"] == 7 and out["recovery"]["last_used_at"] is not None
    assert _sign_in(client, _PASSPHRASE).status_code == 401
    assert _sign_in(client, _NEW_PASSPHRASE).status_code == 200
    # Single use.
    assert _recover(client, code, new="yet-another-passphrase").status_code == 401
    # The other codes still work.
    assert _recover(client, body["recovery_codes"][0], new="third-passphrase!").status_code == 200
    consumed = [r for r in _rows(app, body["guardian"]["guardian_ref"]) if r.consumed_at]
    assert len(consumed) == 2
    me = client.get("/v1/identity/me", headers=_bearer(out)).json()
    assert me["recovery"]["remaining"] == 6


def test_recovery_revokes_every_existing_guardian_session(app: FastAPI, client: TestClient) -> None:
    body = _register(client)
    other_device = _sign_in(client, _PASSPHRASE).json()
    response = _recover(client, body["recovery_codes"][0])
    assert response.status_code == 200
    for old in (body["refresh_token"], other_device["refresh_token"]):
        refreshed = client.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": old}, headers=_ip()
        )
        assert refreshed.status_code == 401
    ref = body["guardian"]["guardian_ref"]
    with app.state.identity_session_factory() as s:
        live = s.scalars(
            select(RefreshTokenRow).where(
                RefreshTokenRow.subject_ref == ref, RefreshTokenRow.revoked_at.is_(None)
            )
        ).all()
    assert len(live) == 1  # only the session the recovery itself issued
    new_refresh = client.post(
        "/v1/identity/sessions:refresh",
        json={"refreshToken": response.json()["refresh_token"]},
        headers=_ip(),
    )
    assert new_refresh.status_code == 200


def test_every_failure_is_the_same_401(client: TestClient) -> None:
    body = _register(client)
    _register(client, "other@example.com")
    used = body["recovery_codes"][0]
    assert _recover(client, used).status_code == 200
    cases = [
        _recover(client, used),  # already used
        _recover(client, recovery.new_recovery_code()),  # wrong code
        _recover(client, "not a code at all"),  # malformed
        _recover(client, body["recovery_codes"][1], email="nobody@example.com"),  # unknown
        _recover(client, body["recovery_codes"][1], email="other@example.com"),  # wrong family
        _recover(client, body["recovery_codes"][1], email="not-an-email"),  # bad email
    ]
    shapes = {(r.status_code, r.json()["code"], r.json()["detail"]) for r in cases}
    assert len(shapes) == 1
    status, code, detail = shapes.pop()
    assert status == 401 and code == "UNAUTHORIZED"
    sign_in = _sign_in(client, "wrong-passphrase-here").json()
    assert (sign_in["code"], sign_in["detail"]) == (code, detail)


def test_the_new_passphrase_policy_is_enforced_before_any_lookup(client: TestClient) -> None:
    body = _register(client)
    for email in ("parent@example.com", "nobody@example.com"):
        short = _recover(client, body["recovery_codes"][0], email=email, new="short")
        assert short.status_code == 422
        assert short.json()["errors"][0]["code"] == "PASSPHRASE_TOO_SHORT"
    # A refused policy does not consume the code.
    assert _recover(client, body["recovery_codes"][0]).status_code == 200


def test_a_suspended_guardian_cannot_recover(app: FastAPI, client: TestClient) -> None:
    body = _register(client)
    ref = body["guardian"]["guardian_ref"]
    with app.state.identity_session_factory() as s, s.begin():
        s.get(GuardianRow, ref).status = "suspended"  # type: ignore[union-attr]
    assert _recover(client, body["recovery_codes"][0]).status_code == 401
    with app.state.identity_session_factory() as s:
        assert s.get(GuardianRow, ref).status == "suspended"  # type: ignore[union-attr]


def test_recovery_lifts_a_passphrase_lockout(app: FastAPI) -> None:
    service = app.state.identity_service
    body = service.register_guardian(
        email="locked@example.com", passphrase=_PASSPHRASE, display_name="Ali"
    )
    for _ in range(MAX_PASSPHRASE_ATTEMPTS):
        with pytest.raises(Problem):
            service.sign_in_guardian(email="locked@example.com", passphrase=_WRONG)
    with pytest.raises(Problem):  # locked, even with the right passphrase
        service.sign_in_guardian(email="locked@example.com", passphrase=_PASSPHRASE)
    out = service.recover_guardian(
        email="locked@example.com", code=body["recovery_codes"][0], new_passphrase=_NEW_PASSPHRASE
    )
    assert out["guardian"]["status"] == "active"
    assert service.sign_in_guardian(email="locked@example.com", passphrase=_NEW_PASSPHRASE)


def test_wrong_codes_never_lock_the_guardian_out(app: FastAPI) -> None:
    """Anyone who knows a guardian's email can send wrong codes. That must never lock the
    account or disable recovery (a denial-of-service lever against a parent who needs to reach
    their child's account); guessing is bounded by rate limits and ~59-bit codes, and is audited."""
    service = app.state.identity_service
    body = service.register_guardian(
        email="guess@example.com", passphrase=_PASSPHRASE, display_name="Ali"
    )
    for _ in range(recovery.MAX_RECOVERY_ATTEMPTS + 2):
        with pytest.raises(Problem) as info:
            service.recover_guardian(
                email="guess@example.com",
                code=recovery.new_recovery_code(),
                new_passphrase=_NEW_PASSPHRASE,
            )
        assert info.value.status == 401
    # The guardian can still sign in with their passphrase...
    assert service.sign_in_guardian(email="guess@example.com", passphrase=_PASSPHRASE)
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        account = uow.guardians.by_email("guess@example.com")
        assert account is not None
        assert account.status.value == "active"
        events = uow.audit.for_subject(account.guardian_ref, limit=50)
    actions = [e.action.value for e in events]
    assert "guardian.recovery_locked" in actions  # flagged for review, nothing more
    # ...and a genuine code still recovers the account.
    assert service.recover_guardian(
        email="guess@example.com", code=body["recovery_codes"][0], new_passphrase=_NEW_PASSPHRASE
    )


def test_successful_recovery_resets_the_recovery_counter(app: FastAPI) -> None:
    service = app.state.identity_service
    body = service.register_guardian(
        email="reset@example.com", passphrase=_PASSPHRASE, display_name="Ali"
    )
    for _ in range(recovery.MAX_RECOVERY_ATTEMPTS - 1):
        with pytest.raises(Problem):
            service.recover_guardian(
                email="reset@example.com",
                code=recovery.new_recovery_code(),
                new_passphrase=_NEW_PASSPHRASE,
            )
    service.recover_guardian(
        email="reset@example.com", code=body["recovery_codes"][0], new_passphrase=_NEW_PASSPHRASE
    )
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        account = uow.guardians.by_email("reset@example.com")
    assert account is not None and account.recovery_failed_attempts == 0


# ------------------------------------------------------------------------------- rate limits


def test_recovery_is_rate_limited_per_client(client: TestClient) -> None:
    same = _ip()
    statuses = [
        _recover(
            client, recovery.new_recovery_code(), email=f"p{i}@example.com", headers=same
        ).status_code
        for i in range(7)
    ]
    assert statuses[:5] == [401] * 5
    assert statuses[5:] == [429, 429]


def test_recovery_is_rate_limited_per_account_across_clients(client: TestClient) -> None:
    body = _register(client)
    statuses = [_recover(client, recovery.new_recovery_code()).status_code for _ in range(6)]
    assert statuses == [401] * 5 + [429]
    # A different spelling of the same address is the same account budget.
    assert (
        _recover(client, body["recovery_codes"][0], email=" PARENT@example.com ").status_code == 429
    )
    # Another family is unaffected.
    other = _register(client, "other@example.com")
    assert (
        _recover(client, other["recovery_codes"][0], email="other@example.com").status_code == 200
    )


def test_the_limiters_are_shared_scopes() -> None:
    from taleem_core.contexts.identity.adapters import identity_api

    assert identity_api.RECOVER_LIMIT <= identity_api.SIGN_IN_LIMIT
    assert identity_api.RECOVER_ACCOUNT_WINDOW_SECONDS >= 600


def test_recovery_uses_the_shared_limiter_when_a_store_exists() -> None:
    """With a store, both recovery limits are ``SharedRateLimiter`` scopes (PostgreSQL in prod)."""
    from taleem_core.contexts.identity.adapters.identity_api import build_identity_router

    class _Store:
        def __init__(self) -> None:
            self.scopes: list[str] = []

        def hit(self, scope: str, key_digest: str, window_start: int, window_seconds: int) -> Any:
            self.scopes.append(scope)
            return (1, 0)

        def purge_expired(self, now: float) -> int:
            return 0

    class _Service:
        def recover_guardian(self, **_: Any) -> dict[str, Any]:
            return {"ok": True}

    store = _Store()
    router = build_identity_router(
        _Service(),  # type: ignore[arg-type]
        lambda: None,  # type: ignore[arg-type, return-value]
        clock=lambda: 1_000.0,
        rate_limit_store=store,
    )
    test_app = FastAPI()
    test_app.include_router(router)
    response = TestClient(test_app).post(
        "/v1/identity/guardians:recover",
        json={"email": "a@example.com", "code": "x", "newPassphrase": _NEW_PASSPHRASE},
    )
    assert response.status_code == 200
    assert store.scopes == ["identity.recover", "identity.recover_account"]


# ------------------------------------------------------------------------- audit, no secrets


def test_audit_records_recovery_without_any_code(
    client: TestClient, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    body = _register(client)
    codes = body["recovery_codes"]
    _recover(client, recovery.new_recovery_code())
    out = _recover(client, codes[0]).json()
    regenerated = client.post(
        "/v1/identity/guardians/me/recovery-codes",
        json={"passphrase": _NEW_PASSPHRASE},
        headers={**_bearer(out), **_ip()},
    ).json()["recovery_codes"]
    events = _audit(client, _bearer(out))
    actions = [e["action"] for e in events]
    assert actions.count("guardian.recovery_codes_generated") == 2
    assert "guardian.recovered" in actions and "guardian.recovery_failed" in actions
    recovered = next(e for e in events if e["action"] == "guardian.recovered")
    assert recovered["detail"]["revoked_sessions"] >= 1
    assert recovered["detail"]["codes_remaining"] == 7
    generated = [e for e in events if e["action"] == "guardian.recovery_codes_generated"]
    assert generated[0]["detail"] == {"count": 8, "invalidated": 8}
    captured = capsys.readouterr()
    blob = str(events) + captured.out + captured.err + caplog.text
    for code in (*codes, *regenerated):
        assert code not in blob
        assert code.replace("-", "") not in blob
    assert _NEW_PASSPHRASE not in blob
    assert "pbkdf2" not in str(events)


# ----------------------------------------------------------------------------------- privacy


def test_the_table_is_in_the_privacy_completeness_map() -> None:
    reason = EXEMPT_TABLES["identity.guardian_recovery_code"]
    assert "digest" in reason and "deleted" in reason


def test_learner_export_never_carries_recovery_material(client: TestClient) -> None:
    body = _register(client)
    auth = _bearer(body)
    learner = client.post(
        "/v1/identity/learners", json={"displayName": "Ayesha", "pin": "4813"}, headers=auth
    ).json()
    export = client.get(f"/v1/privacy/learners/{learner['student_ref']}/export", headers=auth)
    assert export.status_code == 200, export.text
    text = export.text
    assert "guardian_recovery_code" not in text and "pbkdf2" not in text
    assert not any(code in text for code in body["recovery_codes"])


def test_deleting_a_guardian_deletes_their_codes(app: FastAPI, client: TestClient) -> None:
    body = _register(client)
    ref = body["guardian"]["guardian_ref"]
    assert len(_rows(app, ref)) == 8
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        uow.refresh_tokens.revoke_all_for(ref, now=0.0)
        assert uow.guardians.delete(ref)
        uow.commit()
    assert _rows(app, ref) == []


# --------------------------------------------------------------------------------- migration


def _module() -> Any:
    path = _BASE / "alembic" / "versions" / "0021_guardian_recovery_codes.py"
    spec = importlib.util.spec_from_file_location("m0021", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0021_follows_0020() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (
        "0021_guardian_recovery_codes",
        "0020_homework_client_key",
    )
    assert any("DROP TABLE" in s for s in module.DOWNGRADE_STATEMENTS)
    assert any("recovery_failed_attempts" in s for s in module.DOWNGRADE_STATEMENTS)


def test_orm_matches_the_migration_columns() -> None:
    module = _module()
    ddl = " ".join(module.UPGRADE_STATEMENTS)
    for column in RecoveryCodeRow.__table__.columns:
        assert column.name in ddl
    assert "ON DELETE CASCADE" in ddl
    assert "recovery_failed_attempts" in GuardianRow.__table__.columns


def _cfg() -> Any:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _state() -> tuple[bool, bool]:
    engine = create_engine(PG_URL or "")
    try:
        inspector = inspect(engine)
        table = "guardian_recovery_code" in inspector.get_table_names(schema="identity")
        column = "recovery_failed_attempts" in {
            c["name"] for c in inspector.get_columns("guardian_account", schema="identity")
        }
        return table, column
    finally:
        engine.dispose()


@_pg_only
def test_up_down_up() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    assert _state() == (True, True)
    command.downgrade(_cfg(), "0020_homework_client_key")
    assert _state() == (False, False)
    command.upgrade(_cfg(), "head")
    assert _state() == (True, True)
