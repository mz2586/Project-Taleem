"""FastAPI router for operational controls — kill switch + ops status (Software Completion Mode).

Operator-only controls used during a pilot: engage/disengage the kill switch (halt child-facing
traffic during an incident) and read an ops status summary (kill-switch state + pseudonymous
counters). Authenticated + PDP-gated (system operates the kill switch; system/mentor read status).
No child data; pseudonymous counters only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform.kill_switch import KillSwitch


class EngageIn(BaseModel):
    reason: str = Field(default="operator-engaged", max_length=200)


def build_ops_router(
    kill_switch: KillSwitch,
    status_provider: Callable[[], dict[str, Any]],
    claims_dependency: Callable[..., Claims],
) -> APIRouter:
    router = APIRouter(prefix="/v1/ops", tags=["ops"])

    @router.get("/kill-switch")
    def get_kill_switch(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "ops.status")
        return kill_switch.status().to_dict()

    @router.post("/kill-switch:engage")
    def engage(body: EngageIn, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "operate", "ops.control")
        return kill_switch.engage(body.reason).to_dict()

    @router.post("/kill-switch:disengage")
    def disengage(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "operate", "ops.control")
        return kill_switch.disengage().to_dict()

    @router.get("/status")
    def status(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "ops.status")
        return status_provider()

    return router
