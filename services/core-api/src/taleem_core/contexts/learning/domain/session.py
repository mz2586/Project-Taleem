"""The Session aggregate (pure-stdlib) — the learning-session saga (SESSION_ENGINE.md).

A durable state machine spanning multiple interactions, resumable and interruptible. Escalation and
safe-end are reachable from any active state (child safety is structural, not an error path).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SessionState(StrEnum):
    CREATED = "created"
    LOADING = "loading"
    PLANNING = "planning"
    TEACHING = "teaching"
    INTERACTING = "interacting"
    ASSESSING = "assessing"
    UPDATING = "updating"
    SCHEDULING = "scheduling"
    RECORDING = "recording"
    ENDED = "ended"
    PAUSED = "paused"
    ESCALATED = "escalated"
    ENDED_SAFELY = "ended_safely"
    ABANDONED = "abandoned"


_ACTIVE = {
    SessionState.LOADING,
    SessionState.PLANNING,
    SessionState.TEACHING,
    SessionState.INTERACTING,
    SessionState.ASSESSING,
    SessionState.UPDATING,
    SessionState.SCHEDULING,
    SessionState.RECORDING,
    SessionState.PAUSED,
}

# Canonical forward edges of the lifecycle; loops back to TEACHING for the next objective.
_FORWARD: dict[SessionState, set[SessionState]] = {
    SessionState.CREATED: {SessionState.LOADING},
    SessionState.LOADING: {SessionState.PLANNING},
    SessionState.PLANNING: {SessionState.TEACHING, SessionState.ENDED},
    SessionState.TEACHING: {SessionState.INTERACTING},
    SessionState.INTERACTING: {SessionState.ASSESSING},
    SessionState.ASSESSING: {SessionState.UPDATING},
    SessionState.UPDATING: {SessionState.SCHEDULING},
    SessionState.SCHEDULING: {SessionState.RECORDING},
    SessionState.RECORDING: {SessionState.TEACHING, SessionState.ENDED},
    SessionState.PAUSED: _ACTIVE,
}


class SessionError(ValueError):
    """Raised on an illegal session state transition."""


@dataclass
class Turn:
    actor: str  # 'tutor' | 'student'
    kind: str
    text: str
    at: float


@dataclass
class Interaction:
    interaction_id: str
    objective_code: str
    decision_kind: str
    turns: list[Turn] = field(default_factory=list)
    outcome: str | None = None
    evidence_id: str | None = None
    occurred_at: float = 0.0


@dataclass
class Session:
    session_id: str
    student_ref: str
    state: SessionState = SessionState.CREATED
    started_at: float = 0.0
    ended_at: float | None = None
    correlation_id: str = ""
    interactions: list[Interaction] = field(default_factory=list)
    lock_version: int = 1

    def transition_to(self, to: SessionState) -> None:
        allowed = _FORWARD.get(self.state, set())
        if to not in allowed:
            raise SessionError(f"illegal session transition: {self.state} -> {to}")
        self.state = to

    def escalate(self) -> None:
        """Reachable from any active state — safety/pedagogical handoff (never blocked)."""
        if self.state in _ACTIVE or self.state in (SessionState.CREATED, SessionState.RECORDING):
            self.state = SessionState.ESCALATED
        else:
            raise SessionError(f"cannot escalate from {self.state}")

    def pause(self) -> None:
        if self.state in _ACTIVE:
            self.state = SessionState.PAUSED
        else:
            raise SessionError(f"cannot pause from {self.state}")

    def end(self, at: float, *, safely: bool = False) -> None:
        self.state = SessionState.ENDED_SAFELY if safely else SessionState.ENDED
        self.ended_at = at

    def add_interaction(self, interaction: Interaction) -> None:
        self.interactions.append(interaction)
