"""0015_evidence_lesson_version: a single linear parent, reversible (up/down/up), nullable columns
that match the ORM, and existing evidence rows stay NULL (nothing is backfilled or guessed).

The PostgreSQL-gated tests apply the migrations, prove ``downgrade`` to 0014 drops the two columns
and a re-upgrade restores them, and that a row written before the upgrade reads back NULL.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

from taleem_core.contexts.learning.adapters.persistence.models import AssessmentEvidenceRow

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_BASE = Path(__file__).resolve().parents[1]


def _cfg() -> object:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0015_evidence_lesson_version.py"
    spec = importlib.util.spec_from_file_location("m0015", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0015_follows_the_reporting_migration() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0015_evidence_lesson_version",
        "0014_reporting",
    )
    # alembic_version.version_num is varchar(32)
    assert len(module.revision) <= 32  # type: ignore[attr-defined]


def test_the_migration_adds_exactly_the_orm_columns_as_nullable() -> None:
    module = _module()
    table = AssessmentEvidenceRow.__table__
    for name in module.COLUMNS:  # type: ignore[attr-defined]
        assert table.c[name].nullable, name
    up = " ".join(module.UPGRADE_STATEMENTS)  # type: ignore[attr-defined]
    down = " ".join(module.DOWNGRADE_STATEMENTS)  # type: ignore[attr-defined]
    for name in module.COLUMNS:  # type: ignore[attr-defined]
        assert f"ADD COLUMN {name} " in up and f"DROP COLUMN IF EXISTS {name}" in down
    assert "NOT NULL" not in up and "UPDATE" not in up and "DEFAULT" not in up


def _columns() -> set[str]:
    engine = create_engine(PG_URL or "")
    try:
        return {c["name"] for c in inspect(engine).get_columns("assessment_evidence", "learning")}
    finally:
        engine.dispose()


@_pg_only
def test_up_down_up() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    assert {"lesson_id", "lesson_version"} <= _columns()
    command.downgrade(_cfg(), "0014_reporting")
    assert not {"lesson_id", "lesson_version"} & _columns()
    command.upgrade(_cfg(), "head")
    assert {"lesson_id", "lesson_version"} <= _columns()


@_pg_only
def test_existing_rows_stay_null_after_the_upgrade() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    command.downgrade(_cfg(), "0014_reporting")
    engine = create_engine(PG_URL or "")
    evidence_id = f"ev-{uuid.uuid4().hex}"
    try:
        with engine.begin() as conn:  # an evidence row written before 0015
            conn.execute(
                text(
                    "INSERT INTO learning.assessment_evidence (id, student_ref, objective_code, "
                    "item_ref, session_id, outcome, context, mastery_before, mastery_after, "
                    "occurred_at) VALUES (:id, 'stu_x', 'OBJ', 'i1', '', 'correct', 'practice', "
                    "0.1, 0.2, 1)"
                ),
                {"id": evidence_id},
            )
        command.upgrade(_cfg(), "head")
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT lesson_id, lesson_version FROM learning.assessment_evidence "
                    "WHERE id = :id"
                ),
                {"id": evidence_id},
            ).one()
        assert tuple(row) == (None, None)
    finally:
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:  # the erasure-style DELETE the trigger admits
            conn.execute(text("SET LOCAL taleem.privacy_erasure = 'on'"))
            conn.execute(
                text("DELETE FROM learning.assessment_evidence WHERE id = :id"),
                {"id": evidence_id},
            )
        engine.dispose()
