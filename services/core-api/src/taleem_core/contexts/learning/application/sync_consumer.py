"""Durable sync consumer — Phase 6.2B (offline synchronization engine).

Translates offline ``attempt.submitted`` deltas (from ``POST /v1/sync/batch``) into durable
``AssessmentEvidence`` via the existing ``LearningUnitOfWork``, reusing the existing idempotency
model: evidence is append-only and the aggregate hydrates every recorded ``evidence_id``, so a
replayed attempt (same client-generated ``evidence_id``) is detected and skipped **before** any
mastery mutation — idempotent and durable across restarts (the evidence table *is* the ledger).

This closes gap **G3** from OFFLINE_ARCHITECTURE.md §12 without changing the learning domain, the
session path, or adding any child-data table. Grading is session-less: the published lesson's
``ItemView`` is scored by the existing pure ``evaluate`` scorer, then applied through the same
aggregate + outbox the live session path uses.

Non-negotiable enforced here: a **summative** item is never auto-graded by sync (mentor-mediated).
"""

from __future__ import annotations

from collections.abc import Callable

from ...learning.domain import events as ev
from ...learning.domain.curriculum_view import ItemView, LessonView
from ...learning.domain.events import LearningEvent
from ...learning.domain.knowledge import AttemptResult, StudentKnowledge
from ...learning.domain.protocols import ForgettingModel, MasteryEstimator
from ...learning.domain.scorer import evaluate
from ...learning.domain.values import InteractionContext, Outcome
from ...sync.domain import DeltaType, Status, SyncDelta
from ..adapters.persistence.uow import LearningUnitOfWork
from .ports import CurriculumReadModel

# decision_kind (or an explicit context) -> the learning-science interaction context.
_CONTEXT_FOR: dict[str, InteractionContext] = {
    "diagnose": InteractionContext.DIAGNOSTIC,
    "practice": InteractionContext.PRACTICE,
    "teach": InteractionContext.PRACTICE,
    "review": InteractionContext.SPACED_REVIEW,
    "revise": InteractionContext.SPACED_REVIEW,
    "remediate": InteractionContext.REMEDIATION,
}


class SyncEvidenceConsumer:
    """Applies ``attempt.submitted`` deltas durably + idempotently. Implements ``EvidenceSink``."""

    def __init__(
        self,
        uow_factory: Callable[[], LearningUnitOfWork],
        curriculum: CurriculumReadModel,
        estimator: MasteryEstimator,
        forgetting: ForgettingModel,
        clock: Callable[[], float],
    ) -> None:
        self._uow = uow_factory
        self._curriculum = curriculum
        self._estimator = estimator
        self._forgetting = forgetting
        self._now = clock

    def apply_attempt(self, delta: SyncDelta) -> Status:
        """Grade + record one offline attempt. Returns applied / duplicate / ignored / conflict."""
        if delta.type is not DeltaType.ATTEMPT_SUBMITTED:
            return Status.CONFLICT  # routing error — never silently dropped

        p = delta.payload
        try:
            student_ref = str(p["student_ref"])
            objective_code = str(p["objective_code"])
            item_ref = str(p["item_ref"])
            option_raw = p["option"]
        except KeyError:
            return Status.CONFLICT  # malformed payload — surfaced, not dropped
        if not isinstance(option_raw, (int, str)) or isinstance(option_raw, bool):
            return Status.CONFLICT
        try:
            option = int(option_raw)
        except ValueError:
            return Status.CONFLICT

        # Stable, client-generated idempotency key (falls back to the delta's clientEventId).
        evidence_id = str(p.get("evidence_id") or delta.client_event_id)
        session_id = str(p.get("session_id", ""))
        hints_used = _as_int(p.get("hints_used"), 0)
        response_time_ms = _as_int(p.get("response_time_ms"), 0)
        self_confidence = _as_float(p.get("self_confidence"))
        context = _CONTEXT_FOR.get(str(p.get("context", "practice")), InteractionContext.PRACTICE)

        lesson = self._curriculum.lesson_for(objective_code)
        if lesson is None:
            return Status.CONFLICT  # no published content to grade against
        item = _gradable_item(lesson, item_ref)
        if item is None:
            # Either unknown, or a mentor-mediated summative item — never auto-graded by sync.
            return Status.IGNORED

        now = self._now()
        with self._uow() as uow:
            knowledge = uow.knowledge.get(student_ref) or StudentKnowledge(student_ref=student_ref)
            # Idempotency (durable): the aggregate hydrates all recorded evidence.
            if any(e.evidence_id == evidence_id for e in knowledge.evidence):
                return Status.DUPLICATE

            outcome, misconception_hits = evaluate(item, option)
            knowledge.ensure_objective(objective_code, initial=self._estimator.initial())
            result = knowledge.apply_attempt(
                evidence_id=evidence_id,
                objective_code=objective_code,
                item_ref=item_ref,
                session_id=session_id,
                correct=outcome is Outcome.CORRECT,
                misconception_hits=misconception_hits,
                hints_used=hints_used,
                response_time_ms=response_time_ms,
                context=context,
                self_confidence=self_confidence,
                estimator=self._estimator,
                forgetting=self._forgetting,
                now=now,
            )
            obj = knowledge.get(objective_code)
            next_review = obj.memory.next_review_at if obj else 0.0
            uow.knowledge.save(knowledge)
            uow.events.publish(self._events_for(result, student_ref, session_id, next_review, now))
            uow.commit()
        return Status.APPLIED

    def _events_for(
        self,
        result: AttemptResult,
        student_ref: str,
        session_id: str,
        next_review_at: float,
        now: float,
    ) -> list[LearningEvent]:
        events: list[LearningEvent] = [
            ev.interaction_recorded(session_id, result.objective_code, result.outcome.value, now)
        ]
        for ref in result.confirmed_misconceptions:
            events.append(ev.misconception_detected(student_ref, result.objective_code, ref, now))
        for ref in result.cleared_misconceptions:
            events.append(ev.misconception_cleared(student_ref, result.objective_code, ref, now))
        if result.newly_mastered:
            events.append(ev.objective_mastered(student_ref, result.objective_code, now))
            events.append(
                ev.review_scheduled(student_ref, result.objective_code, next_review_at, now)
            )
        return events


def _gradable_item(lesson: LessonView, item_ref: str) -> ItemView | None:
    """Find an auto-gradable item by ref. Summative is excluded (mentor-mediated, never auto)."""
    pools = (lesson.practice_items, lesson.homework_items, lesson.assessment_formative)
    for pool in pools:
        for item in pool:
            if item.item_ref == item_ref:
                return item
    return None


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) else default


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
