"""SQLAlchemy StudentKnowledge repository (implements StudentKnowledgeRepository port).

Persists the aggregate root + owned objective-mastery rows (reconciled in place) + immutable
append-only assessment evidence. Optimistic-locked via the root's ``lock_version``.

Reads come in sizes, so a write path never pays for a learner's whole history:

- ``get`` hydrates the full aggregate, evidence included (or without evidence on request);
- ``get_for_objectives`` hydrates the root and only the named objectives, no evidence — all an
  attempt needs (BKT and the forgetting model read the objective's own state, never past evidence);
- ``has_evidence`` is the indexed idempotency probe for one ``evidence_id``.

``save`` touches only the objectives the aggregate holds and inserts only evidence this repository
did not load, so its cost does not grow with the learner's history either.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.attributes import flag_modified

from .....platform.ids import uuid7
from ...domain.knowledge import StudentKnowledge
from . import mapper
from .models import AssessmentEvidenceRow, ObjectiveMasteryRow, StudentKnowledgeRow


class SqlAlchemyStudentKnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        # Evidence ids known to be stored, per learner, as hydrated or written through this
        # repository. ``save`` skips these without asking the database again (evidence is
        # immutable and append-only).
        self._known_evidence: dict[str, set[str]] = {}

    def get(self, student_ref: str, *, include_evidence: bool = True) -> StudentKnowledge | None:
        root = self._session.execute(
            select(StudentKnowledgeRow)
            .where(StudentKnowledgeRow.student_ref == student_ref)
            .options(selectinload(StudentKnowledgeRow.objectives))
        ).scalar_one_or_none()
        if root is None:
            return None
        evidence: list[AssessmentEvidenceRow] = []
        if include_evidence:
            evidence = list(
                self._session.execute(
                    select(AssessmentEvidenceRow).where(
                        AssessmentEvidenceRow.student_ref == student_ref
                    )
                ).scalars()
            )
        self._known_evidence.setdefault(student_ref, set()).update(e.id for e in evidence)
        return mapper.knowledge_from_rows(root, list(root.objectives), evidence)

    def get_for_objectives(
        self, student_ref: str, objective_codes: Iterable[str]
    ) -> StudentKnowledge | None:
        """The root plus only the named objectives, without evidence (the attempt write path).

        A partial aggregate is safe to ``save``: objectives it does not hold are left untouched,
        and only the evidence it appends is inserted. The root is loaded, so optimistic locking
        works exactly as for a full aggregate.
        """
        root = self._session.execute(
            select(StudentKnowledgeRow).where(StudentKnowledgeRow.student_ref == student_ref)
        ).scalar_one_or_none()
        if root is None:
            return None
        codes = sorted(set(objective_codes))
        rows: list[ObjectiveMasteryRow] = []
        if codes:
            rows = list(
                self._session.execute(
                    select(ObjectiveMasteryRow).where(
                        ObjectiveMasteryRow.student_ref == student_ref,
                        ObjectiveMasteryRow.objective_code.in_(codes),
                    )
                ).scalars()
            )
        return mapper.knowledge_from_rows(root, rows, [])

    def has_evidence(self, student_ref: str, evidence_id: str) -> bool:
        """Durable idempotency probe: is this learner's ``evidence_id`` already recorded?"""
        found = self._session.execute(
            select(AssessmentEvidenceRow.id).where(
                AssessmentEvidenceRow.id == evidence_id,
                AssessmentEvidenceRow.student_ref == student_ref,
            )
        ).first()
        return found is not None

    def objective_progress(
        self, student_refs: Iterable[str], objective_code: str, *, since: float
    ) -> dict[str, dict[str, object]]:
        """One objective's progress for many learners in three queries (teacher class reads).

        Keyed by learner, for learners that have a knowledge root (others are absent):
        ``{"mastery": float | None, "state": str | None, "attempts_since": int}``. ``mastery`` and
        ``state`` are None when the learner has no row for this objective; ``attempts_since``
        counts evidence on the objective at or after ``since``.
        """
        refs = sorted({r for r in student_refs if r})
        if not refs:
            return {}
        known = sorted(
            set(
                self._session.execute(
                    select(StudentKnowledgeRow.student_ref).where(
                        StudentKnowledgeRow.student_ref.in_(refs)
                    )
                ).scalars()
            )
        )
        if not known:
            return {}
        objectives: dict[str, tuple[float, str]] = {
            str(ref): (float(value), str(state))
            for ref, value, state in self._session.execute(
                select(
                    ObjectiveMasteryRow.student_ref,
                    ObjectiveMasteryRow.mastery_value,
                    ObjectiveMasteryRow.state,
                ).where(
                    ObjectiveMasteryRow.student_ref.in_(known),
                    ObjectiveMasteryRow.objective_code == objective_code,
                )
            )
        }
        counts: dict[str, int] = {
            str(ref): int(n)
            for ref, n in self._session.execute(
                select(AssessmentEvidenceRow.student_ref, func.count())
                .where(
                    AssessmentEvidenceRow.student_ref.in_(known),
                    AssessmentEvidenceRow.objective_code == objective_code,
                    AssessmentEvidenceRow.occurred_at >= since,
                )
                .group_by(AssessmentEvidenceRow.student_ref)
            )
        }
        out: dict[str, dict[str, object]] = {}
        for ref in known:
            obj = objectives.get(ref)
            out[ref] = {
                "mastery": obj[0] if obj is not None else None,
                "state": obj[1] if obj is not None else None,
                "attempts_since": counts.get(ref, 0),
            }
        return out

    def save(self, knowledge: StudentKnowledge) -> None:
        root = self._session.execute(
            select(StudentKnowledgeRow).where(
                StudentKnowledgeRow.student_ref == knowledge.student_ref
            )
        ).scalar_one_or_none()
        is_new_root = root is None
        if root is None:
            root = StudentKnowledgeRow(id=uuid7(), student_ref=knowledge.student_ref)
            self._session.add(root)

        # Reconcile objective-mastery rows in place (keyed on objective_code). Only the objectives
        # this aggregate holds are read and written; the learner's other objectives are untouched.
        codes = sorted(knowledge.objectives)
        existing: dict[str, ObjectiveMasteryRow] = {}
        if codes and not is_new_root:
            existing = {
                o.objective_code: o
                for o in self._session.execute(
                    select(ObjectiveMasteryRow).where(
                        ObjectiveMasteryRow.student_ref == knowledge.student_ref,
                        ObjectiveMasteryRow.objective_code.in_(codes),
                    )
                ).scalars()
            }
        for code in codes:
            values = mapper.objective_column_values(knowledge.objectives[code])
            current = existing.get(code)
            if current is None:
                # Appended through the relationship (delete-orphan needs the parent link). For an
                # existing root this loads its objective list once — bounded by the curriculum,
                # and only when the learner meets a new objective.
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

        # Append only new immutable evidence rows. Evidence this repository loaded or wrote is
        # already stored; anything else is checked against the table by id (one indexed query).
        known = self._known_evidence.setdefault(knowledge.student_ref, set())
        candidates = [ev for ev in knowledge.evidence if ev.evidence_id not in known]
        if candidates:
            stored = set(
                self._session.execute(
                    select(AssessmentEvidenceRow.id).where(
                        AssessmentEvidenceRow.student_ref == knowledge.student_ref,
                        AssessmentEvidenceRow.id.in_([ev.evidence_id for ev in candidates]),
                    )
                ).scalars()
            )
            for ev in candidates:
                if ev.evidence_id not in stored:
                    self._session.add(AssessmentEvidenceRow(**mapper.evidence_column_values(ev)))
                    stored.add(ev.evidence_id)
                known.add(ev.evidence_id)

        # Optimistic locking (CTO H6): a save mutates only child rows, so the versioned root would
        # never be UPDATEd and `version_id_col` would stay dormant. Force the root into the UPDATE
        # so `lock_version` bumps and concurrent writers to one learner collide (StaleDataError).
        # A brand-new root is INSERTed anyway (a concurrent creator hits the unique constraint).
        if is_new_root:
            return
        if "updated_at" in inspect(root).unloaded:
            _ = root.updated_at  # server-generated and expired by an earlier flush: load it
        flag_modified(root, "updated_at")
