"""0013_homework: a single linear parent, reversible (up/down/up), and a rollback never deletes
safeguarding records.

The PostgreSQL-gated tests apply the migrations, prove ``downgrade`` to 0012 removes
``school.submission`` and a re-upgrade restores it, and that ``downgrade`` **refuses** while a
teacher-raised concern exists (the restored two-role CHECK could not hold it).
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_BASE = Path(__file__).resolve().parents[1]


def _cfg() -> object:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0013_homework.py"
    spec = importlib.util.spec_from_file_location("m0013", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0013_follows_the_safeguarding_migration() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0013_homework",
        "0012_safeguarding",
    )


def test_the_migration_lists_match_the_domain() -> None:
    module = _module()
    assert module.MARK_OUTCOMES == ("met", "not_yet")  # type: ignore[attr-defined]
    assert "teacher" in module.RAISER_ROLES  # type: ignore[attr-defined]
    assert "teacher" not in module.PREVIOUS_RAISER_ROLES  # type: ignore[attr-defined]


def _has_submission_table() -> bool:
    engine = create_engine(PG_URL or "")
    try:
        return "submission" in inspect(engine).get_table_names(schema="school")
    finally:
        engine.dispose()


@_pg_only
def test_up_down_up() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    assert _has_submission_table()
    command.downgrade(_cfg(), "0012_safeguarding")
    assert not _has_submission_table()
    command.upgrade(_cfg(), "head")
    assert _has_submission_table()


@_pg_only
def test_downgrade_refuses_while_teacher_raised_concerns_exist() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    engine = create_engine(PG_URL or "")
    concern_id = f"sgc_{uuid.uuid4().hex}"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO safeguarding.concern (concern_id, subject_ref, raised_by_ref, "
                    "raised_by_role, category, priority, status, outcome, created_at, free_text) "
                    "VALUES (:id, 'stu_x', 'tch_x', 'teacher', 'other', 'T3', 'open', NULL, 1, "
                    "NULL)"
                ),
                {"id": concern_id},
            )
        with pytest.raises(RuntimeError, match="teacher-raised safeguarding"):
            command.downgrade(_cfg(), "0012_safeguarding")
        with engine.connect() as conn:  # the record survived the refused rollback
            kept = conn.execute(
                text("SELECT count(*) FROM safeguarding.concern WHERE concern_id = :id"),
                {"id": concern_id},
            ).scalar()
        assert kept == 1
        assert _has_submission_table()
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM safeguarding.concern WHERE concern_id = :id"), {"id": concern_id}
            )
        engine.dispose()
        command.upgrade(_cfg(), "head")
