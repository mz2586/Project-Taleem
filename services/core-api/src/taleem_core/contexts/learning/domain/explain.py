"""Explainable recommendations (pure) — the structured "why" behind each next step.

The decision engine already says *what* to do next and carries English trace notes. This module
turns a learner's knowledge into recommendations a teacher or guardian can inspect: each carries
stable reason codes with parameters (``decision.ReasonCode`` — rendered by clients from their own
ur/en catalogs, never English strings), the calibrated confidence and uncertainty behind it, and
the evidence counts it rests on — practice and diagnostic evidence counted separately, because they
are different kinds of evidence (``InteractionContext.DIAGNOSTIC``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .ai_teacher import TeacherConfidence, confidence_from
from .decision import (
    CurriculumGraph,
    Decision,
    Reason,
    ReasonCode,
    below_threshold_reason,
    misconception_reason,
    placement_reason,
    review_reason,
)
from .knowledge import ObjectiveMastery, StudentKnowledge
from .values import InteractionContext, Mastery, MasteryState, Outcome


@dataclass(frozen=True)
class EvidenceCounts:
    practice: int = 0
    practice_correct: int = 0
    diagnostic: int = 0
    diagnostic_correct: int = 0
    last_at: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "practice": self.practice,
            "practice_correct": self.practice_correct,
            "diagnostic": self.diagnostic,
            "diagnostic_correct": self.diagnostic_correct,
            "last_at": self.last_at,
        }


@dataclass(frozen=True)
class Recommendation:
    kind: str  # the decision kind for the next action; review / practice / remediate otherwise
    objective_code: str | None
    reasons: tuple[Reason, ...]
    confidence: TeacherConfidence
    mastery: float | None
    uncertainty: float | None
    state: str
    evidence: EvidenceCounts
    estimate_source: str  # practice | diagnostic | none — what the current estimate rests on
    is_next_action: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "objective_code": self.objective_code,
            "is_next_action": self.is_next_action,
            "reasons": [r.to_dict() for r in self.reasons],
            "confidence": self.confidence.value,
            "mastery": self.mastery,
            "uncertainty": self.uncertainty,
            "state": self.state,
            "evidence": self.evidence.to_dict(),
            "estimate_source": self.estimate_source,
        }


def evidence_counts(knowledge: StudentKnowledge) -> dict[str, EvidenceCounts]:
    """Per objective: practice vs diagnostic evidence, from the immutable evidence record."""
    out: dict[str, EvidenceCounts] = {}
    for ev in knowledge.evidence:
        cur = out.get(ev.objective_code, EvidenceCounts())
        correct = ev.outcome is Outcome.CORRECT
        last = max(cur.last_at or 0.0, ev.occurred_at)
        if ev.context is InteractionContext.DIAGNOSTIC:
            cur = EvidenceCounts(
                cur.practice,
                cur.practice_correct,
                cur.diagnostic + 1,
                cur.diagnostic_correct + correct,
                last,
            )
        else:
            cur = EvidenceCounts(
                cur.practice + 1,
                cur.practice_correct + correct,
                cur.diagnostic,
                cur.diagnostic_correct,
                last,
            )
        out[ev.objective_code] = cur
    return out


def _estimate_source(obj: ObjectiveMastery | None, ev: EvidenceCounts) -> str:
    if obj is not None and obj.attempts:
        return "practice"
    if (obj is not None and obj.provenance is not None) or ev.diagnostic:
        return "diagnostic"
    return "none"


def objective_reasons(
    knowledge: StudentKnowledge, graph: CurriculumGraph, code: str, now: float
) -> tuple[Reason, ...]:
    """Why an objective needs attention (weak-topic reasons), most important first."""
    obj = knowledge.get(code)
    if obj is None:
        return ()
    out: list[Reason] = [
        misconception_reason(obj, m.misconception_ref) for m in obj.active_misconceptions()
    ]
    if obj.state is MasteryState.AT_RISK:
        out.append(
            Reason.of(
                ReasonCode.RETENTION_AT_RISK, objective=code, mastery=round(obj.mastery.value, 3)
            )
        )
    elif obj.state is MasteryState.NEEDS_REVIEW or code in knowledge.due_reviews(now):
        out.append(review_reason(knowledge, code, now))
    elif obj.state is MasteryState.IN_PROGRESS:
        out.append(below_threshold_reason(obj))
    info = graph.by_code(code)
    for pre in info.prerequisites if info else ():
        p = knowledge.get(pre)
        if p is None or (p.state is not MasteryState.MASTERED and not p.placed_secure):
            out.append(Reason.of(ReasonCode.PREREQUISITE_GAP, objective=code, prereq=pre))
    placed = placement_reason(obj)
    if placed is not None:
        out.append(placed)
    return tuple(out)


def _rec(
    kind: str,
    code: str | None,
    reasons: tuple[Reason, ...],
    knowledge: StudentKnowledge,
    counts: dict[str, EvidenceCounts],
    *,
    is_next: bool = False,
) -> Recommendation:
    obj = knowledge.get(code) if code else None
    ev = counts.get(code or "", EvidenceCounts())
    mastery = obj.mastery if obj is not None else Mastery()
    return Recommendation(
        kind=kind,
        objective_code=code,
        reasons=reasons,
        confidence=confidence_from(mastery, (obj.attempts if obj else 0) + ev.diagnostic),
        mastery=round(obj.mastery.value, 4) if obj is not None else None,
        uncertainty=round(obj.mastery.uncertainty, 4) if obj is not None else None,
        state=obj.state.value if obj is not None else MasteryState.NOT_STARTED.value,
        evidence=ev,
        estimate_source=_estimate_source(obj, ev),
        is_next_action=is_next,
    )


def recommendations(
    knowledge: StudentKnowledge,
    graph: CurriculumGraph,
    next_action: Decision,
    weak_codes: tuple[str, ...],
    revision_due: tuple[str, ...],
    now: float,
    *,
    limit: int = 6,
) -> list[Recommendation]:
    """The next action first, then due reviews, then weak topics — one per objective."""
    counts = evidence_counts(knowledge)
    first_reasons = tuple(r for step in next_action.rationale for r in step.reasons)
    out = [
        _rec(
            next_action.kind.value,
            next_action.objective_code,
            first_reasons,
            knowledge,
            counts,
            is_next=True,
        )
    ]
    seen = {next_action.objective_code} if next_action.objective_code else set()
    for code in revision_due:
        if code in seen:
            continue
        seen.add(code)
        due = len(revision_due)
        out.append(
            _rec(
                "review",
                code,
                (review_reason(knowledge, code, now, due_count=due),),
                knowledge,
                counts,
            )
        )
    for code in weak_codes:
        if code in seen:
            continue
        seen.add(code)
        obj = knowledge.get(code)
        kind = "remediate" if obj is not None and obj.active_misconceptions() else "practice"
        out.append(
            _rec(kind, code, objective_reasons(knowledge, graph, code, now), knowledge, counts)
        )
    return out[:limit]
