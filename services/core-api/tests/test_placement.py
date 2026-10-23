"""Diagnostic placement (R2) — the pure fold, its safeguards, and the API over real persistence.

Domain: a single wrong answer never makes a verdict or crosses the not-yet line; one answer moves a
prior by at most the cap; misses step down the DAG, hits step up; the stop rule holds; placement
converges on simulated learners with known ability (a simulation, not a learning-outcome study).

API (composed app, SQLite): the honest "no placement possible yet" state with nothing published;
the synthetic fixture lesson end to end; provenance on every seeded prior; diagnostic evidence is
distinguishable from practice evidence; idempotent retries; eligibility; the IDOR guard.
"""

from __future__ import annotations

import itertools
import random
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.learning.adapters.persistence.mapper import (
    objective_column_values,
    objective_from_row,
)
from taleem_core.contexts.learning.adapters.persistence.models import ObjectiveMasteryRow
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.learning.domain import placement as pl
from taleem_core.contexts.learning.domain.decision import (
    CurriculumGraph,
    DecisionConfig,
    DecisionKind,
    ObjectiveInfo,
    ReasonCode,
    select_next,
)
from taleem_core.contexts.learning.domain.knowledge import (
    PriorProvenance,
    StudentKnowledge,
)
from taleem_core.contexts.learning.domain.values import InteractionContext
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.tools import placement_eval
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE
from tests.test_sync_evidence import _publish_fractions

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
CFG = pl.PlacementConfig()


def _chain(n: int) -> CurriculumGraph:
    return CurriculumGraph(tuple(ObjectiveInfo(f"o{i}", f"L{i}", (), i) for i in range(n)))


def _items(graph: CurriculumGraph, per: int = 5) -> dict[str, tuple[str, ...]]:
    return {
        o.objective_code: tuple(f"{o.objective_code}-q{j}" for j in range(per))
        for o in graph.objectives
    }


def _run(
    graph: CurriculumGraph, answers: list[bool], per: int = 5
) -> tuple[pl.PlacementResult, list[pl.Observation]]:
    """Answer the placement's own questions with the given correctness sequence."""
    items = _items(graph, per)
    obs: list[pl.Observation] = []
    for i, correct in enumerate(answers):
        r = pl.place(graph, items, obs)
        if r.next_item is None:
            break
        obs.append(pl.Observation(r.next_item.objective_code, r.next_item.item_ref, correct, i))
    return pl.place(graph, items, obs), obs


# --------------------------------------------------------------------- the safeguards


def test_one_wrong_answer_is_never_a_verdict() -> None:
    graph = _chain(3)
    r, obs = _run(graph, [False])
    entry = r.get("o0")
    assert entry is not None
    assert entry.status is pl.PlacementStatus.UNCERTAIN
    assert entry.value >= CFG.not_yet_line
    # A miss with no prerequisite below it is followed by a second question on the same objective.
    assert r.next_item is not None and r.next_item.objective_code == "o0"
    assert not r.done


def test_a_single_miss_never_drops_a_prior_below_the_not_yet_line_exhaustively() -> None:
    """Every answer sequence up to length 6 on a 3-objective chain: any objective with fewer than
    two direct misses is above the not-yet line and never marked not-yet."""
    graph = _chain(3)
    for n in range(1, 7):
        for answers in itertools.product([True, False], repeat=n):
            r, obs = _run(graph, list(answers))
            for o in r.objectives:
                if o.incorrect < CFG.min_consistent:
                    assert o.value >= CFG.not_yet_line, (answers, o)
                    assert o.status is not pl.PlacementStatus.NOT_YET, (answers, o)


def test_two_consistent_misses_mark_not_yet() -> None:
    r, _ = _run(_chain(3), [False, False])
    entry = r.get("o0")
    assert entry is not None and entry.status is pl.PlacementStatus.NOT_YET
    assert entry.value < CFG.not_yet_line and entry.incorrect == 2
    assert r.done and r.stop_reason is pl.StopReason.FRONTIER_RESOLVED
    assert r.frontier == ("o0",)


