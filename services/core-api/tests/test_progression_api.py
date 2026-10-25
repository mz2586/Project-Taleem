"""The path, unit checks and the academic record (PROGRESSION_AND_EXAMINATION_CONTRACT.md), end
to end on the composed app.

Covers: path states (completed vs demonstrated), unit-check assembly from the published unit
(balanced, auto-scored only, recent items avoided), sittings (start / resume / answer once /
finish / expiry -> incomplete), server-side scoring with summative evidence, remediation routing,
retake rules, the record (learner / guardian / teacher boundaries, not-accredited grade entry),
cohort isolation (a real learner never sees a demo unit), the consent gate, the kill switch and
privacy export / erasure of sittings.
"""

from __future__ import annotations

import base64
import copy
import json
import time
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.assessment import AssessmentItem
from taleem_core.contexts.curriculum_studio.domain.content import Locale, LocalizedText
from taleem_core.contexts.curriculum_studio.domain.hierarchy import (
    Chapter,
    EducationSystem,
    Grade,
    Subject,
    Topic,
)
from taleem_core.contexts.curriculum_studio.domain.lesson import Lesson
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.contexts.learning.adapters.persistence.models import (
    AssessmentEvidenceRow,
    UnitCheckSittingRow,
)
from taleem_core.contexts.learning.domain.curriculum_view import SECRET_ITEM_FIELDS
from taleem_core.contexts.privacy.domain.policy import RetainedSet
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import build_fractions_lesson
from tests.test_school_api import _SECRET, Family, _class, _family, _join, _org, _teacher
from tests.test_sync_evidence import _REVIEW_ROLES

PACK = "PK-NCP"
UNIT_FR, UNIT_MS, UNIT_DEMO = "math.u-fractions", "math.u-measure", "math.u-demo"
OBJ_A, OBJ_B, OBJ_C, OBJ_D = "TST-G4-A", "TST-G4-B", "TST-G4-C", "TST-G4-D"
DEMO_TITLE = "[DEMO · unreviewed AI draft]"


def _loc(text: str) -> LocalizedText:
    return LocalizedText(text={Locale.UR: text, Locale.EN: text})


def _hierarchy() -> EducationSystem:
    return EducationSystem(
        system_id="",
        key=PACK,
        name="",
        grades=[
            Grade(
                grade_id="",
                key="G4",
                subjects=[
                    Subject(
                        subject_id="",
                        key="math",
                        title=_loc("Mathematics"),
                        chapters=[
                            Chapter(
                                "",
                                "u-fractions",
                                _loc("Fractions"),
                                [Topic("", "t1", _loc("Parts")), Topic("", "t2", _loc("Compare"))],
                            ),
                            Chapter(
                                "",
                                "u-measure",
                                _loc("Measurement"),
                                [Topic("", "t1", _loc("Length"))],
                            ),
                            Chapter(
                                "", "u-demo", _loc("Demo unit"), [Topic("", "t1", _loc("Demo"))]
                            ),
                        ],
                    )
                ],
            )
        ],
    )


def make_lesson(
    key: str, code: str, chapter: str, topic: str, *, audience: str = "", summative: int = 8
) -> Lesson:
    """A copy of the fractions lesson, re-keyed: unique item ids, one objective, placed in a
    chapter, with ``summative`` extra auto-scored summative items (correct option 0)."""
    lesson = build_fractions_lesson()
    lesson.lesson_id = key
    lesson.learning_outcomes = [code]
    lesson.provenance.aligned_slo_codes = [code]
    lesson.ai_teaching_object.learning_goals = [code]
    lesson.metadata.chapter_key = chapter
    lesson.metadata.topic_key = topic
    lesson.metadata.audience = audience
    lesson.offline_package = f"pkg/{key}"
    for route in lesson.adaptive_remediation:
        route.remediation_ref = code
    if audience == "demo":
        for loc in (Locale.UR, Locale.EN):
            lesson.title.text[loc] = f"{DEMO_TITLE} {lesson.title.text[loc]}"
    renamed: set[int] = set()
    for item in (
        *lesson.practice_questions,
        *lesson.interactive_activities,
        *lesson.homework,
        *lesson.assessment.formative,
    ):
        if id(item) in renamed:
            continue
        renamed.add(id(item))
        item.item_id = f"{key}-{item.item_id}"
        item.objective_ref = code
    template = lesson.practice_questions[0]
    for i in range(summative):
        extra: AssessmentItem = copy.deepcopy(template)
        extra.item_id = f"{key}-s{i}"
        lesson.assessment.summative.append(extra)
    return lesson


