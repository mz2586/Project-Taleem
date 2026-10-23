"""The registered-role hook on identity's refresh flow, exercised with a fake role.

``IdentityService.register_session_subject`` lets another component (Studio staff today, teachers
next) continue sessions through identity's rotating refresh tokens. Everything identity guarantees
for its own roles must hold unchanged for a registered one: rotation, single use, replay revokes the
whole family, device binding, sign-out, and the live "may this subject continue" check on every
refresh.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.contexts.identity.application.identity_service import IdentityService
from taleem_core.contexts.identity.application.tokens import IssuedToken, TokenIssuer
from taleem_core.main import create_app
from taleem_core.platform.config import Settings

ROLE = "fake_role"
_SETTINGS = Settings(database_url="", kdf_iterations=1_000)
# The dev-path issuer the app itself uses (same iss/aud, HS256 dev secret).
_ISSUER = TokenIssuer(
    issuer=_SETTINGS.jwt_issuer,
    audience=_SETTINGS.jwt_audience,
    hs256_secret=_SETTINGS.jwt_dev_secret,
)


def _never_called(_ref: str, _now: float) -> IssuedToken:
    raise AssertionError("not reached")


class FakeOwner:
    """A component that owns ``fake_role`` subjects and decides whether each may continue."""

    def __init__(self) -> None:
        self.active: set[str] = set()
        self.checks: list[str] = []

    def is_active(self, subject_ref: str) -> bool:
        self.checks.append(subject_ref)
        return subject_ref in self.active

    def issue_access(self, subject_ref: str, now: float) -> IssuedToken:
        return _ISSUER.issue(subject=subject_ref, role=ROLE, now=now, ttl_seconds=600)

    def profile(self, subject_ref: str) -> dict[str, Any]:
        return {"fake": {"ref": subject_ref}}


@pytest.fixture
def app() -> FastAPI:
    return create_app(_SETTINGS)


@pytest.fixture
def owner(app: FastAPI) -> FakeOwner:
    identity: IdentityService = app.state.identity_service
    fake = FakeOwner()
    identity.register_session_subject(
        ROLE,
        is_active=fake.is_active,
        issue_access=fake.issue_access,
        profile=fake.profile,
        refresh_ttl_seconds=3600,
    )
    fake.active.add("fake_1")
    return fake


def _refresh(client: TestClient, token: str, device: str = "") -> Any:
    return client.post(
        "/v1/identity/sessions:refresh", json={"refreshToken": token, "deviceId": device}
    )


def test_a_registered_role_refreshes_and_rotates(app: FastAPI, owner: FakeOwner) -> None:
    client = TestClient(app)
    first = app.state.identity_service.issue_refresh_token("fake_1", ROLE)
    response = _refresh(client, first)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["session"]["role"], body["session"]["subject"]) == (ROLE, "fake_1")
    assert body["fake"] == {"ref": "fake_1"}
    assert body["refresh_token"] != first
    assert owner.checks == ["fake_1"]  # the live check ran on this refresh


def test_reuse_revokes_the_whole_family_for_a_registered_role(
    app: FastAPI, owner: FakeOwner
) -> None:
    client = TestClient(app)
    first = app.state.identity_service.issue_refresh_token("fake_1", ROLE)
    successor = _refresh(client, first).json()["refresh_token"]
    assert _refresh(client, first).status_code == 401  # replay
    assert _refresh(client, successor).status_code == 401  # the family went with it


def test_the_live_check_runs_on_every_refresh(app: FastAPI, owner: FakeOwner) -> None:
    client = TestClient(app)
    token = app.state.identity_service.issue_refresh_token("fake_1", ROLE)
    token = _refresh(client, token).json()["refresh_token"]
    owner.active.discard("fake_1")  # e.g. the owner suspended the account
    assert _refresh(client, token).status_code == 401
    assert owner.checks == ["fake_1", "fake_1"]


def test_device_binding_and_sign_out_apply_unchanged(app: FastAPI, owner: FakeOwner) -> None:
    client = TestClient(app)
    bound = app.state.identity_service.issue_refresh_token("fake_1", ROLE, "device-a")
    assert _refresh(client, bound, device="device-b").status_code == 401
    other = app.state.identity_service.issue_refresh_token("fake_1", ROLE)
    client.post("/v1/identity/sessions:signout", json={"refreshToken": other})
    assert _refresh(client, other).status_code == 401


def test_an_owner_cannot_widen_or_move_a_session(app: FastAPI) -> None:
    identity: IdentityService = app.state.identity_service

    def widened(subject_ref: str, now: float) -> IssuedToken:
        return _ISSUER.issue(subject=subject_ref, role="guardian", now=now, ttl_seconds=600)

    identity.register_session_subject(
        "sneaky_role", is_active=lambda _ref: True, issue_access=widened
    )
    token = identity.issue_refresh_token("x_1", "sneaky_role")
    assert _refresh(TestClient(app), token).status_code == 401


@pytest.mark.parametrize("role", ["student", "guardian", ""])
def test_built_in_roles_cannot_be_registered(app: FastAPI, role: str) -> None:
    with pytest.raises(ValueError, match="cannot be registered"):
        app.state.identity_service.register_session_subject(
            role, is_active=lambda _r: True, issue_access=_never_called
        )


def test_a_role_registers_once_and_unregistered_roles_get_no_chain(
    app: FastAPI, owner: FakeOwner
) -> None:
    identity: IdentityService = app.state.identity_service
    with pytest.raises(ValueError, match="already registered"):
        identity.register_session_subject(
            ROLE, is_active=owner.is_active, issue_access=owner.issue_access
        )
    with pytest.raises(ValueError, match="not a registered session subject"):
        identity.issue_refresh_token("t_1", "teacher")
    with pytest.raises(ValueError, match="positive"):
        identity.register_session_subject(
            "other_role",
            is_active=owner.is_active,
            issue_access=owner.issue_access,
            refresh_ttl_seconds=0,
        )


def test_staff_roles_are_registered_through_the_same_hook(app: FastAPI) -> None:
    identity: IdentityService = app.state.identity_service
    with pytest.raises(ValueError, match="already registered"):
        identity.register_session_subject(
            "subject_author", is_active=lambda _r: True, issue_access=_never_called
        )
