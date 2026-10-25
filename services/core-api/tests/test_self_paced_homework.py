"""The AI-led homework path (HOMEWORK_AND_MARKING_CONTRACT §6), end to end on the composed app.

Self-paced homework from every studied lesson (no assignment, no class, no teacher), dedupe
against assignments, reliable auto-marking only for exact keys (with the auto ``not_yet`` retry
rule), open answers as ``self_check`` with "compare your answer" only after submitting, the
deterministic disclosure screen raising one system concern per submission, cohort filtering,
privacy export / erasure, refs-only audit, and the AI rubric marker never running.
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
from taleem_core.contexts.curriculum_studio.domain.assessment import ItemType
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.contexts.learning.adapters.persistence.models import AssessmentEvidenceRow
from taleem_core.contexts.safeguarding.adapters.persistence.models import ConcernRow
from taleem_core.contexts.school.adapters.persistence.models import SchoolAuditRow, SubmissionRow
from taleem_core.main import create_app
from taleem_core.platform.cohort import DEMO, reading_as
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)
from tests.test_homework_api import CRITERIA, GUIDANCE, SAMPLE, _rubric, _written
from tests.test_school_api import _SECRET, Family, _class, _family, _join, _org, _teacher
from tests.test_sync_evidence import _REVIEW_ROLES

EXACT = "1/4"
VARIANT = "one quarter"
OPEN_TEXT = "Ammi cut the roti into 4 equal parts and I ate one"


def publish(app: FastAPI, *, audience: str = "") -> None:
    """The fractions lesson with open written items and one exact-key written item."""
    lesson = build_fractions_lesson()
    lesson.metadata.audience = audience
    lesson.homework.append(_written("hw-short", ItemType.SHORT, key={"sample_answer": SAMPLE}))
    lesson.homework.append(
        _written("hw-long", ItemType.LONG, rubric=_rubric(), key={"guidance": GUIDANCE})
    )
    lesson.challenge_problems.append(
        _written("ch-word", ItemType.WORD_PROBLEM, rubric=_rubric(), key={})
    )
    exact = _written("hw-exact", ItemType.SHORT, key={"answer": EXACT})
    exact.accepted_variants = [VARIANT]
    lesson.homework.append(exact)
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


def study(app: FastAPI, student_ref: str, *, context: str = "practice", eid: str = "") -> None:
    """Record one evidence row on the lesson's objective (as a live session answer would)."""
    with app.state.learning_session_factory() as s, s.begin():
        s.add(
            AssessmentEvidenceRow(
                id=eid or f"ev-{student_ref}-{time.time_ns()}",
                student_ref=student_ref,
                objective_code=OBJECTIVE_CODE,
                item_ref="p1-one-of-four",
                session_id="sess-1",
                outcome="correct",
                context=context,
                mastery_before=0.3,
                mastery_after=0.4,
                occurred_at=time.time(),
            )
        )


@dataclass
class S:
    client: TestClient
    app: FastAPI
    fam: Family  # no class, no progress sharing: the AI-led learner


@pytest.fixture
def s() -> S:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    fam = _family(client, "solo@example.com")
    study(app, fam.student_ref)
    return S(client, app, fam)


def _hw(s: S, fam: Family | None = None) -> Any:
    f = fam or s.fam
    r = s.client.get(f"/v1/school/learners/{f.student_ref}/homework", headers=f.learner)
    assert r.status_code == 200, r.text
    return r


def _items(s: S) -> dict[str, dict[str, Any]]:
    (entry,) = _hw(s).json()["assignments"]
    return {i["item_ref"]: i for i in entry["items"]}


def _submit(s: S, item: str, text: str = OPEN_TEXT, fam: Family | None = None) -> Any:
    f = fam or s.fam
    return s.client.post(
        f"/v1/school/learners/{f.student_ref}/homework/self-paced/"
        f"{OBJECTIVE_CODE}/items/{item}:submit",
        json={"text": text},
        headers=f.learner,
    )


