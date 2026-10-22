"""AI Teacher application service (Phase 8; generative tier Phase D).

Wires the pure AI Teacher orchestration (`domain/ai_teacher.py`) to existing components: the
SessionService (in-flight session), the CurriculumReadModel (published `LessonView` — the grounding
boundary), the KnowledgeService (mastery snapshot), the templated runtime, and the decision graph.
No new child-data table; every output is derived and explainable.

Phase D adds an optional **generative tier** (``GenerativeTier``) that may *rephrase* the authored
explanation. It runs only when ALL of these hold, checked in this order on every request:

1. the ``ai_teacher.generative_rephrase`` feature flag is on (default OFF) — with it off nothing
   else is consulted and the response is byte-identical to the templated tier;
2. the kill switch is not engaged;
3. the learner is not being escalated to a human (a struggling child gets a person, not a model);
4. the learner's guardian has live ``ai_teaching`` consent (read on every request, fail closed);
5. the learner's per-period inference quota is not exhausted (exhaustion => templated engine).

The rephrase is built only from LessonView fields, checked by the safety gate, and on any failure
(refusal, provider error) the authored response is served unchanged. Generated text is returned in a
separate ``generation`` block marked ``generated: true`` / ``verified: false`` with its provenance
and a notice key the client must display — never mixed into the verified ``utterances``. No real
provider exists in this build (FD-03); see ``ports/llm_inert.py``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ....platform.feature_flags import FlagProvider
from ....platform.logging import DEFAULT_ALLOW, StructuredLogger
from ....platform.metrics import registry
from ....ports.llm import (
    CostMeter,
    InMemoryCostLedger,
    LearnerQuota,
    LearnerUsageLedger,
    LLMGateway,
    LLMRequest,
    Tier,
    UsageRecord,
    route_tier,
    usage_of,
)
from ...learning.domain import ai_teacher as ait
from ...learning.domain import ai_teacher_gate as gate
from ...learning.domain.curriculum_view import LessonView
from ...learning.domain.decision import CurriculumGraph, DecisionConfig
from ...learning.domain.knowledge import StudentKnowledge
from ...learning.domain.runtime import TemplatedTeachingRuntime, Utterance
from ...learning.domain.values import Mastery
from .knowledge_service import KnowledgeService
from .ports import CurriculumReadModel
from .session_service import SessionService

_GraphSource = CurriculumGraph | Callable[[], CurriculumGraph]

REPHRASE_PURPOSE = "ai_teacher.rephrase"
# The client must show this notice with any generated text: an AI rephrase, not verified fact.
GENERATED_NOTICE_KEY = "ai_teacher.generated_explanation_unverified"


# ---------------------------------------------------------------------------- generative tier


SAFETY_EVENT_FIELDS: tuple[str, ...] = (
    "decision",
    "reason",
    "lesson_id",
    "objective_code",
    "locale",
    "grade_band",
    "provider",
    "tier",
    "dimensions",
    "output_chars",
    "output_sha256",
    "grounding_fields",
    "prompt_tokens",
    "completion_tokens",
    "cost_micros",
)
SAFETY_LOG_ALLOW: frozenset[str] = DEFAULT_ALLOW | frozenset(SAFETY_EVENT_FIELDS)


@dataclass(frozen=True)
class SafetyEvent:
    """One structured record per generative decision. Carries NO generated or learner text.

    No learner identifier either: the correlation id on the log line links an event to its request.
    The output is identified only by a truncated SHA-256, so a reviewer can correlate repeats
    without the log ever holding what was said.
    """

    decision: str  # accepted | refused | unavailable | skipped
    reason: str  # rule ids (refused), error class (unavailable), or the skip reason
    lesson_id: str
    objective_code: str
    locale: str
    grade_band: str
    provider: str = ""
    tier: str = ""
    dimensions: str = ""
    output_chars: int = 0
    output_sha256: str = ""
    grounding_fields: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_micros: int = 0

    def log_fields(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in SAFETY_EVENT_FIELDS}


def logging_safety_sink(logger: StructuredLogger) -> Callable[[SafetyEvent], None]:
    """Emit safety events through the allow-list logger (only declared fields can leave)."""

    def sink(event: SafetyEvent) -> None:
        emit = logger.warn if event.decision in ("refused", "unavailable") else logger.info
        emit("ai_teacher_safety_event", event="ai_teacher_safety_event", **event.log_fields())

    return sink


@dataclass(frozen=True)
class RephraseOutcome:
    status: str  # accepted | refused | unavailable
    text: str  # the accepted rephrase; "" otherwise (refused output is discarded, never stored)
    prompt: gate.GroundedPrompt
    verdict: gate.GateVerdict | None
    provider: str
    tier: Tier
    usage: UsageRecord | None
    error: str = ""
    output_chars: int = 0
    output_sha256: str = ""


def run_rephrase(
    lesson: LessonView,
    utterances: tuple[Utterance, ...],
    gateway: LLMGateway,
    *,
    locale: str,
    grade_band: str,
    cost_meter: CostMeter,
    answer_context: gate.AnswerContext | None = None,
    learner_ref: str = "",
    now: float = 0.0,
) -> RephraseOutcome:
    """Prompt the gateway with LessonView-only grounding, account the call, and gate the output.

    ``learner_ref`` (pseudonymous) attributes the call's cost in the ledger; it is never put in the
    prompt. If grounding cannot be established the model is not called at all.
    """
    tier = route_tier(distress_adjacent=False, difficulty="easy")
    try:
        prompt = gate.build_prompt(lesson, utterances, locale=locale, grade_band=grade_band)
    except gate.UngroundedPromptError:
        empty = gate.GroundedPrompt(lesson.lesson_id, lesson.objective_code, locale, grade_band, ())
        verdict = gate.unverifiable("utterances are not authored lesson content")
        return RephraseOutcome("refused", "", empty, verdict, gateway.name, tier, None)
    if not prompt.passages:
        verdict = gate.unverifiable("no grounding passages")
        return RephraseOutcome("refused", "", prompt, verdict, gateway.name, tier, None)
    request = LLMRequest(prompt=prompt.render(), tier=tier, grounding=prompt.texts)
    try:
        response = gateway.complete(request)
    except Exception as exc:  # any provider failure degrades to authored content
        return RephraseOutcome(
            "unavailable", "", prompt, None, gateway.name, tier, None, type(exc).__name__
        )
    usage = usage_of(response, REPHRASE_PURPOSE, learner_ref=learner_ref, recorded_at=now)
    cost_meter.record(usage)
    verdict = gate.gate(lesson, prompt, response.text, answer_context=answer_context)
    return RephraseOutcome(
        status="accepted" if verdict.accepted else "refused",
        text=response.text.strip() if verdict.accepted else "",
        prompt=prompt,
        verdict=verdict,
        provider=response.provider,
        tier=response.tier,
        usage=usage,
        output_chars=len(response.text),
        output_sha256=hashlib.sha256(response.text.encode("utf-8")).hexdigest()[:16],
    )


@dataclass(frozen=True)
class GenerativeTier:
    """Everything the optional rephrase tier needs. Absent => the templated tier only."""

    gateway: LLMGateway
    flags: FlagProvider
    ai_teaching_consent: Callable[[str], bool]  # live per-request read of the ai_teaching scope
    kill_switch_engaged: Callable[[], bool]
    cost_meter: LearnerUsageLedger = field(default_factory=InMemoryCostLedger)
    safety_events: Callable[[SafetyEvent], None] | None = None
    # Per-learner inference budget (keeps the free tier sustainable). None => unlimited (tests).
    quota: LearnerQuota | None = None

    def quota_exhausted(self, student_ref: str, now: float) -> bool:
        if self.quota is None:
            return False
        used = self.cost_meter.usage_for(student_ref, since=self.quota.period_start(now))
        return self.quota.exhausted(used)

    def enabled_for(self, student_ref: str) -> bool:
        return self.flags.is_enabled(gate.GENERATIVE_FLAG, context=f"student:{student_ref}")


def _fail_closed(check: Callable[[], bool], *, default: bool) -> bool:
    """Run a gating check; if it cannot be evaluated, take the safe answer."""
    try:
        return bool(check())
    except Exception:  # a broken check must never open the gate
        return default


# ---------------------------------------------------------------------------- service


class AITeacherService:
    """Curriculum-grounded, explainable teaching over existing components.

    Templated by default; the optional generative tier only rephrases, behind flag + consent + kill
    switch + safety gate.
    """

    def __init__(
        self,
        sessions: SessionService,
        knowledge_service: KnowledgeService,
        curriculum: CurriculumReadModel,
        runtime: TemplatedTeachingRuntime,
        graph: _GraphSource,
        config: DecisionConfig,
        clock: Callable[[], float],
        *,
        generative: GenerativeTier | None = None,
    ) -> None:
        self._sessions = sessions
        self._knowledge = knowledge_service
        self._curriculum = curriculum
        self._runtime = runtime
        self._graph = graph
        self._config = config
        self._now = clock
        self._generative = generative

    def _graph_now(self) -> CurriculumGraph:
        return self._graph() if callable(self._graph) else self._graph

    def explain(
        self,
        student_ref: str,
        objective_code: str,
        *,
        style: str | None = None,
        grade_band: str = "middle",
        locale: str = "ur",
    ) -> dict[str, Any] | None:
        """A styled, grounded, confidence-annotated explanation for one objective.

        Returns None if the objective has no published lesson (the caller maps this to 404).
        """
        lesson = self._curriculum.lesson_for(objective_code)
        if lesson is None:
            return None

        knowledge = self._knowledge.snapshot(student_ref)
        obj = knowledge.get(objective_code) if knowledge else None
        attempts = obj.attempts if obj else 0
        mastery = obj.mastery if obj else Mastery()
        consecutive_failures = obj.consecutive_failures if obj else 0
        last_incorrect = consecutive_failures > 0

        chosen = self._resolve_style(style, grade_band, attempts, last_incorrect)
        utterances = ait.explain(lesson, chosen, self._runtime, locale)
        confidence = ait.confidence_from(mastery, attempts)
        escalate = consecutive_failures >= 3
        escalate_reason = (
            f"{consecutive_failures} consecutive failures after help" if escalate else ""
        )
        guardrail = ait.guardrail_report(
            lesson,
            utterances,
            confidence=confidence,
            age_appropriate=True,
            escalate=escalate,
            escalate_reason=escalate_reason,
        )
        rationale = (
            f"style={chosen.value}",
            f"attempts={attempts}",
            f"last_incorrect={last_incorrect}",
            f"grade_band={grade_band}",
        )
        result: dict[str, Any] = {
            "objective_code": objective_code,
            "style": chosen.value,
            "utterances": [
                {"kind": u.kind.value, "text": u.text, "locale": u.locale} for u in utterances
            ],
            "confidence": confidence.value,
            "grounded": guardrail.grounded,
            "guardrail": guardrail.to_dict(),
            "rationale": list(rationale),
        }
        generation = self._maybe_rephrase(
            student_ref, lesson, utterances, locale=locale, grade_band=grade_band, escalate=escalate
        )
        if generation is not None:
            result["generation"] = generation
        return result

    # ------------------------------------------------------------------------ generative tier

    def _maybe_rephrase(
        self,
        student_ref: str,
        lesson: LessonView,
        utterances: tuple[Utterance, ...],
        *,
        locale: str,
        grade_band: str,
        escalate: bool,
    ) -> dict[str, Any] | None:
        """The ``generation`` block, or None to serve the templated response untouched."""
        tier = self._generative
        if tier is None or not tier.enabled_for(student_ref):
            return (
                None  # flag off: nothing else is consulted (byte-identical to the templated tier)
            )

        def skip(reason: str) -> None:
            self._emit(
                tier,
                SafetyEvent(
                    "skipped", reason, lesson.lesson_id, lesson.objective_code, locale, grade_band
                ),
            )

        if _fail_closed(tier.kill_switch_engaged, default=True):
            skip("kill_switch_engaged")
            return None
        if escalate:
            skip("escalating_to_human")
            return None
        if not _fail_closed(lambda: tier.ai_teaching_consent(student_ref), default=False):
            skip("no_ai_teaching_consent")
            return None
        now = self._now()
        if _fail_closed(lambda: tier.quota_exhausted(student_ref, now), default=True):
            # Not an error and not a weaker path: the learner simply gets the authored engine.
            skip("learner_quota_exhausted")
            return None

        # The server holds no trusted hint state for :explain (hint levels are client-reported), so
        # the ladder is never treated as exhausted here: no item's answer may surface.
        outcome = run_rephrase(
            lesson,
            utterances,
            tier.gateway,
            locale=locale,
            grade_band=grade_band,
            cost_meter=tier.cost_meter,
            answer_context=gate.AnswerContext(),
            learner_ref=student_ref,
            now=now,
        )
        verdict, usage = outcome.verdict, outcome.usage
        self._emit(
            tier,
            SafetyEvent(
                decision=outcome.status,
                reason=",".join(verdict.rules) if verdict is not None else outcome.error,
                lesson_id=lesson.lesson_id,
                objective_code=lesson.objective_code,
                locale=locale,
                grade_band=grade_band,
                provider=outcome.provider,
                tier=outcome.tier.value,
                dimensions=",".join(verdict.dimensions) if verdict is not None else "",
                output_chars=outcome.output_chars,
                output_sha256=outcome.output_sha256,
                grounding_fields=len(outcome.prompt.passages),
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                cost_micros=usage.cost_micros if usage else 0,
            ),
        )
        registry().inc("taleem_ai_teacher_generation_total", status=outcome.status)
        if outcome.status != "accepted":
            # Refuse, don't soften: the authored utterances above are the whole answer.
            return {"status": outcome.status, "fallback": "authored", "explanation": None}
        return {
            "status": "accepted",
            "fallback": None,
            "explanation": {
                "text": outcome.text,
                "locale": locale,
                "generated": True,  # NOT verified curriculum text — the client must label it
                "verified": False,  # the gate checks grounding lexically; it cannot vouch for it
                "verified_source": "utterances",  # the authored text above is the verified version
                "notice_key": GENERATED_NOTICE_KEY,  # client i18n key for the "AI-written" label
                "source": "generated",
                "lesson_id": lesson.lesson_id,
                "objective_code": lesson.objective_code,
                "grounded_on": list(outcome.prompt.fields),
                "provider": outcome.provider,
                "tier": outcome.tier.value,
            },
        }

    @staticmethod
    def _emit(tier: GenerativeTier, event: SafetyEvent) -> None:
        if tier.safety_events is not None:
            tier.safety_events(event)

    @staticmethod
    def _resolve_style(
        style: str | None, grade_band: str, attempts: int, last_incorrect: bool
    ) -> ait.ExplanationStyle:
        if style:
            try:
                return ait.ExplanationStyle(style)
            except ValueError:
                pass  # unknown style → fall through to the deterministic policy
        return ait.choose_style(grade_band, attempts, last_incorrect)

    def plan(self, student_ref: str) -> dict[str, Any]:
        """The adaptive plan: weak topics, revision, personalized practice, and next action."""
        knowledge = self._knowledge.snapshot(student_ref) or StudentKnowledge(
            student_ref=student_ref
        )
        plan = ait.adaptive_plan(knowledge, self._graph_now(), self._config, self._now())
        return {
            "next_action": {
                "kind": plan.next_action.kind.value,
                "objective_code": plan.next_action.objective_code,
                "rationale": [
                    {"rule_id": r.rule_id, "note": r.note} for r in plan.next_action.rationale
                ],
            },
            "weak_topics": [
                {
                    "objective_code": w.objective_code,
                    "state": w.state.value,
                    "mastery": round(w.mastery, 4),
                    "active_misconceptions": list(w.active_misconceptions),
                    "reason": w.reason,
                }
                for w in plan.weak_topics
            ],
            "revision_due": list(plan.revision_due),
            "practice": [
                {
                    "objective_code": p.objective_code,
                    "difficulty": p.difficulty,
                    "confidence": p.confidence.value,
                }
                for p in plan.practice
            ],
            "confidence": plan.confidence.value,
            "rationale": list(plan.rationale),
        }

    def capabilities(self) -> dict[str, Any]:
        """The offline capability matrix (what works offline vs needs connectivity)."""
        return {"offline": ait.offline_capabilities()}
