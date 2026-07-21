"""Persistence-layer tests for Curriculum Studio (SQLAlchemy repository + Unit of Work).

Portable tests run against in-memory SQLite (``Base.metadata.create_all``) so CI needs no database.
The PostgreSQL-specific guarantees (the Alembic migration's reversibility and the FTS trigger) are
covered by tests gated on ``CS_DATABASE_URL`` — they run in the environments that set it and skip
elsewhere. See docs/10-curriculum-studio/persistence/.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    Base,
    UnitOfWork,
    create_db_engine,
    create_session_factory,
    unit_of_work,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence.models import (
    AuditLogRow,
    LessonRow,
    LessonVersionRow,
    OutboxRow,
    WorkflowTransitionRow,
)
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction

from .studio_helpers import make_valid_lesson

T = TypeVar("T")

REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _clock() -> float:
    return 1000.0


@pytest.fixture
def factory() -> sessionmaker[Session]:
    """In-memory SQLite with the schema created from the ORM metadata."""
    engine = create_db_engine("sqlite://")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def _op[T](factory: sessionmaker[Session], fn: Callable[[CurriculumStudioService], T]) -> T:
    with unit_of_work(factory) as uow:
        service = CurriculumStudioService(uow.lessons, uow.publish, clock=_clock)
        result = fn(service)
        uow.commit()
        return result


def _publish(factory: sessionmaker[Session], lesson_id: str = "L1") -> None:
    _op(factory, lambda s: s.create(make_valid_lesson(lesson_id)))
    _op(factory, lambda s: s.submit(lesson_id, "subject_author"))
    for role in REVIEW_ROLES:
        _op(factory, lambda s, role=role: s.review(lesson_id, ReviewAction.APPROVE, role))
    _op(factory, lambda s: s.publish(lesson_id, "curriculum_architect", "v1"))


def test_roundtrip_preserves_the_whole_aggregate(factory: sessionmaker[Session]) -> None:
    original = make_valid_lesson("L-rt")
    _op(factory, lambda s: s.create(original))
    with unit_of_work(factory) as uow:
        loaded = uow.lessons.get("L-rt")
    assert loaded is not None
    assert loaded == original  # dataclass structural equality across the full graph


def test_body_excludes_bookkeeping(factory: sessionmaker[Session]) -> None:
    _op(factory, lambda s: s.create(make_valid_lesson("L-body")))
    with unit_of_work(factory) as uow:
        row = uow.session.execute(
            select(LessonRow).where(LessonRow.lesson_key == "L-body")
        ).scalar_one()
        for key in ("workflow", "quality_gate_results", "version", "version_history"):
            assert key not in row.body


def test_full_lifecycle_persists_version_gates_and_event(factory: sessionmaker[Session]) -> None:
    _publish(factory)
    with unit_of_work(factory) as uow:
        lesson = uow.lessons.get("L1")
        assert lesson is not None
        assert lesson.workflow.state.value == "published"
        assert lesson.version == 1
        assert len(lesson.version_history.versions) == 1
        assert len(lesson.quality_gate_results) == 9
        assert all(r.passed for r in lesson.quality_gate_results)

        session = uow.session
        assert session.execute(select(func.count()).select_from(LessonVersionRow)).scalar() == 1
        # submit + 5 approvals + publish == 7 transitions
        assert (
            session.execute(select(func.count()).select_from(WorkflowTransitionRow)).scalar() == 7
        )
        events = session.execute(select(OutboxRow)).scalars().all()
        assert len(events) == 1
        assert events[0].event_type == "LessonPublished"
        assert events[0].payload["version_no"] == 1
        assert events[0].payload["content_hash"].startswith("sha256:")


def test_rollback_records_forward_transition(factory: sessionmaker[Session]) -> None:
    _publish(factory)
    _op(factory, lambda s: s.rollback("L1", 1, "curriculum_architect"))
    with unit_of_work(factory) as uow:
        lesson = uow.lessons.get("L1")
        assert lesson is not None
        actions = [t.action.value for t in lesson.workflow.history]
        assert actions[-1] == "rollback"  # history is append-only; rollback moves forward


def test_audit_log_is_hash_chained(factory: sessionmaker[Session]) -> None:
    _op(factory, lambda s: s.create(make_valid_lesson("L-audit")))
    _op(factory, lambda s: s.submit("L-audit", "subject_author"))
    with unit_of_work(factory) as uow:
        rows = (
            uow.session.execute(
                select(AuditLogRow)
                .where(AuditLogRow.entity_type == "lesson")
                .order_by(AuditLogRow.at)
            )
            .scalars()
            .all()
        )
    assert len(rows) >= 2
    assert rows[0].prev_hash == ""
    for prev, curr in zip(rows, rows[1:], strict=False):
        assert curr.prev_hash == prev.row_hash  # unbroken chain
        assert curr.row_hash.startswith("sha256:")


def test_optimistic_lock_rejects_stale_write(tmp_path: Path) -> None:
    # Two independent sessions (file-backed SQLite gives true connection isolation).
    engine = create_db_engine(f"sqlite:///{tmp_path/'lock.db'}")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    _op(factory, lambda s: s.create(make_valid_lesson("L-lock")))

    session_a = factory()
    session_b = factory()
    try:
        row_a = session_a.execute(
            select(LessonRow).where(LessonRow.lesson_key == "L-lock")
        ).scalar_one()
        row_b = session_b.execute(
            select(LessonRow).where(LessonRow.lesson_key == "L-lock")
        ).scalar_one()

        row_a.subject_key = "science"
        session_a.commit()  # bumps lock_version 1 -> 2

        row_b.subject_key = "english"
        with pytest.raises(StaleDataError):
            session_b.commit()  # WHERE lock_version = 1 matches no rows
    finally:
        session_a.close()
        session_b.close()


def test_schema_holds_no_child_pii() -> None:
    # Security invariant (architecture §16, review condition 6): this context never stores
    # student-linked data. No column may reference a student/child/learner identity.
    forbidden = ("student", "child", "learner", "pupil", "guardian", "parent_id")
    for table in Base.metadata.tables.values():
        for column in table.columns:
            name = column.name.lower()
            assert not any(token in name for token in forbidden), f"{table.name}.{column.name}"


# --------------------------------------------------------------- PostgreSQL-gated tests

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")


def _alembic_config() -> object:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


@_pg_only
def test_migration_is_reversible() -> None:
    from alembic import command
    from sqlalchemy import create_engine, inspect

    cfg = _alembic_config()
    engine = create_engine(PG_URL or "")
    command.downgrade(cfg, "base")  # clean slate
    command.upgrade(cfg, "head")
    assert "curriculum_studio" in inspect(engine).get_schema_names()
    command.downgrade(cfg, "base")
    assert "curriculum_studio" not in inspect(engine).get_schema_names()
    command.upgrade(cfg, "head")  # re-apply for the FTS test / a usable end state
    engine.dispose()


@_pg_only
def test_fts_finds_lesson_by_title() -> None:
    # Guards design-review finding F1: the search-vector trigger must index the title path.
    from sqlalchemy import text

    engine = create_db_engine(PG_URL or "")
    factory = create_session_factory(engine)
    lesson_id = "L-fts"
    _op(factory, lambda s: s.create(make_valid_lesson(lesson_id)))
    with unit_of_work(factory) as uow:
        hit = uow.session.execute(
            text(
                "SELECT count(*) FROM curriculum_studio.lesson "
                "WHERE search_vector @@ plainto_tsquery('simple', 'counting')"
            )
        ).scalar()
    assert hit == 1
    engine.dispose()


# UnitOfWork type is referenced to keep the import meaningful under linting.
assert UnitOfWork is not None
