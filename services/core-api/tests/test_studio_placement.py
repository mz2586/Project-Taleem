"""Lesson placement (chapter/topic) checked against the pack's stored hierarchy.

The curriculum_alignment gate blocks a non-empty placement that is not in the stored hierarchy and
reports an unplaced lesson as a non-blocking (MINOR) finding; PATCH accepts and validates
placement. PostgreSQL-gated variant where ``CS_DATABASE_URL`` is set.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    create_db_engine,
    create_session_factory,
    unit_of_work,
)
from taleem_core.contexts.curriculum_studio.application.repository import (
    InMemoryHierarchyRepository,
    InMemoryLessonRepository,
    RecordingPublishPort,
)
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain import validation
from taleem_core.contexts.curriculum_studio.domain.content import Locale, LocalizedText
from taleem_core.contexts.curriculum_studio.domain.hierarchy import (
    Chapter,
    EducationSystem,
    Grade,
    Subject,
    Topic,
    merge_hierarchy,
    placement_errors,
)
from taleem_core.contexts.curriculum_studio.domain.lesson import Lesson
from taleem_core.contexts.curriculum_studio.domain.packs import (
    PackRegistry,
    default_pack,
    parse_pack,
)
from taleem_core.contexts.curriculum_studio.domain.quality import Gate, Severity
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from tests.studio_helpers import make_valid_lesson

UNPLACED = "lesson is not placed in the curriculum hierarchy (no chapter/topic)"


def _t(en: str) -> LocalizedText:
    return LocalizedText(text={Locale.EN: en})


def _g1_math(key: str = "PK-NCP", grade: str = "G1") -> EducationSystem:
    return EducationSystem(
        system_id="",
        key=key,
        name="",
        grades=[
            Grade(
                grade_id="",
                key=grade,
                subjects=[
                    Subject(
                        subject_id="",
                        key="math",
                        title=_t("Mathematics"),
                        chapters=[
                            Chapter(
                                chapter_id="",
                                key="CH1",
                                title=_t("Numbers"),
                                topics=[Topic(topic_id="", key="T1", title=_t("Counting"))],
                            )
                        ],
                    )
                ],
            )
        ],
    )


def _placed(chapter: str = "CH1", topic: str = "T1", lesson_id: str = "P1") -> Lesson:
    lesson = make_valid_lesson(lesson_id)  # G1 math
    lesson.metadata.chapter_key, lesson.metadata.topic_key = chapter, topic
    return lesson


def _alignment(result: validation.ValidationResult) -> Any:
    return next(g for g in result.gate_results if g.gate is Gate.CURRICULUM_ALIGNMENT)


STORED = merge_hierarchy(None, _g1_math(), default_pack())


# ---- domain -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("chapter", "topic", "system", "error"),
    [
        ("", "", None, None),
        ("CH1", "T1", STORED, None),
        ("CH1", "", STORED, None),
        ("", "T1", STORED, "requires a chapter_key"),
        ("CH1", "T1", None, "no stored PK-NCP hierarchy"),
        ("CH9", "", STORED, "chapter 'CH9' is not in the stored PK-NCP hierarchy for G1/math"),
        ("CH1", "T9", STORED, "topic 'T9' is not in chapter 'CH1'"),
    ],
)
def test_placement_errors(
    chapter: str, topic: str, system: EducationSystem | None, error: str | None
) -> None:
    errors = placement_errors(
        system,
        pack_id="PK-NCP",
        grade_key="G1",
        subject_key="math",
        chapter_key=chapter,
        topic_key=topic,
    )
    if error is None:
        assert errors == []
    else:
        assert len(errors) == 1 and error in errors[0]


def test_placement_is_scoped_to_the_lessons_grade_and_subject() -> None:
    errors = placement_errors(
        STORED,
        pack_id="PK-NCP",
        grade_key="G2",
        subject_key="math",
        chapter_key="CH1",
        topic_key="",
    )
    assert errors and "for G2/math" in errors[0]


def test_unplaced_lesson_passes_alignment_with_a_minor_finding() -> None:
    result = validation.validate(make_valid_lesson())
    gate = _alignment(result)
    assert result.ok and gate.passed
    assert [(f.severity, f.message) for f in gate.findings] == [(Severity.MINOR, UNPLACED)]


def test_valid_placement_passes_and_invalid_placement_blocks() -> None:
    ok = validation.validate(_placed(), hierarchy=STORED)
    assert ok.ok and _alignment(ok).findings == []
    for lesson, hierarchy in (
        (_placed("CH9", ""), STORED),
        (_placed("CH1", "T9"), STORED),
        (_placed("", "T1"), STORED),
        (_placed(), None),  # placed, but no hierarchy is stored for the pack
    ):
        result = validation.validate(lesson, hierarchy=hierarchy)
        gate = _alignment(result)
        assert not result.ok and not gate.passed
        assert any(f.severity is Severity.BLOCKER for f in gate.findings)


# ---- service ------------------------------------------------------------------------------


def _service(with_hierarchy: bool = True, packs: PackRegistry | None = None) -> Any:
    return CurriculumStudioService(
        InMemoryLessonRepository(),
        RecordingPublishPort(),
        hierarchy=InMemoryHierarchyRepository() if with_hierarchy else None,
        packs=packs,
    )


def test_service_validates_placement_against_the_stored_hierarchy() -> None:
    svc = _service()
    svc.create(_placed())
    assert not svc.validate("P1").ok  # nothing stored yet
    svc.upsert_hierarchy("PK-NCP", _g1_math())
    assert svc.validate("P1").ok
    svc.create(_placed("CH1", "T9", "P2"))
    assert not svc.validate("P2").ok
    assert svc.placement_errors(svc.get("P2"))
    assert svc.placement_errors(svc.get("P1")) == []


def test_service_without_a_hierarchy_store_blocks_placed_lessons_only() -> None:
    svc = _service(with_hierarchy=False)
    svc.create(make_valid_lesson("U1"))
    svc.create(_placed(lesson_id="P1"))
    assert svc.validate("U1").ok
    assert not svc.validate("P1").ok


# ---- API ----------------------------------------------------------------------------------

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
AUTHOR_H = {
    "Authorization": "Bearer "
    + sign_hs256(
        {"sub": "staff-author", "role": "subject_author", "exp": int(time.time()) + 3600}, _SECRET
    )
}


def _client(store_hierarchy: bool = True) -> TestClient:
    app = create_app(Settings(database_url=""))  # private in-memory store
    with unit_of_work(app.state.studio_session_factory) as uow:
        svc = CurriculumStudioService(uow.lessons, uow.publish, hierarchy=uow.hierarchy)
        if store_hierarchy:
            svc.upsert_hierarchy("PK-NCP", _g1_math())
        svc.create(make_valid_lesson("A1"))
        uow.commit()
    return TestClient(app)


def _patch(c: TestClient, body: dict[str, Any]) -> Any:
    etag = c.get("/v1/studio/lessons/A1", headers=AUTHOR_H).headers["ETag"]
    return c.patch("/v1/studio/lessons/A1", json=body, headers={**AUTHOR_H, "If-Match": etag})


def test_patch_sets_validates_and_clears_placement() -> None:
    c = _client()
    r = _patch(c, {"chapter_key": "CH1", "topic_key": "T1"})
    assert r.status_code == 200, r.text
    assert (r.json()["metadata"]["chapter_key"], r.json()["metadata"]["topic_key"]) == ("CH1", "T1")
    v = c.post("/v1/studio/lessons/A1:validate", headers=AUTHOR_H).json()
    assert v["ok"]
    alignment = next(g for g in v["gates"] if g["gate"] == "curriculum_alignment")
    assert alignment["passed"] and alignment["findings"] == []

    for bad, detail in (
        ({"chapter_key": "CH9"}, "chapter 'CH9' is not in the stored PK-NCP hierarchy"),
        ({"topic_key": "T9"}, "topic 'T9' is not in chapter 'CH1'"),
        ({"chapter_key": ""}, "requires a chapter_key"),  # topic left without its chapter
    ):
        r = _patch(c, bad)
        assert r.status_code == 422, bad
        assert r.json()["code"] == "BAD_PLACEMENT" and detail in r.json()["detail"]

    r = _patch(c, {"chapter_key": "", "topic_key": ""})
    assert r.status_code == 200
    assert r.json()["metadata"]["chapter_key"] == ""
    v = c.post("/v1/studio/lessons/A1:validate", headers=AUTHOR_H).json()
    alignment = next(g for g in v["gates"] if g["gate"] == "curriculum_alignment")
    assert alignment["passed"] and alignment["findings"] == [UNPLACED]


def test_patch_placement_without_a_stored_hierarchy_is_refused() -> None:
    c = _client(store_hierarchy=False)
    r = _patch(c, {"chapter_key": "CH1"})
    assert r.status_code == 422 and r.json()["code"] == "BAD_PLACEMENT"
    assert "no stored PK-NCP hierarchy" in r.json()["detail"]


# ---- PostgreSQL ---------------------------------------------------------------------------

PG_URL = os.environ.get("CS_DATABASE_URL")


def _test_pack(pack_id: str) -> Any:
    return parse_pack(
        {
            "schema_version": 1,
            "pack_id": pack_id,
            "version": "0.0.1-test",
            "country": "ZZ",
            "education_system": "Synthetic test system (not a real curriculum)",
            "grades": ["G1"],
            "subject_roster": {"G1": ["math"]},
            "academic_calendar": {"year_start_month": 9, "terms": [{"key": "t1", "name": "T1"}]},
            "language_of_instruction": "ur",
            "default_numeral_system": "western",
            "locales": {
                "ur": {"name": "Urdu", "direction": "rtl"},
                "en": {"name": "English", "direction": "ltr"},
            },
            "instructional_locales": {
                "ur": {
                    "required_locales": ["ur", "en"],
                    "audio_required_locales": ["ur"],
                    "readability_locales": ["ur"],
                }
            },
            "readability": {"ur": {"max_words_per_sentence": {"G1": 8}, "default_max_words": 8}},
        },
        "test",
    )


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_placement_gate_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.upgrade(cfg, "head")  # no-op when already migrated
    # A unique synthetic pack per run: never touches the shared PK-NCP rows.
    pack_id = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    packs = PackRegistry([default_pack(), _test_pack(pack_id)])
    suffix = uuid.uuid4().hex[:8]
    engine = create_db_engine(PG_URL or "")
    factory = create_session_factory(engine)

    def lesson(lesson_id: str, chapter: str, topic: str) -> Lesson:
        x = _placed(chapter, topic, lesson_id)
        x.metadata.curriculum_pack = pack_id
        x.title = LocalizedText(text={Locale.UR: "مقام", Locale.EN: "Placement probe"})
        return x

    def svc(uow: Any) -> CurriculumStudioService:
        return CurriculumStudioService(
            uow.lessons, uow.publish, on_commit=uow.commit, hierarchy=uow.hierarchy, packs=packs
        )

    try:
        with unit_of_work(factory) as uow:
            s = svc(uow)
            s.upsert_hierarchy(pack_id, _g1_math(pack_id))
            s.create(lesson(f"PG-ok-{suffix}", "CH1", "T1"))
            s.create(lesson(f"PG-bad-{suffix}", "CH1", "T9"))
        with unit_of_work(factory) as uow:  # fresh session: hierarchy + lessons from the DB
            s = svc(uow)
            assert s.validate(f"PG-ok-{suffix}").ok
            bad = s.validate(f"PG-bad-{suffix}")
            assert not bad.ok
            assert not _alignment(bad).passed
    finally:
        engine.dispose()
