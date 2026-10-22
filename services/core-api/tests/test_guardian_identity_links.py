"""Guardian Portal over identity links (R1: correct progress visible to an authorized guardian).

A guardian who registered through ``/v1/identity`` sees, in ``/v1/guardian``, exactly the learners
they enrolled whose live consent covers ``learning_data`` — and nothing else: not an unconsented
sibling, not another family's child, not a child whose consent was just withdrawn. The static
``TALEEM_GUARDIAN_LINKS`` seed survives only as a dev/demo aid and is ignored in production.
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

from taleem_core.auth.jwt_verifier import sign_eddsa
from taleem_core.auth.keys import SigningKey
from taleem_core.contexts.guardian.adapters.identity_links import (
    IdentityGuardianLinks,
    build_guardian_links,
)
from taleem_core.contexts.guardian.application.links import LayeredLinks
from taleem_core.main import create_app
from taleem_core.platform.config import Environment, Settings
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE

from .test_guardian_api import _publish

_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"
_FAST_KDF = 1_000


def _app(**overrides: Any) -> FastAPI:
    app = create_app(Settings(database_url="", kdf_iterations=_FAST_KDF, **overrides))
    _publish(app)
    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app())


def _register(client: TestClient, email: str) -> dict[str, Any]:
    response = client.post(
        "/v1/identity/guardians",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Fatima"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "auth": {"Authorization": f"Bearer {body['session']['access_token']}"},
        "guardian": body["guardian"],
    }


def _enrol(client: TestClient, fam: dict[str, Any], name: str, consent: bool = True) -> str:
    response = client.post(
        "/v1/identity/learners",
        json={"displayName": name, "pin": _PIN, "gradeLevel": 4},
        headers=fam["auth"],
    )
    assert response.status_code == 201, response.text
    ref = str(response.json()["student_ref"])
    if consent:
        granted = client.post(
            "/v1/identity/consents",
            json={"studentRef": ref, "scopes": ["learning_data", "ai_teaching"]},
            headers=fam["auth"],
        )
        assert granted.status_code == 200, granted.text
    return ref


def _learn(client: TestClient, fam: dict[str, Any], name: str) -> None:
    """Real learning activity, driven with the learner's own identity-issued token."""
    signin = client.post(
        "/v1/identity/learners:signin",
        json={"familyCode": fam["guardian"]["family_code"], "displayName": name, "pin": _PIN},
    )
    assert signin.status_code == 200, signin.text
    session = signin.json()["session"]
    h = {"Authorization": f"Bearer {session['access_token']}"}
    started = client.post(
        "/v1/learning/sessions", json={"student_ref": session["subject"]}, headers=h
    )
    assert started.status_code in (200, 201), started.text
    sid = started.json()["session_id"]
    client.post(f"/v1/learning/sessions/{sid}:next", headers=h)
    client.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h
    )
    for _ in range(3):
        client.post(
            f"/v1/learning/sessions/{sid}:answer",
            json={"objective_code": OBJECTIVE_CODE, "item_ref": "p1-one-of-four", "option": 0},
            headers=h,
        )
    client.post(f"/v1/learning/sessions/{sid}:end", headers=h)


def _portal_children(client: TestClient, fam: dict[str, Any]) -> tuple[list[str], list[str]]:
    me = client.get("/v1/guardian/me", headers=fam["auth"])
    dashboard = client.get("/v1/guardian/dashboard", headers=fam["auth"])
    assert me.status_code == 200 and dashboard.status_code == 200
    return me.json()["children"], [row["student_ref"] for row in dashboard.json()["children"]]


# --------------------------------------------------------------------------- the journey


def test_a_guardian_sees_exactly_their_consented_learners_with_real_progress(
    client: TestClient,
) -> None:
    fam = _register(client, "a@example.com")
    ayesha = _enrol(client, fam, "Ayesha")
    bilal = _enrol(client, fam, "Bilal", consent=False)  # enrolled, never consented
    _learn(client, fam, "Ayesha")

    me = client.get("/v1/guardian/me", headers=fam["auth"]).json()
    assert me["children"] == [ayesha]
    assert me["child_count"] == 1
    assert me["display_name"] == "Fatima"

    dashboard = client.get("/v1/guardian/dashboard", headers=fam["auth"]).json()
    assert [row["student_ref"] for row in dashboard["children"]] == [ayesha]
    assert dashboard["children"][0]["progress"]["total_attempts"] >= 1

    child = client.get(f"/v1/guardian/children/{ayesha}", headers=fam["auth"])
    assert child.status_code == 200, child.text
    assert child.json()["student_ref"] == ayesha
    assert child.json()["progress_overview"]["total_attempts"] >= 1

    assert client.get(f"/v1/guardian/children/{bilal}", headers=fam["auth"]).status_code == 403


