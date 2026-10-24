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

Cost per delta is independent of the learner's history: the idempotency probe is one indexed
lookup of the ``evidence_id``, and the attempt loads only the knowledge root (optimistic lock) and
the one objective it updates — BKT and the forgetting model read that objective's state, never past
evidence. Within one batch (``batch()``), each objective's published lesson is resolved once.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from ...learning.domain import events as ev
from ...learning.domain.curriculum_view import ItemView, LessonView
from ...learning.domain.events import LearningEvent
from ...learning.domain.knowledge import AttemptResult, StudentKnowledge
from ...learning.domain.protocols import ForgettingModel, MasteryEstimator
from ...learning.domain.scorer import Answer, AnswerShapeError, answer_fits, evaluate
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
        # Published-lesson lookups memoised for the duration of one batch (None outside a batch).
        # A context variable, not an attribute: one consumer serves concurrent requests.
        self._batch_lessons: ContextVar[dict[str, LessonView | None] | None] = ContextVar(
            f"sync_batch_lessons_{id(self)}", default=None
        )

    @contextmanager
    def batch(self) -> Iterator[None]:
        """Scope one sync batch: each objective's published lesson is read once, not per delta.

        Content is resolved when the batch starts using it and is not carried past the batch, so a
        publish or rollback applies from the next batch on.
        """
        if self._batch_lessons.get() is not None:  # nested: the outer batch owns the memo
            yield
            return
        token = self._batch_lessons.set({})
        try:
            yield
        finally:
            self._batch_lessons.reset(token)

    def _lesson_for(self, objective_code: str) -> LessonView | None:
        memo = self._batch_lessons.get()
        if memo is None:
            return self._curriculum.lesson_for(objective_code)
        if objective_code not in memo:
            memo[objective_code] = self._curriculum.lesson_for(objective_code)
        return memo[objective_code]

    def apply_attempt(self, delta: SyncDelta) -> Status:
        """Grade + record one offline attempt. Returns applied / duplicate / ignored / conflict."""
        if delta.type is not DeltaType.ATTEMPT_SUBMITTED:
            return Status.CONFLICT  # routing error — never silently dropped

        p = delta.payload
        try:
            student_ref = str(p["student_ref"])
            objective_code = str(p["objective_code"])
            item_ref = str(p["item_ref"])
        except KeyError:
            return Status.CONFLICT  # malformed payload — surfaced, not dropped
        answer = _parse_answer(p)
        if answer is None:
            return Status.CONFLICT  # not exactly one well-typed answer field

        # Stable, client-generated idempotency key (falls back to the delta's clientEventId).
        evidence_id = str(p.get("evidence_id") or delta.client_event_id)
        session_id = str(p.get("session_id", ""))
        hints_used = _as_int(p.get("hints_used"), 0)
        response_time_ms = _as_int(p.get("response_time_ms"), 0)
        self_confidence = _as_float(p.get("self_confidence"))
        context = _CONTEXT_FOR.get(str(p.get("context", "practice")), InteractionContext.PRACTICE)

        lesson = self._lesson_for(objective_code)
        if lesson is None:
            return Status.CONFLICT  # no published content to grade against
        item = _gradable_item(lesson, item_ref)
        if item is None:
            # Either unknown, or a mentor-mediated summative item — never auto-graded by sync.
            return Status.IGNORED
        if not answer_fits(item, answer):
            return Status.CONFLICT  # the answer's shape does not fit the item's kind

        now = self._now()
        with self._uow() as uow:
            # Idempotency (durable): the evidence table is the ledger, probed by evidence_id.
            if uow.knowledge.has_evidence(student_ref, evidence_id):
                return Status.DUPLICATE
            knowledge = uow.knowledge.get_for_objectives(
                student_ref, (objective_code,)
            ) or StudentKnowledge(student_ref=student_ref)

            outcome, misconception_hits = evaluate(item, answer)
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


def _parse_answer(payload: dict[str, object]) -> Answer | None:
    """The delta's answer: exactly one of ``option`` | ``text`` | ``order`` | ``pairs``.

    ``option`` may also arrive as a numeric string (pre-contract clients).
    """
    fields = dict(payload)
    raw = fields.get("option")
    if isinstance(raw, str):
        try:
            fields["option"] = int(raw)
        except ValueError:
            return None
    try:
        return Answer.from_payload(fields)
    except AnswerShapeError:
        return None


def _as_int(value: object, default: int) -> int:
    return value if isinstance(value, int) else default


def _as_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None
