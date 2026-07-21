"""Unit + domain tests for the Learning Intelligence Platform core (the 'critical learning logic').

Covers the pure brain: estimator, forgetting model, knowledge aggregate, scorer, teaching runtime,
session state machine, and the decision engine. Deterministic; no I/O.
"""

from __future__ import annotations

import pytest

from taleem_core.contexts.learning.domain.curriculum_view import ItemView, LessonView
from taleem_core.contexts.learning.domain.decision import (
    CurriculumGraph,
    Decision,
    DecisionConfig,
    DecisionKind,
    ObjectiveInfo,
    post_interaction,
    select_next,
)
from taleem_core.contexts.learning.domain.estimator import BKTEstimator, BKTParams
from taleem_core.contexts.learning.domain.forgetting import HalfLifeForgettingModel
from taleem_core.contexts.learning.domain.knowledge import (
    AttemptResult,
    ObjectiveMastery,
    StudentKnowledge,
)
from taleem_core.contexts.learning.domain.runtime import TemplatedTeachingRuntime
from taleem_core.contexts.learning.domain.scorer import evaluate
from taleem_core.contexts.learning.domain.session import Session, SessionError, SessionState
from taleem_core.contexts.learning.domain.values import (
    InteractionContext,
    Mastery,
    MasteryState,
    MemoryStrength,
    Outcome,
)

EST = BKTEstimator()
FOG = HalfLifeForgettingModel()
CFG = DecisionConfig()
OBJ = "MATH-G4-FR-01"


# --------------------------------------------------------------------------- estimator


def test_estimator_initial_is_prior_at_high_uncertainty() -> None:
    m = EST.initial()
    assert m.value == pytest.approx(0.30)
    assert m.uncertainty == 1.0


def test_estimator_correct_raises_incorrect_lowers() -> None:
    prior = Mastery(0.4, 1.0)
    up = EST.update(prior, correct=True)
    down = EST.update(prior, correct=False)
    assert up.value > prior.value > down.value
    assert up.uncertainty < prior.uncertainty  # narrows with evidence


def test_estimator_params_clamped() -> None:
    p = BKTParams(p_slip=2.0, p_guess=-1.0)
    assert p.p_slip == 1.0
    assert p.p_guess == 0.0


# --------------------------------------------------------------------------- forgetting


def test_forgetting_decays_over_time() -> None:
    m = Mastery(1.0, 0.1)
    mem = MemoryStrength(stability_s=100.0, last_seen_at=0.0)
    assert FOG.predicted_recall(m, mem, now=0.0) == pytest.approx(1.0)
    assert FOG.predicted_recall(m, mem, now=100.0) < 0.5


def test_forgetting_review_expands_and_contracts() -> None:
    mem = MemoryStrength(stability_s=100_000.0, last_seen_at=0.0)
    grown = FOG.on_review(mem, correct=True, now=10.0)
    shrunk = FOG.on_review(mem, correct=False, now=10.0)
    assert grown.stability_s > mem.stability_s > shrunk.stability_s
    assert grown.next_review_at > 10.0


def test_forgetting_on_learned_schedules_future_review() -> None:
    mem = FOG.on_learned(now=500.0)
    assert mem.next_review_at > 500.0


# --------------------------------------------------------------------------- knowledge


def _apply(
    k: StudentKnowledge,
    *,
    correct: bool,
    hits: tuple[str, ...] = (),
    now: float = 1.0,
    ctx: InteractionContext = InteractionContext.PRACTICE,
) -> AttemptResult:
    return k.apply_attempt(
        evidence_id=f"e{len(k.evidence)}",
        objective_code=OBJ,
        item_ref="i",
        session_id="s",
        correct=correct,
        misconception_hits=hits,
        hints_used=0,
        response_time_ms=0,
        context=ctx,
        self_confidence=0.8,
        estimator=EST,
        forgetting=FOG,
        now=now,
    )


def test_knowledge_correct_raises_mastery_and_streak() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    r = _apply(k, correct=True)
    obj = k.get(OBJ)
    assert obj is not None and obj.correct_streak == 1 and obj.consecutive_failures == 0
    assert r.mastery_after.value > r.mastery_before.value
    assert len(k.evidence) == 1  # immutable evidence appended


def test_knowledge_wrong_increments_failures() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    _apply(k, correct=False)
    _apply(k, correct=False)
    assert k.get(OBJ).consecutive_failures == 2  # type: ignore[union-attr]


def test_misconception_suspected_then_confirmed_then_cleared() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    r1 = _apply(k, correct=False, hits=("m1",))
    assert not r1.confirmed_misconceptions  # first hit only suspected
    r2 = _apply(k, correct=False, hits=("m1",))
    assert r2.confirmed_misconceptions == ["m1"]  # second hit confirms
    assert k.get(OBJ).has_confirmed_misconception()  # type: ignore[union-attr]
    r3 = _apply(k, correct=True)
    assert r3.cleared_misconceptions == ["m1"]
    assert not k.get(OBJ).has_confirmed_misconception()  # type: ignore[union-attr]


