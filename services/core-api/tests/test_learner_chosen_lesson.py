"""A learner-chosen lesson (a lesson row on the path, a unit-check remediation link).

``:teach`` with ``learner_chosen`` opens any published lesson visible to the learner's cohort
(DEMO_COHORT_CONTRACT §3: another cohort's or an unpublished lesson is 404), records the choice in
the session's rationale ("You chose this lesson") beside the engine's own recommendation, and
returns unmet prerequisites as a gentle ``prerequisite_hint`` — never a block.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.learning.domain.decision import (
    LEARNER_CHOICE_RULE,
    Decision,
    DecisionKind,
    ReasonCode,
    learner_choice,
    unmet_prerequisites,
)
from taleem_core.contexts.learning.domain.knowledge import PriorProvenance, StudentKnowledge
from taleem_core.contexts.learning.domain.session import CHOSEN_BY_ENGINE, CHOSEN_BY_LEARNER
from taleem_core.contexts.learning.domain.values import MasteryState
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from tests.test_progression_api import (
    OBJ_A,
    OBJ_B,
    OBJ_C,
    OBJ_D,
    Clock,
    P,
    make_lesson,
    publish,
    store_hierarchy,
)
from tests.test_school_api import _SECRET, _family

OBJ_E = "TST-G4-E"  # created, never published


@pytest.fixture
def p() -> P:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    store_hierarchy(app)
    publish(app, make_lesson("L-A", OBJ_A, "u-fractions", "t1"))
    lesson_b = make_lesson("L-B", OBJ_B, "u-fractions", "t2")
    lesson_b.prerequisites = [OBJ_A, OBJ_D]  # OBJ_D is taught only by a demo lesson
    publish(app, lesson_b)
    publish(app, make_lesson("L-C", OBJ_C, "u-measure", "t1"))
    publish(app, make_lesson("L-D", OBJ_D, "u-demo", "t1", audience="demo"))
    with cs_uow(app.state.studio_session_factory) as uow:
        CurriculumStudioService(uow.lessons, uow.publish, clock=lambda: 1000.0).create(
            make_lesson("L-E", OBJ_E, "u-measure", "t1")
        )
        uow.commit()
    client = TestClient(app)
    fam = _family(client, "chosen@example.com")
    other = _family(client, "chosen-other@example.com")
    return P(client, app, fam, other, Clock())


def _session(p: P) -> str:
    res = p.client.post(
        "/v1/learning/sessions", json={"student_ref": p.fam.student_ref}, headers=p.fam.learner
    )
    assert res.status_code == 201, res.text
    return str(res.json()["session_id"])


def _choose(p: P, sid: str, code: str) -> Any:
    return p.client.post(
        f"/v1/learning/sessions/{sid}:teach",
        json={"objective_code": code, "learner_chosen": True},
        headers=p.fam.learner,
    )


def test_a_chosen_lesson_opens_straight_after_start_and_is_marked_learner_chosen(p: P) -> None:
    sid = _session(p)
    res = _choose(p, sid, OBJ_C)  # no :next first — the learner picked it from the path
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["items"] and body["utterances"]
    assert body["chosen_by"] == "learner"
    choice = body["choice"]
    assert choice["objective_code"] == OBJ_C and choice["chosen_by"] == "learner"
    assert choice["rationale"][0].startswith("You chose this lesson")
    # The AI still recommends — reported beside the choice, never blocking it.
    rec = choice["recommended"]
    assert rec["decision"] == "teach" and rec["objective_code"] in (OBJ_A, OBJ_B, OBJ_C)
    suggested = f"suggested teach {rec['objective_code']}" in choice["rationale"][0]
    assert suggested is (rec["objective_code"] != OBJ_C)
    assert choice["prerequisite_hint"] is None and choice["reasons"] == []


def test_the_session_rationale_records_the_learner_choice_and_the_interaction(p: P) -> None:
    sid = _session(p)
    body = _choose(p, sid, OBJ_C).json()
    item = body["items"][0]
    ans = p.client.post(
        f"/v1/learning/sessions/{sid}:answer",
        json={"objective_code": OBJ_C, "item_ref": item["item_ref"], "option": 0},
        headers=p.fam.learner,
    )
    assert ans.status_code == 200, ans.text
    session = p.app.state.session_service.get_session(sid)
    (record,) = session.decisions
    assert record.chosen_by == CHOSEN_BY_LEARNER and record.objective_code == OBJ_C
    assert record.kind == "teach" and record.rationale[0].startswith("You chose this lesson")
    assert [i.chosen_by for i in session.interactions] == [CHOSEN_BY_LEARNER]
    assert session.learner_chosen_objective == OBJ_C


def test_the_engine_path_is_unchanged_and_says_so(p: P) -> None:
    sid = _session(p)
    decision = p.client.post(f"/v1/learning/sessions/{sid}:next", headers=p.fam.learner).json()
    res = p.client.post(
        f"/v1/learning/sessions/{sid}:teach",
        json={"objective_code": decision["objective_code"]},
        headers=p.fam.learner,
    )
    assert res.status_code == 200, res.text
    assert res.json()["chosen_by"] == "engine" and res.json()["choice"] is None
    session = p.app.state.session_service.get_session(sid)
    assert [d.chosen_by for d in session.decisions] == [CHOSEN_BY_ENGINE]
    assert session.learner_chosen_objective is None


def test_unmet_prerequisites_are_a_hint_with_titles_never_a_block(p: P) -> None:
    sid = _session(p)
    res = _choose(p, sid, OBJ_B)
    assert res.status_code == 200, res.text  # allowed despite unmet prerequisites
    choice = res.json()["choice"]
    unmet = choice["prerequisite_hint"]["unmet"]
    assert [u["objective_code"] for u in unmet] == [OBJ_A, OBJ_D]
    assert unmet[0]["title"]["en"] and unmet[0]["title"]["ur"]
    # A real learner never receives the demo lesson's title, even as a prerequisite's.
    assert unmet[1]["title"] is None
    assert "[DEMO" not in res.text
    assert [r["code"] for r in choice["reasons"]] == ["prerequisite_gap", "prerequisite_gap"]
    assert choice["reasons"][0]["params"] == {"objective": OBJ_B, "prereq": OBJ_A}
    assert "prerequisites not yet met" in choice["rationale"][0]


def test_another_cohorts_lesson_is_not_found(p: P) -> None:
    sid = _session(p)
    res = _choose(p, sid, OBJ_D)  # demo-audience lesson; this learner is in the real cohort
    assert res.status_code == 404
    assert "[DEMO" not in res.text
    # Nothing was recorded and the session still accepts a real choice.
    assert p.app.state.session_service.get_session(sid).decisions == []
    assert _choose(p, sid, OBJ_A).status_code == 200


@pytest.mark.parametrize("code", [OBJ_E, "TST-G4-UNKNOWN"])
def test_an_unpublished_or_unknown_lesson_is_not_found(p: P, code: str) -> None:
    assert _choose(p, _session(p), code).status_code == 404


def test_choosing_mid_lesson_is_a_state_conflict(p: P) -> None:
    sid = _session(p)
    assert _choose(p, sid, OBJ_A).status_code == 200
    res = _choose(p, sid, OBJ_C)  # still INTERACTING with OBJ_A
    assert res.status_code == 409


def test_another_learners_session_cannot_be_chosen_into(p: P) -> None:
    sid = _session(p)
    res = p.client.post(
        f"/v1/learning/sessions/{sid}:teach",
        json={"objective_code": OBJ_A, "learner_chosen": True},
        headers=p.other.learner,
    )
    assert res.status_code in (403, 404)


# ------------------------------------------------------------------------------- domain


def test_unmet_prerequisites_counts_mastered_and_placed_secure_as_met() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective("A").state = MasteryState.MASTERED
    k.ensure_objective("B").provenance = PriorProvenance(
        source="diagnostic", placement_id="pl", status="secure", value=0.9, uncertainty=0.1
    )
    k.ensure_objective("C").state = MasteryState.IN_PROGRESS
    assert unmet_prerequisites(k, ("A", "B", "C", "D")) == ("C", "D")
    assert unmet_prerequisites(k, ()) == ()


def test_learner_choice_is_a_teach_decision_with_an_honest_rationale() -> None:
    plain = learner_choice("X")
    assert plain.kind is DecisionKind.TEACH and plain.objective_code == "X"
    (step,) = plain.rationale
    assert step.rule_id == LEARNER_CHOICE_RULE and step.note == "You chose this lesson"
    same = learner_choice("X", recommended=Decision(DecisionKind.TEACH, "X"))
    assert same.rationale[0].note == "You chose this lesson"
    other = learner_choice(
        "X", unmet=("P",), recommended=Decision(DecisionKind.REVIEW, objective_code="Y")
    )
    note = other.rationale[0].note
    assert "suggested review Y" in note and "prerequisites not yet met: P" in note
    assert [r.code for r in other.rationale[0].reasons] == [ReasonCode.PREREQUISITE_GAP]
