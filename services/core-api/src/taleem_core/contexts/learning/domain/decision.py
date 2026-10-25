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


class ReasonCode(StrEnum):
    """Stable, localizable reason codes for "why this recommendation" (teacher/guardian/student).

    The codes and their parameter names are a public contract (ai-teacher/school/guardian OpenAPI):
    clients render them from their own catalogs. Never rename one; add a new code instead. Parameter
    values are strings (objective / misconception codes) or numbers (probabilities in [0, 1], day
    counts) — never prose.
    """

    SAFETY_GATE = "safety_gate"  # {}
    REVIEW_DUE = "review_due"  # {objective, days_overdue, due_count}
    MISCONCEPTION_ACTIVE = "misconception_active"  # {objective, misconception, evidence_count}
    HIGH_UNCERTAINTY = "high_uncertainty"  # {objective, uncertainty}
    READY_FOR_NEW = "ready_for_new"  # {objective, prerequisites}
    MASTERY_BELOW_THRESHOLD = "mastery_below_threshold"  # {objective, mastery, threshold}
    PREREQUISITE_GAP = "prerequisite_gap"  # {objective, prereq}
    DIAGNOSTIC_PLACEMENT = "diagnostic_placement"  # {objective, status, correct, incorrect, ...}
    PLACED_ABOVE = "placed_above"  # {count}: objectives skipped because placement put them secure
    RETENTION_AT_RISK = "retention_at_risk"  # {objective, mastery}
    REPEATED_FAILURE = "repeated_failure"  # {objective, consecutive_failures}
    MASTERY_REACHED = "mastery_reached"  # {objective, mastery, threshold}
    ALL_MASTERED = "all_mastered"  # {}


ReasonParam = str | int | float


@dataclass(frozen=True)
class Reason:
    code: ReasonCode
    params: tuple[tuple[str, ReasonParam], ...] = ()

    @staticmethod
    def of(code: ReasonCode, **params: ReasonParam) -> Reason:
        return Reason(code, tuple(params.items()))

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code.value, "params": dict(self.params)}


@dataclass(frozen=True)
class RationaleStep:
    rule_id: str
    note: str
    # The structured, localizable form of this step (``note`` stays the engine's English trace).
    reasons: tuple[Reason, ...] = ()


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
    return all(_mastered(knowledge, p) or _placed_secure(knowledge, p) for p in info.prerequisites)


def _placed_secure(knowledge: StudentKnowledge, code: str) -> bool:
    obj = knowledge.get(code)
    return obj is not None and obj.placed_secure


def unmet_prerequisites(
    knowledge: StudentKnowledge, prerequisites: tuple[str, ...]
) -> tuple[str, ...]:
    """The prerequisites not yet met (neither mastered nor placed secure), in the given order."""
    return tuple(
        p for p in prerequisites if not (_mastered(knowledge, p) or _placed_secure(knowledge, p))
    )


LEARNER_CHOICE_RULE = "learner_choice"


def learner_choice(
    objective_code: str,
    *,
    unmet: tuple[str, ...] = (),
    recommended: Decision | None = None,
) -> Decision:
    """A TEACH decision for a lesson the LEARNER chose (not the engine), with an honest rationale.

    The engine's own recommendation is recorded beside it (it still recommends, it never blocks a
    choice); unmet prerequisites become ``prerequisite_gap`` reasons — a hint, not a gate.
    """
    notes = ["You chose this lesson"]
    if recommended is not None and recommended.objective_code not in (None, objective_code):
        notes.append(
            f"the AI teacher suggested {recommended.kind.value} {recommended.objective_code}"
        )
    if unmet:
        notes.append(f"prerequisites not yet met: {', '.join(unmet)}")
    step = RationaleStep(
        rule_id=LEARNER_CHOICE_RULE,
        note="; ".join(notes),
        reasons=tuple(
            Reason.of(ReasonCode.PREREQUISITE_GAP, objective=objective_code, prereq=p)
            for p in unmet
        ),
    )
    return Decision(kind=DecisionKind.TEACH, objective_code=objective_code, rationale=(step,))


_DAY_S = 86_400.0


def review_reason(
    knowledge: StudentKnowledge, code: str, now: float, *, due_count: int = 1
) -> Reason:
    obj = knowledge.get(code)
    due_at = obj.memory.next_review_at if obj else 0.0
    overdue = max(0.0, now - due_at) / _DAY_S if due_at else 0.0
    return Reason.of(
        ReasonCode.REVIEW_DUE,
        objective=code,
        days_overdue=round(overdue, 1),
        due_count=due_count,
    )


def misconception_reason(obj: ObjectiveMastery, ref: str) -> Reason:
    count = next((m.evidence_count for m in obj.misconceptions if m.misconception_ref == ref), 0)
    return Reason.of(
        ReasonCode.MISCONCEPTION_ACTIVE,
        objective=obj.objective_code,
        misconception=ref,
        evidence_count=count,
    )


def below_threshold_reason(obj: ObjectiveMastery) -> Reason:
    return Reason.of(
        ReasonCode.MASTERY_BELOW_THRESHOLD,
        objective=obj.objective_code,
        mastery=round(obj.mastery.value, 3),
        threshold=obj.threshold.tau,
    )


def first_exposure(info: ObjectiveInfo) -> Reason:
    return Reason.of(
        ReasonCode.READY_FOR_NEW,
        objective=info.objective_code,
        prerequisites=len(info.prerequisites),
    )


