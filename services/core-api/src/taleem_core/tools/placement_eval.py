"""Diagnostic-placement evaluation on SIMULATED learners (domain/placement.py).

**This is a simulation, not a learning-outcome study.** Every learner here is synthetic: a known,
down-closed set of objectives they "know", answering each item correctly with probability
``1 - slip`` if they know its objective and ``guess`` otherwise. The harness drives the production
placement fold (``placement.place``) item by item, exactly as the service does, and scores the
result against the learner's true state. It says how well the walk + stop rule recover a *known*
ability under that answer model; it says nothing about whether real children learn more, whether
real items behave like this, or whether the slip/guess values fit real data.

Scenarios: an ordered prerequisite-free curriculum (today's published graph shape, walked as a
chain), a longer chain that the 12-item cap cannot fully cover, and a branching prerequisite DAG.

Metrics (per scenario):
- ``start_exact`` / ``start_within_1``: the placement's first frontier objective is the learner's
  true first not-known objective (or one step from it, in curriculum order);
- ``decided_accuracy``: of the objectives placed secure or not-yet (inferred included), the share
  that match the truth; ``coverage``: the share of objectives that got a verdict at all;
- ``false_not_yet``: objectives the learner KNOWS that were placed not-yet — the harmful error the
  two-consistent-misses rule exists to prevent;
- ``items_mean`` / ``items_max``: diagnostic length.

Usage:
    python -m taleem_core.tools.placement_eval                 # table
    python -m taleem_core.tools.placement_eval --json out.json --learners 2000 --seed 7

Exit code is non-zero if a scenario misses its floor (see ``FLOORS``) — a regression guard for the
simulation, not a claim about real learners.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from ..contexts.learning.domain import placement as pl
from ..contexts.learning.domain.decision import CurriculumGraph, ObjectiveInfo

SLIP = 0.10
GUESS = 0.25
ITEMS_PER_OBJECTIVE = 5


@dataclass(frozen=True)
class Scenario:
    name: str
    graph: CurriculumGraph
    # rng -> the set of objective codes this synthetic learner knows (down-closed in the DAG).
    learner: Callable[[random.Random], frozenset[str]]


@dataclass
class Score:
    scenario: str
    learners: int
    start_exact: float
    start_within_1: float
    decided_accuracy: float
    coverage: float
    false_not_yet: float
    items_mean: float
    items_max: int


# Floors on the simulated metrics (regression guard; see the module docstring).
FLOORS: dict[str, dict[str, float]] = {
    "chain-8 (ordered, prerequisite-free)": {
        "start_within_1": 0.85,
        "decided_accuracy": 0.9,
        "false_not_yet_max": 0.03,
    },
    "chain-20 (longer than the item cap)": {"decided_accuracy": 0.85, "false_not_yet_max": 0.03},
    "dag-9 (branching prerequisites)": {"decided_accuracy": 0.85, "false_not_yet_max": 0.05},
}


def _chain(n: int) -> Scenario:
    graph = CurriculumGraph(tuple(ObjectiveInfo(f"c{i:02d}", f"L{i}", (), i) for i in range(n)))
    codes = [o.objective_code for o in graph.objectives]

    def learner(rng: random.Random) -> frozenset[str]:
        return frozenset(codes[: rng.randint(0, n)])

    label = (
        "chain-8 (ordered, prerequisite-free)"
        if n == 8
        else f"chain-{n} (longer than the item cap)"
    )
    return Scenario(label, graph, learner)


def _dag() -> Scenario:
    #        a
    #      /   \
    #     b     c
    #    / \     \
    #   d   e     f
    #    \ /     /
    #     g     h
    #      \   /
    #        i
    edges = {
        "a": (),
        "b": ("a",),
        "c": ("a",),
        "d": ("b",),
        "e": ("b",),
        "f": ("c",),
        "g": ("d", "e"),
        "h": ("f",),
        "i": ("g", "h"),
    }
    graph = CurriculumGraph(
        tuple(
            ObjectiveInfo(code, f"L-{code}", pre, seq)
            for seq, (code, pre) in enumerate(edges.items())
        )
    )

    def learner(rng: random.Random) -> frozenset[str]:
        p = rng.random()  # the learner's overall ability
        known: set[str] = set()
        for code, pre in edges.items():
            if all(x in known for x in pre) and rng.random() < p:
                known.add(code)
        return frozenset(known)

    return Scenario("dag-9 (branching prerequisites)", graph, learner)


def scenarios() -> list[Scenario]:
    return [_chain(8), _chain(20), _dag()]


def _true_start(graph: CurriculumGraph, known: frozenset[str]) -> int:
    """Index (curriculum order) of the first objective not known whose prerequisites are known."""
    ordered = sorted(graph.objectives, key=lambda o: o.sequence)
    chain = not any(o.prerequisites for o in ordered)
    for i, o in enumerate(ordered):
        pre = (ordered[i - 1].objective_code,) if chain and i else o.prerequisites
        if o.objective_code not in known and all(p in known for p in pre):
            return i
    return len(ordered)


def simulate_one(
    scenario: Scenario,
    known: frozenset[str],
    rng: random.Random,
    config: pl.PlacementConfig | None = None,
) -> pl.PlacementResult:
    items = {
        o.objective_code: tuple(f"{o.objective_code}-q{j}" for j in range(ITEMS_PER_OBJECTIVE))
        for o in scenario.graph.objectives
    }
    observations: list[pl.Observation] = []
    while True:
        result = pl.place(scenario.graph, items, observations, config)
        if result.done or result.next_item is None:
            return result
        nxt = result.next_item
        p_correct = 1.0 - SLIP if nxt.objective_code in known else GUESS
        observations.append(
            pl.Observation(
                nxt.objective_code, nxt.item_ref, rng.random() < p_correct, float(len(observations))
            )
        )


def evaluate(scenario: Scenario, learners: int, seed: int) -> Score:
    rng = random.Random(seed)  # noqa: S311 (synthetic simulation, not cryptographic)
    ordered = [
        o.objective_code for o in sorted(scenario.graph.objectives, key=lambda o: o.sequence)
    ]
    index = {c: i for i, c in enumerate(ordered)}
    exact = within = decided = correct = known_total = false_not_yet = 0
    items: list[int] = []
    for _ in range(learners):
        known = scenario.learner(rng)
        result = simulate_one(scenario, known, rng)
        items.append(result.items_used)
        truth = _true_start(scenario.graph, known)
        start = index[result.frontier[0]] if result.frontier else len(ordered)
        exact += start == truth
        within += abs(start - truth) <= 1
        known_total += len(known)
        for o in result.objectives:
            if o.status is pl.PlacementStatus.UNCERTAIN:
                continue
            decided += 1
            correct += (o.status is pl.PlacementStatus.SECURE) == (o.objective_code in known)
            if o.status is pl.PlacementStatus.NOT_YET and o.objective_code in known:
                false_not_yet += 1
    n = max(1, learners)
    return Score(
        scenario=scenario.name,
        learners=learners,
        start_exact=round(exact / n, 4),
        start_within_1=round(within / n, 4),
        decided_accuracy=round(correct / decided, 4) if decided else 0.0,
        coverage=round(decided / (n * len(ordered)), 4),
        false_not_yet=round(false_not_yet / known_total, 4) if known_total else 0.0,
        items_mean=round(sum(items) / n, 2),
        items_max=max(items, default=0),
    )


def failures(score: Score) -> list[str]:
    floor = FLOORS.get(score.scenario, {})
    out: list[str] = []
    for metric, minimum in floor.items():
        if metric == "false_not_yet_max":
            if score.false_not_yet > minimum:
                out.append(f"false_not_yet {score.false_not_yet} > {minimum}")
        elif getattr(score, metric) < minimum:
            out.append(f"{metric} {getattr(score, metric)} < {minimum}")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    parser.add_argument("--learners", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--json", dest="json_path", default="")
    args = parser.parse_args(argv)

    print("SIMULATION — synthetic learners with a known ability; not a learning-outcome study.")
    print(f"answer model: slip={SLIP} guess={GUESS}; {ITEMS_PER_OBJECTIVE} items per objective")
    cfg = pl.PlacementConfig()
    print(
        f"placement: max_items={cfg.max_items} max_step={cfg.max_step} "
        f"not_yet_line={cfg.not_yet_line} secure_line={cfg.secure_line} "
        f"min_consistent={cfg.min_consistent} stop_uncertainty={cfg.stop_uncertainty}"
    )
    scores = [evaluate(s, args.learners, args.seed) for s in scenarios()]
    header = (
        f"{'scenario':40} {'start=':>7} {'start±1':>8} {'decided':>8} {'cover':>6} "
        f"{'falseNY':>8} {'items':>6} {'max':>4}"
    )
    print(header)
    bad: list[str] = []
    for s in scores:
        print(
            f"{s.scenario:40} {s.start_exact:7.3f} {s.start_within_1:8.3f} "
            f"{s.decided_accuracy:8.3f} {s.coverage:6.3f} {s.false_not_yet:8.3f} "
            f"{s.items_mean:6.2f} {s.items_max:4d}"
        )
        bad += [f"{s.scenario}: {f}" for f in failures(s)]
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump({"simulation": True, "scores": [asdict(s) for s in scores]}, fh, indent=2)
    for line in bad:
        print(f"BELOW FLOOR: {line}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
