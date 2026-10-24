"""SQLAlchemy foundations for the reporting-context persistence adapter.

Its own declarative base (contexts share no ORM metadata) and the ``reporting`` schema, translated
away on SQLite so the suite runs with no database server — the same pattern as the other contexts.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

REPORTING_SCHEMA = "reporting"

JsonType = JSON().with_variant(JSONB(), "postgresql")


class ReportingBase(DeclarativeBase):
    """Declarative base for all reporting-context ORM models."""


def reporting_engine_sharing(engine: Engine) -> Engine:
    """Reuse another context's engine — and so its connection pool — for the reporting schema
    (the schema, not the pool, is the boundary). On SQLite the schema is translated away alongside
    whatever the source engine already translates."""
    if engine.dialect.name != "sqlite":
        return engine
    existing = dict(engine.get_execution_options().get("schema_translate_map") or {})
    return engine.execution_options(schema_translate_map={**existing, REPORTING_SCHEMA: None})


def create_reporting_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
