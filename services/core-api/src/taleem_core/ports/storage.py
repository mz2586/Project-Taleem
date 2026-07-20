"""Object-storage abstraction (pure-stdlib) with an in-memory adapter.

S3-compatible object storage is the production adapter (docs/34-media, docs/36-infrastructure).
The in-memory adapter is for tests/local only. NO live child media is handled in M1.
"""

from __future__ import annotations

import hashlib
from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> str: ...
    def get(self, key: str) -> bytes | None: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


class InMemoryObjectStore:
    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> str:
        self._store[key] = data
        return hashlib.sha256(data).hexdigest()  # content hash (integrity, docs/34 §6)

    def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    def exists(self, key: str) -> bool:
        return key in self._store

    def delete(self, key: str) -> None:
        self._store.pop(key, None)
