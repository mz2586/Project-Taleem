"""learning schema (Student Knowledge Model + evidence + outbox)

Revision ID: 0002_learning
Revises: 0001_initial
Create Date: 2026-07-21

Creates the ``learning`` bounded-context schema — the Student Knowledge Model aggregate
(``student_knowledge`` + ``objective_mastery``), the immutable append-only ``assessment_evidence``
system of record, and the transactional ``learning_outbox`` — matching the ORM models in
``contexts/learning/adapters/persistence/models.py`` (CTO H3). Sharded/keyed by ``student_ref``.

Reversible: ``downgrade`` drops the schema (CASCADE). PostgreSQL-specific (JSONB); the ORM runs on
SQLite in tests via ``metadata.create_all`` and column parity is asserted by a dedicated CI test.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_learning"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS learning",
    """
    CREATE TABLE learning.student_knowledge (
        id           uuid PRIMARY KEY,
        student_ref  text NOT NULL,
        lock_version int  NOT NULL DEFAULT 1,
        updated_at   timestamptz NOT NULL DEFAULT now(),
        CONSTRAINT uq_student_ref UNIQUE (student_ref)
    )
    """,
    "COMMENT ON TABLE learning.student_knowledge IS "
    "'Student Knowledge aggregate root; keyed by pseudonymous student_ref (no PII).'",
    """
    CREATE TABLE learning.objective_mastery (
        id                   uuid PRIMARY KEY,
        knowledge_id         uuid NOT NULL REFERENCES learning.student_knowledge (id) ON DELETE CASCADE,
        student_ref          text NOT NULL,
        objective_code       text NOT NULL,
        mastery_value        double precision NOT NULL DEFAULT 0.0,
        mastery_uncertainty  double precision NOT NULL DEFAULT 1.0,
        state                text NOT NULL DEFAULT 'not_started',
        attempts             int  NOT NULL DEFAULT 0,
        correct_streak       int  NOT NULL DEFAULT 0,
        consecutive_failures int  NOT NULL DEFAULT 0,
        next_review_at       double precision NOT NULL DEFAULT 0.0,
        memory               jsonb NOT NULL DEFAULT '{}'::jsonb,
        confidence           jsonb NOT NULL DEFAULT '{}'::jsonb,
        pace                 jsonb NOT NULL DEFAULT '{}'::jsonb,
        threshold            jsonb NOT NULL DEFAULT '{}'::jsonb,
        misconceptions       jsonb NOT NULL DEFAULT '[]'::jsonb,
        CONSTRAINT uq_objective_mastery UNIQUE (student_ref, objective_code)
    )
    """,
    "CREATE INDEX ix_om_review ON learning.objective_mastery (student_ref, next_review_at)",
    # Immutable, append-only evidence — the system of record. id is a domain-supplied string.
    """
    CREATE TABLE learning.assessment_evidence (
        id                 text PRIMARY KEY,
        student_ref        text NOT NULL,
        objective_code     text NOT NULL,
        item_ref           text NOT NULL,
        session_id         text NOT NULL,
        outcome            text NOT NULL,
        context            text NOT NULL,
        misconception_hits jsonb NOT NULL DEFAULT '[]'::jsonb,
        hints_used         int  NOT NULL DEFAULT 0,
        response_time_ms   int  NOT NULL DEFAULT 0,
        mastery_before     double precision NOT NULL,
        mastery_after      double precision NOT NULL,
        occurred_at        double precision NOT NULL
    )
    """,
    "CREATE INDEX ix_evidence_student ON learning.assessment_evidence (student_ref, occurred_at)",
    "CREATE INDEX ix_evidence_objective ON learning.assessment_evidence (student_ref, objective_code)",
    # assessment_evidence is append-only — forbid UPDATE/DELETE (tamper-evidence of the record).
    """
    CREATE FUNCTION learning.forbid_mutation() RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'append-only table %: % is forbidden', TG_TABLE_NAME, TG_OP;
    END;
    $$ LANGUAGE plpgsql
    """,
    "CREATE TRIGGER trg_evidence_immutable BEFORE UPDATE OR DELETE "
    "ON learning.assessment_evidence FOR EACH ROW "
    "EXECUTE FUNCTION learning.forbid_mutation()",
    """
    CREATE TABLE learning.learning_outbox (
        id             uuid PRIMARY KEY,
        aggregate_type text NOT NULL,
        aggregate_id   text NOT NULL,
        event_type     text NOT NULL,
        payload        jsonb NOT NULL,
        occurred_at    double precision NOT NULL,
        published_at   timestamptz
    )
    """,
    "CREATE INDEX ix_learning_outbox_unpublished ON learning.learning_outbox (occurred_at)",
    # RLS defence-in-depth: rows are per-learner; app scopes by student_ref (auth PDP is primary).
    "ALTER TABLE learning.student_knowledge ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE learning.objective_mastery ENABLE ROW LEVEL SECURITY",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS learning CASCADE")
