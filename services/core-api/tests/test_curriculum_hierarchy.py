"""Pack-scoped curriculum hierarchy persistence + the locale-generic authoring API.

The hierarchy (Grade → Subject → Chapter → Topic) is persisted through the application service
(``upsert_hierarchy`` / ``get_hierarchy``) behind the ``HierarchyRepository`` port, over the
existing ``education_system`` / ``grade`` / ``subject`` tables (chapters/topics in
``subject.titles``) — no new migration. PostgreSQL-gated tests run where ``CS_DATABASE_URL`` is
set.
"""

from __future__ import annotations

import copy
import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    Base,
    SqlAlchemyHierarchyRepository,
    create_db_engine,
    create_session_factory,
    unit_of_work,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence.hierarchy import (
    STRUCTURE_KEY,
    system_key_for,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence.models import (
    AuditLogRow,
    EducationSystemRow,
    GradeRow,
    LessonRow,
    SubjectRow,
)
from taleem_core.contexts.curriculum_studio.adapters.persistence.repository import (
    DEFAULT_SYSTEM_KEY,
)
from taleem_core.contexts.curriculum_studio.application.repository import (
    HierarchyRepository,
    InMemoryHierarchyRepository,
    InMemoryLessonRepository,
    RecordingPublishPort,
)
from taleem_core.contexts.curriculum_studio.application.service import (
    CurriculumStudioService,
    StudioError,
)
from taleem_core.contexts.curriculum_studio.domain.content import Locale, LocalizedText
from taleem_core.contexts.curriculum_studio.domain.hierarchy import (
    Chapter,
    EducationSystem,
    Grade,
    Subject,
    Topic,
    check_against_pack,
    merge_hierarchy,
)
from taleem_core.contexts.curriculum_studio.domain.packs import (
    PackRegistry,
    default_pack,
    parse_pack,
)
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from tests.studio_helpers import make_valid_lesson


def _t(ur: str = "", en: str = "") -> LocalizedText:
    text: dict[Locale, str] = {}
    if ur:
        text[Locale.UR] = ur
    if en:
        text[Locale.EN] = en
    return LocalizedText(text=text)


def _g4(*, extra_topic: bool = False, key: str = "PK-NCP") -> EducationSystem:
    """A C2-shaped hierarchy: G4 → math/science → units → topics (ids deliberately ad hoc)."""
    topics = [Topic(topic_id="x", key="t1", title=_t("حصہ", "Fractions as parts"))]
    if extra_topic:
        topics.append(Topic(topic_id="y", key="t2", title=_t(en="Equivalent fractions")))
    return EducationSystem(
        system_id="whatever",
        key=key,
        name="",
        grades=[
            Grade(
                grade_id="G4",
                key="G4",
                subjects=[
                    Subject(
                        subject_id="G4/science",
                        key="science",
                        title=_t(en="Science"),
                        chapters=[Chapter(chapter_id="s1", key="s1", title=_t(en="Living things"))],
                    ),
                    Subject(
                        subject_id="G4/math",
                        key="math",
                        title=_t(en="Mathematics"),
                        chapters=[
                            Chapter(
                                chapter_id="u1", key="u1", title=_t(en="Fractions"), topics=topics
                            )
                        ],
                    ),
                ],
            )
        ],
    )


def _shape(system: EducationSystem | None) -> Any:
    """Comparable structure (keys, ids, titles) of a hierarchy."""
    assert system is not None

    def chapter(c: Chapter) -> Any:
        return (
            c.chapter_id,
            dict(c.title.text),
            [(t.topic_id, dict(t.title.text)) for t in c.topics],
        )

    return [
        (
            g.grade_id,
            [
                (s.subject_id, dict(s.title.text), [chapter(c) for c in s.chapters])
                for s in g.subjects
            ],
        )
        for g in system.grades
    ]


def _test_pack(pack_id: str = "TEST-EN") -> Any:
    return parse_pack(
        {
            "schema_version": 1,
            "pack_id": pack_id,
            "version": "0.0.1-test",
            "country": "ZZ",
            "education_system": "Synthetic test system (not a real curriculum)",
            "grades": ["Y1", "Y2"],
            "subject_roster": {"Y1": ["math"], "Y2": ["math", "science"]},
            "academic_calendar": {"year_start_month": 9, "terms": [{"key": "t1", "name": "T1"}]},
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
        },
        "test",
    )


def _y_system(key: str) -> EducationSystem:
    return EducationSystem(
        system_id="",
        key=key,
        name="Synthetic",
        grades=[
            Grade(
                grade_id="",
                key="Y2",
                subjects=[Subject(subject_id="", key="science", title=_t(en="Science"))],
            )
        ],
    )


def _svc(
    hierarchy: HierarchyRepository | None = None, packs: PackRegistry | None = None
) -> CurriculumStudioService:
    return CurriculumStudioService(
        InMemoryLessonRepository(),
        RecordingPublishPort(),
        hierarchy=hierarchy if hierarchy is not None else InMemoryHierarchyRepository(),
        packs=packs,
    )


# =============================================================================================
# Domain rules
# =============================================================================================


def test_valid_hierarchy_has_no_errors() -> None:
    assert check_against_pack(_g4(), default_pack()) == []


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (lambda s: setattr(s, "key", "XX"), "does not match curriculum pack PK-NCP"),
        (lambda s: setattr(s.grades[0], "key", "Y9"), "not a grade of curriculum pack PK-NCP"),
        (lambda s: s.grades.append(copy.deepcopy(s.grades[0])), "duplicate grade 'G4'"),
        (lambda s: setattr(s.grades[0].subjects[0], "key", "physics"), "not in the PK-NCP roster"),
        (
            lambda s: s.grades[0].subjects.append(copy.deepcopy(s.grades[0].subjects[0])),
            "duplicate subject 'science'",
        ),
        (
            lambda s: s.grades[0]
            .subjects[1]
            .chapters.append(copy.deepcopy(s.grades[0].subjects[1].chapters[0])),
            "duplicate chapter 'u1'",
        ),
        (
            lambda s: setattr(s.grades[0].subjects[1].chapters[0], "key", " "),
            "chapter with an empty key",
        ),
        (
            lambda s: s.grades[0]
            .subjects[1]
            .chapters[0]
            .topics.append(copy.deepcopy(s.grades[0].subjects[1].chapters[0].topics[0])),
            "duplicate topic 't1'",
        ),
        (
            lambda s: setattr(s.grades[0].subjects[1].chapters[0].topics[0], "key", ""),
            "topic with an empty key",
        ),
        (
            lambda s: s.grades[0].subjects[0].title.text.__setitem__(Locale("fr"), "Sciences"),
            "title locale 'fr' is not declared by curriculum pack PK-NCP",
        ),
        (
            lambda s: s.grades[0]
            .subjects[1]
            .chapters[0]
            .topics[0]
            .title.audio_ref.__setitem__(Locale("ar"), "a.mp3"),
            "title locale 'ar' is not declared",
        ),
    ],
)
def test_invalid_hierarchy_is_rejected(mutate: Any, error: str) -> None:
    system = _g4()
    mutate(system)
    errors = check_against_pack(system, default_pack())
    assert any(error in e for e in errors), errors


