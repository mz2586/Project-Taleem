"""Learning-context persistence adapter (SQLAlchemy 2.x).

Durable storage for the durable learning data — the Student Knowledge Model (mastery, immutable
assessment evidence, misconceptions) and the transactional event outbox — sharded/keyed by
``student_ref`` per LEARNING_DOMAIN_MODEL §9. Schema-per-context (`learning`), no cross-context FK.
"""

from __future__ import annotations

from .base import LEARNING_SCHEMA, LearningBase
from .repository import SqlAlchemyStudentKnowledgeRepository
from .uow import LearningUnitOfWork

__all__ = [
    "LEARNING_SCHEMA",
    "LearningBase",
    "LearningUnitOfWork",
    "SqlAlchemyStudentKnowledgeRepository",
]
