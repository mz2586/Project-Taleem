"""identity.rate_limit_bucket — shared, cross-instance rate limiting

Revision ID: 0006_rate_limit
Revises: 0005_refresh
Create Date: 2026-10-22

The per-client limiter on the public identity routes was process-local. Production runs as many
serverless instances, so each instance granted its own budget and the limit did not hold. This table
moves the counter into PostgreSQL (there is deliberately no Redis in the deployment), where every
instance increments the same row with one atomic ``INSERT ... ON CONFLICT ... DO UPDATE ...
RETURNING``.

Shape:

- One row per (scope, client digest, fixed window). The limiter combines the current and previous
  windows into a sliding estimate, so a row matters for two windows and ``expires_at`` is set two
  windows after it opened; expired rows are purged by the application.
- ``key_hash`` is a SHA-256 digest of the client identifier. No raw IP address or other identifier
  is stored.
- ``UNLOGGED``: the counters are disposable (losing them on a crash resets a one-minute budget),
  and skipping the WAL keeps a hot, write-per-request table off the replication path.

Reversible: ``downgrade`` drops the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006_rate_limit"
down_revision: str | None = "0005_refresh"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE UNLOGGED TABLE identity.rate_limit_bucket (
        scope        varchar(32) NOT NULL,
        key_hash     varchar(64) NOT NULL,
        window_start bigint NOT NULL,
        hits         integer NOT NULL DEFAULT 0,
        expires_at   double precision NOT NULL,
        CONSTRAINT pk_rate_limit_bucket PRIMARY KEY (scope, key_hash, window_start)
    )
    """,
    "CREATE INDEX ix_rate_limit_expires ON identity.rate_limit_bucket (expires_at)",
    "COMMENT ON TABLE identity.rate_limit_bucket IS "
    "'Shared sliding-window rate-limit counters for the public identity routes. key_hash is a "
    "SHA-256 digest of the client identifier; rows expire two windows after they open.'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity.rate_limit_bucket")
