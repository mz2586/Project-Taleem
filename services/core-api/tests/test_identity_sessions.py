"""Refresh-token sessions — continuity that never outlives permission.

The property under test is not "refresh works". It is that everything which could stop a child at
sign-in still stops them at refresh: withdrawn consent, a locked account, a changed PIN, a stolen
token. A refresh path that skipped any of those would quietly convert a ten-minute consent bound
into a thirty-day one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from taleem_core.contexts.identity.domain.sessions import (
    REFRESH_TOKEN_TTL_SECONDS,
    RefreshToken,
    RefreshTokenError,
    split,
)
from taleem_core.main import create_app
from taleem_core.platform.config import Settings

_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"
_FAST_KDF = 1_000


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(database_url="", kdf_iterations=_FAST_KDF)))


def _family(client: TestClient, email: str = "parent@example.com") -> dict:
    registration = client.post(
        "/v1/identity/guardians",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Fatima"},
    ).json()
    auth = {"Authorization": f"Bearer {registration['session']['access_token']}"}
    learner = client.post(
        "/v1/identity/learners",
        json={"displayName": "Ayesha", "pin": _PIN, "gradeLevel": 4},
        headers=auth,
    ).json()
    client.post(
        "/v1/identity/consents",
        json={"studentRef": learner["student_ref"], "scopes": ["learning_data"]},
        headers=auth,
    )
    return {
        "auth": auth,
        "guardian": registration["guardian"],
        "guardian_refresh": registration["refresh_token"],
        "learner": learner,
    }


def _learner_signin(client: TestClient, refs: dict, device: str = "device-a") -> dict:
    response = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": refs["guardian"]["family_code"],
            "displayName": "Ayesha",
            "pin": _PIN,
            "deviceId": device,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------------------- domain unit


def test_wire_form_splits_into_an_addressable_id_and_a_secret() -> None:
    record, wire = RefreshToken.issue(subject_ref="stu_1", role="student", device_id="d", now=0.0)
    token_id, secret = split(wire)
    assert token_id == record.token_id
    assert record.matches(secret)
    assert not record.matches(secret + "x")


def test_the_stored_digest_is_not_the_secret() -> None:
    record, wire = RefreshToken.issue(subject_ref="stu_1", role="student", device_id="d", now=0.0)
    _, secret = split(wire)
    assert secret not in record.token_hash
    assert len(record.token_hash) == 64


def test_malformed_tokens_raise_rather_than_matching_anything() -> None:
    for bad in ("", "no-dot", ".only-secret", "only-id."):
        with pytest.raises(RefreshTokenError):
            split(bad)


def test_usability_covers_expiry_consumption_revocation_and_device() -> None:
    record, _ = RefreshToken.issue(
        subject_ref="stu_1", role="student", device_id="device-a", now=0.0
    )
    assert record.is_usable(1.0, "device-a")
    assert not record.is_usable(1.0, "device-b")  # bound to its device
    assert not record.is_usable(REFRESH_TOKEN_TTL_SECONDS + 1, "device-a")  # expired

    consumed, _ = RefreshToken.issue(subject_ref="s", role="student", device_id="", now=0.0)
    consumed.consume(1.0)
    assert not consumed.is_usable(2.0, "anything")

    revoked, _ = RefreshToken.issue(subject_ref="s", role="student", device_id="", now=0.0)
    revoked.revoke(1.0)
    assert not revoked.is_usable(2.0, "anything")


def test_an_unbound_token_works_from_any_device() -> None:
    """A client that identified no device gets no binding, rather than a silent lock-out."""
    record, _ = RefreshToken.issue(subject_ref="s", role="student", device_id="", now=0.0)
    assert record.is_usable(1.0, "whatever")


def test_a_successor_inherits_its_family() -> None:
    first, _ = RefreshToken.issue(subject_ref="s", role="student", device_id="d", now=0.0)
    second, _ = RefreshToken.issue(
        subject_ref="s", role="student", device_id="d", now=1.0, family_id=first.family_id
    )
    assert second.family_id == first.family_id
    assert second.token_id != first.token_id


# ------------------------------------------------------------------------------- refresh flow


def test_sign_in_returns_a_refresh_token_for_both_roles(client: TestClient) -> None:
    refs = _family(client)
    assert refs["guardian_refresh"].startswith("rft_")
    assert _learner_signin(client, refs)["refresh_token"].startswith("rft_")


def test_refresh_returns_a_working_access_token_and_rotates(client: TestClient) -> None:
    refs = _family(client)
    session = _learner_signin(client, refs)

    refreshed = client.post(
        "/v1/identity/sessions:refresh",
        json={"refreshToken": session["refresh_token"], "deviceId": "device-a"},
    )
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["refresh_token"] != session["refresh_token"]  # rotated
    assert body["session"]["role"] == "student"

    student_ref = refs["learner"]["student_ref"]
    probe = client.get(
        f"/v1/learning/students/{student_ref}/today",
        headers={"Authorization": f"Bearer {body['session']['access_token']}"},
    )
    assert probe.status_code == 200


def test_a_guardian_can_refresh_too(client: TestClient) -> None:
    refs = _family(client)
    body = client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": refs["guardian_refresh"]}
    ).json()
    assert body["session"]["role"] == "guardian"
    assert body["guardian"]["family_code"] == refs["guardian"]["family_code"]
    probe = client.get(
        "/v1/identity/me",
        headers={"Authorization": f"Bearer {body['session']['access_token']}"},
    )
    assert probe.status_code == 200


def test_refresh_chains_across_several_rotations(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]
    for _ in range(5):
        response = client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": token, "deviceId": "device-a"},
        )
        assert response.status_code == 200
        token = response.json()["refresh_token"]


# ----------------------------------------------------------------------------------- theft


def test_reusing_a_consumed_token_revokes_the_whole_family(client: TestClient) -> None:
    refs = _family(client)
    original = _learner_signin(client, refs)["refresh_token"]
    successor = client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": original, "deviceId": "device-a"}
    ).json()["refresh_token"]

    # A thief replays the token they captured.
    replay = client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": original, "deviceId": "device-a"}
    )
    assert replay.status_code == 401

    # …and the legitimate holder's successor is dead too, because the two are indistinguishable.
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": successor, "deviceId": "device-a"},
        ).status_code
        == 401
    )


def test_reuse_detection_is_audited(client: TestClient) -> None:
    refs = _family(client)
    original = _learner_signin(client, refs)["refresh_token"]
    client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": original, "deviceId": "device-a"}
    )
    client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": original, "deviceId": "device-a"}
    )
    actions = {
        e["action"] for e in client.get("/v1/identity/audit", headers=refs["auth"]).json()["events"]
    }
    assert "session.reuse_detected" in actions


def test_a_token_lifted_to_another_device_is_refused(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs, device="device-a")["refresh_token"]
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": token, "deviceId": "device-thief"},
        ).status_code
        == 401
    )
    # The real device still works — refusing the thief did not consume the token.
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": token, "deviceId": "device-a"},
        ).status_code
        == 200
    )


def test_an_unknown_or_malformed_token_fails_like_any_other_sign_in(client: TestClient) -> None:
    for bad in ("rft_nope.secret", "garbage", "rft_x."):
        response = client.post("/v1/identity/sessions:refresh", json={"refreshToken": bad})
        assert response.status_code in (401, 422), bad


def test_a_valid_id_with_the_wrong_secret_is_refused(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]
    token_id, _ = split(token)
    forged = f"{token_id}.not-the-secret"
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": forged, "deviceId": "device-a"},
        ).status_code
        == 401
    )


# ------------------------------------------------------------------- permission still governs


def test_withdrawing_consent_kills_a_live_learner_session_at_once(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]

    client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": refs["learner"]["student_ref"]},
        headers=refs["auth"],
    )

    refused = client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": token, "deviceId": "device-a"}
    )
    # Revoked outright by the withdrawal, so this is the uniform sign-in failure rather than the
    # consent-specific 403 — the session is gone, not merely un-permitted.
    assert refused.status_code == 401


def test_a_partial_withdrawal_that_still_permits_learning_does_not_end_the_session(
    client: TestClient,
) -> None:
    refs = _family(client)
    student_ref = refs["learner"]["student_ref"]
    client.post(
        "/v1/identity/consents",
        json={"studentRef": student_ref, "scopes": ["learning_data", "ai_teaching"]},
        headers=refs["auth"],
    )
    token = _learner_signin(client, refs)["refresh_token"]
    client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": student_ref, "scopes": ["ai_teaching"]},
        headers=refs["auth"],
    )
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": token, "deviceId": "device-a"},
        ).status_code
        == 200
    )


def test_resetting_the_pin_ends_sessions_opened_with_the_old_one(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]
    client.post(
        f"/v1/identity/learners/{refs['learner']['student_ref']}/pin:reset",
        json={"pin": "5271"},
        headers=refs["auth"],
    )
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": token, "deviceId": "device-a"},
        ).status_code
        == 401
    )


def test_a_locked_learner_cannot_refresh(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]
    for _ in range(5):
        client.post(
            "/v1/identity/learners:signin",
            json={
                "familyCode": refs["guardian"]["family_code"],
                "displayName": "Ayesha",
                "pin": "9999",
            },
        )
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": token, "deviceId": "device-a"},
        ).status_code
        == 401
    )


# ---------------------------------------------------------------------------------- sign out


def test_signing_out_ends_the_session(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]
    signed_out = client.post("/v1/identity/sessions:signout", json={"refreshToken": token})
    assert signed_out.status_code == 200
    assert (
        client.post(
            "/v1/identity/sessions:refresh",
            json={"refreshToken": token, "deviceId": "device-a"},
        ).status_code
        == 401
    )


def test_sign_out_is_idempotent_and_silent_about_unknown_tokens(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]
    first = client.post("/v1/identity/sessions:signout", json={"refreshToken": token})
    second = client.post("/v1/identity/sessions:signout", json={"refreshToken": token})
    unknown = client.post("/v1/identity/sessions:signout", json={"refreshToken": "rft_x.y"})
    assert first.status_code == second.status_code == unknown.status_code == 200
    assert first.json() == second.json() == unknown.json() == {"signed_out": True}


def test_sign_out_is_audited(client: TestClient) -> None:
    refs = _family(client)
    token = _learner_signin(client, refs)["refresh_token"]
    client.post("/v1/identity/sessions:signout", json={"refreshToken": token})
    actions = {
        e["action"] for e in client.get("/v1/identity/audit", headers=refs["auth"]).json()["events"]
    }
    assert "session.signed_out" in actions


def test_signing_out_one_family_leaves_another_device_family_alone(client: TestClient) -> None:
    """Two devices sign in separately, so they are separate chains: logging out of one is not a
    global sign-out."""
    refs = _family(client)
    phone = _learner_signin(client, refs, device="phone")["refresh_token"]
    tablet = _learner_signin(client, refs, device="tablet")["refresh_token"]
    client.post("/v1/identity/sessions:signout", json={"refreshToken": phone})
    assert (
        client.post(
            "/v1/identity/sessions:refresh", json={"refreshToken": tablet, "deviceId": "tablet"}
        ).status_code
        == 200
    )
