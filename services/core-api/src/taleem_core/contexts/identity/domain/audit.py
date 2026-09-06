"""Append-only identity audit trail (pure domain).

Auditability is a safeguarding requirement, not an engineering nicety: when a guardian asks "who
signed in as my child, and when", or a safeguarding lead asks "was consent in place at the time",
the answer has to come from a record that cannot have been edited afterwards.

The trail is therefore **append-only by construction** — the repository exposes no update or delete
— and every entry is deliberately PII-light: refs, not names; hashes, not addresses. An audit log
that accumulates children's personal data becomes its own privacy risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ....platform.ids import uuid7


class AuditAction(StrEnum):
    GUARDIAN_REGISTERED = "guardian.registered"
    GUARDIAN_SIGNED_IN = "guardian.signed_in"
    GUARDIAN_SIGN_IN_FAILED = "guardian.sign_in_failed"
    GUARDIAN_LOCKED = "guardian.locked"
    LEARNER_CREATED = "learner.created"
    LEARNER_SIGNED_IN = "learner.signed_in"
    LEARNER_SIGN_IN_FAILED = "learner.sign_in_failed"
    LEARNER_SIGN_IN_DENIED_NO_CONSENT = "learner.sign_in_denied_no_consent"
    LEARNER_LOCKED = "learner.locked"
    LEARNER_PIN_RESET = "learner.pin_reset"
    LEARNER_SUSPENDED = "learner.suspended"
    LEARNER_REINSTATED = "learner.reinstated"
    CONSENT_GRANTED = "consent.granted"
    CONSENT_WITHDRAWN = "consent.withdrawn"
    SESSION_REFRESHED = "session.refreshed"
    SESSION_SIGNED_OUT = "session.signed_out"
    SESSION_REVOKED = "session.revoked"
    # A consumed refresh token presented a second time. Either a race or a stolen token, and the
    # two are indistinguishable — so the whole rotation family is revoked and this is recorded.
    SESSION_REUSE_DETECTED = "session.reuse_detected"


# Actions a guardian must be able to see for their own family without an operator in the loop:
# these are the ones that answer "what happened to my child's account".
GUARDIAN_VISIBLE = frozenset(AuditAction)


@dataclass(frozen=True)
class AuditEvent:
    """One immutable audit entry."""

    event_id: str
    at: float
    action: AuditAction
    actor_ref: str  # who did it (a guardian ref, a learner ref, or "system")
    actor_role: str
    subject_ref: str  # who it was about (usually a learner ref)
    correlation_id: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def record(
        *,
        action: AuditAction,
        actor_ref: str,
        actor_role: str,
        subject_ref: str,
        now: float,
        correlation_id: str = "",
        detail: dict[str, Any] | None = None,
    ) -> AuditEvent:
        return AuditEvent(
            event_id=f"aud_{uuid7()}",
            at=now,
            action=action,
            actor_ref=actor_ref,
            actor_role=actor_role,
            subject_ref=subject_ref,
            correlation_id=correlation_id,
            detail=detail or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "at": self.at,
            "action": self.action.value,
            "actor_ref": self.actor_ref,
            "actor_role": self.actor_role,
            "subject_ref": self.subject_ref,
            "correlation_id": self.correlation_id,
            "detail": self.detail,
        }
