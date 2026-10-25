"""ProgressionService — the path, unit checks and the academic record.

PROGRESSION_AND_EXAMINATION_CONTRACT.md. Composes the published path of the learner's grade
(cohort-filtered by the curriculum read model), the immutable evidence, the student model and the
stored sittings. Policy lives in ``domain.progression`` (pure); this service loads, persists and
shapes responses. Every answer is scored here, on the server, against the published item; the
paper and every response carry item references and display fields only — never an answer key,
and never a per-item right/wrong while the check is open.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

from sqlalchemy.exc import IntegrityError

from ....platform.errors import conflict
from ....platform.ids import uuid7
from ..adapters.persistence.student_read_model import SqlAlchemyStudentReadModel
from ..adapters.persistence.uow import LearningUnitOfWork
from ..domain.curriculum_view import ItemView
from ..domain.knowledge import AttemptResult
from ..domain.progression import (
    CHECK_LABEL,
    CHECK_NOTICE,
    RECENT_WINDOW_S,
    RESUME_WINDOW_S,
    SITTING_PREFIX,
    GradePath,
    GradeState,
    LessonProgress,
    PathUnit,
    ProgressionError,
    Sitting,
    SittingAnswer,
    SittingStatus,
    UnitState,
    assemble,
    best_sitting,
    grade_key_for,
    grade_label,
    grade_level_of,
    grade_state,
    lesson_progress,
    retake_decision,
    unit_key_of,
    unit_state,
)
from ..domain.scorer import Answer, evaluate
from ..domain.values import InteractionContext
from .concurrency import ConcurrencyConflictError, retry_on_conflict
from .knowledge_service import KnowledgeService
from .ports import EvidenceRow, ProgressionCurriculum

_T = TypeVar("_T")

DEFAULT_GRADE_LEVEL = 4  # the identity context's enrolment default


def _learner_item(item: ItemView, position: int, total: int) -> dict[str, Any]:
    """An item as the learner sees it in a unit check: display fields only (no key, no hints)."""
    return {
        "item_ref": item.item_ref,
        **item.learner_fields(),
        "prompt": item.prompt,
        "options": list(item.options),
        "position": position,
        "total": total,
    }


@dataclass
class _Derived:
    path: GradePath
    evidence: list[EvidenceRow]
    mastered: set[str]
    sittings: list[Sitting]
    lessons: dict[str, LessonProgress]
    units: dict[str, UnitState]
    grade: GradeState

    def sittings_for(self, unit_id: str) -> list[Sitting]:
        return [s for s in self.sittings if s.unit_id == unit_id]

    def titles(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for unit in self.path.units:
            for lesson in unit.lessons:
                for code in lesson.objective_codes:
                    out.setdefault(code, lesson.title)
        return out


class ProgressionService:
    def __init__(
        self,
        uow_factory: Callable[[], LearningUnitOfWork],
        curriculum: ProgressionCurriculum,
        knowledge: KnowledgeService,
        grade_of: Callable[[str], int | None],
        clock: Callable[[], float],
    ) -> None:
        self._uow = uow_factory
        self._curriculum = curriculum
        self._knowledge = knowledge
        self._grade_of = grade_of
        self._now = clock

    # ----------------------------------------------------------------------- derivation

    def _grade_key(self, student_ref: str) -> str:
        level = self._grade_of(student_ref)
        return grade_key_for(DEFAULT_GRADE_LEVEL if level is None else level)

    def _derive(self, student_ref: str) -> _Derived:
        path = self._curriculum.grade_path(self._grade_key(student_ref))
        with self._uow() as uow:
            reads = SqlAlchemyStudentReadModel(uow.session)
            evidence = reads.evidence(student_ref)
            states = reads.objective_states(student_ref)
            mastered = {s.objective_code for s in states if s.state == "mastered"}
            sittings = uow.sittings.for_student(student_ref)
        now = self._now()
        for s in sittings:  # derived (not persisted on a read): past its window = incomplete
            s.status = s.effective_status(now)
        lessons: dict[str, LessonProgress] = {}
        units: dict[str, UnitState] = {}
        for unit in path.units:
            progress = [lesson_progress(lesson, evidence, mastered) for lesson in unit.lessons]
            for lesson, p in zip(unit.lessons, progress, strict=True):
                lessons[lesson.lesson_id] = p
            units[unit.unit_id] = unit_state(
                progress, [s for s in sittings if s.unit_id == unit.unit_id]
            )
        return _Derived(
            path=path,
            evidence=evidence,
            mastered=mastered,
            sittings=sittings,
            lessons=lessons,
            units=units,
            grade=grade_state(list(units.values())),
        )

    @staticmethod
    def _eligible(d: _Derived, unit: PathUnit) -> bool:
        """A unit check may be sat once every lesson is practised (or the unit was sat before)."""
        state = d.units[unit.unit_id]
        return state in (UnitState.READY_FOR_CHECK, UnitState.COMPLETED) or bool(
            d.sittings_for(unit.unit_id)
        )

    @staticmethod
    def _grade(d: _Derived) -> int | str:
        level = grade_level_of(d.path.grade_key)
        return level if level is not None else d.path.grade_key

    # ------------------------------------------------------------------------------ path

    def path(self, student_ref: str) -> dict[str, Any]:
        d = self._derive(student_ref)
        now = self._now()
        subjects: list[dict[str, Any]] = []
        for subject in d.path.subjects:
            units: list[dict[str, Any]] = []
            for unit in subject.units:
                sittings = d.sittings_for(unit.unit_id)
                decision = retake_decision(sittings, d.evidence, now)
                live = next((s for s in sittings if s.status is SittingStatus.IN_PROGRESS), None)
                best = best_sitting(sittings)
                closed = [s for s in sittings if s.status is not SittingStatus.IN_PROGRESS]
                eligible = self._eligible(d, unit)
                units.append(
                    {
                        "unit_key": unit.unit_key,
                        "unit_id": unit.unit_id,
                        "title": unit.title,
                        "state": d.units[unit.unit_id].value,
                        "lessons": [
                            {
                                "lesson_id": lesson.lesson_id,
                                "objective_code": lesson.objective_codes[0],
                                "title": lesson.title,
                                **_progress(d.lessons[lesson.lesson_id]),
                            }
                            for lesson in unit.lessons
                        ],
                        "check": {
                            "available": live is not None or (eligible and decision.allowed),
                            "best_score": (
                                best.result.score_percent if best and best.result else None
                            ),
                            "passed": any(s.status is SittingStatus.PASSED for s in sittings),
                            "last_sitting_id": closed[-1].sitting_id if closed else None,
                            "open_sitting_id": live.sitting_id if live else None,
                            "can_retake": bool(closed) and live is None and decision.allowed,
                            "retake_after": decision.allowed_after,
                            "item_count": d.path.settings.items,
                            "pass_mark": d.path.settings.pass_percent,
                        },
                    }
                )
            subjects.append({"subject_key": subject.key, "title": subject.title, "units": units})
        return {
            "student_ref": student_ref,
            "grade": self._grade(d),
            "grade_key": d.path.grade_key,
            "grade_state": d.grade.value,
            "label": CHECK_LABEL,
            "notice": CHECK_NOTICE,
            "online_only": True,
            "subjects": subjects,
            "next_step": self._next_step(d, now),
            "derived_at": now,
        }

    def _next_step(self, d: _Derived, now: float) -> dict[str, Any] | None:
        """The recommended next step: a check (open, or ready) or a lesson (remediation first)."""
        for s in d.sittings:
            unit = d.path.unit(s.unit_id)
            if s.status is SittingStatus.IN_PROGRESS and unit is not None:
                return _step_check(unit, s.sitting_id)
        for unit in d.path.units:
            if d.units[unit.unit_id] is UnitState.COMPLETED:
                continue
            decision = retake_decision(d.sittings_for(unit.unit_id), d.evidence, now)
            if not decision.allowed and decision.remediation_due:
                return _step_lesson(unit, decision.remediation_due[0], reason="remediation")
            if self._eligible(d, unit) and decision.allowed:
                return _step_check(unit, None)
            lesson = next(
                (lesson for lesson in unit.lessons if not d.lessons[lesson.lesson_id].completed),
                unit.lessons[0],
            )
            return _step_lesson(unit, lesson.objective_codes[0], reason="practice")
        return None

    # ------------------------------------------------------------------------- sittings

    def get(self, sitting_id: str) -> Sitting | None:
        with self._uow() as uow:
            return uow.sittings.get(sitting_id)

    def resolve_unit(self, student_ref: str, unit_key: str) -> str:
        """The canonical unit id of ``unit_key`` on the learner's path (404 otherwise)."""
        unit = self._curriculum.grade_path(self._grade_key(student_ref)).unit_by_key(unit_key)
        if unit is None:
            raise ProgressionError("UNIT_NOT_FOUND", "no such unit on this learner's path")
        return unit.unit_id

    def start(self, student_ref: str, unit_key: str) -> tuple[dict[str, Any], bool]:
        """Start a sitting of the unit (``created=True``), or resume the open one."""
        d = self._derive(student_ref)
        unit = d.path.unit_by_key(unit_key)
        if unit is None:
            raise ProgressionError("UNIT_NOT_FOUND", "no such unit on this learner's path")
        now = self._now()
        self._expire(student_ref, now)
        sittings = d.sittings_for(unit.unit_id)
        live = next((s for s in sittings if s.status is SittingStatus.IN_PROGRESS), None)
        if live is not None:
            return self.current(live.sitting_id), False
        if not self._eligible(d, unit):
            raise ProgressionError(
                "UNIT_NOT_READY", "practise every lesson of this unit before its unit check"
            )
        decision = retake_decision(sittings, d.evidence, now)
        if not decision.allowed:
            raise ProgressionError(
                "RETAKE_NOT_YET",
                "a retake is allowed after remediation on the missed objectives, or after 24 "
                "hours",
                retake_after=decision.allowed_after,
                remediation_due=list(decision.remediation_due),
            )
        sitting_id = f"{SITTING_PREFIX}{uuid7()}"
        recent = {e.item_ref for e in d.evidence if e.occurred_at >= now - RECENT_WINDOW_S}
        for s in sittings:
            if s.started_at >= now - RECENT_WINDOW_S:
                recent.update(p.item_ref for p in s.items)
        paper = assemble(unit, size=d.path.settings.items, recent=recent, seed=sitting_id)
        if not paper:
            raise ProgressionError(
                "UNIT_CHECK_UNAVAILABLE", "this unit has no auto-scored items for a unit check"
            )
        sitting = Sitting(
            sitting_id=sitting_id,
            student_ref=student_ref,
            pack_id=d.path.pack_id,
            grade_key=d.path.grade_key,
            subject_key=unit.subject_key,
            unit_id=unit.unit_id,
            unit_title=dict(unit.title),
            items=paper,
            pass_percent=d.path.settings.pass_percent,
            started_at=now,
            expires_at=now + RESUME_WINDOW_S,
        )
        try:
            with self._uow() as uow:
                uow.sittings.add(sitting)
                uow.commit()
        except IntegrityError:
            # A concurrent start won the one-open-sitting index: resume that one.
            with self._uow() as uow:
                open_ = [
                    s
                    for s in uow.sittings.for_student(student_ref)
                    if s.unit_id == unit.unit_id and s.status is SittingStatus.IN_PROGRESS
                ]
            if not open_:
                raise
            return self.current(open_[0].sitting_id), False
        return self.current(sitting_id), True

    def _expire(self, student_ref: str, now: float) -> None:
        """Persist ``incomplete`` on the learner's open sittings past their window."""

        def _txn() -> None:
            with self._uow() as uow:
                changed = False
                for s in uow.sittings.for_student(student_ref):
                    if s.expire_if_due(now):
                        uow.sittings.save(s)
                        changed = True
                if changed:
                    uow.commit()

        self._retrying(_txn)

    def _load_expiring(self, sitting_id: str, now: float) -> Sitting:
        def _txn() -> Sitting:
            with self._uow() as uow:
                sitting = uow.sittings.get(sitting_id)
                if sitting is None:
                    raise ProgressionError("SITTING_NOT_FOUND", "no such unit check")
                if sitting.expire_if_due(now):
                    uow.sittings.save(sitting)
                    uow.commit()
                return sitting

        return self._retrying(_txn)

    def current(self, sitting_id: str) -> dict[str, Any]:
        """The open sitting with its next unanswered item (to resume). Expired: 410."""
        now = self._now()
        sitting = self._load_expiring(sitting_id, now)
        if sitting.status is SittingStatus.INCOMPLETE:
            raise _expired()
        sitting, item = self._next_item(sitting_id, sitting, now)
        return {**self._head(sitting, now), "item": item}

    def _next_item(
        self, sitting_id: str, sitting: Sitting, now: float
    ) -> tuple[Sitting, dict[str, Any] | None]:
        """The next unanswered item's learner view; an unpublished item is withdrawn on the way."""
        while sitting.status is SittingStatus.IN_PROGRESS:
            pending = sitting.next_item()
            if pending is None:
                return sitting, None
            item = self._item(pending.lesson_id, pending.item_ref)
            if item is not None:
                position = sitting.items.index(pending) + 1
                return sitting, _learner_item(item, position, len(sitting.items))
            self._withdraw(sitting_id, pending.item_ref, now)
            sitting = self._load_expiring(sitting_id, now)
        return sitting, None

    def _head(self, sitting: Sitting, now: float) -> dict[str, Any]:
        total = len(sitting.items)
        return {
            "sitting_id": sitting.sitting_id,
            "unit_key": unit_key_of(sitting.unit_id),
            "unit_title": sitting.unit_title,
            "label": CHECK_LABEL,
            "status": sitting.effective_status(now).value,
            "started_at": sitting.started_at,
            "expires_at": sitting.expires_at,
            "total": total,
            "answered": total - sitting.unanswered,
        }

    def _item(self, lesson_id: str, item_ref: str) -> ItemView | None:
        """The published item a paper names (current version; cohort-filtered), or None if it
        is no longer published."""
        view = self._curriculum.lesson_view(lesson_id)
        if view is None:
            return None
        return next(
            (
                i
                for i in (
                    *view.practice_items,
                    *view.assessment_formative,
                    *view.assessment_summative,
                )
                if i.item_ref == item_ref
            ),
            None,
        )

    def _withdraw(self, sitting_id: str, item_ref: str, now: float) -> None:
        """An item no longer published is excluded from the paper (no evidence, not scored)."""

        def _txn() -> None:
            with self._uow() as uow:
                sitting = uow.sittings.get(sitting_id)
                if sitting is None or item_ref in sitting.answers:
                    return
                sitting.record(SittingAnswer(item_ref, {}, None, (), "", now))
                uow.sittings.save(sitting)
                uow.commit()

        self._retrying(_txn)

    def answer(
        self, sitting_id: str, item_ref: str, given: Answer, *, response_time_ms: int = 0
    ) -> dict[str, Any]:
        """Score one answer on the server and record its evidence (context ``summative``).

        Each item is answered once per sitting: a repeated submission changes nothing and
        returns ``duplicate: true``. The response never says whether the answer was correct (the
        result comes with ``:finish``)."""
        now = self._now()
        sitting = self._load_expiring(sitting_id, now)
        paper_item = sitting.item(item_ref)
        if paper_item is None:
            raise ProgressionError("ITEM_NOT_IN_SITTING", "this item is not on this unit check")
        if item_ref in sitting.answers:
            return self._answered(sitting, now, duplicate=True)
        if sitting.status is SittingStatus.INCOMPLETE:
            raise _expired()
        sitting.require_open(now)
        view = self._curriculum.lesson_view(paper_item.lesson_id)
        item = self._item(paper_item.lesson_id, item_ref) if view is not None else None
        if item is None:
            self._withdraw(sitting_id, item_ref, now)
            return self._answered(self._load_expiring(sitting_id, now), now)
        outcome, hits = evaluate(item, given)  # AnswerKindMismatchError -> 422 in the adapter
        correct = outcome.value == "correct"
        version = view.version if view is not None else paper_item.lesson_version
        recorded: list[AttemptResult] = []

        def _txn() -> tuple[Sitting, bool]:
            recorded.clear()
            with self._uow() as uow:
                current = uow.sittings.get(sitting_id)
                if current is None:
                    raise ProgressionError("SITTING_NOT_FOUND", "no such unit check")
                if item_ref in current.answers:
                    return current, True
                current.require_open(self._now())
                attempt = self._knowledge.record_attempt_in(
                    uow,
                    student_ref=current.student_ref,
                    objective_code=paper_item.objective_code,
                    item_ref=item_ref,
                    session_id=sitting_id,
                    correct=correct,
                    misconception_hits=hits,
                    hints_used=0,
                    response_time_ms=max(0, response_time_ms),
                    context=InteractionContext.SUMMATIVE,
                    self_confidence=None,
                    lesson_id=paper_item.lesson_id,
                    lesson_version=version,
                )
                current.record(
                    SittingAnswer(
                        item_ref=item_ref,
                        answer=_answer_fields(given),
                        correct=correct,
                        misconceptions=tuple(hits) if not correct else (),
                        evidence_id=attempt.result.evidence_id,
                        answered_at=now,
                    )
                )
                uow.sittings.save(current)
                uow.commit()
                recorded.append(attempt.result)
                return current, False

        try:
            current, duplicate = self._retrying(_txn)
        except ProgressionError as exc:
            if exc.code == "SITTING_EXPIRED":
                raise _expired() from exc
            raise
        for result in recorded:
            self._knowledge.observe(current.student_ref, result)
        return self._answered(current, now, duplicate=duplicate)

    def _answered(self, sitting: Sitting, now: float, *, duplicate: bool = False) -> dict[str, Any]:
        sitting, item = self._next_item(sitting.sitting_id, sitting, now)
        total = len(sitting.items)
        return {
            "sitting_id": sitting.sitting_id,
            "accepted": True,
            "duplicate": duplicate,
            "answered": total - sitting.unanswered,
            "total": total,
            "next_item": item,
        }

    def finish(self, sitting_id: str) -> dict[str, Any]:
        """Score the sitting (every item answered). Idempotent once finished."""
        now = self._now()

        def _txn() -> Sitting:
            with self._uow() as uow:
                sitting = uow.sittings.get(sitting_id)
                if sitting is None:
                    raise ProgressionError("SITTING_NOT_FOUND", "no such unit check")
                if sitting.scored:
                    return sitting
                if sitting.expire_if_due(now):
                    uow.sittings.save(sitting)
                    uow.commit()
                    return sitting
                if sitting.status is SittingStatus.INCOMPLETE:
                    return sitting
                sitting.finish(now)
                uow.sittings.save(sitting)
                uow.commit()
                return sitting

        sitting = self._retrying(_txn)
        if sitting.status is SittingStatus.INCOMPLETE:
            raise _expired()
        return self.result(sitting)

    def result(self, sitting: Sitting) -> dict[str, Any]:
        """A finished sitting's result, the remediation it routes to and the retake rule."""
        now = self._now()
        d = self._derive(sitting.student_ref)
        titles = d.titles()
        unit = d.path.unit(sitting.unit_id)
        result = sitting.result
        decision = retake_decision(d.sittings_for(sitting.unit_id), d.evidence, now)
        missed = result.missed_objectives if result is not None else ()
        return {
            "sitting_id": sitting.sitting_id,
            "unit_key": unit_key_of(sitting.unit_id),
            "label": CHECK_LABEL,
            "notice": CHECK_NOTICE,
            "status": sitting.status.value,
            "finished_at": sitting.finished_at,
            "score_percent": result.score_percent if result else None,
            "passed": result.passed if result else False,
            "pass_mark": sitting.pass_percent,
            "correct": result.correct if result else 0,
            "total": result.total if result else 0,
            "per_objective": _per_objective(sitting, titles),
            "misconceptions": list(result.misconceptions) if result else [],
            "remediation": [_teaching(unit, code, sitting, titles) for code in missed],
            "can_retake": decision.allowed,
            "retake_after": decision.allowed_after,
        }

    # --------------------------------------------------------------------------- record

    def record(
        self, student_ref: str, *, report_cards: Sequence[dict[str, Any]] = ()
    ) -> dict[str, Any]:
        """The academic record (contract §3). Every figure derives from stored sittings and
        evidence; nothing on it can be typed in. Open sittings are not results and not listed."""
        d = self._derive(student_ref)
        now = self._now()
        titles = d.titles()
        closed = [s for s in d.sittings if s.status is not SittingStatus.IN_PROGRESS]
        subjects = []
        for subject in d.path.subjects:
            units = []
            for u in subject.units:
                mine = [s for s in closed if s.unit_id == u.unit_id]
                best = best_sitting(mine)
                units.append(
                    {
                        "unit_key": u.unit_key,
                        "title": u.title,
                        "state": d.units[u.unit_id].value,
                        "best_score": best.result.score_percent if best and best.result else None,
                        "sittings": [s.sitting_id for s in mine],
                    }
                )
            subjects.append({"subject_key": subject.key, "title": subject.title, "units": units})
        sittings = [
            {
                "sitting_id": s.sitting_id,
                "unit_key": unit_key_of(s.unit_id),
                "unit_title": s.unit_title,
                "label": CHECK_LABEL,
                "started_at": s.started_at,
                "finished_at": s.finished_at,
                "state": "finished" if s.scored else "incomplete",
                "score_percent": s.result.score_percent if s.result else None,
                "passed": s.result.passed if s.result else None,
                "pass_mark": s.pass_percent,
                "per_objective": _per_objective(s, titles),
            }
            for s in closed
        ]
        seen: set[str] = set()
        mastered: list[dict[str, Any]] = []
        for unit in d.path.units:
            for lesson in unit.lessons:
                if not d.lessons[lesson.lesson_id].demonstrated:
                    continue
                for code in lesson.objective_codes:
                    if code not in seen:
                        seen.add(code)
                        mastered.append(
                            {
                                "objective_code": code,
                                "title": lesson.title,
                                "lesson_id": lesson.lesson_id,
                            }
                        )
        completion: dict[str, Any] | None = None
        if d.grade is GradeState.COMPLETED:
            label = grade_label(d.path.grade_key)
            completed_at = max(
                min(
                    s.finished_at or 0.0
                    for s in d.sittings_for(u.unit_id)
                    if s.status is SittingStatus.PASSED
                )
                for u in d.path.units
            )
            completion = {
                "grade": self._grade(d),
                "grade_key": d.path.grade_key,
                "completed_at": completed_at,
                "accredited": False,
                "label": {
                    "en": f"{label['en']} completed in Taleem — not an accredited certificate",
                    "ur": f"{label['ur']} تعلیم میں مکمل — یہ تسلیم شدہ سند نہیں ہے",
                },
            }
        return {
            "student_ref": student_ref,
            "grade": self._grade(d),
            "grade_key": d.path.grade_key,
            "grade_state": d.grade.value,
            "grade_completion": completion,
            "subjects": subjects,
            "sittings": sittings,
            "lessons_mastered": mastered,
            "report_cards": list(report_cards),
            "notice": CHECK_NOTICE,
            "derived_at": now,
        }

    # -------------------------------------------------------------------------- helpers

    @staticmethod
    def _retrying(fn: Callable[[], _T]) -> _T:
        try:
            return retry_on_conflict(fn)
        except ConcurrencyConflictError as exc:
            raise conflict("unit check write conflict; please retry") from exc


