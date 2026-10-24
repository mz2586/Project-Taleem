"""Adapters onto other contexts, built from callables the composition root supplies.

No school, identity or learning module is imported here: each adapter is duck-typed over the
JSON-shaped values those contexts' public services return, so the reporting context depends on
behaviour, not on their models.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..application.ports import ClassRoster, LearnerVisibility
from ..domain.report_card import EvidenceRecord, HomeworkOutcome, LessonPin, MasteryEvent


def _roster(row: dict[str, Any]) -> ClassRoster:
    return ClassRoster(
        class_id=str(row["class_id"]),
        organization_id=str(row["organization_id"]),
        class_name=str(row.get("class_name") or ""),
        organization_name=str(row.get("organization_name") or ""),
        curriculum_pack_id=str(row.get("curriculum_pack_id") or ""),
        student_refs=tuple(str(r) for r in row.get("student_refs") or ()),
        teacher_name=str(row.get("teacher_name") or ""),
    )


def _version(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


class CallableSchoolDirectory:
    """``SchoolDirectory`` over the school service (``reporting_roster(s)`` +
    ``marked_homework``). The school context's 404 / 403 Problems pass through unchanged.
    """

    def __init__(
        self,
        roster: Callable[[str, str], dict[str, Any]],
        rosters: Callable[[str], list[dict[str, Any]]],
        marked_homework: Callable[[str], list[dict[str, Any]]],
    ) -> None:
        self._roster = roster
        self._rosters = rosters
        self._homework = marked_homework

    def teacher_class(self, *, teacher_ref: str, class_id: str) -> ClassRoster:
        return _roster(self._roster(teacher_ref, class_id))

    def teacher_classes(self, teacher_ref: str) -> list[ClassRoster]:
        return [_roster(row) for row in self._rosters(teacher_ref)]

    def marked_homework(self, student_ref: str) -> list[HomeworkOutcome]:
        return [
            HomeworkOutcome(
                submission_id=str(r["submission_id"]),
                class_id=str(r["class_id"]),
                objective_code=str(r["objective_code"]),
                outcome=str(r["outcome"]),
                marked_at=float(r["marked_at"]),
            )
            for r in self._homework(student_ref)
            if r.get("outcome") and r.get("marked_at") is not None
        ]


class CallableLearnerDirectory:
    """``LearnerDirectory`` over identity. Every call reads live state (no cache)."""

    def __init__(
        self,
        guardian_of: Callable[[str], str | None],
        teacher_visibility: Callable[[list[str]], dict[str, dict[str, Any]]],
        learner: Callable[[str], dict[str, Any] | None],
    ) -> None:
        self._guardian_of = guardian_of
        self._visibility = teacher_visibility
        # ``learner(ref)`` -> ``{"display_name", "refusal"}`` (refusal: None | "inactive" |
        # "consent_withdrawn"), or None when there is no such learner.
        self._learner = learner

    def guardian_of(self, student_ref: str) -> str | None:
        return self._guardian_of(student_ref)

    def display_name(self, student_ref: str) -> str | None:
        row = self._learner(student_ref)
        return str(row.get("display_name") or "") if row else None

    def learning_refusal(self, student_ref: str) -> str | None:
        row = self._learner(student_ref)
        if row is None:
            return "inactive"
        refusal = row.get("refusal")
        return str(refusal) if refusal else None

    def teacher_visibility(self, student_refs: list[str]) -> dict[str, LearnerVisibility]:
        """``teacher_visibility(refs)`` returns ``{ref: {"display_name", "reason"}}``; a ref it
        leaves out is treated as hidden (``inactive``)."""
        refs = list(dict.fromkeys(r for r in student_refs if r))
        rows = self._visibility(refs) if refs else {}
        out: dict[str, LearnerVisibility] = {}
        for ref in refs:
            row = rows.get(ref) or {"reason": "inactive"}
            reason = row.get("reason")
            out[ref] = LearnerVisibility(
                display_name=str(row.get("display_name") or "") if reason is None else None,
                reason=str(reason) if reason is not None else None,
            )
        return out


class CallableLearningRecords:
    """``LearningRecords`` over the learning context's records service.

    ``records(student_ref)`` returns ``{"evidence": [{"evidence_id", "objective_code", "outcome",
    "context", "occurred_at", "lesson_id", "lesson_version"}], "mastered": [{"objective_code",
    "at"}]}``. A missing or null ``lesson_id`` / ``lesson_version`` stays unrecorded.
    """

    def __init__(self, records: Callable[[str], dict[str, Any]]) -> None:
        self._records = records

    def evidence(self, student_ref: str) -> list[EvidenceRecord]:
        return [
            EvidenceRecord(
                evidence_id=str(e["evidence_id"]),
                objective_code=str(e["objective_code"]),
                outcome=str(e["outcome"]),
                context=str(e["context"]),
                occurred_at=float(e["occurred_at"]),
                lesson_id=str(e.get("lesson_id") or ""),
                lesson_version=_version(e.get("lesson_version")),
            )
            for e in self._records(student_ref).get("evidence") or []
        ]

    def mastery_events(self, student_ref: str) -> list[MasteryEvent]:
        return [
            MasteryEvent(objective_code=str(m["objective_code"]), at=float(m["at"]))
            for m in self._records(student_ref).get("mastered") or []
            if m.get("objective_code")
        ]


class CallablePublishedLessons:
    """``PublishedLessons`` over the learning read model's ``published_versions`` rows."""

    def __init__(self, versions: Callable[[], list[dict[str, Any]]]) -> None:
        self._versions = versions

    def pins(self) -> dict[str, LessonPin]:
        out: dict[str, LessonPin] = {}
        for row in self._versions():
            code = str(row["objective_code"])
            if code in out:  # the first published lesson of an objective is the one taught
                continue
            out[code] = LessonPin(
                objective_code=code,
                lesson_id=str(row["lesson_id"]),
                version=int(row.get("version") or 0),
                curriculum_pack=str(row.get("curriculum_pack") or ""),
                subject_key=str(row.get("subject_key") or ""),
                title={str(k): str(v) for k, v in dict(row.get("title") or {}).items() if v},
                subject_name={
                    str(k): str(v) for k, v in dict(row.get("subject_name") or {}).items() if v
                },
            )
        return out
