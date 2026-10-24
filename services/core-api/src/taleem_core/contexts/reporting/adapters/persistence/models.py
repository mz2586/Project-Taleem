"""ORM models for the reporting schema (see alembic 0014_reporting).

- ``report_card`` — C2 learning records. ``body`` is the canonical JSON text the ``content_hash``
  covers, stored as text so the exact bytes survive (a JSONB column would re-serialise them).
  Immutable once written: on PostgreSQL a trigger refuses any UPDATE except setting the
  acknowledgement once. ``supersedes`` names the corrected card (one successor per card); only one
  original card exists per learner, class and period.
- ``report_card_audit`` — who issued / acknowledged which card, when. Refs only.
- ``report_card_outbox`` — ``ReportCardIssued`` events (refs only), for the notification relay.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import REPORTING_SCHEMA, JsonType, ReportingBase


class ReportCardRow(ReportingBase):
    __tablename__ = "report_card"
    __table_args__ = (
        Index(
            "uq_report_card_original",
            "student_ref",
            "class_id",
            "period_start",
            "period_end",
            unique=True,
            postgresql_where=text("supersedes IS NULL"),
            sqlite_where=text("supersedes IS NULL"),
        ),
        Index("ix_report_card_student", "student_ref", "issued_at"),
        Index("ix_report_card_class", "organization_id", "class_id", "period_start", "period_end"),
        {"schema": REPORTING_SCHEMA},
    )

    card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    period_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    period_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(f"{REPORTING_SCHEMA}.report_card.card_id"),
        nullable=True,
        unique=True,
    )
    issued_by: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_at: Mapped[float] = mapped_column(Float, nullable=False)
    acknowledged_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ReportCardAuditRow(ReportingBase):
    __tablename__ = "report_card_audit"
    __table_args__ = (
        Index("ix_report_card_audit_subject", "subject_ref", "at"),
        {"schema": REPORTING_SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    card_id: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[float] = mapped_column(Float, nullable=False)


class ReportCardOutboxRow(ReportingBase):
    __tablename__ = "report_card_outbox"
    __table_args__ = (
        Index("ix_report_card_outbox_student", "student_ref"),
        Index("ix_report_card_outbox_occurred", "occurred_at"),
        {"schema": REPORTING_SCHEMA},
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    student_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False)
    occurred_at: Mapped[float] = mapped_column(Float, nullable=False)
    published_at: Mapped[float | None] = mapped_column(Float, nullable=True)
