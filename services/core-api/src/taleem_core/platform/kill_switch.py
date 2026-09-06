"""Kill switch — operational halt of child-facing traffic (pure-stdlib core).

A deny-when-engaged control an operator flips to immediately stop child-facing use during an
incident ([INCIDENT_RESPONSE.md], [PILOT0_OPERATIONS.md]). When engaged, child-facing routes return
503; health, metrics, and the ops control routes stay up so the operator can observe + disengage.
This is an ops safety control, not a product feature.

**State is pluggable and must be shared whenever more than one instance serves traffic.** The flag
was originally process-local, which made the control fail *open*: engaging it on one instance left
every other instance (another replica, or a fresh serverless invocation) serving children normally,
while the ops endpoint truthfully reported "engaged". `InMemoryKillSwitchState` keeps that
behaviour for local/dev/test single-process use; a SQL-backed state (see
`contexts/ops/adapters/persistence/kill_switch_store.py`) is wired whenever a real database is
configured, so every instance reads the same flag.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class KillSwitchStatus:
    engaged: bool
    reason: str
    changed_at: float

    def to_dict(self) -> dict[str, object]:
        return {"engaged": self.engaged, "reason": self.reason, "changed_at": self.changed_at}


class KillSwitchState(Protocol):
    """Where the halt flag lives. Implementations must be safe to read on every request."""

    def read(self) -> KillSwitchStatus: ...

    def write(self, status: KillSwitchStatus) -> None: ...


class InMemoryKillSwitchState:
    """Process-local flag. Correct only for a single-process deployment (local/dev/tests)."""

    def __init__(self) -> None:
        self._status = KillSwitchStatus(False, "", 0.0)

    def read(self) -> KillSwitchStatus:
        return self._status

    def write(self, status: KillSwitchStatus) -> None:
        self._status = status


class KillSwitch:
    """Halt flag. Engaging it makes child-facing routes fail closed (503) on every instance."""

    def __init__(self, clock: Callable[[], float], state: KillSwitchState | None = None) -> None:
        self._now = clock
        self._state: KillSwitchState = state if state is not None else InMemoryKillSwitchState()

    @property
    def engaged(self) -> bool:
        return self._state.read().engaged

    def engage(self, reason: str) -> KillSwitchStatus:
        status = KillSwitchStatus(True, reason or "engaged", self._now())
        self._state.write(status)
        return status

    def disengage(self) -> KillSwitchStatus:
        status = KillSwitchStatus(False, "", self._now())
        self._state.write(status)
        return status

    def status(self) -> KillSwitchStatus:
        return self._state.read()


# Prefixes considered child-facing — blocked while the kill switch is engaged. Health, metrics, and
# the ops control routes are intentionally excluded so an operator can always observe + disengage.
_CHILD_FACING_PREFIXES: tuple[str, ...] = (
    "/v1/learning/sessions",
    "/v1/learning/students",
    "/v1/offline",
    "/v1/sync",
    # Learner sign-in and the family roster it reads. A halt must stop children *entering* the
    # platform, not only using it. The guardian routes are deliberately NOT listed: during an
    # incident a guardian must still be able to sign in and withdraw consent, and the kill switch
    # exists to protect children, not to lock adults out of the control they hold over their data.
    "/v1/identity/learners:",
)


def is_child_facing(path: str) -> bool:
    return any(path.startswith(p) for p in _CHILD_FACING_PREFIXES)
