"""AI Teacher — templated, curriculum-grounded, explainable teaching orchestration (Phase 8).

The AI Teacher is **not** a generative model. It is a deterministic orchestration over content and
components that already exist — the templated ``TemplatedTeachingRuntime`` (approved content), the
pure decision engine, the Student Knowledge model, and the scorer. Every utterance it emits is
**grounded** in the supplied ``LessonView`` (or a fixed system phrase); it can never source new
curriculum or invent a fact (audit AR-C-06 — no generative AI to children; the offline tier is the
same). Personalization is expressed as deterministic *arrangement* of authored content and
*selection* of next steps — fully explainable, with a rationale and a calibrated confidence.

This module is pure (no I/O); the application service wires it to the read model + knowledge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .curriculum_view import ItemView, LessonView
from .decision import CurriculumGraph, Decision, DecisionConfig, DecisionKind, select_next
from .knowledge import StudentKnowledge
from .runtime import TemplatedTeachingRuntime, Utterance
from .values import Mastery, MasteryState

# Fixed system phrases the runtime may emit (affirmations / generic re-try). Grounded by whitelist —
# they are templated platform text, not free generation. Kept in sync with runtime.affirm/correct.
_SYSTEM_PHRASES: frozenset[str] = frozenset(
    {
        "بہت خوب! یہ درست ہے۔",
        "Well done! That's correct.",
        "آئیے دوبارہ کوشش کرتے ہیں۔",
        "Let's try that again.",
    }
)


class ExplanationStyle(StrEnum):
    """A deterministic *arrangement* of authored content — never new content."""

    DIRECT = "direct"  # title + explanation
    WORKED_EXAMPLE_LED = "worked_example_led"  # title + explanation + worked steps (explain, show)
    CONCRETE_TO_ABSTRACT = (
        "concrete_to_abstract"  # title + worked steps + explanation (show, then rule)
    )
    QUESTION_LED = "question_led"  # title + a leading question + explanation + worked steps


class TeacherConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class GuardrailReport:
    """The AI Teacher's self-certification for a response — the explainable safety envelope."""

    grounded: bool  # every emitted utterance is authored content or a system phrase
    generative: bool  # always False in this tier (templated)
    source: str  # "authored"
    age_appropriate: bool
    reveals_answer: bool  # always False (no answer keys are ever emitted)
    within_curriculum: bool  # the objective is a published, in-scope objective
    escalate: bool
    escalate_reason: str
    confidence: TeacherConfidence

    def to_dict(self) -> dict[str, object]:
        return {
            "grounded": self.grounded,
            "generative": self.generative,
            "source": self.source,
            "age_appropriate": self.age_appropriate,
            "reveals_answer": self.reveals_answer,
            "within_curriculum": self.within_curriculum,
            "escalate": self.escalate,
            "escalate_reason": self.escalate_reason,
            "confidence": self.confidence.value,
        }


@dataclass(frozen=True)
class StyledExplanation:
    objective_code: str
    style: ExplanationStyle
    utterances: tuple[Utterance, ...]
    confidence: TeacherConfidence
    guardrail: GuardrailReport
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class WeakTopic:
    objective_code: str
    state: MasteryState
    mastery: float
    active_misconceptions: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class PracticeItem:
    objective_code: str
    difficulty: str
    confidence: TeacherConfidence


@dataclass(frozen=True)
class AdaptivePlan:
    next_action: Decision
    weak_topics: tuple[WeakTopic, ...]
    revision_due: tuple[str, ...]
    practice: tuple[PracticeItem, ...]
    confidence: TeacherConfidence
    rationale: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------- confidence


def confidence_from(mastery: Mastery, attempts: int) -> TeacherConfidence:
    """Calibrated teacher-confidence in the learner's state — grounded in the BKT uncertainty.

    High only when the estimate is precise *and* backed by evidence; low when we have little
    evidence or the estimate is wide (the honest default).
    """
    if attempts <= 0 or mastery.uncertainty >= 0.6:
        return TeacherConfidence.LOW
    if mastery.uncertainty <= 0.2 and attempts >= 3:
        return TeacherConfidence.HIGH
    return TeacherConfidence.MEDIUM


# ---------------------------------------------------------------- explanation style


