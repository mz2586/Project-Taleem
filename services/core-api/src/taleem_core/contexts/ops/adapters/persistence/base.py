"""SQLAlchemy foundations for the ops-context persistence adapter.

Mirrors the learning / curriculum_studio persistence bases (portable JSONB/JSON, explicit schema
binding translated away on SQLite). Kept independent so the contexts share no ORM base — a DDD
boundary, not duplication for its own sake.

This adapter exists so the two pieces of previously process-local state — the operator kill switch
and the offline-sync idempotency cache — can be shared across instances. On a multi-instance or
serverless runtime, process-local state made the kill switch fail *open*.
"""

from __future__ import annotations

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

OPS_SCHEMA = "ops"

JsonType = JSON().with_variant(JSONB(), "postgresql")


class OpsBase(DeclarativeBase):
    """Declarative base for all ops-context ORM models."""


def _is_memory_sqlite(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or url.endswith(":memory:")


def create_ops_engine(url: str, *, echo: bool = False) -> Engine:
    """Engine bound to the `ops` schema (translated to None on SQLite for tests)."""
    if _is_memory_sqlite(url):
        # One shared in-memory DB across threads (TestClient runs handlers in a worker thread).
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
        engine = engine.execution_options(schema_translate_map={OPS_SCHEMA: None})
    return engine


def create_ops_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
