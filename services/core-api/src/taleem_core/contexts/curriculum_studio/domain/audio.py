"""Audio-asset resolution port (pure-stdlib).

The accessibility gate requires recorded audio for the pack's audio-required locales. A non-empty
``audio_ref`` string is not evidence that the recording exists: the gate resolves every ref
through an ``AudioAssetResolver`` and an unresolvable ref is a BLOCKER.

- Production wiring resolves against the media registry only (the SQL adapter,
  ``adapters/persistence/media.py``).
- ``DEMO_PLACEHOLDER_AUDIO`` accepts ``demo-placeholder/…`` refs. ``validation.validate`` adds it
  **only** for a lesson whose ``metadata.audience`` is ``demo`` — in every environment, production
  included (DEMO_COHORT_CONTRACT §3) — and refuses such a ref on any other lesson, whatever the
  registry says.
- ``SYNTHETIC_FIXTURE_AUDIO`` holds the refs used by the synthetic dev/test fixture lessons
  (``tests/studio_helpers.py``, ``vertical_slice/fractions_lesson.py``). They name no real
  recording; the composition root accepts them only outside production, and they are the default
  when a caller supplies no resolver, so a real-looking ref never passes without a real registry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

# Refs for demo-content assets that do not exist yet (diagrams, offline package ids, recorded
# audio). Valid only on a lesson whose audience is ``demo`` (DEMO_COHORT_CONTRACT §3).
DEMO_PLACEHOLDER_PREFIX = "demo-placeholder/"


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


def is_demo_placeholder(ref: str) -> bool:
    """True for an explicitly synthetic ``demo-placeholder/…`` ref (no real asset behind it)."""
    key = ref.strip()
    return key.startswith(DEMO_PLACEHOLDER_PREFIX) and len(key) > len(DEMO_PLACEHOLDER_PREFIX)


@dataclass(frozen=True)
class DemoPlaceholderAudio:
    """Resolves only ``demo-placeholder/<something>`` refs. Used for demo-audience lessons only."""

    def exists(self, ref: str) -> bool:
        return is_demo_placeholder(ref)


@dataclass(frozen=True)
class RefusingDemoPlaceholders:
    """Wraps a resolver so a ``demo-placeholder/`` ref never resolves (every non-demo lesson)."""

    inner: AudioAssetResolver

    def exists(self, ref: str) -> bool:
        return not ref.strip().startswith(DEMO_PLACEHOLDER_PREFIX) and self.inner.exists(ref)


DEMO_PLACEHOLDER_AUDIO = DemoPlaceholderAudio()


def resolver_for_audience(audience: str, resolver: AudioAssetResolver) -> AudioAssetResolver:
    """The resolver a lesson of ``audience`` is validated with (DEMO_COHORT_CONTRACT §3)."""
    if audience == "demo":
        return AnyAudioResolver((RefusingDemoPlaceholders(resolver), DEMO_PLACEHOLDER_AUDIO))
    return RefusingDemoPlaceholders(resolver)
