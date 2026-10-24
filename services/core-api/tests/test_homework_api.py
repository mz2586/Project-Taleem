"""Homework + marking (HOMEWORK_AND_MARKING_CONTRACT.md), end to end on the composed app.

A published lesson carries written items (short / long with a rubric / word problem / interactive
short). A learner lists and submits homework; the teacher queues, returns and marks it; the mark
becomes ONE mastery evidence. Also: the live consent gate, tenant + class isolation, secrecy of
the marking aids, refs-only audit, the teacher safeguarding hook, and privacy export / erasure.
"""

from __future__ import annotations

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
from taleem_core.contexts.curriculum_studio.domain.assessment import (
    AssessmentItem,
    Competency,
    ItemType,
    Rubric,
    RubricLevel,
)
from taleem_core.contexts.curriculum_studio.domain.content import Hint, Locale, LocalizedText
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.contexts.learning.adapters.persistence.models import (
    AssessmentEvidenceRow,
    ObjectiveMasteryRow,
)
from taleem_core.contexts.safeguarding.adapters.persistence.models import ConcernRow
from taleem_core.contexts.school.adapters.persistence.models import SchoolAuditRow, SubmissionRow
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)
from tests.test_school_api import (
    _SECRET,
    Family,
    _class,
    _family,
    _join,
    _org,
    _teacher,
    _token,
)
from tests.test_sync_evidence import _REVIEW_ROLES

SAMPLE = "SECRET-SAMPLE one half"
GUIDANCE = "SECRET-GUIDANCE accept any fair share"
CRITERIA = "SECRET-CRITERIA explains equal parts"
CHILD_TEXT = "Ammi cut the roti into 4 equal parts and I ate one"


def _loc(en: str, ur: str = "") -> LocalizedText:
    return LocalizedText(text={Locale.UR: ur or f"ur:{en}", Locale.EN: en})


def _written(
    item_id: str, kind: ItemType, *, rubric: Rubric | None = None, key: dict[str, object]
) -> AssessmentItem:
    return AssessmentItem(
        item_id=item_id,
        type=kind,
        objective_ref=OBJECTIVE_CODE,
        competency=Competency.APPLICATION,
        stem=_loc(f"Explain {item_id}"),
        answer_key=key,
        rubric=rubric,
        hints=[Hint(trigger="stuck", hint=_loc("Think of equal parts."))],
    )


def _rubric() -> Rubric:
    return Rubric(
        criteria=CRITERIA,
        max_score=3,
        levels=[RubricLevel(level=n, descriptor=_loc(f"level {n}")) for n in (1, 2, 3)],
    )


def publish_written_lesson(app: FastAPI) -> None:
    """The fractions lesson plus written items in homework, challenges and activities."""
    lesson = build_fractions_lesson()
    lesson.homework.append(
        _written("hw-short", ItemType.SHORT, key={"sample_answer": SAMPLE}),
    )
    lesson.homework.append(
        _written("hw-long", ItemType.LONG, rubric=_rubric(), key={"guidance": GUIDANCE})
    )
    lesson.challenge_problems.append(
        _written("ch-word", ItemType.WORD_PROBLEM, rubric=_rubric(), key={})
    )
    lesson.interactive_activities.append(_written("act-short", ItemType.SHORT, key={}))
    sf = app.state.studio_session_factory

    def op(fn: Any) -> None:
        with cs_uow(sf) as uow:
            fn(CurriculumStudioService(uow.lessons, uow.publish, clock=lambda: 1000.0))
            uow.commit()

    op(lambda s: s.create(lesson))
    op(lambda s: s.submit(LESSON_KEY, "subject_author"))
    for role in _REVIEW_ROLES:
        op(lambda s, role=role: s.review(LESSON_KEY, ReviewAction.APPROVE, role))
    op(lambda s: s.publish(LESSON_KEY, "curriculum_architect", "v1"))


@dataclass
class W:
    client: TestClient
    app: FastAPI
    teacher_a: dict[str, str]
    teacher_a2: dict[str, str]
    teacher_b: dict[str, str]
    class_a: str
    class_a2: str
    assignment: str
    fam: Family


