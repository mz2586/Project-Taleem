"""Curriculum Studio domain tests: provenance, workflow, validation, versioning."""

from __future__ import annotations

import unittest

from taleem_core.contexts.curriculum_studio.domain import validation
from taleem_core.contexts.curriculum_studio.domain.hierarchy import (
    is_valid_grade_subject,
    subjects_for,
)
from taleem_core.contexts.curriculum_studio.domain.provenance import (
    Derivation,
    Provenance,
    ProvenanceError,
    assert_admissible,
    check_provenance,
)
from taleem_core.contexts.curriculum_studio.domain.workflow import (
    ReviewAction,
    WorkflowError,
    WorkflowState,
    next_state,
)
from tests.studio_helpers import make_valid_lesson


class TestHierarchy(unittest.TestCase):
    def test_roster(self) -> None:
        self.assertIn("math", subjects_for("G1"))
        self.assertIn("physics", subjects_for("G9"))
        self.assertTrue(is_valid_grade_subject("G1", "math"))
        self.assertFalse(is_valid_grade_subject("G1", "physics"))  # physics only 9-10


class TestProvenance(unittest.TestCase):
    def test_authored_original_needs_slo(self) -> None:
        self.assertTrue(check_provenance(Provenance(aligned_slo_codes=[])))  # findings present
        self.assertFalse(check_provenance(Provenance(aligned_slo_codes=["MATH-G1-N-01"])))

    def test_prohibited_source_rejected(self) -> None:
        p = Provenance(derivation=Derivation.INGESTED, source="scanned textbook", license="x")
        with self.assertRaises(ProvenanceError):
            assert_admissible(p)

    def test_ingested_needs_license_or_permission(self) -> None:
        self.assertTrue(
            check_provenance(Provenance(derivation=Derivation.INGESTED, license="none"))
        )
        self.assertFalse(
            check_provenance(
                Provenance(
                    derivation=Derivation.INGESTED, license="CC-BY-4.0", aligned_slo_codes=["x"]
                )
            )
        )
        self.assertFalse(
            check_provenance(
                Provenance(
                    derivation=Derivation.INGESTED,
                    license="proprietary",
                    permission_ref="MoU-2026-NCC",
                    aligned_slo_codes=["x"],
                )
            )
        )


class TestWorkflow(unittest.TestCase):
    def test_full_chain(self) -> None:
        s = WorkflowState.DRAFT
        s = next_state(s, ReviewAction.SUBMIT)
        self.assertEqual(s, WorkflowState.SUBJECT_EXPERT)
        for _ in range(5):  # 5-stage review chain → APPROVED
            s = next_state(s, ReviewAction.APPROVE)
        self.assertEqual(s, WorkflowState.APPROVED)
        s = next_state(s, ReviewAction.PUBLISH)
        self.assertEqual(s, WorkflowState.PUBLISHED)

    def test_request_changes_returns_to_draft(self) -> None:
        s = next_state(WorkflowState.SUBJECT_EXPERT, ReviewAction.REQUEST_CHANGES)
        self.assertEqual(s, WorkflowState.DRAFT)

    def test_illegal_transition_raises(self) -> None:
        with self.assertRaises(WorkflowError):
            next_state(WorkflowState.DRAFT, ReviewAction.PUBLISH)


class TestValidation(unittest.TestCase):
    def test_valid_lesson_passes(self) -> None:
        result = validation.validate(make_valid_lesson())
        self.assertTrue(result.ok, msg=str([f.message for f in result.structural]))

    def test_missing_audio_fails_accessibility(self) -> None:
        lesson = make_valid_lesson()
        lesson.student_explanation.audio_ref = {}  # remove Urdu audio
        result = validation.validate(lesson)
        self.assertFalse(result.ok)

    def test_missing_outcome_fails(self) -> None:
        lesson = make_valid_lesson()
        lesson.learning_outcomes = []
        self.assertFalse(validation.validate(lesson).ok)

    def test_readability_too_long_fails(self) -> None:
        from taleem_core.contexts.curriculum_studio.domain.content import Locale

        lesson = make_valid_lesson()
        long = " ".join(["لفظ"] * 20) + "۔"  # 20-word sentence, G1 max is 8
        lesson.student_explanation.text[Locale.UR] = long
        self.assertFalse(validation.validate(lesson).ok)

    def test_content_hash_stable(self) -> None:
        a = make_valid_lesson().content_hash()
        b = make_valid_lesson().content_hash()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
