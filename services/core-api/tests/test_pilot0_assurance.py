"""Pilot 0 assurance validation — Phase 11.

Codifies the *automatable* portions of the Pilot 0 assurance pass (security / offline / load /
AI-safety validation) as repeatable, citable checks over the composed app. This does NOT replace the
human assurance activities (external pentest, on-device a11y audit, the live safeguarding drill) —
those remain operational Pilot 0 activities — but it proves the platform-level invariants a pilot
depends on. No new product features; no domain-model changes. SQLite + PostgreSQL-gated.
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
from taleem_core.contexts.learning.domain.offline_package import signing_payload
from taleem_core.main import create_app
from taleem_core.platform import ed25519
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_STUDENT = "p0-stu"
_REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]

# Keys that would indicate raw child PII (C3) leaking into a response — must NEVER appear.
_PII_KEYS = ("name", "full_name", "email", "phone", "dob", "birth", "address", "guardian_name")


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


def _attempt(student: str, item_ref: str, option: int, seq: int) -> dict[str, object]:
    return {
        "clientEventId": uuid7(),
        "type": "attempt.submitted",
        "entityKey": f"student:{student}|item:{item_ref}",
        "clientSeq": seq,
        "payload": {
            "student_ref": student,
            "objective_code": OBJECTIVE_CODE,
            "item_ref": item_ref,
            "option": option,
            "evidence_id": uuid7(),
            "session_id": "p0-sess",
            "context": "practice",
        },
    }


# ---------------------------------------------------------------- security validation


def _assert_security(client: TestClient) -> None:
    h = _auth("student", _STUDENT)
    # Auth required (deny-by-default): unauthenticated protected reads → 401.
    assert client.get(f"/v1/learning/students/{_STUDENT}/today").status_code == 401
    assert client.get(f"/v1/learning/students/{_STUDENT}/ai-teacher/plan").status_code == 401
    # IDOR-guarded: a learner cannot read another learner's data → 403.
    assert client.get("/v1/learning/students/someone-else/today", headers=h).status_code == 403
    assert (
        client.get("/v1/learning/students/someone-else/ai-teacher/plan", headers=h).status_code
        == 403
    )


def _assert_no_child_pii(client: TestClient) -> None:
    h = _auth("student", _STUDENT)
    for path in (
        f"/v1/learning/students/{_STUDENT}/today",
        f"/v1/learning/students/{_STUDENT}/history",
        f"/v1/learning/students/{_STUDENT}/ai-teacher/plan",
        f"/v1/learning/students/{_STUDENT}/knowledge",
    ):
        body = client.get(path, headers=h).text.lower()
        for key in _PII_KEYS:
            assert f'"{key}"' not in body, f"possible PII key {key} in {path}"


# ---------------------------------------------------------------- offline validation


def _assert_offline_signed(client: TestClient) -> None:
    h = _auth("student", _STUDENT)
    pkg = client.get(f"/v1/offline/packages/{LESSON_KEY}", headers=h).json()
    m = pkg["manifest"]
    # Package is Ed25519-signed and the signature verifies against the published public key.
    assert m["signature"] and m["signing_key_id"]
    key = next(
        k
        for k in client.get("/v1/offline/signing-keys", headers=h).json()["keys"]
        if k["key_id"] == m["signing_key_id"]
    )
    payload = signing_payload(m["package_id"], m["version"], m["content_hash"])
    assert ed25519.verify(
        bytes.fromhex(m["signature"]), payload, bytes.fromhex(key["public_key_hex"])
    )
    # No answer keys ship to the device (child-safe offline content).
    assert "correct_option" not in str(pkg["content"])


# ---------------------------------------------------------------- load / integrity validation


def _sync(client: TestClient, deltas: list[dict[str, object]]) -> list[str]:
    r = client.post("/v1/sync/batch", json={"cursor": 0, "deltas": deltas})
    assert r.status_code == 200, r.text
    return [row["status"] for row in r.json()["results"]]


def _assert_load_idempotent(client: TestClient) -> None:
    # Load validation: a batch of 100 distinct offline attempts all apply exactly once...
    batch = [_attempt(_STUDENT, "p1-one-of-four", 0, i) for i in range(100)]
    statuses = _sync(client, batch)
    assert statuses.count("applied") == 100
    # ...and replaying the SAME batch is fully idempotent (no double-count).
    replay = _sync(client, batch)
    assert replay.count("duplicate") == 100
    h = _auth("student", _STUDENT)
    hist = client.get(f"/v1/learning/students/{_STUDENT}/history", headers=h).json()
    assert sum(s["attempts"] for s in hist["sessions"]) == 100  # exactly once each


def _assert_summative_never_auto_graded(client: TestClient) -> None:
    # A summative / unknown item is never auto-graded by sync (mentor-mediated non-negotiable).
    statuses = _sync(client, [_attempt(_STUDENT, "summative-or-unknown", 0, 999)])
    assert statuses == ["ignored"]


# ---------------------------------------------------------------- AI safety validation


def _assert_ai_safety(client: TestClient) -> None:
    h = _auth("student", _STUDENT)
    sid = client.post("/v1/learning/sessions", json={"student_ref": _STUDENT}, headers=h).json()[
        "session_id"
    ]
    explain = client.post(
        f"/v1/learning/sessions/{sid}:explain",
        json={"objective_code": OBJECTIVE_CODE},
        headers=h,
    ).json()
    g = explain["guardrail"]
    assert g["generative"] is False  # never generative
    assert g["reveals_answer"] is False  # never leaks the answer
    assert explain["grounded"] is True  # only authored content
    caps = client.get(f"/v1/learning/students/{_STUDENT}/ai-teacher/capabilities", headers=h).json()
    assert caps["offline"]["generative_rephrasing"] == "disabled_offline"  # AR-C-06


# ---------------------------------------------------------------- the pass


def _run_assurance(app: FastAPI) -> None:
    client = TestClient(app)
    _publish_fractions(app)
    _assert_security(client)
    _assert_no_child_pii(client)
    _assert_offline_signed(client)
    _assert_load_idempotent(client)
    _assert_summative_never_auto_graded(client)
    _assert_ai_safety(client)


def test_pilot0_assurance_over_sqlite() -> None:
    _run_assurance(create_app(Settings(database_url="")))


# ---------------------------------------------------------------- PostgreSQL-gated

PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_pilot0_assurance_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    _run_assurance(create_app(Settings(database_url=PG_URL or "")))
