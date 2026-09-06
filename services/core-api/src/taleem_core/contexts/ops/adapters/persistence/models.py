"""ORM model for ops-context shared state (see alembic 0003_ops).

One table, deliberately tiny and cheap to read on every request: ``kill_switch`` holds the operator
halt flag in a single row so the control is shared by every instance.
"""

from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, Float, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import OPS_SCHEMA, OpsBase

KILL_SWITCH_ROW_ID = 1


class KillSwitchRow(OpsBase):
    """The operator halt flag. Exactly one row, enforced by a CHECK constraint."""

    __tablename__ = "kill_switch"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_kill_switch_singleton"),
        {"schema": OPS_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engaged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    changed_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
