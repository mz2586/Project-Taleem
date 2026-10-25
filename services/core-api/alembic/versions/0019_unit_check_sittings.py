"""learning.unit_check_sitting: end-of-unit examination sittings

Revision ID: 0019_unit_check_sittings
Revises: 0018_concern_evidence
Create Date: 2026-10-25

PROGRESSION_AND_EXAMINATION_CONTRACT.md §2 and §4. A unit check is a fixed-length, auto-scored
test assembled from a unit's published lessons; a **sitting** is one attempt at it.

- ``learning.unit_check_sitting`` — C2 learning records keyed by the pseudonymous
  ``student_ref``. ``items`` is the paper (item and lesson references only — never an answer
  key); ``answers`` maps each item ref to the learner's answer and its server-side outcome;
  ``result`` is the score with the per-objective breakdown once finished. ``status`` is one of
  ``in_progress`` / ``passed`` / ``failed`` / ``incomplete`` (an unfinished sitting expires as
  ``incomplete``, never ``failed``). A partial unique index allows at most one ``in_progress``
  sitting per learner and unit; ``lock_version`` is the optimistic lock that makes answering an
  item once per sitting idempotent under concurrency. Exported and erased with the learner by
  the privacy context, and covered by its completeness gate.

Reversible, but ``downgrade`` **refuses** while any sitting exists: every sitting is part of a
learner's academic record, and a schema rollback must never silently destroy one. Export (and,
if appropriate, erase through the privacy flow) first.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0019_unit_check_sittings"
down_revision: str | None = "0018_concern_evidence"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SITTING_STATUSES: tuple[str, ...] = ("in_progress", "passed", "failed", "incomplete")
SITTING_PREFIX = "ucs_"
INDEXES: tuple[str, ...] = ("ix_sitting_student", "ix_sitting_unit", "uq_sitting_in_progress")


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


UPGRADE_STATEMENTS: tuple[str, ...] = (
    f"""
    CREATE TABLE learning.unit_check_sitting (
        sitting_id   varchar(64) PRIMARY KEY,
        student_ref  varchar(64) NOT NULL,
        pack_id      varchar(32) NOT NULL,
        grade_key    varchar(16) NOT NULL,
        subject_key  varchar(64) NOT NULL,
        unit_id      varchar(255) NOT NULL,
        unit_title   jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        status       varchar(16) NOT NULL,
        items        jsonb NOT NULL DEFAULT '[]'::jsonb,
        answers      jsonb NOT NULL DEFAULT '{{}}'::jsonb,
        pass_percent integer NOT NULL,
        started_at   double precision NOT NULL,
        expires_at   double precision NOT NULL,
        finished_at  double precision,
        result       jsonb,
        lock_version integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_sitting_status CHECK (status IN ({_in(SITTING_STATUSES)})),
        CONSTRAINT ck_sitting_pass_percent CHECK (pass_percent BETWEEN 1 AND 100),
        CONSTRAINT ck_sitting_window CHECK (expires_at > started_at),
        CONSTRAINT ck_sitting_ref CHECK (substr(sitting_id, 1, 4) = '{SITTING_PREFIX}')
    )
    """,
    "CREATE INDEX ix_sitting_student ON learning.unit_check_sitting (student_ref, started_at)",
    "CREATE INDEX ix_sitting_unit ON learning.unit_check_sitting (student_ref, unit_id)",
    "CREATE UNIQUE INDEX uq_sitting_in_progress "
    "ON learning.unit_check_sitting (student_ref, unit_id) WHERE status = 'in_progress'",
    "COMMENT ON TABLE learning.unit_check_sitting IS "
    "'Unit-check sittings (C2 learning records): the paper as references only (never an answer "
    "key), the learner''s answers and the server-side score. Pseudonymous refs only; exported "
    "and erased with the learner.'",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP INDEX IF EXISTS learning.uq_sitting_in_progress",
    "DROP INDEX IF EXISTS learning.ix_sitting_unit",
    "DROP INDEX IF EXISTS learning.ix_sitting_student",
    "DROP TABLE IF EXISTS learning.unit_check_sitting",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    exists = bind.exec_driver_sql(
        "SELECT to_regclass('learning.unit_check_sitting') IS NOT NULL"
    ).scalar()
    count = (
        bind.exec_driver_sql("SELECT count(*) FROM learning.unit_check_sitting").scalar()
        if exists
        else 0
    )
    if count:
        raise RuntimeError(
            f"refusing to downgrade 0019_unit_check_sittings: {count} unit-check sitting(s) "
            "exist and would be deleted; export (and, if appropriate, erase through the privacy "
            "flow) first"
        )
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
