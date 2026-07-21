"""The Learning Decision Engine (pure, deterministic) — LEARNING_DECISION_ENGINE.md.

Given a learner's knowledge and the curriculum, it decides what happens next and *why*. No I/O, no
LLM, no randomness — every ``Decision`` is reproducible and carries a ``rationale`` for the
mentor/parent "why" view. This is the "critical learning logic" held to ≥95% coverage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .knowledge import AttemptResult, ObjectiveMastery, StudentKnowledge
from .values import MasteryState


class DecisionKind(StrEnum):
    DIAGNOSE = "diagnose"  # narrow uncertainty (cold-start / placement)
    TEACH = "teach"  # new learning (first exposure)
    CONTINUE = "continue"  # keep working the current objective
    REVIEW = "review"  # spaced retrieval of a due objective
    REMEDIATE = "remediate"  # clear a confirmed misconception
    ADVANCE = "advance"  # objective mastered — move on
    REVISE = "revise"  # objective decayed — needs review scheduling
    ESCALATE = "escalate"  # hand off to a mentor / safeguarding
    REST = "rest"  # stop (wellbeing / nothing due)
    COMPLETE = "complete"  # all eligible objectives mastered


@dataclass(frozen=True)
class RationaleStep:
    rule_id: str
    note: str


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    objective_code: str | None = None
    misconception_ref: str | None = None
    lesson_ref: str | None = None
    rationale: tuple[RationaleStep, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ObjectiveInfo:
    objective_code: str
    lesson_ref: str
    prerequisites: tuple[str, ...] = ()
    sequence: int = 0


@dataclass(frozen=True)
class CurriculumGraph:
    """A minimal projection of the curriculum the engine reasons over (prereq DAG + lesson refs)."""

    objectives: tuple[ObjectiveInfo, ...]

    def by_code(self, code: str) -> ObjectiveInfo | None:
        return next((o for o in self.objectives if o.objective_code == code), None)


@dataclass(frozen=True)
class DecisionConfig:
    diagnose_uncertainty_above: float = 0.6
    diagnose_prior_above: float = 0.15
    max_consecutive_failures: int = 4
    daily_review_cap: int = 20


def _mastered(knowledge: StudentKnowledge, code: str) -> bool:
    obj = knowledge.get(code)
    return obj is not None and obj.state is MasteryState.MASTERED


def _prereqs_met(knowledge: StudentKnowledge, info: ObjectiveInfo) -> bool:
    return all(_mastered(knowledge, p) for p in info.prerequisites)


def select_next(
    knowledge: StudentKnowledge,
    curriculum: CurriculumGraph,
    config: DecisionConfig,
    now: float,
    *,
    safety_flag: bool = False,
    reviews_done_today: int = 0,
) -> Decision:
    """Choose the next action to start/continue a session (LEARNING_DECISION_ENGINE §3)."""
    # 1. Safety/wellbeing gate — always first.
    if safety_flag:
        return Decision(
            kind=DecisionKind.ESCALATE,
            rationale=(RationaleStep("safety_gate", "active safety/wellbeing signal"),),
        )

    # 2. Due reviews first (bounded by the daily cap) — spacing wins when retention is at risk.
    if reviews_done_today < config.daily_review_cap:
        due = knowledge.due_reviews(now)
        if due:
            code = _rank_reviews(knowledge, due)
            info = curriculum.by_code(code)
            return Decision(
                kind=DecisionKind.REVIEW,
                objective_code=code,
                lesson_ref=info.lesson_ref if info else None,
                rationale=(RationaleStep("due_reviews", f"{len(due)} due; picked {code}"),),
            )

    # 3. Open confirmed misconceptions block progress → remediate.
    for info in curriculum.objectives:
        obj = knowledge.get(info.objective_code)
        if obj is not None and obj.has_confirmed_misconception():
            ref = next(m.misconception_ref for m in obj.active_misconceptions())
            return Decision(
                kind=DecisionKind.REMEDIATE,
                objective_code=info.objective_code,
                misconception_ref=ref,
                lesson_ref=info.lesson_ref,
                rationale=(RationaleStep("open_misconception", f"confirmed {ref}"),),
            )

    # 4. Eligible new/continuing learning (prerequisites mastered), by curriculum sequence.
    for info in sorted(curriculum.objectives, key=lambda o: o.sequence):
        obj = knowledge.get(info.objective_code)
        state = obj.state if obj else MasteryState.NOT_STARTED
        if state is MasteryState.MASTERED:
            continue
        if not _prereqs_met(knowledge, info):
            continue
        # Cold-start: a downstream objective we hold an uncertain prior about → diagnose first (F2).
        if obj is not None and _should_diagnose(obj, info, config):
            return Decision(
                kind=DecisionKind.DIAGNOSE,
                objective_code=info.objective_code,
                lesson_ref=info.lesson_ref,
                rationale=(RationaleStep("cold_start", "high-uncertainty prior; diagnose"),),
            )
        kind = DecisionKind.TEACH if state is MasteryState.NOT_STARTED else DecisionKind.CONTINUE
        return Decision(
            kind=kind,
            objective_code=info.objective_code,
            lesson_ref=info.lesson_ref,
            rationale=(RationaleStep("select_eligible", f"{info.objective_code} state={state}"),),
        )

    # 5. Nothing eligible — everything mastered.
    return Decision(
        kind=DecisionKind.COMPLETE,
        rationale=(RationaleStep("all_mastered", "no eligible objective remains"),),
    )


def post_interaction(
    obj: ObjectiveMastery, result: AttemptResult, config: DecisionConfig
) -> Decision:
    """Decide continue / revise / remediate / advance after one interaction (§8, brief step 7)."""
    if obj.has_confirmed_misconception():
        ref = next(m.misconception_ref for m in obj.active_misconceptions())
        return Decision(
            kind=DecisionKind.REMEDIATE,
            objective_code=obj.objective_code,
            misconception_ref=ref,
            rationale=(RationaleStep("misconception", f"confirmed {ref} → remediate"),),
        )
    if obj.consecutive_failures >= config.max_consecutive_failures:
        return Decision(
            kind=DecisionKind.ESCALATE,
            objective_code=obj.objective_code,
            rationale=(RationaleStep("struggle", "repeated failure → mentor"),),
        )
    if result.newly_mastered or obj.state is MasteryState.MASTERED:
        return Decision(
            kind=DecisionKind.ADVANCE,
            objective_code=obj.objective_code,
            rationale=(RationaleStep("mastered", "threshold met → advance + schedule review"),),
        )
    if obj.state in (MasteryState.NEEDS_REVIEW, MasteryState.AT_RISK):
        return Decision(
            kind=DecisionKind.REVISE,
            objective_code=obj.objective_code,
            rationale=(RationaleStep("decayed", f"state={obj.state} → revise"),),
        )
    return Decision(
        kind=DecisionKind.CONTINUE,
        objective_code=obj.objective_code,
        rationale=(RationaleStep("in_progress", "below mastery → continue"),),
    )


def _rank_reviews(knowledge: StudentKnowledge, due: list[str]) -> str:
    # Prioritize the most-decayed (lowest mastery) — highest retention risk first (§4).
    def risk(code: str) -> float:
        obj = knowledge.get(code)
        return obj.mastery.value if obj else 1.0

    return min(due, key=risk)


def _should_diagnose(obj: ObjectiveMastery, info: ObjectiveInfo, config: DecisionConfig) -> bool:
    return (
        bool(info.prerequisites)
        and obj.mastery.uncertainty >= config.diagnose_uncertainty_above
        and obj.mastery.value >= config.diagnose_prior_above
    )
