"""Domain <-> ORM mapping for the Lesson aggregate.

The domain ``Lesson`` is deliberately persistence-ignorant (no ``lock_version``, no surrogate id).
This module is the only place that knows both worlds. It splits the aggregate into:

- the authored *document* (content-only fields) → ``lesson.body`` JSONB (architecture §2);
- queryable *columns* projected from the document (placement, state, provenance summary);
- append-only *child rows* (versions, workflow transitions) and current-head gate rows.

On load it does the inverse, reconstituting a faithful ``Lesson`` so the application layer never
sees the ORM. ``round-trip`` fidelity (``Lesson == from_row(to_row(Lesson))``) is asserted in tests.
"""

from __future__ import annotations

from typing import Any

from ...domain.lesson import Lesson
from ...domain.quality import Finding, Gate, GateResult
from ...domain.versioning import Version
from ...domain.workflow import ReviewAction, TransitionRecord, Workflow, WorkflowState
from . import serde
from .models import (
    LessonRow,
    LessonVersionRow,
    QualityGateResultRow,
    WorkflowTransitionRow,
)

# Fields excluded from the document body (they live in columns/child tables). Mirrors the
# exclusion set of ``Lesson.content_hash`` so body and hash describe the same content.
_BOOKKEEPING = ("workflow", "quality_gate_results", "version", "version_history")


def to_body(lesson: Lesson) -> dict[str, Any]:
    """Serialize the authored document (content-only) for the ``lesson.body`` JSONB column."""
    full = serde.to_jsonable(lesson)
    return {k: v for k, v in full.items() if k not in _BOOKKEEPING}


def column_values(lesson: Lesson) -> dict[str, Any]:
    """Project the queryable columns from the aggregate (architecture §15)."""
    return {
        "lesson_key": lesson.lesson_id,
        "grade_key": lesson.metadata.grade_key,
        "subject_key": lesson.metadata.subject_key,
        "state": lesson.workflow.state.value,
        "difficulty": lesson.difficulty.value,
        "estimated_duration_min": lesson.estimated_duration_min,
        "author_role": lesson.metadata.author_role,
        "derivation": lesson.provenance.derivation.value,
        "license": lesson.provenance.license,
        "content_hash": lesson.content_hash(),
        "current_version_no": lesson.version,
        "tags": list(lesson.metadata.tags),
        "body": to_body(lesson),
    }


def gate_values(result: GateResult) -> dict[str, Any]:
    """Row values for one quality-gate result (id/lesson_id added by the repository)."""
    return {
        "gate": result.gate.value,
        "passed": result.passed,
        "mode": result.mode,
        "reviewer_role": result.reviewer_role,
        "findings": serde.to_jsonable(result.findings),
    }


def transition_values(record: TransitionRecord) -> dict[str, Any]:
    """Row values for one workflow transition (append-only)."""
    return {
        "from_state": record.from_state.value,
        "to_state": record.to_state.value,
        "action": record.action.value,
        "actor_role": record.actor_role,
        "note": record.note,
    }


def version_values(version: Version) -> dict[str, Any]:
    """Row values for one immutable published version (append-only)."""
    return {
        "version_no": version.version,
        "content_hash": version.content_hash,
        "body_snapshot": version.snapshot,
        "change_summary": version.change_summary,
        "author_role": version.author_role,
    }


def _gate_from_row(row: QualityGateResultRow) -> GateResult:
    findings = [serde.build(Finding, f) for f in (row.findings or [])]
    return GateResult(
        gate=Gate(row.gate),
        passed=row.passed,
        mode=row.mode,
        reviewer_role=row.reviewer_role,
        findings=findings,
        at=row.created_at.timestamp() if row.created_at else 0.0,
    )


def _transition_from_row(row: WorkflowTransitionRow) -> TransitionRecord:
    return TransitionRecord(
        from_state=WorkflowState(row.from_state),
        to_state=WorkflowState(row.to_state),
        action=ReviewAction(row.action),
        actor_role=row.actor_role,
        at=row.at.timestamp() if row.at else 0.0,
        note=row.note,
    )


def _version_from_row(row: LessonVersionRow) -> Version:
    return Version(
        version=row.version_no,
        created_at=row.created_at.timestamp() if row.created_at else 0.0,
        author_role=row.author_role,
        content_hash=row.content_hash,
        change_summary=row.change_summary,
        snapshot=dict(row.body_snapshot or {}),
    )


def from_row(row: LessonRow) -> Lesson:
    """Reconstruct a faithful domain ``Lesson`` from a loaded ``LessonRow`` (+ its children)."""
    lesson = serde.build(Lesson, dict(row.body))
    # Re-attach the persistence-managed bookkeeping the body deliberately excludes.
    lesson.workflow = Workflow(
        state=WorkflowState(row.state),
        history=[_transition_from_row(t) for t in row.transitions],
    )
    lesson.quality_gate_results = [_gate_from_row(g) for g in row.gates]
    lesson.version = row.current_version_no
    for v in row.versions:
        lesson.version_history.add(_version_from_row(v))
    return lesson
