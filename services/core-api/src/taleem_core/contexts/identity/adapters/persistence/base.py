"""SQLAlchemy foundations for the identity-context persistence adapter.

Mirrors the ops / learning / curriculum bases: its own declarative base (contexts share no ORM
metadata — a DDD boundary), a portable JSON column that becomes JSONB on PostgreSQL, and an explicit
schema binding that is translated away on SQLite so the suite runs with no database server.
"""

from __future__ import annotations

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

IDENTITY_SCHEMA = "identity"

JsonType = JSON().with_variant(JSONB(), "postgresql")


class IdentityBase(DeclarativeBase):
    """Declarative base for all identity-context ORM models."""


def _is_memory_sqlite(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or url.endswith(":memory:")


def create_identity_engine(url: str, *, echo: bool = False) -> Engine:
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
        engine = engine.execution_options(schema_translate_map={IDENTITY_SCHEMA: None})
    return engine


def create_identity_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
