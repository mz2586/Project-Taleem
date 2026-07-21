"""KnowledgeService — records interactions and updates the Student Knowledge Model (one UoW each).

Every attempt: update mastery/misconceptions/memory (via the aggregate + injected science models),
persist the aggregate + immutable evidence, and emit the resulting domain events to the outbox —
all atomically (LEARNING_DOMAIN_MODEL §7).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ....platform.ids import uuid7
from ...learning.domain import events as ev
from ...learning.domain.events import LearningEvent
from ...learning.domain.knowledge import AttemptResult, StudentKnowledge
from ...learning.domain.protocols import ForgettingModel, MasteryEstimator
from ...learning.domain.values import InteractionContext
from ..adapters.persistence.uow import LearningUnitOfWork


@dataclass
class RecordOutcome:
    result: AttemptResult
    events: list[LearningEvent]


class KnowledgeService:
    def __init__(
        self,
        uow_factory: Callable[[], LearningUnitOfWork],
        estimator: MasteryEstimator,
        forgetting: ForgettingModel,
        clock: Callable[[], float],
    ) -> None:
        self._uow = uow_factory
        self._estimator = estimator
        self._forgetting = forgetting
        self._now = clock

    def ensure_student(self, student_ref: str, objective_codes: list[str]) -> None:
        """Cold-start a learner: initialize objectives at the prior (high uncertainty)."""
        with self._uow() as uow:
            knowledge = uow.knowledge.get(student_ref) or StudentKnowledge(student_ref=student_ref)
            for code in objective_codes:
                knowledge.ensure_objective(code, initial=self._estimator.initial())
            uow.knowledge.save(knowledge)
            uow.commit()

    def snapshot(self, student_ref: str) -> StudentKnowledge | None:
        with self._uow() as uow:
            return uow.knowledge.get(student_ref)

    def record_attempt(
        self,
        *,
        student_ref: str,
        objective_code: str,
        item_ref: str,
        session_id: str,
        correct: bool,
        misconception_hits: tuple[str, ...],
        hints_used: int,
        response_time_ms: int,
        context: InteractionContext,
        self_confidence: float | None,
    ) -> RecordOutcome:
        now = self._now()
        with self._uow() as uow:
            knowledge = uow.knowledge.get(student_ref) or StudentKnowledge(student_ref=student_ref)
            knowledge.ensure_objective(objective_code, initial=self._estimator.initial())
            result = knowledge.apply_attempt(
                evidence_id=uuid7(),
                objective_code=objective_code,
                item_ref=item_ref,
                session_id=session_id,
                correct=correct,
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
            events = self._events_for(result, student_ref, session_id, next_review, now)
            uow.knowledge.save(knowledge)
            uow.events.publish(events)
            uow.commit()
        return RecordOutcome(result=result, events=events)

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
