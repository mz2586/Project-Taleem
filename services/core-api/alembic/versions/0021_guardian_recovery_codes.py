"""identity.guardian_recovery_code: passphrase recovery without email (one-time codes)

Revision ID: 0021_guardian_recovery_codes
Revises: 0020_homework_client_key
Create Date: 2026-10-25

A guardian who forgets their passphrase had no way back to their children's accounts, consent
controls or safeguarding reporting (email delivery is not available). Recovery is a set of eight
one-time codes shown once (identity/domain/recovery.py).

- ``identity.guardian_recovery_code`` — one row per code of the guardian's current set: a PBKDF2
  digest (never the code), when it was made, when it was used. A new set deletes the old rows.
  ``ON DELETE CASCADE`` from ``guardian_account``. Adult credential data, not learner data.
- ``identity.guardian_account.recovery_failed_attempts`` — ``integer NOT NULL DEFAULT 0``: wrong
  recovery attempts, kept apart from ``failed_attempts`` so passphrase guesses cannot use up the
  recovery path.

Reversible. ``downgrade`` drops the table and the column: guardians lose their recovery codes (and
must generate new ones after a re-upgrade); no child data and no passphrase is touched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0021_guardian_recovery_codes"
down_revision: str | None = "0020_homework_client_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE identity.guardian_account "
    "ADD COLUMN recovery_failed_attempts integer NOT NULL DEFAULT 0",
    "CREATE TABLE identity.guardian_recovery_code ("
    " code_id varchar(64) PRIMARY KEY,"
    " guardian_ref varchar(64) NOT NULL"
    "  REFERENCES identity.guardian_account (guardian_ref) ON DELETE CASCADE,"
    " code_hash text NOT NULL,"
    " created_at double precision NOT NULL,"
    " consumed_at double precision NULL"
    ")",
    "CREATE INDEX ix_recovery_code_guardian ON identity.guardian_recovery_code (guardian_ref)",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "DROP TABLE IF EXISTS identity.guardian_recovery_code",
    "ALTER TABLE identity.guardian_account DROP COLUMN IF EXISTS recovery_failed_attempts",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
