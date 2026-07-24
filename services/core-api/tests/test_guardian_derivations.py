"""Guardian derivations — the only NEW logic (streak / attendance / weekly / sync freshness).

These are pure functions over the sessions the existing history read model already returns.
"""

from __future__ import annotations

from taleem_core.contexts.guardian.application import guardian_service as gs

_DAY = 86_400.0


def _sessions(
    day_offsets: list[int], attempts: int = 2, correct: int = 1
) -> list[dict[str, object]]:
    # A session per given day offset from a base; timestamps mid-day to avoid boundary ambiguity.
    base = 1_000 * _DAY
    return [
        {"at": base + off * _DAY + _DAY / 2, "attempts": attempts, "correct": correct}
        for off in day_offsets
    ]


def _now(offset_days: int) -> float:
    return 1_000 * _DAY + offset_days * _DAY + _DAY / 2


def test_streak_counts_consecutive_days_ending_today() -> None:
    # Active days 0..4 with a gap at day 2; "now" is day 4 -> current run is days 3,4.
    s = _sessions([0, 1, 3, 4])
    out = gs.streak(s, _now(4))
    assert out["current"] == 2  # days 3,4 ending "today"
    assert out["longest"] == 2  # {0,1} and {3,4} are the runs of length 2


def test_streak_zero_when_last_activity_is_stale() -> None:
    s = _sessions([0, 1, 2])
    out = gs.streak(s, _now(10))  # last active 8 days ago
    assert out["current"] == 0
    assert out["longest"] == 3
    assert out["last_active_day"] is not None


def test_streak_empty() -> None:
    out = gs.streak([], _now(0))
    assert out == {"current": 0, "longest": 0, "last_active_day": None}


def test_attendance_distinct_days() -> None:
    s = _sessions([0, 0, 1, 5])  # two sessions on day 0
    out = gs.attendance(s)
    assert out["active_days"] == 3  # days 0, 1, 5


def test_weekly_summary_window() -> None:
    s = _sessions([0, 3, 6, 10], attempts=4, correct=2)  # day 10 is outside the last 7 days
    out = gs.weekly_summary(s, _now(12))  # trailing-7-day window (days ~5..12): day 6 + day 10
    # days within [5,12]: day 6 and day 10 -> 2 sessions
    assert out["sessions"] == 2
    assert out["attempts"] == 8
    assert out["accuracy"] == 0.5


def test_sync_status_fresh_vs_stale() -> None:
    fresh = gs.sync_status(_sessions([0]), _now(0))
    assert fresh["is_stale"] is False
    assert fresh["last_synced_at"] is not None
    stale = gs.sync_status(_sessions([0]), _now(10))
    assert stale["is_stale"] is True
    empty = gs.sync_status([], _now(0))
    assert empty["is_stale"] is True
    assert empty["last_synced_at"] is None
