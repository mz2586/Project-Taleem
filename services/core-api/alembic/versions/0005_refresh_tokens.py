"""identity.refresh_token — rotating, device-bound session continuity

Revision ID: 0005_refresh
Revises: 0004_identity
Create Date: 2026-09-06

A learner access token lives ten minutes because that window is the blast radius of a consent
withdrawal. Ten minutes is shorter than a lesson, so without a refresh path a child is ejected
mid-question — and the obvious shortcut, keeping the PIN on the device to resubmit silently, would
turn a four-digit secret into a permanently stored credential.

This table holds the alternative: opaque, high-entropy, single-use refresh tokens. Refreshing re-runs
the account and consent gates, so continuity never outlives permission.

Two design points visible in the DDL:

- Rows are **retained after use** (``consumed_at`` rather than a delete), because presenting a
  consumed token has to be *detectable*. Deleting used rows would make a stolen token look like an
  unknown one, and theft would fail silently instead of revoking the chain.
- ``family_id`` groups every token descended from one sign-in. Reuse revokes the family, not just
  the token, because the legitimate holder and a thief hold members of the same chain and cannot be
  told apart (OAuth 2.0 Security BCP §4.14.2).

Only the SHA-256 digest of the secret is stored. The secret carries 256 bits of entropy, so no slow
KDF is warranted; the digest exists so a database read does not yield usable tokens.

Reversible: ``downgrade`` drops the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_refresh"
down_revision: str | None = "0004_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE identity.refresh_token (
        token_id    varchar(64) PRIMARY KEY,
        token_hash  varchar(64) NOT NULL,
        subject_ref varchar(64) NOT NULL,
        role        varchar(32) NOT NULL,
        device_id   varchar(64) NOT NULL DEFAULT '',
        family_id   varchar(64) NOT NULL,
        issued_at   double precision NOT NULL,
        expires_at  double precision NOT NULL,
        consumed_at double precision,
        revoked_at  double precision
    )
    """,
    "CREATE INDEX ix_refresh_family ON identity.refresh_token (family_id)",
    "CREATE INDEX ix_refresh_subject ON identity.refresh_token (subject_ref)",
    "COMMENT ON TABLE identity.refresh_token IS "
    "'Rotating, device-bound refresh tokens. Single use; consumed rows are retained so that reuse "
    "is detectable and revokes the whole family. Only the SHA-256 digest of the secret is stored.'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity.refresh_token")
