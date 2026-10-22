"""Shared rate limiter — the store and the sliding-window decision, without a database server.

The SQL store runs here on SQLite, which supports the same ``INSERT ... ON CONFLICT ... RETURNING``
statement PostgreSQL executes in production; the cross-engine, cross-process proof lives in the
PostgreSQL-gated ``test_rate_limit_shared_pg.py``.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.engine import Engine

from taleem_core.contexts.identity.adapters.persistence.base import (
    IdentityBase,
    create_identity_engine,
)
from taleem_core.contexts.identity.adapters.persistence.models import RateLimitBucketRow
from taleem_core.contexts.identity.adapters.persistence.rate_limit_store import (
    SqlRateLimitStore,
)
from taleem_core.contexts.identity.adapters.rate_limit import (
    RateLimiter,
    SharedRateLimiter,
    client_key_digest,
)
from taleem_core.platform.errors import Problem

LIMIT = 10
WINDOW = 60


class Clock:
    def __init__(self, now: float = 6_000.0) -> None:  # 6000 is a window boundary (100 * 60)
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def engine() -> Engine:
    engine = create_identity_engine("sqlite://")
    IdentityBase.metadata.create_all(engine)
    return engine


@pytest.fixture
def store(engine: Engine) -> SqlRateLimitStore:
    return SqlRateLimitStore(engine)


def _limiter(store: object, clock: Clock, scope: str = "identity.sign_in") -> SharedRateLimiter:
    return SharedRateLimiter(scope, LIMIT, WINDOW, clock, store)  # type: ignore[arg-type]


def _allowed(limiter: SharedRateLimiter, key: str, attempts: int) -> int:
    allowed = 0
    for _ in range(attempts):
        try:
            limiter.check(key)
            allowed += 1
        except Problem as problem:
            assert problem.status == 429
    return allowed


# --------------------------------------------------------------------------------- the store


def test_hit_is_an_atomic_increment_that_returns_the_new_count(store: SqlRateLimitStore) -> None:
    assert store.hit("s", "k" * 64, 6_000, WINDOW) == (1, 0)
    assert store.hit("s", "k" * 64, 6_000, WINDOW) == (2, 0)
    assert store.hit("s", "k" * 64, 6_000, WINDOW) == (3, 0)


def test_hit_reports_the_previous_window(store: SqlRateLimitStore) -> None:
    for _ in range(4):
        store.hit("s", "k" * 64, 6_000, WINDOW)
    assert store.hit("s", "k" * 64, 6_060, WINDOW) == (1, 4)


def test_buckets_are_isolated_by_scope_and_key(store: SqlRateLimitStore) -> None:
    store.hit("a", "k" * 64, 6_000, WINDOW)
    assert store.hit("b", "k" * 64, 6_000, WINDOW) == (1, 0)
    assert store.hit("a", "j" * 64, 6_000, WINDOW) == (1, 0)


def test_purge_removes_only_expired_buckets(store: SqlRateLimitStore, engine: Engine) -> None:
    store.hit("s", "old" + "0" * 61, 6_000, WINDOW)  # expires at 6_120
    store.hit("s", "new" + "0" * 61, 6_060, WINDOW)  # expires at 6_180
    assert store.purge_expired(6_150.0) == 1
    with engine.connect() as conn:
        remaining = conn.execute(select(RateLimitBucketRow.__table__.c.key_hash)).scalars().all()
    assert remaining == ["new" + "0" * 61]


def test_the_store_refuses_an_unsupported_dialect() -> None:
    class FakeEngine:
        class dialect:  # noqa: N801 — mimics the SQLAlchemy attribute
            name = "mysql"

    with pytest.raises(ValueError, match="unsupported dialect"):
        SqlRateLimitStore(FakeEngine())  # type: ignore[arg-type]


# ----------------------------------------------------------------- the limiter over the store


def test_two_limiter_instances_share_one_budget(store: SqlRateLimitStore) -> None:
    """The in-process analogue of two serverless instances; the PostgreSQL test repeats this with
    two separate engines."""
    clock = Clock()
    instance_a, instance_b = _limiter(store, clock), _limiter(store, clock)
    for i in range(LIMIT):
        (instance_a if i % 2 else instance_b).check("203.0.113.7")
    with pytest.raises(Problem) as refused:
        instance_a.check("203.0.113.7")
    assert refused.value.status == 429
    with pytest.raises(Problem):
        instance_b.check("203.0.113.7")


def test_the_budget_is_per_client(store: SqlRateLimitStore) -> None:
    clock = Clock()
    limiter = _limiter(store, clock)
    assert _allowed(limiter, "203.0.113.7", LIMIT + 5) == LIMIT
    assert _allowed(limiter, "198.51.100.9", LIMIT) == LIMIT


def test_scopes_have_independent_budgets(store: SqlRateLimitStore) -> None:
    clock = Clock()
    assert _allowed(_limiter(store, clock, "identity.sign_in"), "c", LIMIT + 1) == LIMIT
    assert _allowed(_limiter(store, clock, "identity.roster"), "c", LIMIT) == LIMIT


def test_no_double_burst_across_a_window_boundary(store: SqlRateLimitStore) -> None:
    """A bare fixed window admits 10 at :59 and 10 more at :01; the sliding estimate does not."""
    clock = Clock(6_059.0)
    limiter = _limiter(store, clock)
    assert _allowed(limiter, "c", LIMIT) == LIMIT
    clock.now = 6_061.0
    assert _allowed(limiter, "c", LIMIT) == 0


def test_the_budget_recovers_as_the_previous_window_ages_out(store: SqlRateLimitStore) -> None:
    clock = Clock(6_000.0)
    limiter = _limiter(store, clock)
    assert _allowed(limiter, "c", LIMIT) == LIMIT
    clock.now = 6_090.0  # halfway through the next window: previous weighs 0.5 -> 5 used
    assert _allowed(limiter, "c", LIMIT) == 5
    clock.now = 6_180.0  # two windows on: nothing carries over
    assert _allowed(limiter, "c", LIMIT) == LIMIT


def test_refused_attempts_still_count(store: SqlRateLimitStore) -> None:
    """A client that keeps hammering does not earn a fresh allowance as its early hits age out."""
    clock = Clock(6_000.0)
    limiter = _limiter(store, clock)
    _allowed(limiter, "c", 40)  # 10 allowed, 30 refused, all counted
    clock.now = 6_090.0  # previous = 40 * 0.5 = 20 > limit
    assert _allowed(limiter, "c", 1) == 0


def test_retry_after_points_at_the_end_of_the_window(store: SqlRateLimitStore) -> None:
    clock = Clock(6_045.0)
    limiter = _limiter(store, clock)
    _allowed(limiter, "c", LIMIT)
    with pytest.raises(Problem) as refused:
        limiter.check("c")
    assert "15 seconds" in refused.value.detail


def test_no_raw_client_identifier_is_stored(store: SqlRateLimitStore, engine: Engine) -> None:
    _limiter(store, Clock()).check("203.0.113.7")
    with engine.connect() as conn:
        rows = conn.execute(select(RateLimitBucketRow.__table__)).mappings().all()
    assert len(rows) == 1
    assert "203.0.113.7" not in repr(dict(rows[0]))
    assert rows[0]["key_hash"] == client_key_digest("identity.sign_in", "203.0.113.7")
    assert len(rows[0]["key_hash"]) == 64


def test_the_digest_is_scope_bound() -> None:
    assert client_key_digest("a", "x") != client_key_digest("b", "x")
    assert client_key_digest("a", "x") == client_key_digest("a", "x")


# --------------------------------------------------------------------- failure and housekeeping


class BrokenStore:
    def __init__(self) -> None:
        self.purges = 0

    def hit(self, *_: object) -> tuple[int, int]:
        raise RuntimeError("database unreachable")

    def purge_expired(self, now: float) -> int:
        self.purges += 1
        raise RuntimeError("database unreachable")


def test_a_store_outage_degrades_to_the_local_limit_rather_than_none() -> None:
    limiter = _limiter(BrokenStore(), Clock())
    assert _allowed(limiter, "c", LIMIT + 5) == LIMIT


class CountingStore:
    def __init__(self) -> None:
        self.purges = 0

    def hit(self, *_: object) -> tuple[int, int]:
        return 1, 0

    def purge_expired(self, now: float) -> int:
        self.purges += 1
        return 0


def test_purge_runs_on_the_first_check_and_then_periodically() -> None:
    store = CountingStore()
    limiter = SharedRateLimiter("s", LIMIT, WINDOW, Clock(), store, purge_every=3)
    for _ in range(7):
        limiter.check("c")
    assert store.purges == 3  # checks 1, 4 and 7


def test_purge_every_one_purges_on_every_check() -> None:
    store = CountingStore()
    limiter = SharedRateLimiter("s", LIMIT, WINDOW, Clock(), store, purge_every=1)
    for _ in range(3):
        limiter.check("c")
    assert store.purges == 3


def test_a_failed_purge_never_fails_the_request() -> None:
    class PurgeFails(CountingStore):
        def purge_expired(self, now: float) -> int:
            raise RuntimeError("lock timeout")

    SharedRateLimiter("s", LIMIT, WINDOW, Clock(), PurgeFails()).check("c")


def test_sub_second_windows_are_refused() -> None:
    with pytest.raises(ValueError, match="whole seconds"):
        SharedRateLimiter("s", LIMIT, 0.5, Clock(), CountingStore())


def test_the_in_memory_limiter_is_unchanged() -> None:
    limiter = RateLimiter(LIMIT, WINDOW, Clock())
    for _ in range(LIMIT):
        limiter.check("c")
    with pytest.raises(Problem):
        limiter.check("c")
    limiter.reset()
    limiter.check("c")
