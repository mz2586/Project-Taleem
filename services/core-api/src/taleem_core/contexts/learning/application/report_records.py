"""Learning records for report cards — the learning context's side of REPORT_CARD_CONTRACT.md.

One read, exposed to the reporting context through its ``LearningRecords`` port (wired in the
composition root; reporting never imports this module): a learner's immutable assessment evidence
and the ``ObjectiveMastered`` events of their knowledge aggregate, as plain JSON-shaped dicts.
Nothing is derived here; the reporting domain decides what counts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..adapters.persistence.student_read_model import SqlAlchemyStudentReadModel
from ..adapters.persistence.uow import LearningUnitOfWork


class LearnerRecordsService:
    def __init__(self, uow_factory: Callable[[], LearningUnitOfWork]) -> None:
        self._uow = uow_factory

    def records(self, student_ref: str) -> dict[str, Any]:
        with self._uow() as uow:
            reads = SqlAlchemyStudentReadModel(uow.session)
            evidence = reads.evidence(student_ref)
            events = reads.knowledge_events(student_ref)
        return {
            "evidence": [
                {
                    "evidence_id": e.evidence_id,
                    "objective_code": e.objective_code,
                    "outcome": e.outcome,
                    "context": e.context,
                    "occurred_at": e.occurred_at,
                    # The lesson answered against; None when not recorded (never guessed).
                    "lesson_id": e.lesson_id or None,
                    "lesson_version": e.lesson_version,
                }
                for e in evidence
            ],
            "mastered": [
                {"objective_code": str(ev.payload.get("objective_code", "")), "at": ev.occurred_at}
                for ev in events
                if ev.event_type == "ObjectiveMastered"
            ],
        }
