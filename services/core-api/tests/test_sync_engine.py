"""Tests for the offline sync engine — the remediated conflict policy (audit AR-H-28, OFFL-02/03)."""

from __future__ import annotations

import unittest

from taleem_core.contexts.sync.domain import (
    DeltaType,
    Status,
    SyncDelta,
    SyncEngine,
    SyncStore,
)


def progress(eid: str, key: str, block: int, seq: int = 0) -> SyncDelta:
    return SyncDelta(eid, DeltaType.PROGRESS, key, {"block": block}, seq)


def attempt(eid: str, key: str, attempt_id: str, seq: int = 0) -> SyncDelta:
    return SyncDelta(eid, DeltaType.ATTEMPT_SUBMITTED, key, {"attempt_id": attempt_id}, seq)


class TestIdempotentReplay(unittest.TestCase):
    def test_replaying_queue_twice_yields_identical_state(self) -> None:
        """OFFL-02: flush the same queue twice → identical server state."""
        store = SyncStore()
        engine = SyncEngine(store)
        batch = [
            progress("e1", "S1|L1", 3),
            attempt("e2", "S1|A1", "att-1"),
        ]
        results1, cursor1 = engine.apply_batch(batch)
        snap1 = store.snapshot("S1|L1").progress_block, sorted(store.snapshot("S1|A1").attempts)

        # Replay the exact same batch (device retried before clearing its queue).
        results2, cursor2 = engine.apply_batch(batch)
        snap2 = store.snapshot("S1|L1").progress_block, sorted(store.snapshot("S1|A1").attempts)

        self.assertEqual(snap1, snap2)  # state unchanged
        self.assertEqual(cursor1, cursor2)  # cursor did not advance on replay
        self.assertTrue(all(r.status is Status.APPLIED for r in results1))
        self.assertTrue(all(r.status is Status.DUPLICATE for r in results2))


class TestProgressMonotonic(unittest.TestCase):
    def test_never_regresses_and_ignores_stale_without_client_clock(self) -> None:
        store = SyncStore()
        engine = SyncEngine(store)
        # Apply block 5, then a *stale* block 2 with a LOWER seq (as if from a lagging device).
        engine.apply_batch([progress("e1", "S1|L1", 5, seq=10)])
        results, _ = engine.apply_batch([progress("e2", "S1|L1", 2, seq=1)])
        self.assertEqual(store.snapshot("S1|L1").progress_block, 5)  # not regressed
        self.assertEqual(results[0].status, Status.IGNORED)

    def test_intra_batch_ordered_by_seq_not_wall_clock(self) -> None:
        store = SyncStore()
        engine = SyncEngine(store)
        # Deltas arrive out of order in the list; engine orders by client_seq.
        engine.apply_batch([progress("e2", "S1|L1", 7, seq=2), progress("e1", "S1|L1", 4, seq=1)])
        self.assertEqual(store.snapshot("S1|L1").progress_block, 7)


class TestAttemptAppendOnly(unittest.TestCase):
    def test_attempts_merge_by_union_never_lost(self) -> None:
        store = SyncStore()
        engine = SyncEngine(store)
        engine.apply_batch([attempt("e1", "S1|A1", "att-1"), attempt("e2", "S1|A1", "att-2")])
        self.assertEqual(store.snapshot("S1|A1").attempts, {"att-1", "att-2"})

    def test_duplicate_attempt_id_reported(self) -> None:
        store = SyncStore()
        engine = SyncEngine(store)
        r, _ = engine.apply_batch(
            [attempt("e1", "S1|A1", "att-1"), attempt("e2", "S1|A1", "att-1")]
        )
        statuses = {res.client_event_id: res.status for res in r}
        self.assertEqual(statuses["e1"], Status.APPLIED)
        self.assertEqual(statuses["e2"], Status.DUPLICATE)


class TestCompletionIdempotent(unittest.TestCase):
    def test_once_completed_stays_completed(self) -> None:
        store = SyncStore()
        engine = SyncEngine(store)
        d1 = SyncDelta("e1", DeltaType.LESSON_COMPLETED, "S1|L1", {})
        d2 = SyncDelta("e2", DeltaType.LESSON_COMPLETED, "S1|L1", {})
        r, _ = engine.apply_batch([d1])
        self.assertEqual(r[0].status, Status.APPLIED)
        r2, _ = engine.apply_batch([d2])
        self.assertEqual(r2[0].status, Status.IGNORED)
        self.assertTrue(store.snapshot("S1|L1").completed)


class TestPreferenceServerOrder(unittest.TestCase):
    def test_server_order_wins_not_client_clock(self) -> None:
        store = SyncStore()
        engine = SyncEngine(store)
        p1 = SyncDelta("e1", DeltaType.PREFERENCE, "S1|pref", {"value": "a"}, client_seq=1)
        p2 = SyncDelta("e2", DeltaType.PREFERENCE, "S1|pref", {"value": "b"}, client_seq=2)
        engine.apply_batch([p2, p1])  # arrive reversed; seq orders them a then b
        self.assertEqual(store.snapshot("S1|pref").preference, "b")


if __name__ == "__main__":
    unittest.main()
