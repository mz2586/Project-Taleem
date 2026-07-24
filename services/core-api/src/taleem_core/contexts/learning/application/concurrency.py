"""Optimistic-concurrency control for the learning write path.

``student_knowledge`` uses SQLAlchemy ``version_id_col`` optimistic locking, so two concurrent
read-modify-write transactions on the *same* learner's knowledge race: the loser's version-guarded
UPDATE matches 0 rows and the ORM raises ``StaleDataError``. That is the lock working (it prevents a
lost update) but the loser must not surface as a 500. The adapter translates the infrastructure
conflict into ``ConcurrencyConflictError`` (defined here so the dependency points inward: the
adapter imports the application, never the reverse), and the application retries the whole
read-modify-write against the freshly-committed state. Legitimate concurrency (a live answer racing
a background sync drain on one learner) then serializes transparently; only pathological contention
exhausts the budget.
"""

from __future__ import annotations

from collections.abc import Callable

# Enough retries to serialize realistic concurrency on one learner's row (a live write racing a sync
# drain is 2 writers). Beyond this the caller gets an honest, retryable conflict rather than a 500.
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
