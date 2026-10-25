"""Learning store: knowledge, mastery, evidence, outbox events, AI usage, unit-check sittings,
live sessions.

Durable rows come from the learning context's ORM models; live tutoring sessions (interactions and
turns) are in-process state held by its ``InMemorySessionRepository``, so they are erased there.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Protocol

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session, sessionmaker

from ...learning.adapters.persistence.models import (
    AIUsageRow,
    AssessmentEvidenceRow,
    LearningOutboxRow,
    ObjectiveMasteryRow,
    StudentKnowledgeRow,
    UnitCheckSittingRow,
)
from ..domain.policy import RetainedSet
from ._rows import affected, jsonable, mentions, row_dict, text_contains

_S = "learning"
# On PostgreSQL, migration 0002 makes ``assessment_evidence`` append-only with a trigger
# (``learning.forbid_mutation``) that refuses every DELETE. Erasure needs that function to admit a
# DELETE inside a transaction that has set this flag (``SET LOCAL``); until a migration does so,
# erasure is reported as blocked and nothing is touched.
ERASURE_GUC = "taleem.privacy_erasure"


class _SessionStore(Protocol):
    """The in-memory session repository (``learning/adapters/memory.py``)."""

    _store: OrderedDict[str, Any]


class LearningLearnerData:
    name = "learning"

    def __init__(
        self, session_factory: sessionmaker[Session], sessions: _SessionStore | None = None
    ) -> None:
        self._sf = session_factory
        self._sessions = sessions

    def covers(self) -> tuple[str, ...]:
        return (
            f"{_S}.student_knowledge",
            f"{_S}.objective_mastery",
            f"{_S}.assessment_evidence",
            f"{_S}.learning_outbox",
            f"{_S}.ai_usage_ledger",
            f"{_S}.unit_check_sitting",
            "memory:learning.sessions",
        )

    @staticmethod
    def _outbox(s: Session, ref: str) -> list[LearningOutboxRow]:
        rows = s.scalars(
            select(LearningOutboxRow).where(
                or_(
                    LearningOutboxRow.aggregate_id == ref,
                    text_contains(LearningOutboxRow.payload, ref),
                )
            )
        ).all()
        return [r for r in rows if r.aggregate_id == ref or mentions(r.payload, ref)]

    def _live_sessions(self, ref: str) -> list[tuple[str, Any]]:
        if self._sessions is None:
            return []
        return [
            (sid, sess)
            for sid, sess in list(self._sessions._store.items())
            if getattr(sess, "student_ref", None) == ref
        ]

    def export(self, student_ref: str) -> dict[str, Any]:
        with self._sf() as s:
            knowledge = s.scalars(
                select(StudentKnowledgeRow).where(StudentKnowledgeRow.student_ref == student_ref)
            ).all()
            mastery = s.scalars(
                select(ObjectiveMasteryRow).where(ObjectiveMasteryRow.student_ref == student_ref)
            ).all()
            evidence = s.scalars(
                select(AssessmentEvidenceRow)
                .where(AssessmentEvidenceRow.student_ref == student_ref)
                .order_by(AssessmentEvidenceRow.occurred_at)
            ).all()
            return {
                "student_knowledge": [row_dict(r) for r in knowledge],
                "objective_mastery": [row_dict(r) for r in mastery],
                "assessment_evidence": [row_dict(r) for r in evidence],
                "events": [row_dict(r) for r in self._outbox(s, student_ref)],
                "ai_usage": [
                    row_dict(r)
                    for r in s.scalars(
                        select(AIUsageRow)
                        .where(AIUsageRow.learner_ref == student_ref)
                        .order_by(AIUsageRow.recorded_at)
                    ).all()
                ],
                # Unit-check sittings (C2): the paper (refs only), the learner's answers and
                # outcomes, and the score (PROGRESSION_AND_EXAMINATION_CONTRACT §4).
                "unit_check_sittings": [
                    row_dict(r)
                    for r in s.scalars(
                        select(UnitCheckSittingRow)
                        .where(UnitCheckSittingRow.student_ref == student_ref)
                        .order_by(UnitCheckSittingRow.started_at)
                    ).all()
                ],
                "live_sessions": [
                    jsonable(sess) for _sid, sess in self._live_sessions(student_ref)
                ],
                "withheld": [],
            }

    def _count(self, s: Session, model: Any, ref: str) -> int:
        return int(
            s.scalar(select(func.count()).select_from(model).where(model.student_ref == ref)) or 0
        )

    def remaining(self, student_ref: str) -> dict[str, int]:
        with self._sf() as s:
            return {
                "student_knowledge": self._count(s, StudentKnowledgeRow, student_ref),
                "objective_mastery": self._count(s, ObjectiveMasteryRow, student_ref),
                "assessment_evidence": self._count(s, AssessmentEvidenceRow, student_ref),
                "learning_outbox": len(self._outbox(s, student_ref)),
                "ai_usage_ledger": int(
                    s.scalar(
                        select(func.count())
                        .select_from(AIUsageRow)
                        .where(AIUsageRow.learner_ref == student_ref)
                    )
                    or 0
                ),
                "unit_check_sitting": self._count(s, UnitCheckSittingRow, student_ref),
                "sessions": len(self._live_sessions(student_ref)),
            }

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        column = {
            "learning_records": AssessmentEvidenceRow.occurred_at,
            "learning_events": LearningOutboxRow.occurred_at,
            "ai_usage": AIUsageRow.recorded_at,
        }.get(data_class)
        if column is None:
            return None
        with self._sf() as s:
            count = int(s.scalar(select(func.count()).where(column < cutoff)) or 0)
            if data_class == "learning_records":  # unit-check sittings are C2 learning records
                count += int(
                    s.scalar(select(func.count()).where(UnitCheckSittingRow.started_at < cutoff))
                    or 0
                )
            return count

    def blockers(self) -> list[str]:
        with self._sf() as s:
            if s.get_bind().dialect.name != "postgresql":
                return []
            definition = s.execute(
                text(
                    "SELECT CASE WHEN to_regproc('learning.forbid_mutation') IS NULL THEN '' "
                    "ELSE pg_get_functiondef(to_regproc('learning.forbid_mutation')) END"
                )
            ).scalar()
        if definition and ERASURE_GUC not in str(definition):
            return [
                "learning.assessment_evidence is append-only (trigger trg_evidence_immutable) and "
                f"its function does not yet admit an erasure (`{ERASURE_GUC}`); a migration is "
                "required before erasure can run on PostgreSQL"
            ]
        return []

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        with self._sf() as s, s.begin():
            if s.get_bind().dialect.name == "postgresql":
                s.execute(text(f"SET LOCAL {ERASURE_GUC} = 'on'"))
            mastery = s.execute(
                delete(ObjectiveMasteryRow).where(ObjectiveMasteryRow.student_ref == student_ref)
            )
            knowledge = s.execute(
                delete(StudentKnowledgeRow).where(StudentKnowledgeRow.student_ref == student_ref)
            )
            evidence = s.execute(
                delete(AssessmentEvidenceRow).where(
                    AssessmentEvidenceRow.student_ref == student_ref
                )
            )
            usage = s.execute(delete(AIUsageRow).where(AIUsageRow.learner_ref == student_ref))
            sittings = s.execute(
                delete(UnitCheckSittingRow).where(UnitCheckSittingRow.student_ref == student_ref)
            )
            events = self._outbox(s, student_ref)
            for row in events:
                s.delete(row)
        live = self._live_sessions(student_ref)
        if self._sessions is not None:
            for sid, _sess in live:
                self._sessions._store.pop(sid, None)
        return {
            "student_knowledge": affected(knowledge),
            "objective_mastery": affected(mastery),
            "assessment_evidence": affected(evidence),
            "learning_outbox": len(events),
            "ai_usage_ledger": affected(usage),
            "unit_check_sitting": affected(sittings),
            "sessions": len(live),
        }
