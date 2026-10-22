"""Gate tightenings that landed with curriculum packs.

1. Readability: an empty measured text is a BLOCKER, never a vacuous pass.
2. Accessibility: a recorded-audio ref must resolve through the ``AudioAssetResolver`` port (the
   media registry in production); a ref to a non-existent asset is a BLOCKER. The synthetic
   fixture refs resolve only outside production wiring.
"""

from __future__ import annotations

import pytest

from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    SqlMediaAudioResolver,
    studio_audio_resolver,
    unit_of_work,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence.models import MediaAssetRow
from taleem_core.contexts.curriculum_studio.application.repository import (
    InMemoryLessonRepository,
    RecordingPublishPort,
)
from taleem_core.contexts.curriculum_studio.application.service import (
    CurriculumStudioService,
    StudioError,
)
from taleem_core.contexts.curriculum_studio.domain import validation
from taleem_core.contexts.curriculum_studio.domain.audio import (
    SYNTHETIC_FIXTURE_AUDIO,
    AnyAudioResolver,
    known_audio,
)
from taleem_core.contexts.curriculum_studio.domain.content import Locale
from taleem_core.contexts.curriculum_studio.domain.quality import Gate, Severity
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.vertical_slice.fractions_lesson import build_fractions_lesson
from tests.studio_helpers import make_valid_lesson

NO_ASSETS = known_audio(())


def _gate(result: validation.ValidationResult, gate: Gate) -> list[str]:
    gr = next(g for g in result.gate_results if g.gate is gate)
    assert all(f.severity is Severity.BLOCKER for f in gr.findings)
    return [f.message for f in gr.findings]


# ---- readability --------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "۔", " . ! "])
def test_empty_readability_text_is_a_blocker(text: str) -> None:
    lesson = make_valid_lesson()
    lesson.student_explanation.text[Locale.UR] = text
    result = validation.validate(lesson)
    assert not result.ok
    assert "no Urdu student_explanation to measure" in _gate(result, Gate.READABILITY)


def test_missing_readability_locale_is_a_blocker() -> None:
    lesson = make_valid_lesson()
    del lesson.student_explanation.text[Locale.UR]
    assert "no Urdu student_explanation to measure" in _gate(
        validation.validate(lesson), Gate.READABILITY
    )


def test_every_readability_locale_must_have_text() -> None:
    lesson = make_valid_lesson()
    lesson.metadata.instructional_locales = [Locale.EN]  # PK-NCP: measured in Urdu and English
    lesson.student_explanation.text[Locale.EN] = ""
    assert _gate(validation.validate(lesson), Gate.READABILITY) == [
        "no English student_explanation to measure"
    ]


# ---- audio resolution ---------------------------------------------------------------------


def test_unresolvable_audio_ref_is_a_blocker() -> None:
    lesson = make_valid_lesson()
    result = validation.validate(lesson, audio_assets=NO_ASSETS)
    assert not result.ok
    assert _gate(result, Gate.ACCESSIBILITY) == [
        "student_explanation Urdu audio 'audio/ur.mp3' is not a registered audio asset"
    ]
    assert validation.validate(lesson, audio_assets=known_audio({"audio/ur.mp3"})).ok


def test_default_resolver_knows_only_the_synthetic_fixture_refs() -> None:
    assert validation.validate(make_valid_lesson()).ok  # fixture refs resolve by default
    lesson = make_valid_lesson()
    lesson.student_explanation.audio_ref[Locale.UR] = "audio/ur/g4-real-lesson.mp3"
    assert (
        "is not a registered audio asset"
        in _gate(validation.validate(lesson), Gate.ACCESSIBILITY)[0]
    )
    assert SYNTHETIC_FIXTURE_AUDIO.exists(" audio/ur.mp3 ")
    assert not SYNTHETIC_FIXTURE_AUDIO.exists("audio/ur/g4-real-lesson.mp3")


def test_each_audio_required_locale_is_resolved() -> None:
    lesson = make_valid_lesson()
    lesson.metadata.instructional_locales = [Locale.EN]  # PK-NCP: Urdu + English audio
    msgs = _gate(
        validation.validate(lesson, audio_assets=known_audio({"audio/ur.mp3"})),
        Gate.ACCESSIBILITY,
    )
    assert msgs == [
        "student_explanation English audio 'audio/en.mp3' is not a registered audio asset"
    ]


def test_service_uses_the_injected_resolver() -> None:
    svc = CurriculumStudioService(
        InMemoryLessonRepository(), RecordingPublishPort(), audio_assets=NO_ASSETS
    )
    svc.create(make_valid_lesson("A1"))
    assert not svc.validate("A1").ok
    with pytest.raises(StudioError, match="automated validation failed"):
        svc.submit("A1", actor_role="subject_author")


def test_vertical_slice_fixture_passes_only_outside_production_wiring() -> None:
    # The fractions fixture's refs are synthetic: no such recordings exist in the registry.
    lesson = build_fractions_lesson()
    empty_registry = NO_ASSETS
    prod = studio_audio_resolver(empty_registry, production=True)
    dev = studio_audio_resolver(empty_registry, production=False)
    assert prod is empty_registry
    assert isinstance(dev, AnyAudioResolver)
    assert (
        "is not a registered audio asset"
        in _gate(validation.validate(lesson, audio_assets=prod), Gate.ACCESSIBILITY)[0]
    )
    assert not _gate(validation.validate(lesson, audio_assets=dev), Gate.ACCESSIBILITY)


def _media(key: str, kind: str = "audio", scan: str = "clean") -> MediaAssetRow:
    return MediaAssetRow(
        id=uuid7(),
        kind=kind,
        storage_key=key,
        content_hash=f"sha256:{key}:{kind}:{scan}",
        mime="audio/mpeg",
        byte_size=1,
        license="authored-original",
        origin="authored",
        scan_status=scan,
        alt_text={},
    )


def test_media_registry_resolver() -> None:
    app = create_app(Settings(database_url=""))
    with unit_of_work(app.state.studio_session_factory) as uow:
        uow.session.add_all(
            [
                _media("audio/ur/clean.mp3"),
                _media("audio/ur/pending.mp3", scan="pending"),
                _media("audio/ur/flagged.mp3", scan="flagged"),
                _media("img/a.svg", kind="svg"),
            ]
        )
        uow.commit()
    with unit_of_work(app.state.studio_session_factory) as uow:
        resolver = uow.audio_assets
        assert isinstance(resolver, SqlMediaAudioResolver)
        assert resolver.exists("audio/ur/clean.mp3")
        assert resolver.exists("  audio/ur/clean.mp3 ")
        assert not resolver.exists("audio/ur/pending.mp3")  # not scanned clean
        assert not resolver.exists("audio/ur/flagged.mp3")
        assert not resolver.exists("img/a.svg")  # not audio
        assert not resolver.exists("audio/ur/missing.mp3")
        assert not resolver.exists("   ")

        lesson = make_valid_lesson()
        lesson.student_explanation.audio_ref[Locale.UR] = "audio/ur/clean.mp3"
        assert validation.validate(lesson, audio_assets=resolver).ok
        assert not validation.validate(make_valid_lesson(), audio_assets=resolver).ok
