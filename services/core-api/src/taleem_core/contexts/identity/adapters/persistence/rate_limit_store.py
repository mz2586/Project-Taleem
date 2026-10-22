"""SQL-backed shared store for the identity rate limiter (``identity.rate_limit_bucket``).

One row per (scope, client digest, fixed window). An attempt is a single atomic statement::

    INSERT ... VALUES (..., hits = 1)
    ON CONFLICT (scope, key_hash, window_start) DO UPDATE SET hits = rate_limit_bucket.hits + 1
    RETURNING hits

so two instances racing on the same client cannot both read "9" and both write "10": PostgreSQL
serialises the conflicting upserts on the row lock and each caller sees its own post-increment
count. The previous window's count (needed for the sliding estimate) is read in the same
transaction; it is no longer being written by anyone except a straggler, so a plain read suffices.

A bucket can influence decisions for two windows (as "current", then as "previous"), so it expires
two windows after it opened and is purged by ``purge_expired``.

The same statements run on SQLite (3.35+ supports ``ON CONFLICT ... RETURNING``), which lets the
unit suite exercise the real SQL path without a server. Production selects this store only for a
PostgreSQL URL.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Table, and_, delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Engine

from .models import RateLimitBucketRow

_TABLE: Table = RateLimitBucketRow.__table__  # type: ignore[assignment]


class SqlRateLimitStore:
    """Shared, cross-process rate-limit counters. Safe to share one instance across threads."""

    def __init__(self, engine: Engine) -> None:
        dialect = engine.dialect.name
        if dialect not in ("postgresql", "sqlite"):
            raise ValueError(f"unsupported dialect for the shared rate limiter: {dialect}")
        self._engine = engine
        self._insert: Any = postgresql.insert if dialect == "postgresql" else sqlite.insert

    def hit(
        self, scope: str, key_digest: str, window_start: int, window_seconds: int
    ) -> tuple[int, int]:
        insert = self._insert(_TABLE).values(
            scope=scope,
            key_hash=key_digest,
            window_start=window_start,
            hits=1,
            expires_at=float(window_start + 2 * window_seconds),
        )
        upsert = insert.on_conflict_do_update(
            index_elements=[_TABLE.c.scope, _TABLE.c.key_hash, _TABLE.c.window_start],
            set_={"hits": _TABLE.c.hits + 1},
        ).returning(_TABLE.c.hits)
        previous_q = select(_TABLE.c.hits).where(
            and_(
                _TABLE.c.scope == scope,
                _TABLE.c.key_hash == key_digest,
                _TABLE.c.window_start == window_start - window_seconds,
            )
        )
        with self._engine.begin() as conn:
            current = int(conn.execute(upsert).scalar_one())
            previous = conn.execute(previous_q).scalar_one_or_none()
        return current, int(previous or 0)

    def purge_expired(self, now: float) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(delete(_TABLE).where(_TABLE.c.expires_at < now))
        return int(result.rowcount or 0)
