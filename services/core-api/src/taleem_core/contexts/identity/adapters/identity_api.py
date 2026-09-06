"""FastAPI router for identity, consent, and the child-safe sign-in journey.

Three of these routes are unauthenticated by necessity — registration, guardian sign-in, and the
learner sign-in pair are how a caller *gets* a token. Everything else derives the acting guardian
from the verified token's subject, never from the request body, so a caller cannot act for another
family by changing a ref.

The two public learner routes are the sensitive ones, and they are protected by four independent
things rather than by authentication: possession of a ~40-bit family code, a durable per-account
attempt lockout, a per-client rate limit on this router, and a consent gate that runs after the PIN
check. Responses are uniform on every failure so none of them becomes an enumeration oracle.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from ....auth.dependencies import authorize
from ....auth.jwt_verifier import Claims
from ....platform.errors import Problem, forbidden
from ..application.identity_service import IdentityService
from ..domain.consent import CURRENT_POLICY_VERSION, ConsentEvidence, ConsentScope
from .rate_limit import RateLimiter

# Sign-in and registration attempts per client per window. Generous enough that a family sharing one
# connection is unaffected; tight enough that a PIN space of 10 000 cannot be walked.
SIGN_IN_LIMIT = 10
SIGN_IN_WINDOW_SECONDS = 60.0
ROSTER_LIMIT = 20
ROSTER_WINDOW_SECONDS = 60.0


class GuardianRegisterIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    email: str = Field(min_length=3, max_length=254)
    passphrase: str = Field(min_length=1, max_length=256)
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    locale: str = Field(default="ur", max_length=8)


class GuardianSignInIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    passphrase: str = Field(min_length=1, max_length=256)


class LearnerCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    pin: str = Field(min_length=4, max_length=6)
    grade_band: str = Field(default="middle", alias="gradeBand", max_length=16)
    grade_level: int = Field(default=4, alias="gradeLevel", ge=0, le=12)
    locale: str = Field(default="ur", max_length=8)


class PinResetIn(BaseModel):
    pin: str = Field(min_length=4, max_length=6)


class ConsentIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    student_ref: str = Field(alias="studentRef", min_length=1, max_length=64)
    scopes: list[str] = Field(default_factory=list, max_length=8)
    attestation: str = Field(default="", max_length=500)


class ConsentWithdrawIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    student_ref: str = Field(alias="studentRef", min_length=1, max_length=64)
    # Omitted means "withdraw everything" — the guardian's stop button.
    scopes: list[str] | None = Field(default=None, max_length=8)
    attestation: str = Field(default="", max_length=500)


class LearnerSignInIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    family_code: str = Field(alias="familyCode", min_length=1, max_length=16)
    display_name: str = Field(alias="displayName", min_length=1, max_length=60)
    pin: str = Field(min_length=4, max_length=6)
    device_id: str = Field(default="", alias="deviceId", max_length=64)


class RosterIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    family_code: str = Field(alias="familyCode", min_length=1, max_length=16)


def _parse_scopes(raw: list[str]) -> set[ConsentScope]:
    known = {s.value for s in ConsentScope}
    unknown = [s for s in raw if s not in known]
    if unknown:
        raise Problem(
            422,
            "UNKNOWN_CONSENT_SCOPE",
            "Validation failed",
            f"unknown consent scope(s): {', '.join(sorted(unknown))}",
        )
    return {ConsentScope(s) for s in raw}


def _hash_context(value: str) -> str:
    """Hash a request context value before it enters a consent record.

    The record needs to show that consent came from a consistent client, not who that client is, so
    the raw IP and user agent are reduced to a truncated digest and the originals are never stored.
    """
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


def _evidence(request: Request, attestation: str) -> ConsentEvidence:
    client_host = request.client.host if request.client else ""
    return ConsentEvidence(
        method="guardian_portal",
        ip_hash=_hash_context(client_host),
        user_agent_hash=_hash_context(request.headers.get("user-agent", "")),
        attestation=attestation.strip(),
    )


def _guardian_ref(claims: Claims) -> str:
    """The acting guardian, taken from the verified token and nowhere else."""
    if claims.role != "guardian":
        raise forbidden("this endpoint is for guardian accounts")
    return claims.sub


def build_identity_router(
    service: IdentityService,
    claims_dependency: Callable[..., Claims],
    *,
    clock: Callable[[], float],
) -> APIRouter:
    router = APIRouter(prefix="/v1/identity", tags=["identity"])
    sign_in_limiter = RateLimiter(SIGN_IN_LIMIT, SIGN_IN_WINDOW_SECONDS, clock)
    roster_limiter = RateLimiter(ROSTER_LIMIT, ROSTER_WINDOW_SECONDS, clock)

    def _client_key(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    # ------------------------------------------------------------------ public (token-issuing)

    @router.post("/guardians", status_code=201)
    def register_guardian(body: GuardianRegisterIn, request: Request) -> dict[str, Any]:
        sign_in_limiter.check(_client_key(request))
        return service.register_guardian(
            email=body.email,
            passphrase=body.passphrase,
            display_name=body.display_name,
            locale=body.locale,
        )

    @router.post("/guardians:signin")
    def sign_in_guardian(body: GuardianSignInIn, request: Request) -> dict[str, Any]:
        sign_in_limiter.check(_client_key(request))
        return service.sign_in_guardian(email=body.email, passphrase=body.passphrase)

    @router.post("/learners:roster")
    def learner_roster(body: RosterIn, request: Request) -> dict[str, Any]:
        """Display names for one family code, so a child taps rather than types.

        A POST because the family code is a shared secret and must not land in a URL, a proxy log,
        or a browser history entry. An unknown code returns an empty roster, exactly like a family
        with no learners.
        """
        roster_limiter.check(_client_key(request))
        return {"learners": service.family_roster(body.family_code)}

    @router.post("/learners:signin")
    def sign_in_learner(body: LearnerSignInIn, request: Request) -> dict[str, Any]:
        sign_in_limiter.check(_client_key(request))
        return service.sign_in_learner(
            family_code=body.family_code,
            display_name=body.display_name,
            pin=body.pin,
            device_id=body.device_id,
        )

    # ------------------------------------------------------------------------ guardian, authed

    @router.get("/me")
    def me(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "identity.self")
        return service.guardian_profile(_guardian_ref(claims))

    @router.post("/learners", status_code=201)
    def enrol_learner(
        body: LearnerCreateIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.learner")
        return service.enrol_learner(
            guardian_ref=_guardian_ref(claims),
            display_name=body.display_name,
            pin=body.pin,
            grade_band=body.grade_band,
            grade_level=body.grade_level,
            locale=body.locale,
        )

    @router.get("/learners")
    def list_learners(claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "manage", "identity.learner")
        return {"learners": service.list_learners(_guardian_ref(claims))}

    @router.post("/learners/{student_ref}/pin:reset")
    def reset_pin(
        student_ref: str, body: PinResetIn, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.learner")
        return service.reset_learner_pin(
            guardian_ref=_guardian_ref(claims), student_ref=student_ref, pin=body.pin
        )

    # ------------------------------------------------------------------------------- consent

    @router.get("/consents/{student_ref}")
    def consent_state(
        student_ref: str, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.consent")
        return service.consent_state(guardian_ref=_guardian_ref(claims), student_ref=student_ref)

    @router.post("/consents")
    def grant_consent(
        body: ConsentIn, request: Request, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.consent")
        return service.grant_consent(
            guardian_ref=_guardian_ref(claims),
            student_ref=body.student_ref,
            scopes=_parse_scopes(body.scopes),
            evidence=_evidence(request, body.attestation),
        )

    @router.post("/consents:withdraw")
    def withdraw_consent(
        body: ConsentWithdrawIn, request: Request, claims: Claims = Depends(claims_dependency)
    ) -> dict[str, Any]:
        authorize(claims, "manage", "identity.consent")
        return service.withdraw_consent(
            guardian_ref=_guardian_ref(claims),
            student_ref=body.student_ref,
            scopes=_parse_scopes(body.scopes) if body.scopes is not None else None,
            evidence=_evidence(request, body.attestation),
        )

    @router.get("/policy")
    def policy() -> dict[str, Any]:
        """The consent vocabulary a client renders. Public: it contains no account data."""
        return {
            "policy_version": CURRENT_POLICY_VERSION,
            "scopes": [
                {"key": s.value, "required": s.value == ConsentScope.LEARNING_DATA.value}
                for s in ConsentScope
            ],
        }

    # --------------------------------------------------------------------------------- audit

    @router.get("/audit")
    def audit(limit: int = 100, claims: Claims = Depends(claims_dependency)) -> dict[str, Any]:
        authorize(claims, "read", "identity.audit")
        return {
            "events": service.audit_trail(
                guardian_ref=_guardian_ref(claims), limit=max(1, min(limit, 500))
            )
        }

    return router
