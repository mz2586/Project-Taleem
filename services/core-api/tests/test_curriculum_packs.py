"""Curriculum packs — market rules as validated data (master scope §20.2, §24; global scope §D).

Covers: pack-file validation, PK-NCP equivalence with the former hard-coded rules (asserted against
literal values), a synthetic test-only English pack, unknown-pack/locale blockers, the open Locale
type, persistence compatibility for pre-pack lessons, and the pack listing API.
"""

from __future__ import annotations

import copy
import dataclasses
import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import mapper, serde
from taleem_core.contexts.curriculum_studio.domain import hierarchy, validation
from taleem_core.contexts.curriculum_studio.domain.content import Locale, LocalizedText
from taleem_core.contexts.curriculum_studio.domain.lesson import Lesson, Metadata
from taleem_core.contexts.curriculum_studio.domain.packs import (
    DEFAULT_PACK_ID,
    CurriculumPack,
    InstructionRules,
    PackError,
    PackRegistry,
    default_pack,
    default_registry,
    load_pack_file,
    parse_pack,
    shipped_packs_dir,
)
from taleem_core.contexts.curriculum_studio.domain.quality import Gate, Severity
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.vertical_slice.fractions_lesson import build_fractions_lesson
from tests.studio_helpers import make_valid_lesson

# ---- literal expectations: the rules exactly as they were hard-coded before packs -------------

OLD_GRADE_KEYS = ("KG", "G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9", "G10")
_G1_3 = ("urdu", "english", "math", "gk")
_G4_5 = ("urdu", "english", "math", "science", "social_studies", "islamiat_ethics")
_G6_8 = (*_G4_5, "computer")
_G9_10 = (
    "urdu",
    "english",
    "math",
    "physics",
    "chemistry",
    "biology",
    "pak_studies",
    "islamiat_ethics",
)
OLD_SUBJECT_ROSTER = {
    "KG": ("ece",),
    "G1": _G1_3,
    "G2": _G1_3,
    "G3": (*_G1_3, "islamiat_ethics"),
    "G4": _G4_5,
    "G5": _G4_5,
    "G6": _G6_8,
    "G7": _G6_8,
    "G8": _G6_8,
    "G9": _G9_10,
    "G10": _G9_10,
}
OLD_READABILITY_MAX_WORDS = {
    "KG": 8,
    "G1": 8,
    "G2": 8,
    "G3": 8,
    "G4": 12,
    "G5": 12,
    "G6": 16,
    "G7": 16,
    "G8": 16,
    "G9": 20,
    "G10": 20,
}
# Content hashes computed on main (2c6da83) before curriculum packs existed.
OLD_VALID_LESSON_HASH = "sha256:3925055fb0066ab1b72431e97877308d8ded740acde76575c636030685fdc4b1"
OLD_FRACTIONS_HASH = "sha256:ce1a6c726a9210c36b2a39562f20a464c8148a3e7c37e73521734f738085c1f9"


def _shipped_pk_ncp() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (shipped_packs_dir() / "pk-ncp.json").read_text(encoding="utf-8")
    )
    return data


# ---- a synthetic, TEST-ONLY pack (never shipped): English-only, LTR -------------------------


def _synthetic_en_pack() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pack_id": "TEST-EN",
        "version": "0.0.1-test",
        "country": "ZZ",  # ISO user-assigned code: deliberately not a real country
        "education_system": "Synthetic test system (not a real curriculum)",
        "grades": ["Y1", "Y2"],
        "subject_roster": {"Y1": ["math"], "Y2": ["math", "science"]},
        "academic_calendar": {
            "year_start_month": 9,
            "terms": [{"key": "t1", "name": "Term 1"}, {"key": "t2", "name": "Term 2"}],
        },
        "language_of_instruction": "en",
        "default_numeral_system": "western",
        "locales": {"en": {"name": "English", "direction": "ltr"}},
        "instructional_locales": {
            "en": {
                "required_locales": ["en"],
                "audio_required_locales": ["en"],
                "readability_locales": ["en"],
            }
        },
        "readability": {
            "en": {"max_words_per_sentence": {"Y1": 8, "Y2": 10}, "default_max_words": 10}
        },
    }