def test_merge_is_idempotent_ordered_and_canonical() -> None:
    once = merge_hierarchy(None, _g4(), default_pack())
    twice = merge_hierarchy(once, _g4(), default_pack())
    assert _shape(once) == _shape(twice)
    # Subjects follow the pack roster order (math before science); ids are canonical paths.
    assert [s.key for s in once.grades[0].subjects] == ["math", "science"]
    assert once.system_id == once.key == "PK-NCP"
    assert once.name == default_pack().education_system
    math = once.grades[0].subjects[0]
    assert math.subject_id == "PK-NCP/G4/math"
    assert math.chapters[0].topics[0].topic_id == "PK-NCP/G4/math/u1/t1"


def test_merge_is_non_destructive_and_merges_titles_per_locale() -> None:
    base = merge_hierarchy(None, _g4(extra_topic=True), default_pack())
    partial = EducationSystem(
        system_id="",
        key="PK-NCP",
        name="",
        grades=[
            Grade(
                grade_id="",
                key="G4",
                subjects=[
                    Subject(
                        subject_id="",
                        key="math",
                        title=_t(ur="ریاضی", en=""),  # adds Urdu, keeps English
                        chapters=[Chapter(chapter_id="", key="u2", title=_t(en="Decimals"))],
                    )
                ],
            ),
            Grade(grade_id="", key="G3", subjects=[]),
        ],
    )
    merged = merge_hierarchy(base, partial, default_pack())
    assert [g.key for g in merged.grades] == ["G3", "G4"]  # pack grade order
    math = next(s for s in merged.grades[1].subjects if s.key == "math")
    assert math.title.text == {"en": "Mathematics", "ur": "ریاضی"}
    assert [c.key for c in math.chapters] == ["u1", "u2"]  # nothing removed, new appended
    assert [t.key for t in math.chapters[0].topics] == ["t1", "t2"]
    assert [s.key for s in merged.grades[1].subjects] == ["math", "science"]


