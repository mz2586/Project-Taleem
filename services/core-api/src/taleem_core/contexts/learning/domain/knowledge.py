"""The Student Knowledge aggregate (pure-stdlib) — the platform's memory of one learner.

Per docs/11-learning-intelligence/STUDENT_MODEL.md. The aggregate owns its objectives, immutable
assessment evidence, and misconception records, and enforces the mastery invariants. Mutation flows
through ``apply_attempt``, which takes injected estimator/forgetting models (the swappable science)
so the aggregate stays stable while the pedagogy evolves.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .protocols import ForgettingModel, MasteryEstimator
from .values import (
    Confidence,
    InteractionContext,
    Mastery,
    MasteryState,
    MasteryThreshold,
    MemoryStrength,
    MisconceptionState,
    Outcome,
    Pace,
    clamp01,
)

# Below this predicted-recall level a mastered objective is considered likely-forgotten.
_AT_RISK_FLOOR = 0.6


@dataclass(frozen=True)
class AssessmentEvidence:
    """Immutable record of one attempt — the system of record every estimate derives from."""

    evidence_id: str
    student_ref: str
    objective_code: str
    item_ref: str
    session_id: str
    outcome: Outcome
    context: InteractionContext
    misconception_hits: tuple[str, ...]
    hints_used: int
    response_time_ms: int
    mastery_before: float
    mastery_after: float
    occurred_at: float


@dataclass
class MisconceptionRecord:
    misconception_ref: str
    objective_code: str
    state: MisconceptionState
    evidence_count: int
    first_detected_at: float
    last_detected_at: float
    cleared_at: float | None = None

    @property
    def is_active(self) -> bool:
        return self.state in (
            MisconceptionState.SUSPECTED,
            MisconceptionState.CONFIRMED,
            MisconceptionState.BEING_REMEDIATED,
        )


@dataclass
class ObjectiveMastery:
    """One learner's state on one SLO."""

    objective_code: str
    mastery: Mastery = field(default_factory=Mastery)
    state: MasteryState = MasteryState.NOT_STARTED
    memory: MemoryStrength = field(default_factory=MemoryStrength)
    confidence: Confidence = field(default_factory=Confidence)
    pace: Pace = field(default_factory=Pace)
    threshold: MasteryThreshold = field(default_factory=MasteryThreshold)
    attempts: int = 0
    correct_streak: int = 0
    consecutive_failures: int = 0
    misconceptions: list[MisconceptionRecord] = field(default_factory=list)

    def has_confirmed_misconception(self) -> bool:
        return any(
            m.state is MisconceptionState.CONFIRMED and m.is_active for m in self.misconceptions
        )

    def active_misconceptions(self) -> list[MisconceptionRecord]:
        return [m for m in self.misconceptions if m.is_active]


@dataclass
class AttemptResult:
    """What changed from one attempt — drives the trace, events, and the next decision."""

    objective_code: str
    outcome: Outcome
    mastery_before: Mastery
    mastery_after: Mastery
    state_before: MasteryState
    state_after: MasteryState
    newly_mastered: bool
    confirmed_misconceptions: list[str]
    cleared_misconceptions: list[str]
    evidence_id: str


