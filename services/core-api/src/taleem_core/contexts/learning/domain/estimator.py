"""Mastery estimation — a transparent Bayesian Knowledge Tracing (BKT) model.

Chosen (STUDENT_MODEL §2, design-review F3) for explainability over benchmark accuracy: every update
is a legible Bayesian step a mentor can be shown. Behind the ``MasteryEstimator`` protocol so it can
be swapped for IRT/DKT later — from our own data, once it beats this baseline on retention.

BKT parameters (per objective, overridable):
- p_slip: P(answer wrong | mastered)          — a careless slip
- p_guess: P(answer right | not mastered)     — a lucky guess
- p_transit: P(learn on this opportunity | not yet mastered)
- p_l0: prior P(mastered) for a fresh learner (the cold-start prior, design-review F2)
"""

from __future__ import annotations

from dataclasses import dataclass

from .values import Mastery, clamp01

# Uncertainty shrinks by this factor per observation (narrows with evidence, STUDENT_MODEL §2),
# floored so we never claim perfect certainty.
_UNCERTAINTY_DECAY = 0.7
_UNCERTAINTY_FLOOR = 0.05


@dataclass(frozen=True)
class BKTParams:
    p_slip: float = 0.10
    p_guess: float = 0.20
    p_transit: float = 0.25
    p_l0: float = 0.30

    def __post_init__(self) -> None:
        for name in ("p_slip", "p_guess", "p_transit", "p_l0"):
            object.__setattr__(self, name, clamp01(getattr(self, name)))


class BKTEstimator:
    """A Bayesian Knowledge Tracing estimator. Implements the ``MasteryEstimator`` port."""

    def __init__(self, params: BKTParams | None = None) -> None:
        self._params = params or BKTParams()

    def initial(self, params: BKTParams | None = None) -> Mastery:
        """Cold-start estimate: the prior at high uncertainty (we have no evidence yet)."""
        p = params or self._params
        return Mastery(value=p.p_l0, uncertainty=1.0)

    def update(self, prior: Mastery, *, correct: bool, params: BKTParams | None = None) -> Mastery:
        """One Bayesian update from an observed correct/incorrect response.

        Returns the posterior mastery after conditioning on the observation and applying the
        learning-transition step. Deterministic and side-effect-free.
        """
        p = params or self._params
        pl = prior.value

        # Condition on the observation (Bayes' rule with slip/guess).
        if correct:
            num = pl * (1.0 - p.p_slip)
            denom = num + (1.0 - pl) * p.p_guess
        else:
            num = pl * p.p_slip
            denom = num + (1.0 - pl) * (1.0 - p.p_guess)
        pl_given_obs = num / denom if denom > 0 else pl

        # Learning transition: a not-yet-mastered learner may learn on this opportunity.
        pl_next = pl_given_obs + (1.0 - pl_given_obs) * p.p_transit

        new_uncertainty = max(_UNCERTAINTY_FLOOR, prior.uncertainty * _UNCERTAINTY_DECAY)
        return Mastery(value=pl_next, uncertainty=new_uncertainty)
