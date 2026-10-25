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

from ....platform.cohort import REAL, current_reader_cohort, visible_to
from ...curriculum_studio.adapters.persistence import unit_of_work as cs_unit_of_work
from ...curriculum_studio.adapters.persistence.models import LessonRow, SubjectRow
from ...curriculum_studio.domain.assessment import HUMAN_GRADED, AssessmentItem, ItemType
from ...curriculum_studio.domain.content import Locale
from ...curriculum_studio.domain.hierarchy import Chapter, EducationSystem
from ...curriculum_studio.domain.interaction import interaction_kind
from ...curriculum_studio.domain.lesson import Lesson
from ...curriculum_studio.domain.packs import DEFAULT_PACK_ID, default_registry
from ..domain.curriculum_view import (
    CHOOSE,
    FILL,
    LONG_MAX_CHARS,
    MATCH,
    ORDER,
    SHORT_MAX_CHARS,
    SORT,
    WRITTEN,
    ItemView,
    LessonView,
    RubricLevelView,
    RubricView,
)
from ..domain.decision import CurriculumGraph, ObjectiveInfo
from ..domain.progression import (
    UNPLACED_TITLE,
    UNPLACED_UNIT_KEY,
    GradePath,
    PathLesson,
    PathSubject,
    PathUnit,
    UnitCheckSettings,
)


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
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _int_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    ints = tuple(v for v in value if isinstance(v, int) and not isinstance(v, bool))
    return ints if len(ints) == len(value) else ()


def _pair_set(value: object) -> frozenset[tuple[int, int]]:
    if not isinstance(value, list):
        return frozenset()
    pairs = [_int_tuple(p) for p in value]
    if any(len(p) != 2 for p in pairs):
        return frozenset()
    return frozenset((p[0], p[1]) for p in pairs)


def _is_written(item: object) -> bool:
    """A human-graded item: ``short`` / ``long`` / ``word_problem`` (HOMEWORK_AND_MARKING §1)."""
    return isinstance(item, AssessmentItem) and item.type in HUMAN_GRADED


def _kind(item: object) -> str:
    """The item's interaction kind (contract §1); pre-contract items project as ``choose``."""
    if _is_written(item):
        return WRITTEN
    kind = interaction_kind(item) if isinstance(item, AssessmentItem) else None
    return kind or CHOOSE


def _rubric(item: object) -> RubricView | None:
    rubric = getattr(item, "rubric", None)
    if rubric is None:
        return None
    return RubricView(
        criteria=str(getattr(rubric, "criteria", "") or ""),
        max_score=max(0, _as_int(getattr(rubric, "max_score", 0))),
        levels=tuple(
            RubricLevelView(level=_as_int(lv.level), descriptor=_bilingual(lv.descriptor))
            for lv in getattr(rubric, "levels", []) or []
        ),
    )


def _key_text(key: dict[str, object], name: str) -> str:
    value = key.get(name)
    return value.strip() if isinstance(value, str) else ""


def _playable_activities(activities: list[AssessmentItem]) -> list[AssessmentItem]:
    """Activities the learner runtime can play + score; widgets / human-graded are skipped."""
    return [a for a in activities if interaction_kind(a) is not None]


def _visible_published(lessons: list[Lesson]) -> list[Lesson]:
    """The published lessons the current reader may see (DEMO_COHORT_CONTRACT §3).

    Every read of this model goes through here: a lesson whose ``metadata.audience`` is ``demo``
    is visible only to a reader whose **account** is in the demo cohort
    (``platform.cohort.current_reader_cohort``; unknown reader = real = never demo)."""
    cohort = current_reader_cohort()
    return [
        lesson
        for lesson in lessons
        if lesson.workflow.state.value == "published"
        and visible_to(lesson.metadata.audience, cohort)
    ]


def _preferred(lessons: list[Lesson]) -> list[Lesson]:
    """``_visible_published``, with a demo reader's own-cohort lessons first (stable), so where a
    demo and a real lesson teach the same objective a demo reader is taught the demo one."""
    visible = _visible_published(lessons)
    cohort = current_reader_cohort()
    if cohort == REAL:
        return visible
    return sorted(visible, key=lambda lesson: lesson.metadata.audience != cohort)


