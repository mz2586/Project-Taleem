"""Per-request learner permission gate (child-safety control, shared by every learner surface).

A learner access token lives ten minutes. Sign-in and refresh re-check consent and account status,
but between refreshes the token alone would keep opening learning routes after a guardian has
withdrawn consent or an operator has suspended the child. This gate closes that window: on **every**
request a ``student`` token makes to a route that reads or writes learning data, and for every
learner a sync batch writes for, the learner is re-checked against **live** identity state. There
is deliberately no cache — immediacy is the point of a guardian's stop button.

Rules (fail closed):

* learner account exists but is not ACTIVE (suspended / locked)              -> ``LEARNER_INACTIVE``
* learner account exists without current consent covering ``learning_data`` -> ``CONSENT_REQUIRED``
* no learner account at all -> ``CONSENT_REQUIRED`` when ``require_enrolled`` (production), else
  permitted — the dev/test HS256 path mints tokens for synthetic learners that have no account;
  production refuses to boot with that path, and there every learner token comes from identity.

Refusals are HTTP 403 with the code and **no learner reference** in the body. Guardian, system and
other roles pass the route gate untouched (their own authorization still applies); where such a
token *writes for* a learner (sync), the caller uses ``enforce`` on the learner refs directly.

This module lives in ``auth`` so learning, sync and the AI teacher can depend on it without
importing identity internals: identity is reached only through the two injected callables, which
the composition root wires to ``IdentityService.consent_state_for`` and the learner repository.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

from fastapi import Depends

from ..platform.errors import Problem
from .jwt_verifier import Claims

CONSENT_REQUIRED = "CONSENT_REQUIRED"
LEARNER_INACTIVE = "LEARNER_INACTIVE"

_TITLE = "Learner may not use learning features"
_DETAIL = "this learner's consent or account status does not permit using learning data"


class _ConsentLike(Protocol):
    @property
    def permits_sign_in(self) -> bool: ...


class _LearnerLike(Protocol):
    @property
    def can_sign_in(self) -> bool: ...


class LearnerGate(Protocol):
    """Returns ``None`` when the learner may proceed, else the refusal code."""

    def refusal(self, student_ref: str) -> str | None: ...


class LearnerRefusedError(Exception):
    """A request touched a learner who may not use learning data right now."""

    def __init__(self, code: str, student_ref: str) -> None:
        super().__init__(code)
        self.code = code
        self.student_ref = student_ref


class IdentityLearnerGate:
    """Live identity check: account status first, then derived consent state. No caching."""

    def __init__(
        self,
        consent_state_for: Callable[[str], _ConsentLike],
        learner_lookup: Callable[[str], _LearnerLike | None],
        *,
        require_enrolled: bool,
    ) -> None:
        self._consent = consent_state_for
        self._learner = learner_lookup
        self._require_enrolled = require_enrolled

    def refusal(self, student_ref: str) -> str | None:
        learner = self._learner(student_ref)
        if learner is None:
            return CONSENT_REQUIRED if self._require_enrolled else None
        if not learner.can_sign_in:
            return LEARNER_INACTIVE
        if not self._consent(student_ref).permits_sign_in:
            return CONSENT_REQUIRED
        return None


def enforce(gate: LearnerGate | None, student_refs: Iterable[str]) -> None:
    """Raise ``LearnerRefusedError`` for the first refused learner (deterministic order)."""
    if gate is None:
        return
    for ref in sorted({r for r in student_refs if r}):
        code = gate.refusal(ref)
        if code is not None:
            raise LearnerRefusedError(code, ref)


class LearnerRefusalError(Problem):
    """The 403 every refusal maps to. Carries the code and never the learner reference — so it
    also omits RFC 9457 ``instance``, which would echo a learner-scoped URL path."""

    def to_dict(self, instance: str | None = None) -> dict[str, Any]:
        return super().to_dict(None)


def refusal_problem(code: str) -> Problem:
    return LearnerRefusalError(403, code, _TITLE, _DETAIL)


def learner_permission_dependency(
    gate: LearnerGate, claims_dependency: Callable[..., Claims]
) -> Callable[..., None]:
    """A FastAPI dependency for router-level wiring: re-checks a ``student`` token's learner on
    every request. Other roles pass through. Shares the request's cached ``claims_dependency``, so
    an unauthenticated call is still a 401 from the verifier, not a 403 from here."""

    def dependency(claims: Claims = Depends(claims_dependency)) -> None:
        if claims.role != "student":
            return
        code = gate.refusal(claims.sub)
        if code is not None:
            raise refusal_problem(code)

    return dependency