def test_one_answer_moves_a_prior_by_at_most_the_cap() -> None:
    rng = random.Random(11)  # noqa: S311 (synthetic test data, not cryptographic)
    graph = _chain(6)
    for _ in range(200):
        r, _ = _run(graph, [rng.random() < 0.5 for _ in range(12)])
        for before, after in zip(r.priors_before, r.priors_after, strict=True):
            assert abs(after - before) <= CFG.max_step + 1e-9


def test_hits_step_up_and_misses_step_down_the_prerequisite_dag() -> None:
    graph = CurriculumGraph(
        (
            ObjectiveInfo("a", "La", (), 0),
            ObjectiveInfo("b", "Lb", ("a",), 1),
            ObjectiveInfo("c", "Lc", ("b",), 2),
        )
    )
    items = _items(graph)
    first = pl.place(graph, items, [])
    assert first.next_item == pl.NextItem("a", "a-q0")  # the grade's entry objective
    assert first.chain_from_sequence is False
    up = pl.place(graph, items, [pl.Observation("a", "a-q0", True, 0)])
    assert up.next_item is not None and up.next_item.objective_code == "b"
    down = pl.place(
        graph,
        items,
        [pl.Observation("a", "a-q0", True, 0), pl.Observation("b", "b-q0", False, 1)],
    )
    assert down.next_item is not None and down.next_item.objective_code == "a"


def test_secure_infers_its_unasked_prerequisites_with_provenance() -> None:
    graph = CurriculumGraph(
        (
            ObjectiveInfo("a", "La", (), 0),
            ObjectiveInfo("b", "Lb", ("a",), 1),
            ObjectiveInfo("c", "Lc", ("b",), 2),
        )
    )
    items = {"a": (), "b": ("b-q0", "b-q1"), "c": ("c-q0",)}  # "a" has nothing to ask
    obs = [pl.Observation("b", "b-q0", True, 0), pl.Observation("b", "b-q1", True, 1)]
    r = pl.place(graph, items, obs)
    b, a = r.get("b"), r.get("a")
    assert b is not None and b.status is pl.PlacementStatus.SECURE and b.item_refs == obs_refs(obs)
    assert a is not None and a.status is pl.PlacementStatus.SECURE and a.inferred_from == "b"
    assert a.item_refs == () and a.uncertainty == CFG.inferred_uncertainty


def obs_refs(obs: list[pl.Observation]) -> tuple[str, ...]:
    return tuple(o.item_ref for o in obs)


def test_stop_rule_max_items_and_uncertainty() -> None:
    graph = _chain(30)
    r, obs = _run(graph, [True] * 40)
    assert r.done and len(obs) == CFG.max_items and r.stop_reason is pl.StopReason.MAX_ITEMS
    # A learner who knows everything on a short chain: resolved well before the cap.
    r, obs = _run(_chain(4), [True] * 40)
    assert r.stop_reason is pl.StopReason.FRONTIER_RESOLVED and len(obs) < CFG.max_items
    assert r.placement_uncertainty <= CFG.stop_uncertainty
    assert all(o.status is pl.PlacementStatus.SECURE for o in r.objectives)
    # Uncertainty is exposed per objective and narrows only with consistent evidence.
    mixed, _ = _run(_chain(1), [True, False])
    only = mixed.get("o0")
    assert only is not None and only.uncertainty == 1.0


def test_nothing_to_ask_means_no_placement() -> None:
    r = pl.place(_chain(3), {}, [])
    assert r.next_item is None and r.stop_reason is pl.StopReason.ITEMS_EXHAUSTED
    empty = pl.place(CurriculumGraph(()), {}, [])
    assert empty.next_item is None


