"""Learning Analytics projector (LEARNING_ANALYTICS.md) — derived from persisted events + evidence.

For the vertical slice this reads the learning store directly to produce a per-learner progress
summary. In production the same metrics are computed in the warehouse from the event stream; the
shape of the summary is identical, so the consumer contract is proven here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import String, and_, case, cast, func, or_, select

from ..adapters.persistence.models import (
    AssessmentEvidenceRow,
    LearningOutboxRow,
    ObjectiveMasteryRow,
)
from ..adapters.persistence.uow import LearningUnitOfWork


@dataclass
class ProgressSummary:
    student_ref: str
    objectives_mastered: int
    objectives_in_progress: int
    total_attempts: int
    accuracy: float
    misconceptions_detected: int
    misconceptions_cleared: int
    reviews_scheduled: int
    events_by_type: dict[str, int] = field(default_factory=dict)
    objective_mastery: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_ref": self.student_ref,
            "objectives_mastered": self.objectives_mastered,
            "objectives_in_progress": self.objectives_in_progress,
            "total_attempts": self.total_attempts,
            "accuracy": round(self.accuracy, 3),
            "misconceptions_detected": self.misconceptions_detected,
            "misconceptions_cleared": self.misconceptions_cleared,
            "reviews_scheduled": self.reviews_scheduled,
            "events_by_type": self.events_by_type,
            "objective_mastery": {k: round(v, 3) for k, v in self.objective_mastery.items()},
        }


class LearningAnalytics:
    def __init__(self, uow_factory: Callable[[], LearningUnitOfWork]) -> None:
        self._uow = uow_factory

    def progress_summary(self, student_ref: str) -> ProgressSummary:
        with self._uow() as uow:
            session = uow.session
            objectives = list(
                session.execute(
                    select(ObjectiveMasteryRow).where(
                        ObjectiveMasteryRow.student_ref == student_ref
                    )
                ).scalars()
            )
            total, correct = session.execute(
                select(
                    func.count(),
                    func.coalesce(
                        func.sum(case((AssessmentEvidenceRow.outcome == "correct", 1), else_=0)), 0
                    ),
                ).where(AssessmentEvidenceRow.student_ref == student_ref)
            ).one()
            # Only THIS learner's events. Knowledge events (mastered, misconceptions, reviews) are
            # keyed by the learner's ref; session events by session id. A learner's sessions are
            # the ones whose SessionStarted payload names them (exact match, so stu_1 never matches
            # stu_10). Counting the whole outbox leaked other learners' activity into every
            # learner's progress (found by the load tests' query review).
            started = session.execute(
                select(LearningOutboxRow.aggregate_id, LearningOutboxRow.payload).where(
                    LearningOutboxRow.event_type == "SessionStarted",
                    cast(LearningOutboxRow.payload, String).contains(student_ref, autoescape=True),
                )
            ).all()
            session_ids = {
                str(sid)
                for sid, payload in started
                if isinstance(payload, dict) and payload.get("student_ref") == student_ref
            }
            event_rows = session.execute(
                select(LearningOutboxRow.event_type, func.count())
                .where(
                    or_(
                        LearningOutboxRow.aggregate_id == student_ref,
                        and_(
                            LearningOutboxRow.aggregate_type == "session",
                            LearningOutboxRow.aggregate_id.in_(session_ids),
                        ),
                    )
                )
                .group_by(LearningOutboxRow.event_type)
            ).all()

        events_by_type: dict[str, int] = {str(etype): int(count) for etype, count in event_rows}
        total = int(total or 0)
        correct = int(correct or 0)
        return ProgressSummary(
            student_ref=student_ref,
            objectives_mastered=sum(1 for o in objectives if o.state == "mastered"),
            objectives_in_progress=sum(1 for o in objectives if o.state == "in_progress"),
            total_attempts=total,
            accuracy=(correct / total) if total else 0.0,
            misconceptions_detected=events_by_type.get("MisconceptionDetected", 0),
            misconceptions_cleared=events_by_type.get("MisconceptionCleared", 0),
            reviews_scheduled=events_by_type.get("ReviewScheduled", 0),
            events_by_type=events_by_type,
            objective_mastery={o.objective_code: o.mastery_value for o in objectives},
        )
