"""Explainable recommendations (R2) — structured, localizable rationale for teachers and guardians.

- Reason codes are a stable public contract (a snapshot of the enum; renaming one fails here).
- The plan carries them additively; every pre-existing plan field keeps its shape.
- The teacher's learner panel follows the guardian's progress_sharing consent LIVE, exactly like
  the existing class reads: withdrawn -> not found on the very next request; re-granted -> back.
- The guardian child view carries the same explanations.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from taleem_core.contexts.learning.domain.decision import ReasonCode
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE
from tests.test_school_api import (
    _ATTEST,
    _SECRET,
    World,
    _class,
    _family,
    _join,
    _org,
    _teacher,
)
from tests.test_sync_evidence import _publish_fractions


@pytest.fixture(name="world")
def _world() -> World:
    """The same composed world as test_school_api (one sharing learner in teacher A's class)."""
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    _publish_fractions(app)
    client = TestClient(app)
    org_a, org_b = _org(client, "School A"), _org(client, "School B", "GB")
    teacher_a = _teacher(client, org_a, "a1@school-a.example")
    teacher_a2 = _teacher(client, org_a, "a2@school-a.example")
    teacher_b = _teacher(client, org_b, "b1@school-b.example")
    class_a = _class(client, teacher_a, "Grade 4 Blue")
    class_b = _class(client, teacher_b, "Year 5 Red")
    fam = _family(client, "parent@example.com")
    assert _join(client, fam, class_a["join_code"]) == 200
    return World(client, app, org_a, org_b, teacher_a, teacher_a2, teacher_b, class_a, class_b, fam)


STABLE_CODES = {
    "safety_gate",
    "review_due",
    "misconception_active",
    "high_uncertainty",
    "ready_for_new",
    "mastery_below_threshold",
    "prerequisite_gap",
    "diagnostic_placement",
    "placed_above",
    "retention_at_risk",
    "repeated_failure",
    "mastery_reached",
    "all_mastered",
}


def test_reason_codes_are_a_stable_contract() -> None:
    assert {c.value for c in ReasonCode} == STABLE_CODES


def _detail(w: World, headers: dict[str, str] | None = None) -> Any:
    return w.client.get(
        f"/v1/school/classes/{w.class_a['class_id']}/learners/{w.family.student_ref}",
        headers=headers or w.teacher_a,
    )


def _place_once(w: World) -> dict[str, Any]:
    ref = w.family.student_ref
    status = w.client.get(f"/v1/learning/students/{ref}/placement", headers=w.family.learner)
    assert status.status_code == 200, status.text
    nxt = status.json()["next_item"]
    r = w.client.post(
        f"/v1/learning/students/{ref}/placement:answer",
        json={"item_ref": nxt["item_ref"], "option": 1},
        headers=w.family.learner,
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_plan_keeps_every_existing_field_and_adds_structured_reasons(world: World) -> None:
    w = world
    _place_once(w)
    plan = w.client.get(
        f"/v1/learning/students/{w.family.student_ref}/ai-teacher/plan", headers=w.family.learner
    ).json()
    for key in (
        "next_action",
        "weak_topics",
        "revision_due",
        "practice",
        "confidence",
        "rationale",
    ):
        assert key in plan
    assert set(plan["next_action"]) >= {"kind", "objective_code", "rationale"}
    assert all(isinstance(r["note"], str) for r in plan["next_action"]["rationale"])
    for reason in plan["next_action"]["reasons"]:
        assert reason["code"] in STABLE_CODES
        assert all(isinstance(v, str | int | float) for v in reason["params"].values())
    rec = plan["recommendations"][0]
    assert set(rec) >= {"kind", "reasons", "confidence", "uncertainty", "evidence"}
    assert rec["evidence"]["diagnostic"] == 1 and rec["confidence"] in ("low", "medium", "high")


def test_teacher_sees_why_for_a_sharing_learner_and_loses_it_live(world: World) -> None:
    w = world
    _place_once(w)
    r = _detail(w)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["display_name"] == "Zara"
    assert body["next_action"]["objective_code"] == OBJECTIVE_CODE
    codes = [x["code"] for x in body["next_action"]["reasons"]]
    assert "diagnostic_placement" in codes
    placed = next(x for x in body["next_action"]["reasons"] if x["code"] == "diagnostic_placement")
    assert placed["params"]["status"] == "uncertain" and placed["params"]["incorrect"] == 1
    rec = body["recommendations"][0]
    assert rec["evidence"] == {
        "practice": 0,
        "practice_correct": 0,
        "diagnostic": 1,
        "diagnostic_correct": 0,
        "last_at": rec["evidence"]["last_at"],
    }
    assert isinstance(rec["uncertainty"], float) and rec["estimate_source"] == "diagnostic"

    # Withdraw progress_sharing: the very next request with the same teacher token is not found.
    out = w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": w.family.student_ref, "scopes": ["progress_sharing"]},
        headers=w.family.guardian,
    )
    assert out.status_code == 200
    hidden = _detail(w)
    assert hidden.status_code == 404 and "diagnostic" not in hidden.text

    regrant = w.client.post(
        "/v1/identity/consents",
        json={
            "studentRef": w.family.student_ref,
            "scopes": ["learning_data", "progress_sharing"],
            "attestation": _ATTEST,
        },
        headers=w.family.guardian,
    )
    assert regrant.status_code == 200
    assert _detail(w).status_code == 200


def test_learner_panel_is_tenant_and_class_scoped(world: World) -> None:
    w = world
    for intruder in (w.teacher_b, w.teacher_a2):
        r = _detail(w, intruder)
        # Not found, and nothing about the learner (the problem's `instance` echoes the request).
        assert r.status_code == 404 and "Zara" not in r.text and "recommendations" not in r.text
    # Own class, but a learner not enrolled in it.
    unknown = w.client.get(
        f"/v1/school/classes/{w.class_a['class_id']}/learners/not-a-learner", headers=w.teacher_a
    )
    assert unknown.status_code == 404
    # A guardian or learner token cannot open the teacher route.
    assert _detail(w, w.family.guardian).status_code == 403
    assert _detail(w, w.family.learner).status_code == 403


def test_guardian_child_view_carries_the_explanations(world: World) -> None:
    w = world
    _place_once(w)
    r = w.client.get(f"/v1/guardian/children/{w.family.student_ref}", headers=w.family.guardian)
    assert r.status_code == 200, r.text
    body = r.json()
    explained = body["recommendation_explanations"]
    assert explained and explained[0]["is_next_action"] is True
    assert all(reason["code"] in STABLE_CODES for reason in explained[0]["reasons"])
    # Additive: the existing aggregate keeps its plan, now carrying the same reasons.
    assert body["ai_teacher_activity"]["recommendations"] == explained