def publish(app: FastAPI, lesson: Lesson) -> None:
    sf = app.state.studio_session_factory

    def op(fn: Any) -> None:
        with cs_uow(sf) as uow:
            fn(
                CurriculumStudioService(
                    uow.lessons, uow.publish, clock=lambda: 1000.0, hierarchy=uow.hierarchy
                )
            )
            uow.commit()

    op(lambda s: s.create(lesson))
    op(lambda s: s.submit(lesson.lesson_id, "subject_author"))
    for role in _REVIEW_ROLES:
        op(lambda s, role=role: s.review(lesson.lesson_id, ReviewAction.APPROVE, role))
    op(lambda s: s.publish(lesson.lesson_id, "curriculum_architect", "v1"))


def store_hierarchy(app: FastAPI) -> None:
    with cs_uow(app.state.studio_session_factory) as uow:
        CurriculumStudioService(uow.lessons, uow.publish, hierarchy=uow.hierarchy).upsert_hierarchy(
            PACK, _hierarchy()
        )
        uow.commit()


class Clock:
    """Real time plus a test-controlled offset (``now += …`` moves it forward), so evidence
    written by other services (on ``time.time``) stays ordered with the sittings."""

    def __init__(self) -> None:
        self.offset = 0.0

    @property
    def now(self) -> float:
        return time.time() + self.offset

    @now.setter
    def now(self, value: float) -> None:
        self.offset = value - time.time()

    def __call__(self) -> float:
        return self.now


@dataclass
class P:
    client: TestClient
    app: FastAPI
    fam: Family
    other: Family
    clock: Clock


def _sub(headers: dict[str, str]) -> str:
    token = headers["Authorization"].split(" ", 1)[1]
    body = token.split(".")[1]
    return str(json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))["sub"])


@pytest.fixture
def p() -> P:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    store_hierarchy(app)
    publish(app, make_lesson("L-A", OBJ_A, "u-fractions", "t1"))
    publish(app, make_lesson("L-B", OBJ_B, "u-fractions", "t2"))
    publish(app, make_lesson("L-C", OBJ_C, "u-measure", "t1"))
    publish(app, make_lesson("L-D", OBJ_D, "u-demo", "t1", audience="demo"))
    client = TestClient(app)
    fam = _family(client, "path@example.com")
    other = _family(client, "other-path@example.com")
    # One controllable clock for the progression service (sittings, windows, retakes).
    clock = Clock()
    app.state.progression_service._now = clock
    return P(client, app, fam, other, clock)


def _path(p: P, fam: Family | None = None) -> dict[str, Any]:
    fam = fam or p.fam
    res = p.client.get(f"/v1/learning/students/{fam.student_ref}/path", headers=fam.learner)
    assert res.status_code == 200, res.text
    return dict(res.json())


def _unit(path: dict[str, Any], unit_key: str) -> dict[str, Any] | None:
    for s in path["subjects"]:
        for u in s["units"]:
            if u["unit_key"] == unit_key:
                return dict(u)
    return None


def _practise(p: P, code: str, *, wrong: int = 0, fam: Family | None = None) -> None:
    """Answer every practice item of the lesson for ``code`` (the first ``wrong`` wrongly)."""
    fam = fam or p.fam
    sid = p.client.post(
        "/v1/learning/sessions", json={"student_ref": fam.student_ref}, headers=fam.learner
    ).json()["session_id"]
    p.client.post(f"/v1/learning/sessions/{sid}:next", headers=fam.learner)
    taught = p.client.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": code}, headers=fam.learner
    )
    assert taught.status_code == 200, taught.text
    for i, item in enumerate(taught.json()["items"]):
        res = p.client.post(
            f"/v1/learning/sessions/{sid}:answer",
            json={"objective_code": code, "item_ref": item["item_ref"], "option": int(i < wrong)},
            headers=fam.learner,
        )
        assert res.status_code == 200, res.text


