"""In-process stores that hold learner references: sync entity state and the AI usage ledger.

Both are process-local today (the sync store and the cost ledger are documented dev/pilot
follow-ups awaiting durable tables), so an erasure clears this process only; a multi-instance
deployment needs the durable versions before erasure can be complete across instances.

Sync *seen ids* are opaque device-generated event ids with no learner reference, so they cannot be
attributed to a learner and are neither exported nor erased (they expire by LRU).
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Protocol

from ..domain.policy import RetainedSet
from ._rows import jsonable, mentions


class _SyncStore(Protocol):
    _entities: OrderedDict[str, Any]


class SyncLearnerData:
    name = "sync"

    def __init__(self, store: _SyncStore) -> None:
        self._store = store

    def covers(self) -> tuple[str, ...]:
        return ("memory:sync.entities",)

    def _keys(self, ref: str) -> list[str]:
        # Entity keys are "student:<ref>|lesson:<id>" — match the student component exactly.
        return [k for k in list(self._store._entities) if f"student:{ref}" in k.split("|")]

    def export(self, student_ref: str) -> dict[str, Any]:
        return {
            "entities": [
                {"entity_key": k, **jsonable(self._store._entities[k])}
                for k in self._keys(student_ref)
            ],
            "withheld": [
                {
                    "field": "seen client event ids",
                    "reason": "opaque device ids with no learner reference; not attributable",
                }
            ],
        }

    def remaining(self, student_ref: str) -> dict[str, int]:
        return {"entities": len(self._keys(student_ref))}

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        return None

    def blockers(self) -> list[str]:
        return []

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        keys = self._keys(student_ref)
        for k in keys:
            self._store._entities.pop(k, None)
        return {"entities": len(keys)}


class _Ledger(Protocol):
    records: list[Any]


class AiUsageLearnerData:
    name = "ai_usage"

    def __init__(self, ledger: Any) -> None:
        # Only the process-local ledger lives here; the durable one is the learning schema's
        # ``ai_usage_ledger`` table, which the learning adapter covers.
        self._ledger: _Ledger | None = ledger if hasattr(ledger, "records") else None

    def covers(self) -> tuple[str, ...]:
        return ("memory:ai.usage_ledger",) if self._ledger is not None else ()

    def _mine(self, ref: str) -> list[Any]:
        if self._ledger is None:
            return []
        return [r for r in self._ledger.records if getattr(r, "learner_ref", "") == ref]

    def export(self, student_ref: str) -> dict[str, Any]:
        return {"usage_records": [jsonable(r) for r in self._mine(student_ref)], "withheld": []}

    def remaining(self, student_ref: str) -> dict[str, int]:
        return {"usage_records": len(self._mine(student_ref))}

    def blockers(self) -> list[str]:
        return []

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        if data_class != "ai_usage" or self._ledger is None:
            return None
        return sum(1 for r in self._ledger.records if getattr(r, "recorded_at", 0.0) < cutoff)

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        if self._ledger is None:
            return {"usage_records": 0}
        before = len(self._ledger.records)
        self._ledger.records[:] = [
            r
            for r in self._ledger.records
            if getattr(r, "learner_ref", "") != student_ref
            and not mentions(getattr(r, "purpose", ""), student_ref)
        ]
        return {"usage_records": before - len(self._ledger.records)}


class GuardianViewData:
    """The guardian portal stores nothing: every view is derived on read from identity + learning.

    Present so the export says so explicitly, and so a future stored read model has an owner.
    """

    name = "guardian"

    def covers(self) -> tuple[str, ...]:
        return ()

    def export(self, student_ref: str) -> dict[str, Any]:
        return {
            "stored_rows": 0,
            "note": "Guardian portal views are derived on read from the identity and learning "
            "records above; nothing is stored separately.",
            "withheld": [],
        }

    def remaining(self, student_ref: str) -> dict[str, int]:
        return {}

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        return None

    def blockers(self) -> list[str]:
        return []

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        return {}
