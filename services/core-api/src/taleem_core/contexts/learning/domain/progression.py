"""Progression and examination (pure) — PROGRESSION_AND_EXAMINATION_CONTRACT.md.

The learner's **path** (grade → subjects → units → lessons) with derived states, and the **unit
check**: a fixed-length, auto-scored end-of-unit examination taken in a resumable **sitting**.

Everything here is derived from inputs (the published path, stored evidence, the student model and
stored sittings) — no I/O, deterministic. Answer keys stay inside ``ItemView`` (server side); the
paper itself (``PaperItem``) holds references only.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .curriculum_view import ITEM_KINDS, ItemView, LessonView
from .values import InteractionContext

# --------------------------------------------------------------------------------- constants

DEFAULT_CHECK_ITEMS = 10
DEFAULT_PASS_PERCENT = 70
RESUME_WINDOW_S = 24 * 3600.0  # a sitting is resumable for 24 hours after it starts
RECENT_WINDOW_S = 7 * 86400.0  # items seen in the last 7 days are avoided when the pool allows
RETAKE_WAIT_S = 24 * 3600.0  # a retake is allowed 24 hours after a scored sitting
SITTING_PREFIX = "ucs_"
CHECK_LABEL = "Taleem unit check"
CHECK_NOTICE = (
    "An unproctored Taleem unit check. It is not a promotion-bearing examination and not a "
    "certification."
)
UNPLACED_UNIT_KEY = "_unplaced"
UNPLACED_TITLE: dict[str, str] = {"en": "More lessons", "ur": "مزید اسباق"}

# Evidence that is not practice: placement answers and examination answers.
_NOT_PRACTICE = {InteractionContext.DIAGNOSTIC.value, InteractionContext.SUMMATIVE.value}


class LessonState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    PRACTISED = "practised"
    MASTERED = "mastered"


class UnitState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    READY_FOR_CHECK = "ready_for_check"
    COMPLETED = "completed"


class GradeState(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class SittingStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    PASSED = "passed"
    FAILED = "failed"
    INCOMPLETE = "incomplete"  # never finished within the resume window (never "failed")


SITTING_STATUSES: tuple[str, ...] = tuple(s.value for s in SittingStatus)


class ProgressionError(ValueError):
    """A unit-check rule refused the request; ``code`` is the stable API error code."""

    def __init__(self, code: str, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.code = code
        self.detail = detail


def grade_key_for(level: int) -> str:
    """The pack grade key of an enrolment ``gradeLevel`` (0 = KG, n = Gn)."""
    return "KG" if level == 0 else f"G{level}"


def unit_key_of(unit_id: str) -> str:
    """The URL-safe unit key of a canonical unit id: ``PK-NCP/G4/math/u1`` -> ``math.u1``."""
    parts = unit_id.split("/")
    return ".".join(parts[-2:]) if len(parts) >= 2 else unit_id


def grade_level_of(grade_key: str) -> int | None:
    if grade_key == "KG":
        return 0
    return int(grade_key[1:]) if grade_key[:1] == "G" and grade_key[1:].isdigit() else None


def grade_label(grade_key: str) -> dict[str, str]:
    if grade_key.startswith("G") and grade_key[1:].isdigit():
        return {"en": f"Grade {grade_key[1:]}", "ur": f"جماعت {grade_key[1:]}"}
    return {"en": grade_key, "ur": grade_key}


# ------------------------------------------------------------------------------ the path


@dataclass(frozen=True)
class UnitCheckSettings:
    """A pack's unit-check settings (defaults 10 items, 70%)."""

    items: int = DEFAULT_CHECK_ITEMS
    pass_percent: int = DEFAULT_PASS_PERCENT


@dataclass(frozen=True)
class PathLesson:
    """A published lesson on the path. ``view`` carries its items (server side only)."""

    lesson_id: str
    title: dict[str, str]
    objective_codes: tuple[str, ...]
    view: LessonView

    @property
    def version(self) -> int | None:
        return self.view.version

    @property
    def practice_refs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(i.item_ref for i in self.view.practice_items))


