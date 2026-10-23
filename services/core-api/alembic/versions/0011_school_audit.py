"""school.enrolment_audit — durable record of class-membership changes

Revision ID: 0011_school_audit
Revises: 0010_staff_accounts
Create Date: 2026-10-23

Every guardian join and leave of a class is recorded here: who acted (the guardian's ref and role),
for which learner (``subject_ref`` = the pseudonymous ``student_ref``), in which organization and
class, and when. No names, no codes, no free text — refs only.

Append-only by convention (the application never updates a row). The privacy context erases a
learner's rows with the learner (``contexts/privacy/adapters/school_data.py``).

Reversible: ``downgrade`` drops the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0011_school_audit"
down_revision: str | None = "0010_staff_accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE school.enrolment_audit (
        event_id        varchar(64) PRIMARY KEY,
        action          varchar(32) NOT NULL,
        actor_ref       varchar(64) NOT NULL,
        actor_role      varchar(32) NOT NULL,
        subject_ref     varchar(64) NOT NULL,
        organization_id varchar(64) NOT NULL,
        class_id        varchar(64) NOT NULL,
        at              double precision NOT NULL
    )
    """,
    "CREATE INDEX ix_school_audit_subject ON school.enrolment_audit (subject_ref)",
    "CREATE INDEX ix_school_audit_org_at ON school.enrolment_audit (organization_id, at)",
    "COMMENT ON TABLE school.enrolment_audit IS "
    "'Class-membership changes (join/leave). Pseudonymous refs only; erased with the learner.'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS school.enrolment_audit")
