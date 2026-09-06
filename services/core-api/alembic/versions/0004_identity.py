"""identity schema (guardian accounts, learner accounts, consent evidence, audit trail)

Revision ID: 0004_identity
Revises: 0003_ops
Create Date: 2026-09-06

Creates the ``identity`` schema, which closes FD-14: production token cryptography already existed,
but there was no way for a real guardian to hold an account, enrol a child, or give the consent that
lets that child sign in.

Four tables, and the DDL carries the child-safety rules rather than leaving them to application
code:

- ``guardian_account`` holds the only adult contact address in the platform, unique so a race
  between two registrations cannot produce two accounts for one email.
- ``learner_account`` holds a child, and deliberately has **no** column for an email address, a
  phone number, a date of birth, or an address. ``(guardian_ref, roster_key)`` is unique because a
  learner's display name is their sign-in handle within their own family.
- ``consent_record`` and ``audit_event`` are **append-only**: no ``updated_at``, no mutable status.
  A withdrawal is a new row, so the history of who agreed to what, under which policy version, is
  reconstructible after the fact.

Reversible: ``downgrade`` drops the schema (CASCADE). The ORM runs the same tables on SQLite in the
suite via ``metadata.create_all``, and the existing schema-parity test asserts the two agree.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_identity"
down_revision: str | None = "0003_ops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS identity",
    """
    CREATE TABLE identity.guardian_account (
        guardian_ref    varchar(64) PRIMARY KEY,
        email           varchar(254) NOT NULL UNIQUE,
        passphrase_hash text NOT NULL,
        display_name    varchar(60) NOT NULL,
        family_code     varchar(16) NOT NULL,
        locale          varchar(8) NOT NULL DEFAULT 'ur',
        status          varchar(16) NOT NULL DEFAULT 'active',
        failed_attempts integer NOT NULL DEFAULT 0,
        created_at      double precision NOT NULL DEFAULT 0,
        version         integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE UNIQUE INDEX ix_guardian_family_code ON identity.guardian_account (family_code)",
    "COMMENT ON TABLE identity.guardian_account IS "
    "'Adult accounts. The only table holding a contact address; a learner never has one.'",
    """
    CREATE TABLE identity.learner_account (
        student_ref     varchar(64) PRIMARY KEY,
        guardian_ref    varchar(64) NOT NULL
                        REFERENCES identity.guardian_account (guardian_ref) ON DELETE CASCADE,
        display_name    varchar(60) NOT NULL,
        roster_key      varchar(60) NOT NULL,
        pin_hash        text NOT NULL,
        grade_band      varchar(16) NOT NULL DEFAULT 'middle',
        grade_level     integer NOT NULL DEFAULT 4,
        locale          varchar(8) NOT NULL DEFAULT 'ur',
        status          varchar(16) NOT NULL DEFAULT 'active',
        failed_attempts integer NOT NULL DEFAULT 0,
        created_at      double precision NOT NULL DEFAULT 0,
        known_devices   jsonb NOT NULL DEFAULT '[]'::jsonb,
        version         integer NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX ix_learner_guardian ON identity.learner_account (guardian_ref)",
    "CREATE UNIQUE INDEX ix_learner_family_roster "
    "ON identity.learner_account (guardian_ref, roster_key)",
    "COMMENT ON TABLE identity.learner_account IS "
    "'Child accounts. No email, phone, date of birth, or address by design — a guardian-chosen "
    "display name, a grade, a locale, and a PIN hash.'",
    """
    CREATE TABLE identity.consent_record (
        consent_id     varchar(64) PRIMARY KEY,
        guardian_ref   varchar(64) NOT NULL,
        student_ref    varchar(64) NOT NULL,
        action         varchar(16) NOT NULL,
        scopes         jsonb NOT NULL DEFAULT '[]'::jsonb,
        policy_version varchar(64) NOT NULL,
        recorded_at    double precision NOT NULL,
        evidence       jsonb NOT NULL DEFAULT '{}'::jsonb
    )
    """,
    "CREATE INDEX ix_consent_student_time "
    "ON identity.consent_record (student_ref, recorded_at)",
    "CREATE INDEX ix_consent_guardian ON identity.consent_record (guardian_ref)",
    "COMMENT ON TABLE identity.consent_record IS "
    "'Append-only consent evidence. A withdrawal is a new row; current state is derived by "
    "folding the history, so what was agreed and when stays reconstructible.'",
    """
    CREATE TABLE identity.audit_event (
        event_id       varchar(64) PRIMARY KEY,
        at             double precision NOT NULL,
        action         varchar(64) NOT NULL,
        actor_ref      varchar(64) NOT NULL,
        actor_role     varchar(32) NOT NULL,
        subject_ref    varchar(64) NOT NULL,
        correlation_id varchar(64) NOT NULL DEFAULT '',
        detail         jsonb NOT NULL DEFAULT '{}'::jsonb
    )
    """,
    "CREATE INDEX ix_audit_subject_time ON identity.audit_event (subject_ref, at)",
    "CREATE INDEX ix_audit_actor_time ON identity.audit_event (actor_ref, at)",
    "COMMENT ON TABLE identity.audit_event IS "
    "'Append-only identity audit trail. Refs and hashes only — an audit log that accumulates "
    "child PII becomes its own privacy risk.'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS identity CASCADE")
