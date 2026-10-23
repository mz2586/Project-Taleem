"""Performance regressions found by the k6 load/soak/spike runs (tests/perf), pinned as tests.

1. Offline sync: the database work per attempt delta must not grow with the learner's history
   (it used to hydrate every evidence row, once per delta), and a batch resolves each lesson once.
2. Offline packages: built + signed manifests are cached per lesson fingerprint and signing key,
   and a changed, unpublished or re-keyed lesson is never served from a stale entry.
3. Kill switch: only child-facing requests read the flag, and those read it live every time.
4. Teacher class reads: the learning-side reads are batched (constant per request), identity is
   read in one transaction, and hidden learners are never read.

Statement counts come from a SQLAlchemy ``before_cursor_execute`` listener on every engine.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.engine import Engine

from taleem_core.contexts.curriculum_studio.adapters.persistence.models import LessonRow
from taleem_core.contexts.learning.adapters.curriculum_read_model import (
    CurriculumStudioReadModel,
)
from taleem_core.contexts.learning.adapters.package_signer import Ed25519PackageSigner
from taleem_core.contexts.learning.adapters.persistence.models import AssessmentEvidenceRow
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.learning.application.offline_service import OfflinePackageService
from taleem_core.contexts.learning.application.sync_consumer import SyncEvidenceConsumer
from taleem_core.contexts.learning.domain.curriculum_view import ItemView, LessonView
from taleem_core.contexts.learning.domain.estimator import BKTEstimator
from taleem_core.contexts.learning.domain.forgetting import HalfLifeForgettingModel
from taleem_core.contexts.learning.domain.offline_package import (
    content_hash,
    lesson_offline_content,
    signing_payload,
)
from taleem_core.contexts.ops.adapters.persistence.kill_switch_store import SqlKillSwitchState
from taleem_core.contexts.sync.domain import DeltaType, SyncDelta, SyncStore
from taleem_core.contexts.sync.service import DurableSyncCoordinator
from taleem_core.main import create_app
from taleem_core.platform import ed25519
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.platform.kill_switch import KillSwitch
from taleem_core.vertical_slice.fractions_lesson import LESSON_KEY, OBJECTIVE_CODE
from tests.test_school_api import _class, _family, _join, _org, _teacher
from tests.test_sync_evidence import _attempt_delta, _auth, _publish_fractions

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_STUDENT = "perf-stu"  # synthetic dev learner (no identity account; permitted outside production)


@dataclass
class _Statements:
    sql: list[str] = field(default_factory=list)

    def selects(self) -> int:
        return sum(1 for s in self.sql if s.lstrip().upper().startswith("SELECT"))

    def touching(self, needle: str) -> int:
        return sum(1 for s in self.sql if needle in s)


@contextmanager
def _count_statements() -> Iterator[_Statements]:
    seen = _Statements()

    def _on_execute(
        conn: Any, cursor: Any, statement: str, params: Any, context: Any, many: bool
    ) -> None:
        seen.sql.append(statement)

    event.listen(Engine, "before_cursor_execute", _on_execute)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", _on_execute)


# ------------------------------------------------------------------------------- 1. sync


def _sync(client: TestClient, deltas: list[dict[str, object]]) -> list[str]:
    r = client.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": deltas},
        headers=_auth("student", _STUDENT),
    )
    assert r.status_code == 200, r.text
    return [row["status"] for row in r.json()["results"]]


def _delta(seq: int, evidence_id: str | None = None, option: int = 0) -> dict[str, object]:
    return _attempt_delta(
        student=_STUDENT,
        item_ref="p1-one-of-four",
        option=option,
        client_event_id=uuid7(),
        evidence_id=evidence_id or uuid7(),
        client_seq=seq,
    )


def _evidence_count(app: FastAPI) -> int:
    with LearningUnitOfWork(app.state.learning_session_factory) as uow:
        return int(
            uow.session.execute(
                select(func.count())
                .select_from(AssessmentEvidenceRow)
                .where(AssessmentEvidenceRow.student_ref == _STUDENT)
            ).scalar_one()
        )


def _one_delta_reads(client: TestClient) -> tuple[int, int, str]:
    """SELECTs for a one-attempt batch, then for re-sending it (a durable DUPLICATE)."""
    evidence_id = uuid7()
    with _count_statements() as applied:
        assert _sync(client, [_delta(1, evidence_id)]) == ["applied"]
    with _count_statements() as replayed:
        # A fresh delta id, the same evidence id: only the evidence table can recognise it.
        assert _sync(client, [_delta(2, evidence_id)]) == ["duplicate"]
    return applied.selects(), replayed.selects(), "\n".join(applied.sql)


def test_sync_reads_per_delta_do_not_grow_with_history() -> None:
    app = create_app(Settings(database_url=""))
    _publish_fractions(app)
    client = TestClient(app)
    # Some history first (the first-ever attempt creates the knowledge root: a different path).
    assert _sync(client, [_delta(i, option=i % 2) for i in range(3)]) == ["applied"] * 3
    small = _one_delta_reads(client)

    for start in range(0, 60, 20):  # +60 attempts of history
        assert _sync(client, [_delta(start + i, option=i % 2) for i in range(20)]) == (
            ["applied"] * 20
        )
    assert _evidence_count(app) == 3 + 1 + 60  # the duplicate re-send recorded nothing
    large = _one_delta_reads(client)

    assert small[0] == large[0], f"apply path grew with history:\n{large[2]}"
    assert small[1] == large[1], "duplicate path grew with history"
    # And the attempt path never reads the learner's whole evidence history.
    assert "assessment_evidence.occurred_at" not in large[2]


def test_a_sync_batch_resolves_each_lesson_once() -> None:
    app = create_app(Settings(database_url=""))
    _publish_fractions(app)

    class _Counting(CurriculumStudioReadModel):
        calls = 0

        def lesson_for(self, objective_code: str) -> LessonView | None:
            type(self).calls += 1
            return super().lesson_for(objective_code)

    curriculum = _Counting(app.state.studio_session_factory)
    consumer = SyncEvidenceConsumer(
        lambda: LearningUnitOfWork(app.state.learning_session_factory),
        curriculum,
        BKTEstimator(),
        HalfLifeForgettingModel(),
        time.time,
    )
    coordinator = DurableSyncCoordinator(SyncStore(), consumer)

    def delta(seq: int) -> SyncDelta:
        raw = _delta(seq)
        return SyncDelta(
            client_event_id=str(raw["clientEventId"]),
            type=DeltaType.ATTEMPT_SUBMITTED,
            entity_key=str(raw["entityKey"]),
            payload=dict(raw["payload"]),  # type: ignore[call-overload]
            client_seq=seq,
        )

    results, _ = coordinator.apply_batch([delta(i) for i in range(5)])
    assert [r.status.value for r in results] == ["applied"] * 5
    assert _Counting.calls == 1  # five deltas, one lesson lookup
    coordinator.apply_batch([delta(10)])
    assert _Counting.calls == 2  # not carried past the batch: the next batch reads it afresh
    consumer.apply_attempt(delta(20))  # outside a batch: no memo at all
    assert _Counting.calls == 3


# ------------------------------------------------------------------------ 2. offline cache


def _view(explanation_en: str = "A fraction is an equal part.") -> LessonView:
    return LessonView(
        lesson_id="L-x",
        objective_code="MATH-G4-FR-01",
        title={"ur": "کسر", "en": "Fractions"},
        explanation={"ur": "حصہ", "en": explanation_en},
        worked_example_steps=("step one",),
        practice_items=(
            ItemView(
                item_ref="p1",
                objective_code="MATH-G4-FR-01",
                prompt={"ur": "سوال", "en": "Which fraction?"},
                options=("1/4", "4/1"),
                correct_option=0,
                option_misconceptions={},
                hints=("Think about slices.",),
            ),
        ),
    )


class _FakeCurriculum:
    """A read model whose lessons and fingerprints the test controls (counts full reads)."""

    def __init__(self) -> None:
        self.lessons: dict[str, tuple[str, LessonView]] = {}  # lesson_id -> (fingerprint, view)
        self.full_reads = 0

    def publish(self, view: LessonView, fingerprint: str) -> None:
        self.lessons[view.lesson_id] = (fingerprint, view)

    def published_fingerprints(self) -> list[tuple[str, str]]:
        return [(i, f) for i, (f, _) in self.lessons.items()]

    def published_lessons(self) -> list[LessonView]:
        self.full_reads += 1
        return [v for _, v in self.lessons.values()]

    def lesson_for(self, objective_code: str) -> LessonView | None:
        return None

    def published_graph(self) -> Any:
        return None


_SEED_A = "11" * 32
_SEED_B = "22" * 32


def _verifies(manifest: dict[str, Any], public_hex: str) -> bool:
    payload = signing_payload(
        str(manifest["package_id"]), str(manifest["version"]), str(manifest["content_hash"])
    )
    return ed25519.verify(
        bytes.fromhex(str(manifest["signature"])), payload, bytes.fromhex(public_hex)
    )


def test_manifests_are_built_once_per_lesson_version() -> None:
    curriculum = _FakeCurriculum()
    curriculum.publish(_view(), "v1")
    clock = [1.0]
    signer = Ed25519PackageSigner(_SEED_A, "key-a")
    service = OfflinePackageService(curriculum, lambda: clock[0], signer=signer)

    first = service.list_packages()["packages"][0]  # type: ignore[index]
    clock[0] = 2.0
    second = service.list_packages()["packages"][0]  # type: ignore[index]
    assert service.builds == 1 and curriculum.full_reads == 1  # the second call was a cache hit
    # Identical manifest apart from the per-response timestamp, exactly as before the cache.
    assert first["created_at_ms"] == 1000 and second["created_at_ms"] == 2000
    assert {k: v for k, v in first.items() if k != "created_at_ms"} == {
        k: v for k, v in second.items() if k != "created_at_ms"
    }
    assert _verifies(second, signer.public_key_hex)

    package = service.get_package("L-x")
    assert package is not None and service.builds == 1
    assert package.manifest.content_hash == content_hash(package.content)
    assert service.get_package("missing") is None


def test_a_republished_lesson_is_rebuilt_never_served_stale() -> None:
    curriculum = _FakeCurriculum()
    curriculum.publish(_view("old text"), "v1")
    service = OfflinePackageService(curriculum, lambda: 1.0, signer=None)
    old = service.list_packages()["packages"][0]  # type: ignore[index]

    new_view = _view("new text")
    curriculum.publish(new_view, "v2")  # publish / rollback: the fingerprint changes
    new = service.list_packages()["packages"][0]  # type: ignore[index]
    assert service.builds == 2
    assert new["content_hash"] != old["content_hash"]
    assert new["content_hash"] == content_hash(lesson_offline_content(new_view))
    package = service.get_package("L-x")
    assert package is not None
    assert package.content["explanation"] == {"ur": "حصہ", "en": "new text"}

    # Unpublished: gone from the index and from the per-lesson route, and evicted.
    del curriculum.lessons["L-x"]
    assert service.list_packages() == {"packages": []}
    assert service.get_package("L-x") is None


def test_a_different_signing_key_never_reuses_a_cached_signature() -> None:
    curriculum = _FakeCurriculum()
    curriculum.publish(_view(), "v1")
    signer_a = Ed25519PackageSigner(_SEED_A, "key-a")
    service = OfflinePackageService(curriculum, lambda: 1.0, signer=signer_a)
    a = service.list_packages()["packages"][0]  # type: ignore[index]

    signer_b = Ed25519PackageSigner(_SEED_B, "key-b")
    service._signer = signer_b  # a key rotation reaching this service
    b = service.list_packages()["packages"][0]  # type: ignore[index]
    assert service.builds == 2
    assert b["signing_key_id"] == "key-b" and _verifies(b, signer_b.public_key_hex)
    assert not _verifies(b, signer_a.public_key_hex) and _verifies(a, signer_a.public_key_hex)

    # Same key id, different key material: still a rebuild.
    service._signer = Ed25519PackageSigner(_SEED_A, "key-b")
    c = service.list_packages()["packages"][0]  # type: ignore[index]
    assert service.builds == 3 and _verifies(c, signer_a.public_key_hex)


def test_lesson_fingerprint_changes_on_every_write_to_a_published_lesson() -> None:
    app = create_app(Settings(database_url=""))
    _publish_fractions(app)
    sf = app.state.studio_session_factory
    read_model = CurriculumStudioReadModel(sf)
    client = TestClient(app)
    h = _auth("student", "pkg-stu")

    before = read_model.published_fingerprints()
    assert [i for i, _ in before] == [LESSON_KEY]
    first = client.get("/v1/offline/packages", headers=h).json()["packages"][0]

    # The published content changes in place (what a republish of new content writes).
    with sf() as session:
        row = session.execute(
            select(LessonRow).where(LessonRow.lesson_key == LESSON_KEY)
        ).scalar_one()
        body = copy.deepcopy(row.body)
        body["student_explanation"]["text"]["en"] = "Changed explanation for the cache test."
        row.body = body
        session.commit()

    after = read_model.published_fingerprints()
    assert after != before
    second = client.get("/v1/offline/packages", headers=h).json()["packages"][0]
    assert second["content_hash"] != first["content_hash"]
    full = client.get(f"/v1/offline/packages/{LESSON_KEY}", headers=h).json()
    assert full["manifest"]["content_hash"] == second["content_hash"]
    assert full["manifest"]["content_hash"] == content_hash(full["content"])
    assert "Changed explanation" in str(full["content"])


# ------------------------------------------------------------------------ 3. kill switch


def test_kill_switch_is_read_only_for_child_facing_requests_and_always_live() -> None:
    app = create_app(Settings(database_url=""))
    client = TestClient(app)
    with _count_statements() as health:
        for _ in range(3):
            assert client.get("/health").status_code == 200
    assert health.touching("kill_switch") == 0

    h = _auth("student", "ks-stu")
    with _count_statements() as child:
        assert client.get("/v1/offline/packages", headers=h).status_code == 200
        assert client.get("/v1/offline/packages", headers=h).status_code == 200
    assert child.touching("kill_switch") == 2  # one live read per child-facing request

    # Engaged elsewhere (another instance): the very next child-facing request is halted.
    other_instance = KillSwitch(time.time, SqlKillSwitchState(app.state.ops_session_factory))
    other_instance.engage("drill")
    assert client.get("/v1/offline/packages", headers=h).status_code == 503
    assert client.get("/health").status_code == 200
    other_instance.disengage()
    assert client.get("/v1/offline/packages", headers=h).status_code == 200


# ---------------------------------------------------------------------- 4. teacher reads


@pytest.fixture
def school() -> tuple[TestClient, FastAPI]:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    _publish_fractions(app)
    return TestClient(app), app


def _progress_reads(
    client: TestClient, teacher: dict[str, str], class_id: object, assignment_id: object
) -> tuple[int, int, list[dict[str, Any]]]:
    url = f"/v1/school/classes/{class_id}/assignments/{assignment_id}/progress"
    with _count_statements() as seen:
        r = client.get(url, headers=teacher)
    assert r.status_code == 200, r.text
    tables = ("student_knowledge", "objective_mastery", "assessment_evidence")
    learning = sum(1 for s in seen.sql if any(t in s for t in tables))
    return learning, seen.selects(), list(r.json()["learners"])


def test_teacher_progress_reads_are_batched(school: tuple[TestClient, FastAPI]) -> None:
    client, _ = school
    org = _org(client, "Perf School")
    teacher = _teacher(client, org, "perf@school.example")
    klass = _class(client, teacher, "Grade 4 Perf")
    assignment = _assign_to(client, teacher, klass["class_id"])

    families = []
    for n in range(4):
        fam = _family(client, f"perf{n}@example.com", ["learning_data", "progress_sharing"])
        assert _join(client, fam, klass["join_code"]) == 200
        families.append(fam)
        sync = client.post(
            "/v1/sync/batch",
            json={
                "cursor": 0,
                "deltas": [
                    _attempt_delta(
                        student=fam.student_ref,
                        item_ref="p1-one-of-four",
                        option=0,
                        client_event_id=uuid7(),
                        evidence_id=uuid7(),
                        client_seq=1,
                    )
                ],
            },
            headers=fam.learner,
        )
        assert sync.status_code == 200, sync.text
        if n == 0:
            one_learning, one_selects, rows = _progress_reads(
                client, teacher, klass["class_id"], assignment["assignment_id"]
            )
            assert len(rows) == 1 and rows[0]["attempts_since_assigned"] == 1

    four_learning, four_selects, rows = _progress_reads(
        client, teacher, klass["class_id"], assignment["assignment_id"]
    )
    assert len(rows) == 4
    assert all(r["completed"] and r["attempts_since_assigned"] == 1 for r in rows)
    # Learning reads are batched: the same three queries for one learner or four.
    assert one_learning == four_learning == 3
    # Identity: two reads per extra learner (account + consent history), one transaction.
    assert four_selects - one_selects <= 2 * 3

    # Live consent is still per request: a withdrawal hides the learner on the next call.
    gone = families[1]
    r = client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": gone.student_ref, "scopes": ["progress_sharing"]},
        headers=gone.guardian,
    )
    assert r.status_code == 200
    _, _, rows = _progress_reads(client, teacher, klass["class_id"], assignment["assignment_id"])
    assert [r["student_ref"] for r in rows] == [f.student_ref for f in families if f is not gone]


def _assign_to(client: TestClient, teacher: dict[str, str], class_id: object) -> dict[str, Any]:
    r = client.post(
        f"/v1/school/classes/{class_id}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 86400},
        headers=teacher,
    )
    assert r.status_code == 201, r.text
    return dict(r.json())
