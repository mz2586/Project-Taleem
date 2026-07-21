"""ORM <-> Alembic migration schema-parity guard (CTO H13).

The unit suite builds the schema from ORM ``metadata.create_all`` (SQLite); production uses the
hand-authored Alembic migrations (PostgreSQL). Nothing previously asserted the two agree, so drift
(e.g. the ``lesson.tags`` column present in the migration but absent from the ORM) went undetected.

This PostgreSQL-gated test applies the migrations, reflects the real schema, and asserts every ORM
table's columns match the migrated table's columns (modulo a small allowlist of intentionally
DB-only, trigger-maintained columns). Runs when ``CS_DATABASE_URL`` is set; skips otherwise.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

# Importing the model modules registers all tables on each MetaData.
import taleem_core.contexts.curriculum_studio.adapters.persistence.models  # noqa: F401
import taleem_core.contexts.learning.adapters.persistence.models  # noqa: F401
from taleem_core.contexts.curriculum_studio.adapters.persistence.base import Base
from taleem_core.contexts.learning.adapters.persistence.base import LearningBase

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")

# Columns intentionally created only by the migration (Postgres-only, trigger-maintained) and not
# mapped by the ORM. Any OTHER divergence is a genuine drift and must fail.
INTENTIONAL_DB_ONLY: dict[tuple[str, str], set[str]] = {
    ("curriculum_studio", "lesson"): {"search_vector"},
}


def _alembic_config() -> object:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


@_pg_only
def test_orm_matches_migration_columns() -> None:
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    engine = create_engine(PG_URL or "")
    inspector = inspect(engine)
    mismatches: list[str] = []

    for base in (Base, LearningBase):
        for table in base.metadata.tables.values():
            schema = table.schema
            name = table.name
            orm_cols = {c.name for c in table.columns}
            db_cols = {c["name"] for c in inspector.get_columns(name, schema=schema)}
            allowed_db_only = INTENTIONAL_DB_ONLY.get((schema or "", name), set())
            expected_db = orm_cols | allowed_db_only
            if db_cols != expected_db:
                missing_in_orm = db_cols - allowed_db_only - orm_cols
                missing_in_db = orm_cols - db_cols
                mismatches.append(
                    f"{schema}.{name}: orm_only={sorted(missing_in_db)} "
                    f"migration_only={sorted(missing_in_orm)}"
                )

    engine.dispose()
    assert not mismatches, "ORM/migration schema drift:\n" + "\n".join(mismatches)
