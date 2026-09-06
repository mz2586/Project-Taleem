"""Identity API — the guardian→consent→child sign-in journey, end to end on the composed app.

Covers the journey, the authorization boundary (IDOR, privilege escalation, role confusion), the
enumeration properties of the sign-in endpoints, the durable lockout, and the consent gate — the
behaviours that decide whether a real child may safely use this system.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.main import create_app
from taleem_core.platform.config import Settings

_SECRET = "dev-only-not-secret"  # noqa: S105 (dev stub)
_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"

# The suite runs the real KDF at a low work factor; a production floor is asserted separately in
# test_platform / below, so this cannot silently become the deployed value.
_FAST_KDF = 1_000


@pytest.fixture
def app() -> FastAPI:
    return create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _register(client: TestClient, email: str = "parent@example.com") -> dict[str, object]:
    response = client.post(
        "/v1/identity/guardians",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Fatima"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _bearer(session: dict[str, object]) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


def _enrol(client: TestClient, auth: dict[str, str], name: str = "Ayesha") -> dict[str, object]:
    response = client.post(
        "/v1/identity/learners",
        json={"displayName": name, "pin": _PIN, "gradeLevel": 4},
        headers=auth,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _consent(
    client: TestClient, auth: dict[str, str], student_ref: str, scopes: list[str] | None = None
) -> dict[str, object]:
    response = client.post(
        "/v1/identity/consents",
        json={
            "studentRef": student_ref,
            "scopes": scopes or ["learning_data", "voice_audio"],
            "attestation": "I am this child's parent and I agree.",
        },
        headers=auth,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _family(client: TestClient, email: str = "parent@example.com") -> tuple[dict[str, str], dict]:
    registration = _register(client, email)
    auth = _bearer(registration["session"])
    learner = _enrol(client, auth)
    _consent(client, auth, str(learner["student_ref"]))
    return auth, {"guardian": registration["guardian"], "learner": learner}


# ------------------------------------------------------------------------------ happy journey


def test_full_journey_register_enrol_consent_sign_in(client: TestClient) -> None:
    auth, refs = _family(client)
    family_code = refs["guardian"]["family_code"]

    roster = client.post("/v1/identity/learners:roster", json={"familyCode": family_code})
    assert roster.status_code == 200
    assert [entry["display_name"] for entry in roster.json()["learners"]] == ["Ayesha"]

    signin = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": family_code,
            "displayName": "Ayesha",
            "pin": _PIN,
            "deviceId": "device-a",
        },
    )
    assert signin.status_code == 200, signin.text
    body = signin.json()
    assert body["session"]["role"] == "student"
    assert body["session"]["subject"] == refs["learner"]["student_ref"]
    assert body["consent"]["permits_sign_in"] is True
    assert auth  # the guardian session is independent of the learner's


def test_learner_token_actually_opens_the_learning_surface(client: TestClient) -> None:
    """The point of the whole journey: the issued token is accepted by the product's own routes."""
    _, refs = _family(client)
    signin = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": refs["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
        },
    )
    token = signin.json()["session"]["access_token"]
    student_ref = refs["learner"]["student_ref"]
    response = client.get(
        f"/v1/learning/students/{student_ref}/today",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text


def test_learner_token_cannot_reach_another_learners_data(client: TestClient) -> None:
    _, refs = _family(client)
    token = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": refs["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
        },
    ).json()["session"]["access_token"]
    response = client.get(
        "/v1/learning/students/stu_someone-else/today",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_family_code_is_readable_and_returned_to_the_guardian(client: TestClient) -> None:
    guardian = _register(client)["guardian"]
    assert isinstance(guardian, dict)
    code = str(guardian["family_code"])
    assert len(code) == 9 and code[4] == "-"


# ---------------------------------------------------------------------------- the consent gate


def test_a_learner_without_consent_cannot_sign_in(client: TestClient) -> None:
    registration = _register(client)
    auth = _bearer(registration["session"])
    _enrol(client, auth)
    response = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": registration["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
        },
    )
    assert response.status_code == 403
    assert response.json()["code"] == "CONSENT_REQUIRED"


