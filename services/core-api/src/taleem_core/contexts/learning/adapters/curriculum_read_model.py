"""Curriculum read-model adapter — projects a published Curriculum Studio lesson into a LessonView.

This is the **integration seam** between the two bounded contexts. In production it is fed by the
``LessonPublished`` event; for the vertical slice it reads the published lesson directly
from the Curriculum Studio store (a legitimate read model over the same database). Cross-context
coupling is confined to this single infrastructure adapter — the learning domain/application only
know the ``CurriculumReadModel`` port.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ...curriculum_studio.adapters.persistence import unit_of_work as cs_unit_of_work
from ...curriculum_studio.adapters.persistence.models import LessonRow
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

    def published_lessons(self) -> list[LessonView]:
        """Project every published lesson once (homework/assessment/recommendation queries)."""
        out: list[LessonView] = []
        with cs_unit_of_work(self._sf) as uow:
            lessons = [x for x in uow.lessons.all() if x.workflow.state.value == "published"]
        for lesson in lessons:
            code = lesson.learning_outcomes[0] if lesson.learning_outcomes else ""
            out.append(self._project(lesson, code))
        return out

    def published_fingerprints(self) -> list[tuple[str, str]]:
        """``(lesson_id, fingerprint)`` for every published lesson, in ``published_lessons`` order.

        Reads row columns only (no body, no child rows). The fingerprint changes whenever the
        lesson row is written: it carries the row id and its optimistic-lock ``lock_version``
        (bumped by every ORM update: a publish, a rollback, any edit), plus ``updated_at``, the
        studio content hash and the published version number. Consumers key caches of derived
        content on it, so a changed lesson is never served from a stale entry.
        """
        with self._sf() as session:
            rows = session.execute(
                select(
                    LessonRow.lesson_key,
                    LessonRow.id,
                    LessonRow.lock_version,
                    LessonRow.updated_at,
                    LessonRow.content_hash,
                    LessonRow.current_version_no,
                )
                .where(LessonRow.deleted_at.is_(None), LessonRow.state == "published")
                .order_by(LessonRow.updated_at.desc())
            )
            return [
                (str(key), "|".join(str(part) for part in (row_id, lock, updated, chash, ver)))
                for key, row_id, lock, updated, chash, ver in rows
            ]

    def published_catalog(self) -> list[dict[str, object]]:
        """Titles-only index of published lessons: one entry per (lesson, objective code).

        ``{"objective_code", "lesson_id", "curriculum_pack", "title": {locale: text}}`` — no items,
        answers, explanations or any other content. Used by the teacher assignment picker.
        """
        out: list[dict[str, object]] = []
        with cs_unit_of_work(self._sf) as uow:
            lessons = [x for x in uow.lessons.all() if x.workflow.state.value == "published"]
        for lesson in lessons:
            for code in lesson.learning_outcomes:
                out.append(
                    {
                        "objective_code": code,
                        "lesson_id": lesson.lesson_id,
                        "curriculum_pack": lesson.metadata.curriculum_pack,
                        "title": _bilingual(lesson.title),
                    }
                )
        return out

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

    def _item_view(
        self, item: object, objective_code: str, corrections: dict[str, str]
    ) -> ItemView:
        key = _as_dict(getattr(item, "answer_key", {}))
        for ref, text in _as_dict(key.get("corrections")).items():
            corrections[str(ref)] = str(text)
        return ItemView(
            item_ref=str(getattr(item, "item_id", "")),
            objective_code=objective_code,
            prompt=_bilingual(getattr(item, "stem", None)),
            options=tuple(_text(o) for o in getattr(item, "options", [])),
            correct_option=_as_int(key.get("correct_option")),
            option_misconceptions={
                int(k): str(v) for k, v in _as_dict(key.get("option_misconceptions")).items()
            },
            hints=tuple(_text(h.hint) for h in getattr(item, "hints", [])),
        )

    def _project(self, lesson: Lesson, objective_code: str) -> LessonView:
        # Each worked-example text, kept bilingual; the English projection below is unchanged.
        bilingual_steps: list[dict[str, str]] = []
        for we in lesson.worked_examples:
            bilingual_steps.append(_bilingual(we.prompt))
            bilingual_steps.extend(_bilingual(s) for s in we.steps)
        # Index-aligned with ``worked_example_steps``: the same filter (a non-empty English text).
        kept = [b for b in bilingual_steps if b.get("en", "")]

        corrections: dict[str, str] = {}
        practice = tuple(
            self._item_view(i, objective_code, corrections) for i in lesson.practice_questions
        )
        homework = tuple(self._item_view(i, objective_code, corrections) for i in lesson.homework)
        formative = tuple(
            self._item_view(i, objective_code, corrections) for i in lesson.assessment.formative
        )
        summative = tuple(
            self._item_view(i, objective_code, corrections) for i in lesson.assessment.summative
        )

        return LessonView(
            lesson_id=lesson.lesson_id,
            objective_code=objective_code,
            title=_bilingual(lesson.title),
            explanation=_bilingual(lesson.student_explanation),
            worked_example_steps=tuple(b["en"] for b in kept),
            practice_items=practice,
            misconception_corrections=corrections,
            homework_items=homework,
            assessment_formative=formative,
            assessment_summative=summative,
            summative_mentor_mediated=lesson.assessment.mentor_mediated_summative,
            worked_example_steps_localized=tuple({k: v for k, v in b.items() if v} for b in kept),
        )
