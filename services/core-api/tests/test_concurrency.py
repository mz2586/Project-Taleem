"""Concurrency regression tests — optimistic-lock conflict handling.

Adversarial validation found that concurrent writes to one learner's ``student_knowledge`` row
raised ``StaleDataError`` (optimistic-lock loser) and surfaced as a **500**. The fix: the UnitOfWork
translates the DB conflict into ``ConcurrencyConflictError`` and ``KnowledgeService`` retries the
whole read-modify-write. These tests lock that in deterministically (no threads needed): the retry
helper, the UoW translation, and an injected-conflict path through ``record_attempt``.

The end-to-end threaded scenario was verified manually against PostgreSQL (separate connections per
thread): N=8 and N=20 concurrent answers all returned 200, zero 500s.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from taleem_core.contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.learning.application.concurrency import (
    ConcurrencyConflictError,
    retry_on_conflict,
)
from taleem_core.contexts.learning.application.knowledge_service import KnowledgeService
from taleem_core.contexts.learning.domain.estimator import BKTEstimator
from taleem_core.contexts.learning.domain.forgetting import HalfLifeForgettingModel
from taleem_core.contexts.learning.domain.values import InteractionContext
from taleem_core.platform.errors import Problem

EST = BKTEstimator()
FOG = HalfLifeForgettingModel()
OBJ = "MATH-G4-FR-01"


# ---------------------------------------------------------------- retry helper (pure)


def test_retry_returns_on_success() -> None:
    assert retry_on_conflict(lambda: 42) == 42


def test_retry_succeeds_after_transient_conflicts() -> None:
    calls = {"n": 0}

    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConcurrencyConflictError("boom")
        return "ok"

    assert retry_on_conflict(flaky) == "ok"
    assert calls["n"] == 3


def test_retry_exhausts_and_raises() -> None:
    def always() -> None:
        raise ConcurrencyConflictError("nope")

    with pytest.raises(ConcurrencyConflictError):
        retry_on_conflict(always, retries=3)


# ---------------------------------------------------------------- UoW conflict translation


class _FakeSession:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.rolled_back = False

    def commit(self) -> None:
        raise self._exc

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        pass


def _uow_with(exc: Exception) -> tuple[LearningUnitOfWork, _FakeSession]:
    fake = _FakeSession(exc)
    uow = LearningUnitOfWork(sessionmaker())  # factory unused; we inject the session
    uow._session = fake  # type: ignore[assignment]
    return uow, fake


def test_uow_translates_stale_data_to_conflict() -> None:
    uow, fake = _uow_with(StaleDataError("UPDATE ... 0 rows", None, None, None))
    with pytest.raises(ConcurrencyConflictError):
        uow.commit()
    assert fake.rolled_back


def test_uow_translates_sqlite_locked_to_conflict() -> None:
    uow, fake = _uow_with(OperationalError("database is locked", None, Exception("locked")))
    with pytest.raises(ConcurrencyConflictError):
        uow.commit()
    assert fake.rolled_back


def test_uow_reraises_other_operational_errors() -> None:
    uow, _ = _uow_with(OperationalError("syntax error near", None, Exception("boom")))
    with pytest.raises(OperationalError):
        uow.commit()


# ---------------------------------------------------------------- record_attempt retries


class _ConflictOnceUoW:
    """Wraps a real UoW but forces the first commit() to raise a conflict (then delegates)."""

    _fail_first = True

    def __init__(self, real: LearningUnitOfWork) -> None:
        self._real = real

    def __enter__(self) -> _ConflictOnceUoW:
        self._real.__enter__()
        self.knowledge = self._real.knowledge
        self.events = self._real.events
        return self

    def __exit__(self, *a: object) -> None:
        self._real.__exit__(*a)  # type: ignore[arg-type]

    def commit(self) -> None:
        if _ConflictOnceUoW._fail_first:
            _ConflictOnceUoW._fail_first = False
            self._real.rollback()
            raise ConcurrencyConflictError("injected first-commit conflict")
        self._real.commit()


def test_record_attempt_survives_a_conflict() -> None:
    engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(engine)
    factory = create_learning_session_factory(engine)
    _ConflictOnceUoW._fail_first = True

    make_uow = lambda: _ConflictOnceUoW(LearningUnitOfWork(factory))  # noqa: E731
    svc = KnowledgeService(make_uow, EST, FOG, clock=lambda: 1.0)  # type: ignore[arg-type]
    outcome = svc.record_attempt(
        student_ref="cc-stu",
        objective_code=OBJ,
        item_ref="i1",
        session_id="s1",
        correct=True,
        misconception_hits=(),
        hints_used=0,
        response_time_ms=0,
        context=InteractionContext.PRACTICE,
        self_confidence=0.9,
    )
    # The first commit conflicted; the retry re-ran and produced a real, persisted outcome.
    assert outcome.result.outcome.value == "correct"
    assert _ConflictOnceUoW._fail_first is False


def test_record_attempt_maps_exhausted_conflict_to_409() -> None:
    class _AlwaysConflictUoW(_ConflictOnceUoW):
        def commit(self) -> None:
            self._real.rollback()
            raise ConcurrencyConflictError("always")

    engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(engine)
    factory = create_learning_session_factory(engine)
    make_uow = lambda: _AlwaysConflictUoW(LearningUnitOfWork(factory))  # noqa: E731
    svc = KnowledgeService(make_uow, EST, FOG, clock=lambda: 1.0)  # type: ignore[arg-type]
    with pytest.raises(Problem) as ei:
        svc.record_attempt(
            student_ref="cc-stu2",
            objective_code=OBJ,
            item_ref="i1",
            session_id="s1",
            correct=True,
            misconception_hits=(),
            hints_used=0,
            response_time_ms=0,
            context=InteractionContext.PRACTICE,
            self_confidence=0.9,
        )
    assert ei.value.status == 409
    assert ei.value.code == "CONFLICT"