def _evidence(app: FastAPI, prefix: str) -> list[str]:
    with app.state.learning_session_factory() as session:
        return sorted(
            session.scalars(
                select(AssessmentEvidenceRow.id).where(AssessmentEvidenceRow.id.startswith(prefix))
            )
        )


def _concerns(app: FastAPI) -> list[ConcernRow]:
    with app.state.safeguarding_session_factory() as session:
        return list(session.scalars(select(ConcernRow)))


# ----------------------------------------------------------------------- self-paced listing


def test_a_studied_lesson_is_homework_with_no_assignment(s: S) -> None:
    r = _hw(s)
    (entry,) = r.json()["assignments"]
    assert entry["source"] == "self_paced" and entry["objective_code"] == OBJECTIVE_CODE
    assert entry["assignment_id"] is None and entry["class_id"] is None
    assert entry["due_at"] is None and entry["overdue"] is False
    assert entry["lesson_title"]["en"]
    items = {i["item_ref"]: i for i in entry["items"]}
    assert list(items) == ["hw-short", "hw-long", "hw-exact", "ch-word"]
    assert {i["source"] for i in items.values()} == {"self_paced"}
    assert items["hw-exact"]["marking"] == "auto"
    assert {items[k]["marking"] for k in ("hw-short", "hw-long", "ch-word")} == {"self_check"}
    for item in items.values():
        assert item["state"] == "not_started" and item["submission"] is None
        assert item["compare"] is None and item["can_retry"] is False
    # Nothing secret before submitting: no sample, guidance, rubric or exact key.
    for secret in (SAMPLE, GUIDANCE, CRITERIA, EXACT, VARIANT, '"rubric"', '"sample_answer"'):
        assert secret not in r.text, secret


def test_placement_or_homework_evidence_is_not_studying(s: S) -> None:
    other = _family(s.client, "placed@example.com")
    study(s.app, other.student_ref, context="diagnostic")
    study(s.app, other.student_ref, eid="sub_0000-not-studying")
    assert _hw(s, other).json() == {"assignments": []}
    r = _submit(s, "hw-short", fam=other)
    assert r.status_code == 404


def test_a_synced_offline_attempt_counts_as_studying(s: S) -> None:
    other = _family(s.client, "offline@example.com")
    r = s.client.post(
        "/v1/sync/batch",
        json={
            "cursor": 0,
            "deltas": [
                {
                    "clientEventId": "ce-1",
                    "type": "attempt.submitted",
                    "entityKey": f"student:{other.student_ref}|lesson:{LESSON_KEY}",
                    "clientSeq": 1,
                    "payload": {
                        "student_ref": other.student_ref,
                        "objective_code": OBJECTIVE_CODE,
                        "item_ref": "p1-one-of-four",
                        "option": 0,
                        "evidence_id": "ev-offline-1",
                        "session_id": "offline-1",
                        "context": "practice",
                    },
                }
            ],
        },
        headers=other.learner,
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["status"] == "applied", r.text
    (entry,) = _hw(s, other).json()["assignments"]
    assert entry["source"] == "self_paced"


def test_an_assignment_of_the_same_lesson_wins(s: S) -> None:
    org = _org(s.client, "School A")
    teacher = _teacher(s.client, org, "t@school-a.example")
    klass = _class(s.client, teacher, "Grade 4")
    assert _join(s.client, s.fam, klass["join_code"]) == 200
    due = time.time() + 86400
    r = s.client.post(
        f"/v1/school/classes/{klass['class_id']}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": due},
        headers=teacher,
    )
    assert r.status_code == 201, r.text
    (entry,) = _hw(s).json()["assignments"]
    assert entry["source"] == "assignment" and entry["due_at"] == pytest.approx(due)
    assert {i["source"] for i in entry["items"]} == {"assignment"}
    blocked = _submit(s, "hw-short")
    assert blocked.status_code == 409 and blocked.json()["code"] == "LESSON_ASSIGNED"


