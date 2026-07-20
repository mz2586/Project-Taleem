"""The Lesson aggregate (pure-stdlib) — the atomic authored unit.

Full field set per docs/10-curriculum-studio/CURRICULUM_DATA_MODEL.md §3 and LESSON_STANDARD.md.
Imports only leaf domain modules (no import cycle).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .ai_teaching import AITeachingObject
from .assessment import AssessmentBlueprint, AssessmentItem
from .content import (
    Difficulty,
    Hint,
    Locale,
    LocalizedText,
    MediaRef,
    Misconception,
    VocabularyTerm,
    WorkedExample,
)
from .provenance import Provenance
from .quality import GateResult
from .versioning import VersionHistory
from .workflow import Workflow


@dataclass
class Metadata:
    grade_key: str  # KG..G10
    subject_key: str  # math, urdu, ...
    languages: list[Locale] = field(default_factory=lambda: [Locale.UR, Locale.EN])
    author_role: str = "subject_author"
    tags: list[str] = field(default_factory=list)


@dataclass
class RemediationRoute:
    signal: str  # e.g. "misses_prerequisite:MATH-G1-N-00"
    remediation_ref: str  # objective/lesson to route to (down the DAG)


@dataclass
class Lesson:
    """The complete lesson object. Rich prose fields are LocalizedText (structure over content)."""

    lesson_id: str
    title: LocalizedText
    metadata: Metadata
    provenance: Provenance
    ai_teaching_object: AITeachingObject
    assessment: AssessmentBlueprint

    description: LocalizedText = field(default_factory=LocalizedText)
    learning_outcomes: list[str] = field(default_factory=list)  # SLO codes
    prerequisites: list[str] = field(default_factory=list)  # SLO codes
    estimated_duration_min: int = 15
    difficulty: Difficulty = Difficulty.INTRO
    keywords: list[str] = field(default_factory=list)
    vocabulary: list[VocabularyTerm] = field(default_factory=list)
    teacher_script: LocalizedText = field(default_factory=LocalizedText)
    student_explanation: LocalizedText = field(default_factory=LocalizedText)
    worked_examples: list[WorkedExample] = field(default_factory=list)
    visual_concepts: list[MediaRef] = field(default_factory=list)
    interactive_activities: list[AssessmentItem] = field(default_factory=list)
    practice_questions: list[AssessmentItem] = field(default_factory=list)
    hints: list[Hint] = field(default_factory=list)
    common_misconceptions: list[Misconception] = field(default_factory=list)
    adaptive_remediation: list[RemediationRoute] = field(default_factory=list)
    challenge_problems: list[AssessmentItem] = field(default_factory=list)
    homework: list[AssessmentItem] = field(default_factory=list)
    revision_notes: LocalizedText = field(default_factory=LocalizedText)
    summary: LocalizedText = field(default_factory=LocalizedText)
    parent_notes: LocalizedText = field(default_factory=LocalizedText)
    mentor_notes: LocalizedText = field(default_factory=LocalizedText)
    accessibility_notes: LocalizedText = field(default_factory=LocalizedText)
    offline_package: str = ""

    workflow: Workflow = field(default_factory=Workflow)
    quality_gate_results: list[GateResult] = field(default_factory=list)
    version: int = 0
    version_history: VersionHistory = field(default_factory=VersionHistory)

    def to_dict(self) -> dict[str, Any]:
        """Deterministic serialization (enums → their string value) for hashing/snapshot/API."""
        return dataclasses.asdict(self)

    def content_hash(self) -> str:
        # Hash only the content fields (exclude mutable workflow/version bookkeeping).
        payload = self.to_dict()
        for k in ("workflow", "quality_gate_results", "version", "version_history"):
            payload.pop(k, None)
        blob = json.dumps(payload, default=str, sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()
