"""0019_unit_check_sittings: a single linear parent, ORM parity, reversible (up/down/up), and a
rollback never deletes a learner's unit-check sitting.

The PostgreSQL-gated tests apply the migrations, prove ``downgrade`` drops the table and a
re-upgrade restores it, the CHECKs and the one-open-sitting index hold, and ``downgrade`` refuses
while a sitting exists.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from taleem_core.contexts.learning.adapters.persistence.models import (
    SITTING_STATUSES,
    UnitCheckSittingRow,
)
from taleem_core.contexts.learning.domain.progression import SITTING_PREFIX, SittingStatus

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_BASE = Path(__file__).resolve().parents[1]
_PARENT = "0018_concern_evidence"


def _cfg() -> object:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0019_unit_check_sittings.py"
    spec = importlib.util.spec_from_file_location("m0019", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0019_follows_0018() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0019_unit_check_sittings",
        _PARENT,
    )
    assert len(module.revision) <= 32  # type: ignore[attr-defined]
    parent = _BASE / "alembic" / "versions" / f"{_PARENT}.py"
    assert parent.is_file()
    assert f'revision: str = "{_PARENT}"' in parent.read_text(encoding="utf-8")


def test_the_migration_matches_the_orm_and_the_domain() -> None:
    module = _module()
    assert tuple(s.value for s in SittingStatus) == module.SITTING_STATUSES  # type: ignore[attr-defined]
    assert SITTING_STATUSES == module.SITTING_STATUSES  # type: ignore[attr-defined]
    assert module.SITTING_PREFIX == SITTING_PREFIX  # type: ignore[attr-defined]
    table = UnitCheckSittingRow.__table__  # type: ignore[attr-defined]
    assert table.schema == "learning" and table.name == "unit_check_sitting"
    up = " ".join(module.UPGRADE_STATEMENTS)  # type: ignore[attr-defined]
    for column in table.columns:
        assert f" {column.name} " in up, column.name
    indexes = {i.name: i for i in table.indexes}
    assert set(indexes) == set(module.INDEXES)  # type: ignore[attr-defined]
    assert indexes["uq_sitting_in_progress"].unique
    down = " ".join(module.DOWNGRADE_STATEMENTS)  # type: ignore[attr-defined]
    for name in module.INDEXES:  # type: ignore[attr-defined]
        assert name in up and name in down
    checks = {c.name for c in table.constraints if c.name and c.name.startswith("ck_")}
    assert checks == {
        "ck_sitting_status",
        "ck_sitting_pass_percent",
        "ck_sitting_window",
        "ck_sitting_ref",
    }
    assert all(name in up for name in checks)


def _tables() -> set[str]:
    engine = create_engine(PG_URL or "")
    try:
        return set(inspect(engine).get_table_names(schema="learning"))
    finally:
        engine.dispose()


_INSERT = (
    "INSERT INTO learning.unit_check_sitting (sitting_id, student_ref, pack_id, grade_key, "
    "subject_key, unit_id, status, pass_percent, started_at, expires_at) VALUES "
    "(:id, 'stu_mig', 'PK-NCP', 'G4', 'math', 'PK-NCP/G4/math/u1', :status, 70, 1, 2)"
)


@_pg_only
def test_up_down_up() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    assert "unit_check_sitting" in _tables()
    command.downgrade(_cfg(), _PARENT)
    assert "unit_check_sitting" not in _tables()
    command.upgrade(_cfg(), "head")
    assert "unit_check_sitting" in _tables()


@_pg_only
def test_checks_the_open_sitting_index_and_the_refused_downgrade() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    engine = create_engine(PG_URL or "")
    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:  # bad status
            conn.execute(text(_INSERT), {"id": f"ucs_{uuid.uuid4().hex}", "status": "failedx"})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # bad prefix
            conn.execute(text(_INSERT), {"id": f"xyz_{uuid.uuid4().hex}", "status": "passed"})
        with engine.begin() as conn:
            conn.execute(text(_INSERT), {"id": f"ucs_{uuid.uuid4().hex}", "status": "in_progress"})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # one open sitting per unit
            conn.execute(text(_INSERT), {"id": f"ucs_{uuid.uuid4().hex}", "status": "in_progress"})
        with engine.begin() as conn:  # closed sittings are many
            conn.execute(text(_INSERT), {"id": f"ucs_{uuid.uuid4().hex}", "status": "failed"})
            conn.execute(text(_INSERT), {"id": f"ucs_{uuid.uuid4().hex}", "status": "failed"})
        with pytest.raises(RuntimeError, match="unit-check sitting"):
            command.downgrade(_cfg(), _PARENT)
        with engine.connect() as conn:
            kept = conn.execute(
                text(
                    "SELECT count(*) FROM learning.unit_check_sitting WHERE student_ref = 'stu_mig'"
                )
            ).scalar()
        assert kept == 3
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM learning.unit_check_sitting WHERE student_ref = 'stu_mig'")
            )
        engine.dispose()
        command.upgrade(_cfg(), "head")
