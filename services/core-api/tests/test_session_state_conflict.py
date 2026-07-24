"""Session state conflict + missing lesson -> clean 4xx (end-to-end validation regression).

E2E validation found ``:teach`` could return **500** two ways:
  1. Out-of-turn — after the planner chose a non-teach step (e.g. an already-mastered objective),
     the forced planning->interacting transition raised a domain ``SessionError``. Now a 409.
  2. No published lesson for the objective raised a bare ``ValueError``. Now a 404 (like :answer).
"""

from __future__ import annotations

import time

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
_REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _auth(sub: str) -> dict[str, str]:
    tok = sign_hs256({"sub": sub, "role": "student", "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {tok}"}


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


def test_teach_out_of_turn_is_409_not_500() -> None:
    app = create_app(Settings(database_url=""))
    _publish(app)
    c = TestClient(app, raise_server_exceptions=False)
    stu = "sess-conflict"
    h = _auth(stu)
    sid = c.post("/v1/learning/sessions", json={"student_ref": stu}, headers=h).json()["session_id"]
    # Skip :next (no planned decision) and force :teach -> the session is still 'planning', so the
    # planning->interacting transition is illegal. Must be a clean 409, not a 500.
    r = c.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "SESSION_STATE_CONFLICT"
    assert body["status"] == 409
    assert "traceId" in body  # RFC-9457 shape, no stack/PII


def test_teach_with_no_published_lesson_is_404_not_500() -> None:
    app = create_app(Settings(database_url=""))  # nothing published
    c = TestClient(app, raise_server_exceptions=False)
    stu = "no-lesson"
    h = _auth(stu)
    sid = c.post("/v1/learning/sessions", json={"student_ref": stu}, headers=h).json()["session_id"]
    c.post(f"/v1/learning/sessions/{sid}:next", headers=h)
    r = c.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": "NO-SUCH-OBJ"}, headers=h
    )
    assert r.status_code == 404, r.text