@dataclass(frozen=True)
class PathUnit:
    """A unit: one chapter of the stored hierarchy (or a subject's unplaced lessons)."""

    unit_id: str
    key: str
    subject_key: str
    title: dict[str, str]
    lessons: tuple[PathLesson, ...]

    @property
    def objective_codes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(c for lesson in self.lessons for c in lesson.objective_codes))

    @property
    def unit_key(self) -> str:
        return unit_key_of(self.unit_id)


@dataclass(frozen=True)
class PathSubject:
    key: str
    title: dict[str, str]
    units: tuple[PathUnit, ...]


@dataclass(frozen=True)
class GradePath:
    """The published path of one grade, as the current reader may see it (cohort-filtered)."""

    pack_id: str
    grade_key: str
    subjects: tuple[PathSubject, ...]
    settings: UnitCheckSettings = field(default_factory=UnitCheckSettings)

    @property
    def units(self) -> tuple[PathUnit, ...]:
        return tuple(u for s in self.subjects for u in s.units)

    def unit(self, unit_id: str) -> PathUnit | None:
        return next((u for u in self.units if u.unit_id == unit_id), None)

    def unit_by_key(self, unit_key: str) -> PathUnit | None:
        return next((u for u in self.units if u.unit_key == unit_key), None)


class EvidenceLike(Protocol):
    """The evidence fields derivation reads (``ports.EvidenceRow`` satisfies it)."""

    @property
    def objective_code(self) -> str: ...
    @property
    def item_ref(self) -> str: ...
    @property
    def outcome(self) -> str: ...
    @property
    def context(self) -> str: ...
    @property
    def occurred_at(self) -> float: ...
    @property
    def lesson_id(self) -> str: ...


@dataclass(frozen=True)
class LessonProgress:
    """A lesson's state. ``completed`` (practice finished) and ``demonstrated`` (every objective
    mastered in the student model) are distinct: finishing practice is never shown as mastery."""

    state: LessonState
    completed: bool
    demonstrated: bool


def _lesson_evidence(lesson: PathLesson, evidence: Iterable[EvidenceLike]) -> list[EvidenceLike]:
    codes = set(lesson.objective_codes)
    return [
        e
        for e in evidence
        if e.lesson_id == lesson.lesson_id or (not e.lesson_id and e.objective_code in codes)
    ]


def lesson_progress(
    lesson: PathLesson, evidence: Iterable[EvidenceLike], mastered: set[str]
) -> LessonProgress:
    """Derive one lesson's state from its evidence and the mastered objective codes."""
    own = _lesson_evidence(lesson, evidence)
    practice = [e for e in own if e.context not in _NOT_PRACTICE]
    refs = set(lesson.practice_refs)
    completed = refs <= {e.item_ref for e in practice} if refs else bool(practice)
    demonstrated = bool(lesson.objective_codes) and all(
        c in mastered for c in lesson.objective_codes
    )
    if demonstrated:
        state = LessonState.MASTERED
    elif completed:
        state = LessonState.PRACTISED
    elif own:
        state = LessonState.IN_PROGRESS
    else:
        state = LessonState.NOT_STARTED
    return LessonProgress(state=state, completed=completed, demonstrated=demonstrated)


def unit_state(progress: Sequence[LessonProgress], sittings: Sequence[Sitting]) -> UnitState:
    """``completed`` once a unit check is passed; ``ready_for_check`` when every lesson is
    practised; ``in_progress`` on any evidence or sitting."""
    if any(s.status is SittingStatus.PASSED for s in sittings):
        return UnitState.COMPLETED
    if progress and all(p.completed for p in progress):
        return UnitState.READY_FOR_CHECK
    if sittings or any(p.state is not LessonState.NOT_STARTED for p in progress):
        return UnitState.IN_PROGRESS
    return UnitState.NOT_STARTED


def grade_state(units: Sequence[UnitState]) -> GradeState:
    if units and all(u is UnitState.COMPLETED for u in units):
        return GradeState.COMPLETED
    if any(u is not UnitState.NOT_STARTED for u in units):
        return GradeState.IN_PROGRESS
    return GradeState.NOT_STARTED


# ---------------------------------------------------------------------------- assembly


