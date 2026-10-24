"""Privacy policy objects (pure stdlib): what survives an erasure, and the retention schedule.

Both are **configuration awaiting M-Gov approval** (DPO + counsel, doc 57 "DECISION REQUIRED").
The defaults encode the most conservative engineering position, not a legal opinion:

- **Retained set.** After an erasure, only a minimum tombstone survives: the consent decisions
  (who decided, what scopes, under which policy version, when — the evidence that processing was
  lawful while it happened) and one erasure event (when it was requested/confirmed and its scope).
  Neither carries the learner's ``student_ref``: both are keyed by a one-way *tombstone ref*
  (salted SHA-256 of the ref), which lets a guardian who still holds the ref prove the erasure
  happened, and lets nobody else reverse it.
- **Safeguarding concerns** (an explicit retained-set entry, also PENDING M-Gov, and tied to the
  FD-04 reporting policy). A guardian requests an erasure, and a child's concern may be about that
  guardian; deleting the child's report on the guardian's request could destroy the record of a
  disclosure. The default is therefore ``retain_pseudonymised``: the concern rows are kept, re-keyed
  to the tombstone ref (no ``student_ref`` survives), and the erasure receipt says so. ``erase``
  deletes them with everything else. Either way the choice is stated, never silent.
- **Retention schedule.** Every data class starts as "period not set" ⇒ automated purge disabled.
  No period is invented; a period exists only when an operator configures one, and even then this
  phase only produces a dry-run report.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, field

APPROVAL_STATUS = "PENDING M-Gov approval (DPO + counsel; doc 57 DECISION REQUIRED)"

# Consent-record fields that *may* be retained in a tombstone (anything else is never kept).
CONSENT_FIELDS: tuple[str, ...] = (
    "consent_id",
    "guardian_ref",
    "action",
    "scopes",
    "policy_version",
    "recorded_at",
    "evidence.method",
    "evidence.attestation",
    "evidence.ip_hash",
    "evidence.user_agent_hash",
)
DEFAULT_CONSENT_FIELDS: tuple[str, ...] = (
    "consent_id",
    "guardian_ref",
    "action",
    "scopes",
    "policy_version",
    "recorded_at",
    "evidence.method",
    "evidence.attestation",
)
ERASURE_EVENT_FIELDS: tuple[str, ...] = (
    "tombstone_ref",
    "guardian_ref",
    "requested_at",
    "confirmed_at",
    "scope",
    "retained",
)

# Data classes the retention schedule governs (doc 57 §1). Each maps to concrete stores in the
# adapters; a class with no configured period is never purged.
RETENTION_CLASSES: dict[str, str] = {
    "learning_records": (
        "C2 learning records: knowledge, mastery, assessment evidence, homework submissions"
    ),
    "learning_events": "learning domain-event outbox",
    "security_audit": "identity audit trail (security/audit logs)",
    "session_credentials": "refresh-token rows (C1 operational)",
    "ai_usage": "AI usage ledger (per-learner inference metering)",
}


SAFEGUARDING_ERASE = "erase"
SAFEGUARDING_RETAIN = "retain_pseudonymised"
SAFEGUARDING_MODES: tuple[str, ...] = (SAFEGUARDING_RETAIN, SAFEGUARDING_ERASE)
SAFEGUARDING_APPROVAL = (
    "PENDING M-Gov approval (DPO + counsel) and FD-04 (mandatory-reporting policy): whether a "
    "safeguarding record must outlive a guardian-requested erasure"
)


class PolicyError(ValueError):
    """An invalid privacy configuration (refused at start-up, never silently corrected)."""


@dataclass(frozen=True)
class RetainedSet:
    """Exactly what an erasure keeps. Configurable; documented as PENDING M-Gov approval."""

    keep_consent_evidence: bool = True
    consent_fields: tuple[str, ...] = DEFAULT_CONSENT_FIELDS
    keep_erasure_event: bool = True
    tombstone_salt: str = ""
    safeguarding_concerns: str = SAFEGUARDING_RETAIN
    approval: str = APPROVAL_STATUS

    def __post_init__(self) -> None:
        unknown = sorted(set(self.consent_fields) - set(CONSENT_FIELDS))
        if unknown:
            raise PolicyError(f"unknown consent tombstone fields: {unknown}")
        if self.safeguarding_concerns not in SAFEGUARDING_MODES:
            raise PolicyError(
                f"safeguarding_concerns must be one of {list(SAFEGUARDING_MODES)}, "
                f"not {self.safeguarding_concerns!r}"
            )

    @property
    def retain_safeguarding(self) -> bool:
        return self.safeguarding_concerns == SAFEGUARDING_RETAIN

    def tombstone_ref(self, student_ref: str) -> str:
        """One-way, salted pseudonym for a learner that no longer exists."""
        digest = hashlib.sha256(f"{self.tombstone_salt}\x00{student_ref}".encode()).hexdigest()
        return f"tomb_{digest[:40]}"

    def describe(self) -> dict[str, object]:
        return {
            "approval": self.approval,
            "consent_evidence": (
                {"kept": True, "fields": list(self.consent_fields), "keyed_by": "tombstone_ref"}
                if self.keep_consent_evidence
                else {"kept": False}
            ),
            "erasure_event": (
                {"kept": True, "fields": list(ERASURE_EVENT_FIELDS), "keyed_by": "tombstone_ref"}
                if self.keep_erasure_event
                else {"kept": False}
            ),
            "safeguarding_concerns": (
                {
                    "kept": True,
                    "mode": SAFEGUARDING_RETAIN,
                    "keyed_by": "tombstone_ref",
                    "approval": SAFEGUARDING_APPROVAL,
                }
                if self.retain_safeguarding
                else {"kept": False, "mode": SAFEGUARDING_ERASE, "approval": SAFEGUARDING_APPROVAL}
            ),
            "student_ref_retained": False,
        }


@dataclass(frozen=True)
class RetentionPolicy:
    """Per data class retention period in seconds. ``None`` = not set ⇒ purge disabled."""

    periods: Mapping[str, float | None] = field(
        default_factory=lambda: dict.fromkeys(RETENTION_CLASSES)
    )
    approval: str = APPROVAL_STATUS

    def __post_init__(self) -> None:
        unknown = sorted(set(self.periods) - set(RETENTION_CLASSES))
        if unknown:
            raise PolicyError(f"unknown retention classes: {unknown}")
        for cls, period in self.periods.items():
            if period is not None and period <= 0:
                raise PolicyError(f"retention period for {cls} must be positive or unset")

    def period(self, data_class: str) -> float | None:
        return self.periods.get(data_class)

    @classmethod
    def from_json(cls, raw: str) -> RetentionPolicy:
        if not raw.strip():
            return cls()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise PolicyError(f"retention policy is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise PolicyError("retention policy must be a JSON object of class -> seconds")
        periods: dict[str, float | None] = dict.fromkeys(RETENTION_CLASSES)
        for key, value in data.items():
            if value is not None and not isinstance(value, (int, float)):
                raise PolicyError(f"retention period for {key} must be a number or null")
            periods[str(key)] = None if value is None else float(value)
        return cls(periods=periods)


@dataclass(frozen=True)
class PrivacyConfig:
    retained: RetainedSet = field(default_factory=RetainedSet)
    retention: RetentionPolicy = field(default_factory=RetentionPolicy)
    confirmation_key: bytes = b""
    confirmation_ttl_s: float = 900.0  # how long a step-1 erasure request may be confirmed

    @property
    def erasure_enabled(self) -> bool:
        return bool(self.confirmation_key)

    @classmethod
    def from_env(cls, env: Mapping[str, str], *, production: bool) -> PrivacyConfig:
        """Read ``TALEEM_PRIVACY_*`` / ``TALEEM_RETENTION_PERIODS`` from the environment.

        Outside production a missing confirmation key gets a random per-process key (requests then
        do not survive a restart). In production a missing key leaves erasure **disabled** (503):
        an erasure flow must never run on an ephemeral or guessable secret.
        """
        key = env.get("TALEEM_PRIVACY_CONFIRMATION_KEY", "").encode()
        if not key and not production:
            key = secrets.token_bytes(32)
        if key and len(key) < 32:
            raise PolicyError("TALEEM_PRIVACY_CONFIRMATION_KEY must be at least 32 bytes")
        keep_consent = env.get("TALEEM_PRIVACY_KEEP_CONSENT_EVIDENCE", "true").lower() != "false"
        fields_raw = env.get("TALEEM_PRIVACY_CONSENT_TOMBSTONE_FIELDS", "")
        fields = (
            tuple(f.strip() for f in fields_raw.split(",") if f.strip())
            if fields_raw.strip()
            else DEFAULT_CONSENT_FIELDS
        )
        retained = RetainedSet(
            keep_consent_evidence=keep_consent,
            consent_fields=fields,
            keep_erasure_event=env.get("TALEEM_PRIVACY_KEEP_ERASURE_EVENT", "true").lower()
            != "false",
            tombstone_salt=env.get("TALEEM_PRIVACY_TOMBSTONE_SALT", ""),
            safeguarding_concerns=(
                env.get("TALEEM_PRIVACY_SAFEGUARDING_CONCERNS", "").strip() or SAFEGUARDING_RETAIN
            ),
        )
        ttl = float(env.get("TALEEM_PRIVACY_CONFIRMATION_TTL_S", "900") or 900)
        return cls(
            retained=retained,
            retention=RetentionPolicy.from_json(env.get("TALEEM_RETENTION_PERIODS", "")),
            confirmation_key=key,
            confirmation_ttl_s=ttl,
        )
