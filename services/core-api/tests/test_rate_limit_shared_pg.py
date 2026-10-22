"""Shared rate limiting over real PostgreSQL — the multi-instance guarantee.

Each "instance" here owns its own SQLAlchemy engine (its own connection pool), which is what two
serverless invocations have: nothing in common but the database. Runs when ``CS_DATABASE_URL`` is
set; skips otherwise.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from taleem_core.contexts.identity.adapters.identity_api import SIGN_IN_LIMIT
from taleem_core.contexts.identity.adapters.persistence.base import create_identity_engine
from taleem_core.contexts.identity.adapters.persistence.rate_limit_store import (
    SqlRateLimitStore,
)
from taleem_core.contexts.identity.adapters.rate_limit import SharedRateLimiter
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.errors import Problem

PG_URL = os.environ.get("CS_DATABASE_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")

LIMIT = 10
WINDOW = 60


def _alembic_config() -> object:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


@pytest.fixture
def migrated() -> None:
    from alembic import command

    command.upgrade(_alembic_config(), "head")


def _engine() -> Engine:
    return create_identity_engine(PG_URL or "")


def _has_table(engine: Engine) -> bool:
    return "rate_limit_bucket" in inspect(engine).get_table_names(schema="identity")


def test_migration_0006_is_reversible() -> None:
    from alembic import command

    cfg = _alembic_config()
    command.upgrade(cfg, "head")
    engine = _engine()
    try:
        assert _has_table(engine)
        with engine.connect() as conn:
            persistence = conn.execute(
                text(
                    "SELECT c.relpersistence FROM pg_class c JOIN pg_namespace n "
                    "ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'identity' AND c.relname = 'rate_limit_bucket'"
                )
            ).scalar_one()
        assert persistence == "u"  # UNLOGGED

        command.downgrade(cfg, "0005_refresh")
        assert not _has_table(engine)
        # The rest of the identity schema is untouched by the downgrade.
        assert "refresh_token" in inspect(engine).get_table_names(schema="identity")

        command.upgrade(cfg, "head")
        assert _has_table(engine)
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()


def test_two_instances_with_separate_engines_share_one_budget(migrated: None) -> None:
    scope = f"test.{uuid.uuid4().hex[:12]}"
    engine_a, engine_b = _engine(), _engine()
    clock = lambda: 6_000.0  # noqa: E731 — a fixed window start, so the estimate is exact
    try:
        instance_a = SharedRateLimiter(scope, LIMIT, WINDOW, clock, SqlRateLimitStore(engine_a))
        instance_b = SharedRateLimiter(scope, LIMIT, WINDOW, clock, SqlRateLimitStore(engine_b))
        for i in range(LIMIT):
            (instance_a if i % 2 else instance_b).check("203.0.113.7")
        for instance in (instance_a, instance_b):
            with pytest.raises(Problem) as refused:
                instance.check("203.0.113.7")
            assert refused.value.status == 429
        # Another client is unaffected on either instance.
        instance_b.check("198.51.100.9")
    finally:
        engine_a.dispose()
        engine_b.dispose()


def test_concurrent_instances_admit_exactly_the_limit(migrated: None) -> None:
    """The atomic upsert is the whole point: racing instances cannot both read 9 and write 10."""
    scope = f"test.{uuid.uuid4().hex[:12]}"
    engines = [_engine() for _ in range(4)]
    clock = lambda: 6_000.0  # noqa: E731
    allowed: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(len(engines))

    def run(engine: Engine) -> None:
        limiter = SharedRateLimiter(scope, LIMIT, WINDOW, clock, SqlRateLimitStore(engine))
        barrier.wait()
        for _ in range(10):
            try:
                limiter.check("203.0.113.7")
                with lock:
                    allowed.append(1)
            except Problem:
                pass

    threads = [threading.Thread(target=run, args=(engine,)) for engine in engines]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(allowed) == LIMIT
        with engines[0].connect() as conn:
            hits = conn.execute(
                text("SELECT hits FROM identity.rate_limit_bucket WHERE scope = :s"), {"s": scope}
            ).scalar_one()
        assert hits == 40  # every attempt counted exactly once
    finally:
        for engine in engines:
            engine.dispose()


def test_expired_buckets_are_purged(migrated: None) -> None:
    scope = f"test.{uuid.uuid4().hex[:12]}"
    engine = _engine()
    try:
        store = SqlRateLimitStore(engine)
        store.hit(scope, "a" * 64, 6_000, WINDOW)
        store.hit(scope, "b" * 64, 9_000_000_000, WINDOW)
        store.purge_expired(6_500.0)
        with engine.connect() as conn:
            remaining = (
                conn.execute(
                    text("SELECT key_hash FROM identity.rate_limit_bucket WHERE scope = :s"),
                    {"s": scope},
                )
                .scalars()
                .all()
            )
        assert remaining == ["b" * 64]
    finally:
        engine.dispose()


def test_two_composed_apps_share_the_sign_in_budget(migrated: None) -> None:
    """End to end through the wiring: a PostgreSQL URL selects the shared store."""
    # Stay clear of a window boundary so the whole burst lands in one window.
    if time.time() % WINDOW > WINDOW - 10:
        time.sleep(11)
    engine = _engine()
    try:
        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM identity.rate_limit_bucket WHERE scope = 'identity.sign_in'")
            )
    finally:
        engine.dispose()

    settings = Settings(database_url=PG_URL or "", kdf_iterations=1_000)
    app_a, app_b = TestClient(create_app(settings)), TestClient(create_app(settings))
    body = {"email": "nobody@example.com", "passphrase": "not-the-passphrase"}
    statuses = [
        (app_a if i % 2 else app_b).post("/v1/identity/guardians:signin", json=body).status_code
        for i in range(SIGN_IN_LIMIT)
    ]
    assert 429 not in statuses
    # The budget is spent across the two "instances"; both now refuse.
    assert app_a.post("/v1/identity/guardians:signin", json=body).status_code == 429
    assert app_b.post("/v1/identity/guardians:signin", json=body).status_code == 429
