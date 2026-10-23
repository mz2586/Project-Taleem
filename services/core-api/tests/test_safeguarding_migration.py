"""0012_safeguarding: a single linear parent, reversible (up/down/up), and the ORM matches it.

The suite builds the safeguarding tables from the ORM on SQLite; production uses the hand-authored
migration. The PostgreSQL-gated test applies the migrations, reflects the ``safeguarding`` schema,
asserts every ORM table's columns match, proves ``downgrade`` removes only 0012 (school audit from
0011 survives) and restores the seven-role staff CHECK, and that a re-upgrade restores both.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

import taleem_core.contexts.safeguarding.adapters.persistence.models  # noqa: F401
from taleem_core.contexts.safeguarding.adapters.persistence.base import (
    SAFEGUARDING_SCHEMA,
    SafeguardingBase,
)

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _cfg() -> object:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


def _module() -> object:
    spec = importlib.util.spec_from_file_location("m0012", _VERSIONS / "0012_safeguarding.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tables(schema: str) -> set[str]:
    engine = create_engine(PG_URL or "")
    try:
        inspector = inspect(engine)
        if schema not in inspector.get_schema_names():
            return set()
        return set(inspector.get_table_names(schema=schema))
    finally:
        engine.dispose()


def _insert_lead(engine: object) -> None:
    with engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                "INSERT INTO identity.staff_account "
                "(staff_ref, email, passphrase_hash, display_name, role) "
                "VALUES (:ref, :email, 'x', 'X', 'safeguarding_lead')"
            ),
            {"ref": f"stf_{uuid.uuid4().hex}", "email": f"{uuid.uuid4().hex}@example.com"},
        )


def test_0012_follows_the_school_audit_migration() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0012_safeguarding",
        "0011_school_audit",
    )


def test_the_migration_lists_match_the_domain_lists() -> None:
    from taleem_core.auth import pdp
    from taleem_core.contexts.safeguarding.domain.model import (
        Category,
        Outcome,
        Priority,
        Status,
    )

    module = _module()
    assert set(module.CATEGORIES) == {c.value for c in Category}  # type: ignore[attr-defined]
    assert set(module.PRIORITIES) == {p.value for p in Priority}  # type: ignore[attr-defined]
    assert set(module.STATUSES) == {s.value for s in Status}  # type: ignore[attr-defined]
    assert set(module.OUTCOMES) == {o.value for o in Outcome}  # type: ignore[attr-defined]
    assert set(module.STAFF_ROLES) == set(pdp.STAFF_ACCOUNT_ROLES)  # type: ignore[attr-defined]


@_pg_only
def test_0012_up_down_up_and_orm_parity() -> None:
    from alembic import command

    cfg = _cfg()
    command.upgrade(cfg, "head")
    expected = {t.name for t in SafeguardingBase.metadata.tables.values()}
    assert _tables(SAFEGUARDING_SCHEMA) == expected

    engine = create_engine(PG_URL or "")
    try:
        inspector = inspect(engine)
        drift = []
        for table in SafeguardingBase.metadata.tables.values():
            orm_cols = {c.name for c in table.columns}
            db_cols = {c["name"] for c in inspector.get_columns(table.name, schema=table.schema)}
            if orm_cols != db_cols:
                drift.append(f"{table.fullname}: orm={sorted(orm_cols)} db={sorted(db_cols)}")
        assert not drift, "ORM/migration drift:\n" + "\n".join(drift)

        _insert_lead(engine)  # downgrade must cope with a lead account existing
        command.downgrade(cfg, "0011_school_audit")
        assert _tables(SAFEGUARDING_SCHEMA) == set()
        assert "enrolment_audit" in _tables("school")  # only 0012 was reverted
        with pytest.raises(IntegrityError):
            _insert_lead(engine)  # the seven-role CHECK is back

        command.upgrade(cfg, "head")
        assert _tables(SAFEGUARDING_SCHEMA) == expected
        _insert_lead(engine)
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM identity.staff_account WHERE display_name = 'X'"))
        engine.dispose()
        command.upgrade(cfg, "head")
