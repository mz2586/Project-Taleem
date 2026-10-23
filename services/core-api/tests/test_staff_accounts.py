"""Curriculum Studio staff accounts — operator provisioning, passphrase sign-in, and the gate.

The properties a reviewer's account must have, each pinned here:

- only ``system`` provisions, with exactly one Studio role, and no other role is reachable;
- the token's role and subject come from the stored account (one person = one subject);
- sign-in fails uniformly, locks durably after ten wrong passphrases, and is rate limited;
- a suspension takes effect on the very next Studio request, and its sessions cannot refresh;
- refresh rotates without ever changing role or subject;
- every lifecycle step is audited.

PostgreSQL-gated variants (migration, CHECK constraints, two instances) are at the end.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from taleem_core.auth import pdp
from taleem_core.auth.jwt_verifier import sign_eddsa, sign_hs256
from taleem_core.auth.keys import SigningKey
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.contexts.identity.domain.sessions import RefreshToken
from taleem_core.contexts.identity.domain.staff import STAFF_ROLES
from taleem_core.main import create_app
from taleem_core.platform.config import Environment, Settings

_DEV_SECRET = "dev-only-not-secret"  # noqa: S105 (dev stub)
_PASSPHRASE = "a-reviewer-passphrase"  # noqa: S105 (test fixture)
_WRONG = "the-wrong-passphrase"  # noqa: S105 (test fixture)
_NEW = "a-brand-new-passphrase"  # noqa: S105 (test fixture)
_WRONG_X = "wrong-passphrase-x"  # noqa: S105 (test fixture)


def _token(role: str, sub: str) -> dict[str, str]:
    tok = sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 600}, _DEV_SECRET)
    return {"Authorization": f"Bearer {tok}"}


def _operator() -> dict[str, str]:
    # Minted per call: a module-level token would expire before this file runs in the full suite.
    return _token("system", "operator-1")


def _app(**overrides: Any) -> FastAPI:
    options: dict[str, Any] = {
        "database_url": "",
        "kdf_iterations": 1_000,
        "client_ip_header": "x-real-ip",
        **overrides,
    }
    return create_app(Settings(**options))


@pytest.fixture
def app() -> FastAPI:
    return _app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _ip() -> dict[str, str]:
    """A fresh client address per call, so lockout tests are not measuring the rate limiter."""
    return {"X-Real-IP": f"198.51.100.{uuid.uuid4().int % 250}-{uuid.uuid4().hex[:6]}"}


def _create(
    client: TestClient, role: str = "subject_expert", email: str = "rev@example.com"
) -> dict[str, Any]:
    response = client.post(
        "/v1/identity/staff",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Reviewer", "role": role},
        headers=_operator(),
    )
    assert response.status_code == 201, response.text
    return response.json()


def _signin(
    client: TestClient, email: str = "rev@example.com", passphrase: str = _PASSPHRASE
) -> Any:
    return client.post(
        "/v1/identity/staff:signin",
        json={"email": email, "passphrase": passphrase},
        headers=_ip(),
    )


def _bearer(session: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['session']['access_token']}"}


def _audit(app: FastAPI, staff_ref: str) -> list[str]:
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        return [e.action.value for e in uow.audit.for_subject(staff_ref)]


# ------------------------------------------------------------------------------- provisioning


def test_the_staff_role_set_is_exactly_the_studio_role_set() -> None:
    assert set(STAFF_ROLES) == set(pdp.CURRICULUM_ROLES)
    assert not {"student", "guardian", "teacher", "mentor", "system"} & set(STAFF_ROLES)


def test_an_operator_provisions_a_staff_account_with_one_role(
    app: FastAPI, client: TestClient
) -> None:
    staff = _create(client, role="safety_officer")
    assert staff["staff_ref"].startswith("stf_")
    assert (staff["role"], staff["status"]) == ("safety_officer", "active")
    assert "passphrase" not in str(staff) and "hash" not in str(staff)
    listed = client.get("/v1/identity/staff", headers=_operator()).json()["staff"]
    assert [s["staff_ref"] for s in listed] == [staff["staff_ref"]]
    assert "staff.created" in _audit(app, staff["staff_ref"])


@pytest.mark.parametrize("role", ["student", "guardian", "teacher", "mentor", "system", ""])
def test_no_non_studio_role_can_be_provisioned(client: TestClient, role: str) -> None:
    response = client.post(
        "/v1/identity/staff",
        json={
            "email": "x@example.com",
            "passphrase": _PASSPHRASE,
            "displayName": "X",
            "role": role,
        },
        headers=_operator(),
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["code"] == "STAFF_ROLE_INVALID"


def test_a_second_role_cannot_be_smuggled_in(client: TestClient) -> None:
    response = client.post(
        "/v1/identity/staff",
        json={
            "email": "x@example.com",
            "passphrase": _PASSPHRASE,
            "displayName": "X",
            "role": "subject_author",
            "roles": ["curriculum_architect"],
        },
        headers=_operator(),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("role", "sub"), [("guardian", "gdn_1"), ("subject_author", "stf_x"), ("teacher", "tch_1")]
)
def test_only_an_operator_provisions_or_suspends(client: TestClient, role: str, sub: str) -> None:
    headers = _token(role, sub)
    body = {"email": "x@example.com", "passphrase": _PASSPHRASE, "displayName": "X"}
    assert (
        client.post(
            "/v1/identity/staff", json={**body, "role": "subject_author"}, headers=headers
        ).status_code
        == 403
    )
    assert client.get("/v1/identity/staff", headers=headers).status_code == 403
    assert client.post("/v1/identity/staff/stf_x:suspend", headers=headers).status_code == 403
    assert client.post("/v1/identity/staff/stf_x:reinstate", headers=headers).status_code == 403


def test_duplicate_email_is_a_conflict(client: TestClient) -> None:
    _create(client)
    response = client.post(
        "/v1/identity/staff",
        json={
            "email": "REV@example.com",
            "passphrase": _PASSPHRASE,
            "displayName": "Again",
            "role": "language_editor",
        },
        headers=_operator(),
    )
    assert response.status_code == 409


def test_unknown_staff_ref_is_404_for_the_operator(client: TestClient) -> None:
    missing = client.post("/v1/identity/staff/stf_nobody:suspend", headers=_operator())
    assert missing.status_code == 404


# ------------------------------------------------------------------------------- sign-in


def test_sign_in_issues_the_accounts_one_role_and_its_stable_subject(
    app: FastAPI, client: TestClient
) -> None:
    staff = _create(client, role="curriculum_architect")
    first = _signin(client)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["session"]["role"] == "curriculum_architect"
    assert body["session"]["subject"] == staff["staff_ref"]
    assert body["refresh_token"]
    # One person, one subject: a second sign-in yields the same subject.
    assert _signin(client).json()["session"]["subject"] == staff["staff_ref"]

    h = _bearer(body)
    assert client.get("/v1/studio/lessons", headers=h).status_code == 200
    me = client.get("/v1/identity/staff/me", headers=h)
    assert me.status_code == 200 and me.json()["staff_ref"] == staff["staff_ref"]
    assert "staff.signed_in" in _audit(app, staff["staff_ref"])


def test_every_sign_in_failure_looks_identical(app: FastAPI, client: TestClient) -> None:
    staff = _create(client)
    other = _create(client, email="sus@example.com")
    client.post(f"/v1/identity/staff/{other['staff_ref']}:suspend", headers=_operator())
    failures = [
        _signin(client, email="nobody@example.com"),
        _signin(client, passphrase=_WRONG),
        _signin(client, email="sus@example.com"),
        _signin(client, email="not-an-email"),
    ]
    assert {f.status_code for f in failures} == {401}
    assert len({f.json()["detail"] for f in failures}) == 1
    assert "staff.sign_in_failed" in _audit(app, staff["staff_ref"])


def test_ten_wrong_passphrases_lock_the_account_until_an_operator_reinstates(
    app: FastAPI, client: TestClient
) -> None:
    staff = _create(client)
    for _ in range(10):
        assert _signin(client, passphrase=_WRONG).status_code == 401
    # The right passphrase no longer works, from any client.
    assert _signin(client).status_code == 401
    listed = client.get("/v1/identity/staff", headers=_operator()).json()["staff"]
    assert listed[0]["status"] == "locked"
    assert "staff.locked" in _audit(app, staff["staff_ref"])

    path = f"/v1/identity/staff/{staff['staff_ref']}:reinstate"
    reinstated = client.post(path, headers=_operator())
    assert reinstated.json()["status"] == "active"
    assert _signin(client).status_code == 200
    assert "staff.reinstated" in _audit(app, staff["staff_ref"])


def test_staff_sign_in_is_rate_limited_per_client() -> None:
    client = TestClient(_app(client_ip_header=""))
    statuses = [
        client.post(
            "/v1/identity/staff:signin",
            json={"email": "nobody@example.com", "passphrase": "whatever-it-is"},
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


# --------------------------------------------------------------------- suspension and refresh


def test_a_suspended_staff_member_is_refused_on_the_next_request(
    app: FastAPI, client: TestClient
) -> None:
    staff = _create(client)
    session = _signin(client).json()
    h = _bearer(session)
    assert client.get("/v1/studio/lessons", headers=h).status_code == 200

    suspended = client.post(f"/v1/identity/staff/{staff['staff_ref']}:suspend", headers=_operator())
    assert suspended.json()["status"] == "suspended"

    refused = client.get("/v1/studio/lessons", headers=h)  # same, still-unexpired token
    assert refused.status_code == 403
    assert refused.json()["code"] == "STAFF_INACTIVE"
    assert client.get("/v1/identity/staff/me", headers=h).status_code == 403
    assert (
        client.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": session["refresh_token"]}
        ).status_code
        == 401
    )
    assert _signin(client).status_code == 401
    events = _audit(app, staff["staff_ref"])
    assert "staff.suspended" in events


def test_refresh_rotates_and_never_changes_role_or_subject(client: TestClient) -> None:
    staff = _create(client, role="a11y_specialist")
    first = _signin(client).json()
    refreshed = client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": first["refresh_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["session"]["role"] == "a11y_specialist"
    assert body["session"]["subject"] == staff["staff_ref"]
    assert body["staff"]["staff_ref"] == staff["staff_ref"]
    assert body["refresh_token"] != first["refresh_token"]
    # Single use: the consumed token is reuse, and revokes the chain.
    assert (
        client.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": first["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": body["refresh_token"]}
        ).status_code
        == 401
    )


def test_sign_out_ends_a_staff_session(client: TestClient) -> None:
    _create(client)
    session = _signin(client).json()
    client.post("/v1/identity/sessions:signout", json={"refreshToken": session["refresh_token"]})
    assert (
        client.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": session["refresh_token"]}
        ).status_code
        == 401
    )


def test_changing_the_passphrase_ends_every_session(app: FastAPI, client: TestClient) -> None:
    staff = _create(client)
    session = _signin(client).json()
    h = _bearer(session)
    wrong = client.post(
        "/v1/identity/staff/me:passphrase",
        json={"current": "not-the-passphrase", "newPassphrase": "a-brand-new-passphrase"},
        headers=h,
    )
    assert wrong.status_code == 401
    changed = client.post(
        "/v1/identity/staff/me:passphrase",
        json={"current": _PASSPHRASE, "newPassphrase": "a-brand-new-passphrase"},
        headers=h,
    )
    assert changed.status_code == 200 and changed.json()["revoked_sessions"] >= 1
    assert (
        client.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": session["refresh_token"]}
        ).status_code
        == 401
    )
    assert _signin(client).status_code == 401
    assert _signin(client, passphrase=_NEW).status_code == 200
    assert "staff.passphrase_changed" in _audit(app, staff["staff_ref"])
    weak = client.post(
        "/v1/identity/staff/me:passphrase",
        json={"current": "a-brand-new-passphrase", "newPassphrase": "short"},
        headers=_bearer(_signin(client, passphrase=_NEW).json()),
    )
    assert weak.status_code == 422
    assert weak.json()["errors"][0]["code"] == "PASSPHRASE_TOO_SHORT"


# --------------------------------------------------------------------------- no escalation


def test_a_staff_token_reaches_no_learner_guardian_teacher_or_operator_surface(
    client: TestClient,
) -> None:
    _create(client, role="curriculum_architect")
    h = _bearer(_signin(client).json())
    for method, path in (
        ("get", "/v1/identity/me"),
        ("get", "/v1/identity/learners"),
        ("get", "/v1/guardian/me"),
        ("get", "/v1/school/me"),
        ("get", "/v1/learning/students/stu_x/today"),
        ("get", "/v1/identity/staff"),
        ("post", "/v1/ops/kill-switch:engage"),
    ):
        kwargs: dict[str, Any] = {"headers": h}
        if method == "post":
            kwargs["json"] = {"reason": "x"}
        assert getattr(client, method)(path, **kwargs).status_code == 403, path


def _plant_refresh(app: FastAPI, subject_ref: str, role: str) -> str:
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        record, wire = RefreshToken.issue(
            subject_ref=subject_ref, role=role, device_id="", now=time.time()
        )
        uow.refresh_tokens.add(record)
        uow.commit()
    return wire


@pytest.mark.parametrize("role", ["guardian", "student", "teacher", "curriculum_architect"])
def test_a_refresh_chain_can_never_mint_another_role_for_a_staff_subject(
    app: FastAPI, client: TestClient, role: str
) -> None:
    """Even a refresh row naming the staff subject with a different role yields nothing."""
    staff = _create(client, role="subject_author")
    wire = _plant_refresh(app, staff["staff_ref"], role)
    refreshed = client.post("/v1/identity/sessions:refresh", json={"refreshToken": wire})
    assert refreshed.status_code == 401


def test_a_staff_profile_route_refuses_other_roles(client: TestClient) -> None:
    assert client.get("/v1/identity/staff/me", headers=_token("guardian", "g")).status_code == 403
    assert client.get("/v1/identity/staff/me").status_code == 401


def test_dev_tokens_without_an_account_still_reach_the_studio_outside_production(
    client: TestClient,
) -> None:
    response = client.get("/v1/studio/lessons", headers=_token("subject_author", "a"))
    assert response.status_code == 200


def test_production_refuses_a_studio_token_with_no_staff_account() -> None:
    seed = bytes(range(32, 64))
    settings = Settings(
        environment=Environment.PRODUCTION,
        jwt_signing_seed_hex=seed.hex(),
        jwt_signing_kid="kid-prod",
        database_url="",
        offline_signing_seed_hex="11" * 32,
        kdf_iterations=1_000,
    )
    client = TestClient(create_app(settings))
    forged_by_key_holder = sign_eddsa(
        {
            "sub": "hand-minted",
            "role": "curriculum_architect",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "exp": int(time.time()) + 600,
        },
        SigningKey("kid-prod", seed),
    )
    response = client.get(
        "/v1/studio/lessons", headers={"Authorization": f"Bearer {forged_by_key_holder}"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "STAFF_INACTIVE"


# ------------------------------------------------------------------------------- PostgreSQL

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")


def _alembic() -> Any:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


def _dispose(app: FastAPI) -> None:
    for name in (
        "identity_session_factory",
        "learning_session_factory",
        "studio_session_factory",
        "ops_session_factory",
    ):
        factory = getattr(app.state, name, None)
        if factory is not None:
            factory.kw["bind"].dispose()


@_pg_only
def test_migration_0010_is_reversible_and_constrains_role() -> None:
    from alembic import command
    from sqlalchemy import create_engine, inspect

    cfg = _alembic()
    command.upgrade(cfg, "head")
    engine = create_engine(PG_URL or "")
    try:
        assert "staff_account" in inspect(engine).get_table_names(schema="identity")
        for role, ref in (("teacher", "stf_bad_role"), ("subject_author", "gdn_bad_prefix")):
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO identity.staff_account "
                        "(staff_ref, email, passphrase_hash, display_name, role) "
                        "VALUES (:ref, :email, 'x', 'X', :role)"
                    ),
                    {"ref": ref, "email": f"{uuid.uuid4().hex}@example.com", "role": role},
                )
        command.downgrade(cfg, "0009_evidence_erasure")
        assert "staff_account" not in inspect(engine).get_table_names(schema="identity")
        command.upgrade(cfg, "head")
        assert "staff_account" in inspect(engine).get_table_names(schema="identity")
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()


@_pg_only
def test_staff_lifecycle_over_postgres_across_two_instances() -> None:
    from alembic import command

    command.upgrade(_alembic(), "head")
    settings = Settings(
        database_url=PG_URL or "", kdf_iterations=1_000, client_ip_header="x-real-ip"
    )
    app_a, app_b = create_app(settings), create_app(settings)
    try:
        a, b = TestClient(app_a), TestClient(app_b)
        email = f"rev-{uuid.uuid4().hex[:8]}@example.com"
        staff = _create(a, role="language_editor", email=email)

        session = _signin(b, email=email).json()
        h = _bearer(session)
        assert session["session"]["subject"] == staff["staff_ref"]
        assert b.get("/v1/studio/lessons", headers=h).status_code == 200

        # Cross-role escalation is refused over the real schema too.
        wire = _plant_refresh(app_a, staff["staff_ref"], "guardian")
        # Refresh is rate limited per client like sign-in, and on PostgreSQL that budget is shared
        # by the whole test run, so each call carries its own synthetic address (as _signin does).
        escalated = b.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": wire}, headers=_ip()
        )
        assert escalated.status_code == 401

        # Instance A suspends; instance B refuses the live token on its next request.
        a.post(f"/v1/identity/staff/{staff['staff_ref']}:suspend", headers=_operator())
        refused = b.get("/v1/studio/lessons", headers=h)
        assert refused.status_code == 403 and refused.json()["code"] == "STAFF_INACTIVE"
        assert (
            b.post(
                "/v1/identity/sessions:refresh",
                json={"refreshToken": session["refresh_token"]},
                headers=_ip(),
            ).status_code
            == 401
        )

        # Lockout is durable across instances.
        a.post(f"/v1/identity/staff/{staff['staff_ref']}:reinstate", headers=_operator())
        for i in range(10):
            client = a if i % 2 else b
            assert _signin(client, email=email, passphrase=_WRONG_X).status_code == 401
        assert _signin(a, email=email).status_code == 401
        accounts = a.get("/v1/identity/staff", headers=_operator()).json()["staff"]
        listed = {s["staff_ref"]: s for s in accounts}
        assert listed[staff["staff_ref"]]["status"] == "locked"
        actions = _audit(app_a, staff["staff_ref"])
        assert {"staff.created", "staff.signed_in", "staff.suspended", "staff.locked"} <= set(
            actions
        )
    finally:
        _dispose(app_a)
        _dispose(app_b)