@pytest.fixture
def w() -> W:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish_written_lesson(app)
    client = TestClient(app)
    org_a, org_b = _org(client, "School A"), _org(client, "School B", "GB")
    ta = _teacher(client, org_a, "a1@school-a.example")
    ta2 = _teacher(client, org_a, "a2@school-a.example")
    tb = _teacher(client, org_b, "b1@school-b.example")
    class_a = _class(client, ta, "Grade 4 Blue")
    class_a2 = _class(client, ta2, "Grade 4 Green")
    fam = _family(client, "parent@example.com")
    assert _join(client, fam, class_a["join_code"]) == 200
    r = client.post(
        f"/v1/school/classes/{class_a['class_id']}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 86400},
        headers=ta,
    )
    assert r.status_code == 201, r.text
    return W(
        client,
        app,
        ta,
        ta2,
        tb,
        str(class_a["class_id"]),
        str(class_a2["class_id"]),
        str(r.json()["assignment_id"]),
        fam,
    )


def _hw(w: W, fam: Family | None = None) -> Any:
    f = fam or w.fam
    return w.client.get(f"/v1/school/learners/{f.student_ref}/homework", headers=f.learner)


def _submit(w: W, item: str, text: str = CHILD_TEXT, assignment: str | None = None) -> Any:
    return w.client.post(
        f"/v1/school/learners/{w.fam.student_ref}/homework/"
        f"{assignment or w.assignment}/items/{item}:submit",
        json={"text": text},
        headers=w.fam.learner,
    )


def _queue(w: W, status: str = "submitted", teacher: dict[str, str] | None = None) -> Any:
    return w.client.get(
        f"/v1/school/classes/{w.class_a}/submissions",
        params={"status": status},
        headers=teacher or w.teacher_a,
    )


def _mark(w: W, sub: str, body: dict[str, object], teacher: dict[str, str] | None = None) -> Any:
    return w.client.post(
        f"/v1/school/submissions/{sub}:mark", json=body, headers=teacher or w.teacher_a
    )


def _evidence(w: W, sub: str) -> int:
    with w.app.state.learning_session_factory() as s:
        return int(
            s.scalar(
                select(func.count())
                .select_from(AssessmentEvidenceRow)
                .where(AssessmentEvidenceRow.id == sub)
            )
            or 0
        )


def _attempts(w: W) -> int:
    with w.app.state.learning_session_factory() as s:
        row = s.scalars(
            select(ObjectiveMasteryRow).where(
                ObjectiveMasteryRow.student_ref == w.fam.student_ref,
                ObjectiveMasteryRow.objective_code == OBJECTIVE_CODE,
            )
        ).first()
        return int(row.attempts) if row is not None else 0


# ------------------------------------------------------------------------------ the journey


def test_learner_lists_written_items_without_any_marking_aid(w: W) -> None:
    r = _hw(w)
    assert r.status_code == 200, r.text
    (assignment,) = r.json()["assignments"]
    assert assignment["assignment_id"] == w.assignment
    assert assignment["objective_code"] == OBJECTIVE_CODE
    assert assignment["class_name"] == "Grade 4 Blue"
    assert assignment["lesson_title"]["en"]
    items = {i["item_ref"]: i for i in assignment["items"]}
    assert list(items) == ["hw-short", "hw-long", "ch-word", "act-short"]
    assert items["hw-short"]["max_chars"] == 200 and items["hw-long"]["max_chars"] == 2000
    assert items["hw-short"]["kind"] == "written"
    assert items["hw-short"]["hints"] == ["Think of equal parts."]
    assert all(i["state"] == "not_started" and i["submission"] is None for i in items.values())
    for secret in (SAMPLE, GUIDANCE, CRITERIA, '"rubric"', '"sample_answer"', '"guidance"'):
        assert secret not in r.text


