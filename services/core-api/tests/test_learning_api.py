"""API tests for the learning FastAPI router (authenticated; drives the real services)."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from taleem_core.auth.dependencies import bearer_claims
from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.learning.adapters.api import LearningApiDeps, build_learning_router
from taleem_core.platform.errors import Problem
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE
from taleem_core.vertical_slice.runner import _make_clock, wire

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_STUDENT = "api-stu"


def _auth(role: str = "student", sub: str = _STUDENT) -> dict[str, str]:
    token = sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    w = wire(_make_clock())
    deps = LearningApiDeps(
        session_service=w.session_service,
        knowledge_service=w.knowledge_service,
        analytics=w.analytics,
        curriculum=w.read_model,
    )
    app = FastAPI()

    @app.exception_handler(Problem)
    async def _problem(request: Request, exc: Problem) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.to_dict(str(request.url.path)))

    app.include_router(build_learning_router(deps, bearer_claims(_SECRET)))
    return TestClient(app)


def test_requires_authentication(client: TestClient) -> None:
    assert client.post("/v1/learning/sessions", json={"student_ref": _STUDENT}).status_code == 401


def test_learner_cannot_access_another_students_data(client: TestClient) -> None:
    # IDOR guard (CTO): a student token may not read another learner's knowledge.
    r = client.get("/v1/learning/students/someone-else/knowledge", headers=_auth())
    assert r.status_code == 403


def test_session_flow_teaches_and_records(client: TestClient) -> None:
    started = client.post("/v1/learning/sessions", json={"student_ref": _STUDENT}, headers=_auth())
    assert started.status_code == 201
    session_id = started.json()["session_id"]

    nxt = client.post(f"/v1/learning/sessions/{session_id}:next", headers=_auth())
    assert nxt.status_code == 200
    assert nxt.json()["decision"] == "teach"
    assert nxt.json()["objective_code"] == OBJECTIVE_CODE

    taught = client.post(
        f"/v1/learning/sessions/{session_id}:teach",
        json={"objective_code": OBJECTIVE_CODE},
        headers=_auth(),
    )
    assert taught.status_code == 200
    item_refs = [i["item_ref"] for i in taught.json()["items"]]
    assert "p2-compare-half-quarter" in item_refs

    wrong = client.post(
        f"/v1/learning/sessions/{session_id}:answer",
        json={"objective_code": OBJECTIVE_CODE, "item_ref": "p2-compare-half-quarter", "option": 1},
        headers=_auth(),
    )
    assert wrong.status_code == 200
    assert wrong.json()["outcome"] == "incorrect"
    assert any("SMALLER" in f for f in wrong.json()["feedback"])

    for ref in ["p1-one-of-four", "p3-denominator", "p4-write-half", "p5-three-of-four"]:
        ok = client.post(
            f"/v1/learning/sessions/{session_id}:answer",
            json={"objective_code": OBJECTIVE_CODE, "item_ref": ref, "option": 0},
            headers=_auth(),
        )
        assert ok.status_code == 200
        assert ok.json()["outcome"] == "correct"

    knowledge = client.get(f"/v1/learning/students/{_STUDENT}/knowledge", headers=_auth())
    assert knowledge.status_code == 200
    assert OBJECTIVE_CODE in knowledge.json()["objectives"]

    progress = client.get(f"/v1/learning/students/{_STUDENT}/progress", headers=_auth())
    assert progress.status_code == 200
    assert progress.json()["total_attempts"] >= 5

    ended = client.post(f"/v1/learning/sessions/{session_id}:end", headers=_auth())
    assert ended.status_code == 200
    assert ended.json()["state"] in ("ended", "ended_safely")


def test_unknown_session_is_404(client: TestClient) -> None:
    assert client.post("/v1/learning/sessions/nope:next", headers=_auth()).status_code == 404


def test_unknown_student_knowledge_is_404(client: TestClient) -> None:
    # 'ghost' matches the token sub so IDOR passes; the student simply has no record yet.
    assert (
        client.get("/v1/learning/students/ghost/knowledge", headers=_auth(sub="ghost")).status_code
        == 404
    )
