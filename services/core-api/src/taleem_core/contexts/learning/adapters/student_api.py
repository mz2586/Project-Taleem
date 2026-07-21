"""FastAPI router for the student-facing query surface (derived read models).

Homework, assessments, revision queue, timetable, notifications, achievements, history,
recommendations, and the dashboard aggregate. Every endpoint is authenticated, authorized (read
learning.knowledge), and IDOR-guarded (a learner reaches only their own data; mentors may read any).
Governance-safe: derived from existing learning data; no new child-data surfaces.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Response

from ....auth.dependencies import authorize, require_owner_or
from ....auth.jwt_verifier import Claims
from ..application.student_queries import StudentQueryService

_MENTOR = ("mentor",)


def build_student_router(
    queries: StudentQueryService, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    router = APIRouter(prefix="/v1/learning/students", tags=["learning"])

    def _guard(claims: Claims, student_ref: str) -> None:
        authorize(claims, "read", "learning.knowledge")
        require_owner_or(claims, student_ref, privileged_roles=_MENTOR)

    @router.get("/{student_ref}/today")
    def today(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.today(student_ref)

    @router.get("/{student_ref}/homework")
    def homework(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.homework(student_ref)

    @router.get("/{student_ref}/assessments")
    def assessments(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.assessments(student_ref)

    @router.get("/{student_ref}/reviews")
    def reviews(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.reviews(student_ref)

    @router.get("/{student_ref}/timetable")
    def timetable(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.timetable(student_ref)

    @router.get("/{student_ref}/notifications")
    def notifications(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.notifications(student_ref)

    @router.post("/{student_ref}/notifications/{notification_id}:read", status_code=204)
    def mark_read(
        student_ref: str,
        notification_id: str,
        claims: Claims = Depends(claims_dependency),
    ) -> Response:
        _guard(claims, student_ref)
        queries.mark_notification_read(student_ref, notification_id)
        return Response(status_code=204)

    @router.get("/{student_ref}/achievements")
    def achievements(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.achievements(student_ref)

    @router.get("/{student_ref}/history")
    def history(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.history(student_ref)

    @router.get("/{student_ref}/recommendations")
    def recommendations(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        _guard(claims, student_ref)
        return queries.recommendations(student_ref)

    return router
