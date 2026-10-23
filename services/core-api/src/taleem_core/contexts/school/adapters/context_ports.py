"""Adapters onto other contexts, built from callables the composition root supplies.

No identity or learning module is imported here: each adapter is duck-typed over the values those
contexts' public services return, so the school context depends on behaviour, not on their models.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..application.ports import ObjectiveProgress, PublishedLesson


class IdentityLearnerDirectory:
    """``LearnerDirectory`` over identity. Every method reads live state (no cache)."""

    def __init__(
        self,
        *,
        learner_lookup: Callable[[str], Any | None],
        learner_refusal: Callable[[str], str | None],
        sharing_allowed: Callable[[str], bool],
        visible_many: Callable[[list[str]], dict[str, str]] | None = None,
    ) -> None:
        self._lookup = learner_lookup
        self._refusal = learner_refusal
        self._sharing = sharing_allowed
        # Optional batched form of ``shares_with_teacher`` + ``display_name`` (one identity read
        # for a whole class). Must apply exactly the same live rules; absent → per-learner calls.
        self._visible_many = visible_many

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

    def visible_to_teacher(self, student_refs: list[str]) -> dict[str, str]:
        refs = list(dict.fromkeys(r for r in student_refs if r))
        if not refs:
            return {}
        if self._visible_many is not None:
            return self._visible_many(refs)
        return {ref: self.display_name(ref) or "" for ref in refs if self.shares_with_teacher(ref)}


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

    def __init__(
        self,
        snapshot: Callable[[str], Any | None],
        *,
        progress_many: Callable[[list[str], str, float], dict[str, dict[str, Any]]] | None = None,
    ) -> None:
        self._snapshot = snapshot
        # Optional batched read: ``{ref: {"mastery", "state", "attempts_since"}}`` for refs that
        # have any knowledge (see learning's ``KnowledgeService.objective_progress``).
        self._progress_many = progress_many

    def objective_progress_many(
        self, student_refs: list[str], objective_code: str, *, since: float
    ) -> dict[str, ObjectiveProgress]:
        refs = list(dict.fromkeys(student_refs))
        if self._progress_many is None:
            return {r: self.objective_progress(r, objective_code, since=since) for r in refs}
        found = self._progress_many(refs, objective_code, since) if refs else {}
        out: dict[str, ObjectiveProgress] = {}
        for ref in refs:
            row = found.get(ref)
            if row is None:  # no knowledge at all
                out[ref] = ObjectiveProgress(mastery=None, state="not_started", attempts_since=0)
                continue
            attempts = int(row.get("attempts_since") or 0)
            mastery = row.get("mastery")
            if mastery is None:  # knowledge, but never this objective
                out[ref] = ObjectiveProgress(
                    mastery=None, state="not_started", attempts_since=attempts
                )
                continue
            out[ref] = ObjectiveProgress(
                mastery=round(float(mastery), 4),
                state=str(row.get("state")),
                attempts_since=attempts,
            )
        return out

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
    """``PublishedCurriculum`` over the learning read model (lookup + titles-only catalog)."""

    def __init__(
        self,
        lesson_for: Callable[[str], object | None],
        catalog: Callable[[], list[dict[str, Any]]] = list,
    ) -> None:
        self._lesson_for = lesson_for
        self._catalog = catalog

    def is_published(self, objective_code: str) -> bool:
        return self._lesson_for(objective_code) is not None

    def catalog(self) -> list[PublishedLesson]:
        return [
            PublishedLesson(
                objective_code=str(row["objective_code"]),
                curriculum_pack=str(row.get("curriculum_pack", "")),
                title={str(k): str(v) for k, v in dict(row.get("title") or {}).items() if v},
            )
            for row in self._catalog()
        ]
