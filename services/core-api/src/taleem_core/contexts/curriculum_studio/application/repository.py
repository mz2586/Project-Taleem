"""Repository + publish ports and in-memory adapters (pure-stdlib).

Phase 3: in-memory only (governance-safe, no production content). The sharded-Postgres
adapter lands later behind the same port.
"""

from __future__ import annotations

import copy
from typing import Protocol, runtime_checkable

from ..domain.hierarchy import EducationSystem
from ..domain.lesson import Lesson
from ..domain.packs import CurriculumPack
from ..domain.versioning import Version


@runtime_checkable
class LessonRepository(Protocol):
    def save(self, lesson: Lesson) -> None: ...
    def get(self, lesson_id: str) -> Lesson | None: ...
    def all(self) -> list[Lesson]: ...


@runtime_checkable
class HierarchyRepository(Protocol):
    """Stores one curriculum hierarchy (EducationSystem tree) per curriculum pack."""

    def get(self, pack_id: str) -> EducationSystem | None: ...
    def save(self, system: EducationSystem, pack: CurriculumPack) -> None: ...


@runtime_checkable
class PublishPort(Protocol):
    """Emits a publish event to the Curriculum Engine + AI Knowledge Base (approved only)."""

    def publish(self, lesson: Lesson, version: Version) -> None: ...


class InMemoryLessonRepository:
    def __init__(self) -> None:
        self._store: dict[str, Lesson] = {}

    def save(self, lesson: Lesson) -> None:
        self._store[lesson.lesson_id] = lesson

    def get(self, lesson_id: str) -> Lesson | None:
        return self._store.get(lesson_id)

    def all(self) -> list[Lesson]:
        return list(self._store.values())


class InMemoryHierarchyRepository:
    def __init__(self) -> None:
        self._store: dict[str, EducationSystem] = {}

    def get(self, pack_id: str) -> EducationSystem | None:
        found = self._store.get(pack_id)
        return copy.deepcopy(found) if found is not None else None

    def save(self, system: EducationSystem, pack: CurriculumPack) -> None:
        self._store[pack.pack_id] = copy.deepcopy(system)


class RecordingPublishPort:
    """Captures publish events (for tests / local; no external side effects)."""

    def __init__(self) -> None:
        self.published: list[tuple[str, int]] = []

    def publish(self, lesson: Lesson, version: Version) -> None:
        self.published.append((lesson.lesson_id, version.version))