def _registry_with_test_pack() -> PackRegistry:
    return PackRegistry([default_pack(), parse_pack(_synthetic_en_pack(), "test")])


def _strip_locale(obj: Any, loc: Locale) -> None:
    """Remove every text + audio entry for ``loc`` throughout a lesson (in place)."""
    if isinstance(obj, LocalizedText):
        obj.text.pop(loc, None)
        obj.audio_ref.pop(loc, None)
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            _strip_locale(getattr(obj, f.name), loc)
    elif isinstance(obj, list):
        for item in obj:
            _strip_locale(item, loc)


def _english_only_lesson(pack_id: str, grade: str) -> Lesson:
    lesson = make_valid_lesson("EN1")
    _strip_locale(lesson, Locale.UR)
    lesson.metadata = Metadata(
        grade_key=grade,
        subject_key="math",
        languages=[Locale.EN],
        author_role="subject_author",
        curriculum_pack=pack_id,
    )
    return lesson


def _messages(result: validation.ValidationResult) -> list[str]:
    msgs = [f.message for f in result.structural]
    for g in result.gate_results:
        msgs += [f.message for f in g.findings]
    return msgs


def _gate(result: validation.ValidationResult, gate: Gate) -> Any:
    return next(g for g in result.gate_results if g.gate is gate)


# =============================================================================================
# Shipped registry + PK-NCP equivalence
# =============================================================================================


def test_only_pk_ncp_is_shipped() -> None:
    # No second real country's pack may ship until it is validated.
    assert default_registry().ids() == ["PK-NCP"]
    assert [p.name for p in sorted(shipped_packs_dir().glob("*.json"))] == ["pk-ncp.json"]


def test_pk_ncp_reproduces_the_former_constants_exactly() -> None:
    pack = default_pack()
    assert pack.pack_id == DEFAULT_PACK_ID == "PK-NCP"
    assert pack.country == "PK"
    assert pack.version == "1.0.0"
    assert pack.grade_keys == OLD_GRADE_KEYS
    assert dict(pack.subject_roster) == OLD_SUBJECT_ROSTER
    assert list(pack.subject_roster) == list(OLD_GRADE_KEYS)
    assert pack.language_of_instruction == "ur"
    assert pack.default_numeral_system == "western"
    assert pack.direction_for("ur") == "rtl"
    assert pack.direction_for("en") == "ltr"
    assert list(pack.instructional_locales) == ["ur", "en"]
    ur_limits = pack.readability[Locale.UR]
    assert dict(ur_limits.max_words) == OLD_READABILITY_MAX_WORDS
    assert ur_limits.default_max_words == 20
    assert ur_limits.for_grade("G99") == 20  # the former `.get(grade, 20)` fallback
    # Default (Urdu) instruction == the former hard-coded gates: Urdu + English everywhere,
    # recorded Urdu audio, readability on the Urdu text.
    assert pack.rules_for([]) == InstructionRules(
        required_locales=(Locale.UR, Locale.EN),
        audio_required_locales=(Locale.UR,),
        readability_locales=(Locale.UR,),
    )
    assert pack.rules_for([]) == pack.rules_for([Locale.UR])


def test_pk_ncp_english_instruction_is_never_weaker_than_urdu() -> None:
    pack = default_pack()
    ur = pack.rules_for([Locale.UR])
    en = pack.rules_for([Locale.EN])
    for attr in ("required_locales", "audio_required_locales", "readability_locales"):
        assert set(getattr(ur, attr)) <= set(getattr(en, attr)), attr
    assert dict(pack.readability[Locale.EN].max_words) == OLD_READABILITY_MAX_WORDS


def test_multiple_instructional_locales_union_rules() -> None:
    both = default_pack().rules_for([Locale.UR, Locale.EN])
    assert both.required_locales == (Locale.UR, Locale.EN)
    assert both.audio_required_locales == (Locale.UR, Locale.EN)
    assert both.readability_locales == (Locale.UR, Locale.EN)


