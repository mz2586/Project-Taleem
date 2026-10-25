"""school.submission.client_key: offline homework sync is idempotent by the device's key

Revision ID: 0020_homework_client_key
Revises: 0019_unit_check_sittings
Create Date: 2026-10-25

HOMEWORK_AND_MARKING_CONTRACT.md §2 and OFFLINE_SYNC_SPEC.md (``homework.submitted``). A written
answer the child sent while offline reaches the server through ``POST /v1/sync/batch``. The row
remembers the device's submission key of the answer it now holds, so a replay of that delta —
even after a server restart — is a duplicate, never a second attempt, a second disclosure screen,
or a second evidence row.

- ``school.submission.client_key`` — ``varchar(64) NULL``. NULL for every existing row and for
  every online submit. Not child data (a random device-generated id); it is erased with the row.

Reversible. ``downgrade`` drops the column; no child work is lost (the answer, its attempt and its
mark stay on the row). A replay of an already-applied offline answer after a downgrade is still
refused as superseded by the attempt check, never stored twice.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_homework_client_key"
down_revision: str | None = "0019_unit_check_sittings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE school.submission ADD COLUMN client_key varchar(64)",
)

DOWNGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE school.submission DROP COLUMN IF EXISTS client_key",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_STATEMENTS:
        op.execute(statement)
