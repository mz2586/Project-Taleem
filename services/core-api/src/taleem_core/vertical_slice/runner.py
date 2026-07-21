"""End-to-end vertical-slice runner (Phase 4.1).

Wires the *real* subsystems together for one lesson and one synthetic learner, and produces a
complete execution trace of every step:

  Curriculum Studio (author → publish)  →  Learning: load student → decide → teach → interact →
  assess → update knowledge → schedule revision → analytics → end session.

No mocks: Curriculum Studio persists to its SQLAlchemy store; the learning Student Knowledge Model,
evidence, and events persist to the learning SQLAlchemy store; the teaching runtime is the real
templated (no-LLM) tier operating strictly on approved content.

Run as a script to print the trace:  ``python -m taleem_core.vertical_slice.runner``
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    Base as CurriculumBase,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    create_db_engine as create_curriculum_engine,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    create_session_factory as create_curriculum_sf,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    unit_of_work as curriculum_uow,
)
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.contexts.learning.adapters.curriculum_read_model import CurriculumStudioReadModel
from taleem_core.contexts.learning.adapters.memory import InMemorySessionRepository
from taleem_core.contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.learning.application.analytics import LearningAnalytics
from taleem_core.contexts.learning.application.knowledge_service import KnowledgeService
from taleem_core.contexts.learning.application.session_service import SessionService
from taleem_core.contexts.learning.domain.decision import (
    CurriculumGraph,
    DecisionConfig,
    DecisionKind,
    ObjectiveInfo,
)
from taleem_core.contexts.learning.domain.estimator import BKTEstimator
from taleem_core.contexts.learning.domain.forgetting import HalfLifeForgettingModel
from taleem_core.contexts.learning.domain.runtime import TemplatedTeachingRuntime

from .fractions_lesson import LESSON_KEY, OBJECTIVE_CODE, build_fractions_lesson

REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]
STUDENT_REF = "stu-0001"  # synthetic, pseudonymous — no real child data (governance-safe)
MAX_PRACTICE = 12  # safety cap on the mastery loop


@dataclass
class Trace:
    steps: list[dict[str, Any]] = field(default_factory=list)

    def add(self, step: str, **detail: Any) -> None:
        self.steps.append({"step": step, **detail})

    def render(self) -> str:
        lines = ["=" * 72, "PROJECT TALEEM — VERTICAL SLICE EXECUTION TRACE", "=" * 72]
        for i, s in enumerate(self.steps, 1):
            head = f"{i:>2}. {s['step']}"
            detail = {k: v for k, v in s.items() if k != "step"}
            lines.append(head)
            for k, v in detail.items():
                lines.append(f"      {k}: {v}")
        return "\n".join(lines)


def _make_clock() -> Callable[[], float]:
    t = [1000.0]

    def clock() -> float:
        t[0] += 1.0
        return t[0]

    return clock


@dataclass
class SliceWiring:
    """The fully-wired, real subsystems + the published lesson info (no mocks)."""

    session_service: SessionService
    knowledge_service: KnowledgeService
    analytics: LearningAnalytics
    read_model: CurriculumStudioReadModel
    published_version: int
    gates_green: bool


def wire(clock: Callable[[], float]) -> SliceWiring:
    """Author + publish the lesson through Curriculum Studio and wire the learning platform.

    Both contexts use their real SQLAlchemy persistence (independent in-memory SQLite stores);
    the learning teaching runtime is the real templated tier. Shared by runner and API tests.
    """
    # Curriculum Studio: author + publish the original lesson through its SQL persistence.
    cs_engine = create_curriculum_engine("sqlite://")
    CurriculumBase.metadata.create_all(cs_engine)
    cs_sf = create_curriculum_sf(cs_engine)

    def cs_op(fn: Callable[[CurriculumStudioService], Any]) -> Any:
        with curriculum_uow(cs_sf) as uow:
            service = CurriculumStudioService(uow.lessons, uow.publish, clock=clock)
            result = fn(service)
            uow.commit()
            return result

    def _review_step(role: str) -> Callable[[CurriculumStudioService], Any]:
        return lambda s: s.review(LESSON_KEY, ReviewAction.APPROVE, role)

    cs_op(lambda s: s.create(build_fractions_lesson()))
    cs_op(lambda s: s.submit(LESSON_KEY, "subject_author"))
    for role in REVIEW_ROLES:
        cs_op(_review_step(role))
    published = cs_op(lambda s: s.publish(LESSON_KEY, "curriculum_architect", "v1"))

    # Learning platform.
    l_engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(l_engine)
    l_sf = create_learning_session_factory(l_engine)

    def luow() -> LearningUnitOfWork:
        return LearningUnitOfWork(l_sf)

    knowledge_service = KnowledgeService(luow, BKTEstimator(), HalfLifeForgettingModel(), clock)
    read_model = CurriculumStudioReadModel(cs_sf)
    session_service = SessionService(
        InMemorySessionRepository(),
        knowledge_service,
        read_model,
        TemplatedTeachingRuntime(),
        CurriculumGraph(objectives=(ObjectiveInfo(OBJECTIVE_CODE, LESSON_KEY, (), 0),)),
        DecisionConfig(),
        clock,
        luow,
    )
    return SliceWiring(
        session_service=session_service,
        knowledge_service=knowledge_service,
        analytics=LearningAnalytics(luow),
        read_model=read_model,
        published_version=published.version,
        gates_green=all(g.passed for g in published.quality_gate_results),
    )


def run_slice() -> dict[str, Any]:
    """Execute the full flow and return {trace, summary, decision_flow, mastered}."""
    trace = Trace()
    clock = _make_clock()

    w = wire(clock)
    session_service = w.session_service
    knowledge_service = w.knowledge_service
    analytics = w.analytics
    trace.add(
        "Curriculum Studio: created draft lesson", lesson=LESSON_KEY, objective=OBJECTIVE_CODE
    )
    trace.add("Curriculum Studio: submitted + 5-gate review chain approved")
    trace.add(
        "Curriculum Studio: PUBLISHED immutable version",
        version=w.published_version,
        gates_green=w.gates_green,
    )
    decision_flow: list[str] = []

    # ---- 2a. Load student (cold-start) ------------------------------------------------
    knowledge_service.ensure_student(STUDENT_REF, [OBJECTIVE_CODE])
    snap = knowledge_service.snapshot(STUDENT_REF)
    obj0 = snap.get(OBJECTIVE_CODE) if snap else None
    trace.add(
        "Learning: loaded student (cold-start)",
        student=STUDENT_REF,
        initial_mastery=round(obj0.mastery.value, 3) if obj0 else None,
        initial_state=obj0.state.value if obj0 else None,
    )

    # ---- 3. Start session -------------------------------------------------------------
    session = session_service.start(STUDENT_REF)
    trace.add("Session: started", session_id=session.session_id, state=session.state.value)

    # ---- 4. Decide next -> teach ------------------------------------------------------
    decision = session_service.plan_next(session)
    decision_flow.append(decision.kind.value)
    trace.add(
        "Decision Engine: select next",
        decision=decision.kind.value,
        objective=decision.objective_code,
        rationale=decision.rationale[0].note if decision.rationale else "",
    )
    utterances, lesson_view = session_service.teach(session, decision)
    trace.add(
        "AI Teaching Runtime: taught concept (approved content only, templated tier)",
        utterances=len(utterances),
        first=utterances[1].text if len(utterances) > 1 else "",
        session_state=session.state.value,
    )

    items = {it.item_ref: it for it in lesson_view.practice_items}

    def answer(item_ref: str, option: int, kind: DecisionKind, hints_used: int, conf: float) -> Any:
        item = items[item_ref]
        return session_service.submit_answer(
            session,
            lesson_view,
            item,
            answer_option=option,
            decision_kind=kind,
            hints_used=hints_used,
            self_confidence=conf,
        )

    # ---- 5-7. Interact / assess / update / decide (scripted synthetic learner) --------
    # p1 correct
    r = answer("p1-one-of-four", 0, DecisionKind.TEACH, 0, 0.9)
    decision_flow.append(r.post_decision.kind.value)
    trace.add(
        "Interact: p1 answered correctly",
        outcome=r.result.outcome.value,
        mastery=round(r.result.mastery_after.value, 3),
        post=r.post_decision.kind.value,
    )
    # p2 wrong (triggers misconception) — hint shown
    hint = session_service.hint(items["p2-compare-half-quarter"], 0)
    r = answer("p2-compare-half-quarter", 1, DecisionKind.CONTINUE, 1, 0.4)
    trace.add(
        "Interact: p2 answered wrong (misconception suspected); hint given",
        hint=hint.text if hint else "",
        misconceptions=[m.state.value for m in _obj(knowledge_service).misconceptions],
    )
    # p2 wrong again -> misconception CONFIRMED -> MisconceptionDetected event
    r = answer("p2-compare-half-quarter", 1, DecisionKind.CONTINUE, 2, 0.4)
    decision_flow.append(r.post_decision.kind.value)
    trace.add(
        "Detect misconception: CONFIRMED",
        confirmed=r.result.confirmed_misconceptions,
        events=[e.event_type for e in r.events],
        post=r.post_decision.kind.value,
    )
    # Remediate: deliver the authored correction, then re-attempt correctly -> CLEARED
    correction = session_service._runtime.correct(  # noqa: SLF001 (slice inspects for the trace)
        lesson_view, r.result.confirmed_misconceptions[0]
    )
    trace.add("Remediate: authored correction delivered", correction=correction.text)
    r = answer("p2-compare-half-quarter", 0, DecisionKind.REMEDIATE, 0, 0.8)
    trace.add(
        "Interact: p2 re-attempted correctly -> misconception CLEARED",
        cleared=r.result.cleared_misconceptions,
        events=[e.event_type for e in r.events],
    )
    # Remaining practice + mastery loop
    remaining = ["p3-denominator", "p4-write-half", "p5-three-of-four"]
    cycle = remaining + ["p1-one-of-four", "p3-denominator", "p4-write-half", "p5-three-of-four"]
    mastered = False
    for idx, ref in enumerate(cycle):
        if idx >= MAX_PRACTICE:
            break
        r = answer(ref, 0, DecisionKind.CONTINUE, 0, 0.9)
        if r.post_decision.kind is DecisionKind.ADVANCE:
            mastered = True
            trace.add(
                "Update Knowledge: objective MASTERED",
                item=ref,
                mastery=round(r.result.mastery_after.value, 3),
                uncertainty=round(r.result.mastery_after.uncertainty, 3),
                newly_mastered=r.result.newly_mastered,
                events=[e.event_type for e in r.events],
            )
            break

    # ---- 8. Revision scheduled (set when mastered) ------------------------------------
    obj = _obj(knowledge_service)
    trace.add(
        "Revision Scheduler: next review computed",
        next_review_at=round(obj.memory.next_review_at, 1),
        stability_s=round(obj.memory.stability_s, 1),
        state=obj.state.value,
    )

    # ---- 9. Complete objective + decide again -----------------------------------------
    session_service.complete_objective(session)
    final_decision = session_service.plan_next(session)
    decision_flow.append(final_decision.kind.value)
    trace.add(
        "Decision Engine: after mastery",
        decision=final_decision.kind.value,
        note=final_decision.rationale[0].note if final_decision.rationale else "",
    )

    # ---- 10. Analytics + end session --------------------------------------------------
    summary = analytics.progress_summary(STUDENT_REF)
    trace.add("Learning Analytics: progress summary", **summary.to_dict())
    session_service.end(session)
    trace.add("Session: ended", state=session.state.value, interactions=len(session.interactions))

    return {
        "trace": trace,
        "summary": summary.to_dict(),
        "decision_flow": decision_flow,
        "mastered": mastered,
        "session_state": session.state.value,
        "final_decision": final_decision.kind.value,
    }


def _obj(knowledge_service: KnowledgeService) -> Any:
    snap = knowledge_service.snapshot(STUDENT_REF)
    obj = snap.get(OBJECTIVE_CODE) if snap else None
    if obj is None:
        raise RuntimeError("student knowledge not initialized")
    return obj


def main() -> None:  # pragma: no cover - CLI entry
    result = run_slice()
    print(result["trace"].render())
    print("\nDECISION FLOW:", " -> ".join(result["decision_flow"]))
    print("MASTERED:", result["mastered"], "| SESSION:", result["session_state"])


if __name__ == "__main__":  # pragma: no cover
    main()
