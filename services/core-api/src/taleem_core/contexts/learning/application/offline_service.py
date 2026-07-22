"""Offline package application service — Phase 6.2A.

Serves content-hashed offline lesson packages built from currently-published curriculum. Curriculum
content is C0 (no child data); packages are derived on the fly from the ``CurriculumReadModel`` — no
new tables, no child-data surface. The client uses the manifest index to decide what to download and
the per-lesson package to render + cache offline (OFFLINE_ARCHITECTURE.md §3, §5).
"""

from __future__ import annotations

from collections.abc import Callable

from ..domain.offline_package import (
    OfflinePackage,
    PackageSigner,
    build_manifest,
    build_package,
)
from .ports import CurriculumReadModel


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

    def _now_ms(self) -> int:
        return int(self._now() * 1000)

    def list_packages(self) -> dict[str, object]:
        """Index of available packages (manifests only) for every published lesson."""
        now_ms = self._now_ms()
        manifests = [
            build_manifest(view, now_ms=now_ms, signer=self._signer).to_dict()
            for view in self._curriculum.published_lessons()
        ]
        return {"packages": manifests}

    def get_package(self, lesson_id: str) -> OfflinePackage | None:
        """The full package (manifest + child-safe content) for one published lesson, or None."""
        now_ms = self._now_ms()
        for view in self._curriculum.published_lessons():
            if view.lesson_id == lesson_id:
                return build_package(view, now_ms=now_ms, signer=self._signer)
        return None

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
