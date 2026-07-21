"""Learning domain events (LEARNING_DOMAIN_MODEL §4).

Past-tense facts emitted via the transactional outbox; de-identified payloads (pseudonymous ref, no
raw content). ``SafeguardingSignalRaised`` additionally travels a real-time path (design-review F6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LearningEvent:
    event_type: str
    aggregate_type: str
    aggregate_id: str
    occurred_at: float
    payload: dict[str, Any] = field(default_factory=dict)


def session_started(session_id: str, student_ref: str, now: float) -> LearningEvent:
    return LearningEvent("SessionStarted", "session", session_id, now, {"student_ref": student_ref})


def interaction_recorded(
    session_id: str, objective_code: str, outcome: str, now: float
) -> LearningEvent:
    return LearningEvent(
        "InteractionRecorded",
        "session",
        session_id,
        now,
        {"objective_code": objective_code, "outcome": outcome},
    )


def objective_mastered(student_ref: str, objective_code: str, now: float) -> LearningEvent:
    return LearningEvent(
        "ObjectiveMastered",
        "student_knowledge",
        student_ref,
        now,
        {"objective_code": objective_code},
    )


def misconception_detected(
    student_ref: str, objective_code: str, misconception_ref: str, now: float
) -> LearningEvent:
    return LearningEvent(
        "MisconceptionDetected",
        "student_knowledge",
        student_ref,
        now,
        {"objective_code": objective_code, "misconception_ref": misconception_ref},
    )


def misconception_cleared(
    student_ref: str, objective_code: str, misconception_ref: str, now: float
) -> LearningEvent:
    return LearningEvent(
        "MisconceptionCleared",
        "student_knowledge",
        student_ref,
        now,
        {"objective_code": objective_code, "misconception_ref": misconception_ref},
    )


def review_scheduled(
    student_ref: str, objective_code: str, next_review_at: float, now: float
) -> LearningEvent:
    return LearningEvent(
        "ReviewScheduled",
        "student_knowledge",
        student_ref,
        now,
        {"objective_code": objective_code, "next_review_at": next_review_at},
    )


def session_completed(session_id: str, student_ref: str, now: float) -> LearningEvent:
    return LearningEvent(
        "SessionCompleted", "session", session_id, now, {"student_ref": student_ref}
    )
