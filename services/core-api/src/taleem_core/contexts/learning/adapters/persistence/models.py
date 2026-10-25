"""ORM models for the learning-context durable data (LEARNING_DOMAIN_MODEL §9).

Tables: student_knowledge (aggregate root), objective_mastery (owned), assessment_evidence
(immutable, append-only — the system of record), learning_outbox (transactional events),
ai_usage_ledger (per-learner AI inference usage for quotas; counts only) and unit_check_sitting
(end-of-unit examination sittings, migration 0019).
Value objects with no query need (memory/confidence/pace/threshold/misconceptions) are stored as
JSON on the objective row; queryable facets (mastery_value, state, next_review_at) are columns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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
    # The published lesson answered against (migration 0015). NULL = not recorded: never guessed.
    lesson_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    lesson_version: Mapped[int | None] = mapped_column(Integer, nullable=True)


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


# bigserial on PostgreSQL; SQLite only auto-increments an INTEGER PRIMARY KEY.
_LedgerId = BigInteger().with_variant(Integer(), "sqlite")


class AIUsageRow(LearningBase):
    """One AI gateway call's usage (migration 0007). Counts only — never prompt or output text.

    ``learner_ref`` is the pseudonymous student_ref; the row carries nothing else about the learner.
    """

    __tablename__ = "ai_usage_ledger"
    __table_args__ = (
        Index("ix_ai_usage_learner_time", "learner_ref", "recorded_at"),
        Index("ix_ai_usage_time", "recorded_at"),
        {"schema": LEARNING_SCHEMA},
    )

    id: Mapped[int] = mapped_column(_LedgerId, primary_key=True, autoincrement=True)
    learner_ref: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    recorded_at: Mapped[float] = mapped_column(Float, nullable=False)


# The sitting statuses (``domain.progression.SittingStatus``; migration 0019's CHECK).
SITTING_STATUSES: tuple[str, ...] = ("in_progress", "passed", "failed", "incomplete")
_STATUS_IN = ", ".join(f"'{v}'" for v in SITTING_STATUSES)


class UnitCheckSittingRow(LearningBase):
    """One unit-check sitting (PROGRESSION_AND_EXAMINATION_CONTRACT §2; migration 0019).

    A C2 learning record keyed by the pseudonymous ``student_ref``. ``items`` is the paper (item
    and lesson references only — never an answer key); ``answers`` maps an item ref to the
    learner's answer and its server-side outcome; ``result`` is the score once finished. At most
    one ``in_progress`` sitting per learner and unit (partial unique index). Optimistic-locked.
    """

    __tablename__ = "unit_check_sitting"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_IN})", name="ck_sitting_status"),
        CheckConstraint("pass_percent BETWEEN 1 AND 100", name="ck_sitting_pass_percent"),
        CheckConstraint("expires_at > started_at", name="ck_sitting_window"),
        CheckConstraint("substr(sitting_id, 1, 4) = 'ucs_'", name="ck_sitting_ref"),
        Index("ix_sitting_student", "student_ref", "started_at"),
        Index("ix_sitting_unit", "student_ref", "unit_id"),
        Index(
            "uq_sitting_in_progress",
            "student_ref",
            "unit_id",
            unique=True,
            postgresql_where=text("status = 'in_progress'"),
            sqlite_where=text("status = 'in_progress'"),
        ),
        {"schema": LEARNING_SCHEMA},
    )

    sitting_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    student_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    pack_id: Mapped[str] = mapped_column(String(32), nullable=False)
    grade_key: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(64), nullable=False)
    unit_id: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_title: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    items: Mapped[list[Any]] = mapped_column(_JSON, nullable=False, default=list)
    answers: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    pass_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[float] = mapped_column(Float, nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False)
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(_JSON, nullable=True)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": lock_version}
