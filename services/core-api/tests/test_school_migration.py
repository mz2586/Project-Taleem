"""0008_school migration: reversible, and the ORM matches it (PostgreSQL-gated).

The suite builds the school tables from the ORM on SQLite; production uses the hand-authored
migration. This guard applies the migrations, reflects the real ``school`` schema, and asserts every
ORM table's columns match; it also proves ``downgrade`` removes the schema and a re-upgrade restores
it (up / down / up).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

import taleem_core.contexts.school.adapters.persistence.models  # noqa: F401
from taleem_core.contexts.school.adapters.persistence.base import SCHOOL_SCHEMA, SchoolBase

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")


def _cfg() -> object:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


def _school_tables() -> set[str]:
    engine = create_engine(PG_URL or "")
    try:
        inspector = inspect(engine)
        if SCHOOL_SCHEMA not in inspector.get_schema_names():
            return set()
        return set(inspector.get_table_names(schema=SCHOOL_SCHEMA))
    finally:
        engine.dispose()


def test_revision_chain_is_a_single_down_revision() -> None:
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0008_school.py"
    spec = importlib.util.spec_from_file_location("m0008", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0008_school"
    assert module.down_revision == "0007_ai_usage"  # a single, linear parent


@_pg_only
def test_up_down_up_and_orm_parity() -> None:
    from alembic import command

    cfg = _cfg()
    command.upgrade(cfg, "head")
    expected = {t.name for t in SchoolBase.metadata.tables.values()}
    assert _school_tables() == expected

    command.downgrade(cfg, "-1")  # 0008 is head: drop just the school schema
    assert _school_tables() == set()

    command.upgrade(cfg, "head")
    engine = create_engine(PG_URL or "")
    inspector = inspect(engine)
    drift: list[str] = []
    for table in SchoolBase.metadata.tables.values():
        orm_cols = {c.name for c in table.columns}
        db_cols = {c["name"] for c in inspector.get_columns(table.name, schema=table.schema)}
        if orm_cols != db_cols:
            drift.append(
                f"{table.schema}.{table.name}: orm={sorted(orm_cols)} db={sorted(db_cols)}"
            )
    engine.dispose()
    assert not drift, "ORM/migration drift:\n" + "\n".join(drift)
