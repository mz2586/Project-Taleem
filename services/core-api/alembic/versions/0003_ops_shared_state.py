"""ops schema (shared operator kill switch)

Revision ID: 0003_ops
Revises: 0002_learning
Create Date: 2026-09-06

Creates the ``ops`` schema holding the operator halt flag.

The flag was process-local, which made a child-safety control fail *open* on any deployment that
runs more than one instance (a second replica, or a fresh serverless invocation): engaging it on one
instance left every other instance serving child-facing traffic while ``/v1/ops/kill-switch``
truthfully reported "engaged". Sharing the flag in the database makes an operator's decision take
effect everywhere.

Single row (``id = 1``), enforced by a CHECK constraint and seeded disengaged.

Reversible: ``downgrade`` drops the schema (CASCADE). The ORM runs on SQLite in tests via
``metadata.create_all`` and column parity is asserted by a dedicated CI test.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_ops"
down_revision: str | None = "0002_learning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    "CREATE SCHEMA IF NOT EXISTS ops",
    """
    CREATE TABLE ops.kill_switch (
        id         int PRIMARY KEY,
        engaged    boolean NOT NULL DEFAULT false,
        reason     text    NOT NULL DEFAULT '',
        changed_at double precision NOT NULL DEFAULT 0,
        CONSTRAINT ck_kill_switch_singleton CHECK (id = 1)
    )
    """,
    "COMMENT ON TABLE ops.kill_switch IS "
    "'Operator halt flag, single row (id=1). Shared so the control cannot fail open "
    "when more than one instance serves traffic.'",
    "INSERT INTO ops.kill_switch (id, engaged, reason, changed_at) VALUES (1, false, '', 0)",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS ops CASCADE")
