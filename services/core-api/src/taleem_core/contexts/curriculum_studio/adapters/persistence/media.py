"""Media-registry adapter for the ``AudioAssetResolver`` port.

A recorded-audio ref resolves iff the content-addressed media registry (``media_asset``) holds an
``audio`` asset stored under that key whose malware/content scan is ``clean``. Pending or flagged
assets do not count: the gate certifies audio a child can actually be served.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.audio import SYNTHETIC_FIXTURE_AUDIO, AnyAudioResolver, AudioAssetResolver
from .models import MediaAssetRow


class SqlMediaAudioResolver:
    def __init__(self, session: Session) -> None:
        self._session = session

    def exists(self, ref: str) -> bool:
        key = ref.strip()
        if not key:
            return False
        row = self._session.execute(
            select(MediaAssetRow.id)
            .where(
                MediaAssetRow.storage_key == key,
                MediaAssetRow.kind == "audio",
                MediaAssetRow.scan_status == "clean",
            )
            .limit(1)
        ).scalar_one_or_none()
        return row is not None


def studio_audio_resolver(registry: AudioAssetResolver, *, production: bool) -> AudioAssetResolver:
    """The composition root's audio policy.

    Production resolves against the media registry only; other environments also accept the
    synthetic dev/test fixture refs.
    """
    if production:
        return registry
    return AnyAudioResolver((registry, SYNTHETIC_FIXTURE_AUDIO))