def choose_style(grade_band: str, attempts: int, last_incorrect: bool) -> ExplanationStyle:
    """Pick an explanation style deterministically from the learner's state (explainable policy)."""
    if last_incorrect:
        return ExplanationStyle.CONCRETE_TO_ABSTRACT  # re-teach concretely after an error
    if grade_band == "early":
        return ExplanationStyle.WORKED_EXAMPLE_LED  # younger learners: show alongside telling
    if grade_band == "senior" and attempts > 0:
        return ExplanationStyle.QUESTION_LED  # stronger learners: prompt retrieval first
    return ExplanationStyle.DIRECT


def _title(lesson: LessonView, locale: str) -> Utterance:
    from .runtime import TurnKind

    return Utterance(TurnKind.PRESENT, lesson.title.get(locale, lesson.title.get("en", "")), locale)


def _leading_question(lesson: LessonView, locale: str) -> Utterance | None:
    from .runtime import TurnKind

    for item in lesson.practice_items:
        prompt = item.prompt.get(locale, item.prompt.get("en", ""))
        if prompt:
            return Utterance(TurnKind.ASK, prompt, locale)  # the question only — never the answer
    return None


def explain(
    lesson: LessonView,
    style: ExplanationStyle,
    runtime: TemplatedTeachingRuntime,
    locale: str = "ur",
) -> tuple[Utterance, ...]:
    """Arrange the runtime's authored utterances into the chosen style. No new content is made."""
    present = runtime.present(lesson, locale)  # [title, explanation, *worked_steps]
    title = present[0] if present else _title(lesson, locale)
    explanation = present[1] if len(present) > 1 else None
    worked = tuple(present[2:])

    if style is ExplanationStyle.DIRECT:
        return tuple(u for u in (title, explanation) if u is not None)
    if style is ExplanationStyle.WORKED_EXAMPLE_LED:
        return tuple(u for u in (title, explanation, *worked) if u is not None)
    if style is ExplanationStyle.CONCRETE_TO_ABSTRACT:
        return tuple(u for u in (title, *worked, explanation) if u is not None)
    # QUESTION_LED
    question = _leading_question(lesson, locale)
    return tuple(u for u in (title, question, explanation, *worked) if u is not None)


# ---------------------------------------------------------------- guardrails


def _authored_texts(lesson: LessonView) -> set[str]:
    """Every text the teacher is allowed to emit for this lesson (the grounding set)."""
    texts: set[str] = set()
    texts.update(lesson.title.values())
    texts.update(lesson.explanation.values())
    texts.update(lesson.worked_example_steps)
    texts.update(lesson.misconception_corrections.values())
    pools: tuple[tuple[ItemView, ...], ...] = (
        lesson.practice_items,
        lesson.homework_items,
        lesson.assessment_formative,
        lesson.assessment_summative,
    )
    for pool in pools:
        for item in pool:
            texts.update(item.prompt.values())
            texts.update(item.hints)
    return texts


def is_grounded(lesson: LessonView, utterances: tuple[Utterance, ...]) -> bool:
    """True iff every utterance is authored lesson content or a fixed system phrase."""
    allowed = _authored_texts(lesson) | set(_SYSTEM_PHRASES)
    return all(u.text in allowed for u in utterances)


def guardrail_report(
    lesson: LessonView,
    utterances: tuple[Utterance, ...],
    *,
    confidence: TeacherConfidence,
    age_appropriate: bool,
    escalate: bool,
    escalate_reason: str,
) -> GuardrailReport:
    """Self-certify a response: grounded, non-generative, in-curriculum, no-answer, age-ok."""
    return GuardrailReport(
        grounded=is_grounded(lesson, utterances),
        generative=False,
        source="authored",
        age_appropriate=age_appropriate,
        reveals_answer=False,
        within_curriculum=bool(lesson.objective_code),
        escalate=escalate,
        escalate_reason=escalate_reason,
        confidence=confidence,
    )


# ---------------------------------------------------------------- adaptive plan


def recommended_difficulty(state: MasteryState, mastery: Mastery) -> str:
    """Map a learner's objective state to the next appropriate difficulty band."""
    if state is MasteryState.NOT_STARTED:
        return "INTRO"
    if state is MasteryState.MASTERED:
        return "STRETCH"
    if state in (MasteryState.NEEDS_REVIEW, MasteryState.AT_RISK):
        return "CORE"
    # IN_PROGRESS: INTRO while shaky, CORE once the estimate is climbing.
    return "INTRO" if mastery.value < 0.5 else "CORE"


