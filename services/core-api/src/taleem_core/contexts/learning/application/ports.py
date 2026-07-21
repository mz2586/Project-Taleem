"""Application ports for the learning context (Clean Architecture — LEARNING_DOMAIN_MODEL §5).

The services depend on these interfaces; infrastructure adapters (SQLAlchemy, in-memory, curriculum
read model) implement them. Nothing in the domain or application layer imports an adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..domain.curriculum_view import LessonView
from ..domain.decision import CurriculumGraph
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
    def published_lessons(self) -> list[LessonView]: ...
    def published_graph(self) -> CurriculumGraph: ...


# --- read-model row DTOs for the student query surface (derived; no new child-data tables) ---


@dataclass(frozen=True)
class ObjectiveStateRow:
    objective_code: str
    state: str
    mastery: float
    uncertainty: float
    next_review_at: float
    last_seen_at: float
    attempts: int
    active_misconceptions: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceRow:
    objective_code: str
    item_ref: str
    session_id: str
    outcome: str
    context: str
    occurred_at: float


@dataclass(frozen=True)
class EventRow:
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    occurred_at: float = 0.0


@runtime_checkable
class StudentReadModel(Protocol):
    """Read-only queries over the learner's persisted data (knowledge, evidence, events)."""

    def objective_states(self, student_ref: str) -> list[ObjectiveStateRow]: ...
    def evidence(self, student_ref: str) -> list[EvidenceRow]: ...
    def knowledge_events(self, student_ref: str) -> list[EventRow]: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Transactional outbox — events commit atomically with the aggregate that produced them."""

    def publish(self, events: Sequence[LearningEvent]) -> None: ...
