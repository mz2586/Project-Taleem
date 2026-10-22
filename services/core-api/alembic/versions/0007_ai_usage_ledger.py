"""learning.ai_usage_ledger — durable, shared per-learner AI inference usage

Revision ID: 0007_ai_usage
Revises: 0006_rate_limit
Create Date: 2026-10-22

The AI Teacher's per-learner quota (free-tier sustainability) was enforced against a process-local
ledger, so each serverless instance granted its own budget and usage vanished on restart. This table
moves the ledger into PostgreSQL so every instance reads and appends the same rows.

Shape and data-protection choices:

- One row per gateway call: provider, tier, purpose, token counts, cost in micro-units, and the
  epoch time it was recorded. **No prompt or output text is stored.**
- ``learner_ref`` is the pseudonymous ``student_ref`` only — never a name, family code, or contact
  detail — so the ledger can be joined to nothing identifying without the identity context.
- Indexed by ``(learner_ref, recorded_at)`` for the quota query and by ``recorded_at`` alone for the
  application's ``purge_older_than`` (the hook for the future retention schedule).
- Logged (not UNLOGGED): unlike rate-limit counters, usage is the basis of cost reporting.

Reversible: ``downgrade`` drops the table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0007_ai_usage"
down_revision: str | None = "0006_rate_limit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UPGRADE_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE learning.ai_usage_ledger (
        id                bigserial PRIMARY KEY,
        learner_ref       text NOT NULL,
        provider          varchar(64) NOT NULL,
        tier              varchar(16) NOT NULL,
        purpose           varchar(64) NOT NULL DEFAULT '',
        prompt_tokens     integer NOT NULL DEFAULT 0,
        completion_tokens integer NOT NULL DEFAULT 0,
        cost_micros       bigint NOT NULL DEFAULT 0,
        recorded_at       double precision NOT NULL,
        CONSTRAINT ck_ai_usage_nonnegative CHECK (
            prompt_tokens >= 0 AND completion_tokens >= 0 AND cost_micros >= 0
        )
    )
    """,
    "CREATE INDEX ix_ai_usage_learner_time ON learning.ai_usage_ledger (learner_ref, recorded_at)",
    "CREATE INDEX ix_ai_usage_time ON learning.ai_usage_ledger (recorded_at)",
    "COMMENT ON TABLE learning.ai_usage_ledger IS "
    "'Per-call AI inference usage for per-learner quotas and cost reporting. learner_ref is the "
    "pseudonymous student_ref; no prompt or output text is stored. Purged by recorded_at.'",
)


def upgrade() -> None:
    for statement in UPGRADE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS learning.ai_usage_ledger")