def _checks(p: P, unit: str = UNIT_FR, fam: Family | None = None) -> str:
    fam = fam or p.fam
    return f"/v1/learning/students/{fam.student_ref}/units/{unit}/checks"


def _start(p: P, unit: str = UNIT_FR, fam: Family | None = None) -> Any:
    fam = fam or p.fam
    return p.client.post(_checks(p, unit, fam), headers=fam.learner)


def _rows(p: P, sitting_id: str) -> UnitCheckSittingRow:
    with p.app.state.learning_session_factory() as s:
        row = s.get(UnitCheckSittingRow, sitting_id)
        assert row is not None
        return row


def _answer(p: P, sid: str, body: dict[str, Any], unit: str = UNIT_FR) -> Any:
    return p.client.post(f"{_checks(p, unit)}/{sid}:answer", json=body, headers=p.fam.learner)


def _sit(
    p: P, start: dict[str, Any], *, wrong_objective: str | None = None, wrong: int = 0
) -> None:
    """Answer every item in the order served: option 0 is correct; items of
    ``wrong_objective`` (or the first ``wrong`` items) are answered wrongly."""
    sid = start["sitting_id"]
    objective = {i["item_ref"]: i["objective_code"] for i in _rows(p, sid).items}
    unit = start["unit_key"]
    item = start["item"]
    i = 0
    while item is not None:
        assert item["position"] == i + 1
        bad = objective[item["item_ref"]] == wrong_objective or i < wrong
        res = _answer(p, sid, {"item_ref": item["item_ref"], "option": int(bad)}, unit)
        assert res.status_code == 200, res.text
        assert set(res.json()) >= {"answered", "total", "next_item"}
        item = res.json()["next_item"]
        i += 1
    assert i == start["total"]


def _finish(p: P, sid: str, unit: str = UNIT_FR) -> Any:
    return p.client.post(f"{_checks(p, unit)}/{sid}:finish", headers=p.fam.learner)


def _record(p: P) -> dict[str, Any]:
    res = p.client.get(f"/v1/learning/students/{p.fam.student_ref}/record", headers=p.fam.learner)
    assert res.status_code == 200, res.text
    return dict(res.json())


def _secret_free(payload: Any) -> None:
    text = json.dumps(payload)
    for name in SECRET_ITEM_FIELDS:
        assert f'"{name}"' not in text, name


def _ready(p: P) -> None:
    _practise(p, OBJ_A)
    _practise(p, OBJ_B)


# ---------------------------------------------------------------------------------- path


def test_path_lists_units_and_lessons_with_distinct_completed_and_demonstrated(p: P) -> None:
    path = _path(p)
    assert path["grade"] == 4 and path["grade_state"] == "not_started"
    (math,) = path["subjects"]
    assert [u["unit_key"] for u in math["units"]] == [UNIT_FR, UNIT_MS]
    fr = _unit(path, UNIT_FR)
    assert fr is not None and fr["title"]["en"] == "Fractions" and fr["state"] == "not_started"
    assert [lesson["lesson_id"] for lesson in fr["lessons"]] == ["L-A", "L-B"]
    check = fr["check"]
    assert check["item_count"] == 10 and check["pass_mark"] == 70
    assert check["available"] is False and check["best_score"] is None
    assert path["next_step"]["kind"] == "lesson" and path["next_step"]["unit_key"] == UNIT_FR
    assert path["next_step"]["lesson_id"] == "L-A"

    _practise(p, OBJ_A, wrong=6)  # practised (every item answered), but not mastered
    fr = _unit(_path(p), UNIT_FR)
    assert fr is not None
    lesson_a = fr["lessons"][0]
    assert lesson_a["state"] == "practised"
    assert lesson_a["completed"] is True and lesson_a["demonstrated"] is False
    assert fr["state"] == "in_progress"
    assert _path(p)["next_step"]["lesson_id"] == "L-B"

    _practise(p, OBJ_B)
    path = _path(p)
    fr = _unit(path, UNIT_FR)
    assert fr is not None and fr["state"] == "ready_for_check" and fr["check"]["available"]
    assert path["next_step"]["kind"] == "unit_check"
    assert path["next_step"]["unit_key"] == UNIT_FR and path["next_step"]["title"]["en"]