def test_placement_converges_on_simulated_learners() -> None:
    """SIMULATION (synthetic learners with known ability), not a learning-outcome study."""
    for scenario in placement_eval.scenarios():
        score = placement_eval.evaluate(scenario, learners=400, seed=7)
        assert not placement_eval.failures(score), score
    # Perfect answerers are placed exactly on a chain the cap can cover.
    scenario = placement_eval.scenarios()[0]
    codes = [o.objective_code for o in scenario.graph.objectives]
    items = _items(scenario.graph)
    for k in range(len(codes) + 1):
        known = frozenset(codes[:k])
        obs: list[pl.Observation] = []
        while not (r := pl.place(scenario.graph, items, obs)).done and r.next_item is not None:
            nxt = r.next_item
            obs.append(
                pl.Observation(nxt.objective_code, nxt.item_ref, nxt.objective_code in known, 0)
            )
        start = codes.index(r.frontier[0]) if r.frontier else len(codes)
        assert start == k, (k, r)


def test_the_eval_script_reports_and_passes() -> None:
    assert placement_eval.main(["--learners", "300"]) == 0


# ------------------------------------------------------- the aggregate + decision engine


def _provenance(status: str, **kw: object) -> PriorProvenance:
    return PriorProvenance(
        source="diagnostic",
        placement_id="placement-x",
        status=status,
        value=float(kw.get("value", 0.8)),  # type: ignore[arg-type]
        uncertainty=0.49,
        item_refs=("q1", "q2"),
        correct=2 if status == "secure" else 0,
        incorrect=0 if status == "secure" else 2,
        recorded_at=100.0,
    )


def test_seeded_priors_never_override_practice() -> None:
    k = StudentKnowledge("s")
    assert k.seed_prior("o0", _provenance("secure")) is True
    assert k.objectives["o0"].placed_secure
    k.objectives["o0"].attempts = 1
    assert k.objectives["o0"].placed_secure is False  # practice now speaks for it
    assert k.seed_prior("o0", _provenance("not_yet", value=0.2)) is False
    assert k.objectives["o0"].mastery.value == pytest.approx(0.8)


def test_diagnostic_evidence_is_distinguishable_and_not_an_attempt() -> None:
    k = StudentKnowledge("s")
    ev = k.record_diagnostic(
        evidence_id="e1",
        objective_code="o0",
        item_ref="q1",
        placement_id="placement-x",
        correct=False,
        misconception_hits=(),
        response_time_ms=0,
        prior_before=0.5,
        prior_after=0.35,
        now=1.0,
    )
    assert ev.context is InteractionContext.DIAGNOSTIC and ev.session_id == "placement-x"
    assert "o0" not in k.objectives  # no attempt, no misconception, no review scheduled


def test_decision_engine_skips_placed_objectives_and_says_why() -> None:
    graph = _chain(3)
    k = StudentKnowledge("s")
    k.seed_prior("o0", _provenance("secure"))
    k.seed_prior("o1", _provenance("not_yet", value=0.2))
    d = select_next(k, graph, DecisionConfig(), now=1000.0)
    assert d.kind is DecisionKind.TEACH and d.objective_code == "o1"
    codes = [r.code for step in d.rationale for r in step.reasons]
    assert codes == [
        ReasonCode.READY_FOR_NEW,
        ReasonCode.DIAGNOSTIC_PLACEMENT,
        ReasonCode.PLACED_ABOVE,
    ]
    placed = dict(d.rationale[0].reasons[1].params)
    assert placed["status"] == "not_yet" and placed["incorrect"] == 2
    # The English trace note is unchanged in shape; the structured reasons sit beside it.
    assert d.rationale[0].rule_id == "select_eligible"


def test_without_a_placement_the_engine_is_unchanged() -> None:
    graph = _chain(2)
    d = select_next(StudentKnowledge("s"), graph, DecisionConfig(), now=0.0)
    assert d.kind is DecisionKind.TEACH and d.objective_code == "o0"
    assert d.rationale[0].note == "o0 state=not_started"