@dataclass
class StudentKnowledge:
    """Aggregate root: one learner's complete, evidence-based learning state."""

    student_ref: str
    objectives: dict[str, ObjectiveMastery] = field(default_factory=dict)
    evidence: list[AssessmentEvidence] = field(default_factory=list)
    lock_version: int = 1

    def ensure_objective(
        self,
        objective_code: str,
        *,
        initial: Mastery | None = None,
        threshold: MasteryThreshold | None = None,
    ) -> ObjectiveMastery:
        obj = self.objectives.get(objective_code)
        if obj is None:
            obj = ObjectiveMastery(
                objective_code=objective_code,
                mastery=initial or Mastery(),
                threshold=threshold or MasteryThreshold(),
            )
            self.objectives[objective_code] = obj
        return obj

    def get(self, objective_code: str) -> ObjectiveMastery | None:
        return self.objectives.get(objective_code)

    def due_reviews(self, now: float) -> list[str]:
        """Objectives whose next review is due (used by the decision engine)."""
        return [
            code
            for code, obj in self.objectives.items()
            if obj.state in (MasteryState.MASTERED, MasteryState.NEEDS_REVIEW, MasteryState.AT_RISK)
            and obj.memory.next_review_at
            and obj.memory.next_review_at <= now
        ]

    def apply_attempt(
        self,
        *,
        evidence_id: str,
        objective_code: str,
        item_ref: str,
        session_id: str,
        correct: bool,
        misconception_hits: tuple[str, ...],
        hints_used: int,
        response_time_ms: int,
        context: InteractionContext,
        self_confidence: float | None,
        estimator: MasteryEstimator,
        forgetting: ForgettingModel,
        now: float,
    ) -> AttemptResult:
        """Apply one scored attempt: update mastery, misconceptions, memory, state, and evidence.

        Pure with respect to injected models; the only mutation is to this aggregate. Returns an
        ``AttemptResult`` describing every change (for events/trace/decisions).
        """
        obj = self.ensure_objective(objective_code)
        state_before = obj.state
        mastery_before = obj.mastery
        outcome = Outcome.CORRECT if correct else Outcome.INCORRECT

        # 1. Update the mastery estimate (explainable Bayesian step).
        obj.mastery = estimator.update(mastery_before, correct=correct)
        obj.attempts += 1
        obj.correct_streak = obj.correct_streak + 1 if correct else 0
        obj.consecutive_failures = 0 if correct else obj.consecutive_failures + 1
        if self_confidence is not None:
            obj.confidence = Confidence(self_reported=clamp01(self_confidence), sampled_at=now)

        # 2. Misconceptions.
        confirmed, cleared = self._update_misconceptions(
            obj, correct=correct, hits=misconception_hits, now=now
        )

        # 3. Memory / scheduling.
        was_mastered = state_before is MasteryState.MASTERED
        newly_mastered = False
        provisional_state = self._derive_state(obj, forgetting, now)
        if provisional_state is MasteryState.MASTERED and not was_mastered:
            obj.memory = forgetting.on_learned(now)
            newly_mastered = True
        elif context is InteractionContext.SPACED_REVIEW:
            obj.memory = forgetting.on_review(obj.memory, correct=correct, now=now)

        obj.state = self._derive_state(obj, forgetting, now)

        # 4. Immutable evidence (system of record).
        self.evidence.append(
            AssessmentEvidence(
                evidence_id=evidence_id,
                student_ref=self.student_ref,
                objective_code=objective_code,
                item_ref=item_ref,
                session_id=session_id,
                outcome=outcome,
                context=context,
                misconception_hits=misconception_hits,
                hints_used=hints_used,
                response_time_ms=response_time_ms,
                mastery_before=mastery_before.value,
                mastery_after=obj.mastery.value,
                occurred_at=now,
            )
        )

        return AttemptResult(
            objective_code=objective_code,
            outcome=outcome,
            mastery_before=mastery_before,
            mastery_after=obj.mastery,
            state_before=state_before,
            state_after=obj.state,
            newly_mastered=newly_mastered,
            confirmed_misconceptions=confirmed,
            cleared_misconceptions=cleared,
            evidence_id=evidence_id,
        )

    # -- internals ------------------------------------------------------------------------

    def _update_misconceptions(
        self, obj: ObjectiveMastery, *, correct: bool, hits: tuple[str, ...], now: float
    ) -> tuple[list[str], list[str]]:
        confirmed: list[str] = []
        cleared: list[str] = []
        by_ref = {m.misconception_ref: m for m in obj.misconceptions}

        for ref in hits:
            record = by_ref.get(ref)
            if record is None:
                record = MisconceptionRecord(
                    misconception_ref=ref,
                    objective_code=obj.objective_code,
                    state=MisconceptionState.SUSPECTED,
                    evidence_count=1,
                    first_detected_at=now,
                    last_detected_at=now,
                )
                obj.misconceptions.append(record)
                by_ref[ref] = record
            else:
                record.evidence_count += 1
                record.last_detected_at = now
                if record.state in (MisconceptionState.SUSPECTED, MisconceptionState.CLEARED):
                    record.state = (
                        MisconceptionState.CONFIRMED
                        if record.state is MisconceptionState.SUSPECTED
                        else MisconceptionState.RECURRED
                    )
                    if record.state is MisconceptionState.CONFIRMED:
                        confirmed.append(ref)

        # A correct answer is evidence the corrected model is taking hold: clear active
        # misconceptions on this objective not just triggered (simplified clearance rule).
        if correct:
            for record in obj.misconceptions:
                if record.is_active and record.misconception_ref not in hits:
                    record.state = MisconceptionState.CLEARED
                    record.cleared_at = now
                    cleared.append(record.misconception_ref)

        return confirmed, cleared

    def _derive_state(
        self, obj: ObjectiveMastery, forgetting: ForgettingModel, now: float
    ) -> MasteryState:
        """Pure function of estimate/uncertainty/misconceptions/memory (STUDENT_MODEL §4)."""
        if obj.attempts == 0:
            return MasteryState.NOT_STARTED
        if obj.has_confirmed_misconception():
            return MasteryState.IN_PROGRESS
        meets = (
            obj.mastery.value >= obj.threshold.tau
            and obj.mastery.uncertainty <= obj.threshold.max_uncertainty
        )
        if not meets:
            return MasteryState.IN_PROGRESS
        # Mastered by the estimate — now check retention decay.
        predicted = forgetting.predicted_recall(obj.mastery, obj.memory, now)
        if obj.memory.last_seen_at and predicted < _AT_RISK_FLOOR:
            return MasteryState.AT_RISK
        if obj.memory.last_seen_at and predicted < obj.threshold.tau:
            return MasteryState.NEEDS_REVIEW
        return MasteryState.MASTERED
