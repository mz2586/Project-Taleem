"""safeguarding.concern: one OPEN disclosure-screen concern per submission (was: one ever)

Revision ID: 0022_concern_open_per_submission
Revises: 0021_guardian_recovery_codes
Create Date: 2026-11-17

0017 allowed a single system concern per homework submission, ever. Once a safeguarding lead
resolved it (for example as a false alarm), a later attempt on the same submission with a new,
different disclosure was never screened into a concern. The unique index now covers only concerns
that are not ``resolved``: at most one open system concern per submission, and a new one may be
raised after the earlier one is closed.

Reversible. ``downgrade`` restores the 0017 index; it fails if a submission already has more than
one system concern (that data must be reviewed by a person, not dropped by a migration).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022_concern_open_per_submission"
down_revision: str | None = "0021_guardian_recovery_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP INDEX IF EXISTS safeguarding.uq_concern_system_submission",
    "CREATE UNIQUE INDEX uq_concern_system_submission_open "
    "ON safeguarding.concern (context_submission_id) "
    "WHERE raised_by_role = 'system' AND status <> 'resolved'",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP INDEX IF EXISTS safeguarding.uq_concern_system_submission_open",
    "CREATE UNIQUE INDEX uq_concern_system_submission "
    "ON safeguarding.concern (context_submission_id) WHERE raised_by_role = 'system'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