def test_provenance_round_trips_through_the_existing_json_column() -> None:
    k = StudentKnowledge("s")
    k.seed_prior("o0", _provenance("secure"))
    values = objective_column_values(k.objectives["o0"])
    assert values["confidence"]["prior_provenance"]["source"] == "diagnostic"
    row = ObjectiveMasteryRow(id="r", knowledge_id="k", student_ref="s", **values)
    back = objective_from_row(row)
    assert back.provenance == k.objectives["o0"].provenance
    # A learner without a placement keeps the exact previous JSON shape.
    plain = objective_column_values(StudentKnowledge("t").ensure_objective("o0"))
    assert set(plain["confidence"]) == {"self_reported", "sampled_at"}


# --------------------------------------------------------------------------- the API


def _h(role: str, sub: str) -> dict[str, str]:
    token = sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


def _app(publish: bool = True) -> tuple[FastAPI, TestClient]:
    app = create_app(Settings(database_url="", jwt_dev_secret=_SECRET))
    if publish:
        _publish_fractions(app)
    return app, TestClient(app)


def _answer(client: TestClient, ref: str, item_ref: str, option: int) -> object:
    return client.post(
        f"/v1/learning/students/{ref}/placement:answer",
        json={"item_ref": item_ref, "option": option},
        headers=_h("student", ref),
    )


