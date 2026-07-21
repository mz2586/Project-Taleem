"""Reusable FastAPI auth dependencies (AuthN JWT + AuthZ PDP).

Business routers use these to require a verified bearer token and a deny-by-default PDP decision,
deriving the actor's role from the *verified token* — never from the request body (CTO B1). Tests
mint a token with ``jwt_verifier.sign_hs256``; production replaces HS256 with JWKS (FD-14).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Header

from ..platform.errors import forbidden, unauthorized
from . import pdp
from .jwt_verifier import Claims, verify_hs256


def bearer_claims(secret: str) -> Callable[[str], Claims]:
    """Build a FastAPI dependency that verifies the bearer token and returns its Claims."""

    def dependency(authorization: str = Header(default="")) -> Claims:
        if not authorization.lower().startswith("bearer "):
            raise unauthorized("Missing bearer token")
        return verify_hs256(authorization.split(" ", 1)[1], secret)

    return dependency


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
