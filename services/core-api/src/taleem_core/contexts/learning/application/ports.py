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
from ..domain.progression import GradePath
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


@runtime_checkable
class PublishedLessonFingerprints(Protocol):
    """Optional, cheap companion to ``CurriculumReadModel.published_lessons``.

    ``(lesson_id, fingerprint)`` per published lesson, in the same order; a fingerprint changes
    whenever that lesson's stored content or state changes. Lets a consumer cache content derived
    from a lesson (signed offline manifests) without re-reading every lesson on every request.
    """

    def published_fingerprints(self) -> list[tuple[str, str]]: ...


@runtime_checkable
class PublishedTitles(Protocol):
    """Optional companion to ``CurriculumReadModel``: the learner-facing lesson title per objective.

    ``{objective_code: {locale: text}}`` for the lessons the current reader may see (the same
    cohort filtering and preference as ``lesson_for``: the title is the lesson that code teaches).
    Titles only — no items, answers or other content.
    """

    def published_titles(self) -> dict[str, dict[str, str]]: ...


@runtime_checkable
class ProgressionCurriculum(Protocol):
    """The published path of a grade and single-lesson lookups (PROGRESSION_AND_EXAMINATION
    _CONTRACT §1). Cohort-filtered exactly like ``lesson_for``: a real reader never receives a
    demo lesson, so never a unit made only of demo lessons."""

    def grade_path(self, grade_key: str) -> GradePath: ...
    def lesson_view(self, lesson_id: str) -> LessonView | None: ...


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
    evidence_id: str = ""
    lesson_id: str = ""  # "" / None: not recorded (rows before migration 0015)
    lesson_version: int | None = None


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
