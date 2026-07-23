"""Kill switch — operational halt of child-facing traffic (pure-stdlib).

A process-local, deny-when-engaged control an operator flips to immediately stop child-facing use
during an incident ([INCIDENT_RESPONSE.md], [PILOT0_OPERATIONS.md]). When engaged, child-facing
routes return 503; health, metrics, and the ops control routes stay up so the operator can observe +
disengage. This is an ops safety control, not a product feature.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class KillSwitchStatus:
    engaged: bool
    reason: str
    changed_at: float

    def to_dict(self) -> dict[str, object]:
        return {"engaged": self.engaged, "reason": self.reason, "changed_at": self.changed_at}


class KillSwitch:
    """Process-local halt flag. Engaging it makes child-facing routes fail closed (503)."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._now = clock
        self._engaged = False
        self._reason = ""
        self._changed_at = 0.0

    @property
    def engaged(self) -> bool:
        return self._engaged

    def engage(self, reason: str) -> KillSwitchStatus:
        self._engaged = True
        self._reason = reason or "engaged"
        self._changed_at = self._now()
        return self.status()

    def disengage(self) -> KillSwitchStatus:
        self._engaged = False
        self._reason = ""
        self._changed_at = self._now()
        return self.status()

    def status(self) -> KillSwitchStatus:
        return KillSwitchStatus(self._engaged, self._reason, self._changed_at)


# Prefixes considered child-facing — blocked while the kill switch is engaged. Health, metrics, and
# the ops control routes are intentionally excluded so an operator can always observe + disengage.
_CHILD_FACING_PREFIXES: tuple[str, ...] = (
    "/v1/learning/sessions",
    "/v1/learning/students",
    "/v1/offline",
    "/v1/sync",
)


def is_child_facing(path: str) -> bool:
    return any(path.startswith(p) for p in _CHILD_FACING_PREFIXES)
