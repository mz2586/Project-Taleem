"""0014_reporting: a single linear parent, reversible (up/down/up), a rollback never destroys an
issued report card, and an issued card is immutable in the database itself.

The PostgreSQL-gated tests apply the migrations, prove ``downgrade`` to 0013 removes the
``reporting`` schema and a re-upgrade restores it, that ``downgrade`` **refuses** while any report
card exists, and that the trigger refuses an edit of a card but admits its one acknowledgement.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from taleem_core.contexts.reporting.adapters.persistence.base import ReportingBase
from taleem_core.contexts.reporting.domain.report_card import AUDIT_ACTIONS, AUDIT_ROLES

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_BASE = Path(__file__).resolve().parents[1]
_HASH = "0" * 64


def _cfg() -> object:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0014_reporting.py"
    spec = importlib.util.spec_from_file_location("m0014", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0014_follows_the_homework_migration() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0014_reporting",
        "0013_homework",
    )


def test_the_migration_lists_match_the_domain_and_the_orm() -> None:
    module = _module()
    assert module.AUDIT_ACTIONS == AUDIT_ACTIONS  # type: ignore[attr-defined]
    assert module.AUDIT_ROLES == AUDIT_ROLES  # type: ignore[attr-defined]
    created = " ".join(module.UPGRADE_STATEMENTS)  # type: ignore[attr-defined]
    for table in ReportingBase.metadata.sorted_tables:
        assert f"CREATE TABLE {table.schema}.{table.name} " in created
        for column in table.columns:
            assert f" {column.name} " in created, (table.name, column.name)


def _tables() -> set[str]:
    engine = create_engine(PG_URL or "")
    try:
        return set(inspect(engine).get_table_names(schema="reporting"))
    finally:
        engine.dispose()


@_pg_only
def test_up_down_up() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    assert {"report_card", "report_card_audit", "report_card_outbox"} <= _tables()
    command.downgrade(_cfg(), "0013_homework")
    assert _tables() == set()
    command.upgrade(_cfg(), "head")
    assert "report_card" in _tables()


@_pg_only
def test_downgrade_refuses_while_a_card_exists_and_cards_are_immutable() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    engine = create_engine(PG_URL or "")
    card_id = f"rpc_{uuid.uuid4().hex}"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO reporting.report_card (card_id, student_ref, organization_id, "
                    "class_id, period_start, period_end, body, content_hash, issued_by, "
                    "issued_at) VALUES (:id, 'stu_x', '', '', 1, 2, '{}', :h, 'system', 3)"
                ),
                {"id": card_id, "h": _HASH},
            )
        with pytest.raises(RuntimeError, match="issued report card"):
            command.downgrade(_cfg(), "0013_homework")
        with engine.connect() as conn:  # the card survived the refused rollback
            kept = conn.execute(
                text("SELECT count(*) FROM reporting.report_card WHERE card_id = :id"),
                {"id": card_id},
            ).scalar()
        assert kept == 1

        with pytest.raises(DBAPIError, match="immutable"), engine.begin() as conn:
            conn.execute(
                # The JSON goes in as a bind value: a literal ``:1`` would be parsed as a parameter.
                text("UPDATE reporting.report_card SET body = :body WHERE card_id = :id"),
                {"id": card_id, "body": '{"x": 1}'},
            )
        with engine.begin() as conn:  # the one acknowledgement is admitted…
            conn.execute(
                text(
                    "UPDATE reporting.report_card SET acknowledged_at = 9, acknowledged_by = 'g' "
                    "WHERE card_id = :id"
                ),
                {"id": card_id},
            )
        with pytest.raises(DBAPIError, match="acknowledged once"), engine.begin() as conn:
            conn.execute(  # …and never changed afterwards
                text("UPDATE reporting.report_card SET acknowledged_at = 10 WHERE card_id = :id"),
                {"id": card_id},
            )
        with pytest.raises(DBAPIError), engine.begin() as conn:  # one system card per period
            conn.execute(
                text(
                    "INSERT INTO reporting.report_card (card_id, student_ref, organization_id, "
                    "class_id, period_start, period_end, body, content_hash, issued_by, "
                    "issued_at) VALUES (:id, 'stu_x', '', '', 1, 2, '{}', :h, 'system', 4)"
                ),
                {"id": f"rpc_{uuid.uuid4().hex}", "h": _HASH},
            )
    finally:
        with engine.begin() as conn:  # an erasure-style DELETE is allowed
            conn.execute(
                text("DELETE FROM reporting.report_card WHERE card_id = :id"), {"id": card_id}
            )
        engine.dispose()
        command.upgrade(_cfg(), "head")