# =============================================================================================
# Application service (in-memory port)
# =============================================================================================


def test_service_upsert_and_get() -> None:
    svc = _svc()
    assert svc.get_hierarchy("PK-NCP") is None
    stored = svc.upsert_hierarchy("PK-NCP", _g4())
    assert _shape(svc.get_hierarchy("PK-NCP")) == _shape(stored)
    again = svc.upsert_hierarchy("PK-NCP", _g4())
    assert _shape(again) == _shape(stored)


def test_service_rejects_unknown_pack_and_invalid_hierarchy_without_writing() -> None:
    repo = InMemoryHierarchyRepository()
    svc = _svc(repo)
    with pytest.raises(StudioError, match="unknown curriculum pack 'XX'"):
        svc.upsert_hierarchy("XX", _g4())
    with pytest.raises(StudioError, match="unknown curriculum pack"):
        svc.get_hierarchy("XX")
    bad = _g4()
    bad.grades[0].subjects[0].key = "physics"
    with pytest.raises(StudioError, match="invalid hierarchy for PK-NCP"):
        svc.upsert_hierarchy("PK-NCP", bad)
    assert repo.get("PK-NCP") is None


def test_service_without_hierarchy_repository() -> None:
    svc = CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort())
    assert svc.get_hierarchy("PK-NCP") is None
    with pytest.raises(StudioError, match="no hierarchy repository"):
        svc.upsert_hierarchy("PK-NCP", _g4())


def test_hierarchies_are_scoped_by_pack() -> None:
    packs = PackRegistry([default_pack(), _test_pack()])
    svc = _svc(packs=packs)
    svc.upsert_hierarchy("PK-NCP", _g4())
    svc.upsert_hierarchy("TEST-EN", _y_system("TEST-EN"))
    pk, test = svc.get_hierarchy("PK-NCP"), svc.get_hierarchy("TEST-EN")
    assert pk is not None and test is not None
    assert [g.key for g in pk.grades] == ["G4"]
    assert [g.key for g in test.grades] == ["Y2"]
    with pytest.raises(StudioError, match="not a grade of curriculum pack TEST-EN"):
        svc.upsert_hierarchy("TEST-EN", _g4(key=""))


# =============================================================================================
# SQL adapter (SQLite here; PostgreSQL-gated below)
# =============================================================================================


@pytest.fixture
def factory() -> sessionmaker[Session]:
    engine = create_db_engine("sqlite://")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def _sql_upsert(
    factory: sessionmaker[Session], pack_id: str, system: EducationSystem, packs: Any = None
) -> EducationSystem:
    with unit_of_work(factory) as uow:
        svc = CurriculumStudioService(
            uow.lessons, uow.publish, on_commit=uow.commit, hierarchy=uow.hierarchy, packs=packs
        )
        return svc.upsert_hierarchy(pack_id, system)


def _sql_get(factory: sessionmaker[Session], pack_id: str, packs: Any = None) -> Any:
    with unit_of_work(factory) as uow:
        svc = CurriculumStudioService(
            uow.lessons, uow.publish, hierarchy=uow.hierarchy, packs=packs
        )
        return svc.get_hierarchy(pack_id)


def _counts(factory: sessionmaker[Session], system_key: str) -> tuple[int, int, int]:
    with unit_of_work(factory) as uow:
        sid = uow.session.execute(
            select(EducationSystemRow.id).where(EducationSystemRow.system_key == system_key)
        ).scalar_one()
        grades = uow.session.execute(
            select(func.count()).select_from(GradeRow).where(GradeRow.system_id == sid)
        ).scalar_one()
        subjects = uow.session.execute(
            select(func.count()).select_from(SubjectRow).where(SubjectRow.system_id == sid)
        ).scalar_one()
        systems = uow.session.execute(
            select(func.count()).select_from(EducationSystemRow)
        ).scalar_one()
        return grades, subjects, systems


