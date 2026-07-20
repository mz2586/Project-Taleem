"""Curriculum Studio application-service tests: full authoring lifecycle + guards."""

from __future__ import annotations

import unittest

from taleem_core.contexts.curriculum_studio.application.repository import (
    InMemoryLessonRepository,
    RecordingPublishPort,
)
from taleem_core.contexts.curriculum_studio.application.service import (
    CurriculumStudioService,
    StudioError,
)
from taleem_core.contexts.curriculum_studio.domain.quality import all_gates_green
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction, WorkflowState
from tests.studio_helpers import make_valid_lesson

REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _service() -> CurriculumStudioService:
    t = [1000.0]

    def clock() -> float:
        t[0] += 1.0
        return t[0]

    return CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort(), clock=clock)


def _drive_to_approved(svc: CurriculumStudioService, lesson_id: str) -> None:
    svc.submit(lesson_id, actor_role="subject_author")
    for role in REVIEW_ROLES:
        svc.review(lesson_id, ReviewAction.APPROVE, actor_role=role)


class TestLifecycle(unittest.TestCase):
    def test_create_validate_submit_review_publish(self) -> None:
        svc = _service()
        svc.create(make_valid_lesson("L1"))
        self.assertTrue(svc.validate("L1").ok)
        _drive_to_approved(svc, "L1")
        self.assertEqual(svc.get("L1").workflow.state, WorkflowState.APPROVED)
        self.assertTrue(all_gates_green(svc.get("L1").quality_gate_results))  # all 9 gates
        published = svc.publish("L1", actor_role="curriculum_architect", change_summary="v1")
        self.assertEqual(published.workflow.state, WorkflowState.PUBLISHED)
        self.assertEqual(published.version, 1)
        self.assertEqual(len(published.version_history.versions), 1)

    def test_publish_emits_event(self) -> None:
        repo = InMemoryLessonRepository()
        pub = RecordingPublishPort()
        svc = CurriculumStudioService(repo, pub)
        svc.create(make_valid_lesson("L2"))
        _drive_to_approved(svc, "L2")
        svc.publish("L2", actor_role="curriculum_architect")
        self.assertEqual(pub.published, [("L2", 1)])


class TestGuards(unittest.TestCase):
    def test_submit_blocked_when_invalid(self) -> None:
        svc = _service()
        lesson = make_valid_lesson("L3")
        lesson.offline_package = ""  # break validation
        svc.create(lesson)
        with self.assertRaises(StudioError):
            svc.submit("L3", actor_role="subject_author")

    def test_no_self_approval(self) -> None:
        svc = _service()
        svc.create(make_valid_lesson("L4"))
        svc.submit("L4", actor_role="subject_author")
        # The author's role cannot review.
        lesson = svc.get("L4")
        lesson.metadata.author_role = "subject_expert"  # author shares the reviewer role
        with self.assertRaises(StudioError):
            svc.review("L4", ReviewAction.APPROVE, actor_role="subject_expert")

    def test_wrong_role_cannot_review(self) -> None:
        svc = _service()
        svc.create(make_valid_lesson("L5"))
        svc.submit("L5", actor_role="subject_author")
        with self.assertRaises(StudioError):  # needs subject_expert, not language_editor
            svc.review("L5", ReviewAction.APPROVE, actor_role="language_editor")

    def test_publish_blocked_before_approved(self) -> None:
        svc = _service()
        svc.create(make_valid_lesson("L6"))
        svc.submit("L6", actor_role="subject_author")
        with self.assertRaises(StudioError):
            svc.publish("L6", actor_role="curriculum_architect")

    def test_edit_only_in_draft(self) -> None:
        svc = _service()
        svc.create(make_valid_lesson("L7"))
        svc.submit("L7", actor_role="subject_author")
        with self.assertRaises(StudioError):
            svc.update(make_valid_lesson("L7"))

    def test_request_changes_reopens_draft(self) -> None:
        svc = _service()
        svc.create(make_valid_lesson("L8"))
        svc.submit("L8", actor_role="subject_author")
        svc.review("L8", ReviewAction.REQUEST_CHANGES, actor_role="subject_expert", note="fix")
        self.assertEqual(svc.get("L8").workflow.state, WorkflowState.DRAFT)


class TestVersioningRollback(unittest.TestCase):
    def test_rollback_to_prior_version(self) -> None:
        svc = _service()
        svc.create(make_valid_lesson("L9"))
        _drive_to_approved(svc, "L9")
        svc.publish("L9", actor_role="curriculum_architect", change_summary="v1")
        lesson = svc.get("L9")
        self.assertEqual(lesson.version, 1)
        rolled = svc.rollback("L9", target_version=1, actor_role="curriculum_architect")
        self.assertEqual(rolled.version, 1)
        # Audit records the rollback transition.
        actions = [t.action for t in rolled.workflow.history]
        self.assertIn(ReviewAction.ROLLBACK, actions)


if __name__ == "__main__":
    unittest.main()
