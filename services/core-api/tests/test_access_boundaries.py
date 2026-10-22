"""Access-boundary regression suite for identity and the guardian portal.

Each test pins one boundary across *every* route it applies to, so a new route that forgets the
ownership guard, or a refactor that drops a role check from one handler, fails here by name. Cases
already pinned elsewhere (test_identity_api, test_identity_sessions, test_guardian_api) are not
repeated; this file fills the gaps an audit found:

- guardian B against guardian A's learner on the routes not yet covered (consent withdrawal, the
  learner list, the guardian portal), with a check that A's state is untouched afterwards;
- access tokens minted by the *real* issuer and then expired, on identity, portal and learning
  routes, plus tokens that carry no expiry at all (previously accepted forever — fixed in
  ``auth/jwt_verifier.py``);
- refresh after consent loss on the paths not yet covered: withdrawing only the required scope,
  consent lost without the service revoking sessions, and re-granting consent afterwards;
- a learner token against every guardian route on both surfaces.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.contexts.identity.application.tokens import TokenIssuer
from taleem_core.contexts.identity.domain.consent import ConsentRecord
from taleem_core.main import create_app
from taleem_core.platform.config import Settings

_SECRET = "dev-only-not-secret"  # noqa: S105 (dev stub)
_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"
_FAST_KDF = 1_000


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _family(client: TestClient, email: str, name: str = "Ayesha") -> dict[str, Any]:
    registration = client.post(
        "/v1/identity/guardians",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Fatima"},
    )
    assert registration.status_code == 201, registration.text
    body = registration.json()
    auth = {"Authorization": f"Bearer {body['session']['access_token']}"}
    learner = client.post(
        "/v1/identity/learners",
        json={"displayName": name, "pin": _PIN, "gradeLevel": 4},
        headers=auth,
    )
    assert learner.status_code == 201, learner.text
    consent = client.post(
        "/v1/identity/consents",
        json={"studentRef": learner.json()["student_ref"], "scopes": ["learning_data"]},
        headers=auth,
    )
    assert consent.status_code == 200, consent.text
    return {"auth": auth, "guardian": body["guardian"], "learner": learner.json(), "name": name}


def _learner_signin(client: TestClient, fam: dict[str, Any], device: str = "device-a") -> Any:
    response = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": fam["guardian"]["family_code"],
            "displayName": fam["name"],
            "pin": _PIN,
            "deviceId": device,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _refresh(client: TestClient, token: str, device: str = "device-a") -> Any:
    return client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": token, "deviceId": device}
    )


def _real_issuer() -> TokenIssuer:
    """The issuer the app itself uses in dev — same iss/aud binding, same dev signing path."""
    settings = Settings(database_url="")
    return TokenIssuer(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        hs256_secret=settings.jwt_dev_secret,
    )


# ------------------------------------------------- guardian A vs guardian B's learner (IDOR)


def _cross_family_calls(student_ref: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    """Every identity route that names a learner, as (method, path, json)."""
    return [
        ("get", f"/v1/identity/consents/{student_ref}", None),
        ("post", "/v1/identity/consents", {"studentRef": student_ref, "scopes": ["learning_data"]}),
        ("post", "/v1/identity/consents:withdraw", {"studentRef": student_ref}),
        (
            "post",
            "/v1/identity/consents:withdraw",
            {"studentRef": student_ref, "scopes": ["learning_data"]},
        ),
        ("post", f"/v1/identity/learners/{student_ref}/pin:reset", {"pin": "7391"}),
    ]


def test_guardian_b_cannot_read_or_act_on_guardian_as_learner_via_any_identity_route(
    client: TestClient,
) -> None:
    fam_a = _family(client, "a@example.com")
    fam_b = _family(client, "b@example.com", name="Bilal")
    student_a = fam_a["learner"]["student_ref"]

    for method, path, body in _cross_family_calls(student_a):
        kwargs: dict[str, Any] = {"headers": fam_b["auth"]}
        if body is not None:
            kwargs["json"] = body
        response = getattr(client, method)(path, **kwargs)
        # 404, not 403: a 403 would confirm the ref names a real child in another family.
        assert response.status_code == 404, f"{method} {path} {body} -> {response.status_code}"

    # None of B's attempts changed A's learner: consent intact, old PIN still works.
    state = client.get(f"/v1/identity/consents/{student_a}", headers=fam_a["auth"])
    assert state.status_code == 200
    assert state.json()["permits_sign_in"] is True
    assert all(entry["action"] == "granted" for entry in state.json()["history"])
    _learner_signin(client, fam_a)


def test_guardian_b_never_sees_guardian_as_learner_in_collection_routes(
    client: TestClient,
) -> None:
    fam_a = _family(client, "a@example.com")
    fam_b = _family(client, "b@example.com", name="Bilal")
    student_a = fam_a["learner"]["student_ref"]

    listed = client.get("/v1/identity/learners", headers=fam_b["auth"]).json()["learners"]
    assert student_a not in {entry["student_ref"] for entry in listed}
    profile = client.get("/v1/identity/me", headers=fam_b["auth"]).text
    assert student_a not in profile
    audit = client.get("/v1/identity/audit", headers=fam_b["auth"]).text
    assert student_a not in audit


def test_guardian_portal_refuses_another_familys_learner(client: TestClient) -> None:
    """The portal's own directory gate holds for identity-issued guardian tokens too."""
    fam_a = _family(client, "a@example.com")
    fam_b = _family(client, "b@example.com", name="Bilal")
    student_a = fam_a["learner"]["student_ref"]

    child = client.get(f"/v1/guardian/children/{student_a}", headers=fam_b["auth"])
    assert child.status_code == 403
    for path in ("/v1/guardian/me", "/v1/guardian/dashboard"):
        response = client.get(path, headers=fam_b["auth"])
        assert response.status_code == 200, path
        assert student_a not in response.text, path


