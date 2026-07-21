"""Domain <-> ORM mapping for the StudentKnowledge aggregate."""

from __future__ import annotations

from typing import Any

from ...domain.knowledge import (
    AssessmentEvidence,
    MisconceptionRecord,
    ObjectiveMastery,
    StudentKnowledge,
)
from ...domain.values import (
    Confidence,
    InteractionContext,
    Mastery,
    MasteryState,
    MasteryThreshold,
    MemoryStrength,
    MisconceptionState,
    Outcome,
    Pace,
)
from .models import AssessmentEvidenceRow, ObjectiveMasteryRow, StudentKnowledgeRow


def objective_column_values(obj: ObjectiveMastery) -> dict[str, Any]:
    return {
        "objective_code": obj.objective_code,
        "mastery_value": obj.mastery.value,
        "mastery_uncertainty": obj.mastery.uncertainty,
        "state": obj.state.value,
        "attempts": obj.attempts,
        "correct_streak": obj.correct_streak,
        "consecutive_failures": obj.consecutive_failures,
        "next_review_at": obj.memory.next_review_at,
        "memory": {
            "stability_s": obj.memory.stability_s,
            "last_seen_at": obj.memory.last_seen_at,
            "next_review_at": obj.memory.next_review_at,
        },
        "confidence": {
            "self_reported": obj.confidence.self_reported,
            "sampled_at": obj.confidence.sampled_at,
        },
        "pace": {
            "attempts_to_mastery": obj.pace.attempts_to_mastery,
            "time_to_mastery_s": obj.pace.time_to_mastery_s,
            "pace_factor": obj.pace.pace_factor,
        },
        "threshold": {"tau": obj.threshold.tau, "max_uncertainty": obj.threshold.max_uncertainty},
        "misconceptions": [
            {
                "misconception_ref": m.misconception_ref,
                "objective_code": m.objective_code,
                "state": m.state.value,
                "evidence_count": m.evidence_count,
                "first_detected_at": m.first_detected_at,
                "last_detected_at": m.last_detected_at,
                "cleared_at": m.cleared_at,
            }
            for m in obj.misconceptions
        ],
    }


def objective_from_row(row: ObjectiveMasteryRow) -> ObjectiveMastery:
    mem = row.memory or {}
    conf = row.confidence or {}
    pace = row.pace or {}
    thr = row.threshold or {}
    return ObjectiveMastery(
        objective_code=row.objective_code,
        mastery=Mastery(value=row.mastery_value, uncertainty=row.mastery_uncertainty),
        state=MasteryState(row.state),
        memory=MemoryStrength(
            stability_s=mem.get("stability_s", 86_400.0),
            last_seen_at=mem.get("last_seen_at", 0.0),
            next_review_at=mem.get("next_review_at", 0.0),
        ),
        confidence=Confidence(
            self_reported=conf.get("self_reported", 0.5), sampled_at=conf.get("sampled_at", 0.0)
        ),
        pace=Pace(
            attempts_to_mastery=pace.get("attempts_to_mastery", 0),
            time_to_mastery_s=pace.get("time_to_mastery_s", 0.0),
            pace_factor=pace.get("pace_factor", 1.0),
        ),
        threshold=MasteryThreshold(
            tau=thr.get("tau", 0.85), max_uncertainty=thr.get("max_uncertainty", 0.20)
        ),
        attempts=row.attempts,
        correct_streak=row.correct_streak,
        consecutive_failures=row.consecutive_failures,
        misconceptions=[
            MisconceptionRecord(
                misconception_ref=m["misconception_ref"],
                objective_code=m["objective_code"],
                state=MisconceptionState(m["state"]),
                evidence_count=m["evidence_count"],
                first_detected_at=m["first_detected_at"],
                last_detected_at=m["last_detected_at"],
                cleared_at=m.get("cleared_at"),
            )
            for m in (row.misconceptions or [])
        ],
    )


def evidence_column_values(ev: AssessmentEvidence) -> dict[str, Any]:
    return {
        "id": ev.evidence_id,
        "student_ref": ev.student_ref,
        "objective_code": ev.objective_code,
        "item_ref": ev.item_ref,
        "session_id": ev.session_id,
        "outcome": ev.outcome.value,
        "context": ev.context.value,
        "misconception_hits": list(ev.misconception_hits),
        "hints_used": ev.hints_used,
        "response_time_ms": ev.response_time_ms,
        "mastery_before": ev.mastery_before,
        "mastery_after": ev.mastery_after,
        "occurred_at": ev.occurred_at,
    }


def evidence_from_row(row: AssessmentEvidenceRow) -> AssessmentEvidence:
    return AssessmentEvidence(
        evidence_id=row.id,
        student_ref=row.student_ref,
        objective_code=row.objective_code,
        item_ref=row.item_ref,
        session_id=row.session_id,
        outcome=Outcome(row.outcome),
        context=InteractionContext(row.context),
        misconception_hits=tuple(row.misconception_hits or ()),
        hints_used=row.hints_used,
        response_time_ms=row.response_time_ms,
        mastery_before=row.mastery_before,
        mastery_after=row.mastery_after,
        occurred_at=row.occurred_at,
    )


def knowledge_from_rows(
    root: StudentKnowledgeRow,
    objectives: list[ObjectiveMasteryRow],
    evidence: list[AssessmentEvidenceRow],
) -> StudentKnowledge:
    knowledge = StudentKnowledge(student_ref=root.student_ref, lock_version=root.lock_version)
    for orow in objectives:
        obj = objective_from_row(orow)
        knowledge.objectives[obj.objective_code] = obj
    knowledge.evidence = [
        evidence_from_row(e) for e in sorted(evidence, key=lambda r: r.occurred_at)
    ]
    return knowledge