@dataclass(frozen=True)
class PaperItem:
    """One item of a sitting's paper: references only (never the key)."""

    item_ref: str
    objective_code: str
    lesson_id: str
    lesson_version: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_ref": self.item_ref,
            "objective_code": self.objective_code,
            "lesson_id": self.lesson_id,
            "lesson_version": self.lesson_version,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> PaperItem:
        version = d.get("lesson_version")
        return cls(
            item_ref=str(d["item_ref"]),
            objective_code=str(d["objective_code"]),
            lesson_id=str(d["lesson_id"]),
            lesson_version=version if isinstance(version, int) else None,
        )


def auto_scored(item: ItemView) -> bool:
    """Whether a unit check may use the item: an auto-scored kind the runtime can play."""
    return item.kind in ITEM_KINDS and item.playable


def unit_pool(unit: PathUnit) -> list[tuple[ItemView, PathLesson]]:
    """Every auto-scored item of the unit's lessons — practice (activities first), formative and
    summative pools — once per item ref, in lesson order."""
    seen: set[str] = set()
    out: list[tuple[ItemView, PathLesson]] = []
    for lesson in unit.lessons:
        view = lesson.view
        for item in (
            *view.practice_items,
            *view.assessment_formative,
            *view.assessment_summative,
        ):
            if item.item_ref in seen or not auto_scored(item):
                continue
            seen.add(item.item_ref)
            out.append((item, lesson))
    return out


def _draw_order(seed: str, item_ref: str) -> str:
    return hashlib.sha256(f"{seed}\x1f{item_ref}".encode()).hexdigest()


def assemble(unit: PathUnit, *, size: int, recent: set[str], seed: str) -> tuple[PaperItem, ...]:
    """Assemble a paper of up to ``size`` items, balanced across the unit's objectives.

    Items the learner saw recently (``recent``) are used only when the fresh pool cannot fill the
    paper. Within each objective the draw order is a hash of ``seed`` (the sitting id), so each
    sitting draws its own paper and the same seed always draws the same paper. Objectives take
    turns (round robin, in unit order), first over fresh items, then over recent ones.
    """
    pool = unit_pool(unit)
    order = list(unit.objective_codes)
    for item, _ in pool:
        if item.objective_code not in order:
            order.append(item.objective_code)
    target = min(max(size, 0), len(pool))
    paper: list[PaperItem] = []
    for fresh in (True, False):
        queues = [
            sorted(
                (
                    (item, lesson)
                    for item, lesson in pool
                    if item.objective_code == code and (item.item_ref not in recent) == fresh
                ),
                key=lambda pair: _draw_order(seed, pair[0].item_ref),
            )
            for code in order
        ]
        while len(paper) < target and any(queues):
            for queue in queues:
                if queue and len(paper) < target:
                    item, lesson = queue.pop(0)
                    paper.append(
                        PaperItem(
                            item.item_ref, item.objective_code, lesson.lesson_id, lesson.version
                        )
                    )
    return tuple(paper)


# ----------------------------------------------------------------------------- scoring


@dataclass(frozen=True)
class ObjectiveScore:
    objective_code: str
    correct: int
    total: int

    @property
    def percent(self) -> float:
        return round(100.0 * self.correct / self.total, 1) if self.total else 0.0

    def met(self, pass_percent: int) -> bool:
        return self.total > 0 and self.correct * 100 >= pass_percent * self.total