def test_compat_helpers_and_constants_delegate_to_default_pack() -> None:
    assert hierarchy.GRADE_KEYS == OLD_GRADE_KEYS
    assert hierarchy.SUBJECT_ROSTER == OLD_SUBJECT_ROSTER
    assert validation.READABILITY_MAX_WORDS == OLD_READABILITY_MAX_WORDS
    for grade, subjects in OLD_SUBJECT_ROSTER.items():
        assert hierarchy.subjects_for(grade) == subjects
        for s in subjects:
            assert hierarchy.is_valid_grade_subject(grade, s)
    assert hierarchy.subjects_for("G11") == ()
    assert not hierarchy.is_valid_grade_subject("G1", "physics")
    with pytest.raises(AttributeError):
        _ = hierarchy.NOPE  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        _ = validation.NOPE  # type: ignore[attr-defined]


def test_content_hash_of_pk_ncp_lessons_is_unchanged() -> None:
    # Published-version hashes stay comparable: default pack fields are not hashed.
    assert make_valid_lesson().content_hash() == OLD_VALID_LESSON_HASH
    assert build_fractions_lesson().content_hash() == OLD_FRACTIONS_HASH
    other = make_valid_lesson()
    other.metadata.curriculum_pack = "TEST-EN"
    assert other.content_hash() != OLD_VALID_LESSON_HASH
    other = make_valid_lesson()
    other.metadata.instructional_locales = [Locale.EN]
    assert other.content_hash() != OLD_VALID_LESSON_HASH


def test_pk_ncp_messages_are_unchanged() -> None:
    lesson = make_valid_lesson()
    lesson.title.text.pop(Locale.EN)
    lesson.student_explanation.audio_ref = {}
    lesson.student_explanation.text[Locale.UR] = " ".join(["لفظ"] * 20) + "۔"
    msgs = _messages(validation.validate(lesson))
    assert "title requires Urdu + English" in msgs
    assert "student_explanation missing recorded Urdu audio (mandatory)" in msgs
    assert "avg sentence length 20.0 exceeds grade max 8" in msgs


def test_pk_ncp_english_instruction_requires_english_audio_too() -> None:
    lesson = make_valid_lesson()
    lesson.metadata.instructional_locales = [Locale.EN]
    assert validation.validate(lesson).ok
    lesson.student_explanation.audio_ref.pop(Locale.EN)
    result = validation.validate(lesson)
    assert not result.ok
    assert "student_explanation missing recorded English audio (mandatory)" in _messages(result)
    lesson.student_explanation.audio_ref = {Locale.EN: "audio/en.mp3"}  # Urdu still mandatory
    assert "student_explanation missing recorded Urdu audio (mandatory)" in _messages(
        validation.validate(lesson)
    )
    lesson = make_valid_lesson()
    lesson.metadata.instructional_locales = [Locale.EN]
    lesson.student_explanation.text[Locale.EN] = " ".join(["word"] * 12) + "."
    assert "avg sentence length 12.0 exceeds grade max 8 (English)" in _messages(
        validation.validate(lesson)
    )


# =============================================================================================
# Synthetic second pack (test-only)
# =============================================================================================


def test_english_only_lesson_passes_under_english_pack_and_fails_under_pk_ncp() -> None:
    registry = _registry_with_test_pack()
    under_test_pack = validation.validate(_english_only_lesson("TEST-EN", "Y1"), registry)
    assert under_test_pack.ok, _messages(under_test_pack)

    under_pk = validation.validate(_english_only_lesson("PK-NCP", "G1"), registry)
    assert not under_pk.ok
    msgs = _messages(under_pk)
    assert "title requires Urdu + English" in msgs
    assert "student_explanation missing recorded Urdu audio (mandatory)" in msgs


def test_grade_subject_alignment_comes_from_the_lessons_pack() -> None:
    registry = _registry_with_test_pack()
    lesson = _english_only_lesson("TEST-EN", "G1")  # a PK-NCP grade, not in TEST-EN
    assert not _gate(validation.validate(lesson, registry), Gate.CURRICULUM_ALIGNMENT).passed
    lesson.metadata.grade_key, lesson.metadata.subject_key = "Y2", "science"
    assert _gate(validation.validate(lesson, registry), Gate.CURRICULUM_ALIGNMENT).passed


def test_readability_uses_the_packs_locale_and_limits() -> None:
    registry = _registry_with_test_pack()
    lesson = _english_only_lesson("TEST-EN", "Y2")
    lesson.student_explanation.text[Locale.EN] = " ".join(["word"] * 10) + "."
    assert _gate(validation.validate(lesson, registry), Gate.READABILITY).passed  # Y2 max 10
    lesson.metadata.grade_key = "Y1"  # Y1 max 8
    assert not _gate(validation.validate(lesson, registry), Gate.READABILITY).passed


