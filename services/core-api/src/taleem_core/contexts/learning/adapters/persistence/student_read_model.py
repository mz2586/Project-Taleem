"""Read-only student query adapter (implements StudentReadModel).

Derives everything the student-facing query surface needs from data the learning context already
persists — the Student Knowledge Model, immutable assessment evidence, and the outbox — so no new
child-data tables are introduced (governance-safe). Pure reads; never mutates.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...application.ports import EventRow, EvidenceRow, ObjectiveStateRow
from .models import AssessmentEvidenceRow, LearningOutboxRow, ObjectiveMasteryRow

_ACTIVE_MISCONCEPTION = {"suspected", "confirmed", "being_remediated", "recurred"}


class SqlAlchemyStudentReadModel:
    def __init__(self, session: Session) -> None:
        self._session = session

    def objective_states(self, student_ref: str) -> list[ObjectiveStateRow]:
        rows = self._session.execute(
            select(ObjectiveMasteryRow).where(ObjectiveMasteryRow.student_ref == student_ref)
        ).scalars()
        out: list[ObjectiveStateRow] = []
        for r in rows:
            memory = r.memory or {}
            active = tuple(
                str(m.get("misconception_ref"))
                for m in (r.misconceptions or [])
                if m.get("state") in _ACTIVE_MISCONCEPTION
            )
            out.append(
                ObjectiveStateRow(
                    objective_code=r.objective_code,
                    state=r.state,
                    mastery=r.mastery_value,
                    uncertainty=r.mastery_uncertainty,
                    next_review_at=r.next_review_at,
                    last_seen_at=float(memory.get("last_seen_at", 0.0)),
                    attempts=r.attempts,
                    active_misconceptions=active,
                )
            )
        return out

    def evidence(self, student_ref: str) -> list[EvidenceRow]:
        rows = self._session.execute(
            select(AssessmentEvidenceRow)
            .where(AssessmentEvidenceRow.student_ref == student_ref)
            .order_by(AssessmentEvidenceRow.occurred_at)
        ).scalars()
        return [
            EvidenceRow(
                objective_code=r.objective_code,
                item_ref=r.item_ref,
                session_id=r.session_id,
                outcome=r.outcome,
                context=r.context,
                occurred_at=r.occurred_at,
            )
            for r in rows
        ]

    def knowledge_events(self, student_ref: str) -> list[EventRow]:
        # student_knowledge events carry the student_ref as aggregate_id (ObjectiveMastered,
        # MisconceptionDetected/Cleared, ReviewScheduled).
        rows = self._session.execute(
            select(LearningOutboxRow)
            .where(
                LearningOutboxRow.aggregate_type == "student_knowledge",
                LearningOutboxRow.aggregate_id == student_ref,
            )
            .order_by(LearningOutboxRow.occurred_at)
        ).scalars()
        return [
            EventRow(event_type=r.event_type, payload=r.payload or {}, occurred_at=r.occurred_at)
            for r in rows
        ]
