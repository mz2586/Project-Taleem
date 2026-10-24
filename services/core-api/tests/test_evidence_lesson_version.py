"""Every evidence path records the lesson id + published version answered against (migration 0015).

REPORT_CARD_CONTRACT §1: a report card cites the exact lesson version the work was done on, so the
evidence itself must say which it was. One test per creation path on the composed app (SQLite):
live session ``:answer``, diagnostic placement answers, offline sync ``attempt.submitted`` (the
version comes from the device's package; absent or malformed, it is NULL, never the current one),
a teacher's homework mark, and the version pin a report card then derives across a republish. The
vertical-slice runner is covered in ``test_vertical_slice.py``; the domain/mapper defaults here.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import WorkflowState
from taleem_core.contexts.learning.adapters.persistence import mapper
from taleem_core.contexts.learning.adapters.persistence.models import AssessmentEvidenceRow
from taleem_core.contexts.learning.domain.knowledge import AssessmentEvidence
from taleem_core.contexts.learning.domain.values import InteractionContext, Outcome
from taleem_core.platform.ids import uuid7
from taleem_core.vertical_slice.fractions_lesson import LESSON_KEY, OBJECTIVE_CODE
from tests.test_placement import _answer as _placement_answer
from tests.test_placement import _app as _placement_app
from tests.test_placement import _h as _placement_h
from tests.test_reporting_api import (
    R,
    _attempts,
    _closed_now,
    _generate,
    _marked_homework,
    make_world,
)
from tests.test_sync_evidence import _attempt_delta


@pytest.fixture
def r() -> R:
    return make_world()


def _pins(app: FastAPI, student_ref: str) -> list[tuple[str, str | None, int | None]]:
    """(context, lesson_id, lesson_version) of every stored evidence row, in time order."""
    with app.state.learning_session_factory() as s:
        rows = s.scalars(
            select(AssessmentEvidenceRow)
            .where(AssessmentEvidenceRow.student_ref == student_ref)
            .order_by(AssessmentEvidenceRow.occurred_at)
        ).all()
    return [(row.context, row.lesson_id, row.lesson_version) for row in rows]


def _republish(app: FastAPI) -> int:
    """Publish the fixture lesson again (its next version) and return the new version number.

    The studio workflow has no published -> approved edge (an edit is a new draft lesson in the
    product), so the test puts the stored lesson back to ``approved`` and publishes it again.
    """
    sf = app.state.studio_session_factory
    with cs_uow(sf) as uow:
        lesson = uow.lessons.get(LESSON_KEY)
        assert lesson is not None
        lesson.workflow.state = WorkflowState.APPROVED
        uow.lessons.save(lesson)
        uow.commit()
    with cs_uow(sf) as uow:
        svc = CurriculumStudioService(uow.lessons, uow.publish, clock=lambda: 2000.0)
        published = svc.publish(LESSON_KEY, "curriculum_architect", "v2")
        uow.commit()
    return published.version


# ----------------------------------------------------------------------- domain + mapping


def test_old_constructors_still_work_and_the_mapper_round_trips_null() -> None:
    old = AssessmentEvidence(
        "e1", "stu", "OBJ", "i1", "", Outcome.CORRECT, InteractionContext.PRACTICE, (), 0, 0,
        0.1, 0.2, 1.0,
    )  # fmt: skip
    assert (old.lesson_id, old.lesson_version) == ("", None)
    cols = mapper.evidence_column_values(old)
    assert (cols["lesson_id"], cols["lesson_version"]) == (None, None)  # NULL, never ""
    back = mapper.evidence_from_row(AssessmentEvidenceRow(**cols))
    assert back == old
    pinned = AssessmentEvidence(**{**old.__dict__, "lesson_id": "L-1", "lesson_version": 4})
    back = mapper.evidence_from_row(AssessmentEvidenceRow(**mapper.evidence_column_values(pinned)))
    assert (back.lesson_id, back.lesson_version) == ("L-1", 4)


# --------------------------------------------------------------------------- live session


def test_live_session_answer_records_the_taught_lesson_and_version(r: R) -> None:
    h = r.loner.learner
    ref = r.loner.student_ref
    sid = r.client.post("/v1/learning/sessions", json={"student_ref": ref}, headers=h).json()[
        "session_id"
    ]
    assert r.client.post(f"/v1/learning/sessions/{sid}:next", headers=h).status_code == 200
    taught = r.client.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h
    )
    assert taught.status_code == 200, taught.text
    item = taught.json()["items"][0]["item_ref"]
    answered = r.client.post(
        f"/v1/learning/sessions/{sid}:answer",
        json={"objective_code": OBJECTIVE_CODE, "item_ref": item, "option": 0, "hints_used": 0},
        headers=h,
    )
    assert answered.status_code == 200, answered.text
    assert _pins(r.app, ref) == [("practice", LESSON_KEY, 1)]

    # After a republish the next answer names the version it was answered against (v2), and
    # the earlier row keeps v1: evidence is immutable.
    assert _republish(r.app) == 2
    again = r.client.post(
        f"/v1/learning/sessions/{sid}:answer",
        json={"objective_code": OBJECTIVE_CODE, "item_ref": item, "option": 0, "hints_used": 0},
        headers=h,
    )
    assert again.status_code == 200, again.text
    assert _pins(r.app, ref) == [("practice", LESSON_KEY, 1), ("practice", LESSON_KEY, 2)]


# ------------------------------------------------------------------------------ placement


def test_placement_answers_record_the_lesson_the_question_came_from() -> None:
    app, client = _placement_app()
    ref = "pl-version"
    first = client.get(
        f"/v1/learning/students/{ref}/placement", headers=_placement_h("student", ref)
    ).json()
    one = _placement_answer(client, ref, first["next_item"]["item_ref"], 1)
    assert one.status_code == 200, one.text  # type: ignore[attr-defined]
    assert _pins(app, ref) == [("diagnostic", LESSON_KEY, 1)]


# ----------------------------------------------------------------------------- offline sync


def _sync(r: R, deltas: list[dict[str, Any]]) -> list[str]:
    res = r.client.post(
        "/v1/sync/batch", json={"cursor": 0, "deltas": deltas}, headers=r.loner.learner
    )
    assert res.status_code == 200, res.text
    return [row["status"] for row in res.json()["results"]]


def _delta(r: R, seq: int, **payload: Any) -> dict[str, Any]:
    delta = _attempt_delta(
        student=r.loner.student_ref,
        item_ref="p1-one-of-four",
        option=0,
        client_event_id=uuid7(),
        evidence_id=uuid7(),
        client_seq=seq,
    )
    delta["payload"].update(payload)  # type: ignore[union-attr]
    return delta


def test_offline_package_carries_the_version_and_sync_records_what_the_device_sent(r: R) -> None:
    manifest = next(
        p
        for p in r.client.get("/v1/offline/packages", headers=r.loner.learner).json()["packages"]
        if p["lesson_id"] == LESSON_KEY
    )
    assert manifest["lesson_version"] == 1  # what the device will echo back

    statuses = _sync(
        r,
        [
            _delta(r, 1, lesson_version=manifest["lesson_version"]),  # from the package
            _delta(r, 2),  # a client that sends no version
            _delta(r, 3, lesson_version=True),  # malformed: not a version
            _delta(r, 4, lesson_version=0),  # malformed: versions start at 1
            _delta(r, 5, lesson_version="1"),  # malformed: not an integer
            _delta(r, 6, lesson_version=1, lesson_id="L-some-other-lesson"),  # another lesson's
        ],
    )
    assert statuses == ["applied"] * 6
    pins = _pins(r.app, r.loner.student_ref)
    assert pins[0] == ("practice", LESSON_KEY, 1)
    # Absent / malformed / another lesson's version: NULL, never the version published now.
    assert pins[1:] == [("practice", LESSON_KEY, None)] * 5


def test_sync_after_a_republish_keeps_the_packaged_version(r: R) -> None:
    assert _republish(r.app) == 2
    # The device still holds the v1 package: its attempt is recorded against v1, not v2.
    assert _sync(r, [_delta(r, 1, lesson_version=1)]) == ["applied"]
    assert _pins(r.app, r.loner.student_ref) == [("practice", LESSON_KEY, 1)]
    manifest = r.client.get(f"/v1/offline/packages/{LESSON_KEY}", headers=r.loner.learner)
    assert manifest.status_code == 200 and manifest.json()["manifest"]["lesson_version"] == 2


# ------------------------------------------------------------------------- homework marking


def test_a_teacher_mark_records_the_lesson_and_version_of_the_written_item(r: R) -> None:
    sub = _marked_homework(r)
    with r.app.state.learning_session_factory() as s:
        row = s.get(AssessmentEvidenceRow, sub)
    assert row is not None and (row.lesson_id, row.lesson_version) == (LESSON_KEY, 1)


def test_a_mark_for_an_item_no_longer_published_records_no_lesson() -> None:
    from taleem_core.contexts.learning.application.written_work import WrittenWorkService
    from taleem_core.contexts.learning.domain.curriculum_view import LessonView

    calls: list[dict[str, Any]] = []

    class _Knowledge:
        def record_human_graded(self, **kw: Any) -> bool:
            calls.append(kw)
            return True

    class _Curriculum:
        def lesson_for(self, code: str) -> LessonView | None:
            return LessonView("L-1", code, {}, {}, version=3) if code == "OBJ" else None

    svc = WrittenWorkService(_Curriculum(), _Knowledge())  # type: ignore[arg-type]
    for code in ("OBJ", "GONE"):  # the item is not in L-1 v3 / no lesson is published at all
        svc.record_marked(
            submission_id="sub_1", student_ref="s", objective_code=code, item_ref="w", met=True
        )
    assert [(c["lesson_id"], c["lesson_version"]) for c in calls] == [("", None), ("", None)]


# --------------------------------------------------------------------- the derived card pin


def test_a_card_pins_the_versions_the_work_was_done_on_across_a_republish(r: R) -> None:
    _attempts(r, r.loner, 2, lesson_version=1)
    assert _republish(r.app) == 2  # published at issue time: v2; the work was done on v1
    end = _closed_now()
    card = _generate(r, r.loner, end).json()
    (obj,) = card["subjects"][0]["objectives"]
    assert card["derivation"] == "taleem.reporting.derive/2"
    assert (obj["lesson_id"], obj["lesson_version"], obj["lesson_versions"]) == (LESSON_KEY, 1, [1])
    assert obj["version_source"] == "evidence" and obj["unversioned_evidence"] == 0


def test_a_card_says_when_versions_were_not_recorded(r: R) -> None:
    _attempts(r, r.loner, 1, lesson_version=1)
    _attempts(r, r.loner, 1, lesson_version=None)  # an old client: no version sent
    card = _generate(r, r.loner, _closed_now()).json()
    (obj,) = card["subjects"][0]["objectives"]
    assert (obj["lesson_version"], obj["lesson_versions"], obj["version_source"]) == (
        None,
        [1],
        "mixed",
    )
    assert obj["unversioned_evidence"] == 1
