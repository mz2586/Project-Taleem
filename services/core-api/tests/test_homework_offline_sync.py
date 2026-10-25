"""Offline homework submission — the ``homework.submitted`` sync delta, end to end on the app.

A written answer sent while offline is applied by the SAME school service as the online submit
(HOMEWORK_AND_MARKING_CONTRACT §2, §6; OFFLINE_SYNC_SPEC.md): automatic marking, self-check with
the compare view, the disclosure screen (once), cohort filtering, the consent gate and
``SHARING_REQUIRED`` all behave identically. Idempotent by the device's submission key (a replay is
a duplicate, even with a fresh clientEventId, i.e. after a restart); every refusal is a conflict
with a reason, never silently dropped, and never remembered — so the same answer can be re-sent.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from taleem_core.contexts.school.adapters.persistence.models import SchoolAuditRow, SubmissionRow
from taleem_core.contexts.sync.domain import DeltaType, Status, SyncDelta, SyncStore
from taleem_core.contexts.sync.service import DurableSyncCoordinator, learners_touched
from taleem_core.main import create_app
from taleem_core.platform.cohort import DEMO
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE
from tests.test_school_api import (
    _ATTEST,
    _SECRET,
    _SYSTEM,
    Family,
    _class,
    _family,
    _join,
    _org,
    _teacher,
)
from tests.test_self_paced_homework import (
    EXACT,
    OPEN_TEXT,
    S,
    _concerns,
    _evidence,
    _submit,
    publish,
    study,
)


@pytest.fixture
def s() -> S:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    fam = _family(client, "offline@example.com")
    study(app, fam.student_ref)
    return S(client, app, fam)


_seq = iter(range(1, 10_000))


def _delta(
    fam: Family,
    item: str,
    text: str = OPEN_TEXT,
    *,
    key: str | None = None,
    event: str | None = None,
    attempt: int | None = 1,
    assignment_id: str | None = None,
    objective_code: str = OBJECTIVE_CODE,
    **extra: object,
) -> dict[str, Any]:
    key = key or str(uuid.uuid4())
    source = "assignment" if assignment_id else "self_paced"
    target = (
        {"assignment_id": assignment_id} if assignment_id else {"objective_code": objective_code}
    )
    payload: dict[str, object] = {
        "student_ref": fam.student_ref,
        "source": source,
        **target,
        "item_ref": item,
        "text": text,
        "submission_key": key,
        "submitted_at": time.time() * 1000,
        **({"attempt": attempt} if attempt is not None else {}),
        **extra,
    }
    return {
        "clientEventId": event or key,
        "type": "homework.submitted",
        "entityKey": f"student:{fam.student_ref}|homework:{source}|item:{item}",
        "clientSeq": next(_seq),
        "payload": payload,
    }


def _sync(s: S, *deltas: dict[str, Any], headers: dict[str, str] | None = None) -> Any:
    return s.client.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": list(deltas)},
        headers=headers or s.fam.learner,
    )


def _one(s: S, delta: dict[str, Any]) -> dict[str, Any]:
    r = _sync(s, delta)
    assert r.status_code == 200, r.text
    (result,) = r.json()["results"]
    return dict(result)


def _rows(app: FastAPI, student_ref: str) -> list[SubmissionRow]:
    with app.state.school_session_factory() as session:
        return list(
            session.scalars(select(SubmissionRow).where(SubmissionRow.student_ref == student_ref))
        )


def _audit_count(app: FastAPI, sid: str) -> int:
    with app.state.school_session_factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(SchoolAuditRow)
                .where(SchoolAuditRow.object_ref == sid)
            )
            or 0
        )


# ------------------------------------------------------------------- online-equivalent results


def test_an_offline_open_answer_gets_exactly_the_online_result(s: S) -> None:
    result = _one(s, _delta(s.fam, "hw-short"))
    assert result["status"] == "applied" and "reason" not in result
    view = result["result"]
    # The same learner-facing shape as the online submit, nothing more (no rubric, no key).
    online_fam = _family(s.client, "online@example.com")
    study(s.app, online_fam.student_ref)
    online = _submit(s, "hw-short", fam=online_fam).json()
    assert set(view) == set(online)
    assert view["state"] == online["state"] == "submitted"
    assert view["marking"] == online["marking"] == "self_check"
    assert view["compare"] == online["compare"] and view["compare"] is not None
    assert view["submission"]["text"] == OPEN_TEXT and view["submission"]["attempt"] == 1
    # And it is the child's homework now, as if sent online.
    (row,) = _rows(s.app, s.fam.student_ref)
    assert row.source == "self_paced" and row.client_key is not None
    assert row.submission_id == view["submission"]["submission_id"]


def test_an_offline_exact_answer_is_checked_by_taleem_with_one_evidence(s: S) -> None:
    result = _one(s, _delta(s.fam, "hw-exact", EXACT))
    view = result["result"]
    assert result["status"] == "applied"
    assert view["state"] == "marked" and view["submission"]["reviewed_by"] == "auto"
    assert view["submission"]["outcome"] == "met" and view["can_retry"] is False
    sid = view["submission"]["submission_id"]
    assert _evidence(s.app, sid) == [sid]


# ----------------------------------------------------------------------------- idempotency


def test_a_replay_is_a_duplicate_and_changes_nothing(s: S) -> None:
    d = _delta(s.fam, "hw-exact", "1/3")  # an automatic not_yet: a retry would add an attempt
    first = _one(s, d)
    sid = first["result"]["submission"]["submission_id"]
    again = _one(s, d)  # same clientEventId (this process remembers it)
    assert again["status"] == "duplicate" and again["result"] == first["result"]
    # A fresh clientEventId with the same submission key — what a restart looks like — is still a
    # duplicate: the row remembers the key durably.
    fresh = _one(s, {**d, "clientEventId": str(uuid.uuid4())})
    assert fresh["status"] == "duplicate" and fresh["result"]["submission"]["attempt"] == 1
    (row,) = _rows(s.app, s.fam.student_ref)
    assert row.attempt == 1
    assert _evidence(s.app, sid) == [sid]  # one evidence, never one per replay
    assert _audit_count(s.app, sid) == 2  # submitted + marked, once each


def test_the_disclosure_screen_fires_once_however_often_the_delta_is_replayed(s: S) -> None:
    d = _delta(s.fam, "hw-short", "My uncle hits me when nobody is home.")
    result = _one(s, d)
    assert result["status"] == "applied"
    assert result["result"]["state"] == "submitted"  # the child's screen never changes
    assert "concern" not in str(result)
    _one(s, d)
    _one(s, {**d, "clientEventId": str(uuid.uuid4())})
    (concern,) = _concerns(s.app)
    assert concern.raised_by_role == "system"
    assert concern.context_submission_id == result["result"]["submission"]["submission_id"]


def test_a_new_offline_answer_to_the_same_item_is_a_resubmission(s: S) -> None:
    _one(s, _delta(s.fam, "hw-short", "first try"))
    second = _one(s, _delta(s.fam, "hw-short", "second try", attempt=2))
    assert second["status"] == "applied"
    assert second["result"]["submission"]["attempt"] == 2
    (row,) = _rows(s.app, s.fam.student_ref)
    assert row.text == "second try"


# ------------------------------------------------------------------------------- conflicts


def test_a_final_mark_is_a_conflict_with_a_reason_and_keeps_the_mark(s: S) -> None:
    assert _submit(s, "hw-exact", EXACT).json()["state"] == "marked"  # online: met, final
    result = _one(s, _delta(s.fam, "hw-exact", "something else", attempt=2))
    assert result == {
        "clientEventId": result["clientEventId"],
        "status": "conflict",
        "version": result["version"],
        "reason": "SUBMISSION_MARKED",
    }
    (row,) = _rows(s.app, s.fam.student_ref)
    assert row.text == EXACT and row.outcome == "met"


def test_an_older_offline_answer_never_overwrites_a_newer_one(s: S) -> None:
    _submit(s, "hw-short", "sent online from the tablet")  # attempt 1 on the server
    result = _one(s, _delta(s.fam, "hw-short", "written offline earlier", attempt=1))
    assert result["status"] == "conflict" and result["reason"] == "SUBMISSION_SUPERSEDED"
    (row,) = _rows(s.app, s.fam.student_ref)
    assert row.text == "sent online from the tablet" and row.attempt == 1


def test_a_lesson_that_is_not_available_is_a_conflict(s: S) -> None:
    unstudied = _one(s, _delta(s.fam, "hw-short", objective_code="PK.G4.MATH.NOPE"))
    assert unstudied["status"] == "conflict" and unstudied["reason"] == "NOT_AVAILABLE"
    unknown_item = _one(s, _delta(s.fam, "not-an-item"))
    assert unknown_item["reason"] == "NOT_AVAILABLE"
    gone = _one(s, _delta(s.fam, "hw-short", assignment_id="asg_does_not_exist"))
    assert gone["status"] == "conflict" and gone["reason"] == "NOT_AVAILABLE"
    assert _rows(s.app, s.fam.student_ref) == []


def test_a_conflict_is_not_remembered_so_the_same_answer_can_be_sent_again(s: S) -> None:
    d = _delta(s.fam, "hw-short", "")  # empty: refused like online (422)
    assert _one(s, d)["reason"] == "INVALID"
    fixed = {**d, "payload": {**d["payload"], "text": "now with words"}}
    assert _one(s, fixed)["status"] == "applied"


def test_malformed_payloads_are_conflicts_never_guesses(s: S) -> None:
    base = _delta(s.fam, "hw-short")
    for change in (
        {"source": "teacher"},
        {"text": 42},
        {"item_ref": ""},
        {"attempt": 0},
        {"attempt": True},
        {"submitted_at": "yesterday"},
        {"submission_key": "k" * 65},
        {"objective_code": None},
    ):
        bad = {**base, "clientEventId": str(uuid.uuid4())}
        bad["payload"] = {**base["payload"], **change}
        assert _one(s, bad)["reason"] == "INVALID", change
    assert _rows(s.app, s.fam.student_ref) == []


# ------------------------------------------------------------------- consent, sharing, cohort


def test_withdrawn_consent_rejects_the_whole_batch_like_attempts(s: S) -> None:
    r = s.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": s.fam.student_ref},
        headers=s.fam.guardian,
    )
    assert r.status_code == 200
    held = _sync(s, _delta(s.fam, "hw-short"))
    assert held.status_code == 403 and held.json()["code"] == "CONSENT_REQUIRED"
    assert s.fam.student_ref not in held.text
    assert _rows(s.app, s.fam.student_ref) == []


def test_only_the_learner_may_sync_their_own_homework(s: S) -> None:
    other = _family(s.client, "other@example.com")
    forged = _sync(s, _delta(other, "hw-short"))
    assert forged.status_code == 403
    operator = _sync(s, _delta(s.fam, "hw-short"), headers=_SYSTEM)
    assert operator.status_code == 403
    missing = _delta(s.fam, "hw-short")
    missing["payload"].pop("student_ref")
    assert _sync(s, missing).status_code == 422
    assert _rows(s.app, s.fam.student_ref) == [] and _rows(s.app, other.student_ref) == []


def test_sharing_required_applies_to_an_offline_assignment_answer() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    teacher = _teacher(client, _org(client, "School A"), "t@school-a.example")
    klass = _class(client, teacher, "Grade 4")
    fam = _family(client, "class@example.com")
    assert _join(client, fam, klass["join_code"]) == 200
    asg = client.post(
        f"/v1/school/classes/{klass['class_id']}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 86400},
        headers=teacher,
    ).json()["assignment_id"]
    s = S(client, app, fam)
    client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": fam.student_ref, "scopes": ["progress_sharing"]},
        headers=fam.guardian,
    )
    d = _delta(fam, "hw-long", assignment_id=asg)
    refused = _one(s, d)
    assert refused["status"] == "conflict" and refused["reason"] == "SHARING_REQUIRED"
    assert _rows(app, fam.student_ref) == []
    # A grown-up allows sharing again: the very same queued answer now goes to the teacher.
    client.post(
        "/v1/identity/consents",
        json={
            "studentRef": fam.student_ref,
            "scopes": ["learning_data", "progress_sharing"],
            "attestation": _ATTEST,
        },
        headers=fam.guardian,
    )
    sent = _one(s, d)
    assert sent["status"] == "applied" and sent["result"]["source"] == "assignment"
    assert sent["result"]["state"] == "submitted" and sent["result"]["assignment_id"] == asg
    queue = client.get(
        f"/v1/school/classes/{klass['class_id']}/submissions",
        params={"status": "submitted"},
        headers=teacher,
    )
    assert [row["text"] for row in queue.json()["submissions"]] == [OPEN_TEXT]


def test_a_demo_lesson_is_not_available_to_a_real_learner_offline_either() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app, audience=DEMO)
    client = TestClient(app)
    fam = _family(client, "real@example.com")
    study(app, fam.student_ref)
    result = _one(S(client, app, fam), _delta(fam, "hw-short"))
    assert result["status"] == "conflict" and result["reason"] == "NOT_AVAILABLE"
    assert _rows(app, fam.student_ref) == []


def test_a_lesson_assigned_since_is_a_conflict_with_its_reason() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    teacher = _teacher(client, _org(client, "School A"), "t2@school-a.example")
    klass = _class(client, teacher, "Grade 4")
    fam = _family(client, "assigned@example.com")
    study(app, fam.student_ref)
    assert _join(client, fam, klass["join_code"]) == 200
    client.post(
        f"/v1/school/classes/{klass['class_id']}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 86400},
        headers=teacher,
    )
    result = _one(S(client, app, fam), _delta(fam, "hw-short"))
    assert result["status"] == "conflict" and result["reason"] == "LESSON_ASSIGNED"


# ----------------------------------------------------------------------- coordinator (pure)


class _NoAttempts:
    def apply_attempt(self, delta: SyncDelta) -> Status:
        raise AssertionError("not an attempt")


def test_homework_deltas_are_consent_gated_and_never_dropped_when_unwired() -> None:
    d = SyncDelta(
        "h1", DeltaType.HOMEWORK_SUBMITTED, "student:L1|homework", {"student_ref": "L1"}, 1
    )
    assert learners_touched([d]) == {"L1"}
    store = SyncStore()
    (result,), _ = DurableSyncCoordinator(store, _NoAttempts()).apply_batch([d])
    assert result.status is Status.CONFLICT and result.reason == "HOMEWORK_UNAVAILABLE"
    assert not store.is_seen("h1")  # a later re-send (once wired) is applied, not a duplicate


def test_0020_follows_the_unit_check_migration_and_matches_the_orm() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "alembic/versions/0020_homework_client_key.py"
    spec = importlib.util.spec_from_file_location("m0020", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (module.revision, module.down_revision) == (
        "0020_homework_client_key",
        "0019_unit_check_sittings",
    )
    assert len(module.revision) <= 32
    column = SubmissionRow.__table__.c.client_key
    assert column.nullable and column.type.length == 64
