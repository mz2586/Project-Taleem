"""SQLAlchemy implementations of the LessonRepository and PublishPort ports.

These replace the in-memory adapters (``application/repository.py``) behind the *same* Protocol, so
the application service is unchanged. The repository persists the whole Lesson aggregate (root
columns + body + append-only versions/transitions + current-head gate rows) and reconstitutes a
faithful domain object on load. All writes go through a ``UnitOfWork`` session and commit atomically
with the audit + outbox rows it emits.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .....platform.ids import uuid7
from ...domain.lesson import Lesson
from ...domain.versioning import Version
from . import mapper
from .models import (
    EducationSystemRow,
    LessonRow,
    LessonVersionRow,
    QualityGateResultRow,
    WorkflowTransitionRow,
)

if TYPE_CHECKING:
    from .uow import UnitOfWork

# In this governance-safe phase every lesson belongs to the single NCP national curriculum. New
# education systems (provincial/international variants) are added as rows without any schema change
# (architecture §1); the repository resolves this default lazily.
DEFAULT_SYSTEM_KEY = "NCP-2023-NATIONAL"


class SqlAlchemyLessonRepository:
    """Persist/reconstruct the Lesson aggregate (the ``LessonRepository`` port)."""

    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow
        self._system_id: str | None = None

    # -- port surface ---------------------------------------------------------------------

    def save(self, lesson: Lesson) -> None:
        system_id = self._default_system_id()
        row = self._get_row(lesson.lesson_id)
        cols = mapper.column_values(lesson)
        is_new = row is None

        if row is None:
            row = LessonRow(id=uuid7(), system_id=system_id, **cols)
            self._session.add(row)
        else:
            for key, value in cols.items():
                setattr(row, key, value)

        # Current-head gate results are mutable. Reconcile in place keyed on ``gate`` (the unique
        # column) — updating existing rows and adding/removing deltas — rather than replacing the
        # whole collection, which would violate uq_gate_per_lesson mid-flush (insert-before-delete).
        existing_gates = {g.gate: g for g in row.gates}
        desired_gates = {g.gate.value: g for g in lesson.quality_gate_results}
        for gate_key, result in desired_gates.items():
            values = mapper.gate_values(result)
            current = existing_gates.get(gate_key)
            if current is None:
                row.gates.append(QualityGateResultRow(id=uuid7(), lesson_id=row.id, **values))
            else:
                for field_name, value in values.items():
                    setattr(current, field_name, value)
        for gate_key, current in existing_gates.items():
            if gate_key not in desired_gates:
                row.gates.remove(current)
        # Workflow transitions are append-only → append only the newly-recorded tail.
        existing_transitions = len(row.transitions)
        for record in lesson.workflow.history[existing_transitions:]:
            row.transitions.append(
                WorkflowTransitionRow(
                    id=uuid7(), lesson_id=row.id, **mapper.transition_values(record)
                )
            )
        # Published versions are immutable → append only versions not already stored.
        stored_versions = {v.version_no for v in row.versions}
        for version in lesson.version_history.versions:
            if version.version not in stored_versions:
                row.versions.append(
                    LessonVersionRow(id=uuid7(), lesson_id=row.id, **mapper.version_values(version))
                )

        self._uow.record_audit(
            entity_type="lesson",
            entity_id=row.id,
            action="create" if is_new else "update",
            actor_role=lesson.metadata.author_role,
            after={
                "state": row.state,
                "content_hash": row.content_hash,
                "version": row.current_version_no,
            },
        )

    def get(self, lesson_id: str) -> Lesson | None:
        row = self._get_row(lesson_id, eager=True)
        return mapper.from_row(row) if row is not None else None

    def all(self) -> list[Lesson]:
        rows = self._session.execute(
            select(LessonRow)
            .where(LessonRow.deleted_at.is_(None))
            .options(
                selectinload(LessonRow.gates),
                selectinload(LessonRow.transitions),
                selectinload(LessonRow.versions),
            )
            .order_by(LessonRow.updated_at.desc())
        ).scalars()
        return [mapper.from_row(row) for row in rows]

    # -- internals ------------------------------------------------------------------------

    def _get_row(self, lesson_id: str, *, eager: bool = False) -> LessonRow | None:
        stmt = select(LessonRow).where(
            LessonRow.lesson_key == lesson_id,
            LessonRow.system_id == self._default_system_id(),
        )
        if eager:
            stmt = stmt.options(
                selectinload(LessonRow.gates),
                selectinload(LessonRow.transitions),
                selectinload(LessonRow.versions),
            )
        return self._session.execute(stmt).scalar_one_or_none()

    def _default_system_id(self) -> str:
        if self._system_id is not None:
            return self._system_id
        row = self._session.execute(
            select(EducationSystemRow).where(EducationSystemRow.system_key == DEFAULT_SYSTEM_KEY)
        ).scalar_one_or_none()
        if row is None:
            row = EducationSystemRow(
                id=uuid7(),
                system_key=DEFAULT_SYSTEM_KEY,
                name="National Curriculum of Pakistan (2023)",
                jurisdiction="national",
                curriculum_version="2023",
            )
            self._session.add(row)
            self._session.flush()
        self._system_id = row.id
        return row.id


class SqlAlchemyPublishPort:
    """Emit a ``LessonPublished`` event via the outbox (approved content only)."""

    def __init__(self, session: Session, uow: UnitOfWork) -> None:
        self._session = session
        self._uow = uow

    def publish(self, lesson: Lesson, version: Version) -> None:
        row = self._session.execute(
            select(LessonRow).where(LessonRow.lesson_key == lesson.lesson_id)
        ).scalar_one_or_none()
        aggregate_id = row.id if row is not None else lesson.lesson_id
        self._uow.emit_event(
            aggregate_type="lesson",
            aggregate_id=aggregate_id,
            event_type="LessonPublished",
            payload={
                "lesson_id": lesson.lesson_id,
                "version_no": version.version,
                "content_hash": version.content_hash,
                "system_key": DEFAULT_SYSTEM_KEY,
                "grade_key": lesson.metadata.grade_key,
                "subject_key": lesson.metadata.subject_key,
                "learning_outcomes": list(lesson.learning_outcomes),
                "languages": [loc.value for loc in lesson.metadata.languages],
                "published_by": version.author_role,
            },
        )
