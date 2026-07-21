"""Curriculum Studio application service — authoring workflow orchestration (pure-stdlib).

Enforces the workflow, quality gates, provenance, and versioning server-side (the UI cannot bypass).
See docs/10-curriculum-studio/AUTHORING_WORKFLOW.md.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ....platform import observability
from ..domain import validation
from ..domain.lesson import Lesson
from ..domain.quality import (
    ALL_GATES,
    Gate,
    GateResult,
    all_gates_green,
)
from ..domain.versioning import Version
from ..domain.workflow import (
    STATE_ROLE,
    ReviewAction,
    TransitionRecord,
    WorkflowError,
    WorkflowState,
    next_state,
)
from .repository import LessonRepository, PublishPort

# Which quality gates each human review stage certifies (the 4 remaining gates are auto pre-checks).
STAGE_GATES: dict[WorkflowState, tuple[Gate, ...]] = {
    WorkflowState.SUBJECT_EXPERT: (Gate.TECHNICAL_ACCURACY,),
    WorkflowState.EDUCATIONAL_QA: (Gate.EDUCATIONAL_REVIEW, Gate.AGE_APPROPRIATENESS),
    WorkflowState.ACCESSIBILITY: (Gate.ACCESSIBILITY,),
    WorkflowState.LANGUAGE: (Gate.LANGUAGE,),
    WorkflowState.AI_SAFETY: (Gate.AI_SAFETY,),
}


class StudioError(ValueError):
    """Raised on an invalid Curriculum Studio operation."""


class CurriculumStudioService:
    def __init__(
        self,
        repo: LessonRepository,
        publisher: PublishPort,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._repo = repo
        self._publisher = publisher
        self._now: Callable[[], float] = clock if clock is not None else time.time

    # ---- authoring ----
    def create(self, lesson: Lesson) -> Lesson:
        if self._repo.get(lesson.lesson_id) is not None:
            raise StudioError(f"lesson already exists: {lesson.lesson_id}")
        lesson.workflow.state = WorkflowState.DRAFT
        self._repo.save(lesson)
        return lesson

    def get(self, lesson_id: str) -> Lesson:
        lesson = self._repo.get(lesson_id)
        if lesson is None:
            raise StudioError(f"lesson not found: {lesson_id}")
        return lesson

    def find(self, lesson_id: str) -> Lesson | None:
        return self._repo.get(lesson_id)

    def list(self) -> list[Lesson]:
        return self._repo.all()

    def update(self, lesson: Lesson) -> Lesson:
        existing = self.get(lesson.lesson_id)
        if existing.workflow.state is not WorkflowState.DRAFT:
            raise StudioError("only draft lessons can be edited")
        lesson.workflow = existing.workflow
        lesson.version = existing.version
        lesson.version_history = existing.version_history
        self._repo.save(lesson)
        return lesson

    # ---- validation ----
    def validate(self, lesson_id: str) -> validation.ValidationResult:
        return validation.validate(self.get(lesson_id))

    # ---- workflow ----
    def submit(self, lesson_id: str, actor_role: str, note: str = "") -> Lesson:
        lesson = self.get(lesson_id)
        result = validation.validate(lesson)
        if not result.ok:
            raise StudioError("cannot submit: automated validation failed (fix findings first)")
        # Store the automated gate results so they count toward the 9 at publish.
        for gr in result.gate_results:
            self._record_gate(lesson, gr)
        self._transition(lesson, ReviewAction.SUBMIT, actor_role, note)
        self._repo.save(lesson)
        return lesson

    def review(
        self, lesson_id: str, action: ReviewAction, actor_role: str, note: str = ""
    ) -> Lesson:
        lesson = self.get(lesson_id)
        state = lesson.workflow.state
        expected_role = STATE_ROLE.get(state)
        if expected_role is None:
            raise StudioError(f"no review possible in state {state.value}")
        if actor_role != expected_role:
            raise StudioError(
                f"role {actor_role} may not review {state.value} (needs {expected_role})"
            )
        if actor_role == lesson.metadata.author_role:
            raise StudioError("no self-approval: the author cannot review their own lesson")
        if action is ReviewAction.APPROVE:
            for gate in STAGE_GATES.get(state, ()):
                self._record_gate(
                    lesson,
                    GateResult(gate=gate, passed=True, mode="human", reviewer_role=actor_role),
                )
        self._transition(lesson, action, actor_role, note)
        self._repo.save(lesson)
        return lesson

    def publish(self, lesson_id: str, actor_role: str, change_summary: str = "") -> Lesson:
        lesson = self.get(lesson_id)
        if lesson.workflow.state is not WorkflowState.APPROVED:
            raise StudioError("only approved lessons can be published")
        if not validation.validate(lesson).ok:
            raise StudioError("cannot publish: automated validation no longer passes")
        if not all_gates_green(lesson.quality_gate_results):
            missing = [
                g.value
                for g in ALL_GATES
                if not any(r.gate is g and r.passed for r in lesson.quality_gate_results)
            ]
            raise StudioError(f"cannot publish: gates not green: {missing}")
        version_no = lesson.version_history.next_version_number()
        version = Version(
            version=version_no,
            created_at=float(self._now()),
            author_role=actor_role,
            content_hash=lesson.content_hash(),
            change_summary=change_summary,
            snapshot=lesson.to_dict(),
        )
        lesson.version_history.add(version)
        lesson.version = version_no
        self._transition(lesson, ReviewAction.PUBLISH, actor_role, change_summary)
        self._repo.save(lesson)
        self._publisher.publish(lesson, version)
        observability.record_event("taleem_lessons_published_total")
        observability.log_event(
            "lesson_published", lesson_id=lesson.lesson_id, version=version.version
        )
        return lesson

    def rollback(
        self, lesson_id: str, target_version: int, actor_role: str, note: str = ""
    ) -> Lesson:
        lesson = self.get(lesson_id)
        target = lesson.version_history.get(target_version)
        if target is None:
            raise StudioError(f"version not found: {target_version}")
        lesson.version = target.version
        self._transition(
            lesson, ReviewAction.ROLLBACK, actor_role, note or f"rollback to v{target_version}"
        )
        self._repo.save(lesson)
        return lesson

    # ---- helpers ----
    def _transition(self, lesson: Lesson, action: ReviewAction, actor_role: str, note: str) -> None:
        frm = lesson.workflow.state
        try:
            to = next_state(frm, action)
        except WorkflowError as exc:
            raise StudioError(str(exc)) from exc
        lesson.workflow.state = to
        lesson.workflow.history.append(
            TransitionRecord(frm, to, action, actor_role, float(self._now()), note)
        )

    @staticmethod
    def _record_gate(lesson: Lesson, result: GateResult) -> None:
        # Replace any prior result for this gate (last authoritative wins).
        lesson.quality_gate_results = [
            r for r in lesson.quality_gate_results if r.gate is not result.gate
        ]
        lesson.quality_gate_results.append(result)


__all__ = ["CurriculumStudioService", "StudioError"]
