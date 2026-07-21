"""StudentQueryService — the derived read models behind the student-facing query APIs.

Composes the Student Knowledge Model, immutable evidence, and the outbox (via StudentReadModel) with
the published-curriculum read model to produce homework, assessments, revision queue, timetable,
notifications, achievements, history, recommendations, and the dashboard aggregate. Derived —
no new child-data tables; governance-safe. Reads only.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..adapters.persistence.student_read_model import SqlAlchemyStudentReadModel
from ..adapters.persistence.uow import LearningUnitOfWork
from .ports import CurriculumReadModel, EvidenceRow, ObjectiveStateRow

_REVIEW_STATES = {"needs_review", "at_risk"}
_DEFAULT_EST_MINUTES = 10


class StudentQueryService:
    def __init__(
        self,
        uow_factory: Callable[[], LearningUnitOfWork],
        curriculum: CurriculumReadModel,
        clock: Callable[[], float],
    ) -> None:
        self._uow = uow_factory
        self._curriculum = curriculum
        self._now = clock

    # -- shared reads ---------------------------------------------------------------------

    def _states(self, student_ref: str) -> list[ObjectiveStateRow]:
        with self._uow() as uow:
            return SqlAlchemyStudentReadModel(uow.session).objective_states(student_ref)

    def _evidence(self, student_ref: str) -> list[EvidenceRow]:
        with self._uow() as uow:
            return SqlAlchemyStudentReadModel(uow.session).evidence(student_ref)

    def _events(self, student_ref: str) -> list[dict[str, Any]]:
        with self._uow() as uow:
            rows = SqlAlchemyStudentReadModel(uow.session).knowledge_events(student_ref)
        return [{"type": r.event_type, "payload": r.payload, "at": r.occurred_at} for r in rows]

    # -- surfaces -------------------------------------------------------------------------

    def homework(self, student_ref: str) -> dict[str, Any]:
        done_items = {e.item_ref for e in self._evidence(student_ref)}
        items: list[dict[str, Any]] = []
        for lesson in self._curriculum.published_lessons():
            for hw in lesson.homework_items:
                items.append(
                    {
                        "item_ref": hw.item_ref,
                        "objective_code": hw.objective_code,
                        "prompt": hw.prompt,
                        "status": "done" if hw.item_ref in done_items else "todo",
                        "est_minutes": _DEFAULT_EST_MINUTES,
                    }
                )
        return {"items": items}

    def assessments(self, student_ref: str) -> dict[str, Any]:
        out: list[dict[str, Any]] = []
        for lesson in self._curriculum.published_lessons():
            if lesson.assessment_formative:
                out.append(
                    {
                        "id": f"{lesson.lesson_id}:formative",
                        "objective_code": lesson.objective_code,
                        "type": "formative",
                        "item_count": len(lesson.assessment_formative),
                        "mentor_mediated": False,
                    }
                )
            if lesson.assessment_summative:
                out.append(
                    {
                        "id": f"{lesson.lesson_id}:summative",
                        "objective_code": lesson.objective_code,
                        "type": "summative",
                        "item_count": len(lesson.assessment_summative),
                        # Summative is mentor-mediated / identity-assured — never auto-graded here.
                        "mentor_mediated": lesson.summative_mentor_mediated,
                    }
                )
        return {"assessments": out}

    def reviews(self, student_ref: str) -> dict[str, Any]:
        now = self._now()
        due = [
            s
            for s in self._states(student_ref)
            if s.state in _REVIEW_STATES or (s.next_review_at and s.next_review_at <= now)
        ]
        # Highest retention risk first (lowest mastery).
        due.sort(key=lambda s: s.mastery)
        reviews = [
            {
                "objective_code": s.objective_code,
                "due_at": s.next_review_at,
                "last_seen_at": s.last_seen_at,
                "mastery": round(s.mastery, 3),
                "reason": s.state,
            }
            for s in due
        ]
        return {"reviews": reviews, "due_count": len(reviews)}

    def timetable(self, student_ref: str) -> dict[str, Any]:
        states = {s.objective_code: s for s in self._states(student_ref)}
        blocks: list[dict[str, Any]] = []
        for info in sorted(self._curriculum.published_graph().objectives, key=lambda o: o.sequence):
            st = states.get(info.objective_code)
            if st is None or st.state != "mastered":
                blocks.append(
                    {"objective_code": info.objective_code, "est_minutes": _DEFAULT_EST_MINUTES}
                )
        # A single suggested "today" block set derived from the plan (no fixed calendar).
        return {"days": [{"day_offset": 0, "blocks": blocks[:4]}]}

    def notifications(self, student_ref: str) -> dict[str, Any]:
        notes: list[dict[str, Any]] = []
        review = self.reviews(student_ref)
        if review["due_count"] > 0:
            notes.append(
                {
                    "id": "revision-due",
                    "type": "revision_due",
                    "message": f"You have {review['due_count']} idea(s) to review today.",
                    "read": False,
                    "action": "/student/session",
                }
            )
        for ev in self._events(student_ref):
            if ev["type"] == "ObjectiveMastered":
                code = ev["payload"].get("objective_code", "")
                notes.append(
                    {
                        "id": f"mastered-{code}",
                        "type": "mastered",
                        "message": f"Great work — you mastered {code}!",
                        "read": False,
                        "action": "/student/progress",
                    }
                )
        return {"notifications": notes, "unread": len(notes)}

    def mark_notification_read(self, student_ref: str, notification_id: str) -> None:
        # Notifications are derived (deterministic ids); read-state is tracked client-side in this
        # phase to avoid a new child-data table. Accepted as a no-op server-side.
        return None

    def achievements(self, student_ref: str) -> dict[str, Any]:
        earned: list[dict[str, Any]] = []
        for ev in self._events(student_ref):
            if ev["type"] == "ObjectiveMastered":
                code = ev["payload"].get("objective_code", "")
                earned.append(
                    {
                        "id": f"mastery-{code}",
                        "name": f"Mastered {code}",
                        "description": "You mastered a new idea.",
                        "earned_at": ev["at"],
                    }
                )
            elif ev["type"] == "MisconceptionCleared":
                code = ev["payload"].get("objective_code", "")
                earned.append(
                    {
                        "id": f"cleared-{code}-{ev['at']}",
                        "name": "Cleared a misconception",
                        "description": "You corrected a tricky idea.",
                        "earned_at": ev["at"],
                    }
                )
        mastered_count = sum(1 for e in earned if e["id"].startswith("mastery-"))
        return {"achievements": earned, "mastered_count": mastered_count}

    def history(self, student_ref: str, limit: int = 50) -> dict[str, Any]:
        evidence = self._evidence(student_ref)
        by_session: dict[str, dict[str, Any]] = {}
        by_objective: dict[str, dict[str, Any]] = {}
        for e in evidence:
            s = by_session.setdefault(
                e.session_id,
                {
                    "session_id": e.session_id,
                    "objectives": set(),
                    "attempts": 0,
                    "correct": 0,
                    "at": e.occurred_at,
                },
            )
            s["objectives"].add(e.objective_code)
            s["attempts"] += 1
            s["correct"] += 1 if e.outcome == "correct" else 0
            s["at"] = max(s["at"], e.occurred_at)

            o = by_objective.setdefault(
                e.objective_code,
                {"objective_code": e.objective_code, "attempts": 0, "last_at": e.occurred_at},
            )
            o["attempts"] += 1
            o["last_at"] = max(o["last_at"], e.occurred_at)

        sessions = sorted(
            ({**s, "objectives": sorted(s["objectives"])} for s in by_session.values()),
            key=lambda s: s["at"],
            reverse=True,
        )[:limit]
        lessons = sorted(by_objective.values(), key=lambda o: o["last_at"], reverse=True)[:limit]
        return {"sessions": sessions, "lessons": lessons}

    def recommendations(self, student_ref: str) -> dict[str, Any]:
        states = {s.objective_code: s for s in self._states(student_ref)}
        recs: list[dict[str, Any]] = []
        # 1. Active misconceptions -> remediate.
        for s in states.values():
            if s.active_misconceptions and s.state != "mastered":
                recs.append(
                    {"objective_code": s.objective_code, "reason": "remediate", "priority": 1}
                )
        # 2. Due reviews.
        for r in self.reviews(student_ref)["reviews"]:
            recs.append({"objective_code": r["objective_code"], "reason": "review", "priority": 2})
        # 3. Next unlearned objective from the plan.
        for info in sorted(self._curriculum.published_graph().objectives, key=lambda o: o.sequence):
            st = states.get(info.objective_code)
            if st is None or st.state not in ("mastered",):
                recs.append(
                    {"objective_code": info.objective_code, "reason": "learn", "priority": 3}
                )
                break
        recs.sort(key=lambda r: r["priority"])
        return {"recommendations": recs[:5]}

    def today(self, student_ref: str) -> dict[str, Any]:
        states = self._states(student_ref)
        mastered = sum(1 for s in states if s.state == "mastered")
        in_progress = sum(1 for s in states if s.state == "in_progress")
        reviews = self.reviews(student_ref)
        recs = self.recommendations(student_ref)["recommendations"]
        next_action = (
            recs[0] if recs else {"objective_code": None, "reason": "complete", "priority": 9}
        )
        return {
            "next_action": {
                "objective_code": next_action["objective_code"],
                "reason": next_action["reason"],
            },
            "mastery_summary": {
                "mastered": mastered,
                "in_progress": in_progress,
                "total": len(states),
            },
            "revision_due_count": reviews["due_count"],
        }
