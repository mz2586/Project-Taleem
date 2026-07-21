"""Read-only projection of published curriculum the learning context consumes.

The learning context never imports Curriculum Studio's domain (no cross-context coupling). Instead a
``CurriculumReadModel`` adapter projects a published lesson into these immutable views, which the
teaching runtime and scorer operate on. This is the boundary that keeps the AI runtime *in scope*:
it can only ever use content present in a ``LessonView``.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ItemView:
    """A single assessment item, projected for teaching + scoring."""

    item_ref: str
    objective_code: str
    prompt: dict[str, str]  # locale -> text
    options: tuple[str, ...] = ()  # display options (localized to the session language upstream)
    correct_option: int = 0
    option_misconceptions: dict[int, str] = field(
        default_factory=dict
    )  # wrong option -> misconception
    hints: tuple[str, ...] = ()  # graduated hint ladder (authored)


@dataclass(frozen=True)
class LessonView:
    """A published lesson projected for the teaching runtime (approved content only)."""

    lesson_id: str
    objective_code: str
    title: dict[str, str]
    explanation: dict[str, str]
    worked_example_steps: tuple[str, ...] = ()
    practice_items: tuple[ItemView, ...] = ()
    misconception_corrections: dict[str, str] = field(
        default_factory=dict
    )  # ref -> correction text
    # Projected for the student-facing Homework and Assessment surfaces (approved content only).
    homework_items: tuple[ItemView, ...] = ()
    assessment_formative: tuple[ItemView, ...] = ()
    assessment_summative: tuple[ItemView, ...] = ()
    summative_mentor_mediated: bool = True
