"""Diagnostic placement (pure, deterministic) — where a learner with no history should start.

A short adaptive diagnostic over published items that walks the prerequisite DAG and seeds
per-objective knowledge priors (GLOBAL_PRODUCT_SCOPE §C, PROJECT_TALEEM_MASTER_SCOPE §20 "Learning
intelligence": diagnostic placement). Everything here is a fold over the observations, so the
service can rebuild the placement from the durable diagnostic evidence on every request — there is
no placement table and no hidden state.

The walk (a staircase over the DAG):

- start at the grade's entry objective (the first objective of the published curriculum);
- on a hit, step **up** to an unresolved objective that builds on the one just answered;
- on a miss, step **down** to an unresolved prerequisite (or ask a second item on the same
  objective when it has none) — so a miss is always followed by more evidence, never a verdict;
- when the walk has nowhere to go, probe the unresolved *frontier*: objectives whose prerequisites
  are all placed secure.

The safeguards the scope asks for:

- **BKT with slip/guess.** Each answer is a Bayesian Knowledge Tracing update (``BKTEstimator``)
  with diagnostic slip/guess and no learning transition (a diagnostic does not teach).
- **A per-answer cap.** One answer moves an objective's prior by at most ``max_step``.
- **Never "not yet" from one answer.** ``not_yet`` needs ``min_consistent`` (2) direct misses, the
  last ``min_consistent`` direct answers all wrong, and a prior below ``not_yet_line``. With fewer
  misses the prior is floored at ``not_yet_line`` (the cap alone already keeps a single miss above
  it — the floor makes that a guarantee, not an accident of the numbers).
- **Secure needs corroboration.** ``secure`` needs the last direct answer right, a prior at or
  above ``secure_line``, and at least ``min_consistent`` net consistent observations — direct hits
  plus hits on objectives that build on it, minus direct misses. Prerequisites of a secure objective
  that were never asked are *inferred* secure, and say so (``inferred_from``).
- **Uncertainty is explicit.** Each objective's uncertainty shrinks only with *net consistent*
  evidence (mixed answers keep it wide).

Stop rule: ``max_items`` answered, or the placement uncertainty — the widest uncertainty on the
frontier — falls to ``stop_uncertainty`` (every frontier objective resolved), or no item is left to
ask. Every prior carries provenance (source=diagnostic, item refs, counts, timestamp).

When the curriculum declares no prerequisite edges at all (today's published graph is ordered and
prerequisite-free), the curriculum *sequence* is used as the chain: each objective's predecessor is
its prerequisite for the walk and for inference. This is stated, not hidden: ``chain_from_sequence``
on the result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import StrEnum

from .decision import CurriculumGraph, ObjectiveInfo
from .estimator import BKTEstimator, BKTParams
from .values import Mastery, clamp01

PLACEMENT_SOURCE = "diagnostic"
PLACEMENT_SESSION_PREFIX = "placement-"


class PlacementStatus(StrEnum):
    SECURE = "secure"
    NOT_YET = "not_yet"
    UNCERTAIN = "uncertain"


class StopReason(StrEnum):
    MAX_ITEMS = "max_items"
    FRONTIER_RESOLVED = "frontier_resolved"
    ITEMS_EXHAUSTED = "items_exhausted"


@dataclass(frozen=True)
class PlacementConfig:
    max_items: int = 12
    start_prior: float = 0.5  # neutral: the diagnostic does not assume the cold-start p_l0
    max_step: float = 0.15  # the most one answer may move a prior
    not_yet_line: float = 0.30
    secure_line: float = 0.60
    min_consistent: int = 2
    stop_uncertainty: float = 0.5
    uncertainty_decay: float = 0.7  # per net consistent observation (as the practice estimator)
    uncertainty_floor: float = 0.05
    inferred_uncertainty: float = 0.6  # an inferred-secure prior is honestly less certain
    p_slip: float = 0.15
    p_guess: float = 0.25  # four-option items

    def bkt(self) -> BKTParams:
        # No learning transition: answering a diagnostic item is not a teaching opportunity.
        return BKTParams(p_slip=self.p_slip, p_guess=self.p_guess, p_transit=0.0, p_l0=0.5)


@dataclass(frozen=True)
class Observation:
    objective_code: str
    item_ref: str
    correct: bool
    at: float


@dataclass(frozen=True)
class ObjectivePlacement:
    """The seeded prior for one objective, with its confidence and provenance."""

    objective_code: str
    status: PlacementStatus
    value: float
    uncertainty: float
    correct: int = 0  # direct diagnostic answers on this objective
    incorrect: int = 0
    support: int = 0  # direct hits + hits on objectives that build on this one
    item_refs: tuple[str, ...] = ()
    inferred_from: str | None = None
    observed_at: float = 0.0

    @property
    def observed(self) -> bool:
        return bool(self.correct or self.incorrect)


@dataclass(frozen=True)
class NextItem:
    objective_code: str
    item_ref: str


@dataclass(frozen=True)
class PlacementResult:
    objectives: tuple[ObjectivePlacement, ...]
    items_used: int
    next_item: NextItem | None
    stop_reason: StopReason | None
    placement_uncertainty: float
    frontier: tuple[str, ...]  # where learning should start (unresolved or not-yet, prereqs secure)
    chain_from_sequence: bool
    priors_before: tuple[float, ...] = field(default_factory=tuple)  # per observation, in order
    priors_after: tuple[float, ...] = field(default_factory=tuple)

    @property
    def done(self) -> bool:
        return self.stop_reason is not None

    def get(self, code: str) -> ObjectivePlacement | None:
        return next((o for o in self.objectives if o.objective_code == code), None)


# ------------------------------------------------------------------------------------- the DAG


class _Dag:
    """Effective prerequisite relation for placement (explicit edges, else the sequence chain)."""

    def __init__(self, graph: CurriculumGraph) -> None:
        self.ordered: tuple[ObjectiveInfo, ...] = tuple(
            sorted(graph.objectives, key=lambda o: (o.sequence, o.objective_code))
        )
        codes = {o.objective_code for o in self.ordered}
        explicit = any(p in codes for o in self.ordered for p in o.prerequisites)
        self.chain = not explicit
        self.seq = {o.objective_code: i for i, o in enumerate(self.ordered)}
        self.prereqs: dict[str, tuple[str, ...]] = {}
        for i, o in enumerate(self.ordered):
            if self.chain:
                self.prereqs[o.objective_code] = (
                    (self.ordered[i - 1].objective_code,) if i > 0 else ()
                )
            else:
                self.prereqs[o.objective_code] = tuple(p for p in o.prerequisites if p in codes)
        self.dependents: dict[str, list[str]] = {o.objective_code: [] for o in self.ordered}
        for code, pres in self.prereqs.items():
            for p in pres:
                self.dependents[p].append(code)
        for deps in self.dependents.values():
            deps.sort(key=self.seq.__getitem__)

    def codes(self) -> list[str]:
        return [o.objective_code for o in self.ordered]

    def ancestors(self, code: str) -> set[str]:
        out: set[str] = set()
        stack = list(self.prereqs.get(code, ()))
        while stack:
            c = stack.pop()
            if c not in out:
                out.add(c)
                stack.extend(self.prereqs.get(c, ()))
        return out

    def descendants(self, code: str) -> set[str]:
        out: set[str] = set()
        stack = list(self.dependents.get(code, ()))
        while stack:
            c = stack.pop()
            if c not in out:
                out.add(c)
                stack.extend(self.dependents.get(c, ()))
        return out

    def entry(self) -> str | None:
        return self.ordered[0].objective_code if self.ordered else None


# ----------------------------------------------------------------------------------- the fold


def _capped_update(
    estimator: BKTEstimator, params: BKTParams, prior: float, correct: bool, cfg: PlacementConfig
) -> float:
    posterior = estimator.update(Mastery(prior, 1.0), correct=correct, params=params).value
    step = max(-cfg.max_step, min(cfg.max_step, posterior - prior))
    return clamp01(prior + step)


def _status(
    value: float,
    direct: list[bool],
    support: int,
    cfg: PlacementConfig,
) -> PlacementStatus:
    k = cfg.min_consistent
    misses = direct.count(False)
    if misses >= k and len(direct) >= k and not any(direct[-k:]) and value < cfg.not_yet_line:
        return PlacementStatus.NOT_YET
    if direct and direct[-1] and value >= cfg.secure_line and support - misses >= k:
        return PlacementStatus.SECURE
    return PlacementStatus.UNCERTAIN


def place(
    graph: CurriculumGraph,
    items: dict[str, tuple[str, ...]],
    observations: list[Observation],
    config: PlacementConfig | None = None,
) -> PlacementResult:
    """Fold the observations into per-objective priors, and choose the next item (or stop).

    ``items`` maps objective code -> the diagnostic item refs available for it, in asking order.
    Objectives without items can still be *inferred* secure, but are never asked about.
    """
    cfg = config or PlacementConfig()
    dag = _Dag(graph)
    estimator = BKTEstimator(cfg.bkt())
    params = cfg.bkt()

    values: dict[str, float] = {}
    direct: dict[str, list[bool]] = {}
    refs: dict[str, list[str]] = {}
    last_at: dict[str, float] = {}
    before: list[float] = []
    after: list[float] = []
    known_codes = set(dag.codes())
    for ob in observations:
        if ob.objective_code not in known_codes:
            continue  # an objective unpublished since it was asked: its evidence stays on record
        prior = values.get(ob.objective_code, cfg.start_prior)
        post = _capped_update(estimator, params, prior, ob.correct, cfg)
        answers = direct.setdefault(ob.objective_code, [])
        answers.append(ob.correct)
        if answers.count(False) < cfg.min_consistent:
            post = max(post, cfg.not_yet_line)  # one miss is never a verdict (floor, guaranteed)
        values[ob.objective_code] = post
        refs.setdefault(ob.objective_code, []).append(ob.item_ref)
        last_at[ob.objective_code] = ob.at
        before.append(prior)
        after.append(post)

    # Support: direct hits on an objective plus hits on anything that builds on it.
    hits = {c: a.count(True) for c, a in direct.items()}
    placements: dict[str, ObjectivePlacement] = {}
    for code in dag.codes():
        if code not in direct:
            continue
        answers = direct[code]
        support = hits.get(code, 0) + sum(hits.get(d, 0) for d in dag.descendants(code))
        misses = answers.count(False)
        # Net consistent evidence in the direction of the latest answer (mixed answers keep the
        # estimate wide; agreeing answers narrow it).
        net = support - misses if answers[-1] else misses - answers.count(True)
        net = max(0, net)
        uncertainty = max(cfg.uncertainty_floor, cfg.uncertainty_decay**net)
        value = values[code]
        placements[code] = ObjectivePlacement(
            objective_code=code,
            status=_status(value, answers, support, cfg),
            value=round(value, 4),
            uncertainty=round(uncertainty, 4),
            correct=answers.count(True),
            incorrect=misses,
            support=support,
            item_refs=tuple(refs[code]),
            observed_at=last_at[code],
        )

    # Inference: the prerequisites of a directly secure objective are secure too (DAG closure) —
    # unasked ones, and asked ones still uncertain (e.g. one early slip). A prerequisite with its
    # own consistent misses stays not-yet: the conflict is resolved toward teaching it.
    for code in [c for c, p in placements.items() if p.status is PlacementStatus.SECURE]:
        for anc in sorted(dag.ancestors(code), key=dag.seq.__getitem__):
            seen = placements.get(anc)
            if seen is not None:
                if seen.status is PlacementStatus.UNCERTAIN:
                    placements[anc] = replace(
                        seen,
                        status=PlacementStatus.SECURE,
                        value=round(max(seen.value, cfg.secure_line), 4),
                        inferred_from=code,
                    )
                continue
            placements[anc] = ObjectivePlacement(
                objective_code=anc,
                status=PlacementStatus.SECURE,
                value=round(max(cfg.secure_line, values[code]), 4),
                uncertainty=cfg.inferred_uncertainty,
                inferred_from=code,
                observed_at=last_at[code],
            )

    def secure(code: str) -> bool:
        p = placements.get(code)
        return p is not None and p.status is PlacementStatus.SECURE

    used = {r for rs in refs.values() for r in rs}

    def next_ref(code: str) -> str | None:
        return next((r for r in items.get(code, ()) if r not in used), None)

    def resolved(code: str) -> bool:
        p = placements.get(code)
        return (p is not None and p.status is not PlacementStatus.UNCERTAIN) or next_ref(
            code
        ) is None

    frontier = tuple(
        c for c in dag.codes() if not secure(c) and all(secure(p) for p in dag.prereqs[c])
    )
    # The placement's uncertainty is the widest uncertainty among frontier objectives that are not
    # yet resolved (never asked = 1.0). It reaches the stop threshold when the frontier is placed.
    open_frontier = [c for c in frontier if not resolved(c)]
    unc = [placements[c].uncertainty if c in placements else 1.0 for c in open_frontier]
    placement_uncertainty = round(max(unc), 4) if unc else 0.0
    open_frontier = [c for c, u in zip(open_frontier, unc, strict=True) if u > cfg.stop_uncertainty]

    ordered = sorted(placements.values(), key=lambda p: dag.seq[p.objective_code])
    n = len(observations)

    def result(nxt: NextItem | None, stop: StopReason | None) -> PlacementResult:
        return PlacementResult(
            objectives=tuple(ordered),
            items_used=n,
            next_item=nxt,
            stop_reason=stop,
            placement_uncertainty=placement_uncertainty,
            frontier=frontier,
            chain_from_sequence=dag.chain,
            priors_before=tuple(before),
            priors_after=tuple(after),
        )

    if not any(items.get(c) for c in dag.codes()):
        return result(None, StopReason.ITEMS_EXHAUSTED)
    if n >= cfg.max_items:
        return result(None, StopReason.MAX_ITEMS)
    if n and placement_uncertainty <= cfg.stop_uncertainty:
        return result(None, StopReason.FRONTIER_RESOLVED)

    target = _walk(dag, observations, resolved)
    if target is None:
        target = open_frontier[0] if open_frontier else None
    if target is None:
        # Nothing on the frontier can be asked: fall back to any unresolved objective, in order.
        target = next((c for c in dag.codes() if not resolved(c)), None)
    if target is None:
        return result(None, StopReason.ITEMS_EXHAUSTED if n == 0 else StopReason.FRONTIER_RESOLVED)
    ref = next_ref(target)
    if ref is None:  # unreachable: resolved() is False only while an item remains
        return result(None, StopReason.ITEMS_EXHAUSTED)
    return result(NextItem(target, ref), None)


def _walk(
    dag: _Dag, observations: list[Observation], is_resolved: Callable[[str], bool]
) -> str | None:
    if not observations:
        entry = dag.entry()
        # The entry may have no items (unpublished); the frontier fallback then takes over.
        return entry if entry is not None and not is_resolved(entry) else None
    last = observations[-1]
    here = last.objective_code
    if here not in dag.seq:
        return None
    if last.correct:
        step = [d for d in dag.dependents[here] if not is_resolved(d)]
    else:
        step = sorted(
            (p for p in dag.prereqs[here] if not is_resolved(p)),
            key=dag.seq.__getitem__,
            reverse=True,  # the nearest prerequisite first
        )
    if step:
        return step[0]
    return here if not is_resolved(here) else None
