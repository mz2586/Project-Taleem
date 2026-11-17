"""FastAPI router for the AI Teacher (Phase 8).

Two derived, explainable surfaces over existing data (no new child-data table):
  POST /v1/learning/sessions/{id}:explain   — a styled, grounded, confidence-annotated explanation
  POST /v1/learning/sessions/{id}:ask       — ask the teacher: answered by quoting the published
                                              lesson (tap intents always; typed questions only
                                              behind a flag, a disclosure screen and consent)
  GET  /v1/learning/students/{ref}/ai-teacher/plan          — the adaptive plan (weak topics, …)
  GET  /v1/learning/students/{ref}/ai-teacher/capabilities  — the offline capability matrix

Authenticated + authorized (operate learning.session / read learning.knowledge) + IDOR-guarded, in
line with the existing session + student routers. The AI Teacher is templated. The Phase D
generative tier (flag-gated, default OFF; consent- and kill-switch-gated) can only add a separate,
safety-gated ``generation`` block to ``:explain`` — the request shape is unchanged, and no real
model provider is connected in this build (FD-03).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ....auth.dependencies import authorize, require_owner_or
from ....auth.jwt_verifier import Claims
from ....platform.errors import Problem
from ..application.ai_teacher_service import AITeacherService, AskRefusedError
from ..application.session_service import SessionService

_STUDENT_ONLY: tuple[str, ...] = ()
_MENTOR = ("mentor",)


class ExplainIn(BaseModel):
    objective_code: str = Field(min_length=1)
    style: str | None = None
    grade_band: str = "middle"
    locale: str = "ur"


class AskIn(BaseModel):
    objective_code: str = Field(min_length=1, max_length=64)
    intent: str = Field(min_length=1, max_length=32)
    # Child free text: length-capped here and in the service (lesson_qa.QUESTION_MAX_CHARS).
    question: str | None = Field(default=None, max_length=300)
    locale: str = Field(default="ur", max_length=35)


_ASK_REFUSAL_STATUS = {
    "UNKNOWN_INTENT": 422,
    "QUESTION_REQUIRED": 422,
    "QUESTION_TOO_LONG": 422,
    "FREE_TEXT_DISABLED": 403,
}


def build_ai_teacher_router(
    teacher: AITeacherService,
    sessions: SessionService,
    claims_dependency: Callable[..., Claims],
) -> APIRouter:
    router = APIRouter(prefix="/v1/learning", tags=["ai-teacher"])

    @router.post("/sessions/{session_id}:explain")
    def explain(
        session_id: str,
        body: ExplainIn,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        session = sessions.get_session(session_id)
        if session is None:
            raise Problem(404, "SESSION_NOT_FOUND", "No such session", session_id)
        require_owner_or(claims, session.student_ref, privileged_roles=_STUDENT_ONLY)
        result = teacher.explain(
            session.student_ref,
            body.objective_code,
            style=body.style,
            grade_band=body.grade_band,
            locale=body.locale,
        )
        if result is None:
            raise Problem(
                404, "NO_PUBLISHED_LESSON", "No published lesson for objective", body.objective_code
            )
        return result

    @router.post("/sessions/{session_id}:ask")
    def ask(
        session_id: str,
        body: AskIn,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        session = sessions.get_session(session_id)
        if session is None:
            raise Problem(404, "SESSION_NOT_FOUND", "No such session", session_id)
        require_owner_or(claims, session.student_ref, privileged_roles=_STUDENT_ONLY)
        try:
            result = teacher.ask(
                session.student_ref,
                body.objective_code,
                intent=body.intent,
                ask_id=f"ask_{uuid.uuid4().hex}",
                question=body.question,
                locale=body.locale,
            )
        except AskRefusedError as exc:
            raise Problem(
                _ASK_REFUSAL_STATUS.get(exc.code, 422), exc.code, "Question not accepted", ""
            ) from None
        if result is None:
            raise Problem(
                404, "NO_PUBLISHED_LESSON", "No published lesson for objective", body.objective_code
            )
        return result

    @router.get("/students/{student_ref}/ai-teacher/plan")
    def plan(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        require_owner_or(claims, student_ref, privileged_roles=_MENTOR)
        return teacher.plan(student_ref)

    @router.get("/students/{student_ref}/ai-teacher/capabilities")
    def capabilities(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        require_owner_or(claims, student_ref, privileged_roles=_MENTOR)
        return teacher.capabilities()

    return router
