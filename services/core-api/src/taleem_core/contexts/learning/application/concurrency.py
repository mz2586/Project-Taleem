"""Optimistic-concurrency control for the learning write path.

The primitives now live in ``platform.concurrency`` (shared with Curriculum Studio, which has the
same ``version_id_col`` optimistic locking). This module re-exports them so existing learning
imports and the retry wiring in ``KnowledgeService`` / ``LearningUnitOfWork`` keep working as-is.
"""

from __future__ import annotations

from ....platform.concurrency import (
    MAX_CONFLICT_RETRIES,
    ConcurrencyConflictError,
    retry_on_conflict,
)

__all__ = ["MAX_CONFLICT_RETRIES", "ConcurrencyConflictError", "retry_on_conflict"]