def test_submit_return_resubmit_mark_records_one_evidence(w: W) -> None:
    r = _submit(w, "hw-long", "  first try  ")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "submitted" and body["submission"]["text"] == "first try"
    assert body["submission"]["state"] == "submitted"
    sub = body["submission"]["submission_id"]
    assert SAMPLE not in r.text and CRITERIA not in r.text

    rows = _queue(w).json()["submissions"]
    assert [x["submission_id"] for x in rows] == [sub]
    row = rows[0]
    assert row["learner_display_name"] == "Zara" and row["student_ref"] == w.fam.student_ref
    assert row["text"] == "first try" and row["state"] == "submitted"
    assert row["rubric"]["max_score"] == 3 and row["rubric"]["criteria"] == CRITERIA
    assert row["rubric"]["levels"][0] == {
        "score": 1,
        "label": "1",
        "descriptor": {"ur": "ur:level 1", "en": "level 1"},
    }
    assert row["guidance"] == GUIDANCE and row["sample_answer"] is None
    assert row["lesson_title"]["en"] and row["prompt"]["en"] == "Explain hw-long"

    back = w.client.post(
        f"/v1/school/submissions/{sub}:return",
        json={"feedback": "Say why the parts are equal."},
        headers=w.teacher_a,
    )
    assert back.status_code == 200 and back.json()["state"] == "returned"
    again = w.client.post(
        f"/v1/school/submissions/{sub}:return", json={"feedback": "x"}, headers=w.teacher_a
    )
    assert again.status_code == 409 and again.json()["code"] == "SUBMISSION_RETURNED"
    item = next(i for i in _hw(w).json()["assignments"][0]["items"] if i["item_ref"] == "hw-long")
    assert item["state"] == "returned"
    assert item["submission"]["feedback"] == "Say why the parts are equal."
    assert _queue(w, "returned").json()["submissions"][0]["submission_id"] == sub

    resubmitted = _submit(w, "hw-long", CHILD_TEXT)
    assert resubmitted.status_code == 200
    assert resubmitted.json()["submission"]["submission_id"] == sub  # same row, next attempt
    assert resubmitted.json()["submission"]["attempt"] == 2

    assert _mark(w, sub, {"outcome": "met", "score": None}).status_code == 422  # rubric: score
    assert _mark(w, sub, {"outcome": "met", "score": 4}).status_code == 422  # > max_score
    assert _mark(w, sub, {"outcome": "great", "score": 2}).status_code == 422
    before = _attempts(w)
    marked = _mark(w, sub, {"outcome": "met", "score": 3, "feedback": "Well explained."})
    assert marked.status_code == 200, marked.text
    assert marked.json()["state"] == "marked" and marked.json()["score"] == 3
    assert _evidence(w, sub) == 1 and _attempts(w) == before + 1

    # Retrying the mark: 409, and still exactly one evidence row / one mastery update.
    retry = _mark(w, sub, {"outcome": "met", "score": 3})
    assert retry.status_code == 409 and retry.json()["code"] == "SUBMISSION_MARKED"
    assert _evidence(w, sub) == 1 and _attempts(w) == before + 1
    # Marked is final for the child too.
    final = _submit(w, "hw-long", "changed my mind")
    assert final.status_code == 409 and final.json()["code"] == "SUBMISSION_MARKED"
    item = next(i for i in _hw(w).json()["assignments"][0]["items"] if i["item_ref"] == "hw-long")
    assert item["state"] == "marked"
    assert item["submission"]["outcome"] == "met" and item["submission"]["score"] == 3
    assert _queue(w, "marked").json()["submissions"][0]["outcome"] == "met"


def test_item_without_rubric_takes_no_score_and_not_yet_is_incorrect(w: W) -> None:
    sub = _submit(w, "hw-short").json()["submission"]["submission_id"]
    assert _mark(w, sub, {"outcome": "not_yet", "score": 1}).status_code == 422
    r = _mark(w, sub, {"outcome": "not_yet", "score": None, "feedback": "Try counting."})
    assert r.status_code == 200 and r.json()["score"] is None
    with w.app.state.learning_session_factory() as s:
        outcome = s.scalar(
            select(AssessmentEvidenceRow.outcome).where(AssessmentEvidenceRow.id == sub)
        )
        context = s.scalar(
            select(AssessmentEvidenceRow.context).where(AssessmentEvidenceRow.id == sub)
        )
    assert outcome == "incorrect" and context == "practice"


def test_submission_validation(w: W) -> None:
    assert _submit(w, "hw-short", "   ").status_code == 422
    assert _submit(w, "hw-short", "x" * 201).status_code == 422
    assert _submit(w, "hw-short", "x" * 200).status_code == 200
    assert _submit(w, "hw-long", "x" * 2000).status_code == 200
    assert _submit(w, "hw-long", "x" * 2001).status_code == 422
    # Not a written item of the lesson (an MCQ, or unknown): 404. Unknown assignment: 404.
    assert _submit(w, "hw1-half-of-two").status_code == 404
    assert _submit(w, "nope").status_code == 404
    assert _submit(w, "hw-short", assignment="asg_unknown").status_code == 404


# ------------------------------------------------------------------------ access control


def test_withdrawn_consent_is_403_on_the_next_request(w: W) -> None:
    assert _hw(w).status_code == 200
    r = w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": w.fam.student_ref},
        headers=w.fam.guardian,
    )
    assert r.status_code == 200
    assert _hw(w).status_code == 403
    blocked = _submit(w, "hw-short")
    assert blocked.status_code == 403 and blocked.json()["code"] == "CONSENT_REQUIRED"


