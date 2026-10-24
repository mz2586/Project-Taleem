"""0016_account_cohort: a single linear parent, reversible (up/down/up), columns that match the
ORM (NOT NULL, default ''), and existing accounts read back as the real cohort.

The PostgreSQL-gated tests apply the migrations, prove ``downgrade`` to 0015 drops the three columns
and a re-upgrade restores them, that a guardian written before the upgrade reads back ``''``, and
that the CHECK constraint refuses an unknown cohort.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from taleem_core.contexts.identity.adapters.persistence.models import GuardianRow, LearnerRow
from taleem_core.contexts.school.adapters.persistence.models import TeacherRow
from taleem_core.platform.cohort import COHORTS

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_BASE = Path(__file__).resolve().parents[1]


def _cfg() -> object:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0016_account_cohort.py"
    spec = importlib.util.spec_from_file_location("m0016", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0016_follows_the_evidence_lesson_version_migration() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0016_account_cohort",
        "0015_evidence_lesson_version",
    )
    assert len(module.revision) <= 32  # type: ignore[attr-defined]  # alembic_version varchar(32)


def test_the_migration_matches_the_orm_and_the_domain() -> None:
    module = _module()
    assert module.COHORTS == COHORTS  # type: ignore[attr-defined]
    for row in (GuardianRow, LearnerRow, TeacherRow):
        column = row.__table__.c["cohort"]  # type: ignore[attr-defined]
        assert not column.nullable and column.type.length == 16
        assert column.server_default is not None
    tables = {
        f"{t.schema}.{t.name}"
        for t in (GuardianRow.__table__, LearnerRow.__table__, TeacherRow.__table__)
    }
    assert set(module.TABLES) == tables  # type: ignore[attr-defined]
    up = " ".join(module.UPGRADE_STATEMENTS)  # type: ignore[attr-defined]
    down = " ".join(module.DOWNGRADE_STATEMENTS)  # type: ignore[attr-defined]
    for table in tables:
        assert f"ALTER TABLE {table} ADD COLUMN cohort varchar(16) NOT NULL DEFAULT ''" in up
        assert f"ALTER TABLE {table} DROP COLUMN IF EXISTS cohort" in down


def _columns(table: str, schema: str) -> set[str]:
    engine = create_engine(PG_URL or "")
    try:
        return {c["name"] for c in inspect(engine).get_columns(table, schema=schema)}
    finally:
        engine.dispose()


@_pg_only
def test_up_down_up() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    assert "cohort" in _columns("guardian_account", "identity")
    command.downgrade(_cfg(), "0015_evidence_lesson_version")
    for table, schema in (
        ("guardian_account", "identity"),
        ("learner_account", "identity"),
        ("teacher_account", "school"),
    ):
        assert "cohort" not in _columns(table, schema)
    command.upgrade(_cfg(), "head")
    assert "cohort" in _columns("teacher_account", "school")


@_pg_only
def test_existing_accounts_become_real_and_unknown_cohorts_are_refused() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    command.downgrade(_cfg(), "0015_evidence_lesson_version")
    ref = f"gdn_mig_{uuid.uuid4().hex[:12]}"
    engine = create_engine(PG_URL or "")
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO identity.guardian_account (guardian_ref, email, passphrase_hash, "
                    "display_name, family_code, locale, status, failed_attempts, created_at, "
                    "version) VALUES (:r, :e, 'x', 'P', :c, 'ur', 'active', 0, 0, 1)"
                ),
                {"r": ref, "e": f"{ref}@example.org", "c": uuid.uuid4().hex[:9].upper()},
            )
        command.upgrade(_cfg(), "head")
        with engine.begin() as conn:
            cohort = conn.execute(
                text("SELECT cohort FROM identity.guardian_account WHERE guardian_ref = :r"),
                {"r": ref},
            ).scalar_one()
            assert cohort == ""
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE identity.guardian_account SET cohort = 'staff' WHERE guardian_ref = :r"
                ),
                {"r": ref},
            )
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM identity.guardian_account WHERE guardian_ref = :r"), {"r": ref}
            )
    finally:
        engine.dispose()