def test_withdrawing_consent_stops_the_next_sign_in_immediately(client: TestClient) -> None:
    auth, refs = _family(client)
    code = refs["guardian"]["family_code"]
    body = {"familyCode": code, "displayName": "Ayesha", "pin": _PIN}
    assert client.post("/v1/identity/learners:signin", json=body).status_code == 200

    withdrawn = client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": refs["learner"]["student_ref"]},
        headers=auth,
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["permits_sign_in"] is False

    denied = client.post("/v1/identity/learners:signin", json=body)
    assert denied.status_code == 403
    assert denied.json()["code"] == "CONSENT_REQUIRED"


def test_partial_withdrawal_leaves_the_child_able_to_learn(client: TestClient) -> None:
    auth, refs = _family(client)
    student_ref = refs["learner"]["student_ref"]
    _consent(client, auth, student_ref, ["learning_data", "ai_teaching"])
    client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": student_ref, "scopes": ["ai_teaching"]},
        headers=auth,
    )
    state = client.get(f"/v1/identity/consents/{student_ref}", headers=auth).json()
    assert state["permits_sign_in"] is True
    assert "ai_teaching" not in state["granted_scopes"]
    assert "learning_data" in state["granted_scopes"]


def test_consent_history_is_append_only_and_readable(client: TestClient) -> None:
    auth, refs = _family(client)
    student_ref = refs["learner"]["student_ref"]
    client.post("/v1/identity/consents:withdraw", json={"studentRef": student_ref}, headers=auth)
    _consent(client, auth, student_ref)
    history = client.get(f"/v1/identity/consents/{student_ref}", headers=auth).json()["history"]
    actions = [entry["action"] for entry in history]
    # Newest first: grant, withdraw, grant — every decision still present.
    assert actions == ["granted", "withdrawn", "granted"]
    assert all(entry["policy_version"] for entry in history)


def test_consent_requires_the_learning_data_scope(client: TestClient) -> None:
    registration = _register(client)
    auth = _bearer(registration["session"])
    learner = _enrol(client, auth)
    response = client.post(
        "/v1/identity/consents",
        json={"studentRef": learner["student_ref"], "scopes": ["ai_teaching"]},
        headers=auth,
    )
    assert response.status_code == 422


def test_unknown_consent_scope_is_rejected_not_ignored(client: TestClient) -> None:
    registration = _register(client)
    auth = _bearer(registration["session"])
    learner = _enrol(client, auth)
    response = client.post(
        "/v1/identity/consents",
        json={"studentRef": learner["student_ref"], "scopes": ["learning_data", "everything"]},
        headers=auth,
    )
    assert response.status_code == 422
    assert response.json()["code"] == "UNKNOWN_CONSENT_SCOPE"


def test_policy_endpoint_advertises_the_scope_vocabulary(client: TestClient) -> None:
    body = client.get("/v1/identity/policy").json()
    keys = {scope["key"] for scope in body["scopes"]}
    assert {"learning_data", "ai_teaching", "voice_audio", "progress_sharing"} <= keys
    required = [scope["key"] for scope in body["scopes"] if scope["required"]]
    assert required == ["learning_data"]


# ------------------------------------------------------------------ enumeration & failure shape


@pytest.mark.parametrize(
    "payload",
    [
        {"familyCode": "ZZZZ-ZZZZ", "displayName": "Ayesha", "pin": _PIN},  # no such family
        {"familyCode": "REAL", "displayName": "Nobody", "pin": _PIN},  # no such learner
        {"familyCode": "REAL", "displayName": "Ayesha", "pin": "9999"},  # wrong PIN
        {"familyCode": "bad", "displayName": "Ayesha", "pin": _PIN},  # malformed code
    ],
)
def test_every_sign_in_failure_looks_identical(client: TestClient, payload: dict) -> None:
    _, refs = _family(client)
    if payload["familyCode"] == "REAL":
        payload["familyCode"] = refs["guardian"]["family_code"]
    response = client.post("/v1/identity/learners:signin", json=payload)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"
    assert response.json()["detail"] == "Sign-in details are not correct"


