"""safeguarding schema (concerns, triage notes, audit) + the safeguarding_lead staff role

Revision ID: 0012_safeguarding
Revises: 0011_school_audit
Create Date: 2026-10-23

A child or a guardian raises a safeguarding concern; a safeguarding lead triages it. The schema is
separate from learning and identity because these rows are the most sensitive data class (C4).

- ``safeguarding.concern`` — pseudonymous refs only (``subject_ref`` = the learner's
  ``student_ref``; ``raised_by_ref`` = that learner or their guardian). ``free_text`` is the
  raiser's own short words, bounded by a CHECK. Category, priority, status, raiser role and outcome
  are closed lists enforced by CHECKs, so even a direct write cannot invent a state. ``version`` is
  the optimistic-lock column (two leads acting at once: one gets a 409).
- ``safeguarding.concern_note`` — a lead's triage notes (cascade with the concern).
- ``safeguarding.concern_audit`` — append-only by convention; every action with its actor subject.
  No foreign key, so no cascade can remove audit rows; only the privacy erasure touches them.
- ``identity.staff_account`` role CHECK gains ``safeguarding_lead`` (operator-provisioned exactly
  like the Studio roles, 0010).

Reversible. ``downgrade`` drops the schema and restores the seven-role CHECK; any
``safeguarding_lead`` staff accounts are deleted first, because the restored CHECK cannot hold them
and the console they sign in to no longer exists.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0012_safeguarding"
down_revision: str | None = "0011_school_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STUDIO_ROLES = (
    "subject_author",
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
    "curriculum_architect",
)
STAFF_ROLES = (*STUDIO_ROLES, "safeguarding_lead")
CATEGORIES = ("felt_unsafe", "very_sad", "bullying", "upsetting_lesson", "other")
PRIORITIES = ("T1", "T2", "T3")
STATUSES = ("open", "acknowledged", "escalated", "resolved")
OUTCOMES = ("no_further_action", "support_given", "referred_externally", "duplicate")


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS safeguarding",
    f"""
    CREATE TABLE safeguarding.concern (
        concern_id        varchar(64) PRIMARY KEY,
        subject_ref       varchar(64) NOT NULL,
        raised_by_ref     varchar(64) NOT NULL,
        raised_by_role    varchar(16) NOT NULL,
        category          varchar(32) NOT NULL,
        priority          varchar(4) NOT NULL,
        free_text         text,
        context_screen    varchar(64) NOT NULL DEFAULT '',
        context_lesson_id varchar(128),
        status            varchar(16) NOT NULL,
        outcome           varchar(32),
        created_at        double precision NOT NULL,
        acknowledged_at   double precision,
        acknowledged_by   varchar(64),
        escalated_at      double precision,
        escalated_by      varchar(64),
        resolved_at       double precision,
        resolved_by       varchar(64),
        version           integer NOT NULL DEFAULT 1,
        CONSTRAINT ck_concern_ref CHECK (left(concern_id, 4) = 'sgc_'),
        CONSTRAINT ck_concern_raised_by_role CHECK (raised_by_role IN ('student', 'guardian')),
        CONSTRAINT ck_concern_category CHECK (category IN ({_in(CATEGORIES)})),
        CONSTRAINT ck_concern_priority CHECK (priority IN ({_in(PRIORITIES)})),
        CONSTRAINT ck_concern_status CHECK (status IN ({_in(STATUSES)})),
        CONSTRAINT ck_concern_outcome CHECK (outcome IS NULL OR outcome IN ({_in(OUTCOMES)})),
        CONSTRAINT ck_concern_resolved_has_outcome
            CHECK ((status = 'resolved') = (outcome IS NOT NULL)),
        CONSTRAINT ck_concern_text_bounded
            CHECK (free_text IS NULL OR char_length(free_text) <= 500)
    )
    """,
    "CREATE INDEX ix_concern_status_priority ON safeguarding.concern (status, priority, created_at)",
    "CREATE INDEX ix_concern_subject ON safeguarding.concern (subject_ref)",
    "CREATE INDEX ix_concern_raised_by ON safeguarding.concern (raised_by_ref)",
    """
    CREATE TABLE safeguarding.concern_note (
        note_id    varchar(64) PRIMARY KEY,
        concern_id varchar(64) NOT NULL
            REFERENCES safeguarding.concern (concern_id) ON DELETE CASCADE,
        author_ref varchar(64) NOT NULL,
        body       text NOT NULL,
        created_at double precision NOT NULL,
        CONSTRAINT ck_concern_note_bounded CHECK (char_length(body) BETWEEN 1 AND 2000)
    )
    """,
    "CREATE INDEX ix_concern_note_concern ON safeguarding.concern_note (concern_id, created_at)",
    """
    CREATE TABLE safeguarding.concern_audit (
        event_id   varchar(64) PRIMARY KEY,
        concern_id varchar(64) NOT NULL,
        action     varchar(32) NOT NULL,
        actor_ref  varchar(64) NOT NULL,
        actor_role varchar(32) NOT NULL,
        at         double precision NOT NULL,
        detail     jsonb NOT NULL DEFAULT '{}'::jsonb
    )
    """,
    "CREATE INDEX ix_concern_audit_concern ON safeguarding.concern_audit (concern_id, at)",
    "CREATE INDEX ix_concern_audit_actor ON safeguarding.concern_audit (actor_ref)",
    "COMMENT ON TABLE safeguarding.concern IS "
    "'Safeguarding concerns (C4). Pseudonymous refs only; free text visible to safeguarding_lead "
    "only. Covered by privacy export/erasure (retained set: PENDING M-Gov).'",
    "COMMENT ON TABLE safeguarding.concern_audit IS "
    "'Every safeguarding action by actor subject. No free text. Append-only by convention.'",
    "ALTER TABLE identity.staff_account DROP CONSTRAINT ck_staff_role",
    f"ALTER TABLE identity.staff_account ADD CONSTRAINT ck_staff_role "
    f"CHECK (role IN ({_in(STAFF_ROLES)}))",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS safeguarding CASCADE")
    op.execute("DELETE FROM identity.staff_account WHERE role = 'safeguarding_lead'")
    op.execute("ALTER TABLE identity.staff_account DROP CONSTRAINT ck_staff_role")
    op.execute(
        f"ALTER TABLE identity.staff_account ADD CONSTRAINT ck_staff_role "
        f"CHECK (role IN ({_in(STUDIO_ROLES)}))"
    )
