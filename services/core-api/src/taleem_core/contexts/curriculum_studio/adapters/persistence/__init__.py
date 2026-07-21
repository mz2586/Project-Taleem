"""Curriculum Studio persistence adapter (SQLAlchemy 2.x + Alembic).

Infrastructure layer. The application talks to it only through the ``LessonRepository`` /
``PublishPort`` ports; the domain never imports it. See DATABASE_ARCHITECTURE.md and the sibling
design docs under ``docs/10-curriculum-studio/persistence/``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from .base import (
    SCHEMA,
    Base,
    create_db_engine,
    create_session_factory,
    session_scope,
)
from .repository import SqlAlchemyLessonRepository, SqlAlchemyPublishPort
from .uow import UnitOfWork


def unit_of_work(session_factory: sessionmaker[Session]) -> UnitOfWork:
    """Open a Unit of Work (transaction scope) on the given session factory."""
    return UnitOfWork(session_factory)


__all__ = [
    "SCHEMA",
    "Base",
    "SqlAlchemyLessonRepository",
    "SqlAlchemyPublishPort",
    "UnitOfWork",
    "create_db_engine",
    "create_session_factory",
    "session_scope",
    "unit_of_work",
]
