"""Pure progression rules (PROGRESSION_AND_EXAMINATION_CONTRACT.md): lesson / unit / grade states,
unit-check assembly, scoring, sittings and retakes. No I/O."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from taleem_core.contexts.learning.domain.curriculum_view import ItemView, LessonView
from taleem_core.contexts.learning.domain.progression import (
    RESUME_WINDOW_S,
    RETAKE_WAIT_S,
    GradeState,
    LessonState,
    PaperItem,
    PathLesson,
    PathUnit,
    ProgressionError,
    Sitting,
    SittingAnswer,
    SittingStatus,
    UnitState,
    assemble,
    best_sitting,
    grade_key_for,
    grade_state,
    lesson_progress,
    retake_decision,
    score,
    unit_key_of,
    unit_pool,
    unit_state,
)


@dataclass(frozen=True)
class Ev:
    objective_code: str
    item_ref: str
    outcome: str = "correct"
    context: str = "practice"
    occurred_at: float = 100.0
    lesson_id: str = ""


def _item(ref: str, code: str, **kw: object) -> ItemView:
    return ItemView(item_ref=ref, objective_code=code, prompt={"en": ref}, options=("a", "b"), **kw)  # type: ignore[arg-type]


def _lesson(lid: str, code: str, practice: int = 2, summative: int = 0) -> PathLesson:
    view = LessonView(
        lesson_id=lid,
        objective_code=code,
        title={"en": lid},
        explanation={},
        practice_items=tuple(_item(f"{lid}-p{i}", code) for i in range(practice)),
        assessment_summative=tuple(_item(f"{lid}-s{i}", code) for i in range(summative)),
        version=3,
    )
    return PathLesson(lid, {"en": lid}, (code,), view)


def _unit(*lessons: PathLesson) -> PathUnit:
    return PathUnit("PK-NCP/G4/math/u1", "u1", "math", {"en": "U1"}, lessons)


# ----------------------------------------------------------------------------- states


def test_completed_and_demonstrated_are_distinct() -> None:
    lesson = _lesson("L1", "A")
    assert lesson_progress(lesson, [], set()).state is LessonState.NOT_STARTED
    some = [Ev("A", "L1-p0", lesson_id="L1")]
    assert lesson_progress(lesson, some, set()).state is LessonState.IN_PROGRESS
    done = [*some, Ev("A", "L1-p1", outcome="incorrect", lesson_id="L1")]
    p = lesson_progress(lesson, done, set())
    assert p.state is LessonState.PRACTISED and p.completed and not p.demonstrated
    # Mastered in the student model without finishing practice: demonstrated, not completed.
    m = lesson_progress(lesson, some, {"A"})
    assert m.state is LessonState.MASTERED and m.demonstrated and not m.completed


def test_placement_and_unit_check_answers_are_not_practice() -> None:
    lesson = _lesson("L1", "A")
    ev = [
        Ev("A", "L1-p0", context="diagnostic", lesson_id="L1"),
        Ev("A", "L1-p1", context="summative", lesson_id="L1"),
    ]
    p = lesson_progress(lesson, ev, set())
    assert p.state is LessonState.IN_PROGRESS and not p.completed
    # Legacy evidence without a lesson id counts through the objective.
    legacy = [Ev("A", "L1-p0"), Ev("A", "L1-p1")]
    assert lesson_progress(lesson, legacy, set()).completed


def _sitting(status: SittingStatus = SittingStatus.IN_PROGRESS, **kw: object) -> Sitting:
    base: dict[str, object] = {
        "sitting_id": "ucs_1",
        "student_ref": "stu",
        "pack_id": "PK-NCP",
        "grade_key": "G4",
        "subject_key": "math",
        "unit_id": "PK-NCP/G4/math/u1",
        "unit_title": {},
        "items": (PaperItem("i1", "A", "L1", 1), PaperItem("i2", "B", "L2", 1)),
        "pass_percent": 70,
        "started_at": 0.0,
        "expires_at": RESUME_WINDOW_S,
        "status": status,
    }
    base.update(kw)
    return Sitting(**base)  # type: ignore[arg-type]


def test_unit_and_grade_states() -> None:
    lesson = _lesson("L1", "A")
    practised = lesson_progress(lesson, [Ev("A", "L1-p0"), Ev("A", "L1-p1")], set())
    fresh = lesson_progress(lesson, [], set())
    assert unit_state([fresh, fresh], []) is UnitState.NOT_STARTED
    assert unit_state([practised, fresh], []) is UnitState.IN_PROGRESS
    assert unit_state([practised, practised], []) is UnitState.READY_FOR_CHECK
    failed = _sitting(SittingStatus.FAILED)
    assert unit_state([practised, practised], [failed]) is UnitState.READY_FOR_CHECK
    assert unit_state([practised], [_sitting(SittingStatus.PASSED)]) is UnitState.COMPLETED
    assert grade_state([]) is GradeState.NOT_STARTED
    assert grade_state([UnitState.COMPLETED, UnitState.IN_PROGRESS]) is GradeState.IN_PROGRESS
    assert grade_state([UnitState.COMPLETED, UnitState.COMPLETED]) is GradeState.COMPLETED
    assert grade_key_for(4) == "G4" and grade_key_for(0) == "KG"
    assert unit_key_of("PK-NCP/G4/math/u1") == "math.u1"


# --------------------------------------------------------------------------- assembly


def test_pool_is_auto_scored_only_and_deduplicated() -> None:
    written = ItemView(item_ref="w", objective_code="A", prompt={}, kind="written")
    fill_no_key = ItemView(item_ref="f", objective_code="A", prompt={}, kind="fill")
    view = LessonView(
        lesson_id="L1",
        objective_code="A",
        title={},
        explanation={},
        practice_items=(_item("p0", "A"), fill_no_key),
        assessment_formative=(_item("p0", "A"), written),
    )
    unit = _unit(PathLesson("L1", {}, ("A",), view))
    assert [i.item_ref for i, _ in unit_pool(unit)] == ["p0"]


def test_assembly_is_balanced_reproducible_and_avoids_recent_items() -> None:
    unit = _unit(_lesson("L1", "A", 6, 6), _lesson("L2", "B", 2, 0))
    paper = assemble(unit, size=6, recent=set(), seed="x")
    assert len(paper) == 6
    assert [p.objective_code for p in paper].count("B") == 2  # B has only 2 items
    assert assemble(unit, size=6, recent=set(), seed="x") == paper  # same seed, same paper
    assert all(p.lesson_version == 3 for p in paper)
    balanced = assemble(
        _unit(_lesson("L1", "A", 6), _lesson("L2", "B", 6)), size=6, recent=set(), seed="y"
    )
    assert [p.objective_code for p in balanced].count("A") == 3
    # Recent items are used only when the fresh pool runs out.
    recent = {f"L1-p{i}" for i in range(6)}
    avoid = assemble(unit, size=8, recent=recent, seed="x")
    refs = [p.item_ref for p in avoid]
    assert {f"L1-s{i}" for i in range(6)} <= set(refs) and {"L2-p0", "L2-p1"} <= set(refs)
    filled = assemble(unit, size=12, recent=recent, seed="x")
    assert len(filled) == 12 and sum(1 for p in filled if p.item_ref in recent) == 4
    assert len(assemble(unit, size=50, recent=set(), seed="x")) == 14  # capped by the pool


# ---------------------------------------------------------------------------- scoring


def _answers(**correct: bool | None) -> dict[str, SittingAnswer]:
    return {
        ref: SittingAnswer(ref, {"option": 0}, ok, ("m1",) if ok is False else (), "e", 1.0)
        for ref, ok in correct.items()
    }


@pytest.mark.parametrize(("right", "passed"), [(7, True), (6, False), (10, True), (0, False)])
def test_pass_mark_is_an_exact_threshold(right: int, passed: bool) -> None:
    paper = tuple(PaperItem(f"i{i}", "A", "L1", 1) for i in range(10))
    answers = _answers(**{f"i{i}": i < right for i in range(10)})
    result = score(paper, answers, pass_percent=70)
    assert result.passed is passed and result.score_percent == right * 10.0
    assert score(paper, answers, pass_percent=70) == result  # reproducible


def test_breakdown_misconceptions_withdrawn_and_missed() -> None:
    paper = (
        PaperItem("a1", "A", "L1", 1),
        PaperItem("a2", "A", "L1", 1),
        PaperItem("b1", "B", "L2", 1),
        PaperItem("b2", "B", "L2", 1),
    )
    result = score(paper, _answers(a1=True, a2=True, b1=False, b2=None), pass_percent=70)
    assert (result.correct, result.total) == (2, 3)  # b2 withdrawn: excluded
    assert [(o.objective_code, o.correct, o.total) for o in result.breakdown] == [
        ("A", 2, 2),
        ("B", 0, 1),
    ]
    assert result.missed_objectives == ("B",) and result.misconceptions == ("m1",)
    assert result.score_percent == pytest.approx(66.7)
    assert result.to_dict()["passed"] is False


# --------------------------------------------------------------------------- sittings


def test_sitting_answers_once_finishes_once_and_expires_incomplete() -> None:
    s = _sitting()
    s.record(_answers(i1=True)["i1"])
    with pytest.raises(ProgressionError) as dup:
        s.record(_answers(i1=False)["i1"])
    assert dup.value.code == "ALREADY_ANSWERED"
    with pytest.raises(ProgressionError) as early:
        s.finish(10.0)
    assert early.value.code == "SITTING_UNANSWERED"
    s.record(_answers(i2=False)["i2"])
    result = s.finish(10.0)
    assert s.status is SittingStatus.FAILED and result.score_percent == 50.0
    with pytest.raises(ProgressionError):
        s.finish(11.0)

    late = _sitting()
    assert late.effective_status(RESUME_WINDOW_S - 1) is SittingStatus.IN_PROGRESS
    assert late.effective_status(RESUME_WINDOW_S) is SittingStatus.INCOMPLETE
    assert late.expire_if_due(RESUME_WINDOW_S) and late.status is SittingStatus.INCOMPLETE
    with pytest.raises(ProgressionError) as exc:
        late.require_open(RESUME_WINDOW_S)
    assert exc.value.code == "SITTING_EXPIRED"


def _scored(status: SittingStatus, missed: str, finished: float, sid: str = "ucs_1") -> Sitting:
    s = _sitting(sitting_id=sid)
    s.record(_answers(i1=True)["i1"])
    s.record(_answers(i2=missed != "B")["i2"])
    s.finish(finished)
    assert s.status is status
    return s


def test_retake_rules() -> None:
    assert retake_decision([], [], 0.0).reason == "first"
    assert not retake_decision([_sitting()], [], 1.0).allowed  # one open sitting at a time
    expired = _sitting(status=SittingStatus.INCOMPLETE)
    assert retake_decision([expired], [], 1.0).reason == "after_incomplete"

    failed = _scored(SittingStatus.FAILED, "B", 100.0)
    blocked = retake_decision([failed], [], 200.0)
    assert not blocked.allowed and blocked.remediation_due == ("B",)
    assert blocked.allowed_after == 100.0 + RETAKE_WAIT_S
    # Practice before the failure, a wrong answer, or a summative answer is not remediation.
    noise = [
        Ev("B", "x", occurred_at=50.0),
        Ev("B", "x", outcome="incorrect", occurred_at=150.0),
        Ev("B", "x", context="summative", occurred_at=150.0),
    ]
    assert not retake_decision([failed], noise, 200.0).allowed
    done = retake_decision(
        [failed], [Ev("B", "x", context="remediation", occurred_at=150.0)], 200.0
    )
    assert done.allowed and done.reason == "remediated"
    waited = retake_decision([failed], [], 100.0 + RETAKE_WAIT_S)
    assert waited.allowed and waited.reason == "waited"


def test_best_sitting_is_the_highest_score_earliest_on_a_tie() -> None:
    a = _scored(SittingStatus.FAILED, "B", 10.0, "ucs_a")
    b = _scored(SittingStatus.PASSED, "", 20.0, "ucs_b")
    c = _scored(SittingStatus.PASSED, "", 30.0, "ucs_c")
    assert best_sitting([a, b, c]) is b
    assert best_sitting([_sitting()]) is None