def placement_reason(obj: ObjectiveMastery) -> Reason | None:
    """The diagnostic-placement reason for an objective whose prior placement seeded, if any."""
    p = obj.provenance
    if p is None or p.source != "diagnostic":
        return None
    params: dict[str, ReasonParam] = {
        "objective": obj.objective_code,
        "status": p.status,
        "correct": p.correct,
        "incorrect": p.incorrect,
        "prior": round(p.value, 3),
        "uncertainty": round(p.uncertainty, 3),
    }
    if p.inferred_from:
        params["inferred_from"] = p.inferred_from
    return Reason.of(ReasonCode.DIAGNOSTIC_PLACEMENT, **params)


def _placement_reasons(obj: ObjectiveMastery | None, skipped: int) -> tuple[Reason, ...]:
    out: list[Reason] = []
    if obj is not None and obj.attempts == 0:
        placed = placement_reason(obj)
        if placed is not None:
            out.append(placed)
    if skipped:
        out.append(Reason.of(ReasonCode.PLACED_ABOVE, count=skipped))
    return tuple(out)


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
            rationale=(
                RationaleStep(
                    "safety_gate",
                    "active safety/wellbeing signal",
                    (Reason.of(ReasonCode.SAFETY_GATE),),
                ),
            ),
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
                rationale=(
                    RationaleStep(
                        "due_reviews",
                        f"{len(due)} due; picked {code}",
                        (review_reason(knowledge, code, now, due_count=len(due)),),
                    ),
                ),
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
                rationale=(
                    RationaleStep(
                        "open_misconception",
                        f"confirmed {ref}",
                        (misconception_reason(obj, ref),),
                    ),
                ),
            )

    # 4. Eligible new/continuing learning (prerequisites mastered), by curriculum sequence.
    #    A diagnostic placement that put the learner above an objective counts like mastery here
    #    (only while they have not practised it); learners without a placement are unaffected.
    skipped = 0
    for info in sorted(curriculum.objectives, key=lambda o: o.sequence):
        obj = knowledge.get(info.objective_code)
        state = obj.state if obj else MasteryState.NOT_STARTED
        if state is MasteryState.MASTERED:
            continue
        if obj is not None and obj.placed_secure:
            skipped += 1
            continue
        if not _prereqs_met(knowledge, info):
            continue
        placed = _placement_reasons(obj, skipped)
        # Cold-start: a downstream objective we hold an uncertain prior about → diagnose first (F2).
        if obj is not None and _should_diagnose(obj, info, config):
            return Decision(
                kind=DecisionKind.DIAGNOSE,
                objective_code=info.objective_code,
                lesson_ref=info.lesson_ref,
                rationale=(
                    RationaleStep(
                        "cold_start",
                        "high-uncertainty prior; diagnose",
                        (
                            Reason.of(
                                ReasonCode.HIGH_UNCERTAINTY,
                                objective=info.objective_code,
                                uncertainty=round(obj.mastery.uncertainty, 3),
                            ),
                            *placed,
                        ),
                    ),
                ),
            )
        kind = DecisionKind.TEACH if state is MasteryState.NOT_STARTED else DecisionKind.CONTINUE
        first = (
            below_threshold_reason(obj)
            if kind is DecisionKind.CONTINUE and obj is not None
            else first_exposure(info)
        )
        return Decision(
            kind=kind,
            objective_code=info.objective_code,
            lesson_ref=info.lesson_ref,
            rationale=(
                RationaleStep(
                    "select_eligible",
                    f"{info.objective_code} state={state}",
                    (first, *placed),
                ),
            ),
        )

    # 5. Nothing eligible — everything mastered.
    return Decision(
        kind=DecisionKind.COMPLETE,
        rationale=(
            RationaleStep(
                "all_mastered",
                "no eligible objective remains",
                (
                    Reason.of(ReasonCode.ALL_MASTERED),
                    *((Reason.of(ReasonCode.PLACED_ABOVE, count=skipped),) if skipped else ()),
                ),
            ),
        ),
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
            rationale=(
                RationaleStep(
                    "misconception",
                    f"confirmed {ref} → remediate",
                    (misconception_reason(obj, ref),),
                ),
            ),
        )
    if obj.consecutive_failures >= config.max_consecutive_failures:
        return Decision(
            kind=DecisionKind.ESCALATE,
            objective_code=obj.objective_code,
            rationale=(
                RationaleStep(
                    "struggle",
                    "repeated failure → mentor",
                    (
                        Reason.of(
                            ReasonCode.REPEATED_FAILURE,
                            objective=obj.objective_code,
                            consecutive_failures=obj.consecutive_failures,
                        ),
                    ),
                ),
            ),
        )
    if result.newly_mastered or obj.state is MasteryState.MASTERED:
        return Decision(
            kind=DecisionKind.ADVANCE,
            objective_code=obj.objective_code,
            rationale=(
                RationaleStep(
                    "mastered",
                    "threshold met → advance + schedule review",
                    (
                        Reason.of(
                            ReasonCode.MASTERY_REACHED,
                            objective=obj.objective_code,
                            mastery=round(obj.mastery.value, 3),
                            threshold=obj.threshold.tau,
                        ),
                    ),
                ),
            ),
        )
    if obj.state in (MasteryState.NEEDS_REVIEW, MasteryState.AT_RISK):
        return Decision(
            kind=DecisionKind.REVISE,
            objective_code=obj.objective_code,
            rationale=(
                RationaleStep(
                    "decayed",
                    f"state={obj.state} → revise",
                    (
                        Reason.of(
                            ReasonCode.RETENTION_AT_RISK,
                            objective=obj.objective_code,
                            mastery=round(obj.mastery.value, 3),
                        ),
                    ),
                ),
            ),
        )
    return Decision(
        kind=DecisionKind.CONTINUE,
        objective_code=obj.objective_code,
        rationale=(
            RationaleStep(
                "in_progress", "below mastery → continue", (below_threshold_reason(obj),)
            ),
        ),
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
