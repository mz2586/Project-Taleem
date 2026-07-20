"""The curriculum knowledge hierarchy (pure-stdlib).

Education System → Grade → Subject → Chapter → Topic (→ Lesson lives in lesson.py).
See docs/10-curriculum-studio/CURRICULUM_ARCHITECTURE.md §3.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .content import LocalizedText


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
    key: str  # KG, G1..G10
    subjects: list[Subject] = field(default_factory=list)


@dataclass
class EducationSystem:
    system_id: str
    key: str  # e.g. "PK-NCP"
    name: str
    grades: list[Grade] = field(default_factory=list)


# The canonical NCP grade keys and the verified subject roster per grade band
# (see curriculum-research/02_MASTER_CURRICULUM_MATRIX.md). Roster is data, not hardcoded.
GRADE_KEYS: tuple[str, ...] = ("KG", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")

SUBJECT_ROSTER: dict[str, tuple[str, ...]] = {
    "KG": ("ece",),
    "G1": ("urdu", "english", "math", "gk"),
    "G2": ("urdu", "english", "math", "gk"),
    "G3": ("urdu", "english", "math", "gk", "islamiat_ethics"),
    "G4": ("urdu", "english", "math", "science", "social_studies", "islamiat_ethics"),
    "G5": ("urdu", "english", "math", "science", "social_studies", "islamiat_ethics"),
    "G6": ("urdu", "english", "math", "science", "social_studies", "islamiat_ethics", "computer"),
    "G7": ("urdu", "english", "math", "science", "social_studies", "islamiat_ethics", "computer"),
    "G8": ("urdu", "english", "math", "science", "social_studies", "islamiat_ethics", "computer"),
    "G9": (
        "urdu",
        "english",
        "math",
        "physics",
        "chemistry",
        "biology",
        "pak_studies",
        "islamiat_ethics",
    ),
    "G10": (
        "urdu",
        "english",
        "math",
        "physics",
        "chemistry",
        "biology",
        "pak_studies",
        "islamiat_ethics",
    ),
}


def subjects_for(grade_key: str) -> tuple[str, ...]:
    return SUBJECT_ROSTER.get(grade_key, ())


def is_valid_grade_subject(grade_key: str, subject_key: str) -> bool:
    return subject_key in SUBJECT_ROSTER.get(grade_key, ())
