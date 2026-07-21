"""Integration test: the full end-to-end vertical slice (Phase 4.1)."""

from __future__ import annotations

from taleem_core.vertical_slice.runner import run_slice


def test_vertical_slice_runs_end_to_end() -> None:
    result = run_slice()

    # The lesson was authored + published through Curriculum Studio's real persistence.
    assert result["summary"]["objective_mastery"]  # objective present

    # Decision flow proves the whole loop fired: teach -> ... -> remediate -> complete.
    flow = result["decision_flow"]
    assert flow[0] == "teach"
    assert "remediate" in flow
    assert flow[-1] == "complete"

    # The learner mastered the objective and the session closed cleanly.
    assert result["mastered"] is True
    assert result["session_state"] == "ended"
    assert result["final_decision"] == "complete"


def test_vertical_slice_records_knowledge_and_events() -> None:
    summary = run_slice()["summary"]
    assert summary["objectives_mastered"] == 1
    assert summary["misconceptions_detected"] == 1  # confirmed once
    assert summary["misconceptions_cleared"] == 1
    assert summary["reviews_scheduled"] == 1
    assert summary["total_attempts"] >= 5
    # Events persisted to the outbox for analytics/downstream consumers.
    events = summary["events_by_type"]
    assert events["ObjectiveMastered"] == 1
    assert events["InteractionRecorded"] >= 5
    assert summary["objective_mastery"]["MATH-G4-FR-01"] >= 0.85


def test_vertical_slice_trace_renders() -> None:
    trace = run_slice()["trace"]
    text = trace.render()
    assert "EXECUTION TRACE" in text
    assert "PUBLISHED immutable version" in text
    assert "objective MASTERED" in text
