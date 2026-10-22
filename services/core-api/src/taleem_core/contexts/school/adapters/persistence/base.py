"""SQLAlchemy foundations for the school-context persistence adapter.

Its own declarative base (contexts share no ORM metadata) and the ``school`` schema, translated
away on SQLite so the suite runs with no database server — the same pattern as the other contexts.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

SCHOOL_SCHEMA = "school"


class SchoolBase(DeclarativeBase):
    """Declarative base for all school-context ORM models."""


def _is_memory_sqlite(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or url.endswith(":memory:")


def create_school_engine(url: str, *, echo: bool = False) -> Engine:
    if _is_memory_sqlite(url):
        engine = create_engine(
            url,
            echo=echo,
            future=True,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
    else:
        engine = create_engine(url, echo=echo, future=True, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(schema_translate_map={SCHOOL_SCHEMA: None})
    return engine


def school_engine_sharing(engine: Engine) -> Engine:
    """Reuse another context's engine — and therefore its connection pool — for the school schema.

    Every composed app would otherwise open one more pool against the same database; on a shared
    PostgreSQL server that is real connection pressure for no isolation benefit (the schema, not the
    pool, is the boundary). ``execution_options`` returns a view over the same pool; on SQLite the
    school schema is translated away alongside whatever the source engine already translates.
    """
    if engine.dialect.name != "sqlite":
        return engine
    existing = dict(engine.get_execution_options().get("schema_translate_map") or {})
    return engine.execution_options(schema_translate_map={**existing, SCHOOL_SCHEMA: None})


def create_school_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
