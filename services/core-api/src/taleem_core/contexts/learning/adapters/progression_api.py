"""FastAPI adapter: the path, unit checks and the academic record (PROGRESSION_AND_EXAMINATION
_CONTRACT.md; contract: ``packages/contracts/learning.openapi.yaml``).

Who may call what (deny-by-default PDP, then the relationship here):

- ``student``: their own path, their own unit-check sittings (start or resume / resume /
  answer / finish) and their own record. Mounted behind the live learner permission gate.
- ``guardian``: their own child's record (``/v1/guardian/children/{ref}/record``; anyone else's
  child: 404).
- ``teacher`` (optional): the record of a learner in one of their own classes whom they may see
  now (progress-sharing consent); anyone else: 404.

Answers are scored on the server; no response carries an answer key, and no per-item right/wrong
is revealed while a check is open.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, Depends, Response
from pydantic import Field

from ....auth.dependencies import authorize, require_owner_or
from ....auth.jwt_verifier import Claims
from ....platform.errors import Problem, not_found
from ..application.progression_service import ProgressionService
from ..domain.progression import ProgressionError, Sitting, unit_key_of
from ..domain.scorer import AnswerKindMismatchError
from .api import AnswerFields

_MENTOR = ("mentor",)
_CHECK = "learning.unit_check"
_RECORD = "learning.record"
_STATUS: dict[str, int] = {
    "UNIT_NOT_FOUND": 404,
    "SITTING_NOT_FOUND": 404,
    "ITEM_NOT_IN_SITTING": 404,
    "SITTING_EXPIRED": 410,
    "RETAKE_NOT_YET": 429,
}
_REF = 255


class CheckAnswerIn(AnswerFields):
    item_ref: str = Field(min_length=1, max_length=_REF)
    response_time_ms: int = Field(default=0, ge=0)


@dataclass
class ProgressionApiDeps:
    service: ProgressionService
    # ``guardian_of(student_ref)`` -> the guardian ref, or None (no such learner).
    guardian_of: Callable[[str], str | None]
    # ``teacher_sees(teacher_ref, student_ref)``: in one of the teacher's classes and visible now.
    teacher_sees: Callable[[str, str], bool]
    # ``report_cards(role, actor_ref, student_ref)`` -> the cards that reader may open.
    report_cards: Callable[[str, str, str], list[dict[str, Any]]]


def _problem(exc: ProgressionError) -> Problem:
    status = _STATUS.get(exc.code, 409)
    extensions = dict(exc.detail)
    return Problem(status, exc.code, "Unit check", str(exc), extensions=extensions)


def _card_links(role: str, student_ref: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Report cards as links (contract §3): a learner opens their list, an adult the card."""
    out: list[dict[str, Any]] = []
    for c in cards:
        card_id = str(c.get("card_id") or "")
        out.append(
            {
                "card_id": card_id,
                "period_start": c.get("period_start"),
                "period_end": c.get("period_end"),
                "issued_at": c.get("issued_at"),
                "href": (
                    f"/v1/reporting/learners/{student_ref}/report-cards"
                    if role == "student"
                    else f"/v1/reporting/report-cards/{card_id}"
                ),
            }
        )
    return out


def build_progression_router(
    deps: ProgressionApiDeps, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    router = APIRouter(tags=["learning"])
    service = deps.service
    base = "/v1/learning/students/{student_ref}"
    checks = base + "/units/{unit_key}/checks"

    def _guarded(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except ProgressionError as exc:
            raise _problem(exc) from exc

    def _own(claims: Claims, student_ref: str) -> None:
        authorize(claims, "operate", _CHECK)
        require_owner_or(claims, student_ref, privileged_roles=())

    def _sitting(student_ref: str, unit_key: str, sitting_id: str, claims: Claims) -> Sitting:
        """The learner's own sitting of that unit (any mismatch reads as not found)."""
        _own(claims, student_ref)
        sitting = service.get(sitting_id)
        if (
            sitting is None
            or sitting.student_ref != student_ref
            or unit_key_of(sitting.unit_id) != unit_key
        ):
            raise not_found("unit check not found")
        return sitting

    # -------------------------------------------------------------------------- path

    @router.get(base + "/path")
    def path(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        require_owner_or(claims, student_ref, privileged_roles=_MENTOR)
        return service.path(student_ref)

    # -------------------------------------------------------------------- unit checks

    @router.post(checks, status_code=201)
    def start(
        student_ref: str,
        unit_key: str,
        response: Response,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        _own(claims, student_ref)
        view, created = _guarded(lambda: service.start(student_ref, unit_key))
        if not created:
            response.status_code = 200  # the open sitting, resumed
        return {**view, "resumed": not created}

    @router.get(checks + "/{sitting_id}")
    def resume(
        student_ref: str,
        unit_key: str,
        sitting_id: str,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        sitting = _sitting(student_ref, unit_key, sitting_id, claims)
        if sitting.scored:
            return {**dict(_guarded(lambda: service.result(sitting))), "item": None}
        return dict(_guarded(lambda: service.current(sitting_id)))

    @router.post(checks + "/{sitting_id}:answer")
    def answer(
        student_ref: str,
        unit_key: str,
        sitting_id: str,
        body: CheckAnswerIn,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        _sitting(student_ref, unit_key, sitting_id, claims)
        given = body.answer()
        try:
            return dict(
                _guarded(
                    lambda: service.answer(
                        sitting_id, body.item_ref, given, response_time_ms=body.response_time_ms
                    )
                )
            )
        except AnswerKindMismatchError as exc:
            raise Problem(
                422, "ANSWER_KIND_MISMATCH", "Answer does not fit the item", str(exc)
            ) from exc

    @router.post(checks + "/{sitting_id}:finish")
    def finish(
        student_ref: str,
        unit_key: str,
        sitting_id: str,
        claims: Claims = Depends(claims_dependency),
    ) -> dict[str, Any]:
        _sitting(student_ref, unit_key, sitting_id, claims)
        return dict(_guarded(lambda: service.finish(sitting_id)))

    # ------------------------------------------------------------------------- record

    @router.get(base + "/record")
    def learner_record(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        """The learner themself, or a teacher for a learner in one of their own classes."""
        authorize(claims, "read", _RECORD)
        if claims.role == "teacher":
            if not deps.teacher_sees(claims.sub, student_ref):
                raise not_found("learner not found")
        else:
            require_owner_or(claims, student_ref, privileged_roles=())
        cards = deps.report_cards(claims.role, claims.sub, student_ref)
        return service.record(
            student_ref, report_cards=_card_links(claims.role, student_ref, cards)
        )

    @router.get("/v1/guardian/children/{student_ref}/record")
    def child_record(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        """A guardian's own child (any other child: 404, the same answer as identity's)."""
        authorize(claims, "read", _RECORD)
        if claims.role != "guardian" or deps.guardian_of(student_ref) != claims.sub:
            raise not_found("learner not found")
        cards = deps.report_cards(claims.role, claims.sub, student_ref)
        return service.record(
            student_ref, report_cards=_card_links(claims.role, student_ref, cards)
        )

    return router
