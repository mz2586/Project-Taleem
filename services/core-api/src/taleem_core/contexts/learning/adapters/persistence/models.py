"""ORM models for the learning-context durable data (LEARNING_DOMAIN_MODEL §9).

Tables: student_knowledge (aggregate root), objective_mastery (owned), assessment_evidence
(immutable, append-only — the system of record), and learning_outbox (transactional events).
Value objects with no query need (memory/confidence/pace/threshold/misconceptions) are stored as
JSON on the objective row; queryable facets (mastery_value, state, next_review_at) are columns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import LEARNING_SCHEMA, JsonType, LearningBase, PkType

_JSON = JsonType


class StudentKnowledgeRow(LearningBase):
    """Aggregate root: one learner's knowledge state. Keyed by pseudonymous student_ref."""

    __tablename__ = "student_knowledge"
    __table_args__ = (
        UniqueConstraint("student_ref", name="uq_student_ref"),
        {"schema": LEARNING_SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    student_ref: Mapped[str] = mapped_column(Text, nullable=False)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    objectives: Mapped[list[ObjectiveMasteryRow]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )

    __mapper_args__ = {"version_id_col": lock_version}


class ObjectiveMasteryRow(LearningBase):
    """One learner's mastery of one SLO (owned by StudentKnowledge)."""

    __tablename__ = "objective_mastery"
    __table_args__ = (
        UniqueConstraint("student_ref", "objective_code", name="uq_objective_mastery"),
        Index("ix_om_review", "student_ref", "next_review_at"),
        {"schema": LEARNING_SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(
        PkType,
        ForeignKey(f"{LEARNING_SCHEMA}.student_knowledge.id", ondelete="CASCADE"),
        nullable=False,
    )
    student_ref: Mapped[str] = mapped_column(Text, nullable=False)
    objective_code: Mapped[str] = mapped_column(Text, nullable=False)
    mastery_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mastery_uncertainty: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    state: Mapped[str] = mapped_column(Text, nullable=False, default="not_started")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    memory: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    confidence: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    pace: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    threshold: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    misconceptions: Mapped[list[Any]] = mapped_column(_JSON, nullable=False, default=list)


class AssessmentEvidenceRow(LearningBase):
    """Immutable, append-only evidence — the system of record for every estimate."""

    __tablename__ = "assessment_evidence"
    __table_args__ = (
        Index("ix_evidence_student", "student_ref", "occurred_at"),
        Index("ix_evidence_objective", "student_ref", "objective_code"),
        {"schema": LEARNING_SCHEMA},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # evidence_id (domain-supplied string)
    student_ref: Mapped[str] = mapped_column(Text, nullable=False)
    objective_code: Mapped[str] = mapped_column(Text, nullable=False)
    item_ref: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str] = mapped_column(Text, nullable=False)
    misconception_hits: Mapped[list[Any]] = mapped_column(_JSON, nullable=False, default=list)
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mastery_before: Mapped[float] = mapped_column(Float, nullable=False)
    mastery_after: Mapped[float] = mapped_column(Float, nullable=False)
    occurred_at: Mapped[float] = mapped_column(Float, nullable=False)


class LearningOutboxRow(LearningBase):
    """Transactional outbox for learning domain events."""

    __tablename__ = "learning_outbox"
    __table_args__ = (
        Index("ix_learning_outbox_unpublished", "occurred_at"),
        {"schema": LEARNING_SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    occurred_at: Mapped[float] = mapped_column(Float, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
