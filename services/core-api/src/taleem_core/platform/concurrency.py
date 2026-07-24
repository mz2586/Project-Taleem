"""Optimistic-concurrency primitives shared across contexts (pure-stdlib).

Aggregate roots use SQLAlchemy ``version_id_col`` optimistic locking, so two concurrent
read-modify-write transactions on the same row race: the loser's version-guarded UPDATE matches 0
rows and the ORM raises ``StaleDataError``. That is the lock working (it prevents a lost update) but
it must never surface as a 500. Adapters translate the infrastructure conflict into
``ConcurrencyConflictError`` (defined in ``platform`` so any context can raise/handle it with no
cross-context coupling). Callers either retry the whole read-modify-write (``retry_on_conflict``,
for high-frequency child-facing writes) or map it to a 409 (staff tooling, where a client retry is
the standard optimistic-concurrency answer).
"""

from __future__ import annotations

from collections.abc import Callable

# Enough retries to serialize realistic concurrency on one row (a live write racing a background
# job is 2 writers). Beyond this the caller gets an honest, retryable conflict rather than a 500.
MAX_CONFLICT_RETRIES = 16


class ConcurrencyConflictError(RuntimeError):
    """An optimistic-lock conflict (a concurrent writer bumped the version). Retryable."""


def retry_on_conflict[T](fn: Callable[[], T], *, retries: int = MAX_CONFLICT_RETRIES) -> T:
    """Run ``fn`` (a full read-modify-write in its own transaction), retrying on a lock conflict.

    ``fn`` MUST open a fresh Unit of Work each call so a retry re-reads the latest committed row.
    Re-raises the last ``ConcurrencyConflictError`` if the retry budget is exhausted.
    """
    last: ConcurrencyConflictError | None = None
    for _ in range(max(1, retries)):
        try:
            return fn()
        except ConcurrencyConflictError as exc:
            last = exc
    raise last if last is not None else ConcurrencyConflictError("conflict")