def test_consenting_later_adds_the_child_on_the_next_request(client: TestClient) -> None:
    fam = _register(client, "a@example.com")
    ref = _enrol(client, fam, "Ayesha", consent=False)
    assert _portal_children(client, fam) == ([], [])
    client.post(
        "/v1/identity/consents",
        json={"studentRef": ref, "scopes": ["learning_data"]},
        headers=fam["auth"],
    )
    assert _portal_children(client, fam) == ([ref], [ref])


def test_withdrawn_consent_removes_the_child_from_the_portal_immediately(
    client: TestClient,
) -> None:
    fam = _register(client, "a@example.com")
    ref = _enrol(client, fam, "Ayesha")
    assert client.get(f"/v1/guardian/children/{ref}", headers=fam["auth"]).status_code == 200

    withdrawn = client.post(
        "/v1/identity/consents:withdraw", json={"studentRef": ref}, headers=fam["auth"]
    )
    assert withdrawn.status_code == 200

    assert client.get(f"/v1/guardian/children/{ref}", headers=fam["auth"]).status_code == 403
    assert _portal_children(client, fam) == ([], [])


def test_withdrawing_only_learning_data_also_removes_the_child(client: TestClient) -> None:
    fam = _register(client, "a@example.com")
    ref = _enrol(client, fam, "Ayesha")
    client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": ref, "scopes": ["learning_data"]},
        headers=fam["auth"],
    )
    assert client.get(f"/v1/guardian/children/{ref}", headers=fam["auth"]).status_code == 403


def test_withdrawing_an_optional_scope_keeps_the_child_visible(client: TestClient) -> None:
    fam = _register(client, "a@example.com")
    ref = _enrol(client, fam, "Ayesha")
    client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": ref, "scopes": ["ai_teaching"]},
        headers=fam["auth"],
    )
    assert client.get(f"/v1/guardian/children/{ref}", headers=fam["auth"]).status_code == 200


def test_a_locked_learner_stays_visible_to_their_guardian(client: TestClient) -> None:
    fam = _register(client, "a@example.com")
    ref = _enrol(client, fam, "Ayesha")
    for _ in range(5):
        client.post(
            "/v1/identity/learners:signin",
            json={
                "familyCode": fam["guardian"]["family_code"],
                "displayName": "Ayesha",
                "pin": "9999",
            },
        )
    learners = client.get("/v1/identity/learners", headers=fam["auth"]).json()["learners"]
    assert learners[0]["status"] == "locked"
    assert client.get(f"/v1/guardian/children/{ref}", headers=fam["auth"]).status_code == 200


def test_guardian_b_never_sees_guardian_as_child(client: TestClient) -> None:
    fam_a = _register(client, "a@example.com")
    fam_b = _register(client, "b@example.com")
    ayesha = _enrol(client, fam_a, "Ayesha")
    bilal = _enrol(client, fam_b, "Bilal")

    assert _portal_children(client, fam_b) == ([bilal], [bilal])
    assert client.get(f"/v1/guardian/children/{ayesha}", headers=fam_b["auth"]).status_code == 403
    assert _portal_children(client, fam_a) == ([ayesha], [ayesha])


# ----------------------------------------------------------------------- the dev/demo seed


def test_the_seed_still_serves_demo_families_outside_production() -> None:
    client = TestClient(_app(guardian_links_csv="demo-guardian=Amina:demo-child"))
    from taleem_core.auth.jwt_verifier import sign_hs256

    token = sign_hs256(
        {"sub": "demo-guardian", "role": "guardian", "exp": int(time.time()) + 600},
        "dev-only-not-secret",
    )
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/guardian/me", headers=h).json()["children"] == ["demo-child"]
    assert client.get("/v1/guardian/children/demo-child", headers=h).status_code in (200, 404)


def test_the_seed_can_never_add_a_child_to_a_real_account() -> None:
    client = TestClient(_app())
    fam = _register(client, "a@example.com")
    ref = _enrol(client, fam, "Ayesha")
    real = fam["guardian"]["guardian_ref"]
    # A second app sharing nothing but the seed string cannot help; so build the layered links
    # directly over this app's identity service with a seed naming the real guardian.
    links = build_guardian_links(
        client.app.state.identity_service,  # type: ignore[attr-defined]
        seed_csv=f"{real}=Intruder:someone-elses-child",
        production=False,
    )
    assert isinstance(links, LayeredLinks)
    assert links.children(real) == (ref,)
    assert not links.is_linked(real, "someone-elses-child")