def test_sql_round_trip_idempotent_and_shares_the_lesson_system_row(
    factory: sessionmaker[Session],
) -> None:
    # A lesson saved first creates the NCP system row; the PK-NCP hierarchy must attach to it.
    with unit_of_work(factory) as uow:
        CurriculumStudioService(uow.lessons, uow.publish).create(make_valid_lesson("L1"))
        uow.commit()
    assert system_key_for("PK-NCP") == DEFAULT_SYSTEM_KEY
    assert _sql_get(factory, "PK-NCP") is None  # system row exists but holds no hierarchy

    stored = _sql_upsert(factory, "PK-NCP", _g4())
    loaded = _sql_get(factory, "PK-NCP")
    assert _shape(loaded) == _shape(stored)
    assert loaded.key == "PK-NCP"
    assert loaded.name == "National Curriculum of Pakistan (2023)"  # existing row not renamed
    first = _counts(factory, DEFAULT_SYSTEM_KEY)
    assert first == (1, 2, 1)

    _sql_upsert(factory, "PK-NCP", _g4())  # idempotent: same rows, same tree
    assert _counts(factory, DEFAULT_SYSTEM_KEY) == first
    assert _shape(_sql_get(factory, "PK-NCP")) == _shape(stored)

    _sql_upsert(factory, "PK-NCP", _g4(extra_topic=True))  # additive
    topics = _sql_get(factory, "PK-NCP").grades[0].subjects[0].chapters[0].topics
    assert [t.key for t in topics] == ["t1", "t2"]

    with unit_of_work(factory) as uow:
        lesson_system = uow.session.execute(select(LessonRow.system_id)).scalar_one()
        math = uow.session.execute(
            select(SubjectRow).where(SubjectRow.subject_key == "math")
        ).scalar_one()
        assert math.system_id == lesson_system
        # The documented {locale: title} shape is kept at the top level of `titles`.
        assert math.titles["en"] == "Mathematics"
        assert set(math.titles[STRUCTURE_KEY]) == {"G4"}
        audits = uow.session.execute(
            select(func.count())
            .select_from(AuditLogRow)
            .where(AuditLogRow.action == "hierarchy_upsert")
        ).scalar_one()
        assert audits == 3


def test_sql_other_pack_gets_its_own_system_row(factory: sessionmaker[Session]) -> None:
    packs = PackRegistry([default_pack(), _test_pack()])
    _sql_upsert(factory, "PK-NCP", _g4(), packs)
    _sql_upsert(factory, "TEST-EN", _y_system("TEST-EN"), packs)
    assert _counts(factory, "TEST-EN") == (1, 1, 2)
    test = _sql_get(factory, "TEST-EN", packs)
    assert test.name == "Synthetic"
    assert [(g.key, [s.key for s in g.subjects]) for g in test.grades] == [("Y2", ["science"])]
    assert [g.key for g in _sql_get(factory, "PK-NCP", packs).grades] == ["G4"]


def test_sql_repository_ignores_structure_for_unknown_grades(
    factory: sessionmaker[Session],
) -> None:
    _sql_upsert(factory, "PK-NCP", _g4())
    with unit_of_work(factory) as uow:
        math = uow.session.execute(
            select(SubjectRow).where(SubjectRow.subject_key == "math")
        ).scalar_one()
        titles = dict(math.titles)
        titles[STRUCTURE_KEY] = {**titles[STRUCTURE_KEY], "G9": {"position": 0}}
        math.titles = titles
        uow.commit()
    with unit_of_work(factory) as uow:
        repo = uow.hierarchy
        assert isinstance(repo, SqlAlchemyHierarchyRepository)
        loaded = repo.get("PK-NCP")
        assert loaded is not None and [g.key for g in loaded.grades] == ["G4"]


PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")


@_pg_only
def test_hierarchy_round_trip_on_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.upgrade(cfg, "head")  # no-op when already migrated
    # A unique synthetic pack per run: never touches the shared PK-NCP rows on the test database.
    pack_id = f"TEST-{uuid.uuid4().hex[:8].upper()}"
    packs = PackRegistry([default_pack(), _test_pack(pack_id)])
    engine = create_db_engine(PG_URL or "")
    pg = create_session_factory(engine)
    try:
        stored = _sql_upsert(pg, pack_id, _y_system(pack_id), packs)
        assert _shape(_sql_get(pg, pack_id, packs)) == _shape(stored)
        _sql_upsert(pg, pack_id, _y_system(pack_id), packs)
        grades, subjects, _ = _counts(pg, pack_id)
        assert (grades, subjects) == (1, 1)
        with unit_of_work(pg) as uow:
            titles = uow.session.execute(
                select(SubjectRow.titles)
                .join(EducationSystemRow, EducationSystemRow.id == SubjectRow.system_id)
                .where(EducationSystemRow.system_key == pack_id)
            ).scalar_one()
            assert titles["en"] == "Science"
            assert titles[STRUCTURE_KEY]["Y2"]["position"] == 0
    finally:
        engine.dispose()