@dataclass(frozen=True)
class CheckResult:
    """A scored sitting: one point per correct item; ``passed`` iff score ≥ the pass mark."""

    correct: int
    total: int
    pass_percent: int
    breakdown: tuple[ObjectiveScore, ...]
    misconceptions: tuple[str, ...]

    @property
    def score_percent(self) -> float:
        return round(100.0 * self.correct / self.total, 1) if self.total else 0.0

    @property
    def passed(self) -> bool:
        # Integer comparison: reproducible, no rounding at the boundary.
        return self.total > 0 and self.correct * 100 >= self.pass_percent * self.total

    @property
    def missed_objectives(self) -> tuple[str, ...]:
        return tuple(o.objective_code for o in self.breakdown if not o.met(self.pass_percent))

    def to_dict(self) -> dict[str, Any]:
        return {
            "correct": self.correct,
            "total": self.total,
            "pass_mark": self.pass_percent,
            "score_percent": self.score_percent,
            "passed": self.passed,
            "breakdown": [
                {
                    "objective_code": o.objective_code,
                    "correct": o.correct,
                    "total": o.total,
                    "percent": o.percent,
                    "met": o.met(self.pass_percent),
                }
                for o in self.breakdown
            ],
            "misconceptions": list(self.misconceptions),
            "missed_objectives": list(self.missed_objectives),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> CheckResult:
        return cls(
            correct=int(d["correct"]),
            total=int(d["total"]),
            pass_percent=int(d["pass_mark"]),
            breakdown=tuple(
                ObjectiveScore(str(o["objective_code"]), int(o["correct"]), int(o["total"]))
                for o in d.get("breakdown", [])
            ),
            misconceptions=tuple(str(m) for m in d.get("misconceptions", [])),
        )


@dataclass(frozen=True)
class SittingAnswer:
    """One recorded answer. ``correct`` is None for an item withdrawn from publication (it is
    excluded from the score). ``answer`` is the learner's own answer fields."""

    item_ref: str
    answer: dict[str, Any]
    correct: bool | None
    misconceptions: tuple[str, ...]
    evidence_id: str
    answered_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": dict(self.answer),
            "correct": self.correct,
            "misconceptions": list(self.misconceptions),
            "evidence_id": self.evidence_id,
            "answered_at": self.answered_at,
        }

    @classmethod
    def from_dict(cls, item_ref: str, d: Mapping[str, Any]) -> SittingAnswer:
        correct = d.get("correct")
        return cls(
            item_ref=item_ref,
            answer=dict(d.get("answer") or {}),
            correct=correct if isinstance(correct, bool) else None,
            misconceptions=tuple(str(m) for m in d.get("misconceptions", [])),
            evidence_id=str(d.get("evidence_id") or ""),
            answered_at=float(d.get("answered_at") or 0.0),
        )


def score(
    paper: Sequence[PaperItem],
    answers: Mapping[str, SittingAnswer],
    *,
    pass_percent: int,
    objective_order: Sequence[str] = (),
) -> CheckResult:
    """Score a paper (pure, reproducible). Withdrawn items are excluded; an unanswered item
    counts as not correct."""
    order = list(dict.fromkeys([*objective_order, *(p.objective_code for p in paper)]))
    tallies: dict[str, list[int]] = {}
    misconceptions: list[str] = []
    for p in paper:
        a = answers.get(p.item_ref)
        if a is not None and a.correct is None:
            continue  # withdrawn
        tally = tallies.setdefault(p.objective_code, [0, 0])
        tally[1] += 1
        if a is not None and a.correct:
            tally[0] += 1
        elif a is not None:
            misconceptions.extend(a.misconceptions)
    breakdown = tuple(
        ObjectiveScore(c, tallies[c][0], tallies[c][1]) for c in order if c in tallies
    )
    return CheckResult(
        correct=sum(o.correct for o in breakdown),
        total=sum(o.total for o in breakdown),
        pass_percent=pass_percent,
        breakdown=breakdown,
        misconceptions=tuple(sorted(set(misconceptions))),
    )


# ----------------------------------------------------------------------------- sitting


