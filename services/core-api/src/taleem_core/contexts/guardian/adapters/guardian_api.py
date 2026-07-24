"""FastAPI router for the Guardian Portal (read-only, consumes existing learning read models).

Three endpoints — the minimum required to serve the whole portal by aggregation, with no duplication
of the ~13 student endpoints:

    GET /v1/guardian/me                       guardian profile + linked children
    GET /v1/guardian/dashboard                overview across all linked children
    GET /v1/guardian/children/{student_ref}   full detail for ONE linked child

Every endpoint is authenticated (bearer JWT), authorized (PDP: guardian reads its own surface),
**IDOR-guarded by the association directory** (a guardian may only reach a linked child), validated,
audit-logged (pseudonymous), and monitored. Read-only: a guardian never mutates learner state.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform import observability
from ....platform.errors import forbidden, not_found
from ..application.guardian_service import GuardianService

_RESOURCE = "guardian.self"


def build_guardian_router(
    service: GuardianService, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    router = APIRouter(prefix="/v1/guardian", tags=["guardian"])

    def _require_linked(claims: Claims, student_ref: str) -> None:
        # AuthZ is two gates: (1) the PDP allows the guardian role onto this surface, (2) the
        # directory says this guardian is linked to this specific child. A non-linked child is a
        # uniform 403 — never reveal whether the child exists (no enumeration).
        authorize(claims, "read", _RESOURCE)
        if not service.is_linked(claims.sub, student_ref):
            observability.record_event("taleem_guardian_denied_total")
            observability.log_event(
                "guardian_access_denied", guardian=claims.sub, student=student_ref
            )
            raise forbidden("not permitted to access this learner")

    @router.get("/me")
    def me(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", _RESOURCE)
        profile = service.profile(claims.sub)
        observability.record_event("taleem_guardian_views_total", view="me")
        if profile is None:
            # Authenticated as a guardian but linked to no children (e.g. consent not yet captured).
            return {
                "guardian_ref": claims.sub,
                "display_name": claims.sub,
                "children": [],
                "child_count": 0,
            }
        return profile.to_dict()

    @router.get("/dashboard")
    def dashboard(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", _RESOURCE)
        observability.record_event("taleem_guardian_views_total", view="dashboard")
        observability.log_event("guardian_dashboard", guardian=claims.sub)
        return service.dashboard(claims.sub)

    @router.get("/children/{student_ref}")
    def child(student_ref: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        _require_linked(claims, student_ref)
        observability.record_event("taleem_guardian_views_total", view="child")
        observability.log_event("guardian_child_view", guardian=claims.sub, student=student_ref)
        try:
            return service.child_overview(student_ref)
        except KeyError as exc:  # defensive: a linked child with no data yet
            raise not_found("no learner data") from exc

    return router