def test_language_not_declared_by_pack_is_blocked() -> None:
    registry = _registry_with_test_pack()
    lesson = _english_only_lesson("TEST-EN", "Y1")
    lesson.metadata.languages = [Locale.EN, Locale.UR]
    result = validation.validate(lesson, registry)
    assert not _gate(result, Gate.CURRICULUM_ALIGNMENT).passed
    assert any("not declared by curriculum pack TEST-EN" in m for m in _messages(result))


# =============================================================================================
# Unknown pack / instructional locale: BLOCKER, never a silent pass
# =============================================================================================


def test_unknown_pack_is_a_blocker_in_every_pack_dependent_check() -> None:
    lesson = make_valid_lesson()
    lesson.metadata.curriculum_pack = "XX-NOPE"
    result = validation.validate(lesson)
    assert not result.ok
    assert any(
        f.severity is Severity.BLOCKER and "unknown curriculum pack 'XX-NOPE'" in f.message
        for f in result.structural
    )
    for gate in (Gate.CURRICULUM_ALIGNMENT, Gate.ACCESSIBILITY, Gate.READABILITY):
        gr = _gate(result, gate)
        assert not gr.passed, gate
        assert all(f.severity is Severity.BLOCKER for f in gr.findings)


def test_unknown_instructional_locale_is_a_blocker() -> None:
    lesson = make_valid_lesson()
    lesson.metadata.instructional_locales = [Locale("fr")]
    result = validation.validate(lesson)
    assert not result.ok
    assert any("not offered by curriculum pack PK-NCP" in m for m in _messages(result))
    for gate in (Gate.CURRICULUM_ALIGNMENT, Gate.ACCESSIBILITY, Gate.READABILITY):
        assert not _gate(result, gate).passed


# =============================================================================================
# Pack-file validation
# =============================================================================================


def _mutate(path: str, value: Any) -> dict[str, Any]:
    data = copy.deepcopy(_shipped_pk_ncp())
    *parents, last = path.split(".")
    node: Any = data
    for p in parents:
        node = node[p]
    if value is _DELETE:
        del node[last]
    else:
        node[last] = value
    return data


_DELETE = object()


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        ("schema_version", 2, "unsupported schema_version"),
        ("pack_id", _DELETE, "missing required field 'pack_id'"),
        ("pack_id", "  ", "pack_id must be non-empty"),
        ("version", "", "version must be non-empty"),
        ("version", 1, "wrong type"),
        ("country", "PAK", "ISO 3166-1 alpha-2"),
        ("country", "pk", "ISO 3166-1 alpha-2"),
        ("education_system", " ", "education_system must be non-empty"),
        ("grades", [], "grades must not be empty"),
        ("grades", ["G1", "G1"], "duplicates"),
        ("subject_roster.G11", ["math"], "unknown grade 'G11'"),
        ("subject_roster.KG", _DELETE, "no entry for grade(s) ['KG']"),
        ("subject_roster.G1", ["math", ""], "non-empty strings"),
        ("academic_calendar.year_start_month", 13, "1-12"),
        ("academic_calendar.year_start_month", True, "wrong type"),
        ("academic_calendar.terms", [], "terms must not be empty"),
        ("academic_calendar.terms", ["x"], "must be an object"),
        (
            "academic_calendar.terms",
            [{"key": "a", "name": "A"}, {"key": "a", "name": "B"}],
            "duplicate keys",
        ),
        ("academic_calendar.notes", 5, "notes must be a string"),
        ("locales", {}, "locales must not be empty"),
        ("locales.ur", "Urdu", "must be an object"),
        ("locales.ur.direction", _DELETE, "missing its text direction"),
        ("locales.ur.direction", "ttb", "'ltr' or 'rtl'"),
        ("locales.ur.name", " ", "needs a name"),
        ("locales.UR!", {"name": "x", "direction": "ltr"}, "not a valid locale tag"),
        ("readability.fr", {"max_words_per_sentence": {}, "default_max_words": 1}, "'fr' not"),
        ("readability.ur", 3, "must be an object"),
        ("readability.ur.max_words_per_sentence.G11", 8, "unknown grade 'G11'"),
        ("readability.ur.max_words_per_sentence.KG", _DELETE, "no limit for grade(s) ['KG']"),
        ("readability.ur.max_words_per_sentence.KG", 0, "positive integer"),
        ("readability.ur.default_max_words", -1, "positive integer"),
        ("instructional_locales", {}, "instructional_locales must not be empty"),
        ("instructional_locales.fr", {}, "not declared in 'locales'"),
        ("instructional_locales.ur", [], "must be an object"),
        ("instructional_locales.ur.required_locales", ["en"], "must itself be required"),
        ("instructional_locales.ur.required_locales", ["ur", "fr"], "'fr' not declared"),
        ("instructional_locales.ur.audio_required_locales", ["fr"], "not declared"),
        ("instructional_locales.ur.readability_locales", [], "must not be empty"),
        ("instructional_locales.ur.required_locales", ["ur"], "'en' is not a required locale"),
        ("language_of_instruction", "fr", "is not instructional"),
        ("default_numeral_system", "roman", "default_numeral_system must be one of"),
    ],
)
def test_malformed_pack_is_rejected(path: str, value: Any, error: str) -> None:
    data = _mutate(path, value)
    if path == "instructional_locales.ur.required_locales" and value == ["ur"]:
        data["instructional_locales"]["ur"]["audio_required_locales"] = ["ur"]
        data["instructional_locales"]["ur"]["readability_locales"] = ["ur", "en"]
    with pytest.raises(PackError, match=None) as exc:
        parse_pack(data, "pk-ncp.json")
    assert error in str(exc.value)