def test_a_demo_lesson_is_never_self_paced_homework_for_a_real_learner() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app, audience=DEMO)
    client = TestClient(app)
    fam = _family(client, "real@example.com")
    study(app, fam.student_ref)
    r = client.get(f"/v1/school/learners/{fam.student_ref}/homework", headers=fam.learner)
    assert r.status_code == 200 and r.json() == {"assignments": []}
    sub = client.post(
        f"/v1/school/learners/{fam.student_ref}/homework/self-paced/"
        f"{OBJECTIVE_CODE}/items/hw-short:submit",
        json={"text": "hello"},
        headers=fam.learner,
    )
    assert sub.status_code == 404
    with reading_as(DEMO):  # the same lesson is there for a demo reader
        assert app.state.school_service.learner_homework(fam.student_ref)["assignments"]


# --------------------------------------------------------------------------- open answers


def test_open_answer_is_self_check_with_compare_only_after_submitting(s: S) -> None:
    r = _submit(s, "hw-short", "  " + OPEN_TEXT + "  ")
    assert r.status_code == 200, r.text  # no progress_sharing needed: nobody else reads it
    body = r.json()
    assert body["source"] == "self_paced" and body["assignment_id"] is None
    assert body["objective_code"] == OBJECTIVE_CODE and body["item_ref"] == "hw-short"
    assert body["state"] == "submitted" and body["marking"] == "self_check"
    assert body["can_retry"] is False
    assert body["submission"]["text"] == OPEN_TEXT and body["submission"]["outcome"] is None
    assert body["compare"] == {
        "label": "compare_your_answer",
        "sample_answer": SAMPLE,
        "guidance": None,
    }
    assert '"marked"' not in r.text and CRITERIA not in r.text  # never says "marked"
    long = _submit(s, "hw-long").json()
    assert long["compare"]["guidance"] == GUIDANCE and long["compare"]["sample_answer"] is None
    word = _submit(s, "ch-word").json()  # the author gave neither: nothing to compare with
    assert word["compare"] is None and word["state"] == "submitted"
    items = _items(s)
    assert items["hw-short"]["compare"]["sample_answer"] == SAMPLE
    assert items["hw-long"]["compare"]["guidance"] == GUIDANCE
    assert items["hw-exact"]["compare"] is None  # not submitted
    for item in ("hw-short", "hw-long", "ch-word"):
        assert items[item]["state"] == "submitted"
    assert CRITERIA not in _hw(s).text and '"rubric"' not in _hw(s).text
    assert _evidence(s.app, "sub_") == []  # an open answer is never mastery evidence
    # Resubmitting an open answer is allowed (same row, next attempt).
    again = _submit(s, "hw-short", "a better try").json()
    assert again["submission"]["attempt"] == 2
    assert again["submission"]["submission_id"] == body["submission"]["submission_id"]
    with s.app.state.school_session_factory() as session:
        rows = session.scalars(select(SubmissionRow)).all()
    assert {(r.source, r.assignment_id, r.class_id, r.organization_id) for r in rows} == {
        ("self_paced", None, None, "")
    }
    assert len(rows) == 3


