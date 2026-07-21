"""FastAPI adapter for the learning context (LEARNING_DOMAIN_MODEL §8).

Session + knowledge endpoints. Every endpoint is authenticated (bearer JWT) and authorized
(deny-by-default PDP); a learner may only reach their own data (IDOR guard). Governance-gated: real
child-facing use awaits the Phase-1.5 decisions. Request models are module-scope (FastAPI + future
annotations).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ....auth.dependencies import authorize, require_owner_or
from ....auth.jwt_verifier import Claims
from ..application.analytics import LearningAnalytics
from ..application.knowledge_service import KnowledgeService
from ..application.ports import CurriculumReadModel
from ..application.session_service import SessionService
from ..domain.decision import Decision, DecisionKind
from ..domain.session import Session, SessionState

_STUDENT_ONLY: tuple[str, ...] = ()  # learners only; no privileged override for operating a session
_MENTOR = ("mentor",)


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


class HintIn(BaseModel):
    objective_code: str
    item_ref: str
    hint_level: int = 0


@dataclass
class LearningApiDeps:
    session_service: SessionService
    knowledge_service: KnowledgeService
    analytics: LearningAnalytics
    curriculum: CurriculumReadModel


def build_learning_router(
    deps: LearningApiDeps, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    router = APIRouter(prefix="/v1/learning", tags=["learning"])

    def _session_or_404(session_id: str, claims: Claims) -> Session:
        session = deps.session_service.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail=f"session not found: {session_id}")
        # IDOR: a learner may only act on their own session.
        require_owner_or(claims, session.student_ref, privileged_roles=_STUDENT_ONLY)
        return session

    @router.post("/sessions", status_code=201)
    def start_session(
        body: StartSessionIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        require_owner_or(claims, body.student_ref, privileged_roles=_STUDENT_ONLY)
        session = deps.session_service.start(body.student_ref, correlation_id="")
        return {"session_id": session.session_id, "state": session.state.value}

    @router.post("/sessions/{session_id}:next")
    def next_decision(
        session_id: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        session = _session_or_404(session_id, claims)
        decision = deps.session_service.plan_next(session)
        return {
            "decision": decision.kind.value,
            "objective_code": decision.objective_code,
            "rationale": [r.note for r in decision.rationale],
        }

    @router.post("/sessions/{session_id}:teach")
    def teach(
        session_id: str, body: TeachIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        session = _session_or_404(session_id, claims)
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
    def answer(
        session_id: str, body: AnswerIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        session = _session_or_404(session_id, claims)
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

    @router.post("/sessions/{session_id}:hint")
    def hint(
        session_id: str, body: HintIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        # The next AUTHORED graduated hint (never the answer first). Content comes from the approved
        # published lesson only; if the ladder is exhausted the client offers re-explanation/help.
        authorize(claims, "operate", "learning.session")
        _session_or_404(session_id, claims)
        lesson = deps.curriculum.lesson_for(body.objective_code)
        if lesson is None:
            raise HTTPException(status_code=404, detail="lesson not found")
        item = next((i for i in lesson.practice_items if i.item_ref == body.item_ref), None)
        if item is None:
            raise HTTPException(status_code=404, detail="item not found")
        level = body.hint_level
        has_hint = 0 <= level < len(item.hints)
        return {
            "hint": item.hints[level] if has_hint else None,
            "level": level,
            "exhausted": level >= len(item.hints),
        }

    @router.post("/sessions/{session_id}:end")
    def end_session(session_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        session = _session_or_404(session_id, claims)
        # Already-terminal / escalated sessions are not re-ended (CTO M1/M2: never mask an
        # escalation as a normal completion, never raise on an out-of-order end).
        if session.state in (
            SessionState.ENDED,
            SessionState.ENDED_SAFELY,
            SessionState.ESCALATED,
        ):
            return {"state": session.state.value, "interactions": len(session.interactions)}
        if session.state is SessionState.INTERACTING:
            deps.session_service.complete_objective(session)
        ended = deps.session_service.end(session)
        return {"state": ended.state.value, "interactions": len(ended.interactions)}

    @router.get("/students/{student_ref}/knowledge")
    def knowledge(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        require_owner_or(claims, student_ref, privileged_roles=_MENTOR)
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
    def progress(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        require_owner_or(claims, student_ref, privileged_roles=_MENTOR)
        return deps.analytics.progress_summary(student_ref).to_dict()

    return router