def test_roster_for_an_unknown_family_is_empty_not_an_error(client: TestClient) -> None:
    response = client.post("/v1/identity/learners:roster", json={"familyCode": "ZZZZ-ZZZZ"})
    assert response.status_code == 200
    assert response.json()["learners"] == []


def test_roster_discloses_names_only(client: TestClient) -> None:
    _, refs = _family(client)
    entries = client.post(
        "/v1/identity/learners:roster",
        json={"familyCode": refs["guardian"]["family_code"]},
    ).json()["learners"]
    assert entries and set(entries[0]) == {"display_name", "grade_level"}
    assert "student_ref" not in entries[0]


def test_guardian_sign_in_does_not_reveal_whether_an_email_exists(client: TestClient) -> None:
    _register(client)
    unknown = client.post(
        "/v1/identity/guardians:signin",
        json={"email": "nobody@example.com", "passphrase": _PASSPHRASE},
    )
    wrong = client.post(
        "/v1/identity/guardians:signin",
        json={"email": "parent@example.com", "passphrase": "wrong-passphrase"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


# ---------------------------------------------------------------------------------- lockout


def test_learner_locks_after_repeated_wrong_pins_and_a_correct_pin_no_longer_works(
    client: TestClient,
) -> None:
    _, refs = _family(client)
    code = refs["guardian"]["family_code"]
    for _ in range(5):
        bad = client.post(
            "/v1/identity/learners:signin",
            json={"familyCode": code, "displayName": "Ayesha", "pin": "9999"},
        )
        assert bad.status_code == 401
    locked = client.post(
        "/v1/identity/learners:signin",
        json={"familyCode": code, "displayName": "Ayesha", "pin": _PIN},
    )
    assert locked.status_code == 401


def test_a_guardian_can_unlock_their_child_by_resetting_the_pin(client: TestClient) -> None:
    auth, refs = _family(client)
    code = refs["guardian"]["family_code"]
    for _ in range(5):
        client.post(
            "/v1/identity/learners:signin",
            json={"familyCode": code, "displayName": "Ayesha", "pin": "9999"},
        )
    reset = client.post(
        f"/v1/identity/learners/{refs['learner']['student_ref']}/pin:reset",
        json={"pin": "5271"},
        headers=auth,
    )
    assert reset.status_code == 200
    assert reset.json()["status"] == "active"
    ok = client.post(
        "/v1/identity/learners:signin",
        json={"familyCode": code, "displayName": "Ayesha", "pin": "5271"},
    )
    assert ok.status_code == 200


def test_a_successful_sign_in_clears_the_attempt_counter(client: TestClient) -> None:
    _, refs = _family(client)
    code = refs["guardian"]["family_code"]
    good = {"familyCode": code, "displayName": "Ayesha", "pin": _PIN}
    bad = {"familyCode": code, "displayName": "Ayesha", "pin": "9999"}
    for _ in range(3):
        client.post("/v1/identity/learners:signin", json=bad)
    assert client.post("/v1/identity/learners:signin", json=good).status_code == 200
    for _ in range(4):
        client.post("/v1/identity/learners:signin", json=bad)
    # Still under the limit because the counter reset — a child who eventually remembers their PIN
    # is not locked out by attempts made days earlier.
    assert client.post("/v1/identity/learners:signin", json=good).status_code == 200


# ----------------------------------------------------------------------- authorization / IDOR


def test_a_guardian_cannot_reach_another_familys_learner(client: TestClient) -> None:
    auth_a, refs_a = _family(client, "a@example.com")
    auth_b, _ = _family(client, "b@example.com")
    student_ref = refs_a["learner"]["student_ref"]

    # Guardian B holds a valid token and a real learner ref that is not theirs.
    assert client.get(f"/v1/identity/consents/{student_ref}", headers=auth_b).status_code == 404
    assert (
        client.post(
            "/v1/identity/consents",
            json={"studentRef": student_ref, "scopes": ["learning_data"]},
            headers=auth_b,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/v1/identity/learners/{student_ref}/pin:reset", json={"pin": "7391"}, headers=auth_b
        ).status_code
        == 404
    )
    # …and A is unaffected.
    assert client.get(f"/v1/identity/consents/{student_ref}", headers=auth_a).status_code == 200


def test_a_learner_token_cannot_manage_identity(client: TestClient) -> None:
    _, refs = _family(client)
    token = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": refs["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
        },
    ).json()["session"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/identity/me", headers=headers).status_code == 403
    assert (
        client.post(
            "/v1/identity/learners",
            json={"displayName": "Sibling", "pin": "7391"},
            headers=headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/identity/consents",
            json={"studentRef": refs["learner"]["student_ref"], "scopes": ["learning_data"]},
            headers=headers,
        ).status_code
        == 403
    )


def test_a_forged_role_claim_is_still_bounded_by_ownership(client: TestClient) -> None:
    """A hand-minted guardian token for a ref that owns nothing reaches nothing."""
    token = sign_hs256(
        {"sub": "gdn_not-real", "role": "guardian", "exp": int(time.time()) + 3600}, _SECRET
    )
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/v1/identity/me", headers=headers).status_code == 404
    assert client.get("/v1/identity/learners", headers=headers).status_code == 404


def test_identity_routes_require_authentication(client: TestClient) -> None:
    for method, path in (
        ("get", "/v1/identity/me"),
        ("get", "/v1/identity/learners"),
        ("get", "/v1/identity/audit"),
    ):
        assert getattr(client, method)(path).status_code == 401


def test_operator_role_cannot_grant_consent_on_a_guardians_behalf(client: TestClient) -> None:
    """Consent is a decision only the responsible adult may make — not an operator convenience."""
    _, refs = _family(client)
    token = sign_hs256(
        {"sub": "operator", "role": "system", "exp": int(time.time()) + 3600}, _SECRET
    )
    response = client.post(
        "/v1/identity/consents",
        json={"studentRef": refs["learner"]["student_ref"], "scopes": ["learning_data"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# -------------------------------------------------------------------------------- enrolment


def test_duplicate_display_name_within_a_family_is_refused(client: TestClient) -> None:
    registration = _register(client)
    auth = _bearer(registration["session"])
    _enrol(client, auth, "Ayesha")
    response = client.post(
        "/v1/identity/learners", json={"displayName": "  ayesha ", "pin": "7391"}, headers=auth
    )
    assert response.status_code == 422


def test_the_same_name_in_two_different_families_is_fine(client: TestClient) -> None:
    _, first = _family(client, "a@example.com")
    _, second = _family(client, "b@example.com")
    assert first["learner"]["display_name"] == second["learner"]["display_name"] == "Ayesha"
    assert first["learner"]["student_ref"] != second["learner"]["student_ref"]


def test_weak_pins_are_refused_at_enrolment(client: TestClient) -> None:
    auth = _bearer(_register(client)["session"])
    for pin in ("1234", "0000", "12", "abcd"):
        response = client.post(
            "/v1/identity/learners", json={"displayName": f"Child{pin}", "pin": pin}, headers=auth
        )
        assert response.status_code == 422, pin


def test_short_guardian_passphrase_is_refused(client: TestClient) -> None:
    response = client.post(
        "/v1/identity/guardians",
        json={"email": "x@example.com", "passphrase": "short", "displayName": "X"},
    )
    assert response.status_code == 422


def test_duplicate_registration_is_a_conflict(client: TestClient) -> None:
    _register(client)
    response = client.post(
        "/v1/identity/guardians",
        json={"email": "PARENT@example.com", "passphrase": _PASSPHRASE, "displayName": "Other"},
    )
    assert response.status_code == 409


def test_a_newly_enrolled_learner_reports_that_it_cannot_sign_in_yet(client: TestClient) -> None:
    auth = _bearer(_register(client)["session"])
    learner = _enrol(client, auth)
    assert learner["can_sign_in"] is False
    assert learner["consent"]["permits_sign_in"] is False


def test_guardian_profile_lists_only_their_own_learners(client: TestClient) -> None:
    auth_a, _ = _family(client, "a@example.com")
    _family(client, "b@example.com")
    profile = client.get("/v1/identity/me", headers=auth_a).json()
    assert len(profile["learners"]) == 1
    assert profile["guardian"]["email"] == "a@example.com"


# ------------------------------------------------------------------------------------ audit


def test_the_audit_trail_records_the_journey_and_stops_at_the_family_boundary(
    client: TestClient,
) -> None:
    auth_a, refs_a = _family(client, "a@example.com")
    auth_b, _ = _family(client, "b@example.com")
    client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": refs_a["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
        },
    )
    events = client.get("/v1/identity/audit", headers=auth_a).json()["events"]
    actions = {event["action"] for event in events}
    assert {
        "guardian.registered",
        "learner.created",
        "consent.granted",
        "learner.signed_in",
    } <= actions

    subjects = {event["subject_ref"] for event in events}
    b_events = client.get("/v1/identity/audit", headers=auth_b).json()["events"]
    assert subjects.isdisjoint({event["subject_ref"] for event in b_events})


def test_failed_sign_ins_are_audited(client: TestClient) -> None:
    auth, refs = _family(client)
    client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": refs["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": "9999",
        },
    )
    actions = {e["action"] for e in client.get("/v1/identity/audit", headers=auth).json()["events"]}
    assert "learner.sign_in_failed" in actions


