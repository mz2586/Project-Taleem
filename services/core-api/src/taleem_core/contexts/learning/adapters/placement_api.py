"""FastAPI router for diagnostic placement (PlacementService).

    GET  /v1/learning/students/{ref}/placement          — state + the next question (or the result)
    POST /v1/learning/students/{ref}/placement:answer   — answer the current question

Authenticated + authorized + IDOR-guarded exactly like the session and AI Teacher routers: the
learner answers their own placement (no privileged override for operating it); a mentor may read
it. The response never includes an item's answer key — only the prompt and options.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ....auth.dependencies import authorize, require_owner_or
from ....auth.jwt_verifier import Claims
from ..application.placement_service import PlacementService

_STUDENT_ONLY: tuple[str, ...] = ()
_MENTOR = ("mentor",)


class PlacementAnswerIn(BaseModel):
    item_ref: str = Field(min_length=1)
    option: int = Field(ge=0)
    response_time_ms: int = Field(default=0, ge=0)


def build_placement_router(
    service: PlacementService, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    router = APIRouter(prefix="/v1/learning", tags=["placement"])

    @router.get("/students/{student_ref}/placement")
    def placement(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        require_owner_or(claims, student_ref, privileged_roles=_MENTOR)
        return service.status(student_ref)

    @router.post("/students/{student_ref}/placement:answer")
    def answer(
        student_ref: str, body: PlacementAnswerIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "operate", "learning.session")
        require_owner_or(claims, student_ref, privileged_roles=_STUDENT_ONLY)
        return service.answer(
            student_ref,
            item_ref=body.item_ref,
            option=body.option,
            response_time_ms=body.response_time_ms,
        )

    return router
