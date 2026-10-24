"""0017_self_paced_homework: a single linear parent, ORM parity, reversible (up/down/up), and a
rollback never deletes a child's self-paced work or a system-raised safeguarding concern.

The PostgreSQL-gated tests apply the migrations, prove ``downgrade`` to 0016 drops ``source`` and
restores ``NOT NULL``, a re-upgrade restores them, the shape CHECK refuses a half-self-paced row,
and ``downgrade`` refuses while a self-paced submission or a system concern exists.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from taleem_core.contexts.safeguarding.adapters.persistence.models import ConcernRow
from taleem_core.contexts.safeguarding.domain.model import RaisedBy
from taleem_core.contexts.school.adapters.persistence.models import SubmissionRow
from taleem_core.contexts.school.domain.model import SubmissionSource

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_BASE = Path(__file__).resolve().parents[1]


def _cfg() -> object:
    from alembic.config import Config

    cfg = Config(str(_BASE / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BASE / "alembic"))
    return cfg


def _module() -> object:
    path = _BASE / "alembic" / "versions" / "0017_self_paced_homework.py"
    spec = importlib.util.spec_from_file_location("m0017", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0017_follows_the_account_cohort_migration() -> None:
    module = _module()
    assert (module.revision, module.down_revision) == (  # type: ignore[attr-defined]
        "0017_self_paced_homework",
        "0016_account_cohort",
    )
    assert len(module.revision) <= 32  # type: ignore[attr-defined]


def test_the_migration_matches_the_orm_and_the_domain() -> None:
    module = _module()
    assert tuple(s.value for s in SubmissionSource) == module.SUBMISSION_SOURCES  # type: ignore[attr-defined]
    assert tuple(r.value for r in RaisedBy) == module.RAISER_ROLES  # type: ignore[attr-defined]
    assert "system" not in module.PREVIOUS_RAISER_ROLES  # type: ignore[attr-defined]
    cols = SubmissionRow.__table__.c  # type: ignore[attr-defined]
    assert cols["assignment_id"].nullable and cols["class_id"].nullable
    assert not cols["source"].nullable and cols["source"].type.length == 16
    assert cols["source"].server_default is not None
    sub_idx = {i.name: i for i in SubmissionRow.__table__.indexes}  # type: ignore[attr-defined]
    assert sub_idx["uq_submission_self_paced"].unique
    concern_idx = {i.name: i for i in ConcernRow.__table__.indexes}  # type: ignore[attr-defined]
    assert concern_idx["uq_concern_system_submission"].unique
    up = " ".join(module.UPGRADE_STATEMENTS)  # type: ignore[attr-defined]
    down = " ".join(module.DOWNGRADE_STATEMENTS)  # type: ignore[attr-defined]
    for name in ("uq_submission_self_paced", "uq_concern_system_submission"):
        assert name in up and name in down
    assert "DROP COLUMN IF EXISTS source" in down


def _columns() -> dict[str, dict[str, object]]:
    engine = create_engine(PG_URL or "")
    try:
        return {c["name"]: c for c in inspect(engine).get_columns("submission", schema="school")}
    finally:
        engine.dispose()


@_pg_only
def test_up_down_up() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    cols = _columns()
    assert "source" in cols and cols["assignment_id"]["nullable"]
    command.downgrade(_cfg(), "0016_account_cohort")
    cols = _columns()
    assert "source" not in cols and not cols["assignment_id"]["nullable"]
    assert not cols["class_id"]["nullable"]
    command.upgrade(_cfg(), "head")
    assert "source" in _columns()


_INSERT = (
    "INSERT INTO school.submission (submission_id, organization_id, class_id, assignment_id, "
    "objective_code, item_ref, student_ref, text, status, submitted_at, created_at, source) "
    "VALUES (:id, :org, NULL, NULL, 'OBJ-1', 'hw-1', 'stu_mig', 'an answer', 'submitted', 1, 1, "
    ":source)"
)


@_pg_only
def test_the_shape_check_and_the_refused_downgrade() -> None:
    from alembic import command

    command.upgrade(_cfg(), "head")
    engine = create_engine(PG_URL or "")
    sub_id = f"sub_{uuid.uuid4().hex}"
    concern_id = f"sgc_{uuid.uuid4().hex}"
    try:
        with pytest.raises(IntegrityError), engine.begin() as conn:  # assignment without one
            conn.execute(
                text(_INSERT), {"id": f"sub_{uuid.uuid4().hex}", "org": "", "source": "assignment"}
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:  # self-paced with an org
            conn.execute(
                text(_INSERT),
                {"id": f"sub_{uuid.uuid4().hex}", "org": "org_x", "source": "self_paced"},
            )
        with engine.begin() as conn:
            conn.execute(text(_INSERT), {"id": sub_id, "org": "", "source": "self_paced"})
        with pytest.raises(IntegrityError), engine.begin() as conn:  # one row per item
            conn.execute(
                text(_INSERT), {"id": f"sub_{uuid.uuid4().hex}", "org": "", "source": "self_paced"}
            )
        with pytest.raises(RuntimeError, match="self-paced"):
            command.downgrade(_cfg(), "0016_account_cohort")
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM school.submission WHERE submission_id = :id"), {"id": sub_id}
            )
            conn.execute(
                text(
                    "INSERT INTO safeguarding.concern (concern_id, subject_ref, raised_by_ref, "
                    "raised_by_role, category, priority, status, outcome, created_at, free_text, "
                    "context_submission_id) VALUES (:id, 'stu_mig', 'disclosure_screen', "
                    "'system', 'very_sad', 'T1', 'open', NULL, 1, NULL, :sub)"
                ),
                {"id": concern_id, "sub": sub_id},
            )
        with pytest.raises(RuntimeError, match="system-raised"):
            command.downgrade(_cfg(), "0016_account_cohort")
        with engine.connect() as conn:
            kept = conn.execute(
                text("SELECT count(*) FROM safeguarding.concern WHERE concern_id = :id"),
                {"id": concern_id},
            ).scalar()
        assert kept == 1
    finally:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM safeguarding.concern WHERE concern_id = :id"), {"id": concern_id}
            )
            conn.execute(text("DELETE FROM school.submission WHERE student_ref = 'stu_mig'"))
        engine.dispose()
        command.upgrade(_cfg(), "head")
