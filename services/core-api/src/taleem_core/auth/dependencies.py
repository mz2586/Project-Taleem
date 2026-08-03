"""Reusable FastAPI auth dependencies (AuthN JWT + AuthZ PDP).

Business routers use these to require a verified bearer token and a deny-by-default PDP decision,
deriving the actor's role from the *verified token* — never from the request body (CTO B1). The
verifier is built from configured key material: asymmetric EdDSA/JWKS in production, HS256 for
local/dev/tests (FD-14).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Header

from ..platform.errors import forbidden, unauthorized
from . import pdp
from .jwt_verifier import Claims, TokenVerifier


def bearer_claims_from(verifier: TokenVerifier) -> Callable[[str], Claims]:
    """Build a FastAPI dependency that verifies the bearer token against ``verifier``'s keys."""

    def dependency(authorization: str = Header(default="")) -> Claims:
        if not authorization.lower().startswith("bearer "):
            raise unauthorized("Missing bearer token")
        return verifier.verify(authorization.split(" ", 1)[1])

    return dependency


def bearer_claims(secret: str) -> Callable[[str], Claims]:
    """Backward-compatible HS256 dependency (dev/test). Prod wiring uses ``bearer_claims_from``."""
    return bearer_claims_from(TokenVerifier(hs256_secret=secret))


def authorize(claims: Claims, action: str, resource: str) -> None:
    """Enforce a PDP decision (fail closed / deny by default)."""
    if not pdp.authorize(claims.role, action, resource).allow:
        raise forbidden(f"role '{claims.role}' may not {action} {resource}")


def require_owner_or(
    claims: Claims, subject_ref: str, *, privileged_roles: tuple[str, ...]
) -> None:
    """IDOR guard: a learner reaches only their own data; listed roles may reach any."""
    if claims.role in privileged_roles:
        return
    if claims.sub != subject_ref:
        raise forbidden("not permitted to access another learner's data")