def test_production_ignores_the_seed_entirely() -> None:
    seed = bytes(range(32))
    settings = Settings(
        environment=Environment.PRODUCTION,
        jwt_signing_seed_hex=seed.hex(),
        jwt_signing_kid="kid-a",
        database_url="",
        offline_signing_seed_hex="11" * 32,
        guardian_links_csv="grd-1=Amina:gchild-1",
    )
    client = TestClient(create_app(settings))
    token = sign_eddsa(
        {
            "sub": "grd-1",
            "role": "guardian",
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "exp": int(time.time()) + 600,
        },
        SigningKey("kid-a", seed),
    )
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/guardian/me", headers=h).json()["children"] == []
    assert client.get("/v1/guardian/dashboard", headers=h).json()["children"] == []
    assert client.get("/v1/guardian/children/gchild-1", headers=h).status_code == 403


def test_build_guardian_links_selects_by_environment() -> None:
    class NoIdentity:
        def portal_links(self, guardian_ref: str) -> tuple[str, list[str]] | None:
            return None

    seed = "g=Name:c"
    assert isinstance(
        build_guardian_links(NoIdentity(), seed_csv=seed, production=True), IdentityGuardianLinks
    )
    assert isinstance(
        build_guardian_links(NoIdentity(), seed_csv="", production=False), IdentityGuardianLinks
    )
    dev = build_guardian_links(NoIdentity(), seed_csv=seed, production=False)
    assert isinstance(dev, LayeredLinks)
    assert dev.is_linked("g", "c")
    assert dev.profile("nobody") is None
    assert dev.children("nobody") == ()


def test_a_suspended_guardian_has_no_portal_links() -> None:
    class Suspended:
        def portal_links(self, guardian_ref: str) -> tuple[str, list[str]] | None:
            return None  # what IdentityService returns for a suspended or unknown account

    links = IdentityGuardianLinks(Suspended())
    assert links.profile("g") is None
    assert links.children("g") == ()
    assert not links.is_linked("g", "c")


def test_identity_service_hides_suspended_accounts_and_learners() -> None:
    from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
    from taleem_core.contexts.identity.domain.accounts import AccountStatus

    app = _app()
    client = TestClient(app)
    fam = _register(client, "a@example.com")
    ayesha = _enrol(client, fam, "Ayesha")
    bilal = _enrol(client, fam, "Bilal")
    service = app.state.identity_service
    guardian_ref = fam["guardian"]["guardian_ref"]

    def mutate(apply: Any) -> None:
        with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
            apply(uow)
            uow.commit()

    def suspend_learner(uow: Any) -> None:
        learner = uow.learners.get(bilal)
        learner.status = AccountStatus.SUSPENDED
        uow.learners.save(learner)

    mutate(suspend_learner)
    assert service.portal_links(guardian_ref) == ("Fatima", [ayesha])

    def suspend_guardian(uow: Any) -> None:
        account = uow.guardians.get(guardian_ref)
        account.status = AccountStatus.SUSPENDED
        uow.guardians.save(account)

    mutate(suspend_guardian)
    assert service.portal_links(guardian_ref) is None
    assert service.portal_links("gdn_unknown") is None


# ------------------------------------------------------------------------------ PostgreSQL

PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_portal_links_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.upgrade(cfg, "head")

    app = create_app(Settings(database_url=PG_URL or "", kdf_iterations=_FAST_KDF))
    # The shared limiter persists across tests on this database; start this test's budget clean.
    with app.state.identity_session_factory() as session:
        session.execute(
            text("DELETE FROM identity.rate_limit_bucket WHERE scope = 'identity.sign_in'")
        )
        session.commit()
    try:
        client = TestClient(app)
        tag = uuid.uuid4().hex[:8]
        fam_a = _register(client, f"a-{tag}@example.com")
        fam_b = _register(client, f"b-{tag}@example.com")
        ayesha = _enrol(client, fam_a, "Ayesha")
        hidden = _enrol(client, fam_a, "Bilal", consent=False)
        bilal = _enrol(client, fam_b, "Bilal")

        assert _portal_children(client, fam_a) == ([ayesha], [ayesha])
        assert _portal_children(client, fam_b) == ([bilal], [bilal])

        def child_status(ref: str) -> int:
            return client.get(f"/v1/guardian/children/{ref}", headers=fam_a["auth"]).status_code

        assert child_status(ayesha) == 200
        for ref in (hidden, bilal):
            assert child_status(ref) == 403

        client.post(
            "/v1/identity/consents:withdraw", json={"studentRef": ayesha}, headers=fam_a["auth"]
        )
        assert _portal_children(client, fam_a) == ([], [])
        assert child_status(ayesha) == 403
    finally:
        # Release this app's pooled connections: the PostgreSQL server is shared.
        for name in (
            "identity_session_factory",
            "learning_session_factory",
            "studio_session_factory",
            "ops_session_factory",
        ):
            getattr(app.state, name).kw["bind"].dispose()
