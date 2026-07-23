"""Kill switch + ops controls — Software Completion Mode.

The kill switch halts child-facing routes (503) during an incident while health/metrics/ops stay up;
only a system operator may engage/disengage. Covers the pure state machine + the wired middleware +
authorization.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.kill_switch import KillSwitch, is_child_facing

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)


def _auth(role: str, sub: str = "op-1") -> dict[str, str]:
    exp = int(time.time()) + 3600
    return {
        "Authorization": f"Bearer {sign_hs256({'sub': sub, 'role': role, 'exp': exp}, _SECRET)}"
    }


# ---------------------------------------------------------------- unit: state machine


def test_kill_switch_engage_disengage() -> None:
    ks = KillSwitch(lambda: 100.0)
    assert ks.engaged is False
    s = ks.engage("incident")
    assert s.engaged is True and s.reason == "incident" and s.changed_at == 100.0
    d = ks.disengage()
    assert d.engaged is False and d.reason == ""


def test_is_child_facing() -> None:
    assert is_child_facing("/v1/learning/sessions/x:next") is True
    assert is_child_facing("/v1/learning/students/s/today") is True
    assert is_child_facing("/v1/offline/packages") is True
    assert is_child_facing("/v1/sync/batch") is True
    assert is_child_facing("/health") is False
    assert is_child_facing("/metrics") is False
    assert is_child_facing("/v1/ops/kill-switch") is False


# ---------------------------------------------------------------- integration: wired behaviour


def test_kill_switch_halts_child_facing_and_stays_reachable() -> None:
    app = create_app(Settings(database_url=""))
    c = TestClient(app)
    sysh = _auth("system")
    stu = _auth("student", "kss-stu")

    # Initially disengaged.
    assert c.get("/v1/ops/kill-switch", headers=sysh).json()["engaged"] is False
    # A child-facing route is reachable (401 = auth reached the app, not blocked by the switch).
    assert c.get("/v1/learning/students/kss-stu/today").status_code == 401

    # Engage → child-facing routes return 503; health + ops stay up.
    engaged = c.post("/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=sysh)
    assert engaged.status_code == 200 and engaged.json()["engaged"] is True
    assert c.get("/v1/learning/students/kss-stu/today", headers=stu).status_code == 503
    assert c.post("/v1/sync/batch", json={"cursor": 0, "deltas": []}).status_code == 503
    assert c.get("/health").status_code == 200  # health unaffected
    assert c.get("/metrics").status_code == 200  # metrics unaffected
    assert c.get("/v1/ops/status", headers=sysh).status_code == 200  # ops reachable

    # Disengage → child-facing routes reachable again.
    c.post("/v1/ops/kill-switch:disengage", headers=sysh)
    assert c.get("/v1/learning/students/kss-stu/today", headers=stu).status_code in (200, 403)


def test_kill_switch_controls_are_operator_only() -> None:
    app = create_app(Settings(database_url=""))
    c = TestClient(app)
    # A non-system role cannot engage the kill switch (deny-by-default PDP).
    assert (
        c.post(
            "/v1/ops/kill-switch:engage", json={"reason": "x"}, headers=_auth("student")
        ).status_code
        == 403
    )
    # Unauthenticated cannot reach the controls.
    assert c.post("/v1/ops/kill-switch:engage", json={"reason": "x"}).status_code == 401


def test_ops_status_summary() -> None:
    app = create_app(Settings(database_url=""))
    c = TestClient(app)
    body = c.get("/v1/ops/status", headers=_auth("system")).json()
    assert "kill_switch" in body and "ready" in body and "counters" in body
    assert set(body["counters"]) == {
        "sessions_started",
        "objectives_mastered",
        "misconceptions_detected",
    }
