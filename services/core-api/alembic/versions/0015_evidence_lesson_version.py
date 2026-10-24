"""assessment evidence: the lesson id and published version each attempt was answered against

Revision ID: 0015_evidence_lesson_version
Revises: 0014_reporting
Create Date: 2026-10-24

REPORT_CARD_CONTRACT.md §1 (doc 29 §1 principle 3: a report card cites the exact curriculum
version). Until now an evidence row named only the objective, so a report card had to pin each
objective to whatever lesson version was published when the card was issued; a republish or a
rollback between the learning and the issue misattributed the work.

- ``learning.assessment_evidence.lesson_id`` (``text``) and ``lesson_version`` (``integer``) —
  the published lesson the attempt was answered against, recorded by every evidence path from now
  on. Both are **nullable** and NULL means "not recorded": rows written before this migration stay
  NULL (nothing is backfilled or guessed), and an offline attempt whose package did not say which
  version it was built from records a NULL version.

Adding a column does not fire the row-level append-only trigger (``trg_evidence_immutable``), and
the rows stay immutable afterwards.

Reversible: ``downgrade`` drops both columns (the recorded pins are lost with them).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_evidence_lesson_version"
down_revision: str | None = "0014_reporting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS: tuple[str, ...] = ("lesson_id", "lesson_version")

UPGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE learning.assessment_evidence ADD COLUMN lesson_id text",
    "ALTER TABLE learning.assessment_evidence ADD COLUMN lesson_version integer",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE learning.assessment_evidence DROP COLUMN IF EXISTS lesson_version",
    "ALTER TABLE learning.assessment_evidence DROP COLUMN IF EXISTS lesson_id",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