def test_real_learner_never_sees_a_demo_unit_and_cannot_sit_one(p: P) -> None:
    path = _path(p)
    assert _unit(path, UNIT_DEMO) is None
    assert DEMO_TITLE not in json.dumps(path)
    refused = _start(p, UNIT_DEMO)
    assert refused.status_code == 404 and refused.json()["code"] == "UNIT_NOT_FOUND"


def test_demo_learner_sees_the_demo_unit(p: P) -> None:
    demo = _family(p.client, "demo-path@example.org")
    p.app.state.identity_service.assign_family_cohort(
        guardian_ref=_sub(demo.guardian), cohort="demo"
    )
    unit = _unit(_path(p, demo), UNIT_DEMO)
    assert unit is not None and unit["lessons"][0]["lesson_id"] == "L-D"


def test_path_is_owner_only(p: P) -> None:
    url = f"/v1/learning/students/{p.fam.student_ref}/path"
    assert p.client.get(url, headers=p.other.learner).status_code == 403
    assert p.client.get(url, headers=p.fam.guardian).status_code == 403


# --------------------------------------------------------------------------- unit checks


def test_unit_check_requires_practice_first(p: P) -> None:
    _practise(p, OBJ_A)
    res = _start(p)
    assert res.status_code == 409 and res.json()["code"] == "UNIT_NOT_READY"


def test_sitting_paper_is_balanced_auto_scored_fresh_and_keyless(p: P) -> None:
    _ready(p)
    started = _start(p)
    assert started.status_code == 201, started.text
    view = started.json()
    assert view["unit_key"] == UNIT_FR and view["total"] == 10 and view["answered"] == 0
    assert view["expires_at"] - view["started_at"] == pytest.approx(24 * 3600)
    item = view["item"]
    assert set(item) >= {"item_ref", "kind", "prompt", "options", "left_count"}
    assert "hint_count" not in item
    _secret_free(view)
    items = _rows(p, view["sitting_id"]).items
    per_objective = {
        code: sum(1 for i in items if i["objective_code"] == code) for code in (OBJ_A, OBJ_B)
    }
    assert per_objective == {OBJ_A: 5, OBJ_B: 5}
    # Every practice item was just answered (recent), so the paper uses the fresh summative pool.
    assert all("-s" in i["item_ref"] for i in items)
    assert {i["lesson_id"] for i in items} == {"L-A", "L-B"}
    assert all(i["lesson_version"] == 1 for i in items)
    assert item["item_ref"] == items[0]["item_ref"]


def test_a_sitting_resumes_answers_once_and_scores_on_the_server(p: P) -> None:
    _ready(p)
    start = _start(p).json()
    sid = start["sitting_id"]
    again = _start(p)
    assert again.status_code == 200 and again.json()["sitting_id"] == sid
    resumed = p.client.get(f"{_checks(p)}/{sid}", headers=p.fam.learner)
    assert resumed.status_code == 200 and resumed.json()["item"] == start["item"]

    first = start["item"]["item_ref"]
    one = _answer(p, sid, {"item_ref": first, "option": 0})
    assert one.status_code == 200 and one.json()["duplicate"] is False
    assert one.json()["answered"] == 1 and one.json()["next_item"]["position"] == 2
    assert "outcome" not in one.json() and "correct" not in one.json()
    _secret_free(one.json())
    two = _answer(p, sid, {"item_ref": first, "option": 1})  # a changed answer is not taken
    assert two.status_code == 200 and two.json()["duplicate"] is True
    assert two.json()["answered"] == 1
    with p.app.state.learning_session_factory() as s:
        rows = s.scalars(
            select(AssessmentEvidenceRow).where(AssessmentEvidenceRow.session_id == sid)
        ).all()
    (ev,) = rows
    assert ev.context == "summative" and ev.outcome == "correct"
    paper = _rows(p, sid)
    assert ev.lesson_id == paper.items[0]["lesson_id"] and ev.lesson_version == 1
    assert paper.answers[first]["evidence_id"] == ev.id
    # Resuming after an answer serves the next unanswered item.
    resumed = p.client.get(f"{_checks(p)}/{sid}", headers=p.fam.learner).json()
    assert resumed["answered"] == 1 and resumed["item"]["item_ref"] == paper.items[1]["item_ref"]

    mismatch = _answer(p, sid, {"item_ref": paper.items[1]["item_ref"], "text": "1/4"})
    assert mismatch.status_code == 422
    assert _answer(p, sid, {"item_ref": "nope", "option": 0}).status_code == 404
    early = _finish(p, sid)
    assert early.status_code == 409 and early.json()["code"] == "SITTING_UNANSWERED"
    # A sitting is reached only under its own unit.
    wrong_unit = p.client.get(f"{_checks(p, UNIT_MS)}/{sid}", headers=p.fam.learner)
    assert wrong_unit.status_code == 404


