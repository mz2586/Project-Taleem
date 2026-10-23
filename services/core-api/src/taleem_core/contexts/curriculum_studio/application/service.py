"""Curriculum Studio application service — authoring workflow orchestration (pure-stdlib).

Enforces the workflow, quality gates, provenance, and versioning server-side (the UI cannot bypass).
See docs/10-curriculum-studio/AUTHORING_WORKFLOW.md.
"""

from __future__ import annotations

import builtins
import time
from collections.abc import Callable

from ....platform import observability
from ..domain import validation
from ..domain.audio import AudioAssetResolver
from ..domain.hierarchy import (
    EducationSystem,
    check_against_pack,
    merge_hierarchy,
    placement_errors,
)
from ..domain.lesson import Lesson
from ..domain.packs import CurriculumPack, PackRegistry, default_registry
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
from .repository import HierarchyRepository, LessonRepository, PublishPort

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
        on_commit: Callable[[], None] | None = None,
        audio_assets: AudioAssetResolver | None = None,
        packs: PackRegistry | None = None,
        hierarchy: HierarchyRepository | None = None,
    ) -> None:
        self._repo = repo
        # Gate dependencies: the audio-asset resolver (None = synthetic dev/test fixture refs only;
        # production wiring passes the media registry) and the curriculum-pack registry
        # (None = the packs shipped with the package).
        self._audio_assets = audio_assets
        self._packs = packs
        # Pack-scoped hierarchy store (None = not configured: upserts are refused, reads are empty).
        self._hierarchy = hierarchy
        self._publisher = publisher
        self._now: Callable[[], float] = clock if clock is not None else time.time
        # Commit inside the mutating method so an optimistic-lock conflict at commit is caught in
        # the request handler (mapped to 409), not during dependency teardown (which becomes a 500).
        # Defaults to a no-op: callers that own the Unit of Work commit it themselves.
        self._commit: Callable[[], None] = on_commit if on_commit is not None else (lambda: None)

    # ---- authoring ----
    def create(self, lesson: Lesson) -> Lesson:
        if self._repo.get(lesson.lesson_id) is not None:
            raise StudioError(f"lesson already exists: {lesson.lesson_id}")
        lesson.workflow.state = WorkflowState.DRAFT
        self._repo.save(lesson)
        self._commit()
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
        # Authorship is fixed at creation: an edit can never re-attribute the lesson.
        if existing.metadata.author_subject:
            lesson.metadata.author_subject = existing.metadata.author_subject
        self._repo.save(lesson)
        self._commit()
        return lesson

    # ---- curriculum hierarchy (scoped by curriculum pack) ----
    def upsert_hierarchy(self, pack_id: str, system: EducationSystem) -> EducationSystem:
        """Merge ``system`` (Grade → Subject → Chapter → Topic) into the pack's stored hierarchy.

        Validated against the pack first (grades, roster, title locales, duplicate keys); any
        violation raises ``StudioError`` and nothing is written. Idempotent and non-destructive:
        nodes match by key, titles merge per locale, nothing absent from ``system`` is removed.
        Returns the full stored hierarchy with canonical ids.
        """
        if self._hierarchy is None:
            raise StudioError("no hierarchy repository is configured for this service")
        pack = self._pack(pack_id)
        errors = check_against_pack(system, pack)
        if errors:
            raise StudioError(f"invalid hierarchy for {pack.pack_id}: " + "; ".join(errors))
        merged = merge_hierarchy(self._hierarchy.get(pack.pack_id), system, pack)
        self._hierarchy.save(merged, pack)
        self._commit()
        return merged

    def get_hierarchy(self, pack_id: str) -> EducationSystem | None:
        """The stored hierarchy for ``pack_id``, or None if none has been stored."""
        if self._hierarchy is None:
            return None
        return self._hierarchy.get(self._pack(pack_id).pack_id)

    def _pack(self, pack_id: str) -> CurriculumPack:
        pack = (self._packs if self._packs is not None else default_registry()).get(pack_id)
        if pack is None:
            raise StudioError(f"unknown curriculum pack {pack_id!r}")
        return pack

    # ---- validation ----
    def validate(self, lesson_id: str) -> validation.ValidationResult:
        return self._validate(self.get(lesson_id))

    # ---- workflow ----
    def submit(
        self, lesson_id: str, actor_role: str, note: str = "", actor_subject: str = ""
    ) -> Lesson:
        lesson = self.get(lesson_id)
        result = self._validate(lesson)
        if not result.ok:
            raise StudioError("cannot submit: automated validation failed (fix findings first)")
        # Store the automated gate results so they count toward the 9 at publish.
        for gr in result.gate_results:
            self._record_gate(lesson, gr)
        self._transition(lesson, ReviewAction.SUBMIT, actor_role, note, actor_subject)
        self._repo.save(lesson)
        self._commit()
        return lesson

    def review(
        self,
        lesson_id: str,
        action: ReviewAction,
        actor_role: str,
        note: str = "",
        actor_subject: str = "",
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
        # The same person may not author and review, whatever role their token carries now.
        if actor_subject and actor_subject in self._author_subjects(lesson):
            raise StudioError("no self-approval: the author cannot review their own lesson")
        if action is ReviewAction.APPROVE:
            for gate in STAGE_GATES.get(state, ()):
                self._record_gate(
                    lesson,
                    GateResult(
                        gate=gate,
                        passed=True,
                        mode="human",
                        reviewer_role=actor_role,
                        reviewer_subject=actor_subject,
                    ),
                )
        self._transition(lesson, action, actor_role, note, actor_subject)
        self._repo.save(lesson)
        self._commit()
        return lesson

    def publish(
        self, lesson_id: str, actor_role: str, change_summary: str = "", actor_subject: str = ""
    ) -> Lesson:
        lesson = self.get(lesson_id)
        if lesson.workflow.state is not WorkflowState.APPROVED:
            raise StudioError("only approved lessons can be published")
        if not self._validate(lesson).ok:
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
            # The lesson body at this version (prior versions are not nested inside it).
            snapshot={k: v for k, v in lesson.to_dict().items() if k != "version_history"},
        )
        lesson.version_history.add(version)
        lesson.version = version_no
        self._transition(lesson, ReviewAction.PUBLISH, actor_role, change_summary, actor_subject)
        self._repo.save(lesson)
        self._publisher.publish(lesson, version)
        self._commit()  # commit before telemetry so a conflict never logs a phantom publish
        observability.record_event("taleem_lessons_published_total")
        observability.log_event(
            "lesson_published", lesson_id=lesson.lesson_id, version=version.version
        )
        return lesson

    def rollback(
        self,
        lesson_id: str,
        target_version: int,
        actor_role: str,
        note: str = "",
        actor_subject: str = "",
    ) -> Lesson:
        lesson = self.get(lesson_id)
        target = lesson.version_history.get(target_version)
        if target is None:
            raise StudioError(f"version not found: {target_version}")
        lesson.version = target.version
        self._transition(
            lesson,
            ReviewAction.ROLLBACK,
            actor_role,
            note or f"rollback to v{target_version}",
            actor_subject,
        )
        self._repo.save(lesson)
        self._commit()
        return lesson

    # ---- helpers ----
    def _validate(self, lesson: Lesson) -> validation.ValidationResult:
        return validation.validate(
            lesson, self._packs, self._audio_assets, hierarchy=self._stored_hierarchy(lesson)
        )

    def _stored_hierarchy(self, lesson: Lesson) -> EducationSystem | None:
        """The stored hierarchy of the lesson's pack, fetched only when the lesson is placed."""
        meta = lesson.metadata
        if self._hierarchy is None or not (meta.chapter_key or meta.topic_key):
            return None
        registry = self._packs if self._packs is not None else default_registry()
        if registry.get(meta.curriculum_pack) is None:
            return None  # an unknown pack is already a BLOCKER in every pack-dependent check
        return self._hierarchy.get(meta.curriculum_pack)

    def placement_errors(self, lesson: Lesson) -> builtins.list[str]:
        """Why the lesson's chapter/topic placement is not in its pack's stored hierarchy."""
        meta = lesson.metadata
        return placement_errors(
            self._stored_hierarchy(lesson),
            pack_id=meta.curriculum_pack,
            grade_key=meta.grade_key,
            subject_key=meta.subject_key,
            chapter_key=meta.chapter_key,
            topic_key=meta.topic_key,
        )

    @staticmethod
    def _author_subjects(lesson: Lesson) -> set[str]:
        """Everyone who authored the lesson: its recorded author and whoever submitted it."""
        subjects = {lesson.metadata.author_subject}
        subjects |= {
            t.actor_subject for t in lesson.workflow.history if t.action is ReviewAction.SUBMIT
        }
        subjects.discard("")
        return subjects

    def _transition(
        self,
        lesson: Lesson,
        action: ReviewAction,
        actor_role: str,
        note: str,
        actor_subject: str = "",
    ) -> None:
        frm = lesson.workflow.state
        try:
            to = next_state(frm, action)
        except WorkflowError as exc:
            raise StudioError(str(exc)) from exc
        lesson.workflow.state = to
        lesson.workflow.history.append(
            TransitionRecord(
                frm, to, action, actor_role, float(self._now()), note, actor_subject=actor_subject
            )
        )

    @staticmethod
    def _record_gate(lesson: Lesson, result: GateResult) -> None:
        # Replace any prior result for this gate (last authoritative wins).
        lesson.quality_gate_results = [
            r for r in lesson.quality_gate_results if r.gate is not result.gate
        ]
        lesson.quality_gate_results.append(result)


__all__ = ["CurriculumStudioService", "StudioError"]