def test_withdrawn_sharing_blocks_submit_and_hides_from_the_teacher(w: W) -> None:
    sub = _submit(w, "hw-short").json()["submission"]["submission_id"]
    w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": w.fam.student_ref, "scopes": ["progress_sharing"]},
        headers=w.fam.guardian,
    )
    blocked = _submit(w, "hw-short", "again")
    assert blocked.status_code == 403 and blocked.json()["code"] == "SHARING_REQUIRED"
    queue = _queue(w)
    assert queue.json()["submissions"] == [] and w.fam.student_ref not in queue.text
    assert _mark(w, sub, {"outcome": "met"}).status_code == 404


def test_another_learner_or_role_cannot_use_a_learners_homework(w: W) -> None:
    other = _family(w.client, "other@example.com")
    url = f"/v1/school/learners/{w.fam.student_ref}/homework"
    assert w.client.get(url, headers=other.learner).status_code == 403
    assert w.client.get(url, headers=w.fam.guardian).status_code == 403
    assert w.client.get(url, headers=w.teacher_a).status_code == 403
    assert w.client.get(url).status_code == 401
    # A learner in no class has no homework and cannot submit to someone else's assignment.
    assert _hw(w, other).json() == {"assignments": []}
    r = w.client.post(
        f"/v1/school/learners/{other.student_ref}/homework/{w.assignment}/items/hw-short:submit",
        json={"text": "hi"},
        headers=other.learner,
    )
    assert r.status_code == 404


def test_queue_and_marking_are_isolated_by_org_and_class(w: W) -> None:
    sub = _submit(w, "hw-short").json()["submission"]["submission_id"]
    for teacher in (w.teacher_b, w.teacher_a2):  # another school; same school, other class
        assert _queue(w, teacher=teacher).status_code == 404
        assert _mark(w, sub, {"outcome": "met"}, teacher=teacher).status_code == 404
        r = w.client.post(
            f"/v1/school/submissions/{sub}:return", json={"feedback": "x"}, headers=teacher
        )
        assert r.status_code == 404
        c = w.client.post(
            f"/v1/school/submissions/{sub}:concern", json={"category": "other"}, headers=teacher
        )
        assert c.status_code == 404
    assert w.client.get(
        f"/v1/school/classes/{w.class_a2}/submissions", headers=w.teacher_a
    ).status_code == (404)
    assert _queue(w, status="bogus").status_code == 422
    assert _mark(w, "sub_unknown", {"outcome": "met"}).status_code == 404
    assert _queue(w, teacher=w.fam.learner).status_code == 403
    assert _mark(w, sub, {"outcome": "met"}, teacher=w.fam.guardian).status_code == 403


# ------------------------------------------------------------------ secrecy, audit, offline


def test_offline_package_and_student_homework_carry_no_marking_aid(w: W) -> None:
    listed = w.client.get("/v1/offline/packages", headers=w.fam.learner)
    assert listed.status_code == 200, listed.text
    pkg = w.client.get(f"/v1/offline/packages/{LESSON_KEY}", headers=w.fam.learner)
    assert pkg.status_code == 200, pkg.text
    homework = w.client.get(
        f"/v1/learning/students/{w.fam.student_ref}/homework", headers=w.fam.learner
    )
    for response in (pkg, homework):
        for secret in (SAMPLE, GUIDANCE, CRITERIA, '"rubric"', '"sample_answer"', '"guidance"'):
            assert secret not in response.text, secret
    items = pkg.json()["content"]["homework_items"]
    short = next(i for i in items if i["item_ref"] == "hw-short")
    assert short["kind"] == "written" and short["max_chars"] == 200


def test_audit_records_refs_only(w: W) -> None:
    sub = _submit(w, "hw-short").json()["submission"]["submission_id"]
    w.client.post(
        f"/v1/school/submissions/{sub}:return",
        json={"feedback": "FEEDBACK-WORDS"},
        headers=w.teacher_a,
    )
    _submit(w, "hw-short", CHILD_TEXT + " again")
    _mark(w, sub, {"outcome": "met", "feedback": "MARK-WORDS"})
    with w.app.state.school_session_factory() as s:
        rows = s.scalars(select(SchoolAuditRow).where(SchoolAuditRow.object_ref == sub)).all()
        dumped = json.dumps([{c.key: getattr(r, c.key) for c in r.__table__.columns} for r in rows])
    assert [r.action for r in rows] == [
        "submission.submitted",
        "submission.returned",
        "submission.submitted",
        "submission.marked",
    ]
    assert {r.actor_role for r in rows} == {"student", "teacher"}
    for words in (CHILD_TEXT, "FEEDBACK-WORDS", "MARK-WORDS"):
        assert words not in dumped


