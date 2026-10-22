"""Audio-asset resolution port (pure-stdlib).

The accessibility gate requires recorded audio for the pack's audio-required locales. A non-empty
``audio_ref`` string is not evidence that the recording exists: the gate resolves every ref
through an ``AudioAssetResolver`` and an unresolvable ref is a BLOCKER.

- Production wiring resolves against the media registry only (the SQL adapter,
  ``adapters/persistence/media.py``).
- ``SYNTHETIC_FIXTURE_AUDIO`` holds the refs used by the synthetic dev/test fixture lessons
  (``tests/studio_helpers.py``, ``vertical_slice/fractions_lesson.py``). They name no real
  recording; the composition root accepts them only outside production, and they are the default
  when a caller supplies no resolver, so a real-looking ref never passes without a real registry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


class AudioAssetResolver(Protocol):
    def exists(self, ref: str) -> bool:
        """True iff ``ref`` names a registered, usable recorded-audio asset."""
        ...


@dataclass(frozen=True)
class KnownAudioAssets:
    """A resolver over a fixed set of asset refs (tests, dev fixtures)."""

    refs: frozenset[str]

    def exists(self, ref: str) -> bool:
        return ref.strip() in self.refs


@dataclass(frozen=True)
class AnyAudioResolver:
    """Resolves a ref if any of the given resolvers does."""

    resolvers: tuple[AudioAssetResolver, ...]

    def exists(self, ref: str) -> bool:
        return any(r.exists(ref) for r in self.resolvers)


def known_audio(refs: Iterable[str]) -> KnownAudioAssets:
    return KnownAudioAssets(frozenset(refs))


# Synthetic fixture refs — dev/test only (see module docstring). Never registered in production.
SYNTHETIC_FIXTURE_AUDIO = known_audio(
    {
        "audio/ur.mp3",
        "audio/en.mp3",
        "audio/ur/fractions.mp3",
        "audio/en/fractions.mp3",
    }
)