def test_a_guardian_token_cannot_reach_its_own_childs_raw_learning_routes(
    client: TestClient,
) -> None:
    """Guardian → own child is still not a student session: the learner surface is the child's."""
    fam = _family(client, "a@example.com")
    student = fam["learner"]["student_ref"]
    response = client.get(f"/v1/learning/students/{student}/today", headers=fam["auth"])
    assert response.status_code == 403


# --------------------------------------------------------------------- expired access tokens


@pytest.mark.parametrize(
    "path",
    ["/v1/identity/me", "/v1/identity/learners", "/v1/identity/audit", "/v1/guardian/me"],
)
def test_an_expired_guardian_access_token_from_the_real_issuer_is_rejected(
    client: TestClient, path: str
) -> None:
    fam = _family(client, "a@example.com")
    guardian_ref = fam["guardian"]["guardian_ref"]
    # Valid signature, valid iss/aud, a real account — only the clock is wrong.
    expired = _real_issuer().issue(
        subject=guardian_ref, role="guardian", now=time.time() - 3600, ttl_seconds=600
    )
    response = client.get(path, headers={"Authorization": f"Bearer {expired.token}"})
    assert response.status_code == 401, response.text
    # Control: the same issuer with a live clock is accepted, so the 401 is the expiry.
    live = _real_issuer().issue(
        subject=guardian_ref, role="guardian", now=time.time(), ttl_seconds=600
    )
    assert client.get(path, headers={"Authorization": f"Bearer {live.token}"}).status_code == 200


def test_an_expired_learner_access_token_is_rejected_on_the_learning_surface(
    client: TestClient,
) -> None:
    fam = _family(client, "a@example.com")
    student = fam["learner"]["student_ref"]
    expired = _real_issuer().issue(
        subject=student, role="student", now=time.time() - 3600, ttl_seconds=600
    )
    response = client.get(
        f"/v1/learning/students/{student}/today",
        headers={"Authorization": f"Bearer {expired.token}"},
    )
    assert response.status_code == 401


