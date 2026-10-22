"""Learner permission gate for offline sync (child-safety control).

An offline device can hold a child's answers for days. Between the moment they were recorded and the
moment they reach the server, a guardian may have **withdrawn consent** or an operator may have
**suspended** the learner. Sign-in and refresh already re-check both, but a sync batch carries a
still-valid access token (up to ten minutes) and a privileged operator token carries none of the
learner's state at all — so without a gate here, learning evidence could be written for a child
whose guardian has pressed stop. This gate closes that hole: every learner a batch touches is
re-checked against **live** identity state, on every batch, before anything is applied.

Rules (fail closed):

* learner account exists but is not ACTIVE (suspended / locked)  -> ``LEARNER_INACTIVE``
* learner account exists without current consent covering ``learning_data`` -> ``CONSENT_REQUIRED``
* no learner account at all -> ``CONSENT_REQUIRED`` when ``require_enrolled`` (production), else
  permitted — the dev/test HS256 path mints tokens for synthetic learners that have no account;
  production refuses to boot with that path, and there every learner token comes from identity.

A refusal rejects the **whole batch** (nothing is applied) with HTTP 403 and the code above; the
client retains the deltas as *held* (never deleted, never retried in a loop). The check reads
identity only through injected callables, so this context does not import identity internals; the
composition root wires them to ``IdentityService.consent_state_for`` and the learner repository.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

CONSENT_REQUIRED = "CONSENT_REQUIRED"
LEARNER_INACTIVE = "LEARNER_INACTIVE"


class _ConsentLike(Protocol):
    @property
    def permits_sign_in(self) -> bool: ...


class _LearnerLike(Protocol):
    @property
    def can_sign_in(self) -> bool: ...


class LearnerGate(Protocol):
    """Returns ``None`` when the learner may sync, else the refusal code."""

    def refusal(self, student_ref: str) -> str | None: ...


class SyncRefusedError(Exception):
    """A batch touched a learner who may not sync right now. Nothing was applied."""

    def __init__(self, code: str, student_ref: str) -> None:
        super().__init__(f"{code} for {student_ref}")
        self.code = code
        self.student_ref = student_ref


class IdentitySyncGate:
    """Live identity check: account status first, then derived consent state."""

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
    """Raise ``SyncRefusedError`` for the first refused learner (deterministic order)."""
    if gate is None:
        return
    for ref in sorted({r for r in student_refs if r}):
        code = gate.refusal(ref)
        if code is not None:
            raise SyncRefusedError(code, ref)
