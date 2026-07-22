"""FastAPI router for offline lesson packages — Phase 6.2A.

Serves the package index and per-lesson packages the client caches for offline rendering. Content is
published curriculum (C0, no child data); every route is authenticated and authorized to read
``learning.knowledge`` (students + mentors already hold this grant — no new PDP rule, no governance
change). Not IDOR-scoped: packages are curriculum, not per-child data.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform.errors import Problem
from ..application.offline_service import OfflinePackageService


def build_offline_router(
    service: OfflinePackageService, claims_dependency: Callable[..., Claims]
) -> APIRouter:
    router = APIRouter(prefix="/v1/offline", tags=["offline"])

    @router.get("/packages")
    def list_packages(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        return service.list_packages()

    @router.get("/packages/{lesson_id}")
    def get_package(lesson_id: str, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "learning.knowledge")
        package = service.get_package(lesson_id)
        if package is None:
            raise Problem(
                404, "PACKAGE_NOT_FOUND", "No published package for this lesson", lesson_id
            )
        return package.to_dict()

    return router
