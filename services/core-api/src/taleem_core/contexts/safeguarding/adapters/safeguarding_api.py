"""FastAPI router for safeguarding concerns (``/v1/safeguarding``).

- ``POST /concerns`` — a ``student`` (about themselves), a ``guardian`` (about their own learner)
  or a ``teacher`` (about a learner in their own class, optionally naming a ``submissionId``)
  raises a concern. Not behind the learner consent gate, and not on the kill switch's child-facing
  list: it is a safety channel and stays open when learning is halted (pinned by a test).
- ``GET /my-concerns`` — a guardian's own raised concerns, coarse status only.
- ``GET /queue``, ``GET /concerns/{id}`` and the triage actions — ``safeguarding_lead`` only.
- ``GET /concerns/{id}/context`` — the flagged homework behind a concern (the child's text, item
  prompt, lesson title, matched phrase entries); ``safeguarding_lead`` only, every read audited.

The router is mounted behind the staff gate, so a suspended lead's live token stops working on its
next request. Raising is rate limited per subject, generously: a flood must not bury real reports,
and a child who hits the limit is told to find a grown-up near them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform.errors import forbidden
from ...identity.adapters.rate_limit import Limiter
from ..application.service import SafeguardingService
from ..domain.model import MAX_FREE_TEXT, MAX_LESSON_ID, MAX_NOTE, MAX_SCREEN

RAISE_LIMIT = 20
RAISE_WINDOW_SECONDS = 3600.0


class ConcernContextIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    screen: str | None = Field(default=None, max_length=MAX_SCREEN * 4)
    lesson_id: str | None = Field(default=None, alias="lessonId", max_length=MAX_LESSON_ID)


class RaiseConcernIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    category: str = Field(min_length=1, max_length=32)
    # Bounded at the edge as well as in the domain (which counts characters after normalisation).
    text: str | None = Field(default=None, max_length=MAX_FREE_TEXT * 2)
    context: ConcernContextIn | None = None
    # Guardian / teacher: which learner. A learner token may omit it or repeat its own subject;
    # naming anyone else is refused.
    student_ref: str | None = Field(default=None, alias="studentRef", max_length=64)
    # Teacher only: the homework submission that prompted the concern.
    submission_id: str | None = Field(default=None, alias="submissionId", max_length=64)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=MAX_NOTE * 2)


class EscalateIn(BaseModel):
    reason: str = Field(min_length=1, max_length=MAX_NOTE * 2)


class ResolveIn(BaseModel):
    outcome: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=MAX_NOTE * 2)


def build_safeguarding_router(
    service: SafeguardingService,
    claims_dependency: Callable[..., Claims],
    *,
    raise_limiter: Limiter,
) -> APIRouter:
    router = APIRouter(prefix="/v1/safeguarding", tags=["safeguarding"])

    def _lead(claims: Claims) -> str:
        authorize(claims, "triage", "safeguarding.concern")
        return claims.sub

    # ------------------------------------------------------------------------ raise a concern

    @router.post("/concerns", status_code=201)
    def raise_concern(
        body: RaiseConcernIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "raise", "safeguarding.concern")
        raise_limiter.check(f"{claims.role}:{claims.sub}")
        context = body.context or ConcernContextIn()
        if claims.role == "teacher":
            return service.raise_by_teacher(
                teacher_ref=claims.sub,
                student_ref=body.student_ref or "",
                category=body.category,
                text=body.text,
                submission_id=body.submission_id or None,
                screen=context.screen,
                lesson_id=context.lesson_id,
            )
        if body.submission_id:
            raise forbidden("only a teacher's concern names a submission")
        if claims.role == "student":
            if body.student_ref not in (None, "", claims.sub):
                raise forbidden("a learner raises a concern about themselves")
            return service.raise_by_student(
                student_ref=claims.sub,
                category=body.category,
                text=body.text,
                screen=context.screen,
                lesson_id=context.lesson_id,
            )
        return service.raise_by_guardian(
            guardian_ref=claims.sub,
            student_ref=body.student_ref or "",
            category=body.category,
            text=body.text,
            screen=context.screen,
            lesson_id=context.lesson_id,
        )

    @router.get("/my-concerns")
    def my_concerns(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "safeguarding.own_concern")
        return {"concerns": service.guardian_concerns(claims.sub)}

    # ------------------------------------------------------------------------------- triage

    @router.get("/queue")
    def queue(
        include_resolved: bool = Query(default=False, alias="includeResolved"),
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        _lead(claims)
        return service.queue(include_resolved=include_resolved)

    @router.get("/concerns/{concern_id}")
    def detail(concern_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        return service.detail(actor_ref=_lead(claims), concern_id=concern_id)

    @router.get("/concerns/{concern_id}/context")
    def context(concern_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        return service.context(actor_ref=_lead(claims), concern_id=concern_id)

    @router.post("/concerns/{concern_id}:acknowledge")
    def acknowledge(concern_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        return service.acknowledge(actor_ref=_lead(claims), concern_id=concern_id)

    @router.post("/concerns/{concern_id}/notes", status_code=201)
    def add_note(
        concern_id: str, body: NoteIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        return service.add_note(actor_ref=_lead(claims), concern_id=concern_id, body=body.body)

    @router.post("/concerns/{concern_id}:escalate")
    def escalate(
        concern_id: str, body: EscalateIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        return service.escalate(actor_ref=_lead(claims), concern_id=concern_id, reason=body.reason)

    @router.post("/concerns/{concern_id}:resolve")
    def resolve(
        concern_id: str, body: ResolveIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        return service.resolve(
            actor_ref=_lead(claims), concern_id=concern_id, outcome=body.outcome, note=body.note
        )

    return router
