"""SQLAlchemy ORM models for the curriculum_studio schema.

These mirror POSTGRES_SCHEMA.md exactly (table names, columns, keys). Postgres-only concerns —
the ``search_vector`` tsvector, partitioning of ``audit_log``, triggers, and RLS — are created by
the Alembic migration, not here, and are intentionally absent from the ORM so the same models run
on SQLite in tests (design: DATABASE_ARCHITECTURE.md §2, §5, §7).

Every ``__table_args__`` binds ``schema=SCHEMA`` (review F9). ``lock_version`` implements optimistic
locking (§9) via ``__mapper_args__['version_id_col']`` on the mutable aggregate roots.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import SCHEMA, Base, JsonType, PkType

_JSON = JsonType


# --------------------------------------------------------------------------- taxonomy layer


class EducationSystemRow(Base):
    """Curriculum authority/edition; parent_system_id yields provincial/international variants."""

    __tablename__ = "education_system"
    __table_args__ = (
        UniqueConstraint("system_key", name="uq_system_key"),
        CheckConstraint(
            "jurisdiction IN ('national','provincial','international')",
            name="ck_system_jurisdiction",
        ),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    parent_system_id: Mapped[str | None] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.education_system.id", ondelete="RESTRICT")
    )
    system_key: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    jurisdiction: Mapped[str] = mapped_column(Text, nullable=False, default="national")
    curriculum_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class GradeRow(Base):
    """Grade offering within an education system."""

    __tablename__ = "grade"
    __table_args__ = (
        UniqueConstraint("system_id", "grade_key", name="uq_grade"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    system_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.education_system.id", ondelete="CASCADE"), nullable=False
    )
    grade_key: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class SubjectRow(Base):
    """Subject offering within an education system (localized titles)."""

    __tablename__ = "subject"
    __table_args__ = (
        UniqueConstraint("system_id", "subject_key", name="uq_subject"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    system_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.education_system.id", ondelete="CASCADE"), nullable=False
    )
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    titles: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    religious_track: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class CurriculumObjectiveRow(Base):
    """Versioned SLO taxonomy; the alignment + prerequisite-DAG node lessons reference."""

    __tablename__ = "curriculum_objective"
    __table_args__ = (
        UniqueConstraint(
            "system_id", "curriculum_version", "standard_code", name="uq_objective_code"
        ),
        Index("ix_objective_placement", "system_id", "grade_key", "subject_key"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    system_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.education_system.id", ondelete="RESTRICT"), nullable=False
    )
    standard_code: Mapped[str] = mapped_column(Text, nullable=False)
    curriculum_version: Mapped[str] = mapped_column(Text, nullable=False, default="")
    grade_key: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    competency: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    provenance: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __mapper_args__ = {"version_id_col": lock_version}


class ObjectivePrereqRow(Base):
    """Prerequisite DAG edges between SLOs (acyclicity enforced in app)."""

    __tablename__ = "objective_prereq"
    __table_args__ = (
        CheckConstraint("objective_id <> prerequisite_id", name="ck_prereq_no_self"),
        Index("ix_prereq_reverse", "prerequisite_id"),
        {"schema": SCHEMA},
    )

    objective_id: Mapped[str] = mapped_column(
        PkType,
        ForeignKey(f"{SCHEMA}.curriculum_objective.id", ondelete="CASCADE"),
        primary_key=True,
    )
    prerequisite_id: Mapped[str] = mapped_column(
        PkType,
        ForeignKey(f"{SCHEMA}.curriculum_objective.id", ondelete="CASCADE"),
        primary_key=True,
    )


# --------------------------------------------------------------------------- authoring layer


class LessonRow(Base):
    """Lesson aggregate root / mutable working head; body holds the authored document."""

    __tablename__ = "lesson"
    __table_args__ = (
        UniqueConstraint("system_id", "lesson_key", name="uq_lesson_system_key"),
        CheckConstraint(
            "state IN ('draft','in_review','subject_expert','educational_qa','accessibility',"
            "'language','ai_safety','approved','published','archived')",
            name="ck_lesson_state",
        ),
        CheckConstraint(
            "difficulty IN ('intro','developing','secure','challenge')", name="ck_lesson_difficulty"
        ),
        CheckConstraint("estimated_duration_min BETWEEN 1 AND 240", name="ck_lesson_duration"),
        # Plain composite here (portable). The Alembic PostgreSQL migration adds the partial
        # ``WHERE deleted_at IS NULL`` variant that hot-path queries actually use (architecture §4).
        Index("ix_lesson_placement", "system_id", "grade_key", "subject_key", "state"),
        Index("ix_lesson_state", "state"),
        Index("ix_lesson_updated_at", "updated_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    system_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.education_system.id", ondelete="RESTRICT"), nullable=False
    )
    lesson_key: Mapped[str] = mapped_column(String(128), nullable=False)
    grade_key: Mapped[str] = mapped_column(Text, nullable=False)
    subject_key: Mapped[str] = mapped_column(Text, nullable=False)
    chapter_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    topic_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state: Mapped[str] = mapped_column(Text, nullable=False, default="draft")
    difficulty: Mapped[str] = mapped_column(Text, nullable=False, default="intro")
    estimated_duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    author_role: Mapped[str] = mapped_column(Text, nullable=False, default="subject_author")
    derivation: Mapped[str] = mapped_column(Text, nullable=False, default="authored-original")
    license: Mapped[str] = mapped_column(Text, nullable=False, default="authored-original")
    content_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    current_version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # `tags` mirrors the migration's `text[]` (ARRAY on PostgreSQL, JSON on SQLite) so the ORM and
    # the migration agree (CTO H10) and the FTS weight-'B' tag signal is actually populated.
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(Text()).with_variant(JSON(), "sqlite"), nullable=False, default=list
    )
    body: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(Text, nullable=False, default="")

    gates: Mapped[list[QualityGateResultRow]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )
    transitions: Mapped[list[WorkflowTransitionRow]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by="WorkflowTransitionRow.at"
    )
    versions: Mapped[list[LessonVersionRow]] = relationship(
        cascade="save-update, merge",
        order_by="LessonVersionRow.version_no",
    )

    __mapper_args__ = {"version_id_col": lock_version}


class LessonVersionRow(Base):
    """Immutable published version snapshots; append-only, never updated."""

    __tablename__ = "lesson_version"
    __table_args__ = (
        UniqueConstraint("lesson_id", "version_no", name="uq_version_lesson_no"),
        Index("ix_version_lesson_created", "lesson_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="RESTRICT"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    body_snapshot: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    gate_results_snapshot: Mapped[list[Any]] = mapped_column(_JSON, nullable=False, default=list)
    change_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LessonObjectiveRow(Base):
    """Lesson-SLO alignment (outcomes & prerequisites) for coverage queries."""

    __tablename__ = "lesson_objective"
    __table_args__ = (
        CheckConstraint("role IN ('outcome','prerequisite')", name="ck_lo_role"),
        Index("ix_lo_objective", "objective_id", "role"),
        {"schema": SCHEMA},
    )

    lesson_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="CASCADE"), primary_key=True
    )
    objective_id: Mapped[str] = mapped_column(
        PkType,
        ForeignKey(f"{SCHEMA}.curriculum_objective.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)


class QualityGateResultRow(Base):
    """Current-head quality-gate outcomes; all must be green to publish."""

    __tablename__ = "quality_gate_result"
    __table_args__ = (
        CheckConstraint("mode IN ('auto','human')", name="ck_gate_mode"),
        UniqueConstraint("lesson_id", "gate", name="uq_gate_per_lesson"),
        Index("ix_gate_lesson", "lesson_id", "gate"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="CASCADE"), nullable=False
    )
    gate: Mapped[str] = mapped_column(Text, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    findings: Mapped[list[Any]] = mapped_column(_JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WorkflowTransitionRow(Base):
    """Append-only review/workflow trail per lesson."""

    __tablename__ = "workflow_transition"
    __table_args__ = (
        Index("ix_transition_lesson_at", "lesson_id", "at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[str] = mapped_column(Text, nullable=False)
    to_state: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor_role: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


# --------------------------------------------------------------------------- supporting layer


class MediaAssetRow(Base):
    """Content-addressed media registry (original/CC0 only, scanned)."""

    __tablename__ = "media_asset"
    __table_args__ = (
        UniqueConstraint("content_hash", name="uq_media_hash"),
        CheckConstraint("scan_status IN ('pending','clean','flagged')", name="ck_media_scan"),
        CheckConstraint("origin IN ('authored','cc0','licensed')", name="ck_media_origin"),
        Index("ix_media_scan", "scan_status"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    mime: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    license: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    scan_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    alt_text: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class LessonMediaRow(Base):
    """Lesson-media links (role-tagged) for packaging & integrity."""

    __tablename__ = "lesson_media"
    __table_args__ = (
        Index("ix_lesson_media_media", "media_id"),
        {"schema": SCHEMA},
    )

    lesson_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.media_asset.id", ondelete="RESTRICT"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, primary_key=True)


class AttachmentRow(Base):
    """Per-lesson generated downloadable artifacts (bytes in object storage)."""

    __tablename__ = "attachment"
    __table_args__ = (
        Index("ix_attachment_lesson", "lesson_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OfflinePackageRow(Base):
    """Offline day-pack bundle pinned to a specific immutable lesson version."""

    __tablename__ = "offline_package"
    __table_args__ = (
        UniqueConstraint("lesson_id", "version_no", name="uq_offline_pkg"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    lesson_id: Mapped[str] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="CASCADE"), nullable=False
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TranslationRow(Base):
    """Per-field localization status/coverage index (governance, not content)."""

    __tablename__ = "translation"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "field_path", "locale", name="uq_translation"),
        CheckConstraint(
            "status IN ('missing','draft','translated','reviewed')", name="ck_translation_status"
        ),
        Index("ix_translation_target", "entity_type", "entity_id", "locale"),
        Index("ix_translation_status", "status", "locale"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(PkType, nullable=False)
    field_path: Mapped[str] = mapped_column(Text, nullable=False)
    locale: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="missing")
    reviewer_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AuditLogRow(Base):
    """Hash-chained, append-only audit of every mutation (month-partitioned on PostgreSQL)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id", "at"),
        Index("ix_audit_correlation", "correlation_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(PkType, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    actor_role: Mapped[str] = mapped_column(Text, nullable=False, default="")
    before: Mapped[dict[str, Any] | None] = mapped_column(_JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(_JSON)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prev_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    row_hash: Mapped[str] = mapped_column(Text, nullable=False)


class OutboxRow(Base):
    """Transactional outbox; relay delivers undelivered rows at-least-once."""

    __tablename__ = "outbox"
    __table_args__ = (
        Index("ix_outbox_unpublished", "occurred_at"),
        Index("ix_outbox_aggregate", "aggregate_type", "aggregate_id", "occurred_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    aggregate_type: Mapped[str] = mapped_column(Text, nullable=False)
    aggregate_id: Mapped[str] = mapped_column(PkType, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(_JSON, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ItemStatisticsRow(Base):
    """Aggregated de-identified item psychometrics for authoring feedback. No PII."""

    __tablename__ = "item_statistics"
    __table_args__ = (
        UniqueConstraint("item_ref", "sample_window", name="uq_item_stats"),
        Index("ix_item_stats_lesson", "lesson_id"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(PkType, primary_key=True)
    item_ref: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_id: Mapped[str | None] = mapped_column(
        PkType, ForeignKey(f"{SCHEMA}.lesson.id", ondelete="CASCADE")
    )
    attempts: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    p_value: Mapped[float | None] = mapped_column(Numeric(5, 4))
    discrimination: Mapped[float | None] = mapped_column(Numeric(5, 4))
    mean_time_s: Mapped[float | None] = mapped_column(Numeric(8, 2))
    misconception_hit_rate: Mapped[dict[str, Any]] = mapped_column(
        _JSON, nullable=False, default=dict
    )
    sample_window: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
