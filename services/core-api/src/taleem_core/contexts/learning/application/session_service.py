"""SessionService — orchestrates the learning-session saga (SESSION_ENGINE.md).

Coordinates the Decision Engine (decides), the Teaching Runtime (teaches), and the KnowledgeService
(remembers). Drives the durable ``SessionState`` machine and emits session-level events. Contains no
learning policy of its own — policy lives in the pure decision engine.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from ....platform import observability
from ....platform.correlation import get_correlation_id
from ....platform.ids import uuid7
from ...learning.domain import events as ev
from ...learning.domain.curriculum_view import ItemView, LessonView
from ...learning.domain.decision import (
    CurriculumGraph,
    Decision,
    DecisionConfig,
    DecisionKind,
    learner_choice,
    post_interaction,
    select_next,
    unmet_prerequisites,
)
from ...learning.domain.events import LearningEvent
from ...learning.domain.knowledge import AttemptResult, StudentKnowledge
from ...learning.domain.runtime import TemplatedTeachingRuntime, Utterance
from ...learning.domain.scorer import Answer, evaluate
from ...learning.domain.session import (
    CHOSEN_BY_ENGINE,
    CHOSEN_BY_LEARNER,
    DecisionRecord,
    Interaction,
    Session,
    SessionError,
    SessionState,
    Turn,
)
from ...learning.domain.values import InteractionContext
from ..adapters.persistence.uow import LearningUnitOfWork
from .knowledge_service import KnowledgeService, RecordOutcome
from .ports import CurriculumReadModel, SessionRepository

_CONTEXT_FOR: dict[DecisionKind, InteractionContext] = {
    DecisionKind.TEACH: InteractionContext.FIRST_EXPOSURE,
    DecisionKind.CONTINUE: InteractionContext.PRACTICE,
    DecisionKind.REVIEW: InteractionContext.SPACED_REVIEW,
    DecisionKind.REMEDIATE: InteractionContext.REMEDIATION,
    DecisionKind.DIAGNOSE: InteractionContext.DIAGNOSTIC,
}


@dataclass
class TurnResult:
    """Outcome of one answered item — drives the trace."""

    result: AttemptResult
    feedback: list[Utterance]
    post_decision: Decision
    events: list[LearningEvent] = field(default_factory=list)


@dataclass(frozen=True)
class PrerequisiteHint:
    """An unmet prerequisite of a learner-chosen lesson, with the title of the lesson that teaches
    it (``None`` when no lesson for it is visible to this reader)."""

    objective_code: str
    title: dict[str, str] | None


@dataclass(frozen=True)
class LearnerChoice:
    """A lesson the learner chose: the recorded decision, the lesson, what the engine would have
    recommended instead, and any prerequisites not yet met (a gentle hint, never a block)."""

    decision: Decision
    lesson: LessonView
    recommended: Decision
    unmet: tuple[PrerequisiteHint, ...]


class SessionService:
    def __init__(
        self,
        session_repo: SessionRepository,
        knowledge_service: KnowledgeService,
        curriculum: CurriculumReadModel,
        runtime: TemplatedTeachingRuntime,
        graph: CurriculumGraph | Callable[[], CurriculumGraph],
        config: DecisionConfig,
        clock: Callable[[], float],
        uow_factory: Callable[[], LearningUnitOfWork],
    ) -> None:
        self._sessions = session_repo
        self._knowledge = knowledge_service
        self._curriculum = curriculum
        self._runtime = runtime
        # Accept a static graph (slice/tests) or a provider that rebuilds it from published content
        # (the mounted app — reflects newly published lessons). Both keep the engine pure.
        self._graph_source = graph
        self._config = config
        self._now = clock
        self._uow = uow_factory

    # -- lifecycle ------------------------------------------------------------------------

    def get_session(self, session_id: str) -> Session | None:
        """Public session lookup (avoids adapters reaching into the private repository)."""
        return self._sessions.get(session_id)

    def start(self, student_ref: str, correlation_id: str = "") -> Session:
        now = self._now()
        # Thread the request correlation id into the saga (CTO H9) when the caller didn't pass one.
        cid = correlation_id or (get_correlation_id() or "")
        session = Session(
            session_id=uuid7(),
            student_ref=student_ref,
            started_at=now,
            correlation_id=cid,
        )
        session.transition_to(SessionState.LOADING)
        session.transition_to(SessionState.PLANNING)
        self._sessions.save(session)
        self._emit([ev.session_started(session.session_id, student_ref, now)])
        observability.record_event("taleem_sessions_started_total")
        observability.log_event("session_started", session_id=session.session_id)
        return session

    def plan_next(self, session: Session, *, safety_flag: bool = False) -> Decision:
        # A not-yet-persisted learner still gets a plan: an empty knowledge yields first-exposure
        # teaching for the entry objective (the first attempt then persists their knowledge).
        # Objective state only: the decision engine never reads the evidence history.
        knowledge = self._knowledge.snapshot(
            session.student_ref, include_evidence=False
        ) or StudentKnowledge(student_ref=session.student_ref)
        graph = self._graph_source() if callable(self._graph_source) else self._graph_source
        now = self._now()
        decision = select_next(knowledge, graph, self._config, now, safety_flag=safety_flag)
        session.record_decision(
            DecisionRecord(
                kind=decision.kind.value,
                objective_code=decision.objective_code,
                chosen_by=CHOSEN_BY_ENGINE,
                rationale=tuple(r.note for r in decision.rationale),
                at=now,
            )
        )
        if decision.kind in _CONTEXT_FOR:
            session.transition_to(SessionState.TEACHING)
            self._sessions.save(session)
        elif decision.kind is DecisionKind.ESCALATE:
            session.escalate()
            self._sessions.save(session)
        return decision

    def choose(self, session: Session, objective_code: str) -> LearnerChoice | None:
        """Plan a lesson the LEARNER chose (a lesson row / a remediation link) instead of the
        engine's pick. ``None`` when no published lesson for it is visible to this reader (the
        read model's cohort filter applies: a cross-cohort or unpublished lesson is not found).

        The engine still recommends — its pick is returned and recorded in the rationale — but it
        never blocks the choice. Unmet prerequisites are returned as a hint, not a gate.
        """
        lesson = self._curriculum.lesson_for(objective_code)
        if lesson is None:
            return None
        if session.state in (SessionState.PLANNING, SessionState.RECORDING):
            session.transition_to(SessionState.TEACHING)
        elif session.state is not SessionState.TEACHING:
            raise SessionError(f"cannot choose a lesson from {session.state}")
        now = self._now()
        knowledge = self._knowledge.snapshot(
            session.student_ref, include_evidence=False
        ) or StudentKnowledge(student_ref=session.student_ref)
        graph = self._graph_source() if callable(self._graph_source) else self._graph_source
        recommended = select_next(knowledge, graph, self._config, now)
        unmet = unmet_prerequisites(knowledge, lesson.prerequisites)
        decision = learner_choice(objective_code, unmet=unmet, recommended=recommended)
        session.record_decision(
            DecisionRecord(
                kind=decision.kind.value,
                objective_code=objective_code,
                chosen_by=CHOSEN_BY_LEARNER,
                rationale=tuple(r.note for r in decision.rationale),
                at=now,
            )
        )
        self._sessions.save(session)
        hints = tuple(PrerequisiteHint(code, self._title_of(code)) for code in unmet)
        return LearnerChoice(decision=decision, lesson=lesson, recommended=recommended, unmet=hints)

    def teach(self, session: Session, decision: Decision) -> tuple[list[Utterance], LessonView]:
        lesson = self._curriculum.lesson_for(decision.objective_code or "")
        if lesson is None:
            raise ValueError(f"no published lesson for objective {decision.objective_code}")
        utterances = self._runtime.present(lesson)
        session.transition_to(SessionState.INTERACTING)
        self._sessions.save(session)
        return utterances, lesson

    def ask(self, item: ItemView) -> Utterance:
        return self._runtime.ask(item)

    def hint(self, item: ItemView, level: int) -> Utterance | None:
        return self._runtime.hint(item, level)

    def submit_answer(
        self,
        session: Session,
        lesson: LessonView,
        item: ItemView,
        *,
        answer: Answer | None = None,
        answer_option: int | None = None,
        decision_kind: DecisionKind,
        hints_used: int,
        self_confidence: float | None,
    ) -> TurnResult:
        """Score one answer, update knowledge, record the interaction (stays in INTERACTING).

        ``answer`` is any kind's answer; ``answer_option`` (a chosen option index) is the
        pre-contract shape, kept for choose items. Exactly one is given. Raises
        ``AnswerKindMismatchError`` if the answer does not fit the item's kind.
        """
        if (answer is None) == (answer_option is None):
            raise ValueError("pass exactly one of answer / answer_option")
        given = answer if answer is not None else Answer(option=answer_option)
        now = self._now()
        outcome, misconception_hits = evaluate(item, given)
        context = _CONTEXT_FOR.get(decision_kind, InteractionContext.PRACTICE)

        recorded: RecordOutcome = self._knowledge.record_attempt(
            student_ref=session.student_ref,
            objective_code=item.objective_code,
            item_ref=item.item_ref,
            session_id=session.session_id,
            correct=outcome.value == "correct",
            misconception_hits=misconception_hits,
            hints_used=hints_used,
            response_time_ms=0,
            context=context,
            self_confidence=self_confidence,
            lesson_id=lesson.lesson_id,
            lesson_version=lesson.version,
        )
        result = recorded.result

        feedback: list[Utterance] = []
        if outcome.value == "correct":
            feedback.append(self._runtime.affirm())
        else:
            for ref in misconception_hits:
                feedback.append(self._runtime.correct(lesson, ref))

        # Record the interaction (append-only within the session).
        knowledge = self._knowledge.snapshot(session.student_ref, include_evidence=False)
        obj = knowledge.get(item.objective_code) if knowledge else None
        post = (
            post_interaction(obj, result, self._config)
            if obj is not None
            else Decision(kind=DecisionKind.CONTINUE)
        )
        session.add_interaction(
            Interaction(
                interaction_id=uuid7(),
                objective_code=item.objective_code,
                decision_kind=decision_kind.value,
                turns=[
                    Turn("student", "answer", given.summary(), now),
                    *[Turn("tutor", u.kind.value, u.text, now) for u in feedback],
                ],
                outcome=outcome.value,
                evidence_id=result.evidence_id,
                occurred_at=now,
                chosen_by=(
                    CHOSEN_BY_LEARNER
                    if session.learner_chosen_objective == item.objective_code
                    else CHOSEN_BY_ENGINE
                ),
            )
        )
        self._sessions.save(session)
        return TurnResult(
            result=result, feedback=feedback, post_decision=post, events=recorded.events
        )

    def complete_objective(self, session: Session) -> None:
        """Walk the per-objective close-out phase of the saga."""
        for state in (
            SessionState.ASSESSING,
            SessionState.UPDATING,
            SessionState.SCHEDULING,
            SessionState.RECORDING,
        ):
            session.transition_to(state)
        self._sessions.save(session)

    def end(self, session: Session) -> Session:
        now = self._now()
        if session.state is SessionState.RECORDING:
            session.transition_to(SessionState.ENDED)
            session.ended_at = now
        else:
            session.end(now)
        self._sessions.save(session)
        self._emit([ev.session_completed(session.session_id, session.student_ref, now)])
        observability.record_event("taleem_sessions_completed_total")
        return session

    # -- internals ------------------------------------------------------------------------

    def _title_of(self, objective_code: str) -> dict[str, str] | None:
        lesson = self._curriculum.lesson_for(objective_code)
        if lesson is None:
            return None
        title = {k: v for k, v in lesson.title.items() if v}
        return title or None

    def _emit(self, events: Sequence[LearningEvent]) -> None:
        with self._uow() as uow:
            uow.events.publish(events)
            uow.commit()
