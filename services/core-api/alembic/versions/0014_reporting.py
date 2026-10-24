"""reporting schema: issued report cards (immutable), their refs-only audit, and their outbox

Revision ID: 0014_reporting
Revises: 0013_homework
Create Date: 2026-10-24

REPORT_CARD_CONTRACT.md. Taleem issues a learner's report card for one period (``issued_by =
'system'``; a learner in no class gets one too); a teacher may also issue one for a learner in
their class. Every figure on a card is derived from records that already exist.

- ``reporting.report_card`` — C2 learning records. Pseudonymous ``student_ref`` only. ``body`` is
  the canonical JSON text and ``content_hash`` the SHA-256 (lower-case hex) of exactly that text;
  it is ``text``, not ``jsonb``, so the hashed bytes are stored unchanged. A card is **immutable**:
  a trigger refuses every UPDATE except setting ``acknowledged_at`` / ``acknowledged_by`` once. A
  correction is a new row whose ``supersedes`` names the old card (one successor per card, never
  itself); only one *original* card exists per learner, class and period (partial unique index).
  A system card has no class: ``class_id`` and ``organization_id`` are ``''`` (never NULL, so the
  unique index also allows at most one system card per learner and identical period).
  There is deliberately no foreign key to ``school.classroom``: removing a class must never
  cascade away issued cards. Exported and erased with the learner by the privacy context.
- ``reporting.report_card_audit`` — who issued or acknowledged which card, and when. Refs only:
  the closed action and role lists are CHECKs and there is no free-text column.
- ``reporting.report_card_outbox`` — ``ReportCardIssued`` events (refs only) for the relay.

Reversible, but ``downgrade`` **refuses** while any report card exists: an issued card is a record
a guardian was given, and a schema rollback must never silently destroy it. Export (and, if
appropriate, erase through the privacy flow) first.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0014_reporting"
down_revision: str | None = "0013_homework"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIT_ACTIONS = ("report_card.issued", "report_card.acknowledged")
AUDIT_ROLES = ("system", "teacher", "guardian")
EVENT_TYPES = ("ReportCardIssued",)
CARD_PREFIX = "rpc_"


def _in(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


# Every column but the one-time acknowledgement is fixed once a card is issued.
_FIXED_COLUMNS = (
    "card_id",
    "student_ref",
    "organization_id",
    "class_id",
    "period_start",
    "period_end",
    "body",
    "content_hash",
    "supersedes",
    "issued_by",
    "issued_at",
)
_CHANGED = " OR ".join(f"NEW.{c} IS DISTINCT FROM OLD.{c}" for c in _FIXED_COLUMNS)

UPGRADE_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS reporting",
    f"""
    CREATE TABLE reporting.report_card (
        card_id         varchar(64) PRIMARY KEY,
        student_ref     varchar(64) NOT NULL,
        organization_id varchar(64) NOT NULL,
        class_id        varchar(64) NOT NULL,
        period_start    bigint NOT NULL,
        period_end      bigint NOT NULL,
        body            text NOT NULL,
        content_hash    varchar(64) NOT NULL,
        supersedes      varchar(64) UNIQUE REFERENCES reporting.report_card (card_id),
        issued_by       varchar(64) NOT NULL,
        issued_at       double precision NOT NULL,
        acknowledged_at double precision,
        acknowledged_by varchar(64),
        CONSTRAINT ck_report_card_ref CHECK (left(card_id, 4) = '{CARD_PREFIX}'),
        CONSTRAINT ck_report_card_period CHECK (period_start >= 0 AND period_start < period_end),
        CONSTRAINT ck_report_card_hash CHECK (content_hash ~ '^[0-9a-f]{{64}}$'),
        CONSTRAINT ck_report_card_body CHECK (char_length(body) > 0),
        CONSTRAINT ck_report_card_not_self CHECK (supersedes IS NULL OR supersedes <> card_id),
        CONSTRAINT ck_report_card_ack
            CHECK ((acknowledged_at IS NULL) = (acknowledged_by IS NULL))
    )
    """,
    "CREATE UNIQUE INDEX uq_report_card_original "
    "ON reporting.report_card (student_ref, class_id, period_start, period_end) "
    "WHERE supersedes IS NULL",
    "CREATE INDEX ix_report_card_student ON reporting.report_card (student_ref, issued_at)",
    "CREATE INDEX ix_report_card_class "
    "ON reporting.report_card (organization_id, class_id, period_start, period_end)",
    f"""
    CREATE FUNCTION reporting.report_card_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF {_CHANGED} THEN
            RAISE EXCEPTION 'reporting.report_card is immutable: issue a card that supersedes it';
        END IF;
        IF OLD.acknowledged_at IS NOT NULL AND (
            NEW.acknowledged_at IS DISTINCT FROM OLD.acknowledged_at
            OR NEW.acknowledged_by IS DISTINCT FROM OLD.acknowledged_by
        ) THEN
            RAISE EXCEPTION 'a report card is acknowledged once';
        END IF;
        RETURN NEW;
    END
    $$
    """,
    "CREATE TRIGGER trg_report_card_immutable BEFORE UPDATE ON reporting.report_card "
    "FOR EACH ROW EXECUTE FUNCTION reporting.report_card_immutable()",
    "COMMENT ON TABLE reporting.report_card IS "
    "'Issued report cards (C2 learning records): immutable canonical-JSON body + sha256 hash; "
    "corrections supersede, never edit. Pseudonymous refs only; exported and erased with the "
    "learner.'",
    f"""
    CREATE TABLE reporting.report_card_audit (
        event_id        varchar(64) PRIMARY KEY,
        action          varchar(32) NOT NULL,
        actor_ref       varchar(64) NOT NULL,
        actor_role      varchar(32) NOT NULL,
        subject_ref     varchar(64) NOT NULL,
        organization_id varchar(64) NOT NULL,
        class_id        varchar(64) NOT NULL,
        card_id         varchar(64) NOT NULL,
        at              double precision NOT NULL,
        CONSTRAINT ck_report_card_audit_action CHECK (action IN ({_in(AUDIT_ACTIONS)})),
        CONSTRAINT ck_report_card_audit_role CHECK (actor_role IN ({_in(AUDIT_ROLES)}))
    )
    """,
    "CREATE INDEX ix_report_card_audit_subject ON reporting.report_card_audit (subject_ref, at)",
    "COMMENT ON TABLE reporting.report_card_audit IS "
    "'Who issued or acknowledged which report card, when. Refs only (no free text); erased with "
    "the learner.'",
    f"""
    CREATE TABLE reporting.report_card_outbox (
        id           varchar(64) PRIMARY KEY,
        event_type   varchar(64) NOT NULL,
        aggregate_id varchar(64) NOT NULL,
        student_ref  varchar(64) NOT NULL,
        payload      jsonb NOT NULL,
        occurred_at  double precision NOT NULL,
        published_at double precision,
        CONSTRAINT ck_report_card_outbox_type CHECK (event_type IN ({_in(EVENT_TYPES)}))
    )
    """,
    "CREATE INDEX ix_report_card_outbox_student ON reporting.report_card_outbox (student_ref)",
    "CREATE INDEX ix_report_card_outbox_occurred ON reporting.report_card_outbox (occurred_at)",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Issued report cards are never silently destroyed by a schema rollback.
    cards = op.get_bind().exec_driver_sql("SELECT count(*) FROM reporting.report_card").scalar()
    if cards:
        raise RuntimeError(
            f"refusing to downgrade 0014_reporting: {cards} issued report card(s) exist and would "
            "be destroyed; export them (and erase through the privacy flow if appropriate) first"
        )
    op.execute("DROP TABLE IF EXISTS reporting.report_card_outbox")
    op.execute("DROP TABLE IF EXISTS reporting.report_card_audit")
    op.execute("DROP TABLE IF EXISTS reporting.report_card")
    op.execute("DROP FUNCTION IF EXISTS reporting.report_card_immutable()")
    op.execute("DROP SCHEMA IF EXISTS reporting")