def test_knowledge_reaches_mastered_and_schedules_review() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    result = None
    for i in range(6):
        result = _apply(k, correct=True, now=float(i + 1))
    obj = k.get(OBJ)
    assert obj is not None and obj.state is MasteryState.MASTERED
    assert obj.memory.next_review_at > 0.0
    assert result is not None and result.newly_mastered is False  # mastered earlier in the loop


def test_due_reviews_lists_overdue_objectives() -> None:
    k = StudentKnowledge("s1")
    obj = k.ensure_objective(OBJ)
    obj.state = MasteryState.MASTERED
    obj.memory = MemoryStrength(stability_s=1.0, last_seen_at=0.0, next_review_at=5.0)
    assert k.due_reviews(now=10.0) == [OBJ]
    assert k.due_reviews(now=1.0) == []


# --------------------------------------------------------------------------- scorer


def _item() -> ItemView:
    return ItemView(
        item_ref="q1",
        objective_code=OBJ,
        prompt={"en": "?"},
        options=("a", "b", "c"),
        correct_option=0,
        option_misconceptions={1: "m1"},
    )


def test_scorer_correct_and_misconception_and_plain_wrong() -> None:
    assert evaluate(_item(), 0) == (Outcome.CORRECT, ())
    assert evaluate(_item(), 1) == (Outcome.INCORRECT, ("m1",))
    assert evaluate(_item(), 2) == (Outcome.INCORRECT, ())


# --------------------------------------------------------------------------- runtime


def _lesson() -> LessonView:
    return LessonView(
        lesson_id="L1",
        objective_code=OBJ,
        title={"en": "T"},
        explanation={"en": "E"},
        worked_example_steps=("step1",),
        practice_items=(_item(),),
        misconception_corrections={"m1": "correction"},
    )


def test_runtime_present_ask_hint_affirm_correct() -> None:
    rt = TemplatedTeachingRuntime()
    lesson = _lesson()
    present = rt.present(lesson, locale="en")
    assert [u.text for u in present] == ["T", "E", "step1"]
    assert rt.ask(_item(), locale="en").text == "?"
    item = ItemView(item_ref="q", objective_code=OBJ, prompt={"en": "?"}, hints=("h0", "h1"))
    assert rt.hint(item, 0, locale="en").text == "h0"  # type: ignore[union-attr]
    assert rt.hint(item, 5) is None  # ladder exhausted (cap)
    assert "correct" in rt.affirm(locale="en").text.lower()
    assert rt.correct(lesson, "m1", locale="en").text == "correction"
    assert "try" in rt.correct(lesson, "unknown", locale="en").text.lower()  # authored fallback


# --------------------------------------------------------------------------- session


def test_session_lifecycle_transitions() -> None:
    s = Session(session_id="x", student_ref="s1")
    s.transition_to(SessionState.LOADING)
    s.transition_to(SessionState.PLANNING)
    s.transition_to(SessionState.TEACHING)
    s.transition_to(SessionState.INTERACTING)
    assert s.state is SessionState.INTERACTING


def test_session_illegal_transition_raises() -> None:
    s = Session(session_id="x", student_ref="s1")
    with pytest.raises(SessionError):
        s.transition_to(SessionState.TEACHING)  # cannot teach straight from CREATED


def test_session_escalation_and_end_reachable() -> None:
    s = Session(session_id="x", student_ref="s1")
    s.transition_to(SessionState.LOADING)
    s.escalate()
    assert s.state is SessionState.ESCALATED
    s2 = Session(session_id="y", student_ref="s1")
    s2.transition_to(SessionState.LOADING)
    s2.pause()
    assert s2.state is SessionState.PAUSED
    s2.end(at=1.0, safely=True)
    assert s2.state is SessionState.ENDED_SAFELY


# --------------------------------------------------------------------------- decision engine


def _graph(*infos: ObjectiveInfo) -> CurriculumGraph:
    return CurriculumGraph(objectives=infos)


def test_select_next_safety_gate_first() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    d = select_next(k, _graph(ObjectiveInfo(OBJ, "L1")), CFG, 1.0, safety_flag=True)
    assert d.kind is DecisionKind.ESCALATE


def test_select_next_teaches_not_started() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    d = select_next(k, _graph(ObjectiveInfo(OBJ, "L1")), CFG, 1.0)
    assert d.kind is DecisionKind.TEACH and d.objective_code == OBJ