# =============================================================================================
# API
# =============================================================================================

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)


def _auth(role: str = "subject_author") -> dict[str, str]:
    token = sign_hs256({"sub": "u1", "role": role, "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


def _isolated_app() -> Any:
    return create_app(Settings(database_url=""))  # private in-memory SQLite


def test_api_hierarchy_falls_back_to_the_pack_then_serves_the_persisted_tree() -> None:
    app = _isolated_app()
    c = TestClient(app)
    before = c.get("/v1/studio/hierarchy", headers=_auth()).json()
    assert before["source"] == "pack" and before["tree"] == []
    assert before["grades"][0] == "KG" and len(before["grades"]) == 11

    with unit_of_work(app.state.studio_session_factory) as uow:
        CurriculumStudioService(
            uow.lessons, uow.publish, on_commit=uow.commit, hierarchy=uow.hierarchy
        ).upsert_hierarchy("PK-NCP", _g4())

    after = c.get("/v1/studio/hierarchy?pack=PK-NCP", headers=_auth()).json()
    assert after["source"] == "persisted"
    assert after["system"] == "PK-NCP"
    assert after["grades"] == ["G4"]
    assert after["subjects_by_grade"] == {"G4": ["math", "science"]}
    math = after["tree"][0]["subjects"][0]
    assert math["title"] == {"en": "Mathematics"}
    assert math["chapters"][0]["topics"][0] == {
        "key": "t1",
        "title": {"ur": "حصہ", "en": "Fractions as parts"},
    }


def _draft(**extra: Any) -> dict[str, Any]:
    return {"grade": "G1", "subject": "math", "learning_outcomes": ["MATH-G1-N-01"], **extra}


def test_api_draft_accepts_a_locale_keyed_title_map() -> None:
    c = TestClient(_isolated_app())
    r = c.post(
        "/v1/studio/lessons",
        json=_draft(lesson_id="T1", title={"ur": "گنتی", "en": "Counting"}),
        headers=_auth(),
    )
    assert r.status_code == 201, r.text
    assert r.json()["title"] == {"ur": "گنتی", "en": "Counting"}
    r = c.post(
        "/v1/studio/lessons", json=_draft(lesson_id="T2", title={"en": "Counting"}), headers=_auth()
    )
    assert r.status_code == 201
    assert r.json()["title"] == {"en": "Counting"}
    # The aliases still work, alone or alongside an agreeing map entry.
    r = c.post(
        "/v1/studio/lessons",
        json=_draft(lesson_id="T3", title={"en": "Counting"}, title_ur="گنتی", title_en="Counting"),
        headers=_auth(),
    )
    assert r.status_code == 201
    assert r.json()["title"] == {"en": "Counting", "ur": "گنتی"}


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"title": {"fr": "Compter"}}, "not a locale of pack PK-NCP"),
        ({"title": {"Not A Tag": "x"}}, "not a valid locale tag"),
        ({"title": {"ur": "a"}, "title_ur": "b"}, "conflicts with title_ur"),
        ({"title": {"en": "  "}}, "a title is required"),
        ({}, "a title is required"),
    ],
)
def test_api_draft_title_errors(body: dict[str, Any], detail: str) -> None:
    c = TestClient(_isolated_app())
    r = c.post("/v1/studio/lessons", json=_draft(lesson_id="E1", **body), headers=_auth())
    assert r.status_code == 422
    assert r.json()["code"] == "BAD_LOCALE"
    assert detail in r.json()["detail"]


def test_api_draft_under_unknown_pack_is_created_then_blocked() -> None:
    c = TestClient(_isolated_app())
    r = c.post(
        "/v1/studio/lessons",
        json=_draft(lesson_id="U1", curriculum_pack="XX-NOPE", title={"fr": "Compter"}),
        headers=_auth(),
    )
    assert r.status_code == 201
    v = c.post("/v1/studio/lessons/U1:validate", headers=_auth()).json()
    assert not v["ok"]
    assert any("unknown curriculum pack 'XX-NOPE'" in f["message"] for f in v["structural"])
