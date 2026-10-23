"""ORM models for the safeguarding schema (see alembic 0012_safeguarding).

- ``concern`` — one raised concern. Pseudonymous refs only (``subject_ref`` is the learner's
  ``student_ref``; ``raised_by_ref`` is that learner or their guardian). ``free_text`` is the
  raiser's own short words and is shown to a safeguarding lead and nobody else.
- ``concern_note`` — a safeguarding lead's triage note.
- ``concern_audit`` — append-only record of every action, by actor subject. ``detail`` carries
  statuses and enum values only, never free text or a note body.

The privacy context covers all three (``contexts/privacy/adapters/safeguarding_data.py``).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import SAFEGUARDING_SCHEMA, JsonType, SafeguardingBase


class ConcernRow(SafeguardingBase):
    __tablename__ = "concern"
    __table_args__ = (
        Index("ix_concern_status_priority", "status", "priority", "created_at"),
        Index("ix_concern_subject", "subject_ref"),
        Index("ix_concern_raised_by", "raised_by_ref"),
        {"schema": SAFEGUARDING_SCHEMA},
    )

    concern_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    subject_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    raised_by_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    raised_by_role: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(4), nullable=False)
    free_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_screen: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    context_lesson_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    acknowledged_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    escalated_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    escalated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}


class ConcernNoteRow(SafeguardingBase):
    __tablename__ = "concern_note"
    __table_args__ = (
        Index("ix_concern_note_concern", "concern_id", "created_at"),
        {"schema": SAFEGUARDING_SCHEMA},
    )

    note_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    concern_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SAFEGUARDING_SCHEMA}.concern.concern_id", ondelete="CASCADE"),
        nullable=False,
    )
    author_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)


class ConcernAuditRow(SafeguardingBase):
    __tablename__ = "concern_audit"
    __table_args__ = (
        Index("ix_concern_audit_concern", "concern_id", "at"),
        Index("ix_concern_audit_actor", "actor_ref"),
        {"schema": SAFEGUARDING_SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # No foreign key, so no cascade can ever remove audit rows silently. Only the privacy erasure
    # touches them, explicitly (removed or re-keyed per the retained set), and reports the count.
    concern_id: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    at: Mapped[float] = mapped_column(Float, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JsonType, nullable=False, default=dict)
