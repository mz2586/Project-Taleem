"""school.submission: self-paced homework; safeguarding.concern: system-raised concerns

Revision ID: 0017_self_paced_homework
Revises: 0016_account_cohort
Create Date: 2026-10-25

HOMEWORK_AND_MARKING_CONTRACT.md §6 (the AI-led path: no teacher required).

- ``school.submission.source`` — ``varchar(16) NOT NULL DEFAULT 'assignment'``, ``'assignment'``
  or ``'self_paced'``. Every existing row is an assignment answer (nothing is guessed).
- ``school.submission.assignment_id`` / ``class_id`` become nullable. A CHECK ties the shape to
  the source: an assignment answer has both; a self-paced answer has neither and organization
  ``''`` (no school is involved). A partial unique index keeps one self-paced row per
  (objective, item, learner); the existing (assignment, item, learner) constraint still covers
  assignment rows.
- ``safeguarding.concern.raised_by_role`` admits ``'system'`` (the homework disclosure screen).
  A system concern always names its submission, and a partial unique index allows at most one
  system concern per submission (the screen is idempotent).

Child data stays where it was: the privacy export and erasure select submissions and concerns by
the learner's ref, so self-paced rows and system concerns are covered with no new table.

Reversible. ``downgrade`` drops the indexes, CHECKs and the ``source`` column and restores
``NOT NULL``. It **refuses** while any self-paced submission or system-raised concern exists:
the restored schema cannot hold them, and a schema rollback must never delete a child's work or a
safeguarding record.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0017_self_paced_homework"
down_revision: str | None = "0016_account_cohort"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUBMISSION_SOURCES: tuple[str, ...] = ("assignment", "self_paced")
RAISER_ROLES: tuple[str, ...] = ("student", "guardian", "teacher", "system")
PREVIOUS_RAISER_ROLES: tuple[str, ...] = ("student", "guardian", "teacher")


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE school.submission "
    "ADD COLUMN source varchar(16) NOT NULL DEFAULT 'assignment'",
    f"ALTER TABLE school.submission ADD CONSTRAINT ck_submission_source "
    f"CHECK (source IN ({_in(SUBMISSION_SOURCES)}))",
    "ALTER TABLE school.submission ALTER COLUMN assignment_id DROP NOT NULL",
    "ALTER TABLE school.submission ALTER COLUMN class_id DROP NOT NULL",
    "ALTER TABLE school.submission ADD CONSTRAINT ck_submission_source_shape CHECK ("
    "(source = 'assignment' AND assignment_id IS NOT NULL AND class_id IS NOT NULL) OR "
    "(source = 'self_paced' AND assignment_id IS NULL AND class_id IS NULL "
    "AND organization_id = ''))",
    "CREATE UNIQUE INDEX uq_submission_self_paced "
    "ON school.submission (objective_code, item_ref, student_ref) WHERE source = 'self_paced'",
    "ALTER TABLE safeguarding.concern DROP CONSTRAINT ck_concern_raised_by_role",
    f"ALTER TABLE safeguarding.concern ADD CONSTRAINT ck_concern_raised_by_role "
    f"CHECK (raised_by_role IN ({_in(RAISER_ROLES)}))",
    "ALTER TABLE safeguarding.concern ADD CONSTRAINT ck_concern_system_names_submission "
    "CHECK (raised_by_role <> 'system' OR context_submission_id IS NOT NULL)",
    "CREATE UNIQUE INDEX uq_concern_system_submission "
    "ON safeguarding.concern (context_submission_id) WHERE raised_by_role = 'system'",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP INDEX IF EXISTS safeguarding.uq_concern_system_submission",
    "ALTER TABLE safeguarding.concern "
    "DROP CONSTRAINT IF EXISTS ck_concern_system_names_submission",
    "ALTER TABLE safeguarding.concern DROP CONSTRAINT ck_concern_raised_by_role",
    f"ALTER TABLE safeguarding.concern ADD CONSTRAINT ck_concern_raised_by_role "
    f"CHECK (raised_by_role IN ({_in(PREVIOUS_RAISER_ROLES)}))",
    "DROP INDEX IF EXISTS school.uq_submission_self_paced",
    "ALTER TABLE school.submission DROP CONSTRAINT IF EXISTS ck_submission_source_shape",
    "ALTER TABLE school.submission ALTER COLUMN class_id SET NOT NULL",
    "ALTER TABLE school.submission ALTER COLUMN assignment_id SET NOT NULL",
    "ALTER TABLE school.submission DROP CONSTRAINT IF EXISTS ck_submission_source",
    "ALTER TABLE school.submission DROP COLUMN IF EXISTS source",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    self_paced = bind.exec_driver_sql(
        "SELECT count(*) FROM school.submission WHERE source = 'self_paced'"
    ).scalar()
    system = bind.exec_driver_sql(
        "SELECT count(*) FROM safeguarding.concern WHERE raised_by_role = 'system'"
    ).scalar()
    if self_paced or system:
        raise RuntimeError(
            f"refusing to downgrade 0017_self_paced_homework: {self_paced or 0} self-paced "
            f"submission(s) and {system or 0} system-raised safeguarding concern(s) exist and "
            "would have to be deleted; erase or re-home them first"
        )
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
