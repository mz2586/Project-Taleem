"""SQL repositories implementing the identity ports.

Mapping is explicit in both directions rather than exposing ORM rows to the application, so the
domain objects stay free of SQLAlchemy and a change of storage does not ripple upward.

The consent and audit repositories implement only ``append`` and reads. There is no code path here
that issues an UPDATE or DELETE against either table.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.accounts import AccountStatus, GuardianAccount, LearnerAccount, roster_key
from ...domain.audit import AuditAction, AuditEvent
from ...domain.consent import ConsentAction, ConsentEvidence, ConsentRecord, ConsentScope
from ...domain.sessions import RefreshToken
from .models import AuditRow, ConsentRow, GuardianRow, LearnerRow, RefreshTokenRow

# ------------------------------------------------------------------------------------- mapping


def _to_guardian(row: GuardianRow) -> GuardianAccount:
    return GuardianAccount(
        guardian_ref=row.guardian_ref,
        email=row.email,
        passphrase_hash=row.passphrase_hash,
        display_name=row.display_name,
        family_code=row.family_code,
        locale=row.locale,
        status=AccountStatus(row.status),
        failed_attempts=row.failed_attempts,
        created_at=row.created_at,
        version=row.version,
    )


def _to_learner(row: LearnerRow) -> LearnerAccount:
    return LearnerAccount(
        student_ref=row.student_ref,
        guardian_ref=row.guardian_ref,
        display_name=row.display_name,
        pin_hash=row.pin_hash,
        grade_band=row.grade_band,
        grade_level=row.grade_level,
        locale=row.locale,
        status=AccountStatus(row.status),
        failed_attempts=row.failed_attempts,
        created_at=row.created_at,
        version=row.version,
        known_devices=list(row.known_devices or []),
    )


def _to_consent(row: ConsentRow) -> ConsentRecord:
    evidence = dict(row.evidence or {})
    return ConsentRecord(
        consent_id=row.consent_id,
        guardian_ref=row.guardian_ref,
        student_ref=row.student_ref,
        action=ConsentAction(row.action),
        # Unknown scope strings are dropped rather than raising: a database written by a newer
        # release must not make an older instance fail to read consent at all, which would deny a
        # child their lesson over a vocabulary mismatch.
        scopes=frozenset(ConsentScope(s) for s in (row.scopes or []) if s in set(ConsentScope)),
        policy_version=row.policy_version,
        recorded_at=row.recorded_at,
        evidence=ConsentEvidence(
            method=str(evidence.get("method", "")),
            ip_hash=str(evidence.get("ip_hash", "")),
            user_agent_hash=str(evidence.get("user_agent_hash", "")),
            attestation=str(evidence.get("attestation", "")),
        ),
    )


def _to_refresh(row: RefreshTokenRow) -> RefreshToken:
    return RefreshToken(
        token_id=row.token_id,
        token_hash=row.token_hash,
        subject_ref=row.subject_ref,
        role=row.role,
        device_id=row.device_id,
        family_id=row.family_id,
        issued_at=row.issued_at,
        expires_at=row.expires_at,
        consumed_at=row.consumed_at,
        revoked_at=row.revoked_at,
    )


def _to_audit(row: AuditRow) -> AuditEvent:
    return AuditEvent(
        event_id=row.event_id,
        at=row.at,
        action=AuditAction(row.action),
        actor_ref=row.actor_ref,
        actor_role=row.actor_role,
        subject_ref=row.subject_ref,
        correlation_id=row.correlation_id,
        detail=dict(row.detail or {}),
    )


# -------------------------------------------------------------------------------- repositories


class SqlGuardianRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, account: GuardianAccount) -> None:
        self._session.add(
            GuardianRow(
                guardian_ref=account.guardian_ref,
                email=account.email,
                passphrase_hash=account.passphrase_hash,
                display_name=account.display_name,
                family_code=account.family_code,
                locale=account.locale,
                status=account.status.value,
                failed_attempts=account.failed_attempts,
                created_at=account.created_at,
            )
        )

    def get(self, guardian_ref: str) -> GuardianAccount | None:
        row = self._session.get(GuardianRow, guardian_ref)
        return _to_guardian(row) if row else None

    def by_email(self, email: str) -> GuardianAccount | None:
        row = self._session.scalars(
            select(GuardianRow).where(GuardianRow.email == email)
        ).one_or_none()
        return _to_guardian(row) if row else None

    def by_family_code(self, family_code: str) -> GuardianAccount | None:
        row = self._session.scalars(
            select(GuardianRow).where(GuardianRow.family_code == family_code)
        ).one_or_none()
        return _to_guardian(row) if row else None

    def save(self, account: GuardianAccount) -> None:
        row = self._session.get(GuardianRow, account.guardian_ref)
        if row is None:
            self.add(account)
            return
        row.email = account.email
        row.passphrase_hash = account.passphrase_hash
        row.display_name = account.display_name
        row.family_code = account.family_code
        row.locale = account.locale
        row.status = account.status.value
        row.failed_attempts = account.failed_attempts


class SqlLearnerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, account: LearnerAccount) -> None:
        self._session.add(
            LearnerRow(
                student_ref=account.student_ref,
                guardian_ref=account.guardian_ref,
                display_name=account.display_name,
                roster_key=account.roster_key,
                pin_hash=account.pin_hash,
                grade_band=account.grade_band,
                grade_level=account.grade_level,
                locale=account.locale,
                status=account.status.value,
                failed_attempts=account.failed_attempts,
                created_at=account.created_at,
                known_devices=list(account.known_devices),
            )
        )

    def get(self, student_ref: str) -> LearnerAccount | None:
        row = self._session.get(LearnerRow, student_ref)
        return _to_learner(row) if row else None

    def for_guardian(self, guardian_ref: str) -> list[LearnerAccount]:
        rows = self._session.scalars(
            select(LearnerRow)
            .where(LearnerRow.guardian_ref == guardian_ref)
            .order_by(LearnerRow.created_at, LearnerRow.student_ref)
        ).all()
        return [_to_learner(row) for row in rows]

    def save(self, account: LearnerAccount) -> None:
        row = self._session.get(LearnerRow, account.student_ref)
        if row is None:
            self.add(account)
            return
        row.display_name = account.display_name
        row.roster_key = roster_key(account.display_name)
        row.pin_hash = account.pin_hash
        row.grade_band = account.grade_band
        row.grade_level = account.grade_level
        row.locale = account.locale
        row.status = account.status.value
        row.failed_attempts = account.failed_attempts
        row.known_devices = list(account.known_devices)


class SqlConsentRepository:
    """Append + read only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, record: ConsentRecord) -> None:
        self._session.add(
            ConsentRow(
                consent_id=record.consent_id,
                guardian_ref=record.guardian_ref,
                student_ref=record.student_ref,
                action=record.action.value,
                scopes=sorted(s.value for s in record.scopes),
                policy_version=record.policy_version,
                recorded_at=record.recorded_at,
                evidence={
                    "method": record.evidence.method,
                    "ip_hash": record.evidence.ip_hash,
                    "user_agent_hash": record.evidence.user_agent_hash,
                    "attestation": record.evidence.attestation,
                },
            )
        )

    def history(self, student_ref: str) -> list[ConsentRecord]:
        rows = self._session.scalars(
            select(ConsentRow)
            .where(ConsentRow.student_ref == student_ref)
            .order_by(ConsentRow.recorded_at, ConsentRow.consent_id)
        ).all()
        return [_to_consent(row) for row in rows]

    def history_for_guardian(self, guardian_ref: str) -> list[ConsentRecord]:
        rows = self._session.scalars(
            select(ConsentRow)
            .where(ConsentRow.guardian_ref == guardian_ref)
            .order_by(ConsentRow.recorded_at, ConsentRow.consent_id)
        ).all()
        return [_to_consent(row) for row in rows]


