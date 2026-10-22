"""assessment evidence: admit a learner-erasure DELETE, nothing else

Revision ID: 0009_evidence_erasure
Revises: 0008_school
Create Date: 2026-10-23

Migration 0002 makes ``learning.assessment_evidence`` append-only: the ``trg_evidence_immutable``
trigger calls ``learning.forbid_mutation()``, which refuses every UPDATE and DELETE. That is the
tamper-evidence of the learning record, and it stays. But a guardian's right to have their child's
data erased (docs/03-security-privacy/58-learner-export-and-erasure.md) cannot be met while every
DELETE is refused, so the privacy context's erasure was fail-closed on PostgreSQL (503
``ERASURE_BLOCKED``).

This narrows the exception to exactly one case: a **DELETE** inside a transaction that has set the
transaction-local flag ``taleem.privacy_erasure = 'on'`` (``SET LOCAL``), which only the privacy
context's learning adapter sets, inside its erase transaction. UPDATE remains forbidden in every
case, so evidence can be removed whole but never silently altered. Anyone able to set the flag can
already drop the trigger, so this grants no new capability to a database role; it makes the
erasure path possible without disabling the control for everything else.

Reversible: ``downgrade`` restores the original function body from 0002.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_evidence_erasure"
down_revision: str | None = "0008_school"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ERASURE_AWARE = """
CREATE OR REPLACE FUNCTION learning.forbid_mutation() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('taleem.privacy_erasure', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'append-only table %: % is forbidden', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql
"""

_ORIGINAL = """
CREATE OR REPLACE FUNCTION learning.forbid_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'append-only table %: % is forbidden', TG_TABLE_NAME, TG_OP;
END;
$$ LANGUAGE plpgsql
"""


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_ERASURE_AWARE)


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(_ORIGINAL)