def _grade_structure(
    system: EducationSystem | None, grade_key: str
) -> tuple[dict[str, list[Chapter]], dict[str, dict[str, str]]]:
    """The stored hierarchy's chapters and subject titles for one grade (empty when none)."""
    chapters: dict[str, list[Chapter]] = {}
    titles: dict[str, dict[str, str]] = {}
    grade = next((g for g in system.grades if g.key == grade_key), None) if system else None
    for subject in grade.subjects if grade is not None else []:
        chapters[subject.key] = list(subject.chapters)
        title = {k: v for k, v in _bilingual(subject.title).items() if v}
        if title:
            titles[subject.key] = title
    return chapters, titles


class CurriculumStudioReadModel:
    """Reads published lessons from the Curriculum Studio store. Implements CurriculumReadModel."""

    def __init__(self, curriculum_session_factory: sessionmaker[Session]) -> None:
        self._sf = curriculum_session_factory

    def lesson_for(self, objective_code: str) -> LessonView | None:
        with cs_unit_of_work(self._sf) as uow:
            for lesson in _preferred(uow.lessons.all()):
                if objective_code in lesson.learning_outcomes:
                    return self._project(lesson, objective_code)
        return None

    def published_lessons(self) -> list[LessonView]:
        """Project every published lesson once (homework/assessment/recommendation queries)."""
        out: list[LessonView] = []
        with cs_unit_of_work(self._sf) as uow:
            lessons = _visible_published(uow.lessons.all())
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
        cohort = current_reader_cohort()
        with self._sf() as session:
            rows = session.execute(
                select(
                    LessonRow.lesson_key,
                    LessonRow.id,
                    LessonRow.lock_version,
                    LessonRow.updated_at,
                    LessonRow.content_hash,
                    LessonRow.current_version_no,
                    # The audience, read from the body without loading it (DEMO_COHORT_CONTRACT).
                    LessonRow.body["metadata"]["audience"].as_string(),
                )
                .where(LessonRow.deleted_at.is_(None), LessonRow.state == "published")
                .order_by(LessonRow.updated_at.desc())
            )
            return [
                (str(key), "|".join(str(part) for part in (row_id, lock, updated, chash, ver)))
                for key, row_id, lock, updated, chash, ver, audience in rows
                if visible_to(audience or "", cohort)
            ]

    def published_catalog(self) -> list[dict[str, object]]:
        """Titles-only index of published lessons: one entry per (lesson, objective code).

        ``{"objective_code", "lesson_id", "curriculum_pack", "title": {locale: text}}`` — no items,
        answers, explanations or any other content. Used by the teacher assignment picker.
        """
        out: list[dict[str, object]] = []
        with cs_unit_of_work(self._sf) as uow:
            lessons = _visible_published(uow.lessons.all())
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

    def published_titles(self) -> dict[str, dict[str, str]]:
        """``{objective_code: {"ur", "en"}}`` — the title of the lesson each code is taught from.

        Same choke point and order as ``lesson_for`` (``_preferred``): a real reader never gets a
        demo title, and a demo reader gets the demo lesson's title where both teach a code."""
        out: dict[str, dict[str, str]] = {}
        with cs_unit_of_work(self._sf) as uow:
            lessons = _preferred(uow.lessons.all())
        for lesson in lessons:
            title = _bilingual(lesson.title)
            for code in lesson.learning_outcomes:
                out.setdefault(code, title)
        return out

    def published_versions(self) -> list[dict[str, object]]:
        """The published lesson of each objective code with its version pin (REPORT_CARD_CONTRACT
        §1): ``{"objective_code", "lesson_id", "version", "curriculum_pack", "subject_key",
        "subject_name", "title"}``. One entry per code — the first published lesson listing it,
        the same one ``lesson_for`` teaches from. Titles only; no items or answers. The subject
        name is the stored hierarchy's localized title (``{}`` when the subject is not stored)."""
        out: list[dict[str, object]] = []
        seen: set[str] = set()
        with cs_unit_of_work(self._sf) as uow:
            lessons = _preferred(uow.lessons.all())
        subject_names = self._subject_names()
        for lesson in lessons:
            for code in lesson.learning_outcomes:
                if code in seen:
                    continue
                seen.add(code)
                out.append(
                    {
                        "objective_code": code,
                        "lesson_id": lesson.lesson_id,
                        "version": lesson.version,
                        "curriculum_pack": lesson.metadata.curriculum_pack,
                        "subject_key": lesson.metadata.subject_key,
                        "subject_name": subject_names.get(lesson.metadata.subject_key, {}),
                        "title": _bilingual(lesson.title),
                    }
                )
        return out

    def _subject_names(self) -> dict[str, dict[str, str]]:
        """``{subject_key: {locale: name}}`` from the stored subject rows (top-level titles)."""
        subject_names: dict[str, dict[str, str]] = {}
        with self._sf() as session:
            for key, titles in session.execute(
                select(SubjectRow.subject_key, SubjectRow.titles).order_by(SubjectRow.id)
            ):
                if key not in subject_names and isinstance(titles, dict):
                    subject_names[str(key)] = {
                        str(k): v
                        for k, v in titles.items()
                        if isinstance(v, str) and v and not str(k).startswith("_")
                    }
        return subject_names

    def lesson_view(self, lesson_id: str) -> LessonView | None:
        """One published lesson the current reader may see, projected (None otherwise)."""
        with cs_unit_of_work(self._sf) as uow:
            lesson = uow.lessons.get(lesson_id)
        if lesson is None or not _visible_published([lesson]):
            return None
        code = lesson.learning_outcomes[0] if lesson.learning_outcomes else ""
        return self._project(lesson, code)

    def grade_path(self, grade_key: str, pack_id: str = DEFAULT_PACK_ID) -> GradePath:
        """The published path of one grade (PROGRESSION_AND_EXAMINATION_CONTRACT §1).

        Subjects → units (the stored hierarchy's chapters) → lessons (published, visible to the
        current reader, placed by ``metadata.chapter_key``). A unit with no visible lesson is not
        on the path — so a real reader never sees a unit made only of demo lessons. A subject's
        lessons placed in no stored chapter form one last unit. Where two visible lessons teach
        the same objectives, only the one ``lesson_for`` teaches is listed (same preference)."""
        with cs_unit_of_work(self._sf) as uow:
            lessons = [
                lesson
                for lesson in _preferred(uow.lessons.all())
                if lesson.metadata.grade_key == grade_key
                and lesson.metadata.curriculum_pack == pack_id
            ]
            system = uow.hierarchy.get(pack_id)
        pack = default_registry().get(pack_id)
        settings = (
            UnitCheckSettings(pack.unit_check_items, pack.unit_check_pass_percent)
            if pack is not None
            else UnitCheckSettings()
        )
        # One lesson per objective, in ``lesson_for`` preference order.
        seen: set[str] = set()
        kept: list[Lesson] = []
        for lesson in lessons:
            if not lesson.learning_outcomes or set(lesson.learning_outcomes) <= seen:
                continue
            seen.update(lesson.learning_outcomes)
            kept.append(lesson)
        chapters_by_subject, subject_titles = _grade_structure(system, grade_key)
        stored_names = self._subject_names()
        roster = pack.subjects_for(grade_key) if pack is not None else ()
        subject_keys = list(
            dict.fromkeys(
                [*chapters_by_subject, *roster, *(lesson.metadata.subject_key for lesson in kept)]
            )
        )
        subjects: list[PathSubject] = []
        for subject_key in subject_keys:
            own = [lesson for lesson in kept if lesson.metadata.subject_key == subject_key]
            if not own:
                continue
            chapters = chapters_by_subject.get(subject_key, [])
            units: list[PathUnit] = []
            placed: set[str] = set()
            for chapter in chapters:
                members = [lesson for lesson in own if lesson.metadata.chapter_key == chapter.key]
                if not members:
                    continue
                placed.update(lesson.lesson_id for lesson in members)
                topic_order = {t.key: i for i, t in enumerate(chapter.topics)}
                members.sort(
                    key=lambda lesson, order=topic_order: (  # type: ignore[misc]
                        order.get(lesson.metadata.topic_key, len(order)),
                        lesson.learning_outcomes[0],
                        lesson.lesson_id,
                    )
                )
                units.append(
                    self._unit(pack_id, grade_key, subject_key, chapter.key, chapter, members)
                )
            rest = sorted(
                (lesson for lesson in own if lesson.lesson_id not in placed),
                key=lambda lesson: (lesson.learning_outcomes[0], lesson.lesson_id),
            )
            if rest:
                units.append(
                    self._unit(pack_id, grade_key, subject_key, UNPLACED_UNIT_KEY, None, rest)
                )
            title = (
                subject_titles.get(subject_key)
                or stored_names.get(subject_key)
                or {"en": subject_key, "ur": subject_key}
            )
            subjects.append(PathSubject(key=subject_key, title=title, units=tuple(units)))
        return GradePath(
            pack_id=pack_id, grade_key=grade_key, subjects=tuple(subjects), settings=settings
        )

    def _unit(
        self,
        pack_id: str,
        grade_key: str,
        subject_key: str,
        key: str,
        chapter: Chapter | None,
        lessons: list[Lesson],
    ) -> PathUnit:
        title = _bilingual(chapter.title) if chapter is not None else dict(UNPLACED_TITLE)
        return PathUnit(
            unit_id=f"{pack_id}/{grade_key}/{subject_key}/{key}",
            key=key,
            subject_key=subject_key,
            title=title,
            lessons=tuple(
                PathLesson(
                    lesson_id=lesson.lesson_id,
                    title=_bilingual(lesson.title),
                    objective_codes=tuple(lesson.learning_outcomes),
                    view=self._project(lesson, lesson.learning_outcomes[0]),
                )
                for lesson in lessons
            ),
        )

    def published_graph(self) -> CurriculumGraph:
        """Build the decision-engine curriculum graph from currently-published lessons.

        Read fresh each call so the mounted learning API reflects newly published content (live
        prerequisite-DAG import is a Phase-5 item; for now objectives are ordered, prereq-free).
        """
        infos: list[ObjectiveInfo] = []
        seen: set[str] = set()
        with cs_unit_of_work(self._sf) as uow:
            lessons = _preferred(uow.lessons.all())
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
        kind = _kind(item)
        accepted: tuple[str, ...] = ()
        # A fill item's key, and a written item's exact key when the author states one
        # (HOMEWORK_AND_MARKING_CONTRACT §6: only such a written item is auto-marked).
        if kind in (FILL, WRITTEN):
            answer = key.get("answer")
            variants = [str(v) for v in getattr(item, "accepted_variants", []) or []]
            accepted = tuple(v for v in [str(answer) if answer else "", *variants] if v.strip())
        misconception = key.get("misconception")
        written = kind == WRITTEN
        item_type = getattr(item, "type", None)
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
            kind=kind,
            left_count=_as_int(key.get("left_count")) if kind in (MATCH, SORT) else 0,
            accepted_answers=accepted,
            correct_order=_int_tuple(key.get("order")) if kind == ORDER else (),
            correct_pairs=_pair_set(key.get("pairs")) if kind in (MATCH, SORT) else frozenset(),
            misconception=misconception if isinstance(misconception, str) else "",
            max_chars=(
                (SHORT_MAX_CHARS if item_type is ItemType.SHORT else LONG_MAX_CHARS)
                if written
                else 0
            ),
            rubric=_rubric(item) if written else None,
            sample_answer=_key_text(key, "sample_answer") if written else "",
            guidance=_key_text(key, "guidance") if written else "",
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
        # Playable activities first, then practice: one sequence (ITEM_INTERACTION_CONTRACT §2).
        activities = _playable_activities(lesson.interactive_activities)
        playable = [*activities, *lesson.practice_questions]
        practice = tuple(self._item_view(i, objective_code, corrections) for i in playable)
        homework = tuple(self._item_view(i, objective_code, corrections) for i in lesson.homework)
        formative = tuple(
            self._item_view(i, objective_code, corrections) for i in lesson.assessment.formative
        )
        summative = tuple(
            self._item_view(i, objective_code, corrections) for i in lesson.assessment.summative
        )
        # Written items (HOMEWORK_AND_MARKING_CONTRACT §1): homework, challenges, activities.
        sources = [*lesson.homework, *lesson.challenge_problems, *lesson.interactive_activities]
        written = tuple(
            self._item_view(i, objective_code, corrections) for i in sources if _is_written(i)
        )

        return LessonView(
            lesson_id=lesson.lesson_id,
            objective_code=objective_code,
            title=_bilingual(lesson.title),
            explanation=_bilingual(lesson.student_explanation),
            worked_example_steps=tuple(b["en"] for b in kept),
            practice_items=practice,
            activity_count=len(activities),
            misconception_corrections=corrections,
            homework_items=homework,
            assessment_formative=formative,
            assessment_summative=summative,
            summative_mentor_mediated=lesson.assessment.mentor_mediated_summative,
            worked_example_steps_localized=tuple({k: v for k, v in b.items() if v} for b in kept),
            written_items=written,
            version=lesson.version if lesson.version > 0 else None,
        )
