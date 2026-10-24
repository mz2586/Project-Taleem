"""Read-only projection of published curriculum the learning context consumes.

The learning context never imports Curriculum Studio's domain (no cross-context coupling). Instead a
``CurriculumReadModel`` adapter projects a published lesson into these immutable views, which the
teaching runtime and scorer operate on. This is the boundary that keeps the AI runtime *in scope*:
it can only ever use content present in a ``LessonView``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Interaction kinds (ITEM_INTERACTION_CONTRACT.md §2). The same strings Curriculum Studio's
# ``interaction_kind`` returns; the learning domain keeps its own names (no cross-context import).
CHOOSE, FILL, ORDER, MATCH, SORT = "choose", "fill", "order", "match", "sort"
ITEM_KINDS: tuple[str, ...] = (CHOOSE, FILL, ORDER, MATCH, SORT)
# A human-graded item (``short`` / ``long`` / ``word_problem``; HOMEWORK_AND_MARKING_CONTRACT §1).
# Never auto-scored: a teacher marks the learner's written answer.
WRITTEN = "written"
SHORT_MAX_CHARS = 200  # a ``short`` answer
LONG_MAX_CHARS = 2000  # a ``long`` or ``word_problem`` answer

# ItemView fields used only by the server-side scorer. They never leave the server: no learner API
# response and no offline package may carry any of them.
SECRET_ITEM_FIELDS: tuple[str, ...] = (
    "correct_option",
    "accepted_answers",
    "correct_order",
    "correct_pairs",
    "option_misconceptions",
    "misconception",
    # Written items: the marking aids, for the teacher only (HOMEWORK_AND_MARKING_CONTRACT §1).
    "rubric",
    "sample_answer",
    "guidance",
)


@dataclass(frozen=True)
class RubricLevelView:
    level: int
    descriptor: dict[str, str]  # locale -> text


@dataclass(frozen=True)
class RubricView:
    """A written item's marking rubric (teacher-only)."""

    criteria: str
    max_score: int
    levels: tuple[RubricLevelView, ...] = ()

    @property
    def scored(self) -> bool:
        """Whether marking against this rubric takes a score (``0..max_score``)."""
        return self.max_score > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "criteria": self.criteria,
            "max_score": self.max_score,
            # ``score`` is the level's score on the rubric scale; ``label`` names the level (no
            # separate label is authored, so it is the level number).
            "levels": [
                {"score": lv.level, "label": str(lv.level), "descriptor": dict(lv.descriptor)}
                for lv in self.levels
            ],
        }


@dataclass(frozen=True)
class ItemView:
    """A single assessment item, projected for teaching + scoring.

    Display fields: ``kind``, ``prompt``, ``options`` (for match/sort: the left items, then the
    right items / group labels), ``left_count`` (match/sort only, else 0) and ``hints``. Every
    field named in ``SECRET_ITEM_FIELDS`` is the answer key and stays server-side.
    """

    item_ref: str
    objective_code: str
    prompt: dict[str, str]  # locale -> text
    options: tuple[str, ...] = ()  # display options (localized to the session language upstream)
    correct_option: int = 0
    option_misconceptions: dict[int, str] = field(
        default_factory=dict
    )  # wrong option -> misconception
    hints: tuple[str, ...] = ()  # graduated hint ladder (authored)
    kind: str = CHOOSE
    left_count: int = 0  # match/sort: options[:left_count] are the left items / cards
    accepted_answers: tuple[str, ...] = ()  # fill: canonical answer first, then variants
    correct_order: tuple[int, ...] = ()  # order: option indices in the correct order
    correct_pairs: frozenset[tuple[int, int]] = frozenset()  # match/sort: (left, right)
    misconception: str = ""  # misconception any wrong answer implies (after option_misconceptions)
    # Written items only: the answer's length cap (learner-visible) and the marking aids
    # (teacher-only; listed in SECRET_ITEM_FIELDS).
    max_chars: int = 0
    rubric: RubricView | None = None
    sample_answer: str = ""
    guidance: str = ""

    @property
    def written(self) -> bool:
        return self.kind == WRITTEN

    @property
    def playable(self) -> bool:
        """Whether the learner runtime can play + auto-score this item (fill has no options; a
        written item is marked by a teacher, never auto-scored)."""
        if self.kind == WRITTEN:
            return False
        if self.kind == FILL:
            return bool(self.accepted_answers)
        return bool(self.options)

    def learner_fields(self) -> dict[str, object]:
        """The display fields every learner-facing item JSON carries next to its own fields."""
        fields: dict[str, object] = {"kind": self.kind, "left_count": self.left_count}
        if self.kind == WRITTEN:
            fields["max_chars"] = self.max_chars
        return fields

    def teacher_fields(self) -> dict[str, object]:
        """The marking aids of a written item, for a teacher's marking view only."""
        return {
            "rubric": self.rubric.to_dict() if self.rubric is not None else None,
            "sample_answer": self.sample_answer or None,
            "guidance": self.guidance or None,
        }


@dataclass(frozen=True)
class LessonView:
    """A published lesson projected for the teaching runtime (approved content only)."""

    lesson_id: str
    objective_code: str
    title: dict[str, str]
    explanation: dict[str, str]
    worked_example_steps: tuple[str, ...] = ()
    # The lesson's playable interactive activities, then its practice questions (one sequence).
    practice_items: tuple[ItemView, ...] = ()
    misconception_corrections: dict[str, str] = field(
        default_factory=dict
    )  # ref -> correction text
    # Projected for the student-facing Homework and Assessment surfaces (approved content only).
    homework_items: tuple[ItemView, ...] = ()
    assessment_formative: tuple[ItemView, ...] = ()
    assessment_summative: tuple[ItemView, ...] = ()
    summative_mentor_mediated: bool = True
    # The same worked-example steps, per locale ({"ur": …, "en": …}), index-aligned with
    # ``worked_example_steps`` (which stays the English projection for compatibility: the runtime,
    # offline packages and their content hashes are unchanged). Used to ground a localized rephrase.
    worked_example_steps_localized: tuple[dict[str, str], ...] = ()
    # How many leading ``practice_items`` are interactive activities (the rest are practice).
    activity_count: int = 0
    # Every written item of the lesson's homework, challenge problems and interactive activities,
    # in that order (HOMEWORK_AND_MARKING_CONTRACT §1). Marked by a teacher, never auto-scored.
    written_items: tuple[ItemView, ...] = ()

    @property
    def practice_questions(self) -> tuple[ItemView, ...]:
        """The practice questions only (``practice_items`` without the leading activities)."""
        return self.practice_items[self.activity_count :]

    def written_item(self, item_ref: str) -> ItemView | None:
        """The written item ``item_ref`` of this lesson, or None."""
        return next((i for i in self.written_items if i.item_ref == item_ref), None)