# ----------------------------------------------------------------------------- safeguarding


def test_teacher_raises_a_concern_from_a_submission(w: W) -> None:
    sub = _submit(w, "hw-short").json()["submission"]["submission_id"]
    r = w.client.post(
        f"/v1/school/submissions/{sub}:concern",
        json={"category": "felt_unsafe", "text": "The answer mentions being hurt."},
        headers=w.teacher_a,
    )
    assert r.status_code == 201, r.text
    assert r.json()["received"] is True and "concern_id" not in r.json()
    with w.app.state.safeguarding_session_factory() as s:
        concern = s.scalars(select(ConcernRow)).one()
    assert concern.raised_by_role == "teacher" and concern.subject_ref == w.fam.student_ref
    assert concern.context_submission_id == sub and concern.priority == "T1"
    # The submission is unchanged, and the child and guardian see nothing.
    assert _queue(w).json()["submissions"][0]["state"] == "submitted"
    assert "concern" not in _hw(w).text
    mine = w.client.get("/v1/safeguarding/my-concerns", headers=w.fam.guardian)
    assert mine.json()["concerns"] == []
    bad = w.client.post(
        f"/v1/school/submissions/{sub}:concern", json={"category": "nope"}, headers=w.teacher_a
    )
    assert bad.status_code == 422


def test_teacher_concern_scope_on_the_safeguarding_route(w: W) -> None:
    sub = _submit(w, "hw-short").json()["submission"]["submission_id"]
    url = "/v1/safeguarding/concerns"
    ok = {"category": "very_sad", "studentRef": w.fam.student_ref, "submissionId": sub}
    assert w.client.post(url, json=ok, headers=w.teacher_a).status_code == 201
    no_sub = {"category": "other", "studentRef": w.fam.student_ref}
    assert w.client.post(url, json=no_sub, headers=w.teacher_a).status_code == 201
    for teacher in (w.teacher_b, w.teacher_a2):  # not their class
        assert w.client.post(url, json=no_sub, headers=teacher).status_code == 404
    other = _family(w.client, "other@example.com")
    stranger = {"category": "other", "studentRef": other.student_ref}
    assert w.client.post(url, json=stranger, headers=w.teacher_a).status_code == 404
    wrong_sub = {"category": "other", "studentRef": other.student_ref, "submissionId": sub}
    assert w.client.post(url, json=wrong_sub, headers=w.teacher_a).status_code == 404
    # Only a teacher names a submission.
    guardian = {"category": "other", "studentRef": w.fam.student_ref, "submissionId": sub}
    assert w.client.post(url, json=guardian, headers=w.fam.guardian).status_code == 403
    # Still a 403 for unrelated roles, and the lead sees the teacher's concern with its ref.
    assert (
        w.client.post(
            url, json=ok, headers={"Authorization": "Bearer " + _token("mentor", "m")}
        ).status_code
        == 403
    )


# ------------------------------------------------------------------------------- privacy


def test_privacy_export_and_erasure_cover_submissions(w: W) -> None:
    sub = _submit(w, "hw-short").json()["submission"]["submission_id"]
    ref = w.fam.student_ref
    export = w.client.get(f"/v1/privacy/learners/{ref}/export", headers=w.fam.guardian)
    assert export.status_code == 200, export.text
    school = export.json()["sections"]["school"]
    assert [s["submission_id"] for s in school["submissions"]] == [sub]
    assert school["submissions"][0]["text"] == CHILD_TEXT

    req = w.client.post(f"/v1/privacy/learners/{ref}/erasure-requests", headers=w.fam.guardian)
    assert req.status_code == 202, req.text
    token = req.json()["confirmation_token"]
    done = w.client.post(
        f"/v1/privacy/learners/{ref}/erasure:confirm",
        json={"confirmationToken": token},
        headers=w.fam.guardian,
    )
    assert done.status_code == 200, done.text
    with w.app.state.school_session_factory() as s:
        left = s.scalar(
            select(func.count()).select_from(SubmissionRow).where(SubmissionRow.student_ref == ref)
        )
    assert left == 0
