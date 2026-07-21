"""SQLAlchemy 2.x foundations for the curriculum_studio persistence adapter.

Clean Architecture note: everything in this package is the *infrastructure* layer. The domain
(``contexts/curriculum_studio/domain``) never imports it; the application layer talks to it only
through the ``LessonRepository`` / ``PublishPort`` ports. The mapping between the pure-stdlib domain
aggregate and these ORM rows lives in ``mapper.py``.

Portability: ORM columns use portable type variants (``JSONB`` on PostgreSQL, ``JSON`` elsewhere)
so the unit-test suite can run against in-memory SQLite with ``Base.metadata.create_all`` while the
authoritative production schema is created by the Alembic migration against PostgreSQL. The schema
name is bound explicitly (``SCHEMA``) rather than via a mutable ``search_path`` (design review F9).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import JSON, Uuid, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# The bounded-context schema. On SQLite (tests) schemas are ignored; on PostgreSQL every table is
# created inside curriculum_studio (no cross-context foreign keys — doc 09).
SCHEMA = "curriculum_studio"

# Portable column types: JSONB where supported (indexable, typed), plain JSON on SQLite.
JsonType = JSON().with_variant(JSONB(), "postgresql")
# Surrogate keys: native ``uuid`` on PostgreSQL, ``CHAR(32)`` on SQLite; the app supplies canonical
# UUIDv7 strings (platform.ids.uuid7) so PK inserts stay time-ordered.
PkType = Uuid(as_uuid=False)


class Base(DeclarativeBase):
    """Declarative base for all curriculum_studio ORM models."""


def _apply_sqlite_pragmas(engine: Engine) -> None:
    """Enforce foreign keys on SQLite (off by default) so tests exercise real FK behaviour."""
    if engine.dialect.name != "sqlite":
        return
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn: object, _rec: object) -> None:  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def create_db_engine(url: str, *, echo: bool = False) -> Engine:
    """Create an Engine for the given URL (e.g. ``sqlite://`` in tests, ``postgresql+psycopg://``).

    Every ORM table is bound to the ``curriculum_studio`` schema. SQLite has no schemas, so for
    SQLite we translate that logical schema to ``None`` at execution time (``schema_translate_map``)
    — the same models then create unqualified tables in tests and schema-qualified tables on
    PostgreSQL, with no divergent model definitions.
    """
    if url in ("sqlite://", "sqlite:///:memory:") or url.endswith(":memory:"):
        # One shared in-memory DB across threads (e.g. FastAPI TestClient worker thread).
        from sqlalchemy.pool import StaticPool

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
        engine = engine.execution_options(schema_translate_map={SCHEMA: None})
    _apply_sqlite_pragmas(engine)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """A session factory bound to ``engine``. Sessions are short-lived, one per Unit of Work."""
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional session scope: commit on success, roll back on error, always close."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