def test_passing_completes_the_unit_and_the_record_shows_it(p: P) -> None:
    _ready(p)
    start = _start(p).json()
    sid = start["sitting_id"]
    _sit(p, start, wrong=2)  # 8 / 10 = 80% >= 70%
    done = _finish(p, sid)
    assert done.status_code == 200, done.text
    result = done.json()
    assert result["score_percent"] == 80.0 and result["passed"] is True
    assert result["pass_mark"] == 70 and result["remediation"] == []
    assert {r["objective_code"] for r in result["per_objective"]} == {OBJ_A, OBJ_B}
    assert sum(r["total"] for r in result["per_objective"]) == 10
    assert sum(r["correct"] for r in result["per_objective"]) == 8
    assert all(r["title"]["en"] for r in result["per_objective"])
    again = _finish(p, sid).json()  # idempotent, reproducible
    assert (again["score_percent"], again["per_objective"]) == (80.0, result["per_objective"])
    with p.app.state.learning_session_factory() as s:
        n = s.scalar(
            select(func.count())
            .select_from(AssessmentEvidenceRow)
            .where(AssessmentEvidenceRow.session_id == sid)
        )
    assert n == 10
    late = _answer(p, sid, {"item_ref": _rows(p, sid).items[0]["item_ref"], "option": 0})
    assert late.json()["duplicate"] is True

    fr = _unit(_path(p), UNIT_FR)
    assert fr is not None and fr["state"] == "completed"
    assert fr["check"]["best_score"] == 80.0 and fr["check"]["passed"] is True
    assert fr["check"]["last_sitting_id"] == sid and fr["check"]["open_sitting_id"] is None
    record = _record(p)
    (sitting,) = record["sittings"]
    assert sitting["sitting_id"] == sid and sitting["state"] == "finished"
    assert sitting["unit_key"] == UNIT_FR and sitting["score_percent"] == 80.0
    assert sitting["passed"] is True and len(sitting["per_objective"]) == 2
    assert record["grade"] == 4 and record["grade_completion"] is None
    units = {u["unit_key"]: u for u in record["subjects"][0]["units"]}
    assert units[UNIT_FR]["state"] == "completed" and units[UNIT_FR]["sittings"] == [sid]
    assert units[UNIT_FR]["best_score"] == 80.0
    assert units[UNIT_MS]["state"] == "not_started" and units[UNIT_MS]["best_score"] is None


def test_failing_routes_to_remediation_and_gates_the_retake(p: P) -> None:
    _ready(p)
    start = _start(p).json()
    sid = start["sitting_id"]
    _sit(p, start, wrong_objective=OBJ_B)  # 5 / 10 = 50%
    done = _finish(p, sid).json()
    assert done["passed"] is False and done["score_percent"] == 50.0
    (remedy,) = done["remediation"]
    assert remedy["objective_code"] == OBJ_B and remedy["lesson_id"] == "L-B"
    assert remedy["title"]["en"]
    assert done["can_retake"] is False and done["retake_after"] is not None
    path = _path(p)
    assert path["next_step"]["kind"] == "lesson" and path["next_step"]["lesson_id"] == "L-B"
    fr = _unit(path, UNIT_FR)
    assert fr is not None and fr["check"]["can_retake"] is False
    assert fr["check"]["retake_after"] == done["retake_after"]
    refused = _start(p)
    assert refused.status_code == 429 and refused.json()["code"] == "RETAKE_NOT_YET"
    assert refused.json()["retake_after"] == done["retake_after"]

    _practise(p, OBJ_B)  # remediation on the missed objective
    assert _unit(_path(p), UNIT_FR)["check"]["can_retake"] is True  # type: ignore[index]
    retake = _start(p)
    assert retake.status_code == 201, retake.text
    assert retake.json()["sitting_id"] != sid
    # A retake is not the same paper: the first paper's items are avoided while the pool allows.
    first = {i["item_ref"] for i in _rows(p, sid).items}
    second = {i["item_ref"] for i in _rows(p, retake.json()["sitting_id"]).items}
    summative = {f"L-{x}-s{i}" for x in "AB" for i in range(8)}
    assert summative - first <= second  # all 6 never-seen items, then 4 seen ones
    assert len(second - (summative - first)) == 4