def test_select_next_remediates_confirmed_misconception() -> None:
    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    _apply(k, correct=False, hits=("m1",))
    _apply(k, correct=False, hits=("m1",))  # confirm
    d = select_next(k, _graph(ObjectiveInfo(OBJ, "L1")), CFG, 100.0)
    assert d.kind is DecisionKind.REMEDIATE and d.misconception_ref == "m1"


def test_select_next_reviews_due_objective() -> None:
    k = StudentKnowledge("s1")
    obj = k.ensure_objective(OBJ)
    obj.state = MasteryState.MASTERED
    obj.memory = MemoryStrength(stability_s=1.0, last_seen_at=0.0, next_review_at=5.0)
    d = select_next(k, _graph(ObjectiveInfo(OBJ, "L1")), CFG, 10.0)
    assert d.kind is DecisionKind.REVIEW


def test_select_next_completes_when_all_mastered() -> None:
    k = StudentKnowledge("s1")
    obj = k.ensure_objective(OBJ)
    obj.state = MasteryState.MASTERED
    d = select_next(k, _graph(ObjectiveInfo(OBJ, "L1")), CFG, 10.0)
    assert d.kind is DecisionKind.COMPLETE


def test_select_next_diagnoses_downstream_high_uncertainty_prior() -> None:
    k = StudentKnowledge("s1")
    a = k.ensure_objective("A")
    a.state = MasteryState.MASTERED
    k.ensure_objective("B", initial=EST.initial())  # prior 0.3, uncertainty 1.0
    graph = _graph(ObjectiveInfo("A", "LA", (), 0), ObjectiveInfo("B", "LB", ("A",), 1))
    d = select_next(k, graph, CFG, 10.0)
    assert d.kind is DecisionKind.DIAGNOSE and d.objective_code == "B"


def _result(**over: object) -> AttemptResult:
    base: dict[str, object] = {
        "objective_code": OBJ,
        "outcome": Outcome.CORRECT,
        "mastery_before": Mastery(),
        "mastery_after": Mastery(),
        "state_before": MasteryState.IN_PROGRESS,
        "state_after": MasteryState.IN_PROGRESS,
        "newly_mastered": False,
        "confirmed_misconceptions": [],
        "cleared_misconceptions": [],
        "evidence_id": "e",
    }
    base.update(over)
    return AttemptResult(**base)  # type: ignore[arg-type]


def test_post_interaction_advance_continue_remediate_escalate_revise() -> None:
    obj = ObjectiveMastery(OBJ)
    assert post_interaction(obj, _result(newly_mastered=True), CFG).kind is DecisionKind.ADVANCE
    assert post_interaction(obj, _result(), CFG).kind is DecisionKind.CONTINUE
    obj.state = MasteryState.NEEDS_REVIEW
    assert post_interaction(obj, _result(), CFG).kind is DecisionKind.REVISE
    obj2 = ObjectiveMastery(OBJ)
    obj2.consecutive_failures = 4
    assert (
        post_interaction(obj2, _result(outcome=Outcome.INCORRECT), CFG).kind
        is DecisionKind.ESCALATE
    )
    obj3 = ObjectiveMastery(OBJ)
    _apply_conf(obj3)
    assert post_interaction(obj3, _result(), CFG).kind is DecisionKind.REMEDIATE


def _apply_conf(obj: ObjectiveMastery) -> None:
    from taleem_core.contexts.learning.domain.knowledge import MisconceptionRecord
    from taleem_core.contexts.learning.domain.values import MisconceptionState

    obj.misconceptions.append(
        MisconceptionRecord("m1", OBJ, MisconceptionState.CONFIRMED, 2, 0.0, 0.0)
    )


def test_decision_carries_rationale() -> None:
    d = Decision(kind=DecisionKind.TEACH, rationale=())
    assert d.kind is DecisionKind.TEACH


def test_misconception_recurrence_stays_active_and_counted() -> None:
    # CTO H7: a cleared-then-re-hit misconception must become RECURRED, stay active, block mastery,
    # and be surfaced (not silently dropped).
    from taleem_core.contexts.learning.domain.values import MisconceptionState

    k = StudentKnowledge("s1")
    k.ensure_objective(OBJ, initial=EST.initial())
    _apply(k, correct=False, hits=("m1",))  # suspected
    _apply(k, correct=False, hits=("m1",))  # confirmed
    _apply(k, correct=True)  # cleared (m1 not hit)
    assert not k.get(OBJ).has_confirmed_misconception()  # type: ignore[union-attr]

    result = _apply(k, correct=False, hits=("m1",))  # re-hit -> RECURRED
    obj = k.get(OBJ)
    assert obj is not None
    record = obj.misconceptions[0]
    assert record.state is MisconceptionState.RECURRED
    assert record.is_active  # no longer a dead state
    assert obj.has_confirmed_misconception()  # blocks mastery again
    assert "m1" in result.confirmed_misconceptions  # surfaced for remediation + events
