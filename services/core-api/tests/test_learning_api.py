"""API tests for the learning FastAPI router (drives the real services over the slice wiring)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.contexts.learning.adapters.api import LearningApiDeps, build_learning_router
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE
from taleem_core.vertical_slice.runner import _make_clock, wire


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
    app.include_router(build_learning_router(deps))
    return TestClient(app)


def test_session_flow_teaches_and_records(client: TestClient) -> None:
    started = client.post("/v1/learning/sessions", json={"student_ref": "api-stu"})
    assert started.status_code == 201
    session_id = started.json()["session_id"]

    nxt = client.post(f"/v1/learning/sessions/{session_id}:next")
    assert nxt.status_code == 200
    assert nxt.json()["decision"] == "teach"
    assert nxt.json()["objective_code"] == OBJECTIVE_CODE

    taught = client.post(
        f"/v1/learning/sessions/{session_id}:teach", json={"objective_code": OBJECTIVE_CODE}
    )
    assert taught.status_code == 200
    item_refs = [i["item_ref"] for i in taught.json()["items"]]
    assert "p2-compare-half-quarter" in item_refs

    # A wrong answer to the comparison item returns the authored misconception correction.
    wrong = client.post(
        f"/v1/learning/sessions/{session_id}:answer",
        json={"objective_code": OBJECTIVE_CODE, "item_ref": "p2-compare-half-quarter", "option": 1},
    )
    assert wrong.status_code == 200
    assert wrong.json()["outcome"] == "incorrect"
    assert any("SMALLER" in f for f in wrong.json()["feedback"])

    # Correct answers move mastery upward and are recorded.
    for ref in ["p1-one-of-four", "p3-denominator", "p4-write-half", "p5-three-of-four"]:
        ok = client.post(
            f"/v1/learning/sessions/{session_id}:answer",
            json={"objective_code": OBJECTIVE_CODE, "item_ref": ref, "option": 0},
        )
        assert ok.status_code == 200
        assert ok.json()["outcome"] == "correct"

    knowledge = client.get("/v1/learning/students/api-stu/knowledge")
    assert knowledge.status_code == 200
    assert OBJECTIVE_CODE in knowledge.json()["objectives"]

    progress = client.get("/v1/learning/students/api-stu/progress")
    assert progress.status_code == 200
    assert progress.json()["total_attempts"] >= 5

    ended = client.post(f"/v1/learning/sessions/{session_id}:end")
    assert ended.status_code == 200
    assert ended.json()["state"] in ("ended", "ended_safely")


def test_unknown_session_is_404(client: TestClient) -> None:
    assert client.post("/v1/learning/sessions/nope:next").status_code == 404


def test_unknown_student_knowledge_is_404(client: TestClient) -> None:
    assert client.get("/v1/learning/students/ghost/knowledge").status_code == 404