def test_a_retake_is_allowed_after_24_hours_without_remediation(p: P) -> None:
    _ready(p)
    start = _start(p).json()
    _sit(p, start, wrong_objective=OBJ_B)
    _finish(p, start["sitting_id"])
    assert _start(p).status_code == 429
    p.clock.now += 24 * 3600 + 1
    assert _start(p).status_code == 201


def test_an_unfinished_sitting_expires_as_incomplete_never_failed(p: P) -> None:
    _ready(p)
    start = _start(p).json()
    sid = start["sitting_id"]
    _answer(p, sid, {"item_ref": start["item"]["item_ref"], "option": 0})
    p.clock.now += 23 * 3600  # still resumable
    assert _start(p).json()["sitting_id"] == sid
    p.clock.now += 3600 + 1
    gone = p.client.get(f"{_checks(p)}/{sid}", headers=p.fam.learner)
    assert gone.status_code == 410 and gone.json()["code"] == "SITTING_EXPIRED"
    assert _rows(p, sid).status == "incomplete"
    second = _rows(p, sid).items[1]["item_ref"]
    late = _answer(p, sid, {"item_ref": second, "option": 0})
    assert late.status_code == 410 and late.json()["code"] == "SITTING_EXPIRED"
    assert _finish(p, sid).status_code == 410
    # Incomplete is not a result: the unit is not completed, and a new sitting may start now.
    assert _unit(_path(p), UNIT_FR)["state"] == "ready_for_check"  # type: ignore[index]
    (listed,) = _record(p)["sittings"]
    assert listed["state"] == "incomplete" and listed["passed"] is None
    fresh = _start(p)
    assert fresh.status_code == 201 and fresh.json()["sitting_id"] != sid


def test_sittings_are_owner_only(p: P) -> None:
    _ready(p)
    sid = _start(p).json()["sitting_id"]
    own = _checks(p)
    assert p.client.get(f"{own}/{sid}", headers=p.other.learner).status_code == 403
    assert p.client.get(f"{own}/{sid}", headers=p.fam.guardian).status_code == 403
    assert p.client.post(own, headers=p.other.learner).status_code == 403
    # Another learner under their own ref cannot reach this sitting either.
    theirs = _checks(p, UNIT_FR, p.other)
    assert p.client.get(f"{theirs}/{sid}", headers=p.other.learner).status_code == 404
    assert p.client.post(f"{theirs}/{sid}:finish", headers=p.other.learner).status_code == 404
    assert p.client.get(f"{own}/ucs_missing", headers=p.fam.learner).status_code == 404


def test_grade_completion_is_a_not_accredited_record_entry(p: P) -> None:
    for code in (OBJ_A, OBJ_B, OBJ_C):
        _practise(p, code)
    for unit in (UNIT_FR, UNIT_MS):
        start = _start(p, unit).json()
        _sit(p, start)
        assert _finish(p, start["sitting_id"], unit).json()["passed"] is True
    path = _path(p)
    assert path["grade_state"] == "completed" and path["next_step"] is None
    record = p.client.get(
        f"/v1/guardian/children/{p.fam.student_ref}/record", headers=p.fam.guardian
    ).json()
    completion = record["grade_completion"]
    assert completion["grade"] == 4 and completion["accredited"] is False
    assert (
        completion["label"]["en"] == "Grade 4 completed in Taleem — not an accredited certificate"
    )
    assert completion["completed_at"] == max(s["finished_at"] for s in record["sittings"])


# -------------------------------------------------------------------------------- record


