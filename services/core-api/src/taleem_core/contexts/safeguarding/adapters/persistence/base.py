"""SQLAlchemy foundations for the safeguarding schema (alembic 0012_safeguarding).

Its own declarative base and its own ``safeguarding`` schema: concern records are the most sensitive
data class (C4, doc 14 §4), so they sit apart from learning and identity data. The schema is
translated away on SQLite so the suite runs without a database server. The engine shares another
context's pool — the schema, not the pool, is the boundary.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

SAFEGUARDING_SCHEMA = "safeguarding"

JsonType = JSON().with_variant(JSONB(), "postgresql")


class SafeguardingBase(DeclarativeBase):
    """Declarative base for every safeguarding-context ORM model."""


def safeguarding_engine_sharing(engine: Engine) -> Engine:
    """Reuse ``engine`` (and its pool) for the safeguarding schema; translate it away on SQLite."""
    if engine.dialect.name != "sqlite":
        return engine
    existing = dict(engine.get_execution_options().get("schema_translate_map") or {})
    return engine.execution_options(schema_translate_map={**existing, SAFEGUARDING_SCHEMA: None})


def create_safeguarding_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
