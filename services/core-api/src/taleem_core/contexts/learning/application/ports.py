"""Application ports for the learning context (Clean Architecture — LEARNING_DOMAIN_MODEL §5).

The services depend on these interfaces; infrastructure adapters (SQLAlchemy, in-memory, curriculum
read model) implement them. Nothing in the domain or application layer imports an adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from ..domain.curriculum_view import LessonView
from ..domain.events import LearningEvent
from ..domain.knowledge import StudentKnowledge
from ..domain.session import Session


@runtime_checkable
class StudentKnowledgeRepository(Protocol):
    def get(self, student_ref: str) -> StudentKnowledge | None: ...
    def save(self, knowledge: StudentKnowledge) -> None: ...


@runtime_checkable
class SessionRepository(Protocol):
    def get(self, session_id: str) -> Session | None: ...
    def save(self, session: Session) -> None: ...


@runtime_checkable
class CurriculumReadModel(Protocol):
    """Read-only projection of published curriculum (fed by LessonPublished in production)."""

    def lesson_for(self, objective_code: str) -> LessonView | None: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Transactional outbox — events commit atomically with the aggregate that produced them."""

    def publish(self, events: Sequence[LearningEvent]) -> None: ...
