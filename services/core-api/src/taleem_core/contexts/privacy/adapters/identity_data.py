"""Identity store: learner account, consent evidence, refresh-token family, audit entries.

Uses the identity context's ORM models and session factory; changes none of its code. The
identity application treats ``consent_record`` and ``audit_event`` as append-only — an erasure is
the one sanctioned exception, and it is itself recorded as the tombstone audit row.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from ....platform.correlation import get_correlation_id
from ...identity.adapters.persistence.models import (
    AuditRow,
    ConsentRow,
    LearnerRow,
    RefreshTokenRow,
)
from ..application.ports import Tombstone
from ..domain.policy import RetainedSet
from ._rows import affected, mentions, row_dict, text_contains

TOMBSTONE_ACTION = "privacy.learner_erased"
_S = "identity"


class IdentityLearnerData:
    name = "identity"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def covers(self) -> tuple[str, ...]:
        return (
            f"{_S}.learner_account",
            f"{_S}.consent_record",
            f"{_S}.refresh_token",
            f"{_S}.audit_event",
        )

    # -- reads ------------------------------------------------------------------------------

    def guardian_of(self, student_ref: str) -> str | None:
        with self._sf() as s:
            row = s.get(LearnerRow, student_ref)
            return row.guardian_ref if row is not None else None

    @staticmethod
    def _audit_rows(s: Session, ref: str) -> list[AuditRow]:
        rows = s.scalars(
            select(AuditRow).where(
                or_(
                    AuditRow.subject_ref == ref,
                    AuditRow.actor_ref == ref,
                    text_contains(AuditRow.detail, ref),
                )
            )
        ).all()
        return [r for r in rows if ref in (r.subject_ref, r.actor_ref) or mentions(r.detail, ref)]

    @staticmethod
    def _consent_rows(s: Session, ref: str) -> list[ConsentRow]:
        rows = s.scalars(
            select(ConsentRow).where(
                or_(ConsentRow.student_ref == ref, text_contains(ConsentRow.evidence, ref))
            )
        ).all()
        return [r for r in rows if r.student_ref == ref or mentions(r.evidence, ref)]

    def export(self, student_ref: str) -> dict[str, Any]:
        with self._sf() as s:
            learner = s.get(LearnerRow, student_ref)
            tokens = s.scalars(
                select(RefreshTokenRow).where(RefreshTokenRow.subject_ref == student_ref)
            ).all()
            return {
                "learner_account": (
                    row_dict(learner, exclude=("pin_hash",)) if learner is not None else None
                ),
                "consent_records": [row_dict(r) for r in self._consent_rows(s, student_ref)],
                "refresh_tokens": [row_dict(t, exclude=("token_hash",)) for t in tokens],
                "audit_events": [row_dict(r) for r in self._audit_rows(s, student_ref)],
                "withheld": [
                    {"field": "learner_account.pin_hash", "reason": "credential digest"},
                    {"field": "refresh_token.token_hash", "reason": "credential digest"},
                ],
            }

    def remaining(self, student_ref: str) -> dict[str, int]:
        with self._sf() as s:
            return {
                "learner_account": int(s.get(LearnerRow, student_ref) is not None),
                "consent_record": len(self._consent_rows(s, student_ref)),
                "refresh_token": int(
                    s.scalar(
                        select(func.count())
                        .select_from(RefreshTokenRow)
                        .where(RefreshTokenRow.subject_ref == student_ref)
                    )
                    or 0
                ),
                "audit_event": len(self._audit_rows(s, student_ref)),
            }

    def blockers(self) -> list[str]:
        return []

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        column = {
            "security_audit": AuditRow.at,
            "session_credentials": RefreshTokenRow.issued_at,
        }.get(data_class)
        if column is None:
            return None
        with self._sf() as s:
            return int(s.scalar(select(func.count()).where(column < cutoff)) or 0)

    # -- erasure ----------------------------------------------------------------------------

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        return self.erase_with_tombstone(student_ref, retained, None)

    def erase_with_tombstone(
        self, student_ref: str, retained: RetainedSet, tombstone: Tombstone | None
    ) -> dict[str, int]:
        """One transaction: anonymize/delete everything, then append the tombstone."""
        tomb_ref = retained.tombstone_ref(student_ref)
        with self._sf() as s, s.begin():
            consents = self._consent_rows(s, student_ref)
            if retained.keep_consent_evidence:
                for row in consents:
                    _anonymize_consent(row, tomb_ref, retained.consent_fields)
            else:
                for row in consents:
                    s.delete(row)
            audits = self._audit_rows(s, student_ref)
            for audit in audits:
                s.delete(audit)
            tokens = s.execute(
                delete(RefreshTokenRow).where(RefreshTokenRow.subject_ref == student_ref)
            )
            learners = s.execute(delete(LearnerRow).where(LearnerRow.student_ref == student_ref))
            if tombstone is not None:
                s.add(
                    AuditRow(
                        event_id=f"tomb-{uuid.uuid4().hex}",
                        at=tombstone.confirmed_at,
                        action=TOMBSTONE_ACTION,
                        actor_ref=tombstone.guardian_ref,
                        actor_role="guardian",
                        subject_ref=tombstone.tombstone_ref,
                        correlation_id=get_correlation_id() or "",
                        detail={
                            "tombstone_ref": tombstone.tombstone_ref,
                            "requested_at": tombstone.requested_at,
                            "confirmed_at": tombstone.confirmed_at,
                            "scope": list(tombstone.scope),
                            "retained": tombstone.retained,
                        },
                    )
                )
        return {
            "learner_account": affected(learners),
            "consent_record": len(consents),
            "refresh_token": affected(tokens),
            "audit_event": len(audits),
        }


def _anonymize_consent(row: ConsentRow, tomb_ref: str, keep: tuple[str, ...]) -> None:
    """Re-key a consent decision to the tombstone ref and blank every field not retained."""
    row.student_ref = tomb_ref
    if "consent_id" not in keep:
        row.consent_id = f"tomb-{uuid.uuid4().hex}"
    if "guardian_ref" not in keep:
        row.guardian_ref = ""
    if "action" not in keep:
        row.action = ""
    if "scopes" not in keep:
        row.scopes = []
    if "policy_version" not in keep:
        row.policy_version = ""
    if "recorded_at" not in keep:
        row.recorded_at = 0.0
    evidence = dict(row.evidence or {})
    row.evidence = {
        k: v for k, v in evidence.items() if f"evidence.{k}" in keep and not isinstance(v, dict)
    }
