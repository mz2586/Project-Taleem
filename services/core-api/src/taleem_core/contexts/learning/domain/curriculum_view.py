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

# ItemView fields used only by the server-side scorer. They never leave the server: no learner API
# response and no offline package may carry any of them.
SECRET_ITEM_FIELDS: tuple[str, ...] = (
    "correct_option",
    "accepted_answers",
    "correct_order",
    "correct_pairs",
    "option_misconceptions",
    "misconception",
)


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

    @property
    def playable(self) -> bool:
        """Whether a learner can answer this item at all (fill has no options)."""
        if self.kind == FILL:
            return bool(self.accepted_answers)
        return bool(self.options)

    def learner_fields(self) -> dict[str, object]:
        """The display fields every learner-facing item JSON carries next to its own fields."""
        return {"kind": self.kind, "left_count": self.left_count}


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

    @property
    def practice_questions(self) -> tuple[ItemView, ...]:
        """The practice questions only (``practice_items`` without the leading activities)."""
        return self.practice_items[self.activity_count :]
