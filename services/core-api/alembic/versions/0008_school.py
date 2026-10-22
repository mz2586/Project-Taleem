"""school schema (organizations, teacher accounts, classes, enrolments, assignments)

Revision ID: 0008_school
Revises: 0007_ai_usage
Create Date: 2026-10-22

The pilot-minimum teacher/organization backend (GLOBAL_PRODUCT_SCOPE §F/§G). The DDL carries the
tenancy rule rather than leaving it to application code alone: every child table repeats
``organization_id`` so each tenant-scoped query filters on a column of its own table, and the
indexes lead with it.

- ``organization``: the tenant (name, ISO country, curriculum pack id, default locale).
- ``teacher_account``: an adult account inside one organization; email unique platform-wide.
- ``classroom``: owned by one teacher; ``join_code`` is unique so a guardian's code names exactly
  one class.
- ``enrolment``: a learner in a class, approved by their guardian. Only the pseudonymous
  ``student_ref`` is stored — a child's name stays in identity. Visibility to the teacher is decided
  per request from live consent (``progress_sharing``), not stored here.
- ``assignment``: a published objective with a due date.

Follows 0007_ai_usage. Reversible: ``downgrade`` drops the schema (CASCADE).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008_school"
down_revision: str | None = "0007_ai_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS school",
    """
    CREATE TABLE school.organization (
        organization_id    varchar(64) PRIMARY KEY,
        name               varchar(120) NOT NULL,
        country            varchar(2) NOT NULL,
        curriculum_pack_id varchar(64) NOT NULL,
        default_locale     varchar(8) NOT NULL,
        created_at         double precision NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE school.teacher_account (
        teacher_ref     varchar(64) PRIMARY KEY,
        organization_id varchar(64) NOT NULL
            REFERENCES school.organization (organization_id) ON DELETE CASCADE,
        email           varchar(254) NOT NULL UNIQUE,
        display_name    varchar(60) NOT NULL,
        passphrase_hash varchar(512) NOT NULL,
        status          varchar(16) NOT NULL DEFAULT 'active',
        failed_attempts integer NOT NULL DEFAULT 0,
        created_at      double precision NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX ix_teacher_org ON school.teacher_account (organization_id)",
    """
    CREATE TABLE school.classroom (
        class_id        varchar(64) PRIMARY KEY,
        organization_id varchar(64) NOT NULL
            REFERENCES school.organization (organization_id) ON DELETE CASCADE,
        teacher_ref     varchar(64) NOT NULL
            REFERENCES school.teacher_account (teacher_ref) ON DELETE CASCADE,
        name            varchar(80) NOT NULL,
        join_code       varchar(16) NOT NULL UNIQUE,
        created_at      double precision NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX ix_classroom_org_teacher ON school.classroom (organization_id, teacher_ref)",
    """
    CREATE TABLE school.enrolment (
        class_id        varchar(64) NOT NULL
            REFERENCES school.classroom (class_id) ON DELETE CASCADE,
        student_ref     varchar(64) NOT NULL,
        organization_id varchar(64) NOT NULL,
        approved_by     varchar(64) NOT NULL,
        joined_at       double precision NOT NULL DEFAULT 0,
        CONSTRAINT pk_enrolment PRIMARY KEY (class_id, student_ref)
    )
    """,
    "CREATE INDEX ix_enrolment_org_class ON school.enrolment (organization_id, class_id)",
    """
    CREATE TABLE school.assignment (
        assignment_id   varchar(64) PRIMARY KEY,
        class_id        varchar(64) NOT NULL
            REFERENCES school.classroom (class_id) ON DELETE CASCADE,
        organization_id varchar(64) NOT NULL,
        objective_code  varchar(64) NOT NULL,
        due_at          double precision NOT NULL,
        assigned_by     varchar(64) NOT NULL,
        created_at      double precision NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX ix_assignment_org_class ON school.assignment (organization_id, class_id)",
    "COMMENT ON TABLE school.enrolment IS "
    "'Guardian-approved class membership. student_ref only (no child PII); teacher visibility is "
    "decided per request from live progress_sharing consent.'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS school CASCADE")
