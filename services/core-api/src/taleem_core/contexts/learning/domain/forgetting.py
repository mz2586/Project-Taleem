"""Forgetting / spaced-repetition model (STUDENT_MODEL §5, LEARNING_SCIENCE §2).

A transparent half-life memory model: predicted recall decays exponentially with time since last
seen, successful spaced retrievals expand the interval (stability grows), failures contract it.
Behind the ``ForgettingModel`` port so it can be upgraded to FSRS-style scheduling later without
changing callers. All computation is offline-capable (a stored ``next_review_at``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .values import Mastery, MemoryStrength, clamp01


@dataclass(frozen=True)
class ForgettingConfig:
    target_recall: float = 0.85  # schedule the next review when predicted recall dips to this
    expansion: float = 2.0  # stability multiplier on a successful review (expanding intervals)
    contraction: float = 0.5  # stability multiplier on a failed review
    min_stability_s: float = 3_600.0  # 1 hour floor
    max_stability_s: float = 315_360_000.0  # ~10 years ceiling


class HalfLifeForgettingModel:
    """Exponential-decay memory model. Implements the ``ForgettingModel`` port."""

    def __init__(self, config: ForgettingConfig | None = None) -> None:
        self._cfg = config or ForgettingConfig()

    def predicted_recall(self, mastery: Mastery, memory: MemoryStrength, now: float) -> float:
        """Mastery decayed by elapsed time since last seen (the value the state machine reads)."""
        elapsed = max(0.0, now - memory.last_seen_at)
        if memory.stability_s <= 0:
            return mastery.value
        decay = math.exp(-elapsed / memory.stability_s)
        return clamp01(mastery.value * decay)

    def on_review(self, memory: MemoryStrength, *, correct: bool, now: float) -> MemoryStrength:
        """Update stability after a spaced retrieval and compute the next due date."""
        factor = self._cfg.expansion if correct else self._cfg.contraction
        stability = min(
            self._cfg.max_stability_s, max(self._cfg.min_stability_s, memory.stability_s * factor)
        )
        return self._schedule(stability, now)

    def on_learned(self, now: float, stability_s: float | None = None) -> MemoryStrength:
        """Initialize memory when an objective is first mastered."""
        stability = stability_s if stability_s is not None else self._cfg.min_stability_s * 24
        return self._schedule(stability, now)

    def _schedule(self, stability_s: float, now: float) -> MemoryStrength:
        # Solve target_recall = exp(-interval / stability) for interval.
        interval = -stability_s * math.log(self._cfg.target_recall)
        return MemoryStrength(
            stability_s=stability_s, last_seen_at=now, next_review_at=now + interval
        )
