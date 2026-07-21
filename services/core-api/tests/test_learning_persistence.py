"""Persistence tests for the learning context — durable StudentKnowledge + evidence + outbox."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from taleem_core.contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from taleem_core.contexts.learning.adapters.persistence.models import (
    AssessmentEvidenceRow,
    LearningOutboxRow,
)
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.learning.domain.estimator import BKTEstimator
from taleem_core.contexts.learning.domain.events import objective_mastered
from taleem_core.contexts.learning.domain.forgetting import HalfLifeForgettingModel
from taleem_core.contexts.learning.domain.knowledge import StudentKnowledge
from taleem_core.contexts.learning.domain.values import InteractionContext, MasteryState

EST = BKTEstimator()
FOG = HalfLifeForgettingModel()
OBJ = "MATH-G4-FR-01"


@pytest.fixture
def factory() -> sessionmaker[Session]:
    engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(engine)
    return create_learning_session_factory(engine)


def _build_knowledge() -> StudentKnowledge:
    k = StudentKnowledge("stu-x")
    k.ensure_objective(OBJ, initial=EST.initial())
    for i in range(6):
        k.apply_attempt(
            evidence_id=f"ev{i}",
            objective_code=OBJ,
            item_ref="i",
            session_id="s",
            correct=True,
            misconception_hits=(),
            hints_used=0,
            response_time_ms=0,
            context=InteractionContext.PRACTICE,
            self_confidence=0.9,
            estimator=EST,
            forgetting=FOG,
            now=float(i + 1),
        )
    return k


def test_knowledge_roundtrip(factory: sessionmaker[Session]) -> None:
    original = _build_knowledge()
    with LearningUnitOfWork(factory) as uow:
        uow.knowledge.save(original)
        uow.commit()
    with LearningUnitOfWork(factory) as uow:
        loaded = uow.knowledge.get("stu-x")
    assert loaded is not None
    obj = loaded.get(OBJ)
    assert obj is not None
    assert obj.state is MasteryState.MASTERED
    assert obj.mastery.value == pytest.approx(original.get(OBJ).mastery.value)  # type: ignore[union-attr]
    assert len(loaded.evidence) == 6


def test_evidence_is_append_only_idempotent(factory: sessionmaker[Session]) -> None:
    k = _build_knowledge()
    with LearningUnitOfWork(factory) as uow:
        uow.knowledge.save(k)
        uow.commit()
    # Re-saving the same aggregate must not duplicate immutable evidence rows.
    with LearningUnitOfWork(factory) as uow:
        again = uow.knowledge.get("stu-x")
        uow.knowledge.save(again)  # type: ignore[arg-type]
        uow.commit()
    with LearningUnitOfWork(factory) as uow:
        count = uow.session.execute(
            select(func.count()).select_from(AssessmentEvidenceRow)
        ).scalar()
    assert count == 6


def test_events_persist_to_outbox(factory: sessionmaker[Session]) -> None:
    k = _build_knowledge()
    with LearningUnitOfWork(factory) as uow:
        uow.knowledge.save(k)
        uow.events.publish([objective_mastered("stu-x", OBJ, 100.0)])
        uow.commit()
    with LearningUnitOfWork(factory) as uow:
        rows = list(uow.session.execute(select(LearningOutboxRow)).scalars())
    assert len(rows) == 1
    assert rows[0].event_type == "ObjectiveMastered"
    assert rows[0].payload["objective_code"] == OBJ


def test_no_child_pii_columns() -> None:
    # The learning store keys on a pseudonymous student_ref only — never a name/identity.
    forbidden = ("name", "email", "phone", "address", "dob", "birth")
    for table in LearningBase.metadata.tables.values():
        for column in table.columns:
            assert not any(tok in column.name.lower() for tok in forbidden), column.name
