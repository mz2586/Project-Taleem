"""SQLAlchemy foundations for the learning-context persistence adapter.

Mirrors the curriculum_studio persistence base (portable JSONB/JSON, UUIDv7 string keys, explicit
schema binding via schema_translate_map on SQLite). Kept independent so the two contexts share no
ORM base — a DDD boundary, not duplication for its own sake.
"""

from __future__ import annotations

from sqlalchemy import JSON, Uuid, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

LEARNING_SCHEMA = "learning"

JsonType = JSON().with_variant(JSONB(), "postgresql")
PkType = Uuid(as_uuid=False)


class LearningBase(DeclarativeBase):
    """Declarative base for all learning-context ORM models."""


def _is_memory_sqlite(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or url.endswith(":memory:")


def create_learning_engine(url: str, *, echo: bool = False) -> Engine:
    """Engine bound to the `learning` schema (translated to None on SQLite for tests)."""
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
        engine = create_engine(url, echo=echo, future=True)
    if engine.dialect.name == "sqlite":
        engine = engine.execution_options(schema_translate_map={LEARNING_SCHEMA: None})
        _enable_sqlite_fks(engine)
    return engine


def _enable_sqlite_fks(engine: Engine) -> None:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn: object, _rec: object) -> None:  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def create_learning_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
