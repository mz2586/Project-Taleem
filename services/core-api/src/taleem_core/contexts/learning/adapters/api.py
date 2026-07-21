"""FastAPI adapter for the learning context (LEARNING_DOMAIN_MODEL §8).

Contract-first-ish session + knowledge endpoints. In production every endpoint is authenticated,
authorized (deny-by-default PDP), audited, and gated on Phase-1.5 governance; here it exposes the
real services for the vertical slice and its API tests. Request models are at module scope (FastAPI
+ ``from __future__ import annotations`` requires it, or bodies parse as query params).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..application.analytics import LearningAnalytics
from ..application.knowledge_service import KnowledgeService
from ..application.ports import CurriculumReadModel
from ..application.session_service import SessionService
from ..domain.decision import DecisionKind


class StartSessionIn(BaseModel):
    student_ref: str


class TeachIn(BaseModel):
    objective_code: str


class AnswerIn(BaseModel):
    objective_code: str
    item_ref: str
    option: int
    hints_used: int = 0
    self_confidence: float | None = None


@dataclass
class LearningApiDeps:
    session_service: SessionService
    knowledge_service: KnowledgeService
    analytics: LearningAnalytics
    curriculum: CurriculumReadModel


def build_learning_router(deps: LearningApiDeps) -> APIRouter:
    router = APIRouter(prefix="/v1/learning", tags=["learning"])

    def _session_or_404(session_id: str) -> Any:
        session = deps.session_service._sessions.get(session_id)  # noqa: SLF001 (adapter access)
        if session is None:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
        return session

    @router.post("/sessions", status_code=201)
    def start_session(body: StartSessionIn) -> dict[str, Any]:
        session = deps.session_service.start(body.student_ref)
        return {"session_id": session.session_id, "state": session.state.value}

    @router.post("/sessions/{session_id}:next")
    def next_decision(session_id: str) -> dict[str, Any]:
        session = _session_or_404(session_id)
        decision = deps.session_service.plan_next(session)
        return {
            "decision": decision.kind.value,
            "objective_code": decision.objective_code,
            "rationale": [r.note for r in decision.rationale],
        }

    @router.post("/sessions/{session_id}:teach")
    def teach(session_id: str, body: TeachIn) -> dict[str, Any]:
        session = _session_or_404(session_id)
        from ..domain.decision import Decision

        decision = Decision(kind=DecisionKind.TEACH, objective_code=body.objective_code)
        utterances, lesson = deps.session_service.teach(session, decision)
        return {
            "utterances": [{"kind": u.kind.value, "text": u.text} for u in utterances],
            "items": [
                {"item_ref": it.item_ref, "prompt": it.prompt, "options": list(it.options)}
                for it in lesson.practice_items
            ],
        }

    @router.post("/sessions/{session_id}:answer")
    def answer(session_id: str, body: AnswerIn) -> dict[str, Any]:
        session = _session_or_404(session_id)
        lesson = deps.curriculum.lesson_for(body.objective_code)
        if lesson is None:
            raise HTTPException(status_code=404, detail="lesson not found")
        item = next((i for i in lesson.practice_items if i.item_ref == body.item_ref), None)
        if item is None:
            raise HTTPException(status_code=404, detail="item not found")
        turn = deps.session_service.submit_answer(
            session,
            lesson,
            item,
            answer_option=body.option,
            decision_kind=DecisionKind.CONTINUE,
            hints_used=body.hints_used,
            self_confidence=body.self_confidence,
        )
        return {
            "outcome": turn.result.outcome.value,
            "mastery": round(turn.result.mastery_after.value, 3),
            "state": turn.result.state_after.value,
            "post_decision": turn.post_decision.kind.value,
            "confirmed_misconceptions": turn.result.confirmed_misconceptions,
            "cleared_misconceptions": turn.result.cleared_misconceptions,
            "feedback": [u.text for u in turn.feedback],
        }

    @router.post("/sessions/{session_id}:end")
    def end_session(session_id: str) -> dict[str, Any]:
        session = _session_or_404(session_id)
        if session.state.value in ("teaching", "interacting"):
            deps.session_service.complete_objective(session)
        ended = deps.session_service.end(session)
        return {"state": ended.state.value, "interactions": len(ended.interactions)}

    @router.get("/students/{student_ref}/knowledge")
    def knowledge(student_ref: str) -> dict[str, Any]:
        snap = deps.knowledge_service.snapshot(student_ref)
        if snap is None:
            raise HTTPException(status_code=404, detail="student not found")
        return {
            "student_ref": student_ref,
            "objectives": {
                code: {
                    "mastery": round(o.mastery.value, 3),
                    "uncertainty": round(o.mastery.uncertainty, 3),
                    "state": o.state.value,
                }
                for code, o in snap.objectives.items()
            },
        }

    @router.get("/students/{student_ref}/progress")
    def progress(student_ref: str) -> dict[str, Any]:
        return deps.analytics.progress_summary(student_ref).to_dict()

    return router
