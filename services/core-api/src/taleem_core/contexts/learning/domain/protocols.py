"""Domain ports for the swappable learning-science models (LEARNING_DOMAIN_MODEL §6).

Defining these in the domain lets the ``StudentKnowledge`` aggregate depend on the *behaviour* of an
estimator / forgetting model without importing a concrete implementation — the single most important
extensibility seam ("the science is a plugin, the domain is stable", design-review maintainability).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .values import Mastery, MemoryStrength


@runtime_checkable
class MasteryEstimator(Protocol):
    def initial(self) -> Mastery: ...
    def update(self, prior: Mastery, *, correct: bool) -> Mastery: ...


@runtime_checkable
class ForgettingModel(Protocol):
    def predicted_recall(self, mastery: Mastery, memory: MemoryStrength, now: float) -> float: ...
    def on_review(self, memory: MemoryStrength, *, correct: bool, now: float) -> MemoryStrength: ...
    def on_learned(self, now: float) -> MemoryStrength: ...
