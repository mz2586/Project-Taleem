"""Verifiable guardian consent (pure domain).

Consent here is **evidence, not a flag**. A boolean column cannot answer the questions a regulator
or a safeguarding review actually asks — *which* policy version was agreed, *when*, *how* it was
captured, *what* it covered, and whether it has since been withdrawn. So every grant and every
withdrawal appends an immutable record, and the current state of a learner's consent is derived by
folding that history.

Scopes are separable because they carry different risk: a guardian can allow curriculum learning
while refusing AI-generated teaching, and the platform must honour that per-feature rather than
treating consent as all-or-nothing (docs/15 child-safety framework; FD-14).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from ....platform.ids import uuid7

# The privacy notice + DPIA version a guardian agreed to. Bumping this invalidates existing consent
# for the purpose of the sign-in gate: a material change to how a child's data is used requires
# fresh agreement, it does not silently inherit the old one.
CURRENT_POLICY_VERSION = "2026-09-consent-v1"


class ConsentScope(StrEnum):
    """What a guardian is separately agreeing to."""

    LEARNING_DATA = "learning_data"  # store progress, mastery, attempts (required to sign in)
    AI_TEACHING = "ai_teaching"  # generated explanations/hints rather than fixed content
    VOICE_AUDIO = "voice_audio"  # spoken lesson audio and, where offered, speech input
    PROGRESS_SHARING = "progress_sharing"  # share progress with an assigned mentor/teacher


# Without this scope the platform holds no learning record, so there is nothing to sign a child in
# *for*. It is the one non-optional scope.
REQUIRED_SCOPES: frozenset[ConsentScope] = frozenset({ConsentScope.LEARNING_DATA})


class ConsentAction(StrEnum):
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class ConsentError(ValueError):
    """Raised when a consent operation is not permitted by the domain's rules."""


@dataclass(frozen=True)
class ConsentEvidence:
    """How a particular consent decision was captured, in a form that carries no raw PII.

    The guardian's IP address and user agent are *hashed* by the adapter before they reach here:
    keeping them in the clear would add identifying data to a child-safety record whose only job is
    to prove that a decision was made by the account holder, from a consistent context.
    """

    method: str = "guardian_portal"  # how consent was captured (portal, signed form, phone call…)
    ip_hash: str = ""
    user_agent_hash: str = ""
    attestation: str = ""  # the exact sentence the guardian affirmed, stored verbatim


@dataclass(frozen=True)
class ConsentRecord:
    """One immutable consent decision. Never updated in place; superseded by a later record."""

    consent_id: str
    guardian_ref: str
    student_ref: str
    action: ConsentAction
    scopes: frozenset[ConsentScope]
    policy_version: str
    recorded_at: float
    evidence: ConsentEvidence = field(default_factory=ConsentEvidence)

    @staticmethod
    def grant(
        *,
        guardian_ref: str,
        student_ref: str,
        scopes: frozenset[ConsentScope] | set[ConsentScope],
        now: float,
        policy_version: str = CURRENT_POLICY_VERSION,
        evidence: ConsentEvidence | None = None,
    ) -> ConsentRecord:
        scope_set = frozenset(scopes)
        missing = REQUIRED_SCOPES - scope_set
        if missing:
            raise ConsentError(
                "consent must include " + ", ".join(sorted(s.value for s in missing))
            )
        return ConsentRecord(
            consent_id=f"con_{uuid7()}",
            guardian_ref=guardian_ref,
            student_ref=student_ref,
            action=ConsentAction.GRANTED,
            scopes=scope_set,
            policy_version=policy_version,
            recorded_at=now,
            evidence=evidence or ConsentEvidence(),
        )

    @staticmethod
    def withdraw(
        *,
        guardian_ref: str,
        student_ref: str,
        now: float,
        scopes: frozenset[ConsentScope] | set[ConsentScope] | None = None,
        policy_version: str = CURRENT_POLICY_VERSION,
        evidence: ConsentEvidence | None = None,
    ) -> ConsentRecord:
        """Withdraw some scopes, or (the default) all of them.

        Withdrawing everything is the guardian's stop button: it must take effect on the next
        request, which is why the sign-in gate reads the derived state rather than a cached claim.
        """
        return ConsentRecord(
            consent_id=f"con_{uuid7()}",
            guardian_ref=guardian_ref,
            student_ref=student_ref,
            action=ConsentAction.WITHDRAWN,
            scopes=frozenset(scopes) if scopes is not None else frozenset(ConsentScope),
            policy_version=policy_version,
            recorded_at=now,
            evidence=evidence or ConsentEvidence(),
        )


@dataclass(frozen=True)
class ConsentState:
    """The derived, current consent position for one learner."""

    student_ref: str
    granted_scopes: frozenset[ConsentScope]
    policy_version: str
    granted_at: float
    last_change_at: float

    @property
    def is_current(self) -> bool:
        return self.policy_version == CURRENT_POLICY_VERSION

    @property
    def permits_sign_in(self) -> bool:
        """A learner may sign in only under current-version consent covering the required scopes."""
        return self.is_current and self.granted_scopes >= REQUIRED_SCOPES

    def allows(self, scope: ConsentScope) -> bool:
        return self.is_current and scope in self.granted_scopes

    def to_dict(self) -> dict[str, object]:
        return {
            "student_ref": self.student_ref,
            "granted_scopes": sorted(s.value for s in self.granted_scopes),
            "policy_version": self.policy_version,
            "current_policy_version": CURRENT_POLICY_VERSION,
            "policy_current": self.is_current,
            "permits_sign_in": self.permits_sign_in,
            "granted_at": self.granted_at,
            "last_change_at": self.last_change_at,
        }


def derive_state(student_ref: str, records: list[ConsentRecord]) -> ConsentState:
    """Fold an append-only consent history into the current position.

    Records are folded in chronological order. A grant adds its scopes and adopts its policy
    version; a withdrawal removes its scopes. A withdrawal that empties the set leaves a state whose
    ``permits_sign_in`` is False — the history is preserved, the permission is gone.
    """
    granted: set[ConsentScope] = set()
    policy_version = ""
    granted_at = 0.0
    last_change_at = 0.0
    for record in sorted(records, key=lambda r: (r.recorded_at, r.consent_id)):
        last_change_at = record.recorded_at
        if record.action is ConsentAction.GRANTED:
            if not granted:
                granted_at = record.recorded_at
            granted |= set(record.scopes)
            policy_version = record.policy_version
        else:
            granted -= set(record.scopes)
            if not granted:
                granted_at = 0.0
    return ConsentState(
        student_ref=student_ref,
        granted_scopes=frozenset(granted),
        policy_version=policy_version,
        granted_at=granted_at,
        last_change_at=last_change_at,
    )


NO_CONSENT = ConsentState(
    student_ref="",
    granted_scopes=frozenset(),
    policy_version="",
    granted_at=0.0,
    last_change_at=0.0,
)
