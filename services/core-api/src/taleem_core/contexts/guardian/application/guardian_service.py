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

from .directory import GuardianProfile
from .links import GuardianLinks

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
    def reviews(self, student_ref: str) -> dict[str, Any]: ...


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


# Stable, client-localizable kinds. The English ``message`` / ``name`` / ``description`` produced by
# the learning read model are kept for compatibility, but a client renders from ``kind`` +
# ``objective_code`` (+ ``params``) so the guardian sees their own language.
NOTIFICATION_KINDS = ("revision_due", "at_risk", "objective_mastered")
ACHIEVEMENT_KINDS = ("objective_mastered", "misconception_cleared")


def _strip_prefix(value: str, prefix: str) -> str | None:
    return value[len(prefix) :] if value.startswith(prefix) else None


def localizable_notification(
    note: dict[str, Any], *, due_count: int | None = None
) -> dict[str, Any]:
    """Add ``kind``, ``objective_code`` and ``params`` to one learner notification."""
    raw_type = str(note.get("type", ""))
    kind = "objective_mastered" if raw_type == "mastered" else raw_type or "unknown"
    objective_code = note.get("objective_code")
    if objective_code is None and kind == "objective_mastered":
        objective_code = _strip_prefix(str(note.get("id", "")), "mastered-")
    params: dict[str, Any] = {}
    if kind == "revision_due" and due_count is not None:
        params["due_count"] = due_count
    return {**note, "kind": kind, "objective_code": objective_code or None, "params": params}


def localizable_achievement(item: dict[str, Any]) -> dict[str, Any]:
    """Add ``kind`` and ``objective_code`` to one learner achievement.

    The learning read model's ids are deterministic (``mastery-<code>``,
    ``cleared-<code>-<earned_at>``), which is what makes this projection stable.
    """
    ident = str(item.get("id", ""))
    kind = "achievement"
    code: str | None = item.get("objective_code")
    mastered = _strip_prefix(ident, "mastery-")
    cleared = _strip_prefix(ident, "cleared-")
    if mastered is not None:
        kind, code = "objective_mastered", code or mastered
    elif cleared is not None:
        kind = "misconception_cleared"
        suffix = f"-{item.get('earned_at')}"
        if code is None:
            code = cleared[: len(cleared) - len(suffix)] if cleared.endswith(suffix) else cleared
    return {**item, "kind": kind, "objective_code": code or None}


class GuardianService:
    """Aggregates a guardian's view by consuming existing learning services (reuse, not copy)."""

    def __init__(
        self,
        directory: GuardianLinks,
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
        plan = self._ai.plan(student_ref)
        return {
            "student_ref": student_ref,
            "progress_overview": progress,
            "knowledge_growth": progress["objective_mastery"],
            "attendance": attendance(sessions),
            "learning_streaks": streak(sessions, now),
            "weekly_summary": weekly_summary(sessions, now),
            "learning_timeline": sessions[:20],
            "assessment_history": self._q.assessments(student_ref),
            "ai_teacher_activity": plan,
            # Additive: why each next step was recommended — stable reason codes + parameters,
            # confidence/uncertainty and evidence counts (rendered from the guardian's own catalog).
            "recommendation_explanations": plan.get("recommendations", []),
            "recommendations": self._q.recommendations(student_ref)["recommendations"],
            "intervention_notifications": self._localized_interventions(student_ref, notifs),
            "offline_sync_status": sync_status(sessions, now),
            "achievement_history": [
                localizable_achievement(a)
                for a in self._q.achievements(student_ref)["achievements"]
            ],
        }

    # -- derivations ---------------------------------------------------------------------------
    def _interventions(self, student_ref: str, notifs: dict[str, Any]) -> list[dict[str, Any]]:
        # A guardian's "intervention" list = the learner's actionable notifications (revision due,
        # etc.) surfaced read-only. Reuses the notifications read model; no new logic.
        return [n for n in notifs["notifications"] if n.get("type") in ("revision_due", "at_risk")]

    def _localized_interventions(
        self, student_ref: str, notifs: dict[str, Any]
    ) -> list[dict[str, Any]]:
        notes = self._interventions(student_ref, notifs)
        due_count: int | None = None
        if any(n.get("type") == "revision_due" for n in notes):
            due_count = int(self._q.reviews(student_ref).get("due_count", 0))
        return [localizable_notification(n, due_count=due_count) for n in notes]
