"""Adapters onto other contexts, built from callables the composition root supplies.

No identity or learning module is imported here: each adapter is duck-typed over the values those
contexts' public services return, so the school context depends on behaviour, not on their models.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..application.ports import ObjectiveProgress


class IdentityLearnerDirectory:
    """``LearnerDirectory`` over identity. Every method reads live state (no cache)."""

    def __init__(
        self,
        *,
        learner_lookup: Callable[[str], Any | None],
        learner_refusal: Callable[[str], str | None],
        sharing_allowed: Callable[[str], bool],
    ) -> None:
        self._lookup = learner_lookup
        self._refusal = learner_refusal
        self._sharing = sharing_allowed

    def guardian_of(self, student_ref: str) -> str | None:
        learner = self._lookup(student_ref)
        return str(learner.guardian_ref) if learner is not None else None

    def display_name(self, student_ref: str) -> str | None:
        learner = self._lookup(student_ref)
        return str(learner.display_name) if learner is not None else None

    def may_learn(self, student_ref: str) -> bool:
        return self._lookup(student_ref) is not None and self._refusal(student_ref) is None

    def shares_with_teacher(self, student_ref: str) -> bool:
        return self.may_learn(student_ref) and self._sharing(student_ref)


class CallableSharingConsent:
    """``GuardianSharingConsent`` over identity's consent service."""

    def __init__(self, grant: Callable[[str, str, str], object]) -> None:
        self._grant = grant

    def grant(self, *, guardian_ref: str, student_ref: str, attestation: str) -> None:
        self._grant(guardian_ref, student_ref, attestation)


class KnowledgeProgressReader:
    """``LearnerProgressReader`` over the learning context's knowledge snapshot.

    Reads only the public shape of the snapshot (``objectives[code].mastery.value / .state`` and
    ``evidence[*].objective_code / .occurred_at``); learning's domain types are never imported.
    """

    def __init__(self, snapshot: Callable[[str], Any | None]) -> None:
        self._snapshot = snapshot

    def objective_progress(
        self, student_ref: str, objective_code: str, *, since: float
    ) -> ObjectiveProgress:
        knowledge = self._snapshot(student_ref)
        if knowledge is None:
            return ObjectiveProgress(mastery=None, state="not_started", attempts_since=0)
        objective = knowledge.objectives.get(objective_code)
        attempts = sum(
            1
            for e in knowledge.evidence
            if e.objective_code == objective_code and e.occurred_at >= since
        )
        if objective is None:
            return ObjectiveProgress(mastery=None, state="not_started", attempts_since=attempts)
        return ObjectiveProgress(
            mastery=round(float(objective.mastery.value), 4),
            state=str(getattr(objective.state, "value", objective.state)),
            attempts_since=attempts,
        )


class CallablePublishedCurriculum:
    def __init__(self, lesson_for: Callable[[str], object | None]) -> None:
        self._lesson_for = lesson_for

    def is_published(self, objective_code: str) -> bool:
        return self._lesson_for(objective_code) is not None
