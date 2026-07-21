"""Value objects for the Learning Intelligence Platform (pure-stdlib, immutable).

Grounded in docs/11-learning-intelligence/STUDENT_MODEL.md and LEARNING_DOMAIN_MODEL.md §2.
No framework imports — the learning "brain" is a pure domain, unit-testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


def clamp01(x: float) -> float:
    """Clamp to the [0, 1] probability range."""
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


class MasteryState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    MASTERED = "mastered"
    NEEDS_REVIEW = "needs_review"
    AT_RISK = "at_risk"


class MisconceptionState(StrEnum):
    SUSPECTED = "suspected"
    CONFIRMED = "confirmed"
    BEING_REMEDIATED = "being_remediated"
    CLEARED = "cleared"
    RECURRED = "recurred"


class Outcome(StrEnum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIAL = "partial"


class InteractionContext(StrEnum):
    DIAGNOSTIC = "diagnostic"
    FIRST_EXPOSURE = "first_exposure"
    PRACTICE = "practice"
    SPACED_REVIEW = "spaced_review"
    REMEDIATION = "remediation"
    FORMATIVE = "formative"


@dataclass(frozen=True)
class Mastery:
    """A calibrated mastery estimate: a probability plus how sure we are of it."""

    value: float = 0.0
    uncertainty: float = 1.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", clamp01(self.value))
        object.__setattr__(self, "uncertainty", clamp01(self.uncertainty))


@dataclass(frozen=True)
class MasteryThreshold:
    """Per-objective bar for declaring mastery (LEARNING_DECISION_ENGINE §8)."""

    tau: float = 0.85
    max_uncertainty: float = 0.20


@dataclass(frozen=True)
class MemoryStrength:
    """Retention parameters driving spaced review; `stability_s` is a half-life."""

    stability_s: float = 86_400.0  # initial half-life ~1 day
    last_seen_at: float = 0.0
    next_review_at: float = 0.0


@dataclass(frozen=True)
class Confidence:
    """The learner's self-reported confidence — separate from measured mastery."""

    self_reported: float = 0.5
    sampled_at: float = 0.0


@dataclass(frozen=True)
class Pace:
    """How much practice this learner needs to reach mastery, vs a baseline (STUDENT_MODEL §7)."""

    attempts_to_mastery: int = 0
    time_to_mastery_s: float = 0.0
    pace_factor: float = 1.0
