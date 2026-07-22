"""AI Teacher application service (Phase 8).

Wires the pure AI Teacher orchestration (`domain/ai_teacher.py`) to existing components: the
SessionService (in-flight session), the CurriculumReadModel (published `LessonView` — the grounding
boundary), the KnowledgeService (mastery snapshot), the templated runtime, and the decision graph.
No new child-data table; every output is derived and explainable.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...learning.domain import ai_teacher as ait
from ...learning.domain.decision import CurriculumGraph, DecisionConfig
from ...learning.domain.knowledge import StudentKnowledge
from ...learning.domain.runtime import TemplatedTeachingRuntime
from ...learning.domain.values import Mastery
from .knowledge_service import KnowledgeService
from .ports import CurriculumReadModel
from .session_service import SessionService

_GraphSource = CurriculumGraph | Callable[[], CurriculumGraph]


class AITeacherService:
    """Curriculum-grounded, explainable teaching over existing components (no generative model)."""

    def __init__(
        self,
        sessions: SessionService,
        knowledge_service: KnowledgeService,
        curriculum: CurriculumReadModel,
        runtime: TemplatedTeachingRuntime,
        graph: _GraphSource,
        config: DecisionConfig,
        clock: Callable[[], float],
    ) -> None:
        self._sessions = sessions
        self._knowledge = knowledge_service
        self._curriculum = curriculum
        self._runtime = runtime
        self._graph = graph
        self._config = config
        self._now = clock

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
        return {
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
