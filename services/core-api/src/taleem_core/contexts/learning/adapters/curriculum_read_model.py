"""Curriculum read-model adapter — projects a published Curriculum Studio lesson into a LessonView.

This is the **integration seam** between the two bounded contexts. In production it is fed by the
``LessonPublished`` event; for the vertical slice it reads the published lesson directly
from the Curriculum Studio store (a legitimate read model over the same database). Cross-context
coupling is confined to this single infrastructure adapter — the learning domain/application only
know the ``CurriculumReadModel`` port.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from ...curriculum_studio.adapters.persistence import unit_of_work as cs_unit_of_work
from ...curriculum_studio.domain.content import Locale
from ...curriculum_studio.domain.lesson import Lesson
from ..domain.curriculum_view import ItemView, LessonView
from ..domain.decision import CurriculumGraph, ObjectiveInfo


def _text(localized: object, prefer: str = "en") -> str:
    """Read a LocalizedText's text map defensively (en preferred for trace readability)."""
    text_map: dict[Locale, str] = getattr(localized, "text", {}) or {}
    return str(text_map.get(Locale.EN if prefer == "en" else Locale.UR, ""))


def _bilingual(localized: object) -> dict[str, str]:
    text_map: dict[Locale, str] = getattr(localized, "text", {}) or {}
    return {"ur": str(text_map.get(Locale.UR, "")), "en": str(text_map.get(Locale.EN, ""))}


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_int(value: object, default: int = 0) -> int:
    return value if isinstance(value, int) else default


class CurriculumStudioReadModel:
    """Reads published lessons from the Curriculum Studio store. Implements CurriculumReadModel."""

    def __init__(self, curriculum_session_factory: sessionmaker[Session]) -> None:
        self._sf = curriculum_session_factory

    def lesson_for(self, objective_code: str) -> LessonView | None:
        with cs_unit_of_work(self._sf) as uow:
            for lesson in uow.lessons.all():
                if (
                    lesson.workflow.state.value == "published"
                    and objective_code in lesson.learning_outcomes
                ):
                    return self._project(lesson, objective_code)
        return None

    def published_graph(self) -> CurriculumGraph:
        """Build the decision-engine curriculum graph from currently-published lessons.

        Read fresh each call so the mounted learning API reflects newly published content (live
        prerequisite-DAG import is a Phase-5 item; for now objectives are ordered, prereq-free).
        """
        infos: list[ObjectiveInfo] = []
        seen: set[str] = set()
        with cs_unit_of_work(self._sf) as uow:
            lessons = [x for x in uow.lessons.all() if x.workflow.state.value == "published"]
        for seq, lesson in enumerate(lessons):
            for code in lesson.learning_outcomes:
                if code not in seen:
                    seen.add(code)
                    infos.append(ObjectiveInfo(code, lesson.lesson_id, (), seq))
        return CurriculumGraph(objectives=tuple(infos))

    def _project(self, lesson: Lesson, objective_code: str) -> LessonView:
        steps: list[str] = []
        for we in lesson.worked_examples:
            steps.append(_text(we.prompt))
            steps.extend(_text(s) for s in we.steps)

        items: list[ItemView] = []
        corrections: dict[str, str] = {}
        for item in lesson.practice_questions:
            key = item.answer_key
            option_misc = {
                int(k): str(v) for k, v in _as_dict(key.get("option_misconceptions")).items()
            }
            for ref, text in _as_dict(key.get("corrections")).items():
                corrections[str(ref)] = str(text)
            items.append(
                ItemView(
                    item_ref=item.item_id,
                    objective_code=objective_code,
                    prompt=_bilingual(item.stem),
                    options=tuple(_text(o) for o in item.options),
                    correct_option=_as_int(key.get("correct_option")),
                    option_misconceptions=option_misc,
                    hints=tuple(_text(h.hint) for h in item.hints),
                )
            )

        return LessonView(
            lesson_id=lesson.lesson_id,
            objective_code=objective_code,
            title=_bilingual(lesson.title),
            explanation=_bilingual(lesson.student_explanation),
            worked_example_steps=tuple(s for s in steps if s),
            practice_items=tuple(items),
            misconception_corrections=corrections,
        )
