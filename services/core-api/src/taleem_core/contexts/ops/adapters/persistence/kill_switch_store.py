"""SQL-backed kill-switch state — the shared-instance implementation of `KillSwitchState`.

Reads the single `ops.kill_switch` row on every check so any instance sees an operator's decision
immediately, and writes it on engage/disengage. Read failures fail **closed** (report engaged): if
the database is unreachable we cannot prove the platform was not halted, and for a child-safety
control the safe default is to stop serving children rather than to keep going.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

from .....platform.kill_switch import KillSwitchStatus
from .models import KILL_SWITCH_ROW_ID, KillSwitchRow

logger = logging.getLogger("taleem.ops")


class SqlKillSwitchState:
    """Shared halt flag persisted in `ops.kill_switch` (single row)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def read(self) -> KillSwitchStatus:
        try:
            with self._sf() as session:
                row = session.get(KillSwitchRow, KILL_SWITCH_ROW_ID)
                if row is None:
                    # No row yet (fresh database, migration not applied): nothing has engaged it.
                    return KillSwitchStatus(False, "", 0.0)
                return KillSwitchStatus(row.engaged, row.reason, row.changed_at)
        except Exception:  # noqa: BLE001 — any failure to read must fail closed
            logger.exception("kill_switch_read_failed")
            return KillSwitchStatus(True, "kill-switch state unreadable (failing closed)", 0.0)

    def write(self, status: KillSwitchStatus) -> None:
        with self._sf() as session:
            row = session.get(KillSwitchRow, KILL_SWITCH_ROW_ID)
            if row is None:
                row = KillSwitchRow(id=KILL_SWITCH_ROW_ID)
                session.add(row)
            row.engaged = status.engaged
            row.reason = status.reason
            row.changed_at = status.changed_at
            session.commit()
