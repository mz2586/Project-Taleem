"""The curriculum knowledge hierarchy (pure-stdlib).

Education System → Grade → Subject → Chapter → Topic (→ Lesson lives in lesson.py).
See docs/10-curriculum-studio/CURRICULUM_ARCHITECTURE.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .content import LocalizedText
from .packs import default_pack


@dataclass
class Topic:
    topic_id: str
    key: str
    title: LocalizedText


@dataclass
class Chapter:
    chapter_id: str
    key: str
    title: LocalizedText
    topics: list[Topic] = field(default_factory=list)


@dataclass
class Subject:
    subject_id: str
    key: str  # e.g. "math"
    title: LocalizedText
    chapters: list[Chapter] = field(default_factory=list)


@dataclass
class Grade:
    grade_id: str
    key: str  # a grade key of the education system's curriculum pack (PK-NCP: KG, G1..G10)
    subjects: list[Subject] = field(default_factory=list)


@dataclass
class EducationSystem:
    system_id: str
    key: str  # e.g. "PK-NCP"
    name: str
    grades: list[Grade] = field(default_factory=list)


# Grade structures and subject rosters are curriculum-pack data (packs.py, packs/*.json), not
# constants. These helpers keep the original API by delegating to the default pack (PK-NCP).


def subjects_for(grade_key: str) -> tuple[str, ...]:
    return default_pack().subjects_for(grade_key)


def is_valid_grade_subject(grade_key: str, subject_key: str) -> bool:
    return default_pack().is_valid_grade_subject(grade_key, subject_key)


def __getattr__(name: str) -> object:
    # Lazy compatibility for the former module constants (now the default pack's data).
    if name == "GRADE_KEYS":
        return default_pack().grade_keys
    if name == "SUBJECT_ROSTER":
        return dict(default_pack().subject_roster)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
