"""Assessment items & tests (pure-stdlib).

See docs/10-curriculum-studio/ASSESSMENT_STANDARD.md and
docs/05-education/58-mastery-and-assessment-validity.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .content import Hint, LocalizedText


class ItemType(StrEnum):
    MCQ = "mcq"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    MATCHING = "matching"
    ORDERING = "ordering"
    SHORT = "short"
    LONG = "long"
    WORD_PROBLEM = "word_problem"
    INTERACTIVE = "interactive"


class TestType(StrEnum):
    DIAGNOSTIC = "diagnostic"
    ADAPTIVE = "adaptive"
    REVISION = "revision"
    SUMMATIVE = "summative"


class Competency(StrEnum):
    KNOWLEDGE = "knowledge"
    COMPREHENSION = "comprehension"
    APPLICATION = "application"
    ANALYSIS = "analysis"


# Item types graded automatically vs. requiring human/mentor grading.
AUTO_GRADED = {
    ItemType.MCQ,
    ItemType.TRUE_FALSE,
    ItemType.FILL_BLANK,
    ItemType.MATCHING,
    ItemType.ORDERING,
    ItemType.INTERACTIVE,
}
HUMAN_GRADED = {ItemType.SHORT, ItemType.LONG, ItemType.WORD_PROBLEM}


@dataclass
class RubricLevel:
    level: int
    descriptor: LocalizedText


@dataclass
class Rubric:
    criteria: str
    levels: list[RubricLevel] = field(default_factory=list)
    max_score: int = 0


@dataclass
class AssessmentItem:
    item_id: str
    type: ItemType
    objective_ref: str  # standard_code — every item maps to an SLO (validity)
    competency: Competency
    stem: LocalizedText
    answer_key: dict[str, object] = field(default_factory=dict)
    accepted_variants: list[str] = field(default_factory=list)
    options: list[LocalizedText] = field(default_factory=list)
    rubric: Rubric | None = None
    auto_marking_guidance: str = ""
    mentor_review_guidance: str = ""
    hints: list[Hint] = field(default_factory=list)
    explanation: LocalizedText = field(default_factory=LocalizedText)

    def is_auto_graded(self) -> bool:
        return self.type in AUTO_GRADED

    def needs_rubric(self) -> bool:
        return self.type in {ItemType.LONG, ItemType.WORD_PROBLEM}


@dataclass
class AssessmentBlueprint:
    """A lesson's assessment: formative practice + optional summative (mentor-mediated)."""

    formative: list[AssessmentItem] = field(default_factory=list)
    summative: list[AssessmentItem] = field(default_factory=list)
    summative_test_type: TestType | None = None
    mentor_mediated_summative: bool = (
        True  # promotion-bearing summative requires human identity assurance
    )