class SqlAuditRepository:
    """Append + read only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, event: AuditEvent) -> None:
        self._session.add(
            AuditRow(
                event_id=event.event_id,
                at=event.at,
                action=event.action.value,
                actor_ref=event.actor_ref,
                actor_role=event.actor_role,
                subject_ref=event.subject_ref,
                correlation_id=event.correlation_id,
                detail=dict(event.detail),
            )
        )

    def for_subject(self, subject_ref: str, *, limit: int = 100) -> list[AuditEvent]:
        rows = self._session.scalars(
            select(AuditRow)
            .where(AuditRow.subject_ref == subject_ref)
            .order_by(AuditRow.at.desc(), AuditRow.event_id.desc())
            .limit(limit)
        ).all()
        return [_to_audit(row) for row in rows]

    def for_guardian_family(
        self, guardian_ref: str, student_refs: list[str], *, limit: int = 100
    ) -> list[AuditEvent]:
        """Everything about this guardian and their own children — and nothing else."""
        subjects = [guardian_ref, *student_refs]
        rows = self._session.scalars(
            select(AuditRow)
            .where(AuditRow.subject_ref.in_(subjects))
            .order_by(AuditRow.at.desc(), AuditRow.event_id.desc())
            .limit(limit)
        ).all()
        return [_to_audit(row) for row in rows]


class SqlRefreshTokenRepository:
    """Primary-key reads only. The presented secret is verified against the stored digest, so an
    id that leaks (in a log, say) is not itself a credential."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, token: RefreshToken) -> None:
        self._session.add(
            RefreshTokenRow(
                token_id=token.token_id,
                token_hash=token.token_hash,
                subject_ref=token.subject_ref,
                role=token.role,
                device_id=token.device_id,
                family_id=token.family_id,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                consumed_at=token.consumed_at,
                revoked_at=token.revoked_at,
            )
        )

    def get(self, token_id: str) -> RefreshToken | None:
        row = self._session.get(RefreshTokenRow, token_id)
        return _to_refresh(row) if row else None

    def save(self, token: RefreshToken) -> None:
        row = self._session.get(RefreshTokenRow, token.token_id)
        if row is None:
            self.add(token)
            return
        row.consumed_at = token.consumed_at
        row.revoked_at = token.revoked_at

    def revoke_family(self, family_id: str, *, now: float) -> int:
        """Kill an entire rotation chain. Called on reuse detection, where the legitimate holder and
        a thief both hold members of the chain and cannot be told apart."""
        rows = self._session.scalars(
            select(RefreshTokenRow).where(
                RefreshTokenRow.family_id == family_id, RefreshTokenRow.revoked_at.is_(None)
            )
        ).all()
        for row in rows:
            row.revoked_at = now
        return len(rows)

    def revoke_all_for(self, subject_ref: str, *, now: float) -> int:
        """Every session for one subject — used on sign-out-everywhere, a PIN reset, and whenever a
        guardian withdraws consent, so a live device stops at the next refresh rather than the next
        access-token expiry."""
        rows = self._session.scalars(
            select(RefreshTokenRow).where(
                RefreshTokenRow.subject_ref == subject_ref, RefreshTokenRow.revoked_at.is_(None)
            )
        ).all()
        for row in rows:
            row.revoked_at = now
        return len(rows)
