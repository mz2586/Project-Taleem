"""AI Teacher — Phase 8 tests.

Unit tests cover the pure orchestration: explanation styles (deterministic arrangement of authored
content), grounding (never emits non-authored text), confidence calibration, difficulty mapping, the
adaptive plan, and the offline capability matrix (no generative AI offline). Integration tests drive
a real session to build learner state, then exercise the endpoints. SQLite + PostgreSQL-gated.
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
from taleem_core.contexts.learning.domain import ai_teacher as ait
from taleem_core.contexts.learning.domain.curriculum_view import ItemView, LessonView
from taleem_core.contexts.learning.domain.decision import (
    CurriculumGraph,
    DecisionConfig,
    ObjectiveInfo,
)
from taleem_core.contexts.learning.domain.knowledge import StudentKnowledge
from taleem_core.contexts.learning.domain.runtime import TemplatedTeachingRuntime, TurnKind
from taleem_core.contexts.learning.domain.values import Mastery, MasteryState
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_STUDENT = "ait-stu"
_REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]

_RUNTIME = TemplatedTeachingRuntime()


def _lesson() -> LessonView:
    return LessonView(
        lesson_id="L1",
        objective_code="MATH-G4-FR-01",
        title={"ur": "کسر", "en": "Fractions"},
        explanation={"ur": "کسر مکمل کا برابر حصہ ہے۔", "en": "A fraction is an equal part."},
        worked_example_steps=("ایک کیک کو چار حصوں میں کاٹیں۔", "ایک حصہ ایک بٹا چار ہے۔"),
        practice_items=(
            ItemView(
                item_ref="p1",
                objective_code="MATH-G4-FR-01",
                prompt={"ur": "کونسی کسر؟", "en": "Which fraction?"},
                options=("1/4", "4/1"),
                hints=("ٹکڑے گنیں۔",),
            ),
        ),
    )


# ---------------------------------------------------------------- unit: styles + grounding


def test_styles_are_distinct_arrangements_of_authored_content() -> None:
    lesson = _lesson()
    direct = ait.explain(lesson, ait.ExplanationStyle.DIRECT, _RUNTIME)
    worked = ait.explain(lesson, ait.ExplanationStyle.WORKED_EXAMPLE_LED, _RUNTIME)
    c2a = ait.explain(lesson, ait.ExplanationStyle.CONCRETE_TO_ABSTRACT, _RUNTIME)
    q_led = ait.explain(lesson, ait.ExplanationStyle.QUESTION_LED, _RUNTIME)

    assert len(direct) == 2  # title + explanation
    assert len(worked) == 4  # title + explanation + 2 worked steps
    # concrete-to-abstract puts worked steps BEFORE the explanation (different order).
    assert tuple(u.text for u in c2a) != tuple(u.text for u in worked)
    assert c2a[-1].text == lesson.explanation["ur"]  # explanation last (the "rule")
    # question-led opens with a question (the prompt only — never the answer).
    assert any(u.kind is TurnKind.ASK for u in q_led)


def test_every_style_is_grounded_no_hallucination() -> None:
    lesson = _lesson()
    for style in ait.ExplanationStyle:
        utterances = ait.explain(lesson, style, _RUNTIME)
        assert ait.is_grounded(lesson, utterances), style


def test_non_authored_utterance_is_flagged_ungrounded() -> None:
    from taleem_core.contexts.learning.domain.runtime import Utterance

    fabricated = (Utterance(TurnKind.PRESENT, "an invented fact not in the lesson", "ur"),)
    assert ait.is_grounded(_lesson(), fabricated) is False


def test_question_led_never_emits_the_answer() -> None:
    lesson = _lesson()
    q = ait.explain(lesson, ait.ExplanationStyle.QUESTION_LED, _RUNTIME)
    joined = " ".join(u.text for u in q)
    assert "1/4" not in joined and "4/1" not in joined  # options/answers never surfaced


# ---------------------------------------------------------------- unit: style policy + confidence


def test_style_policy_is_deterministic_and_explainable() -> None:
    assert ait.choose_style("early", 0, False) is ait.ExplanationStyle.WORKED_EXAMPLE_LED
    assert ait.choose_style("middle", 2, True) is ait.ExplanationStyle.CONCRETE_TO_ABSTRACT
    assert ait.choose_style("senior", 2, False) is ait.ExplanationStyle.QUESTION_LED
    assert ait.choose_style("middle", 0, False) is ait.ExplanationStyle.DIRECT


def test_confidence_calibration() -> None:
    assert ait.confidence_from(Mastery(0.9, 0.1), 0) is ait.TeacherConfidence.LOW  # no evidence
    assert ait.confidence_from(Mastery(0.5, 0.7), 5) is ait.TeacherConfidence.LOW  # wide estimate
    assert ait.confidence_from(Mastery(0.9, 0.1), 5) is ait.TeacherConfidence.HIGH
    assert ait.confidence_from(Mastery(0.7, 0.3), 2) is ait.TeacherConfidence.MEDIUM


def test_difficulty_mapping() -> None:
    assert ait.recommended_difficulty(MasteryState.NOT_STARTED, Mastery()) == "INTRO"
    assert ait.recommended_difficulty(MasteryState.MASTERED, Mastery(0.95, 0.1)) == "STRETCH"
    assert ait.recommended_difficulty(MasteryState.AT_RISK, Mastery(0.8, 0.2)) == "CORE"
    assert ait.recommended_difficulty(MasteryState.IN_PROGRESS, Mastery(0.3, 0.4)) == "INTRO"
    assert ait.recommended_difficulty(MasteryState.IN_PROGRESS, Mastery(0.7, 0.3)) == "CORE"


# ---------------------------------------------------------------- unit: adaptive plan + offline


def test_adaptive_plan_detects_weak_topics_and_practice() -> None:
    graph = CurriculumGraph(objectives=(ObjectiveInfo("O1", "L1", (), 0),))
    k = StudentKnowledge(student_ref="S1")
    obj = k.ensure_objective("O1")
    obj.state = MasteryState.IN_PROGRESS
    obj.mastery = Mastery(0.3, 0.4)
    obj.attempts = 2
    plan = ait.adaptive_plan(k, graph, DecisionConfig(), now=1000.0)
    assert [w.objective_code for w in plan.weak_topics] == ["O1"]
    assert plan.practice[0].difficulty == "INTRO"
    assert plan.confidence in ait.TeacherConfidence


def test_offline_capabilities_disable_generation() -> None:
    caps = ait.offline_capabilities()
    assert caps["lesson_explanation"] == "available"
    assert caps["hints"] == "available"
    assert caps["grading"] == "queued"
    assert caps["generative_rephrasing"] == "disabled_offline"  # no generative AI offline (AR-C-06)


# ---------------------------------------------------------------- integration


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


def _exercise(app: FastAPI) -> None:
    client = TestClient(app)
    _publish_fractions(app)
    h = _auth("student", _STUDENT)

    sid = client.post("/v1/learning/sessions", json={"student_ref": _STUDENT}, headers=h).json()[
        "session_id"
    ]

    # Explain: a styled, grounded, confidence-annotated, non-generative explanation.
    explain = client.post(
        f"/v1/learning/sessions/{sid}:explain",
        json={"objective_code": OBJECTIVE_CODE, "style": "worked_example_led"},
        headers=h,
    )
    assert explain.status_code == 200
    body = explain.json()
    assert body["style"] == "worked_example_led"
    assert body["grounded"] is True
    assert body["guardrail"]["generative"] is False
    assert body["guardrail"]["reveals_answer"] is False
    assert body["confidence"] in ("low", "medium", "high")
    assert len(body["utterances"]) >= 2

    # Unknown objective → 404.
    assert (
        client.post(
            f"/v1/learning/sessions/{sid}:explain",
            json={"objective_code": "DOES-NOT-EXIST"},
            headers=h,
        ).status_code
        == 404
    )

    # Plan: derived weak-topics / revision / practice / confidence.
    plan = client.get(f"/v1/learning/students/{_STUDENT}/ai-teacher/plan", headers=h)
    assert plan.status_code == 200
    pj = plan.json()
    assert "next_action" in pj and "weak_topics" in pj and "practice" in pj
    assert isinstance(pj["rationale"], list)

    # Capabilities: offline matrix.
    caps = client.get(f"/v1/learning/students/{_STUDENT}/ai-teacher/capabilities", headers=h).json()
    assert caps["offline"]["generative_rephrasing"] == "disabled_offline"

    # Security: auth required + IDOR-guarded + missing session → 404.
    assert client.get(f"/v1/learning/students/{_STUDENT}/ai-teacher/plan").status_code == 401
    assert (
        client.get("/v1/learning/students/someone-else/ai-teacher/plan", headers=h).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/learning/sessions/nope:explain",
            json={"objective_code": OBJECTIVE_CODE},
            headers=h,
        ).status_code
        == 404
    )


def test_ai_teacher_over_sqlite() -> None:
    _exercise(create_app(Settings(database_url="")))


# ---------------------------------------------------------------- PostgreSQL-gated

PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_ai_teacher_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    _exercise(create_app(Settings(database_url=PG_URL or "")))
