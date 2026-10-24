"""FastAPI routers for /v1/reporting/** (contract: packages/contracts/reporting.openapi.yaml).

Who may call what (deny-by-default PDP, then the relationship in the service):

- ``teacher`` (optional path): preview and issue cards for their own class; read cards of
  learners in their own classes whom they may currently see (also through the learner route).
  The acting teacher — and so the organization — comes from the verified token.
- ``guardian``: list, read and acknowledge their own child's cards; ask Taleem to generate one
  for a closed period (the primary, teacher-free path); their in-app notifications.
- ``student``: their own cards (``build_reporting_learner_router``, mounted behind the live
  learner consent gate and listed as child-facing for the kill switch). A teacher may use the
  same route for a learner in their own class.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from ....auth.dependencies import authorize, require_owner_or
from ....auth.jwt_verifier import Claims
from ....platform.errors import validation_error
from ..application.service import MAX_LEARNERS_PER_ISSUE, ReportingService
from ..domain.report_card import MAX_COMMENT

_RESOURCE = "reporting.report_card"
_REF = 64


class IssueIn(BaseModel):
    """``POST …/report-cards`` and ``…/report-cards:preview`` (snake_case per the contract;
    the camelCase spelling is accepted too)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    period_start: int = Field(alias="periodStart", ge=0)
    period_end: int = Field(alias="periodEnd", gt=0)
    student_refs: list[str] | None = Field(
        default=None, alias="studentRefs", max_length=MAX_LEARNERS_PER_ISSUE
    )
    comments: dict[str, str] = Field(default_factory=dict, max_length=MAX_LEARNERS_PER_ISSUE)
    supersedes: dict[str, str] = Field(default_factory=dict, max_length=MAX_LEARNERS_PER_ISSUE)

    def bounded(self) -> IssueIn:
        refs = [*(self.student_refs or []), *self.comments, *self.supersedes]
        if any(not r or len(r) > _REF for r in refs):
            raise ValueError("learner refs must be 1-64 characters")
        if any(len(v) > MAX_COMMENT * 2 for v in self.comments.values()):  # edge bound
            raise ValueError("comment too long")
        if any(not v or len(v) > _REF for v in self.supersedes.values()):
            raise ValueError("card ids must be 1-64 characters")
        return self


class GenerateIn(BaseModel):
    """``POST /children/{student_ref}/report-cards:generate``: a closed period only."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    period_start: int = Field(alias="periodStart", ge=0)
    period_end: int = Field(alias="periodEnd", gt=0)


def _validated(body: IssueIn) -> IssueIn:
    try:
        return body.bounded()
    except ValueError as exc:
        raise validation_error(str(exc)) from exc


def build_reporting_router(
    service: ReportingService,
    claims_dependency: Callable[..., Claims],
    *,
    issue_guard: Callable[[str], None] = lambda _key: None,
) -> APIRouter:
    router = APIRouter(prefix="/v1/reporting", tags=["reporting"])

    # ------------------------------------------------------------------------- teacher

    @router.post("/classes/{class_id}/report-cards:preview")
    def preview(
        class_id: str, body: IssueIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "issue", _RESOURCE)
        issue_guard(f"teacher:{claims.sub}")
        b = _validated(body)
        return service.preview(
            teacher_ref=claims.sub,
            class_id=class_id,
            period_start=b.period_start,
            period_end=b.period_end,
            student_refs=b.student_refs,
            comments=b.comments,
            supersedes=b.supersedes,
        )

    @router.post("/classes/{class_id}/report-cards", status_code=201)
    def issue(
        class_id: str, body: IssueIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "issue", _RESOURCE)
        issue_guard(f"teacher:{claims.sub}")
        b = _validated(body)
        return service.issue(
            teacher_ref=claims.sub,
            class_id=class_id,
            period_start=b.period_start,
            period_end=b.period_end,
            student_refs=b.student_refs,
            comments=b.comments,
            supersedes=b.supersedes,
        )

    @router.get("/classes/{class_id}/report-cards")
    def class_cards(class_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "issue", _RESOURCE)
        return {"report_cards": service.class_cards(teacher_ref=claims.sub, class_id=class_id)}

    # ------------------------------------------------------------------------ guardian

    @router.get("/children/{student_ref}/report-cards")
    def child_cards(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "acknowledge", _RESOURCE)
        return {
            "report_cards": service.child_cards(guardian_ref=claims.sub, student_ref=student_ref)
        }

    @router.post("/children/{student_ref}/report-cards:generate", status_code=201)
    def generate(
        student_ref: str, body: GenerateIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        """Taleem issues the guardian's own child's card for a closed period (system issuer)."""
        authorize(claims, "acknowledge", _RESOURCE)
        issue_guard(f"guardian:{claims.sub}")
        return service.generate_for_child(
            guardian_ref=claims.sub,
            student_ref=student_ref,
            period_start=body.period_start,
            period_end=body.period_end,
        )

    @router.get("/children/{student_ref}/notifications")
    def child_notifications(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "acknowledge", _RESOURCE)
        return service.child_notifications(guardian_ref=claims.sub, student_ref=student_ref)

    @router.post("/report-cards/{card_id}:acknowledge")
    def acknowledge(card_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "acknowledge", _RESOURCE)
        return service.acknowledge(guardian_ref=claims.sub, card_id=card_id)

    # ------------------------------------------------------------- guardian or teacher

    @router.get("/report-cards/{card_id}")
    def get_card(card_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", _RESOURCE)
        return service.get_card(actor_ref=claims.sub, role=claims.role, card_id=card_id)

    return router


def build_reporting_learner_router(
    service: ReportingService, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    """A learner's cards (REPORT_CARD_CONTRACT §3): the learner themself, or a teacher for a
    learner in one of their own classes whom they may currently see (anyone else: 404). Mount it
    behind the live learner permission gate: for a student token a withdrawn consent or a
    suspended account is a 403 on the next request (other roles pass the gate)."""
    router = APIRouter(prefix="/v1/reporting", tags=["reporting"])

    @router.get("/learners/{student_ref}/report-cards")
    def learner_cards(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        if claims.role == "teacher":
            authorize(claims, "issue", _RESOURCE)
            cards = service.learner_cards_for_teacher(
                teacher_ref=claims.sub, student_ref=student_ref
            )
            return {"report_cards": cards}
        authorize(claims, "read", "reporting.own_report_card")
        require_owner_or(claims, student_ref, privileged_roles=())
        return {"report_cards": service.learner_cards(student_ref)}

    return router
