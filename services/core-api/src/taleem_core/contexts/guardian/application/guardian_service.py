"""Guardian aggregation service — consumes existing learning read models (no duplicated logic).

Every field a guardian sees is derived from services the Student Platform already exposes:
``StudentQueryService`` (today / history / assessments / achievements / notifications /
recommendations), ``LearningAnalytics`` (progress + per-objective mastery), and the ``AI Teacher``
plan. The only *new* computation is guardian-facing presentation over that data — attendance,
learning streaks, weekly summary, and the (server-known) offline-sync freshness — all pure functions
over the sessions the history read model already returns. No new child-data tables; nothing
re-implemented.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from .directory import GuardianDirectory, GuardianProfile

_DAY = 86_400.0
# A learner's server data is "stale" for a guardian if nothing has synced in this window. Pending
# uploads live on the device and are reported by the client; the server only knows the last sync.
_STALE_AFTER_S = 3 * _DAY


class _StudentQueries(Protocol):
    def today(self, student_ref: str) -> dict[str, Any]: ...
    def history(self, student_ref: str, limit: int = 50) -> dict[str, Any]: ...
    def assessments(self, student_ref: str) -> dict[str, Any]: ...
    def achievements(self, student_ref: str) -> dict[str, Any]: ...
    def notifications(self, student_ref: str) -> dict[str, Any]: ...
    def recommendations(self, student_ref: str) -> dict[str, Any]: ...


class _Analytics(Protocol):
    def progress_summary(self, student_ref: str) -> Any: ...


class _AITeacher(Protocol):
    def plan(self, student_ref: str) -> dict[str, Any]: ...


def _epoch_day(ts: float) -> int:
    return int(ts // _DAY)


def attendance(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    """Distinct active days derived from session timestamps (reuses history; no new data)."""
    days = sorted({_epoch_day(float(s["at"])) for s in sessions})
    return {"active_days": len(days), "day_indices": days[-30:]}


def streak(sessions: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """Consecutive active days ending at the most recent active day (today or yesterday counts)."""
    days = sorted({_epoch_day(float(s["at"])) for s in sessions})
    if not days:
        return {"current": 0, "longest": 0, "last_active_day": None}
    # longest run of consecutive day indices
    longest = run = 1
    for prev, cur in zip(days, days[1:], strict=False):
        run = run + 1 if cur == prev + 1 else 1
        longest = max(longest, run)
    # current streak: walk back from the last active day while consecutive
    today = _epoch_day(now)
    current = 0
    if days[-1] in (today, today - 1):
        current = 1
        for prev, cur in zip(reversed(days[:-1]), reversed(days), strict=False):
            if cur - prev == 1:
                current += 1
            else:
                break
    return {"current": current, "longest": longest, "last_active_day": days[-1]}


def weekly_summary(sessions: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """Attempts / correct / sessions in the trailing 7 days (over the history read model)."""
    cutoff = now - 7 * _DAY
    recent = [s for s in sessions if float(s["at"]) >= cutoff]
    attempts = sum(int(s.get("attempts", 0)) for s in recent)
    correct = sum(int(s.get("correct", 0)) for s in recent)
    return {
        "sessions": len(recent),
        "attempts": attempts,
        "correct": correct,
        "accuracy": round(correct / attempts, 3) if attempts else 0.0,
    }


def sync_status(sessions: list[dict[str, Any]], now: float) -> dict[str, Any]:
    """Server-known offline-sync freshness. Pending uploads are device-side (client-reported)."""
    last = max((float(s["at"]) for s in sessions), default=None)
    is_stale = last is None or (now - last) > _STALE_AFTER_S
    return {
        "last_synced_at": last,
        "is_stale": is_stale,
        "seconds_since_sync": round(now - last) if last is not None else None,
        # The device tracks unsynced local attempts; the server surfaces only what it has received.
        "pending_is_device_reported": True,
    }


class GuardianService:
    """Aggregates a guardian's view by consuming existing learning services (reuse, not copy)."""

    def __init__(
        self,
        directory: GuardianDirectory,
        queries: _StudentQueries,
        analytics: _Analytics,
        ai_teacher: _AITeacher,
        clock: Callable[[], float],
    ) -> None:
        self._dir = directory
        self._q = queries
        self._analytics = analytics
        self._ai = ai_teacher
        self._now = clock

    # -- association ---------------------------------------------------------------------------
    def profile(self, guardian_ref: str) -> GuardianProfile | None:
        return self._dir.profile(guardian_ref)

    def is_linked(self, guardian_ref: str, student_ref: str) -> bool:
        return self._dir.is_linked(guardian_ref, student_ref)

    # -- child summary (dashboard row) ---------------------------------------------------------
    def child_summary(self, student_ref: str) -> dict[str, Any]:
        now = self._now()
        progress = self._analytics.progress_summary(student_ref).to_dict()
        hist = self._q.history(student_ref)["sessions"]
        notifs = self._q.notifications(student_ref)
        interventions = self._interventions(student_ref, notifs)
        return {
            "student_ref": student_ref,
            "progress": {
                "objectives_mastered": progress["objectives_mastered"],
                "objectives_in_progress": progress["objectives_in_progress"],
                "accuracy": progress["accuracy"],
                "total_attempts": progress["total_attempts"],
            },
            "streak": streak(hist, now),
            "sync_status": sync_status(hist, now),
            "open_interventions": len(interventions),
            "achievements_count": self._q.achievements(student_ref)["mastered_count"],
        }

    def dashboard(self, guardian_ref: str) -> dict[str, Any]:
        children = self._dir.children(guardian_ref)
        return {
            "guardian_ref": guardian_ref,
            "children": [self.child_summary(ref) for ref in children],
            "child_count": len(children),
        }

    # -- full child overview -------------------------------------------------------------------
    def child_overview(self, student_ref: str) -> dict[str, Any]:
        now = self._now()
        progress = self._analytics.progress_summary(student_ref).to_dict()
        hist = self._q.history(student_ref)
        sessions = hist["sessions"]
        notifs = self._q.notifications(student_ref)
        return {
            "student_ref": student_ref,
            "progress_overview": progress,
            "knowledge_growth": progress["objective_mastery"],
            "attendance": attendance(sessions),
            "learning_streaks": streak(sessions, now),
            "weekly_summary": weekly_summary(sessions, now),
            "learning_timeline": sessions[:20],
            "assessment_history": self._q.assessments(student_ref),
            "ai_teacher_activity": self._ai.plan(student_ref),
            "recommendations": self._q.recommendations(student_ref)["recommendations"],
            "intervention_notifications": self._interventions(student_ref, notifs),
            "offline_sync_status": sync_status(sessions, now),
            "achievement_history": self._q.achievements(student_ref)["achievements"],
        }

    # -- derivations ---------------------------------------------------------------------------
    def _interventions(self, student_ref: str, notifs: dict[str, Any]) -> list[dict[str, Any]]:
        # A guardian's "intervention" list = the learner's actionable notifications (revision due,
        # etc.) surfaced read-only. Reuses the notifications read model; no new logic.
        return [n for n in notifs["notifications"] if n.get("type") in ("revision_due", "at_risk")]
