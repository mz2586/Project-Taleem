"""Guardian Portal — integration + security (WS2 + WS4 + WS5).

Drives the composed app: a guardian sees an aggregate view of ONLY linked children, built by reusing
the existing learning read models. Covers authorization, IDOR / parameter tampering / privilege
escalation, and the offline-sync status surfaced to the guardian.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

_SECRET = "dev-only-not-secret"  # noqa: S105 (dev stub)
_GUARDIAN = "grd-1"
_CHILD = "gchild-1"
_OTHER_CHILD = "gchild-2"  # exists, linked to a DIFFERENT guardian
_UNLINKED = "not-my-child"
_LINKS = f"{_GUARDIAN}=Amina:{_CHILD};grd-2:{_OTHER_CHILD}"
_REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _auth(role: str, sub: str) -> dict[str, str]:
    exp = int(time.time()) + 3600
    tok = sign_hs256({"sub": sub, "role": role, "exp": exp}, _SECRET)
    return {"Authorization": f"Bearer {tok}"}


def _app() -> FastAPI:
    app = create_app(Settings(database_url="", guardian_links_csv=_LINKS))
    _publish(app)
    return app


def _publish(app: FastAPI) -> None:
    sf = app.state.studio_session_factory

    def op(fn: object) -> None:
        with cs_uow(sf) as uow:
            svc = CurriculumStudioService(uow.lessons, uow.publish, clock=lambda: 1000.0)
            fn(svc)  # type: ignore[operator]
            uow.commit()

    op(lambda s: s.create(build_fractions_lesson()))
    op(lambda s: s.submit(LESSON_KEY, "subject_author"))
    for role in _REVIEW_ROLES:
        op(lambda s, role=role: s.review(LESSON_KEY, ReviewAction.APPROVE, role))
    op(lambda s: s.publish(LESSON_KEY, "curriculum_architect", "v1"))


def _seed_child_activity(c: TestClient, child: str) -> None:
    """Give a child real learning data via the student flow so the guardian view is non-empty."""
    h = _auth("student", child)
    started = c.post("/v1/learning/sessions", json={"student_ref": child}, headers=h)
    sid = started.json()["session_id"]
    c.post(f"/v1/learning/sessions/{sid}:next", headers=h)
    c.post(f"/v1/learning/sessions/{sid}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h)
    for _ in range(3):
        c.post(
            f"/v1/learning/sessions/{sid}:answer",
            json={"objective_code": OBJECTIVE_CODE, "item_ref": "p1-one-of-four", "option": 0},
            headers=h,
        )
    c.post(f"/v1/learning/sessions/{sid}:end", headers=h)


# ---------------------------------------------------------------- WS2: profile + dashboard + child


def test_guardian_me_lists_linked_children() -> None:
    c = TestClient(_app())
    r = c.get("/v1/guardian/me", headers=_auth("guardian", _GUARDIAN))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["guardian_ref"] == _GUARDIAN
    assert body["display_name"] == "Amina"
    assert body["children"] == [_CHILD]
    assert body["child_count"] == 1


def test_guardian_dashboard_aggregates_children() -> None:
    app = _app()
    c = TestClient(app)
    _seed_child_activity(c, _CHILD)
    r = c.get("/v1/guardian/dashboard", headers=_auth("guardian", _GUARDIAN))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["child_count"] == 1
    row = body["children"][0]
    assert row["student_ref"] == _CHILD
    assert set(row) >= {
        "progress",
        "streak",
        "sync_status",
        "open_interventions",
        "achievements_count",
    }
    assert row["progress"]["total_attempts"] >= 1  # reflects the seeded activity


def test_guardian_child_overview_has_every_required_section() -> None:
    app = _app()
    c = TestClient(app)
    _seed_child_activity(c, _CHILD)
    r = c.get(f"/v1/guardian/children/{_CHILD}", headers=_auth("guardian", _GUARDIAN))
    assert r.status_code == 200, r.text
    body = r.json()
    required = {
        "progress_overview",
        "knowledge_growth",
        "attendance",
        "learning_streaks",
        "weekly_summary",
        "learning_timeline",
        "assessment_history",
        "ai_teacher_activity",
        "recommendations",
        "intervention_notifications",
        "offline_sync_status",
        "achievement_history",
    }
    assert required <= set(body), required - set(body)


# -------------------------------------------------------------- WS4: authz / IDOR / escalation


def test_guardian_endpoints_require_auth() -> None:
    c = TestClient(_app())
    for path in ("/v1/guardian/me", "/v1/guardian/dashboard", f"/v1/guardian/children/{_CHILD}"):
        assert c.get(path).status_code == 401, path


def test_guardian_cannot_read_unlinked_child_idor() -> None:
    c = TestClient(_app())
    # A child that exists but is linked to a DIFFERENT guardian.
    r = c.get(f"/v1/guardian/children/{_OTHER_CHILD}", headers=_auth("guardian", _GUARDIAN))
    assert r.status_code == 403, r.text
    # A child that does not exist -> same uniform 403 (no existence disclosure / enumeration).
    r2 = c.get(f"/v1/guardian/children/{_UNLINKED}", headers=_auth("guardian", _GUARDIAN))
    assert r2.status_code == 403, r2.text


def test_parameter_tampering_path_variants_denied() -> None:
    c = TestClient(_app())
    h = _auth("guardian", _GUARDIAN)
    for ref in (f"{_CHILD} ", f"{_CHILD}%20", f"../{_CHILD}", f"{_CHILD}/../{_OTHER_CHILD}", "*"):
        r = c.get(f"/v1/guardian/children/{ref}", headers=h)
        assert r.status_code in (403, 404), f"{ref} -> {r.status_code}"


def test_non_guardian_roles_cannot_use_portal() -> None:
    c = TestClient(_app())
    for role in ("student", "mentor", "subject_author"):
        r = c.get("/v1/guardian/dashboard", headers=_auth(role, "x"))
        assert r.status_code == 403, f"{role} -> {r.status_code}"


def test_guardian_cannot_escalate_to_student_or_ops_surfaces() -> None:
    c = TestClient(_app())
    h = _auth("guardian", _GUARDIAN)
    # Guardian is NOT privileged on the raw student read endpoints (only mentor is).
    assert c.get(f"/v1/learning/students/{_CHILD}/today", headers=h).status_code == 403
    # Guardian cannot operate a session or the kill switch (deny-by-default PDP).
    started = c.post("/v1/learning/sessions", json={"student_ref": _CHILD}, headers=h)
    assert started.status_code == 403
    assert c.post("/v1/ops/kill-switch:engage", json={"reason": "x"}, headers=h).status_code == 403


def test_forged_and_expired_guardian_tokens_rejected() -> None:
    c = TestClient(_app())
    # wrong secret
    bad = sign_hs256({"sub": _GUARDIAN, "role": "guardian", "exp": int(time.time()) + 60}, "nope")
    assert c.get("/v1/guardian/me", headers={"Authorization": f"Bearer {bad}"}).status_code == 401
    # expired
    old = sign_hs256({"sub": _GUARDIAN, "role": "guardian", "exp": int(time.time()) - 5}, _SECRET)
    assert c.get("/v1/guardian/me", headers={"Authorization": f"Bearer {old}"}).status_code == 401


def test_guardian_view_is_read_only_no_mutation_endpoints() -> None:
    c = TestClient(_app())
    h = _auth("guardian", _GUARDIAN)
    # No POST/PUT/DELETE on the guardian surface (read-only).
    assert c.post(f"/v1/guardian/children/{_CHILD}", headers=h).status_code == 405
    assert c.delete("/v1/guardian/dashboard", headers=h).status_code == 405


# ---------------------------------------------------------------- WS5: offline sync status


def test_sync_status_reports_freshness() -> None:
    app = _app()
    c = TestClient(app)
    _seed_child_activity(c, _CHILD)
    r = c.get(f"/v1/guardian/children/{_CHILD}", headers=_auth("guardian", _GUARDIAN))
    sync = r.json()["offline_sync_status"]
    assert set(sync) == {
        "last_synced_at",
        "is_stale",
        "seconds_since_sync",
        "pending_is_device_reported",
    }
    assert sync["last_synced_at"] is not None  # child has synced activity
    assert sync["pending_is_device_reported"] is True


def test_guardian_with_no_links_sees_empty_profile() -> None:
    # Authenticated guardian, but not present in the directory -> empty (not an error).
    c = TestClient(_app())
    r = c.get("/v1/guardian/me", headers=_auth("guardian", "unknown-guardian"))
    assert r.status_code == 200
    assert r.json()["children"] == []


@pytest.mark.parametrize("view", ["me", "dashboard"])
def test_guardian_views_are_monitored(view: str) -> None:
    c = TestClient(_app())
    c.get(f"/v1/guardian/{view}", headers=_auth("guardian", _GUARDIAN))
    metrics = c.get("/metrics").text
    assert "taleem_guardian_views_total" in metrics
