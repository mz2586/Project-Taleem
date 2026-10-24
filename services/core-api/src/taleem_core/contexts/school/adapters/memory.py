"""In-memory ``SubmissionRepository`` (unit tests of the submission rules without a database).

Behaves like the SQL adapter: tenant-scoped reads, oldest first, one row per (assignment, item,
learner), and an optimistic ``version`` check on save. Stores copies, so a caller's object never
aliases the stored state.
"""

from __future__ import annotations

import dataclasses

from ....platform.concurrency import ConcurrencyConflictError
from ..domain.model import Submission, SubmissionStatus


def _key(row: Submission) -> tuple[object, ...]:
    # One row per (assignment, item, learner); a self-paced row per (objective, item, learner).
    if row.self_paced:
        return ("self_paced", row.objective_code, row.item_ref, row.student_ref)
    return ("assignment", row.assignment_id, row.item_ref, row.student_ref)


class InMemorySubmissionRepository:
    def __init__(self) -> None:
        self._rows: dict[str, Submission] = {}

    def add(self, submission: Submission) -> None:
        if any(_key(r) == _key(submission) for r in self._rows.values()):
            raise ConcurrencyConflictError("a submission for this item already exists")
        self._rows[submission.submission_id] = dataclasses.replace(submission)

    def get(self, organization_id: str, submission_id: str) -> Submission | None:
        row = self._rows.get(submission_id)
        if row is None or row.organization_id != organization_id:
            return None
        return dataclasses.replace(row)

    def by_id(self, submission_id: str) -> Submission | None:
        row = self._rows.get(submission_id)
        return dataclasses.replace(row) if row else None

    def find(self, assignment_id: str, item_ref: str, student_ref: str) -> Submission | None:
        for row in self._rows.values():
            if _key(row) == ("assignment", assignment_id, item_ref, student_ref):
                return dataclasses.replace(row)
        return None

    def find_self_paced(
        self, objective_code: str, item_ref: str, student_ref: str
    ) -> Submission | None:
        for row in self._rows.values():
            if _key(row) == ("self_paced", objective_code, item_ref, student_ref):
                return dataclasses.replace(row)
        return None

    def for_student(self, student_ref: str) -> list[Submission]:
        rows = [r for r in self._rows.values() if r.student_ref == student_ref]
        return [dataclasses.replace(r) for r in sorted(rows, key=_oldest_first)]

    def for_class(
        self, organization_id: str, class_id: str, status: SubmissionStatus
    ) -> list[Submission]:
        rows = [
            r
            for r in self._rows.values()
            if r.organization_id == organization_id and r.class_id == class_id
            if r.status is status
        ]
        return [dataclasses.replace(r) for r in sorted(rows, key=_oldest_first)]

    def save(self, submission: Submission) -> None:
        stored = self._rows.get(submission.submission_id)
        if stored is None:
            self.add(submission)
            return
        if stored.version != submission.version:
            raise ConcurrencyConflictError("submission changed since it was read")
        self._rows[submission.submission_id] = dataclasses.replace(
            submission, version=submission.version + 1
        )


def _oldest_first(row: Submission) -> tuple[float, str]:
    return (row.submitted_at, row.submission_id)