def test_a_denied_sign_in_for_missing_consent_is_audited(client: TestClient) -> None:
    registration = _register(client)
    auth = _bearer(registration["session"])
    _enrol(client, auth)
    client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": registration["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
        },
    )
    actions = {e["action"] for e in client.get("/v1/identity/audit", headers=auth).json()["events"]}
    assert "learner.sign_in_denied_no_consent" in actions


# ------------------------------------------------------------------------- ops interactions


def test_the_kill_switch_halts_learner_sign_in_but_not_the_guardian_portal(
    client: TestClient,
) -> None:
    """An operator halt must stop children entering — and must not lock adults out of consent."""
    auth, refs = _family(client)
    operator = {
        "Authorization": "Bearer "
        + sign_hs256({"sub": "op", "role": "system", "exp": int(time.time()) + 3600}, _SECRET)
    }
    assert (
        client.post("/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=operator)
    ).status_code == 200

    halted = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": refs["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
        },
    )
    assert halted.status_code == 503
    # The guardian can still act — including withdrawing consent during an incident.
    assert client.get("/v1/identity/me", headers=auth).status_code == 200
    assert (
        client.post(
            "/v1/identity/consents:withdraw",
            json={"studentRef": refs["learner"]["student_ref"]},
            headers=auth,
        ).status_code
        == 200
    )