def _expired() -> ProgressionError:
    return ProgressionError("SITTING_EXPIRED", "this unit check expired before it was finished")


def _progress(p: LessonProgress) -> dict[str, Any]:
    return {"state": p.state.value, "completed": p.completed, "demonstrated": p.demonstrated}


def _step_check(unit: PathUnit, sitting_id: str | None) -> dict[str, Any]:
    return {
        "kind": "unit_check",
        "unit_key": unit.unit_key,
        "title": unit.title,
        "sitting_id": sitting_id,
    }


def _step_lesson(unit: PathUnit, code: str, *, reason: str) -> dict[str, Any]:
    lesson = next((x for x in unit.lessons if code in x.objective_codes), unit.lessons[0])
    return {
        "kind": "lesson",
        "unit_key": unit.unit_key,
        "title": lesson.title,
        "lesson_id": lesson.lesson_id,
        "objective_code": code,
        "reason": reason,
    }


def _teaching(
    unit: PathUnit | None,
    code: str,
    sitting: Sitting,
    titles: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """The lesson that teaches ``code`` in the unit (falls back to the paper's lesson)."""
    for lesson in unit.lessons if unit is not None else ():
        if code in lesson.objective_codes:
            return {"objective_code": code, "title": lesson.title, "lesson_id": lesson.lesson_id}
    lesson_id = next((p.lesson_id for p in sitting.items if p.objective_code == code), None)
    return {"objective_code": code, "title": titles.get(code, {}), "lesson_id": lesson_id}


def _per_objective(s: Sitting, titles: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    if s.result is None:
        return []
    return [
        {
            "objective_code": o.objective_code,
            "title": titles.get(o.objective_code, {}),
            "correct": o.correct,
            "total": o.total,
            "percent": o.percent,
            "met": o.met(s.pass_percent),
        }
        for o in s.result.breakdown
    ]


def _answer_fields(given: Answer) -> dict[str, Any]:
    if given.option is not None:
        return {"option": given.option}
    if given.text is not None:
        return {"text": given.text}
    if given.order is not None:
        return {"order": list(given.order)}
    return {"pairs": [list(p) for p in given.pairs or ()]}
