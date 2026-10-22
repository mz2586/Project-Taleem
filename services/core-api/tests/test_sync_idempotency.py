"""Offline sync idempotency across crashes and restarts, and partial-batch outcomes.

The client's crash window: the server records the batch and answers, then the device dies before
the local queue delete commits. On restart the client re-sends the SAME deltas — possibly to a
different (or freshly restarted) server instance whose in-memory seen-set is empty. The evidence
table, keyed by the client ``evidence_id``, must make that a DUPLICATE with exactly one record.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.vertical_slice.fractions_lesson import LESSON_KEY, OBJECTIVE_CODE
from tests.test_sync_evidence import _attempt_delta, _auth, _publish_fractions

_STUDENT = "idem-stu"  # synthetic dev learner (no identity account; permitted outside production)


def _post(client: TestClient, deltas: list[dict[str, object]]) -> list[str]:
    r = client.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": deltas},
        headers=_auth("student", _STUDENT),
    )
    assert r.status_code == 200, r.text
    return [row["status"] for row in r.json()["results"]]


def _evidence_ids(app: FastAPI) -> list[str]:
    with LearningUnitOfWork(app.state.learning_session_factory) as uow:
        knowledge = uow.knowledge.get(_STUDENT)
        return [e.evidence_id for e in knowledge.evidence] if knowledge else []


def _delta(cid: str, eid: str, seq: int, item: str = "p1-one-of-four") -> dict[str, object]:
    return _attempt_delta(
        student=_STUDENT,
        item_ref=item,
        option=0,
        client_event_id=cid,
        evidence_id=eid,
        client_seq=seq,
    )


def test_resend_after_server_restart_is_a_duplicate_recorded_once(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path / 'taleem.db'}"
    first = create_app(Settings(database_url=url))
    _publish_fractions(first)
    batch = [_delta(uuid7(), uuid7(), 1), _delta(uuid7(), uuid7(), 2, "p3-denominator")]

    # Server acks; the client "crashes" before deleting its local copies.
    assert _post(TestClient(first), batch) == ["applied", "applied"]

    # A fresh process over the same database: the in-memory seen-set is empty, so only the
    # durable evidence table can recognise the replay.
    restarted = create_app(Settings(database_url=url))
    assert _post(TestClient(restarted), batch) == ["duplicate", "duplicate"]
    ids = _evidence_ids(restarted)
    assert len(ids) == 2 and len(set(ids)) == 2  # exactly once each


def test_resend_with_new_client_event_id_same_evidence_id_is_a_duplicate() -> None:
    app = create_app(Settings(database_url=""))
    _publish_fractions(app)
    client = TestClient(app)
    eid = uuid7()
    assert _post(client, [_delta(uuid7(), eid, 1)]) == ["applied"]
    # Reconciliation re-queued the attempt under a fresh delta id but its stable evidence_id.
    assert _post(client, [_delta(uuid7(), eid, 2)]) == ["duplicate"]
    assert _evidence_ids(app) == [eid]


def test_a_conflict_is_not_remembered_so_a_later_resend_still_records() -> None:
    # The lesson is not published yet → the attempt cannot be graded → CONFLICT, nothing stored.
    app = create_app(Settings(database_url=""))
    client = TestClient(app)
    cid, eid = uuid7(), uuid7()
    assert _post(client, [_delta(cid, eid, 1)]) == ["conflict"]
    assert _evidence_ids(app) == []

    # Once published, re-sending the SAME delta must apply. If the conflict had been marked seen,
    # the server would answer DUPLICATE and the client would release work that was never stored.
    _publish_fractions(app)
    assert _post(client, [_delta(cid, eid, 1)]) == ["applied"]
    assert _evidence_ids(app) == [eid]


def test_partial_batch_reports_per_item_and_records_only_the_valid_attempts() -> None:
    app = create_app(Settings(database_url=""))
    _publish_fractions(app)
    client = TestClient(app)
    good, also_good = uuid7(), uuid7()
    malformed = {
        "clientEventId": uuid7(),
        "type": "attempt.submitted",
        "entityKey": f"student:{_STUDENT}|lesson:{LESSON_KEY}",
        "clientSeq": 2,
        "payload": {"student_ref": _STUDENT, "objective_code": OBJECTIVE_CODE},  # no item/option
    }
    statuses = _post(
        client,
        [
            _delta(uuid7(), good, 1),
            malformed,
            _delta(uuid7(), uuid7(), 3, "summative-or-unknown"),
            _delta(uuid7(), also_good, 4, "p3-denominator"),
        ],
    )
    assert statuses == ["applied", "conflict", "ignored", "applied"]
    assert sorted(_evidence_ids(app)) == sorted([good, also_good])
