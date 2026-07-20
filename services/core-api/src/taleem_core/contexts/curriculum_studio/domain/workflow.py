"""Authoring workflow state machine (pure-stdlib).

See docs/10-curriculum-studio/AUTHORING_WORKFLOW.md. Illegal transitions are rejected by the domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class WorkflowState(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    SUBJECT_EXPERT = "subject_expert"
    EDUCATIONAL_QA = "educational_qa"
    ACCESSIBILITY = "accessibility"
    LANGUAGE = "language"
    AI_SAFETY = "ai_safety"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ReviewAction(StrEnum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    PUBLISH = "publish"
    ROLLBACK = "rollback"
    ARCHIVE = "archive"


# The ordered review chain (each gate role approves to advance).
REVIEW_CHAIN: tuple[WorkflowState, ...] = (
    WorkflowState.SUBJECT_EXPERT,
    WorkflowState.EDUCATIONAL_QA,
    WorkflowState.ACCESSIBILITY,
    WorkflowState.LANGUAGE,
    WorkflowState.AI_SAFETY,
)

# The role responsible for each review state (no self-approval — enforced in the service).
STATE_ROLE: dict[WorkflowState, str] = {
    WorkflowState.SUBJECT_EXPERT: "subject_expert",
    WorkflowState.EDUCATIONAL_QA: "instructional_designer",
    WorkflowState.ACCESSIBILITY: "a11y_specialist",
    WorkflowState.LANGUAGE: "language_editor",
    WorkflowState.AI_SAFETY: "safety_officer",
}


class WorkflowError(ValueError):
    """Raised on an illegal workflow transition."""


@dataclass
class TransitionRecord:
    from_state: WorkflowState
    to_state: WorkflowState
    action: ReviewAction
    actor_role: str
    at: float
    note: str = ""


@dataclass
class Workflow:
    """Holds the current state + append-only transition history for a lesson."""

    state: WorkflowState = WorkflowState.DRAFT
    history: list[TransitionRecord] = field(default_factory=list)


def next_state(state: WorkflowState, action: ReviewAction) -> WorkflowState:
    """Pure transition function. Raises WorkflowError on an illegal transition."""
    if action is ReviewAction.SUBMIT and state is WorkflowState.DRAFT:
        return REVIEW_CHAIN[0]
    if action is ReviewAction.REQUEST_CHANGES and state in REVIEW_CHAIN:
        return WorkflowState.DRAFT
    if action is ReviewAction.APPROVE and state in REVIEW_CHAIN:
        idx = REVIEW_CHAIN.index(state)
        if idx + 1 < len(REVIEW_CHAIN):
            return REVIEW_CHAIN[idx + 1]
        return WorkflowState.APPROVED
    if action is ReviewAction.PUBLISH and state is WorkflowState.APPROVED:
        return WorkflowState.PUBLISHED
    if action is ReviewAction.ROLLBACK and state in (
        WorkflowState.APPROVED,
        WorkflowState.PUBLISHED,
    ):
        return WorkflowState.PUBLISHED
    if action is ReviewAction.ARCHIVE and state is WorkflowState.PUBLISHED:
        return WorkflowState.ARCHIVED
    raise WorkflowError(f"illegal transition: {action.value} from {state.value}")
