"""Written work — the learning context's side of HOMEWORK_AND_MARKING_CONTRACT.md.

Two operations, exposed to the school context through its ``WrittenWork`` port (wired in the
composition root; school never imports this module):

- ``written_lesson`` reads one objective's published written items, as plain JSON-shaped dicts.
  The dict carries the teacher-only marking aids (rubric, sample answer, guidance) next to the
  learner-visible fields; the school context decides which surface may see which (a learner
  response never carries a marking aid).
- ``record_marked`` turns a teacher's mark into ONE ``AssessmentEvidence``, idempotent by
  ``submission_id``, through the knowledge aggregate + outbox (``KnowledgeService``).

Written items are never auto-scored: nothing here looks at the learner's text.
"""

from __future__ import annotations

from typing import Any

from ..domain.curriculum_view import ItemView
from .knowledge_service import KnowledgeService
from .ports import CurriculumReadModel


def written_item_dict(item: ItemView) -> dict[str, Any]:
    """Learner-visible fields plus the teacher-only marking aids of one written item."""
    return {
        "item_ref": item.item_ref,
        "prompt": dict(item.prompt),
        "hints": list(item.hints),
        "max_chars": item.max_chars,
        **item.teacher_fields(),
    }


class WrittenWorkService:
    def __init__(self, curriculum: CurriculumReadModel, knowledge: KnowledgeService) -> None:
        self._curriculum = curriculum
        self._knowledge = knowledge

    def written_lesson(self, objective_code: str) -> dict[str, Any] | None:
        """The published lesson for ``objective_code`` with its written items, or None."""
        lesson = self._curriculum.lesson_for(objective_code)
        if lesson is None:
            return None
        return {
            "objective_code": objective_code,
            "lesson_id": lesson.lesson_id,
            "title": dict(lesson.title),
            "items": [written_item_dict(i) for i in lesson.written_items],
        }

    def record_marked(
        self,
        *,
        submission_id: str,
        student_ref: str,
        objective_code: str,
        item_ref: str,
        met: bool,
    ) -> bool:
        """Record the mark as evidence (correct = ``met``). False when already recorded.

        The evidence names the published lesson the written item belongs to, with its version,
        as it stands when the teacher marks it. The item must still be in that lesson: if it is
        not (the lesson was republished or rolled back without it, or unpublished), the lesson
        the learner wrote for is unknown and the evidence records no lesson and no version rather
        than guessing one.
        """
        lesson = self._curriculum.lesson_for(objective_code)
        served = lesson is not None and lesson.written_item(item_ref) is not None
        return self._knowledge.record_human_graded(
            evidence_id=submission_id,
            student_ref=student_ref,
            objective_code=objective_code,
            item_ref=item_ref,
            correct=met,
            lesson_id=lesson.lesson_id if lesson is not None and served else "",
            lesson_version=lesson.version if lesson is not None and served else None,
        )
