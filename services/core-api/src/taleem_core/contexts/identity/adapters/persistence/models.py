"""ORM models for the identity schema (see alembic 0004_identity).

Four tables, and the shape of each one encodes a rule:

- ``guardian_account`` — the only table in the platform holding an adult contact address.
- ``learner_account`` — a child. Note what is *absent*: no email, no phone, no date of birth, no
  address. A display name, a grade, a locale, a PIN hash, and the guardian who is responsible.
- ``consent_record`` — append-only evidence. No ``updated_at``, no status column to flip: a change
  of mind is a new row.
- ``audit_event`` — append-only. Same reasoning; an audit row that can be updated is not an audit.

Optimistic-lock version columns sit on the two mutable tables so a concurrent guardian edit and a
sign-in counter update cannot silently overwrite each other (the app maps the loser to a 409).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import IDENTITY_SCHEMA, IdentityBase, JsonType


class GuardianRow(IdentityBase):
    __tablename__ = "guardian_account"
    __table_args__ = (
        Index("ix_guardian_family_code", "family_code", unique=True),
        {"schema": IDENTITY_SCHEMA},
    )

    guardian_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Unique so a second registration for the same address is refused by the database, not only by
    # the service — two concurrent registrations would otherwise both pass the read check.
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    passphrase_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    family_code: Mapped[str] = mapped_column(String(16), nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ur")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}


class LearnerRow(IdentityBase):
    __tablename__ = "learner_account"
    __table_args__ = (
        Index("ix_learner_guardian", "guardian_ref"),
        # A learner's display name is their sign-in handle *within a family*, so it must be unique
        # there and nowhere else — two unrelated children may of course share a name.
        Index("ix_learner_family_roster", "guardian_ref", "roster_key", unique=True),
        {"schema": IDENTITY_SCHEMA},
    )

    student_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    guardian_ref: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{IDENTITY_SCHEMA}.guardian_account.guardian_ref", ondelete="CASCADE"),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    roster_key: Mapped[str] = mapped_column(String(60), nullable=False)
    pin_hash: Mapped[str] = mapped_column(Text, nullable=False)
    grade_band: Mapped[str] = mapped_column(String(16), nullable=False, default="middle")
    grade_level: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, default="ur")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    known_devices: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}


class ConsentRow(IdentityBase):
    """Append-only. Nothing in the application updates or deletes a row here."""

    __tablename__ = "consent_record"
    __table_args__ = (
        Index("ix_consent_student_time", "student_ref", "recorded_at"),
        Index("ix_consent_guardian", "guardian_ref"),
        {"schema": IDENTITY_SCHEMA},
    )

    consent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    guardian_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    student_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)


class AuditRow(IdentityBase):
    """Append-only. Nothing in the application updates or deletes a row here."""

    __tablename__ = "audit_event"
    __table_args__ = (
        Index("ix_audit_subject_time", "subject_ref", "at"),
        Index("ix_audit_actor_time", "actor_ref", "at"),
        {"schema": IDENTITY_SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    at: Mapped[float] = mapped_column(Float, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
