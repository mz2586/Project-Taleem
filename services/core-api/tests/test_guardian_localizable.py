"""Guardian read model: stable ``kind`` + ``objective_code`` so the client can localize.

The learning read model produces learner-facing English (``message``, ``name``, ``description``).
The guardian projection keeps that text for compatibility and adds machine-readable fields.
"""

from __future__ import annotations

from typing import Any

from taleem_core.contexts.guardian.application.directory import GuardianDirectory
from taleem_core.contexts.guardian.application.guardian_service import (
    ACHIEVEMENT_KINDS,
    NOTIFICATION_KINDS,
    GuardianService,
    localizable_achievement,
    localizable_notification,
)


def test_revision_due_carries_its_count_as_a_param() -> None:
    note = {"id": "revision-due", "type": "revision_due", "message": "You have 3 idea(s)…"}
    out = localizable_notification(note, due_count=3)
    assert out["kind"] == "revision_due"
    assert out["objective_code"] is None
    assert out["params"] == {"due_count": 3}
    assert out["message"] == note["message"]  # English kept


def test_mastered_notification_maps_to_a_stable_kind_and_code() -> None:
    out = localizable_notification({"id": "mastered-M4.FR-1", "type": "mastered"})
    assert (out["kind"], out["objective_code"], out["params"]) == (
        "objective_mastered",
        "M4.FR-1",
        {},
    )


def test_an_explicit_objective_code_wins_and_unknown_types_pass_through() -> None:
    out = localizable_notification({"id": "x", "type": "at_risk", "objective_code": "OBJ-9"})
    assert (out["kind"], out["objective_code"]) == ("at_risk", "OBJ-9")
    assert localizable_notification({"id": "y"})["kind"] == "unknown"


def test_achievements_map_to_kinds_with_codes_even_when_the_code_has_dashes() -> None:
    mastered = localizable_achievement(
        {"id": "mastery-PK-M4-FR-01", "name": "Mastered PK-M4-FR-01", "earned_at": 10.0}
    )
    assert (mastered["kind"], mastered["objective_code"]) == ("objective_mastered", "PK-M4-FR-01")
    assert mastered["name"] == "Mastered PK-M4-FR-01"

    cleared = localizable_achievement(
        {"id": "cleared-PK-M4-FR-01-1234.5", "name": "Cleared", "earned_at": 1234.5}
    )
    assert (cleared["kind"], cleared["objective_code"]) == (
        "misconception_cleared",
        "PK-M4-FR-01",
    )

    other = localizable_achievement({"id": "streak-7"})
    assert (other["kind"], other["objective_code"]) == ("achievement", None)


def test_kinds_are_published() -> None:
    assert "revision_due" in NOTIFICATION_KINDS
    assert set(ACHIEVEMENT_KINDS) == {"objective_mastered", "misconception_cleared"}


class _Progress:
    def to_dict(self) -> dict[str, Any]:
        return {
            "objectives_mastered": 1,
            "objectives_in_progress": 0,
            "accuracy": 1.0,
            "total_attempts": 3,
            "objective_mastery": {"OBJ-1": 0.97},
        }


class _Analytics:
    def progress_summary(self, student_ref: str) -> _Progress:
        return _Progress()


class _AI:
    def plan(self, student_ref: str) -> dict[str, Any]:
        return {}


class _Queries:
    def today(self, student_ref: str) -> dict[str, Any]:
        return {}

    def history(self, student_ref: str, limit: int = 50) -> dict[str, Any]:
        return {"sessions": []}

    def assessments(self, student_ref: str) -> dict[str, Any]:
        return {}

    def achievements(self, student_ref: str) -> dict[str, Any]:
        return {
            "achievements": [{"id": "mastery-OBJ-1", "name": "Mastered OBJ-1", "earned_at": 5.0}],
            "mastered_count": 1,
        }

    def notifications(self, student_ref: str) -> dict[str, Any]:
        return {
            "notifications": [
                {"id": "revision-due", "type": "revision_due", "message": "You have 2 idea(s)."},
                {"id": "mastered-OBJ-1", "type": "mastered", "message": "Great work"},
            ]
        }

    def recommendations(self, student_ref: str) -> dict[str, Any]:
        return {"recommendations": []}

    def reviews(self, student_ref: str) -> dict[str, Any]:
        return {"due_count": 2}


def test_the_child_overview_carries_localizable_fields() -> None:
    service = GuardianService(
        GuardianDirectory.from_csv("g:c"), _Queries(), _Analytics(), _AI(), lambda: 100.0
    )
    overview = service.child_overview("c")
    interventions = overview["intervention_notifications"]
    assert [n["kind"] for n in interventions] == ["revision_due"]  # mastered is not an intervention
    assert interventions[0]["params"] == {"due_count": 2}
    assert interventions[0]["message"] == "You have 2 idea(s)."
    achievements = overview["achievement_history"]
    assert [(a["kind"], a["objective_code"]) for a in achievements] == [
        ("objective_mastered", "OBJ-1")
    ]
    assert service.child_summary("c")["open_interventions"] == 1