def test_readability_locale_without_limits_is_rejected() -> None:
    data = _shipped_pk_ncp()
    del data["readability"]["en"]
    with pytest.raises(PackError, match="no readability limits for locale"):
        parse_pack(data)


def test_pack_must_be_an_object() -> None:
    with pytest.raises(PackError, match="must be a JSON object"):
        parse_pack([1, 2])


def test_duplicate_pack_ids_and_unknown_require() -> None:
    pack = default_pack()
    with pytest.raises(PackError, match="duplicate curriculum pack id"):
        PackRegistry([pack, pack])
    with pytest.raises(PackError, match="unknown curriculum pack"):
        PackRegistry([pack]).require("NOPE")


def test_registry_loads_a_directory_and_rejects_bad_files(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text(json.dumps(_synthetic_en_pack()), encoding="utf-8")
    reg = PackRegistry.from_directory(tmp_path)
    assert reg.ids() == ["TEST-EN"]
    assert reg.is_known_locale("en") and not reg.is_known_locale("ur")
    pack = reg.require("TEST-EN")
    assert isinstance(pack, CurriculumPack)
    assert pack.summary()["locales"] == [{"tag": "en", "name": "English", "direction": "ltr"}]
    assert pack.locale_name("de") == "de"
    (tmp_path / "b.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(PackError, match="invalid JSON"):
        PackRegistry.from_directory(tmp_path)
    with pytest.raises(PackError, match="invalid JSON"):
        load_pack_file(tmp_path / "b.json")


# =============================================================================================
# Open Locale type
# =============================================================================================


def test_locale_is_an_open_validated_str() -> None:
    assert Locale("ur") == Locale.UR == "ur"
    assert hash(Locale.EN) == hash("en")
    assert {Locale.UR: "x"}["ur"] == "x"
    assert Locale.UR.value == "ur" and type(Locale.UR.value) is str
    assert Locale(Locale.EN) is Locale.EN
    assert Locale("en-GB") == "en-GB"
    assert repr(Locale.UR) == "'ur'"
    for bad in ("", "EN", "e", "english-language-x", "ur_PK"):
        with pytest.raises(ValueError, match="not a valid locale tag"):
            Locale(bad)


# =============================================================================================
# Persistence compatibility (no migration: the pack lives in the JSON body)
# =============================================================================================


def test_pre_pack_body_loads_as_pk_ncp_and_round_trips() -> None:
    lesson = make_valid_lesson()
    body = mapper.to_body(lesson)
    assert body["metadata"]["curriculum_pack"] == "PK-NCP"
    json.dumps(body)  # JSON-able (Locale keys become plain strings)
    assert all(type(k) is str for k in body["title"]["text"])
    legacy = copy.deepcopy(body)
    del legacy["metadata"]["curriculum_pack"]  # a row written before packs existed
    del legacy["metadata"]["instructional_locales"]
    loaded = serde.build(Lesson, legacy)
    assert loaded.metadata.curriculum_pack == "PK-NCP"
    assert loaded.metadata.instructional_locales == []
    assert loaded == lesson
    assert loaded.content_hash() == OLD_VALID_LESSON_HASH
    assert all(isinstance(k, Locale) for k in loaded.title.text)
    assert validation.validate(loaded).ok


def test_non_default_pack_round_trips_through_body() -> None:
    lesson = make_valid_lesson()
    lesson.metadata.curriculum_pack = "TEST-EN"
    lesson.metadata.instructional_locales = [Locale.EN]
    loaded = serde.build(Lesson, json.loads(json.dumps(mapper.to_body(lesson))))
    assert loaded == lesson
    assert loaded.metadata.instructional_locales == [Locale.EN]
    assert isinstance(loaded.metadata.instructional_locales[0], Locale)


# =============================================================================================
# API
# =============================================================================================

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)


def _auth(role: str = "subject_author") -> dict[str, str]:
    token = sign_hs256({"sub": "u1", "role": role, "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


def test_api_lists_packs() -> None:
    c = TestClient(create_app(Settings(database_url="")))  # private in-memory store
    assert c.get("/v1/studio/curriculum-packs").status_code == 401
    r = c.get("/v1/studio/curriculum-packs", headers=_auth())
    assert r.status_code == 200
    assert r.json() == {
        "packs": [
            {
                "pack_id": "PK-NCP",
                "version": "1.0.0",
                "country": "PK",
                "education_system": "Pakistan National Curriculum (NCP)",
                "language_of_instruction": "ur",
                "instructional_locales": ["ur", "en"],
                "locales": [
                    {"tag": "ur", "name": "Urdu", "direction": "rtl"},
                    {"tag": "en", "name": "English", "direction": "ltr"},
                ],
            }
        ]
    }


def test_api_hierarchy_is_served_from_the_registry() -> None:
    # A private in-memory store: no persisted hierarchy, so the pack roster is served.
    c = TestClient(create_app(Settings(database_url="")))
    r = c.get("/v1/studio/hierarchy", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "pack" and body["tree"] == []
    assert body["system"] == "PK-NCP"
    assert body["grades"] == list(OLD_GRADE_KEYS)
    assert body["subjects_by_grade"] == {g: list(s) for g, s in OLD_SUBJECT_ROSTER.items()}
    assert c.get("/v1/studio/hierarchy?pack=PK-NCP", headers=_auth()).json() == body
    assert c.get("/v1/studio/hierarchy?pack=XX-NOPE", headers=_auth()).status_code == 404


def test_api_draft_declares_pack_and_unknown_pack_blocks_validation() -> None:
    c = TestClient(create_app(Settings(database_url="")))  # private in-memory store
    base = {
        "title_ur": "گنتی",
        "title_en": "Counting",
        "grade": "G1",
        "subject": "math",
        "learning_outcomes": ["MATH-G1-N-01"],
    }
    r = c.post("/v1/studio/lessons", json={**base, "lesson_id": "P1"}, headers=_auth())
    assert r.status_code == 201
    assert r.json()["curriculum_pack"] == "PK-NCP"
    assert r.json()["instructional_locales"] == []
    assert r.json()["title"] == {"ur": "گنتی", "en": "Counting"}

    r = c.post(
        "/v1/studio/lessons",
        json={**base, "lesson_id": "P2", "curriculum_pack": "XX-NOPE"},
        headers=_auth(),
    )
    assert r.status_code == 201
    v = c.post("/v1/studio/lessons/P2:validate", headers=_auth()).json()
    assert not v["ok"]
    assert any("unknown curriculum pack 'XX-NOPE'" in f["message"] for f in v["structural"])

    r = c.post(
        "/v1/studio/lessons",
        json={**base, "lesson_id": "P3", "instructional_locales": ["Not A Tag"]},
        headers=_auth(),
    )
    assert r.status_code == 422
