"""accounts: the cohort a guardian, learner or teacher belongs to ("" real / "demo")

Revision ID: 0016_account_cohort
Revises: 0015_evidence_lesson_version
Create Date: 2026-10-24

DEMO_COHORT_CONTRACT.md §2. The owner explores the real deployment with designated synthetic demo
accounts; their cohort decides which published content they may see, and keeps demo content away
from every real reader.

- ``identity.guardian_account.cohort``, ``identity.learner_account.cohort`` and
  ``school.teacher_account.cohort`` — ``varchar(16) NOT NULL DEFAULT ''``, constrained to
  ``''`` (real) or ``'demo'``. Every existing account becomes ``''`` (real): nothing is guessed.
- The value is set only by the demo seeder (``tools/demo_cohort.py``) through application-service
  methods no HTTP route exposes. A learner's cohort is its guardian's.

Reversible: ``downgrade`` drops the three columns (and their CHECK constraints) again.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016_account_cohort"
down_revision: str | None = "0015_evidence_lesson_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COHORTS: tuple[str, ...] = ("", "demo")
TABLES: tuple[str, ...] = (
    "identity.guardian_account",
    "identity.learner_account",
    "school.teacher_account",
)

_ALLOWED = ", ".join(f"'{c}'" for c in COHORTS)


def _constraint(table: str) -> str:
    return f"ck_{table.split('.', 1)[1]}_cohort"


UPGRADE_STATEMENTS: tuple[str, ...] = tuple(
    statement
    for table in TABLES
    for statement in (
        f"ALTER TABLE {table} ADD COLUMN cohort varchar(16) NOT NULL DEFAULT ''",
        f"ALTER TABLE {table} ADD CONSTRAINT {_constraint(table)} CHECK (cohort IN ({_ALLOWED}))",
    )
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = tuple(
    statement
    for table in reversed(TABLES)
    for statement in (
        f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {_constraint(table)}",
        f"ALTER TABLE {table} DROP COLUMN IF EXISTS cohort",
    )
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
