"""Integration tests for the student-facing backend APIs (Phase 5.5).

Seeds a published lesson, drives a real learning session (generating evidence + mastery + events),
then exercises every derived query endpoint. Runs over the composed app: SQLite by default, and a
PostgreSQL-gated variant (CS_DATABASE_URL) over the real migrated schema.
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
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_STUDENT = "itest-stu"
_REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _exp() -> int:
    return int(time.time()) + 3600


def _auth(role: str, sub: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {sign_hs256({'sub': sub, 'role': role, 'exp': _exp()}, _SECRET)}"
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


def _drive_session(client: TestClient, student: str) -> str:
    """Run a full session to completion (generates evidence + mastery). Returns the objective."""
    h = _auth("student", student)
    sid = client.post("/v1/learning/sessions", json={"student_ref": student}, headers=h).json()[
        "session_id"
    ]
    objective = OBJECTIVE_CODE
    for _ in range(15):
        d = client.post(f"/v1/learning/sessions/{sid}:next", headers=h).json()
        if d["decision"] in ("complete", "rest") or not d["objective_code"]:
            break
        objective = d["objective_code"]
        taught = client.post(
            f"/v1/learning/sessions/{sid}:teach", json={"objective_code": objective}, headers=h
        ).json()
        for item in taught["items"]:
            client.post(
                f"/v1/learning/sessions/{sid}:answer",
                json={"objective_code": objective, "item_ref": item["item_ref"], "option": 0},
                headers=h,
            )
    client.post(f"/v1/learning/sessions/{sid}:end", headers=h)
    return objective


def _exercise(app: FastAPI) -> None:
    client = TestClient(app)
    _publish_fractions(app)
    objective = _drive_session(client, _STUDENT)
    h = _auth("student", _STUDENT)
    base = f"/v1/learning/students/{_STUDENT}"

    today = client.get(f"{base}/today", headers=h)
    assert today.status_code == 200
    assert today.json()["mastery_summary"]["total"] >= 1

    homework = client.get(f"{base}/homework", headers=h).json()
    assert any(
        i["objective_code"] == objective for i in homework["items"]
    )  # from the lesson's homework set

    assessments = client.get(f"{base}/assessments", headers=h).json()
    assert any(a["type"] == "formative" for a in assessments["assessments"])

    reviews = client.get(f"{base}/reviews", headers=h)
    assert reviews.status_code == 200 and "due_count" in reviews.json()

    timetable = client.get(f"{base}/timetable", headers=h).json()
    assert isinstance(timetable["days"], list)

    notifications = client.get(f"{base}/notifications", headers=h)
    assert notifications.status_code == 200 and "unread" in notifications.json()

    achievements = client.get(f"{base}/achievements", headers=h).json()
    assert achievements["mastered_count"] >= 1  # the session drove the objective to mastery

    history = client.get(f"{base}/history", headers=h).json()
    assert len(history["sessions"]) >= 1 and len(history["lessons"]) >= 1

    recs = client.get(f"{base}/recommendations", headers=h).json()
    assert isinstance(recs["recommendations"], list)

    # Hint: authored graduated hint (p2 has hints); returns approved content, never the answer.
    sid = client.post("/v1/learning/sessions", json={"student_ref": _STUDENT}, headers=h).json()[
        "session_id"
    ]
    hint = client.post(
        f"/v1/learning/sessions/{sid}:hint",
        json={"objective_code": objective, "item_ref": "p2-compare-half-quarter", "hint_level": 0},
        headers=h,
    )
    assert hint.status_code == 200 and "exhausted" in hint.json()

    # Security: auth required + IDOR-guarded.
    assert client.get(f"{base}/today").status_code == 401
    assert client.get("/v1/learning/students/someone-else/today", headers=h).status_code == 403


def test_student_apis_over_sqlite() -> None:
    _exercise(create_app(Settings(database_url="")))


# ---------------------------------------------------------------- PostgreSQL-gated

PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_student_apis_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    _exercise(create_app(Settings(database_url=PG_URL or "")))
