"""Identity follow-ups for the guardian UI: stable 422 reasons, rename, and suspend/reinstate.

- Every domain validation failure carries a stable ``errors[0].code`` (the top-level ``code`` stays
  ``VALIDATION_FAILED``), so a client can localize the message instead of showing English.
- ``PATCH /v1/identity/learners/{ref}`` changes the display name and nothing else.
- ``:suspend`` pauses a learner — sign-in stops and every refresh family is revoked at once — and
  ``:reinstate`` lifts it. Both are audited and owner-only (another family's learner is ``404``).
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.contexts.identity.domain.accounts import AccountStatus
from taleem_core.main import create_app
from taleem_core.platform.config import Settings

_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(database_url="", kdf_iterations=1_000))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _family(client: TestClient, email: str = "a@example.com", name: str = "Ayesha") -> Any:
    reg = client.post(
        "/v1/identity/guardians",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Fatima"},
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    auth = {"Authorization": f"Bearer {body['session']['access_token']}"}
    learner = client.post(
        "/v1/identity/learners", json={"displayName": name, "pin": _PIN}, headers=auth
    )
    assert learner.status_code == 201, learner.text
    ref = learner.json()["student_ref"]
    client.post(
        "/v1/identity/consents",
        json={"studentRef": ref, "scopes": ["learning_data"]},
        headers=auth,
    )
    return {"auth": auth, "guardian": body["guardian"], "ref": ref, "name": name}


def _signin(client: TestClient, fam: Any, name: str | None = None, pin: str = _PIN) -> Any:
    return client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": fam["guardian"]["family_code"],
            "displayName": name or fam["name"],
            "pin": pin,
            "deviceId": "device-a",
        },
    )


def _reason(response: Any) -> str:
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["type"] and body["title"] and body["status"] == 422  # RFC 9457 shape kept
    assert len(body["errors"]) == 1
    return str(body["errors"][0]["code"])


def _audit_actions(client: TestClient, fam: Any) -> list[dict[str, Any]]:
    events = client.get("/v1/identity/audit", headers=fam["auth"]).json()["events"]
    return [e for e in events if e["subject_ref"] == fam["ref"]]


# -------------------------------------------------------------------------- 422 reason codes


@pytest.mark.parametrize(
    ("body", "reason", "field"),
    [
        ({"email": "not-an-email"}, "EMAIL_INVALID", "email"),
        ({"passphrase": "short"}, "PASSPHRASE_TOO_SHORT", "passphrase"),
        ({"passphrase": "x" * 300}, "PASSPHRASE_TOO_LONG", "passphrase"),
        ({"passphrase": "\ta-long-enough-passphrase"}, "PASSPHRASE_WHITESPACE", "passphrase"),
        ({"displayName": "   "}, "DISPLAY_NAME_EMPTY", "displayName"),
        ({"displayName": "n" * 61}, "DISPLAY_NAME_TOO_LONG", "displayName"),
    ],
)
def test_registration_failures_carry_a_stable_reason(
    client: TestClient, body: dict[str, str], reason: str, field: str
) -> None:
    payload = {"email": "a@example.com", "passphrase": _PASSPHRASE, "displayName": "F", **body}
    response = client.post("/v1/identity/guardians", json=payload)
    assert _reason(response) == reason
    assert response.json()["errors"][0]["field"] == field


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"pin": "12"}, "PIN_FORMAT"),
        ({"pin": "12a4"}, "PIN_FORMAT"),
        ({"pin": "1234567"}, "PIN_FORMAT"),
        ({"pin": "1234"}, "PIN_TOO_EASY"),
        ({"displayName": "n" * 61}, "DISPLAY_NAME_TOO_LONG"),
        ({"displayName": "Ali\u0007"}, "DISPLAY_NAME_INVALID_CHARACTERS"),
        ({"gradeBand": "toddler"}, "GRADE_BAND_INVALID"),
        ({"gradeLevel": 13}, "GRADE_LEVEL_INVALID"),
        ({"displayName": "Ayesha"}, "DUPLICATE_LEARNER_NAME"),
        ({"displayName": " ayesha "}, "DUPLICATE_LEARNER_NAME"),
    ],
)
def test_enrolment_failures_carry_a_stable_reason(
    client: TestClient, body: dict[str, Any], reason: str
) -> None:
    fam = _family(client)
    payload = {"displayName": "Bilal", "pin": "5927", **body}
    response = client.post("/v1/identity/learners", json=payload, headers=fam["auth"])
    assert _reason(response) == reason


def test_the_family_size_limit_has_its_own_reason(client: TestClient) -> None:
    fam = _family(client)
    for i in range(11):
        created = client.post(
            "/v1/identity/learners",
            json={"displayName": f"Child {i}", "pin": "5927"},
            headers=fam["auth"],
        )
        assert created.status_code == 201, created.text
    response = client.post(
        "/v1/identity/learners",
        json={"displayName": "One more", "pin": "5927"},
        headers=fam["auth"],
    )
    assert _reason(response) == "LEARNER_LIMIT_REACHED"


def test_pin_reset_and_consent_failures_carry_a_stable_reason(client: TestClient) -> None:
    fam = _family(client)
    reset = client.post(
        f"/v1/identity/learners/{fam['ref']}/pin:reset", json={"pin": "0000"}, headers=fam["auth"]
    )
    assert _reason(reset) == "PIN_TOO_EASY"
    consent = client.post(
        "/v1/identity/consents",
        json={"studentRef": fam["ref"], "scopes": ["voice_audio"]},
        headers=fam["auth"],
    )
    assert _reason(consent) == "CONSENT_SCOPE_REQUIRED"
    assert consent.json()["errors"][0]["field"] == "scopes"


# ------------------------------------------------------------------------------------ rename


def test_a_guardian_renames_their_learner_and_the_child_signs_in_with_the_new_name(
    client: TestClient,
) -> None:
    fam = _family(client)
    renamed = client.patch(
        f"/v1/identity/learners/{fam['ref']}", json={"displayName": "Ayesha B"}, headers=fam["auth"]
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["display_name"] == "Ayesha B"
    roster = client.post(
        "/v1/identity/learners:roster", json={"familyCode": fam["guardian"]["family_code"]}
    ).json()["learners"]
    assert [r["display_name"] for r in roster] == ["Ayesha B"]
    assert _signin(client, fam, name="Ayesha B").status_code == 200
    assert _signin(client, fam, name="Ayesha").status_code == 401


def test_rename_is_audited_without_recording_the_name(client: TestClient) -> None:
    fam = _family(client)
    client.patch(
        f"/v1/identity/learners/{fam['ref']}", json={"displayName": "Zainab"}, headers=fam["auth"]
    )
    events = [e for e in _audit_actions(client, fam) if e["action"] == "learner.renamed"]
    assert len(events) == 1
    assert events[0]["actor_role"] == "guardian"
    assert "Zainab" not in str(events[0]) and "Ayesha" not in str(events[0])


def test_renaming_to_the_same_name_is_a_silent_no_op(client: TestClient) -> None:
    fam = _family(client)
    same = client.patch(
        f"/v1/identity/learners/{fam['ref']}", json={"displayName": "Ayesha"}, headers=fam["auth"]
    )
    assert same.status_code == 200
    assert not [e for e in _audit_actions(client, fam) if e["action"] == "learner.renamed"]


def test_rename_refuses_a_siblings_name_and_bad_names(client: TestClient) -> None:
    fam = _family(client)
    client.post(
        "/v1/identity/learners", json={"displayName": "Bilal", "pin": "5927"}, headers=fam["auth"]
    )
    path = f"/v1/identity/learners/{fam['ref']}"
    dup = client.patch(path, json={"displayName": "BILAL"}, headers=fam["auth"])
    assert _reason(dup) == "DUPLICATE_LEARNER_NAME"
    assert _reason(client.patch(path, json={"displayName": ""}, headers=fam["auth"])) == (
        "DISPLAY_NAME_EMPTY"
    )


def test_rename_accepts_the_display_name_and_nothing_else(client: TestClient) -> None:
    """No PII expansion through this route: any other property is refused."""
    fam = _family(client)
    response = client.patch(
        f"/v1/identity/learners/{fam['ref']}",
        json={"displayName": "Ayesha", "email": "child@example.com"},
        headers=fam["auth"],
    )
    assert response.status_code == 422
    learner = client.get("/v1/identity/learners", headers=fam["auth"]).json()["learners"][0]
    assert "email" not in learner


# ---------------------------------------------------------------------- suspend / reinstate


def test_suspend_ends_every_session_and_blocks_sign_in(client: TestClient) -> None:
    fam = _family(client)
    session = _signin(client, fam).json()
    refresh = session["refresh_token"]
    learner_auth = {"Authorization": f"Bearer {session['session']['access_token']}"}
    today = f"/v1/learning/students/{fam['ref']}/today"
    assert client.get(today, headers=learner_auth).status_code == 200

    suspended = client.post(f"/v1/identity/learners/{fam['ref']}:suspend", headers=fam["auth"])
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "paused"
    assert suspended.json()["can_sign_in"] is False

    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": refresh, "deviceId": "device-a"},
        ).status_code
        == 401
    )
    assert _signin(client, fam).status_code == 401  # uniform failure, no "paused" oracle
    # The still-unexpired access token is refused on the next request too (per-request gate).
    refused = client.get(today, headers=learner_auth)
    assert refused.status_code == 403
    assert refused.json()["code"] == "LEARNER_INACTIVE"

    events = [e for e in _audit_actions(client, fam) if e["action"] == "learner.suspended"]
    assert len(events) == 1
    assert events[0]["detail"]["revoked_sessions"] >= 1
    assert events[0]["actor_role"] == "guardian"


def test_suspend_is_idempotent(client: TestClient) -> None:
    fam = _family(client)
    path = f"/v1/identity/learners/{fam['ref']}:suspend"
    assert client.post(path, headers=fam["auth"]).json()["status"] == "paused"
    assert client.post(path, headers=fam["auth"]).json()["status"] == "paused"
    assert len([e for e in _audit_actions(client, fam) if e["action"] == "learner.suspended"]) == 1


def test_reinstate_restores_sign_in_and_is_audited(client: TestClient) -> None:
    fam = _family(client)
    client.post(f"/v1/identity/learners/{fam['ref']}:suspend", headers=fam["auth"])
    reinstated = client.post(f"/v1/identity/learners/{fam['ref']}:reinstate", headers=fam["auth"])
    assert reinstated.status_code == 200
    assert reinstated.json()["status"] == "active"
    assert reinstated.json()["can_sign_in"] is True
    assert _signin(client, fam).status_code == 200
    actions = [e["action"] for e in _audit_actions(client, fam)]
    assert "learner.reinstated" in actions
    # Reinstating an active learner changes nothing and records nothing new.
    again = client.post(f"/v1/identity/learners/{fam['ref']}:reinstate", headers=fam["auth"])
    assert again.json()["status"] == "active"
    assert [e["action"] for e in _audit_actions(client, fam)].count("learner.reinstated") == 1


def test_a_paused_learner_stays_visible_in_the_guardian_portal(client: TestClient) -> None:
    fam = _family(client)
    client.post(f"/v1/identity/learners/{fam['ref']}:suspend", headers=fam["auth"])
    assert client.get("/v1/guardian/me", headers=fam["auth"]).json()["children"] == [fam["ref"]]


def test_wrong_pins_cannot_turn_a_pause_into_an_unlockable_lock(client: TestClient) -> None:
    """Regression: five wrong PINs used to overwrite any status with ``locked``, which a PIN reset
    then turns into ``active`` — a way round a pause or an operator suspension."""
    fam = _family(client)
    client.post(f"/v1/identity/learners/{fam['ref']}:suspend", headers=fam["auth"])
    for _ in range(5):
        _signin(client, fam, pin="9999")
    client.post(
        f"/v1/identity/learners/{fam['ref']}/pin:reset", json={"pin": "5927"}, headers=fam["auth"]
    )
    learner = client.get("/v1/identity/learners", headers=fam["auth"]).json()["learners"][0]
    assert learner["status"] == "paused"


def _operator_suspend(app: FastAPI, ref: str) -> None:
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        learner = uow.learners.get(ref)
        assert learner is not None
        learner.status = AccountStatus.SUSPENDED
        uow.learners.save(learner)
        uow.commit()


def test_a_guardian_cannot_lift_an_operator_suspension(app: FastAPI, client: TestClient) -> None:
    fam = _family(client)
    _operator_suspend(app, fam["ref"])
    refused = client.post(f"/v1/identity/learners/{fam['ref']}:reinstate", headers=fam["auth"])
    assert refused.status_code == 409
    assert refused.json()["code"] == "LEARNER_SUSPENDED_BY_OPERATOR"
    # Suspending does not downgrade the operator hold either.
    suspended = client.post(f"/v1/identity/learners/{fam['ref']}:suspend", headers=fam["auth"])
    assert suspended.json()["status"] == "suspended"


def test_an_operator_suspension_survives_wrong_pins_and_a_pin_reset(
    app: FastAPI, client: TestClient
) -> None:
    fam = _family(client)
    _operator_suspend(app, fam["ref"])
    for _ in range(5):
        _signin(client, fam, pin="9999")
    client.post(
        f"/v1/identity/learners/{fam['ref']}/pin:reset", json={"pin": "5927"}, headers=fam["auth"]
    )
    learner = client.get("/v1/identity/learners", headers=fam["auth"]).json()["learners"][0]
    assert learner["status"] == "suspended"
    assert _signin(client, fam, pin="5927").status_code == 401


# --------------------------------------------------------------------- access boundaries


def _admin_calls(ref: str) -> list[tuple[str, str, dict[str, Any] | None]]:
    return [
        ("patch", f"/v1/identity/learners/{ref}", {"displayName": "Hijacked"}),
        ("post", f"/v1/identity/learners/{ref}:suspend", None),
        ("post", f"/v1/identity/learners/{ref}:reinstate", None),
    ]


def test_guardian_b_gets_404_and_changes_nothing(client: TestClient) -> None:
    fam_a = _family(client, "a@example.com")
    fam_b = _family(client, "b@example.com", name="Bilal")
    for method, path, body in _admin_calls(fam_a["ref"]):
        kwargs: dict[str, Any] = {"headers": fam_b["auth"]}
        if body is not None:
            kwargs["json"] = body
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code}"
    learner = client.get("/v1/identity/learners", headers=fam_a["auth"]).json()["learners"][0]
    assert (learner["display_name"], learner["status"]) == ("Ayesha", "active")
    assert not [
        e
        for e in _audit_actions(client, fam_a)
        if e["action"] in ("learner.renamed", "learner.suspended", "learner.reinstated")
    ]


def test_learner_and_operator_tokens_are_refused(client: TestClient) -> None:
    fam = _family(client)
    learner_token = _signin(client, fam).json()["session"]["access_token"]
    operator_token = sign_hs256(
        {"sub": "operator", "role": "system", "exp": int(time.time()) + 600},
        "dev-only-not-secret",
    )
    for token in (learner_token, operator_token):
        for method, path, body in _admin_calls(fam["ref"]):
            kwargs: dict[str, Any] = {"headers": {"Authorization": f"Bearer {token}"}}
            if body is not None:
                kwargs["json"] = body
            response = getattr(client, method)(path, **kwargs)
            assert response.status_code == 403, f"{method} {path} -> {response.status_code}"
    for method, path, body in _admin_calls(fam["ref"]):
        unauthenticated = getattr(client, method)(path, **({"json": body} if body else {}))
        assert unauthenticated.status_code == 401, f"{method} {path}"
