"""FastAPI router for Curriculum Studio staff accounts (``/v1/identity/staff``).

- Operator (``system``) routes create, list, suspend and reinstate staff accounts.
- ``staff:signin`` is public, rate limited per client on the shared limiter, and fails with one
  uniform ``401`` for every cause.
- ``staff/me`` and ``staff/me:passphrase`` are the staff member's own.

Sessions continue through the shared ``/v1/identity/sessions:refresh`` and ``:signout`` routes,
which understand staff refresh tokens. ``staff_gate_dependency`` is mounted on the Studio router so
a suspended account's live access token stops working on its next request.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform.errors import Problem, forbidden
from ..application.staff_service import STAFF_INACTIVE, StaffService
from ..domain.staff import STAFF_ROLES
from .rate_limit import Limiter, RateLimiter, RateLimitStore, SharedRateLimiter

STAFF_SIGN_IN_LIMIT = 10
STAFF_SIGN_IN_WINDOW_SECONDS = 60.0


class StaffCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    email: str = Field(min_length=1, max_length=320)
    passphrase: str = Field(max_length=1024)
    display_name: str = Field(alias="displayName", max_length=120)
    role: str = Field(max_length=32)


class StaffSignInIn(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    passphrase: str = Field(min_length=1, max_length=1024)


class PassphraseChangeIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    current: str = Field(min_length=1, max_length=1024)
    new_passphrase: str = Field(alias="newPassphrase", max_length=1024)


def _staff_ref(claims: Claims) -> str:
    if claims.role not in STAFF_ROLES:
        raise forbidden("this endpoint is for Curriculum Studio staff")
    return claims.sub


def staff_inactive() -> Problem:
    return Problem(
        403,
        STAFF_INACTIVE,
        "Staff account inactive",
        "this staff account is suspended, locked, or no longer holds this role; sign in again",
    )


def staff_gate_dependency(
    service: StaffService,
    claims_dependency: Callable[..., Claims],
    *,
    require_account: bool,
) -> Callable[..., None]:
    """Router-level dependency: refuse a Studio-role token whose staff account is not active.

    Tokens for other roles pass through untouched (the PDP decides what they may do).
    """

    def dependency(claims: Claims = Depends(claims_dependency)) -> None:
        if claims.role not in STAFF_ROLES:
            return
        if service.staff_refusal(claims.sub, claims.role, require_account=require_account):
            raise staff_inactive()

    return dependency


def build_staff_router(
    service: StaffService,
    claims_dependency: Callable[..., Claims],
    *,
    clock: Callable[[], float],
    rate_limit_store: RateLimitStore | None = None,
    client_ip_header: str = "",
) -> APIRouter:
    router = APIRouter(prefix="/v1/identity", tags=["identity"])
    limiter: Limiter = (
        SharedRateLimiter(
            "identity.staff_sign_in",
            STAFF_SIGN_IN_LIMIT,
            STAFF_SIGN_IN_WINDOW_SECONDS,
            clock,
            rate_limit_store,
        )
        if rate_limit_store is not None
        else RateLimiter(STAFF_SIGN_IN_LIMIT, STAFF_SIGN_IN_WINDOW_SECONDS, clock)
    )
    ip_header = client_ip_header.strip().lower()

    def _client_key(request: Request) -> str:
        if ip_header:
            forwarded = request.headers.get(ip_header, "").split(",")[0].strip()
            if forwarded:
                return forwarded[:64]
        return request.client.host if request.client else "unknown"

    # -------------------------------------------------------------------------- public sign-in

    @router.post("/staff:signin")
    def sign_in_staff(body: StaffSignInIn, request: Request) -> dict[str, Any]:
        limiter.check(_client_key(request))
        return service.sign_in_staff(email=body.email, passphrase=body.passphrase)

    # ----------------------------------------------------------------------- the staff member

    @router.get("/staff/me")
    def me(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "identity.staff_self")
        return service.staff_profile(_staff_ref(claims))

    @router.post("/staff/me:passphrase")
    def change_passphrase(
        body: PassphraseChangeIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "read", "identity.staff_self")
        return service.change_passphrase(
            staff_ref=_staff_ref(claims), current=body.current, new_passphrase=body.new_passphrase
        )

    # ------------------------------------------------------------------------------ operator

    @router.post("/staff", status_code=201)
    def create_staff(
        body: StaffCreateIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.staff")
        return service.create_staff(
            operator_ref=claims.sub,
            email=body.email,
            passphrase=body.passphrase,
            display_name=body.display_name,
            role=body.role,
        )

    @router.get("/staff")
    def list_staff(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "manage", "identity.staff")
        return {"staff": service.list_staff()}

    @router.post("/staff/{staff_ref}:suspend")
    def suspend_staff(
        staff_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.staff")
        return service.suspend_staff(operator_ref=claims.sub, staff_ref=staff_ref)

    @router.post("/staff/{staff_ref}:reinstate")
    def reinstate_staff(
        staff_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.staff")
        return service.reinstate_staff(operator_ref=claims.sub, staff_ref=staff_ref)

    return router