def test_rate_limiting_bounds_unauthenticated_sign_in_attempts(client: TestClient) -> None:
    _, refs = _family(client)
    body = {
        "familyCode": refs["guardian"]["family_code"],
        "displayName": "Ayesha",
        "pin": "9999",
    }
    statuses = [
        client.post("/v1/identity/learners:signin", json=body).status_code for _ in range(15)
    ]
    assert 429 in statuses


# --------------------------------------------------------------------------- production floor


def test_production_refuses_to_boot_with_a_weak_password_work_factor() -> None:
    """The suite's fast KDF must be impossible to inherit in production."""
    from taleem_core.platform.config import (
        MIN_KDF_ITERATIONS,
        Environment,
        InsecureConfigurationError,
        _assert_production_safe,
    )

    weak = Settings(
        environment=Environment.PRODUCTION,
        jwt_signing_seed_hex="11" * 32,
        database_url="postgresql+psycopg://x/y",
        offline_signing_seed_hex="22" * 32,
        kdf_iterations=_FAST_KDF,
    )
    with pytest.raises(InsecureConfigurationError) as caught:
        _assert_production_safe(weak)
    assert "TALEEM_KDF_ITERATIONS" in str(caught.value)

    strong = Settings(
        environment=Environment.PRODUCTION,
        jwt_signing_seed_hex="11" * 32,
        database_url="postgresql+psycopg://x/y",
        offline_signing_seed_hex="22" * 32,
        kdf_iterations=MIN_KDF_ITERATIONS,
    )
    _assert_production_safe(strong)