def test_no_published_items_is_an_honest_no_placement_state() -> None:
    _, client = _app(publish=False)
    r = client.get("/v1/learning/students/pl-none/placement", headers=_h("student", "pl-none"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "unavailable" and body["reason"] == "no_published_items"
    assert body["next_item"] is None and body["objectives"] == []
    late = _answer(client, "pl-none", "anything", 0)
    assert late.status_code == 409  # type: ignore[attr-defined]


def test_placement_end_to_end_on_the_fixture_lesson() -> None:
    app, client = _app()
    ref = "pl-stu"
    h = _h("student", ref)
    first = client.get(f"/v1/learning/students/{ref}/placement", headers=h).json()
    assert first["status"] == "available" and first["items_used"] == 0
    item = first["next_item"]
    assert item["objective_code"] == OBJECTIVE_CODE and item["options"]
    assert "correct_option" not in item  # never the answer key

    # One wrong answer: recorded, not a verdict, and the next question is on the same objective.
    one = _answer(client, ref, item["item_ref"], 1).json()  # type: ignore[attr-defined]
    assert one["status"] == "in_progress"
    placed = one["objectives"][0]
    assert placed["status"] == "uncertain" and placed["prior"] >= CFG.not_yet_line
    assert placed["source"] == "diagnostic" and placed["item_refs"] == [item["item_ref"]]
    # A retry of the same answer is not recounted.
    again = _answer(client, ref, item["item_ref"], 1).json()  # type: ignore[attr-defined]
    assert again["duplicate"] is True and again["items_used"] == 1
    # Anything other than the current question is refused.
    wrong_item = _answer(client, ref, "not-the-question", 0)
    assert wrong_item.status_code == 409  # type: ignore[attr-defined]
    assert wrong_item.json()["code"] == "PLACEMENT_ITEM_MISMATCH"  # type: ignore[attr-defined]

    # The second consistent miss marks not-yet and ends the placement (one objective published).
    two = _answer(client, ref, one["next_item"]["item_ref"], 1).json()  # type: ignore[attr-defined]
    assert two["status"] == "completed" and two["stop_reason"] == "frontier_resolved"
    assert two["objectives"][0]["status"] == "not_yet"
    assert two["start_objective"] == OBJECTIVE_CODE
    done = _answer(client, ref, "x", 0)
    assert done.status_code == 409  # type: ignore[attr-defined]

    # Provenance on the seeded prior; the objective is still unpractised.
    knowledge = client.get(f"/v1/learning/students/{ref}/knowledge", headers=h).json()
    obj = knowledge["objectives"][OBJECTIVE_CODE]
    assert obj["state"] == "not_started" and obj["mastery"] < CFG.not_yet_line
    with LearningUnitOfWork(app.state.learning_session_factory) as uow:
        stored = uow.knowledge.get(ref)
    assert stored is not None
    prov = stored.objectives[OBJECTIVE_CODE].provenance
    assert prov is not None and prov.source == "diagnostic" and prov.status == "not_yet"
    assert prov.placement_id == two["placement_id"] and prov.incorrect == 2
    assert prov.recorded_at > 0 and len(prov.item_refs) == 2
    # Every diagnostic answer is evidence of its own kind, under the placement's id.
    assert [(e.context, e.session_id) for e in stored.evidence] == [
        (InteractionContext.DIAGNOSTIC, two["placement_id"])
    ] * 2
    assert stored.objectives[OBJECTIVE_CODE].attempts == 0

    # Diagnostic vs practice evidence: the assessment history tells them apart.
    plan = client.get(f"/v1/learning/students/{ref}/ai-teacher/plan", headers=h).json()
    rec = plan["recommendations"][0]
    assert rec["is_next_action"] and rec["objective_code"] == OBJECTIVE_CODE
    assert rec["evidence"]["diagnostic"] == 2 and rec["evidence"]["practice"] == 0
    assert rec["estimate_source"] == "diagnostic"
    codes = [r["code"] for r in plan["next_action"]["reasons"]]
    assert codes == ["ready_for_new", "diagnostic_placement"]
    assert plan["placement"]["placed"] is True and plan["placement"]["objectives_not_yet"] == 1


def test_secure_placement_moves_the_learner_past_the_objective() -> None:
    _, client = _app()
    ref = "pl-strong"
    h = _h("student", ref)
    nxt = client.get(f"/v1/learning/students/{ref}/placement", headers=h).json()["next_item"]
    one = _answer(client, ref, nxt["item_ref"], 0).json()  # type: ignore[attr-defined]
    assert one["objectives"][0]["status"] == "uncertain"  # one right answer is not enough either
    two = _answer(client, ref, one["next_item"]["item_ref"], 0).json()  # type: ignore[attr-defined]
    assert two["status"] == "completed" and two["objectives"][0]["status"] == "secure"
    plan = client.get(f"/v1/learning/students/{ref}/ai-teacher/plan", headers=h).json()
    assert plan["next_action"]["kind"] == "complete"
    assert [r["code"] for r in plan["next_action"]["reasons"]] == ["all_mastered", "placed_above"]


def test_practice_history_makes_a_learner_ineligible_and_evidence_kinds_stay_apart() -> None:
    app, client = _app()
    ref = "pl-hist"
    h = _h("student", ref)
    sid = client.post("/v1/learning/sessions", json={"student_ref": ref}, headers=h).json()[
        "session_id"
    ]
    client.post(f"/v1/learning/sessions/{sid}:next", headers=h)
    client.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h
    )
    client.post(
        f"/v1/learning/sessions/{sid}:answer",
        json={"objective_code": OBJECTIVE_CODE, "item_ref": "p1-one-of-four", "option": 0},
        headers=h,
    )
    body = client.get(f"/v1/learning/students/{ref}/placement", headers=h).json()
    assert body["status"] == "not_eligible" and body["reason"] == "has_history"
    refused = _answer(client, ref, "p1-one-of-four", 0)
    assert refused.status_code == 409  # type: ignore[attr-defined]
    assert refused.json()["code"] == "PLACEMENT_NOT_ELIGIBLE"  # type: ignore[attr-defined]
    with LearningUnitOfWork(app.state.learning_session_factory) as uow:
        stored = uow.knowledge.get(ref)
    assert stored is not None
    assert stored.evidence
    assert all(e.context is not InteractionContext.DIAGNOSTIC for e in stored.evidence)


def test_placement_is_idor_guarded() -> None:
    _, client = _app()
    assert client.get("/v1/learning/students/pl-a/placement").status_code == 401
    other = client.get("/v1/learning/students/pl-a/placement", headers=_h("student", "pl-b"))
    assert other.status_code == 403
    answer = client.post(
        "/v1/learning/students/pl-a/placement:answer",
        json={"item_ref": "p1-one-of-four", "option": 0},
        headers=_h("student", "pl-b"),
    )
    assert answer.status_code == 403
    mentor = client.get("/v1/learning/students/pl-a/placement", headers=_h("mentor", "m1"))
    assert mentor.status_code == 200