def test_submit_validation_on_the_self_paced_route(s: S) -> None:
    assert _submit(s, "hw-short", "   ").status_code == 422
    assert _submit(s, "hw-short", "x" * 201).status_code == 422
    assert _submit(s, "hw1-half-of-two").status_code == 404  # not a written item
    assert _submit(s, "nope").status_code == 404
    other = _family(s.client, "other@example.com")
    r = s.client.post(
        f"/v1/school/learners/{s.fam.student_ref}/homework/self-paced/"
        f"{OBJECTIVE_CODE}/items/hw-short:submit",
        json={"text": "x"},
        headers=other.learner,
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------- auto-marking


def test_exact_key_is_auto_marked_met_with_one_evidence_and_is_final(s: S) -> None:
    r = _submit(s, "hw-exact", "  ONE   Quarter. ")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "marked" and body["marking"] == "auto"
    sub = body["submission"]
    assert sub["outcome"] == "met" and sub["reviewed_by"] == "auto" and sub["score"] is None
    assert body["can_retry"] is False and sub["can_retry"] is False
    assert body["compare"] is None and EXACT not in r.text
    sid = sub["submission_id"]
    assert _evidence(s.app, sid) == [sid]
    final = _submit(s, "hw-exact", "1/4")
    assert final.status_code == 409 and final.json()["code"] == "SUBMISSION_MARKED"
    assert _evidence(s.app, sid) == [sid]
    with s.app.state.learning_session_factory() as session:
        row = session.get(AssessmentEvidenceRow, sid)
        assert row is not None and row.outcome == "correct" and row.context == "practice"


def test_urdu_digits_follow_the_fill_normalize_rule(s: S) -> None:
    body = _submit(s, "hw-exact", "۱/۴").json()
    assert body["submission"]["outcome"] == "met"


def test_auto_not_yet_may_be_retried_with_one_evidence_per_attempt(s: S) -> None:
    first = _submit(s, "hw-exact", "1/2").json()
    sid = first["submission"]["submission_id"]
    assert first["state"] == "marked" and first["submission"]["outcome"] == "not_yet"
    assert first["can_retry"] is True and first["submission"]["can_retry"] is True
    assert _items(s)["hw-exact"]["can_retry"] is True
    assert _evidence(s.app, sid) == [sid]

    second = _submit(s, "hw-exact", "2/4").json()
    assert second["submission"]["attempt"] == 2 and second["submission"]["submission_id"] == sid
    assert second["submission"]["outcome"] == "not_yet" and second["can_retry"] is True
    assert _evidence(s.app, sid) == [sid, f"{sid}:2"]

    third = _submit(s, "hw-exact", VARIANT).json()
    assert third["submission"]["outcome"] == "met" and third["can_retry"] is False
    assert _evidence(s.app, sid) == [sid, f"{sid}:2", f"{sid}:3"]
    with s.app.state.learning_session_factory() as session:
        outcomes = [session.get(AssessmentEvidenceRow, e).outcome for e in _evidence(s.app, sid)]
    assert outcomes == ["incorrect", "incorrect", "correct"]

    after = _submit(s, "hw-exact", "1/2")
    assert after.status_code == 409 and after.json()["code"] == "SUBMISSION_MARKED"
    assert _evidence(s.app, sid) == [sid, f"{sid}:2", f"{sid}:3"]


def test_replaying_the_evidence_of_one_attempt_records_nothing(s: S) -> None:
    sid = _submit(s, "hw-exact", "1/2").json()["submission"]["submission_id"]
    _submit(s, "hw-exact", "3/4")
    service = s.app.state.school_service
    with service._uow() as uow:  # noqa: SLF001 - the replay path itself
        sub = uow.submissions.by_id(sid)
    assert sub is not None and sub.attempt == 2
    for _ in range(3):
        service._ensure_evidence(sub)  # noqa: SLF001
    assert _evidence(s.app, sid) == [sid, f"{sid}:2"]


def test_auto_marking_also_applies_to_an_assigned_item_and_the_audit_is_refs_only() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    org = _org(client, "School A")
    teacher = _teacher(client, org, "t@school-a.example")
    klass = _class(client, teacher, "Grade 4")
    fam = _family(client, "class@example.com")
    assert _join(client, fam, klass["join_code"]) == 200
    asg = client.post(
        f"/v1/school/classes/{klass['class_id']}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 86400},
        headers=teacher,
    ).json()["assignment_id"]
    r = client.post(
        f"/v1/school/learners/{fam.student_ref}/homework/{asg}/items/hw-exact:submit",
        json={"text": EXACT},
        headers=fam.learner,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "assignment" and body["assignment_id"] == asg
    assert body["state"] == "marked" and body["submission"]["reviewed_by"] == "auto"
    sid = body["submission"]["submission_id"]
    queue = client.get(
        f"/v1/school/classes/{klass['class_id']}/submissions",
        params={"status": "marked"},
        headers=teacher,
    )
    assert [row["reviewed_by"] for row in queue.json()["submissions"]] == ["auto"]
    mark = client.post(
        f"/v1/school/submissions/{sid}:mark", json={"outcome": "not_yet"}, headers=teacher
    )
    assert mark.status_code == 409
    with app.state.school_session_factory() as session:
        audit = session.scalars(select(SchoolAuditRow).where(SchoolAuditRow.object_ref == sid))
        rows = list(audit)
        dumped = json.dumps([{c.key: getattr(x, c.key) for c in x.__table__.columns} for x in rows])
    assert [(x.action, x.actor_role) for x in rows] == [
        ("submission.submitted", "student"),
        ("submission.marked", "system"),
    ]
    assert EXACT not in dumped


def test_a_teacher_never_sees_or_marks_a_self_paced_answer(s: S) -> None:
    org = _org(s.client, "School A")
    teacher = _teacher(s.client, org, "t@school-a.example")
    sid = _submit(s, "hw-short").json()["submission"]["submission_id"]
    klass = _class(s.client, teacher, "Grade 4")
    assert _join(s.client, s.fam, klass["join_code"]) == 200
    for status in ("submitted", "marked"):
        queue = s.client.get(
            f"/v1/school/classes/{klass['class_id']}/submissions",
            params={"status": status},
            headers=teacher,
        )
        assert queue.json()["submissions"] == []
    r = s.client.post(
        f"/v1/school/submissions/{sid}:mark", json={"outcome": "met"}, headers=teacher
    )
    assert r.status_code == 404
    c = s.client.post(
        f"/v1/school/submissions/{sid}:concern", json={"category": "other"}, headers=teacher
    )
    assert c.status_code == 404


# ------------------------------------------------------------------------ disclosure screen


def test_an_english_disclosure_raises_one_system_concern_and_changes_nothing(s: S) -> None:
    text = "My uncle hits me when nobody is home."
    r = _submit(s, "hw-short", text)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "submitted" and "concern" not in json.dumps(body["submission"])
    assert set(body) == {
        "source",
        "assignment_id",
        "objective_code",
        "item_ref",
        "marking",
        "state",
        "can_retry",
        "submission",
        "compare",
    }
    sid = body["submission"]["submission_id"]
    (concern,) = _concerns(s.app)
    assert concern.raised_by_role == "system" and concern.raised_by_ref == "disclosure_screen"
    assert concern.subject_ref == s.fam.student_ref and concern.context_submission_id == sid
    assert concern.category == "felt_unsafe" and concern.priority == "T1"
    assert concern.free_text is not None and "hits me" not in concern.free_text
    assert "en-01" in concern.free_text
    # Idempotent: another matching resubmission of the same submission adds nothing.
    _submit(s, "hw-short", "I want to die")
    assert len(_concerns(s.app)) == 1
    # Never shown to the family.
    assert "concern" not in _hw(s).text
    mine = s.client.get("/v1/safeguarding/my-concerns", headers=s.fam.guardian)
    assert mine.json()["concerns"] == []


def test_an_urdu_disclosure_is_screened_too(s: S) -> None:
    sid = _submit(s, "hw-long", "ابو مجھے مارتے ہیں۔").json()["submission"]["submission_id"]
    (concern,) = _concerns(s.app)
    assert concern.context_submission_id == sid and concern.category == "felt_unsafe"
    _submit(s, "hw-short", "میں مرنا چاہتی ہوں")
    assert {c.category for c in _concerns(s.app)} == {"felt_unsafe", "very_sad"}


def test_ordinary_answers_raise_nothing(s: S) -> None:
    for text in (
        OPEN_TEXT,
        "Ali hit the ball and it broke into 4 equal pieces.",
        "Bilal touched the roti to check it was hot.",
        "روٹی کے چار برابر حصے ہیں، میں نے ایک کھایا۔",
        "I don't know the answer but I tried my best.",
    ):
        assert _submit(s, "hw-long", text).status_code == 200
    assert _concerns(s.app) == []


def test_a_failing_screen_never_blocks_the_child(s: S, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**_: object) -> bool:
        raise RuntimeError("screen down")

    monkeypatch.setattr(s.app.state.safeguarding_service, "screen_submission", boom)
    r = _submit(s, "hw-short", "My uncle hits me.")
    assert r.status_code == 200 and r.json()["state"] == "submitted"


# -------------------------------------------------------------------------------- privacy


def test_export_and_erasure_cover_self_paced_work_and_system_concerns(s: S) -> None:
    sid = _submit(s, "hw-short", "My uncle hits me.").json()["submission"]["submission_id"]
    auto = _submit(s, "hw-exact", EXACT).json()["submission"]["submission_id"]
    ref = s.fam.student_ref
    export = s.client.get(f"/v1/privacy/learners/{ref}/export", headers=s.fam.guardian)
    assert export.status_code == 200, export.text
    school = export.json()["sections"]["school"]
    rows = {r["submission_id"]: r for r in school["submissions"]}
    # The flagged answer (a disclosure) is withheld from the guardian, who may be the person the
    # child wrote about; the ordinary answer is exported. The notice is constant either way.
    assert set(rows) == {auto}
    assert "uncle" not in export.text
    assert school["withheld"]
    assert rows[auto]["source"] == "self_paced" and rows[auto]["assignment_id"] is None
    assert rows[auto]["reviewed_by"] == "auto"
    assert sid not in export.text
    req = s.client.post(f"/v1/privacy/learners/{ref}/erasure-requests", headers=s.fam.guardian)
    assert req.status_code == 202, req.text
    done = s.client.post(
        f"/v1/privacy/learners/{ref}/erasure:confirm",
        json={"confirmationToken": req.json()["confirmation_token"]},
        headers=s.fam.guardian,
    )
    assert done.status_code == 200, done.text
    with s.app.state.school_session_factory() as session:
        left = session.scalar(
            select(func.count()).select_from(SubmissionRow).where(SubmissionRow.student_ref == ref)
        )
    assert left == 0
    assert [c for c in _concerns(s.app) if c.subject_ref == ref] == []
    assert _evidence(s.app, auto) == []


# ---------------------------------------------------------------------- AI marking is inert


def test_ai_rubric_marking_never_runs_even_with_a_stub_provider_and_the_flag_on() -> None:
    app = create_app(
        Settings(
            database_url="",
            kdf_iterations=1_000,
            jwt_dev_secret=_SECRET,
            ai_provider="stub",
            enabled_flags_csv="homework.ai_rubric_marking",
        )
    )
    publish(app)
    client = TestClient(app)
    fam = _family(client, "ai@example.com")
    study(app, fam.student_ref)
    assert app.state.written_marker is None
    gateway = app.state.ai_gateway
    before = gateway.calls
    r = client.post(
        f"/v1/school/learners/{fam.student_ref}/homework/self-paced/"
        f"{OBJECTIVE_CODE}/items/hw-long:submit",
        json={"text": OPEN_TEXT},
        headers=fam.learner,
    )
    assert r.status_code == 200 and r.json()["marking"] == "self_check"
    assert r.json()["state"] == "submitted"
    assert gateway.calls == before
    assert all(OPEN_TEXT not in " ".join(q.grounding) for q in gateway.requests)