@pytest.mark.parametrize("exp", [None, 0, "never"])
def test_a_token_with_no_usable_expiry_is_rejected(client: TestClient, exp: object) -> None:
    """Regression: a token without ``exp`` used to be accepted with no lifetime at all."""
    fam = _family(client, "a@example.com")
    claims: dict[str, object] = {"sub": fam["guardian"]["guardian_ref"], "role": "guardian"}
    if exp is not None:
        claims["exp"] = exp
    token = sign_hs256(claims, _SECRET)
    response = client.get("/v1/identity/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


# ------------------------------------------------------------ refresh after consent is lost


def test_withdrawing_only_the_required_scope_ends_the_session(client: TestClient) -> None:
    fam = _family(client, "a@example.com")
    student = fam["learner"]["student_ref"]
    client.post(
        "/v1/identity/consents",
        json={"studentRef": student, "scopes": ["learning_data", "ai_teaching"]},
        headers=fam["auth"],
    )
    token = _learner_signin(client, fam)["refresh_token"]
    withdrawn = client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": student, "scopes": ["learning_data"]},
        headers=fam["auth"],
    )
    assert withdrawn.json()["permits_sign_in"] is False
    assert _refresh(client, token).status_code == 401


def test_refresh_rechecks_consent_even_when_sessions_were_not_revoked(
    app: FastAPI, client: TestClient
) -> None:
    """Defence in depth: if consent disappears by any path that did not revoke sessions, the refresh
    gate itself refuses — and takes every other session for that learner with it."""
    fam = _family(client, "a@example.com")
    student = fam["learner"]["student_ref"]
    token_a = _learner_signin(client, fam, device="device-a")["refresh_token"]
    token_b = _learner_signin(client, fam, device="device-b")["refresh_token"]

    # Record a withdrawal directly, bypassing the service (and therefore its revocation step).
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        uow.consents.append(
            ConsentRecord.withdraw(
                guardian_ref=fam["guardian"]["guardian_ref"], student_ref=student, now=time.time()
            )
        )
        uow.commit()

    refused = _refresh(client, token_a, device="device-a")
    assert refused.status_code == 403
    assert refused.json()["code"] == "CONSENT_REQUIRED"
    # The other device's chain went too.
    assert _refresh(client, token_b, device="device-b").status_code == 401


def test_regranting_consent_does_not_resurrect_a_revoked_session(client: TestClient) -> None:
    fam = _family(client, "a@example.com")
    student = fam["learner"]["student_ref"]
    token = _learner_signin(client, fam)["refresh_token"]
    client.post("/v1/identity/consents:withdraw", json={"studentRef": student}, headers=fam["auth"])
    client.post(
        "/v1/identity/consents",
        json={"studentRef": student, "scopes": ["learning_data"]},
        headers=fam["auth"],
    )
    assert _refresh(client, token).status_code == 401
    # A fresh sign-in is the way back, and it works.
    _learner_signin(client, fam)


# ------------------------------------------------------- learner token vs guardian routes


def _guardian_routes(student_ref: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    return [
        ("get", "/v1/identity/me", None),
        ("get", "/v1/identity/learners", None),
        ("post", "/v1/identity/learners", {"displayName": "Sibling", "pin": "7391"}),
        ("post", f"/v1/identity/learners/{student_ref}/pin:reset", {"pin": "7391"}),
        ("get", f"/v1/identity/consents/{student_ref}", None),
        ("post", "/v1/identity/consents", {"studentRef": student_ref, "scopes": ["learning_data"]}),
        ("post", "/v1/identity/consents:withdraw", {"studentRef": student_ref}),
        ("get", "/v1/identity/audit", None),
        ("get", "/v1/guardian/me", None),
        ("get", "/v1/guardian/dashboard", None),
        ("get", f"/v1/guardian/children/{student_ref}", None),
    ]


def test_a_learner_token_is_refused_by_every_guardian_route(client: TestClient) -> None:
    fam = _family(client, "a@example.com")
    student = fam["learner"]["student_ref"]
    learner_auth = {
        "Authorization": f"Bearer {_learner_signin(client, fam)['session']['access_token']}"
    }

    for method, path, body in _guardian_routes(student):
        kwargs: dict[str, Any] = {"headers": learner_auth}
        if body is not None:
            kwargs["json"] = body
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, f"{method} {path} -> {response.status_code}"

    # Nothing the learner token attempted took effect: consent intact, PIN unchanged, no sibling.
    state = client.get(f"/v1/identity/consents/{student}", headers=fam["auth"]).json()
    assert state["permits_sign_in"] is True
    listed = client.get("/v1/identity/learners", headers=fam["auth"]).json()["learners"]
    assert [entry["student_ref"] for entry in listed] == [student]
    _learner_signin(client, fam, device="device-b")