@dataclass
class Sitting:
    """One attempt at a unit check (C2 learning record)."""

    sitting_id: str
    student_ref: str
    pack_id: str
    grade_key: str
    subject_key: str
    unit_id: str
    unit_title: dict[str, str]
    items: tuple[PaperItem, ...]
    pass_percent: int
    started_at: float
    expires_at: float
    status: SittingStatus = SittingStatus.IN_PROGRESS
    answers: dict[str, SittingAnswer] = field(default_factory=dict)
    finished_at: float | None = None
    result: CheckResult | None = None
    lock_version: int = 0

    @property
    def scored(self) -> bool:
        return self.status in (SittingStatus.PASSED, SittingStatus.FAILED)

    def effective_status(self, now: float) -> SittingStatus:
        """The status as of ``now``: an unfinished sitting past its window is incomplete."""
        if self.status is SittingStatus.IN_PROGRESS and now >= self.expires_at:
            return SittingStatus.INCOMPLETE
        return self.status

    def expire_if_due(self, now: float) -> bool:
        """Mark an unfinished sitting past its window ``incomplete``. True if it changed."""
        if self.effective_status(now) is not self.status:
            self.status = SittingStatus.INCOMPLETE
            return True
        return False

    def item(self, item_ref: str) -> PaperItem | None:
        return next((p for p in self.items if p.item_ref == item_ref), None)

    def next_item(self) -> PaperItem | None:
        return next((p for p in self.items if p.item_ref not in self.answers), None)

    @property
    def unanswered(self) -> int:
        return sum(1 for p in self.items if p.item_ref not in self.answers)

    def require_open(self, now: float) -> None:
        self.expire_if_due(now)
        if self.status is SittingStatus.INCOMPLETE:
            raise ProgressionError(
                "SITTING_EXPIRED", "this unit check expired before it was finished"
            )
        if self.status is not SittingStatus.IN_PROGRESS:
            raise ProgressionError("SITTING_FINISHED", "this unit check is already finished")

    def record(self, answer: SittingAnswer) -> None:
        if answer.item_ref in self.answers:
            raise ProgressionError("ALREADY_ANSWERED", "this item is already answered")
        if self.item(answer.item_ref) is None:
            raise ProgressionError("ITEM_NOT_IN_SITTING", "this item is not on this unit check")
        self.answers[answer.item_ref] = answer

    def finish(self, now: float, objective_order: Sequence[str] = ()) -> CheckResult:
        self.require_open(now)
        if self.unanswered:
            raise ProgressionError(
                "SITTING_UNANSWERED",
                f"{self.unanswered} item(s) are not answered yet",
                unanswered=self.unanswered,
            )
        result = score(
            self.items,
            self.answers,
            pass_percent=self.pass_percent,
            objective_order=objective_order,
        )
        self.result = result
        self.finished_at = now
        self.status = SittingStatus.PASSED if result.passed else SittingStatus.FAILED
        return result


# ------------------------------------------------------------------------------ retakes


@dataclass(frozen=True)
class RetakeDecision:
    allowed: bool
    reason: (
        str  # first | after_incomplete | waited | remediated | in_progress | remediation_or_wait
    )
    allowed_after: float | None = None
    remediation_due: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "allowed_after": self.allowed_after,
            "remediation_due": list(self.remediation_due),
        }


def remediated(objective_code: str, since: float, evidence: Iterable[EvidenceLike]) -> bool:
    """A correct practice / remediation / review answer on the objective after ``since``."""
    return any(
        e.objective_code == objective_code
        and e.occurred_at > since
        and e.outcome == "correct"
        and e.context not in _NOT_PRACTICE
        for e in evidence
    )


def retake_decision(
    sittings: Sequence[Sitting], evidence: Sequence[EvidenceLike], now: float
) -> RetakeDecision:
    """May the learner start a sitting of this unit now (contract §2)?

    One sitting at a time. After a scored sitting a retake is allowed once the learner has done
    remediation on every missed objective, or 24 hours after it finished. An incomplete sitting
    does not count.
    """
    if any(s.effective_status(now) is SittingStatus.IN_PROGRESS for s in sittings):
        return RetakeDecision(False, "in_progress")
    scored = sorted((s for s in sittings if s.scored), key=lambda s: s.finished_at or 0.0)
    if not scored:
        reason = "after_incomplete" if sittings else "first"
        return RetakeDecision(True, reason)
    last = scored[-1]
    finished = last.finished_at or last.started_at
    wait_until = finished + RETAKE_WAIT_S
    missed = last.result.missed_objectives if last.result is not None else ()
    due = tuple(c for c in missed if not remediated(c, finished, evidence))
    if now >= wait_until:
        return RetakeDecision(True, "waited", remediation_due=due)
    if missed and not due:
        return RetakeDecision(True, "remediated")
    return RetakeDecision(
        False, "remediation_or_wait", allowed_after=wait_until, remediation_due=due
    )


def best_sitting(sittings: Sequence[Sitting]) -> Sitting | None:
    """The best scored sitting: highest score, earliest on a tie."""
    scored = [s for s in sittings if s.scored and s.result is not None]
    if not scored:
        return None
    return min(
        scored,
        key=lambda s: (-(s.result.score_percent if s.result else 0.0), s.finished_at or 0.0),
    )