def test_record_access_boundaries(p: P) -> None:
    ref = p.fam.student_ref
    learner_url = f"/v1/learning/students/{ref}/record"
    guardian_url = f"/v1/guardian/children/{ref}/record"
    own = p.client.get(learner_url, headers=p.fam.learner)
    assert own.status_code == 200 and own.json()["student_ref"] == ref
    assert "derived_at" in own.json() and own.json()["report_cards"] == []
    assert p.client.get(guardian_url, headers=p.fam.guardian).status_code == 200
    assert p.client.get(guardian_url, headers=p.other.guardian).status_code == 404
    assert p.client.get(learner_url, headers=p.other.learner).status_code == 403
    assert p.client.get(guardian_url, headers=p.fam.learner).status_code == 404
    # A teacher: only a learner in their own class (who shares progress).
    org = _org(p.client, "School P")
    teacher = _teacher(p.client, org, "t@school-p.example")
    stranger = _teacher(p.client, org, "s@school-p.example")
    klass = _class(p.client, teacher, "Grade 4 Green")
    assert _join(p.client, p.fam, klass["join_code"]) == 200
    assert p.client.get(learner_url, headers=teacher).status_code == 200
    assert p.client.get(learner_url, headers=stranger).status_code == 404
    other_url = f"/v1/learning/students/{p.other.student_ref}/record"
    assert p.client.get(other_url, headers=teacher).status_code == 404
    assert p.client.get(guardian_url, headers=teacher).status_code == 404
    assert p.client.get(f"/v1/learning/students/{ref}/path", headers=teacher).status_code == 403


def test_record_lists_mastered_objectives_and_report_cards(p: P) -> None:
    for _ in range(3):
        _practise(p, OBJ_A)
    mastered = {m["objective_code"] for m in _record(p)["lessons_mastered"]}
    lesson_a = _unit(_path(p), UNIT_FR)["lessons"][0]  # type: ignore[index]
    assert (OBJ_A in mastered) == lesson_a["demonstrated"]
    assert (lesson_a["state"] == "mastered") == lesson_a["demonstrated"]
    end = int(p.clock.now) - 1
    card = p.client.post(
        f"/v1/reporting/children/{p.fam.student_ref}/report-cards:generate",
        json={"period_start": end - 3600, "period_end": end},
        headers=p.fam.guardian,
    )
    assert card.status_code == 201, card.text
    (link,) = _record(p)["report_cards"]
    assert link["card_id"] == card.json()["card_id"]
    assert set(link) >= {"card_id", "period_start", "period_end", "issued_at"}


def test_consent_withdrawal_closes_the_learner_routes(p: P) -> None:
    _ready(p)
    sid = _start(p).json()["sitting_id"]
    withdrawn = p.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": p.fam.student_ref},
        headers=p.fam.guardian,
    )
    assert withdrawn.status_code == 200
    ref = p.fam.student_ref
    h = p.fam.learner
    assert p.client.get(f"/v1/learning/students/{ref}/path", headers=h).status_code == 403
    assert _start(p).status_code == 403
    assert p.client.get(f"{_checks(p)}/{sid}", headers=h).status_code == 403
    assert p.client.get(f"/v1/learning/students/{ref}/record", headers=h).status_code == 403


def test_kill_switch_covers_the_learner_routes_not_the_guardian_record(p: P) -> None:
    from taleem_core.platform.kill_switch import is_child_facing

    ref = p.fam.student_ref
    assert is_child_facing(f"/v1/learning/students/{ref}/units/{UNIT_FR}/checks")
    assert is_child_facing(f"/v1/learning/students/{ref}/path")
    assert not is_child_facing(f"/v1/guardian/children/{ref}/record")


# ------------------------------------------------------------------------------- privacy


def test_privacy_export_and_erasure_cover_sittings(p: P) -> None:
    _ready(p)
    sid = _start(p).json()["sitting_id"]
    privacy = p.app.state.privacy_service
    learning = next(s for s in privacy._stores if s.name == "learning")
    assert "learning.unit_check_sitting" in learning.covers()
    exported = learning.export(p.fam.student_ref)
    (row,) = exported["unit_check_sittings"]
    assert row["sitting_id"] == sid
    _secret_free(exported["unit_check_sittings"])
    assert learning.remaining(p.fam.student_ref)["unit_check_sitting"] == 1
    erased = learning.erase(p.fam.student_ref, RetainedSet())
    assert erased["unit_check_sitting"] == 1
    assert learning.remaining(p.fam.student_ref)["unit_check_sitting"] == 0
