"""Offline homework submissions — the ``homework.submitted`` sync delta (OFFLINE_SYNC_SPEC.md).

A child with no connection presses Send; the device queues the answer and replays it through
``POST /v1/sync/batch`` once online. This consumer applies it through the **same** ``SchoolService``
submit methods as the online routes (HOMEWORK_AND_MARKING_CONTRACT §2, §6), so everything an online
submit does happens identically: text cleaning and the item's length cap, automatic marking of an
exact key (one idempotent evidence), ``self_check`` with the "compare your answer" view, the
disclosure screen (once per stored answer), the cohort-filtered lesson read, ``LESSON_ASSIGNED``
and ``SHARING_REQUIRED``. The live learner consent gate runs for the whole batch before this.

Idempotency is by the device's **submission key**: the row remembers the key of the answer it now
holds, so a replay of the same delta — even after a restart — answers ``duplicate`` with the
current view and changes nothing (no second attempt, screen, audit or evidence).

Nothing is silently dropped. Every refusal is a ``conflict`` with a stable reason the device shows
the child, and a conflict is not remembered, so the same answer can be sent again later:

- ``SUBMISSION_MARKED``     the answer is marked and final;
- ``SUBMISSION_SUPERSEDED`` a newer answer to the item is already saved (sent from elsewhere);
- ``NOT_AVAILABLE``         the lesson is no longer published / assigned to the learner, or the
                            item is gone;
- ``LESSON_ASSIGNED``       a class assigned the lesson since: answer it in the assignment;
- ``SHARING_REQUIRED``      an assignment answer while the guardian has withdrawn sharing;
- ``INVALID``               an empty / too long answer or a malformed payload;
- ``BUSY``                  the same item was being written at the same moment (send again).
"""

from __future__ import annotations

from typing import Any

from ....platform.errors import Problem
from ...sync.domain import DeltaType, Status, SyncDelta
from ...sync.service import HomeworkOutcome
from .school_service import SchoolService

MAX_KEY = 64  # school.submission.client_key (alembic 0020)
SOURCES = ("self_paced", "assignment")

# Problem code (or HTTP status) of the online path -> the conflict reason the device shows.
_REASON_FOR_CODE = {
    "SUBMISSION_MARKED": "SUBMISSION_MARKED",
    "SUBMISSION_SUPERSEDED": "SUBMISSION_SUPERSEDED",
    "SUBMISSION_RETURNED": "SUBMISSION_SUPERSEDED",
    "LESSON_ASSIGNED": "LESSON_ASSIGNED",
    "SHARING_REQUIRED": "SHARING_REQUIRED",
    "VALIDATION_FAILED": "INVALID",
    "CONFLICT": "BUSY",
    "NOT_FOUND": "NOT_AVAILABLE",
}


def _conflict(reason: str) -> HomeworkOutcome:
    return HomeworkOutcome(Status.CONFLICT, reason=reason)


def _str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) and value.strip() else None


class HomeworkSyncConsumer:
    """Implements the sync ``HomeworkSink`` over the school service."""

    def __init__(self, school: SchoolService) -> None:
        self._school = school

    def apply_homework(self, delta: SyncDelta, *, replay: bool) -> HomeworkOutcome:
        if delta.type is not DeltaType.HOMEWORK_SUBMITTED:
            return _conflict("INVALID")  # routing error — never silently dropped
        parsed = _parse(delta)
        if parsed is None:
            return _conflict("INVALID")
        target = {
            "student_ref": parsed["student_ref"],
            "item_ref": parsed["item_ref"],
            "client_key": parsed["client_key"],
            "assignment_id": parsed["assignment_id"],
            "objective_code": parsed["objective_code"],
        }
        # Durable idempotency first: the stored answer IS this delta's answer.
        current = self._school.synced_submission(**target)
        if current is not None or replay:
            # A replay this process already answered whose answer was superseded since is still
            # a duplicate: it was applied once, and is never applied over the newer answer.
            return HomeworkOutcome(Status.DUPLICATE, result=current)
        try:
            view = self._submit(parsed)
        except Problem as problem:
            return _conflict(_REASON_FOR_CODE.get(problem.code, problem.code or "INVALID"))
        return HomeworkOutcome(Status.APPLIED, result=view)

    def _submit(self, p: dict[str, Any]) -> dict[str, Any]:
        common = {
            "student_ref": p["student_ref"],
            "item_ref": p["item_ref"],
            "text": p["text"],
            "client_key": p["client_key"],
            "expected_attempt": p["attempt"],
        }
        if p["source"] == "assignment":
            return self._school.learner_submit(assignment_id=p["assignment_id"], **common)
        return self._school.learner_submit_self_paced(objective_code=p["objective_code"], **common)


def _parse(delta: SyncDelta) -> dict[str, Any] | None:
    """The delta's fields, or None when the payload is malformed (a conflict, never a guess)."""
    p = delta.payload
    student_ref = _str(p, "student_ref")
    item_ref = _str(p, "item_ref")
    source = p.get("source")
    text = p.get("text")
    if student_ref is None or item_ref is None or source not in SOURCES:
        return None
    if not isinstance(text, str):
        return None
    assignment_id = _str(p, "assignment_id") if source == "assignment" else None
    objective_code = _str(p, "objective_code") if source == "self_paced" else None
    if (assignment_id or objective_code) is None:
        return None
    key = _str(p, "submission_key") or delta.client_event_id
    if len(key) > MAX_KEY:
        return None
    raw_attempt = p.get("attempt")
    attempt: int | None = None
    if raw_attempt is not None:
        if isinstance(raw_attempt, bool) or not isinstance(raw_attempt, int) or raw_attempt < 1:
            return None
        attempt = raw_attempt
    # ``submitted_at`` is the device's clock: informational only, never used for ordering or
    # stored (the server stamps the time it applies the answer, as online).
    submitted_at = p.get("submitted_at")
    if submitted_at is not None and (
        isinstance(submitted_at, bool) or not isinstance(submitted_at, (int, float))
    ):
        return None
    return {
        "student_ref": student_ref,
        "item_ref": item_ref,
        "source": source,
        "text": text,
        "assignment_id": assignment_id,
        "objective_code": objective_code,
        "client_key": key,
        "attempt": attempt,
    }