_WEAK_STATES = (MasteryState.IN_PROGRESS, MasteryState.NEEDS_REVIEW, MasteryState.AT_RISK)


def adaptive_plan(
    knowledge: StudentKnowledge,
    graph: CurriculumGraph,
    config: DecisionConfig,
    now: float,
) -> AdaptivePlan:
    """Compose weak-topic detection, revision planning, and personalized practice (over engine)."""
    next_action = select_next(knowledge, graph, config, now)

    weak: list[WeakTopic] = []
    for code, obj in knowledge.objectives.items():
        active = tuple(m.misconception_ref for m in obj.active_misconceptions())
        if obj.state in _WEAK_STATES or active:
            reason = (
                "active misconception"
                if active
                else (
                    "retention at risk" if obj.state is MasteryState.AT_RISK else "still learning"
                )
            )
            weak.append(
                WeakTopic(
                    objective_code=code,
                    state=obj.state,
                    mastery=obj.mastery.value,
                    active_misconceptions=active,
                    reason=reason,
                )
            )
    weak.sort(key=lambda w: (w.mastery, w.objective_code))  # weakest first, deterministic

    revision = tuple(knowledge.due_reviews(now))

    practice: list[PracticeItem] = []
    for info in graph.objectives:
        ob = knowledge.get(info.objective_code)
        state = ob.state if ob else MasteryState.NOT_STARTED
        mastery = ob.mastery if ob else Mastery()
        attempts = ob.attempts if ob else 0
        practice.append(
            PracticeItem(
                objective_code=info.objective_code,
                difficulty=recommended_difficulty(state, mastery),
                confidence=confidence_from(mastery, attempts),
            )
        )

    overall = _overall_confidence(knowledge)
    rationale = (
        f"next: {next_action.kind.value}",
        f"weak topics: {len(weak)}",
        f"revision due: {len(revision)}",
    )
    return AdaptivePlan(
        next_action=next_action,
        weak_topics=tuple(weak),
        revision_due=revision,
        practice=tuple(practice[:10]),
        confidence=overall,
        rationale=rationale,
    )


def _overall_confidence(knowledge: StudentKnowledge) -> TeacherConfidence:
    if not knowledge.objectives:
        return TeacherConfidence.LOW
    lows = 0
    highs = 0
    for obj in knowledge.objectives.values():
        c = confidence_from(obj.mastery, obj.attempts)
        lows += c is TeacherConfidence.LOW
        highs += c is TeacherConfidence.HIGH
    if lows >= highs and lows > 0:
        return (
            TeacherConfidence.LOW
            if lows > len(knowledge.objectives) / 2
            else TeacherConfidence.MEDIUM
        )
    return TeacherConfidence.HIGH if highs > lows else TeacherConfidence.MEDIUM


# ---------------------------------------------------------------- offline capabilities


def offline_capabilities() -> dict[str, str]:
    """What the AI Teacher can do offline vs what needs connectivity (Phase 8 WS5).

    Everything the teacher *says* is templated + packaged, so teaching works fully offline. Only the
    server-derived / delivery concerns degrade — gracefully, with honest messaging.
    """
    return {
        "lesson_explanation": "available",  # packaged LessonView
        "guided_teaching": "available",
        "step_by_step_tutoring": "available",
        "hints": "available",  # authored, packaged
        "misconception_correction": "available",  # authored, packaged
        "encouragement": "available",
        "grading": "queued",  # server-side; offline attempts queue + sync (6.2B)
        "adaptive_plan": "cached",  # server-derived; cached read model, refreshed on reconnect
        "confidence_indicator": "available",  # from cached mastery snapshot
        "mentor_escalation": "queued",  # flag on reconnect; on-site mentor immediate in pilot
        "generative_rephrasing": "disabled_offline",  # no generative AI offline, ever (AR-C-06)
    }


def escalation_for(
    decision: Decision, consecutive_failures: int, threshold: int = 3
) -> tuple[bool, str]:
    """Decide whether the teacher should hand off to a human, with a reason (explainable)."""
    if decision.kind is DecisionKind.ESCALATE:
        return True, "decision engine requested escalation"
    if consecutive_failures >= threshold:
        return True, f"{consecutive_failures} consecutive failures after help"
    return False, ""
