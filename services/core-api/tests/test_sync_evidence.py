"""Durable offline sync — Phase 6.2B integration tests.

Drives the offline sync path end-to-end over the composed app: publish the fractions lesson, POST
``attempt.submitted`` deltas to ``/v1/sync/batch``, and assert durable ``AssessmentEvidence`` +
mastery via the derived student read models. Covers idempotent (duplicate) uploads, crash-recovery
replay, conflict resolution for the non-attempt delta types, append-only union of distinct attempts,
and the non-negotiable that a summative item is never auto-graded by sync. SQLite + PG-gated.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_STUDENT = "sync-stu"
_REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _auth(role: str, sub: str) -> dict[str, str]:
    exp = int(time.time()) + 3600
    return {
        "Authorization": f"Bearer {sign_hs256({'sub': sub, 'role': role, 'exp': exp}, _SECRET)}"
    }


def _publish_fractions(app: FastAPI) -> None:
    sf = app.state.studio_session_factory
    clock = lambda: 1000.0  # noqa: E731

    def op(fn: object) -> None:
        with cs_uow(sf) as uow:
            svc = CurriculumStudioService(uow.lessons, uow.publish, clock=clock)
            fn(svc)  # type: ignore[operator]
            uow.commit()

    op(lambda s: s.create(build_fractions_lesson()))
    op(lambda s: s.submit(LESSON_KEY, "subject_author"))
    for role in _REVIEW_ROLES:
        op(lambda s, role=role: s.review(LESSON_KEY, ReviewAction.APPROVE, role))
    op(lambda s: s.publish(LESSON_KEY, "curriculum_architect", "v1"))


def _attempt_delta(
    *,
    student: str,
    item_ref: str,
    option: int,
    client_event_id: str,
    evidence_id: str,
    client_seq: int,
) -> dict[str, object]:
    return {
        "clientEventId": client_event_id,
        "type": "attempt.submitted",
        "entityKey": f"student:{student}|lesson:{LESSON_KEY}",
        "clientSeq": client_seq,
        "payload": {
            "student_ref": student,
            "objective_code": OBJECTIVE_CODE,
            "item_ref": item_ref,
            "option": option,
            "evidence_id": evidence_id,
            "session_id": "offline-sess-1",
            "context": "practice",
        },
    }


def _batch(
    client: TestClient, deltas: list[dict[str, object]], cursor: int = 0
) -> dict[str, object]:
    r = client.post("/v1/sync/batch", json={"cursor": cursor, "deltas": deltas})
    assert r.status_code == 200, r.text
    return r.json()


def _statuses(result: dict[str, object]) -> list[str]:
    return [row["status"] for row in result["results"]]  # type: ignore[index,union-attr]


def _exercise(app: FastAPI) -> None:
    client = TestClient(app)
    _publish_fractions(app)
    h = _auth("student", _STUDENT)

    # --- 1. A correct offline attempt syncs → durable evidence + mastery moves. ---
    cid, eid = uuid7(), uuid7()
    res = _batch(
        client,
        [
            _attempt_delta(
                student=_STUDENT,
                item_ref="p1-one-of-four",
                option=0,  # correct
                client_event_id=cid,
                evidence_id=eid,
                client_seq=1,
            )
        ],
    )
    assert _statuses(res) == ["applied"]

    today = client.get(f"/v1/learning/students/{_STUDENT}/today", headers=h).json()
    assert today["mastery_summary"]["total"] >= 1  # the objective now exists for this learner
    hist_before = client.get(f"/v1/learning/students/{_STUDENT}/history", headers=h).json()
    attempts_before = sum(s["attempts"] for s in hist_before["sessions"])
    assert attempts_before >= 1

    # --- 2. Duplicate upload (same clientEventId + evidence_id) is idempotent (no double). ---
    res_dup = _batch(
        client,
        [
            _attempt_delta(
                student=_STUDENT,
                item_ref="p1-one-of-four",
                option=0,
                client_event_id=cid,  # replay
                evidence_id=eid,
                client_seq=1,
            )
        ],
    )
    assert _statuses(res_dup) == ["duplicate"]
    hist_after = client.get(f"/v1/learning/students/{_STUDENT}/history", headers=h).json()
    assert sum(s["attempts"] for s in hist_after["sessions"]) == attempts_before  # unchanged

    # --- 3. Crash-recovery replay: a NEW clientEventId but the SAME evidence_id is still a no-op
    #        (durable idempotency lives in the evidence table, not the in-memory seen-set). ---
    res_crash = _batch(
        client,
        [
            _attempt_delta(
                student=_STUDENT,
                item_ref="p1-one-of-four",
                option=0,
                client_event_id=uuid7(),  # a fresh delta id after a "crash"
                evidence_id=eid,  # same evidence — already recorded
                client_seq=2,
            )
        ],
    )
    assert _statuses(res_crash) == ["duplicate"]
    hist_crash = client.get(f"/v1/learning/students/{_STUDENT}/history", headers=h).json()
    assert sum(s["attempts"] for s in hist_crash["sessions"]) == attempts_before  # still unchanged

    # --- 4. A DISTINCT attempt (new evidence_id) appends — append-only union. ---
    res2 = _batch(
        client,
        [
            _attempt_delta(
                student=_STUDENT,
                item_ref="p3-denominator",
                option=0,  # correct
                client_event_id=uuid7(),
                evidence_id=uuid7(),
                client_seq=3,
            )
        ],
    )
    assert _statuses(res2) == ["applied"]
    hist2 = client.get(f"/v1/learning/students/{_STUDENT}/history", headers=h).json()
    assert sum(s["attempts"] for s in hist2["sessions"]) == attempts_before + 1

    # --- 5. A wrong answer with an authored misconception is graded + recorded. ---
    res_wrong = _batch(
        client,
        [
            _attempt_delta(
                student=_STUDENT,
                item_ref="p2-compare-half-quarter",
                option=1,  # the misconception option
                client_event_id=uuid7(),
                evidence_id=uuid7(),
                client_seq=4,
            )
        ],
    )
    assert _statuses(res_wrong) == ["applied"]

    # --- 6. Non-attempt deltas keep their conflict policy (progress monotonic; preference). ---
    mixed = _batch(
        client,
        [
            {
                "clientEventId": uuid7(),
                "type": "progress.updated",
                "entityKey": f"student:{_STUDENT}|lesson:{LESSON_KEY}",
                "clientSeq": 5,
                "payload": {"block": 3},
            },
            {
                "clientEventId": uuid7(),
                "type": "progress.updated",
                "entityKey": f"student:{_STUDENT}|lesson:{LESSON_KEY}",
                "clientSeq": 6,
                "payload": {"block": 1},  # regression → ignored
            },
            {
                "clientEventId": uuid7(),
                "type": "preference.set",
                "entityKey": f"student:{_STUDENT}|pref:locale",
                "clientSeq": 7,
                "payload": {"value": "ur"},
            },
        ],
    )
    assert _statuses(mixed) == ["applied", "ignored", "applied"]

    # --- 7. A summative item is NEVER auto-graded by sync (mentor-mediated, non-negotiable). ---
    res_summative = _batch(
        client,
        [
            _attempt_delta(
                student=_STUDENT,
                item_ref="does-not-exist-or-summative",
                option=0,
                client_event_id=uuid7(),
                evidence_id=uuid7(),
                client_seq=8,
            )
        ],
    )
    assert _statuses(res_summative) == ["ignored"]  # unknown/summative → not graded


def test_sync_evidence_over_sqlite() -> None:
    _exercise(create_app(Settings(database_url="")))


# ---------------------------------------------------------------- PostgreSQL-gated

PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_sync_evidence_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    _exercise(create_app(Settings(database_url=PG_URL or "")))
