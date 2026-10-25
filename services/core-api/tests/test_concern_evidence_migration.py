"""0018_concern_evidence: a single linear parent, ORM parity, reversible (up/down/up), the evidence
is immutable outside a privacy erasure, and a rollback never destroys a snapshot.

The PostgreSQL-gated tests apply the migrations, reflect the table against the ORM, prove
``downgrade`` to 0017 drops it and a re-upgrade restores it, that UPDATE, DELETE and TRUNCATE are
refused without the erasure flag (and UPDATE/DELETE admitted with it), and that ``downgrade``
refuses while a snapshot exists.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from taleem_core.contexts.safeguarding.adapters.persistence.models import ConcernEvidenceRow

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_BASE = Path(__file__).resolve().parents[1]
_PREVIOUS = "0017_self_paced_homework"


def _cfg() -> object:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0018_concern_evidence.py"
    spec = importlib.util.spec_from_file_location("m0018", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0018_follows_the_self_paced_homework_migration() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0018_concern_evidence",
        _PREVIOUS,
    )
    assert len(module.revision) <= 32  # type: ignore[attr-defined]


def test_the_migration_names_every_orm_column_and_the_erasure_flag() -> None:
    module = _module()
    ddl = module.UPGRADE_STATEMENTS[0]  # type: ignore[attr-defined]
    for column in ConcernEvidenceRow.__table__.columns:
        assert f"\n        {column.name} " in ddl, column.name
    assert module.ERASURE_GUC == "taleem.privacy_erasure"  # type: ignore[attr-defined]
    assert "ON DELETE CASCADE" not in ddl  # no cascade can remove evidence silently


def _has_table() -> bool:
    engine = create_engine(PG_URL or "")
    try:
        return "concern_evidence" in inspect(engine).get_table_names(schema="safeguarding")
    finally:
        engine.dispose()


@pytest.fixture
def pg() -> Iterator[Engine]:
    from alembic import command

    command.upgrade(_cfg(), "head")
    engine = create_engine(PG_URL or "")
    try:
        yield engine
    finally:
        engine.dispose()


def _seed(engine: Engine) -> str:
    concern_id = f"sgc_{uuid.uuid4().hex}"
    words = "probe words"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO safeguarding.concern (concern_id, subject_ref, raised_by_ref, "
                "raised_by_role, category, priority, status, outcome, created_at, free_text, "
                "context_submission_id) VALUES (:id, 'stu_x', 'disclosure_screen', 'system', "
                "'other', 'T3', 'open', NULL, 1, NULL, :sub)"
            ),
            {"id": concern_id, "sub": f"sub_{uuid.uuid4().hex[:20]}"},
        )
        conn.execute(
            text(
                "INSERT INTO safeguarding.concern_evidence (concern_id, submission_id, text, "
                "attempt, submitted_at, item_ref, objective_code, text_sha256, created_at) "
                "VALUES (:id, 'sub_x', :t, 1, 1, 'hw-short', 'OBJ', :h, 2)"
            ),
            {"id": concern_id, "t": words, "h": hashlib.sha256(words.encode()).hexdigest()},
        )
    return concern_id


def _cleanup(engine: Engine, concern_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL taleem.privacy_erasure = 'on'"))
        conn.execute(
            text("DELETE FROM safeguarding.concern_evidence WHERE concern_id = :id"),
            {"id": concern_id},
        )
        conn.execute(
            text("DELETE FROM safeguarding.concern WHERE concern_id = :id"), {"id": concern_id}
        )


@_pg_only
def test_orm_parity(pg: Engine) -> None:
    reflected = {
        c["name"]: c for c in inspect(pg).get_columns("concern_evidence", schema="safeguarding")
    }
    orm = {c.name: c for c in ConcernEvidenceRow.__table__.columns}
    assert set(reflected) == set(orm)
    for name, column in orm.items():
        assert bool(reflected[name]["nullable"]) == bool(column.nullable), name


@_pg_only
def test_up_down_up(pg: Engine) -> None:
    from alembic import command

    assert _has_table()
    command.downgrade(_cfg(), _PREVIOUS)
    assert not _has_table()
    command.upgrade(_cfg(), "head")
    assert _has_table()


@_pg_only
def test_the_snapshot_is_immutable_outside_an_erasure(pg: Engine) -> None:
    concern_id = _seed(pg)
    try:
        for statement in (
            "UPDATE safeguarding.concern_evidence SET text = 'changed' WHERE concern_id = :id",
            "DELETE FROM safeguarding.concern_evidence WHERE concern_id = :id",
            "DELETE FROM safeguarding.concern WHERE concern_id = :id",  # FK: no cascade
        ):
            with (
                pytest.raises(Exception, match="append-only|foreign key|violates"),
                pg.begin() as conn,
            ):
                conn.execute(text(statement), {"id": concern_id})
        with pytest.raises(Exception, match="append-only"), pg.begin() as conn:
            conn.execute(text("TRUNCATE safeguarding.concern_evidence"))
        with pg.connect() as conn:
            kept = conn.execute(
                text("SELECT text FROM safeguarding.concern_evidence WHERE concern_id = :id"),
                {"id": concern_id},
            ).scalar()
        assert kept == "probe words"
        # The privacy erasure's flag admits an UPDATE (pseudonymisation) and a DELETE.
        with pg.begin() as conn:
            conn.execute(text("SET LOCAL taleem.privacy_erasure = 'on'"))
            conn.execute(
                text(
                    "UPDATE safeguarding.concern_evidence SET text = 'tomb words' "
                    "WHERE concern_id = :id"
                ),
                {"id": concern_id},
            )
        # The flag is transaction-local: the next transaction is protected again.
        with pytest.raises(Exception, match="append-only"), pg.begin() as conn:
            conn.execute(
                text("DELETE FROM safeguarding.concern_evidence WHERE concern_id = :id"),
                {"id": concern_id},
            )
    finally:
        _cleanup(pg, concern_id)


@_pg_only
def test_downgrade_refuses_while_a_snapshot_exists(pg: Engine) -> None:
    from alembic import command

    concern_id = _seed(pg)
    try:
        with pytest.raises(RuntimeError, match="safeguarding evidence"):
            command.downgrade(_cfg(), _PREVIOUS)
        assert _has_table()
        with pg.connect() as conn:
            kept = conn.execute(
                text("SELECT count(*) FROM safeguarding.concern_evidence WHERE concern_id = :id"),
                {"id": concern_id},
            ).scalar()
        assert kept == 1
    finally:
        _cleanup(pg, concern_id)
        command.upgrade(_cfg(), "head")
