"""safeguarding.concern_evidence: the immutable snapshot of the homework text behind a concern

Revision ID: 0018_concern_evidence
Revises: 0017_self_paced_homework
Create Date: 2026-10-25

A disclosure-screen concern (and a teacher's concern raised from a marking row) names a homework
submission. Until now the lead's ``GET /v1/safeguarding/concerns/{id}/context`` read the
submission's *current* text, and a resubmission overwrites it — so the words that triggered the
concern could be silently lost. This table keeps them.

- ``safeguarding.concern_evidence`` — one row per concern (the primary key **is** the concern, a
  foreign key with no cascade): the flagged ``text``, its ``attempt``, ``submitted_at``,
  ``item_ref``, ``objective_code``, the hex SHA-256 of the UTF-8 text (``text_sha256``, CHECKed to
  be 64 lowercase hex characters) and ``created_at``. Written in the same transaction as the
  concern. It carries no learner ref: it is reached only through its concern.
- ``trg_concern_evidence_immutable`` (``safeguarding.concern_evidence_immutable()``) refuses every
  UPDATE and DELETE, except inside a transaction that has set ``taleem.privacy_erasure = 'on'``
  (``SET LOCAL``) — the flag only the privacy context's erasure sets (same convention as 0009).
  TRUNCATE is refused too. Anyone able to set the flag could already drop the trigger, so this
  grants no capability; it keeps the only legitimate path (a guardian's erasure, per the retained
  set) possible.

No backfill: a concern raised before this revision has no snapshot, and the API says so instead of
presenting the current text as the flagged one.

Reversible. ``downgrade`` drops the trigger, its function and the table. It **refuses** while any
evidence row exists: a schema rollback must never destroy safeguarding evidence.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0018_concern_evidence"
down_revision: str | None = "0017_self_paced_homework"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ERASURE_GUC = "taleem.privacy_erasure"

UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE safeguarding.concern_evidence (
        concern_id     varchar(64) PRIMARY KEY
            REFERENCES safeguarding.concern (concern_id),
        submission_id  varchar(64) NOT NULL,
        text           text NOT NULL,
        attempt        integer NOT NULL,
        submitted_at   double precision NOT NULL,
        item_ref       varchar(128) NOT NULL,
        objective_code varchar(128) NOT NULL,
        text_sha256    varchar(64) NOT NULL,
        created_at     double precision NOT NULL,
        CONSTRAINT ck_concern_evidence_text CHECK (char_length(text) >= 1),
        CONSTRAINT ck_concern_evidence_attempt CHECK (attempt >= 1),
        CONSTRAINT ck_concern_evidence_sha256 CHECK (text_sha256 ~ '^[0-9a-f]{64}$')
    )
    """,
    "CREATE INDEX ix_concern_evidence_submission "
    "ON safeguarding.concern_evidence (submission_id)",
    f"""
    CREATE FUNCTION safeguarding.concern_evidence_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$
    BEGIN
        IF current_setting('{ERASURE_GUC}', true) = 'on' AND TG_OP IN ('UPDATE', 'DELETE') THEN
            IF TG_OP = 'DELETE' THEN
                RETURN OLD;
            END IF;
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'append-only table %: % is forbidden', TG_TABLE_NAME, TG_OP;
    END;
    $$
    """,
    "CREATE TRIGGER trg_concern_evidence_immutable "
    "BEFORE UPDATE OR DELETE ON safeguarding.concern_evidence "
    "FOR EACH ROW EXECUTE FUNCTION safeguarding.concern_evidence_immutable()",
    "CREATE TRIGGER trg_concern_evidence_no_truncate "
    "BEFORE TRUNCATE ON safeguarding.concern_evidence "
    "FOR EACH STATEMENT EXECUTE FUNCTION safeguarding.concern_evidence_immutable()",
    "COMMENT ON TABLE safeguarding.concern_evidence IS "
    "'Immutable snapshot of the homework text a safeguarding concern was raised from (C4). "
    "safeguarding_lead only; never exported to a guardian; no text in logs or audit. "
    "UPDATE/DELETE only inside a privacy erasure (taleem.privacy_erasure).'",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP TRIGGER IF EXISTS trg_concern_evidence_no_truncate ON safeguarding.concern_evidence",
    "DROP TRIGGER IF EXISTS trg_concern_evidence_immutable ON safeguarding.concern_evidence",
    "DROP TABLE IF EXISTS safeguarding.concern_evidence",
    "DROP FUNCTION IF EXISTS safeguarding.concern_evidence_immutable()",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    kept = (
        op.get_bind().exec_driver_sql("SELECT count(*) FROM safeguarding.concern_evidence").scalar()
    )
    if kept:
        raise RuntimeError(
            f"refusing to downgrade 0018_concern_evidence: {kept} safeguarding evidence "
            "snapshot(s) exist and would be destroyed; they are retained records"
        )
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
