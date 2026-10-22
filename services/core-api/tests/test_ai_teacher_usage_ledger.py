"""Durable per-learner AI usage ledger (migration 0007) — contract, retention, cross-instance quota.

The same contract is asserted for the in-memory ledger (dev/test) and the SQL ledger (production):
per-learner and per-period aggregates, an operator view across learners, and ``purge_older_than``
for the future retention schedule. The table holds counts and a pseudonymous ref only — no text.
PostgreSQL-gated tests prove the migration is reversible and that two app instances enforce ONE
quota for the same learner.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.identity.domain.consent import ConsentEvidence, ConsentScope
from taleem_core.contexts.learning.adapters.persistence.ai_usage_ledger import (
    SqlLearnerUsageLedger,
)
from taleem_core.contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from taleem_core.contexts.learning.adapters.persistence.models import AIUsageRow
from taleem_core.contexts.learning.domain.ai_teacher_gate import GENERATIVE_FLAG
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.ports.llm import (
    InMemoryCostLedger,
    LearnerUsageLedger,
    Tier,
    UsageRecord,
    UsageSummary,
)
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)


def _sqlite_ledger() -> SqlLearnerUsageLedger:
    engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(engine)
    return SqlLearnerUsageLedger(create_learning_session_factory(engine))


@pytest.fixture(params=["memory", "sql"])
def ledger(request: pytest.FixtureRequest) -> LearnerUsageLedger:
    return InMemoryCostLedger() if request.param == "memory" else _sqlite_ledger()


def _rec(ref: str, at: float, tokens: int = 5, cost: int = 0) -> UsageRecord:
    return UsageRecord("stub", Tier.LIGHT, tokens, 1, cost, "ai_teacher.rephrase", ref, at)


def test_ledger_contract_per_learner_and_period(ledger: LearnerUsageLedger) -> None:
    for ref, at, tokens, cost in (("a", 10.0, 5, 1), ("a", 90_000.0, 7, 2), ("b", 20.0, 11, 3)):
        ledger.record(_rec(ref, at, tokens, cost))
    assert ledger.usage_for("a") == UsageSummary(calls=2, tokens=14, cost_micros=3)
    assert ledger.usage_for("a", since=0, until=86_400) == UsageSummary(1, 6, 1)
    assert ledger.usage_for("a", since=86_400) == UsageSummary(1, 8, 2)
    assert ledger.usage_for("nobody") == UsageSummary(0, 0, 0)
    assert ledger.by_learner(until=86_400) == {
        "a": UsageSummary(1, 6, 1),
        "b": UsageSummary(1, 12, 3),
    }


def test_purge_older_than_supports_a_retention_schedule(ledger: LearnerUsageLedger) -> None:
    for at in (1.0, 2.0, 100.0):
        ledger.record(_rec("a", at))
    assert ledger.purge_older_than(50.0) == 2
    assert ledger.usage_for("a").calls == 1
    assert ledger.purge_older_than(50.0) == 0


def test_ledger_rows_hold_counts_and_a_pseudonymous_ref_only() -> None:
    columns = {c.name for c in AIUsageRow.__table__.columns}
    assert columns == {
        "id",
        "learner_ref",
        "provider",
        "tier",
        "purpose",
        "prompt_tokens",
        "completion_tokens",
        "cost_micros",
        "recorded_at",
    }
    assert not any(word in c for c in columns for word in ("text", "prompt_text", "output", "name"))


def test_default_sqlite_app_uses_the_in_memory_ledger() -> None:
    app = create_app(Settings(database_url=""))
    assert isinstance(app.state.ai_cost_ledger, InMemoryCostLedger)


# ---------------------------------------------------------------- PostgreSQL-gated


def _alembic_config() -> Any:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


def _has_table() -> bool:
    engine = create_learning_engine(PG_URL or "")
    try:
        return "ai_usage_ledger" in inspect(engine).get_table_names(schema="learning")
    finally:
        engine.dispose()


@_pg_only
def test_migration_0007_is_reversible() -> None:
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    try:
        assert _has_table()
        command.downgrade(cfg, "0006_rate_limit")
        assert not _has_table()
        command.upgrade(cfg, "head")
        assert _has_table()
    finally:
        command.upgrade(cfg, "head")


@_pg_only
def test_two_ledgers_on_separate_engines_see_the_same_usage() -> None:
    from alembic import command

    command.upgrade(_alembic_config(), "head")
    engines = [create_learning_engine(PG_URL or "") for _ in range(2)]
    try:
        a, b = (SqlLearnerUsageLedger(create_learning_session_factory(e)) for e in engines)
        ref = f"stu-{uuid.uuid4().hex[:10]}"
        a.record(_rec(ref, 1_000.0, tokens=3))
        b.record(_rec(ref, 1_001.0, tokens=4))
        assert a.usage_for(ref) == b.usage_for(ref) == UsageSummary(2, 9, 0)
        assert b.purge_older_than(1_000.5) >= 1
        assert a.usage_for(ref).calls == 1
    finally:
        for e in engines:
            e.dispose()


def _auth(sub: str) -> dict[str, str]:
    exp = int(time.time()) + 3600
    token = sign_hs256({"sub": sub, "role": "student", "exp": exp}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pg_apps() -> Iterator[tuple[FastAPI, FastAPI]]:
    from alembic import command

    cfg = _alembic_config()
    command.downgrade(cfg, "base")  # a clean schema: the lesson is published exactly once below
    command.upgrade(cfg, "head")
    settings = Settings(
        database_url=PG_URL or "",
        kdf_iterations=1_000,
        enabled_flags_csv=GENERATIVE_FLAG,
        ai_provider="stub",
        ai_learner_daily_calls=2,
    )
    yield create_app(settings), create_app(settings)


@_pg_only
def test_quota_is_enforced_once_across_two_app_instances(pg_apps: tuple[FastAPI, FastAPI]) -> None:
    from tests.test_ai_teacher import _publish_fractions

    app_a, app_b = pg_apps
    assert isinstance(app_a.state.ai_cost_ledger, SqlLearnerUsageLedger)
    _publish_fractions(app_a)

    identity = app_a.state.identity_service
    guardian = identity.register_guardian(
        email=f"quota-{uuid.uuid4().hex[:8]}@example.org",
        passphrase="a-guardian-passphrase",  # noqa: S106 (test fixture)
        display_name="Amina",
    )["guardian"]["guardian_ref"]
    student = identity.enrol_learner(guardian_ref=guardian, display_name="Sara", pin="4826")[
        "student_ref"
    ]
    identity.grant_consent(
        guardian_ref=guardian,
        student_ref=student,
        scopes={ConsentScope.LEARNING_DATA, ConsentScope.AI_TEACHING},
        evidence=ConsentEvidence(attestation="test"),
    )

    def explain(app: FastAPI) -> dict[str, Any]:
        client = TestClient(app)
        h = _auth(student)
        sid = client.post("/v1/learning/sessions", json={"student_ref": student}, headers=h).json()[
            "session_id"
        ]
        r = client.post(
            f"/v1/learning/sessions/{sid}:explain",
            json={"objective_code": OBJECTIVE_CODE, "locale": "en"},
            headers=h,
        )
        assert r.status_code == 200, r.text
        body: dict[str, Any] = r.json()
        return body

    first, second, third = explain(app_a), explain(app_b), explain(app_a)
    assert first["generation"]["status"] == "accepted"
    assert second["generation"]["status"] == "accepted"
    # The quota (2/day) was spent across BOTH instances: the third call is templated, not an error.
    assert "generation" not in third
    assert app_b.state.ai_cost_ledger.usage_for(student).calls == 2
