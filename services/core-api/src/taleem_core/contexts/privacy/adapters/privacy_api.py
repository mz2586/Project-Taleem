"""FastAPI router for data-subject rights under ``/v1/privacy`` (see privacy.openapi.yaml).

- A guardian exports, or erases, a learner **they are the guardian of**. The PDP gate is the
  existing ``guardian manage identity.learner`` permission; ownership is settled by the service
  against the token subject, and anything not theirs is a uniform 404.
- Erasure is two-step: ``erasure-requests`` returns a short-lived signed confirmation token, and
  ``erasure:confirm`` must present it. Nothing is erased on the first call.
- The retention dry-run is an operator control (``system operate ops.control``); it never deletes.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ..application.service import PrivacyService


class ConfirmIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    confirmation_token: str = Field(alias="confirmationToken", min_length=10, max_length=2048)


def build_privacy_router(
    service: PrivacyService, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    router = APIRouter(prefix="/v1/privacy", tags=["privacy"])

    @router.get("/policy")
    def policy(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        if claims.role != "guardian":
            authorize(claims, "operate", "ops.control")
        return service.policy()

    @router.get("/learners/{student_ref}/export")
    def export(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "manage", "identity.learner")
        return service.export(guardian_ref=claims.sub, student_ref=student_ref)

    @router.post("/learners/{student_ref}/erasure-requests", status_code=202)
    def request_erasure(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.learner")
        return service.request_erasure(guardian_ref=claims.sub, student_ref=student_ref)

    @router.post("/learners/{student_ref}/erasure:confirm")
    def confirm_erasure(
        student_ref: str, body: ConfirmIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.learner")
        return service.confirm_erasure(
            guardian_ref=claims.sub,
            student_ref=student_ref,
            confirmation_token=body.confirmation_token,
        )

    @router.get("/retention:dry-run")
    def retention_dry_run(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "operate", "ops.control")
        return service.retention_dry_run()

    return router
