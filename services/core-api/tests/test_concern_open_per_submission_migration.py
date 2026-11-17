"""0022_concern_open_per_submission: one OPEN system concern per submission (was one ever).

Static: the revision chain and ORM parity. PostgreSQL-gated: a resolved and an open system concern
may share a submission, two open ones may not, and up/down/up is clean.
"""

from __future__ import annotations

import importlib.util
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from taleem_core.contexts.safeguarding.adapters.persistence.models import ConcernRow
from tests.test_self_paced_homework_migration import _BASE, PG_URL, _cfg, _pg_only


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0022_concern_open_per_submission.py"
    spec = importlib.util.spec_from_file_location("m0022", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0022_follows_0021_and_matches_the_orm() -> None:
    m = _module()
    assert (m.revision, m.down_revision) == (  # type: ignore[attr-defined]
        "0022_concern_open_per_submission",
        "0021_guardian_recovery_codes",
    )
    assert len(m.revision) <= 32  # type: ignore[attr-defined]
    idx = {i.name: i for i in ConcernRow.__table__.indexes}  # type: ignore[attr-defined]
    assert idx["uq_concern_system_submission_open"].unique
    assert "uq_concern_system_submission" not in idx
    up = " ".join(m.UPGRADE_STATEMENTS)  # type: ignore[attr-defined]
    assert "status <> 'resolved'" in up


_CONCERN = (
    "INSERT INTO safeguarding.concern (concern_id, subject_ref, raised_by_ref, raised_by_role, "
    "category, priority, status, outcome, created_at, free_text, context_submission_id) VALUES "
    "(:id, 'stu_m22', 'disclosure_screen', 'system', 'very_sad', 'T1', :status, :outcome, 1, "
    "NULL, :sub)"
)


@_pg_only
def test_one_open_system_concern_per_submission() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    engine = create_engine(PG_URL or "")
    sub = f"sub_{uuid.uuid4().hex}"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(_CONCERN),
                {
                    "id": f"sgc_{uuid.uuid4().hex}",
                    "status": "resolved",
                    "outcome": "duplicate",
                    "sub": sub,
                },
            )
            conn.execute(
                text(_CONCERN),
                {"id": f"sgc_{uuid.uuid4().hex}", "status": "open", "outcome": None, "sub": sub},
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text(_CONCERN),
                {"id": f"sgc_{uuid.uuid4().hex}", "status": "open", "outcome": None, "sub": sub},
            )
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM safeguarding.concern WHERE subject_ref = 'stu_m22'"))
        engine.dispose()
    command.downgrade(_cfg(), "0021_guardian_recovery_codes")
    command.upgrade(_cfg(), "head")
