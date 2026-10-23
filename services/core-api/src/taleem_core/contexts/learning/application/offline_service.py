"""Offline package application service — Phase 6.2A.

Serves content-hashed offline lesson packages built from currently-published curriculum. Curriculum
content is C0 (no child data); packages are derived on the fly from the ``CurriculumReadModel`` — no
new tables, no child-data surface. The client uses the manifest index to decide what to download and
the per-lesson package to render + cache offline (OFFLINE_ARCHITECTURE.md §3, §5).

Built packages are cached per lesson. Building one means projecting the lesson, hashing its content
and Ed25519-signing the manifest (the pure-Python signer is the bulk of the cost), and none of that
changes until the lesson does. An entry is keyed by the lesson's **fingerprint** — read fresh from
the curriculum store on every request, a row-columns-only query whose value changes on every write
to the lesson (publish, rollback, edit) — and by the signing key. So:

- a publish or rollback changes the fingerprint and the next request rebuilds from the new content;
  a lesson that is no longer published is dropped;
- a different signing key (id or public key) never reuses a signature made by another key;
- nothing is served that the current published lesson would not produce: the cached content hash
  is the hash of the content built from the lesson at that fingerprint.

``created_at_ms`` is stamped per response exactly as before (it is not part of the signed payload).
Without a fingerprint source (``PublishedLessonFingerprints``) the service builds on every call.
"""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable
from dataclasses import dataclass

from ..domain.curriculum_view import LessonView
from ..domain.offline_package import (
    OfflinePackage,
    PackageSigner,
    build_package,
)
from .ports import CurriculumReadModel, PublishedLessonFingerprints


@dataclass(frozen=True)
class _CacheEntry:
    fingerprint: str
    signer_key: tuple[str, str]
    package: OfflinePackage


def _matches(entry: _CacheEntry | None, fingerprint: str, signer_key: tuple[str, str]) -> bool:
    return entry is not None and entry.fingerprint == fingerprint and entry.signer_key == signer_key


class OfflinePackageService:
    """Builds offline packages from published lessons. Pure over the read model + injected clock.

    An optional ``signer`` Ed25519-signs every manifest (Phase 6.2C-1); when absent, manifests are
    unsigned (backward-compatible). The signer's public key is exposed via ``signing_keys`` so a
    client can pin it.
    """

    def __init__(
        self,
        curriculum: CurriculumReadModel,
        now: Callable[[], float],
        signer: PackageSigner | None = None,
    ) -> None:
        self._curriculum = curriculum
        self._now = now
        self._signer = signer
        self._fingerprints: PublishedLessonFingerprints | None = (
            curriculum if isinstance(curriculum, PublishedLessonFingerprints) else None
        )
        self._cache: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()
        self.builds = 0  # packages built (cache misses); observable in tests

    def _now_ms(self) -> int:
        return int(self._now() * 1000)

    def _signer_key(self) -> tuple[str, str]:
        if self._signer is None:
            return ("", "")
        return (self._signer.key_id, self._signer.public_key_hex)

    def _build(self, view: LessonView) -> OfflinePackage:
        self.builds += 1
        return build_package(view, now_ms=self._now_ms(), signer=self._signer)

    def _stamped(self, package: OfflinePackage, now_ms: int) -> OfflinePackage:
        manifest = dataclasses.replace(package.manifest, created_at_ms=now_ms)
        return OfflinePackage(manifest=manifest, content=package.content)

    def _current_packages(self, only: str | None = None) -> list[OfflinePackage] | None:
        """Packages for every published lesson (or just ``only``), served from the cache where the
        lesson's fingerprint and the signing key still match. None: no fingerprint source."""
        if self._fingerprints is None:
            return None
        fingerprints = self._fingerprints.published_fingerprints()
        ids = [lesson_id for lesson_id, _ in fingerprints]
        if len(set(ids)) != len(ids):
            return None  # ambiguous lesson ids: never guess which entry is which
        wanted = [(i, f) for i, f in fingerprints if only is None or i == only]
        signer_key = self._signer_key()
        with self._lock:
            cached = {i: self._cache.get(i) for i, _ in wanted}
        missing = {i for i, f in wanted if not _matches(cached[i], f, signer_key)}
        if missing:
            # Read the lessons after their fingerprints: the content is at least as new as the
            # fingerprint it is filed under, so an entry can never be older than its key.
            views = {v.lesson_id: v for v in self._curriculum.published_lessons()}
            for i, f in wanted:
                if i not in missing:
                    continue
                view = views.get(i)
                if view is None:
                    return None  # changed under us (e.g. unpublished meanwhile): build uncached
                cached[i] = _CacheEntry(f, signer_key, self._build(view))
        with self._lock:
            for i, _ in wanted:
                entry = cached[i]
                if entry is not None:
                    self._cache[i] = entry
            if only is None:  # drop lessons that are no longer published
                current = set(ids)
                for stale in [k for k in self._cache if k not in current]:
                    del self._cache[stale]
        out: list[OfflinePackage] = []
        for i, _ in wanted:
            entry = cached[i]
            if entry is not None:
                out.append(entry.package)
        return out

    def list_packages(self) -> dict[str, object]:
        """Index of available packages (manifests only) for every published lesson."""
        now_ms = self._now_ms()
        packages = self._current_packages()
        if packages is None:
            packages = [self._build(view) for view in self._curriculum.published_lessons()]
        return {"packages": [self._stamped(p, now_ms).manifest.to_dict() for p in packages]}

    def get_package(self, lesson_id: str) -> OfflinePackage | None:
        """The full package (manifest + child-safe content) for one published lesson, or None."""
        now_ms = self._now_ms()
        packages = self._current_packages(only=lesson_id)
        if packages is None:
            for view in self._curriculum.published_lessons():
                if view.lesson_id == lesson_id:
                    return self._stamped(self._build(view), now_ms)
            return None
        return self._stamped(packages[0], now_ms) if packages else None

    def signing_keys(self) -> dict[str, object]:
        """Public signing key(s) a client pins to verify manifests (public keys are not secret)."""
        keys: list[dict[str, str]] = []
        if self._signer is not None:
            keys.append(
                {
                    "key_id": self._signer.key_id,
                    "algorithm": "Ed25519",
                    "public_key_hex": self._signer.public_key_hex,
                }
            )
        return {"keys": keys}
