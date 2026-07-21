"""SQLAlchemy StudentKnowledge repository (implements StudentKnowledgeRepository port).

Persists the aggregate root + owned objective-mastery rows (reconciled in place) + immutable
append-only assessment evidence. Optimistic-locked via the root's ``lock_version``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .....platform.ids import uuid7
from ...domain.knowledge import StudentKnowledge
from . import mapper
from .models import AssessmentEvidenceRow, ObjectiveMasteryRow, StudentKnowledgeRow


class SqlAlchemyStudentKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, student_ref: str) -> StudentKnowledge | None:
        root = self._session.execute(
            select(StudentKnowledgeRow)
            .where(StudentKnowledgeRow.student_ref == student_ref)
            .options(selectinload(StudentKnowledgeRow.objectives))
        ).scalar_one_or_none()
        if root is None:
            return None
        evidence = list(
            self._session.execute(
                select(AssessmentEvidenceRow).where(
                    AssessmentEvidenceRow.student_ref == student_ref
                )
            ).scalars()
        )
        return mapper.knowledge_from_rows(root, list(root.objectives), evidence)

    def save(self, knowledge: StudentKnowledge) -> None:
        root = self._session.execute(
            select(StudentKnowledgeRow)
            .where(StudentKnowledgeRow.student_ref == knowledge.student_ref)
            .options(selectinload(StudentKnowledgeRow.objectives))
        ).scalar_one_or_none()
        if root is None:
            root = StudentKnowledgeRow(id=uuid7(), student_ref=knowledge.student_ref)
            self._session.add(root)

        # Reconcile objective-mastery rows in place (keyed on objective_code).
        existing = {o.objective_code: o for o in root.objectives}
        for code, obj in knowledge.objectives.items():
            values = mapper.objective_column_values(obj)
            current = existing.get(code)
            if current is None:
                root.objectives.append(
                    ObjectiveMasteryRow(
                        id=uuid7(),
                        knowledge_id=root.id,
                        student_ref=knowledge.student_ref,
                        **values,
                    )
                )
            else:
                for field_name, value in values.items():
                    setattr(current, field_name, value)

        # Append only new immutable evidence rows.
        stored_ids = set(
            self._session.execute(
                select(AssessmentEvidenceRow.id).where(
                    AssessmentEvidenceRow.student_ref == knowledge.student_ref
                )
            ).scalars()
        )
        for ev in knowledge.evidence:
            if ev.evidence_id not in stored_ids:
                self._session.add(AssessmentEvidenceRow(**mapper.evidence_column_values(ev)))
