"""PlacementService — diagnostic placement for a learner with no history (domain/placement.py).

Stateless by design: the placement is rebuilt on every request by folding the learner's durable
diagnostic evidence (``context=diagnostic``, ``session_id`` = the placement id) through the pure
``placement.place``. There is no placement table — the evidence record is the system of record,
the seeded priors live on the objective rows (with ``PriorProvenance`` in the existing
``confidence`` JSON), and each answer is one unit of work: append the diagnostic evidence, re-seed
the priors of every placed objective, publish the outbox events.

States (``status``):

- ``unavailable`` — no published lesson has a diagnostic item ("no placement possible yet"; today's
  reality with ~0 published lessons);
- ``not_eligible`` — the learner already has practice history (placement is for a cold start);
- ``available`` — eligible, nothing answered yet; ``next_item`` is the first question;
- ``in_progress`` — answered some; ``next_item`` is the next question;
- ``completed`` — the stop rule fired; the priors are seeded and the decision engine uses them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from ....platform import observability
from ....platform.errors import Problem, conflict
from ....platform.ids import uuid7
from ..adapters.persistence.uow import LearningUnitOfWork
from ..domain import events as ev
from ..domain import placement as pl
from ..domain.curriculum_view import ItemView, LessonView
from ..domain.decision import CurriculumGraph
from ..domain.knowledge import PriorProvenance, StudentKnowledge
from ..domain.scorer import evaluate
from ..domain.values import InteractionContext, Outcome
from .concurrency import ConcurrencyConflictError, retry_on_conflict
from .ports import CurriculumReadModel

_GraphSource = CurriculumGraph | Callable[[], CurriculumGraph]


def placement_observations(
    knowledge: StudentKnowledge | None,
) -> tuple[str | None, list[pl.Observation]]:
    """The learner's placement id and its observations, in answer order."""
    if knowledge is None:
        return None, []
    rows = [
        e
        for e in knowledge.evidence
        if e.context is InteractionContext.DIAGNOSTIC
        and e.session_id.startswith(pl.PLACEMENT_SESSION_PREFIX)
    ]
    if not rows:
        return None, []
    rows.sort(key=lambda e: (e.occurred_at, e.evidence_id))
    placement_id = rows[0].session_id
    obs = [
        pl.Observation(e.objective_code, e.item_ref, e.outcome is Outcome.CORRECT, e.occurred_at)
        for e in rows
        if e.session_id == placement_id
    ]
    return placement_id, obs


def has_practice_history(knowledge: StudentKnowledge | None) -> bool:
    if knowledge is None:
        return False
    if any(o.attempts for o in knowledge.objectives.values()):
        return True
    return any(
        not (
            e.context is InteractionContext.DIAGNOSTIC
            and e.session_id.startswith(pl.PLACEMENT_SESSION_PREFIX)
        )
        for e in knowledge.evidence
    )


class PlacementService:
    def __init__(
        self,
        uow_factory: Callable[[], LearningUnitOfWork],
        curriculum: CurriculumReadModel,
        graph: _GraphSource,
        clock: Callable[[], float],
        config: pl.PlacementConfig | None = None,
    ) -> None:
        self._uow = uow_factory
        self._curriculum = curriculum
        self._graph = graph
        self._now = clock
        self._cfg = config or pl.PlacementConfig()

    # ------------------------------------------------------------------------------ reads

    def status(self, student_ref: str) -> dict[str, Any]:
        graph, lessons = self._content()
        with self._uow() as uow:
            knowledge = uow.knowledge.get(student_ref)
        return self._view(student_ref, knowledge, graph, lessons)

    # ----------------------------------------------------------------------------- writes

    def answer(
        self, student_ref: str, *, item_ref: str, option: int, response_time_ms: int = 0
    ) -> dict[str, Any]:
        graph, lessons = self._content()
        items = _item_refs(graph, lessons)

        def _txn() -> dict[str, Any]:
            with self._uow() as uow:
                knowledge = uow.knowledge.get(student_ref) or StudentKnowledge(
                    student_ref=student_ref
                )
                placement_id, obs = placement_observations(knowledge)
                if placement_id is None and has_practice_history(knowledge):
                    raise Problem(
                        409,
                        "PLACEMENT_NOT_ELIGIBLE",
                        "Placement not available",
                        "placement is for a learner with no practice history",
                    )
                before = pl.place(graph, items, obs, self._cfg)
                if any(o.item_ref == item_ref for o in obs):
                    # A retried answer (offline replay, double tap): already recorded, no recount.
                    view = self._view(student_ref, knowledge, graph, lessons)
                    return {**view, "duplicate": True}
                if before.done or before.next_item is None:
                    raise Problem(
                        409,
                        "PLACEMENT_COMPLETE" if obs else "PLACEMENT_UNAVAILABLE",
                        "Placement not open",
                        "there is no diagnostic question to answer",
                    )
                if before.next_item.item_ref != item_ref:
                    raise Problem(
                        409,
                        "PLACEMENT_ITEM_MISMATCH",
                        "Not the current question",
                        "answer the question the placement is asking now",
                    )
                item = _find_item(lessons, before.next_item)
                if item is None:  # unpublished between the read and this write
                    raise conflict("the diagnostic question is no longer published")
                outcome, hits = evaluate(item, option)
                now = self._now()
                if obs:  # strictly increasing, so the fold's order never depends on ties
                    now = max(now, obs[-1].at + 1e-3)
                placement_id = placement_id or f"{pl.PLACEMENT_SESSION_PREFIX}{uuid7()}"
                correct = outcome is Outcome.CORRECT
                obs_after = [*obs, pl.Observation(item.objective_code, item.item_ref, correct, now)]
                after = pl.place(graph, items, obs_after, self._cfg)
                knowledge.record_diagnostic(
                    evidence_id=uuid7(),
                    objective_code=item.objective_code,
                    item_ref=item.item_ref,
                    placement_id=placement_id,
                    correct=correct,
                    misconception_hits=hits,
                    response_time_ms=max(0, int(response_time_ms)),
                    prior_before=after.priors_before[-1],
                    prior_after=after.priors_after[-1],
                    now=now,
                )
                self._seed(knowledge, after, placement_id, now)
                events = [
                    ev.placement_answer_recorded(
                        student_ref, placement_id, item.objective_code, outcome.value, now
                    )
                ]
                if after.done and after.stop_reason is not None:
                    events.append(
                        ev.placement_completed(
                            student_ref,
                            placement_id,
                            after.stop_reason.value,
                            after.items_used,
                            now,
                        )
                    )
                uow.knowledge.save(knowledge)
                uow.events.publish(events)
                uow.commit()
                return self._view(student_ref, knowledge, graph, lessons)

        try:
            view = retry_on_conflict(_txn)
        except ConcurrencyConflictError as exc:
            raise conflict(f"placement write conflict for {student_ref}") from exc
        observability.record_event("taleem_placement_answers_total")
        return view

    # ---------------------------------------------------------------------------- helpers

    def _content(self) -> tuple[CurriculumGraph, dict[str, LessonView]]:
        graph = self._graph() if callable(self._graph) else self._graph
        by_code: dict[str, LessonView] = {}
        for info in graph.objectives:
            lesson = self._curriculum.lesson_for(info.objective_code)
            if lesson is not None:
                by_code[info.objective_code] = lesson
        return graph, by_code

    def _seed(
        self,
        knowledge: StudentKnowledge,
        result: pl.PlacementResult,
        placement_id: str,
        now: float,
    ) -> None:
        for o in result.objectives:
            knowledge.seed_prior(
                o.objective_code,
                PriorProvenance(
                    source=pl.PLACEMENT_SOURCE,
                    placement_id=placement_id,
                    status=o.status.value,
                    value=o.value,
                    uncertainty=o.uncertainty,
                    item_refs=o.item_refs,
                    correct=o.correct,
                    incorrect=o.incorrect,
                    recorded_at=o.observed_at or now,
                    inferred_from=o.inferred_from,
                ),
            )

    def _view(
        self,
        student_ref: str,
        knowledge: StudentKnowledge | None,
        graph: CurriculumGraph,
        lessons: dict[str, LessonView],
    ) -> dict[str, Any]:
        items = _item_refs(graph, lessons)
        placement_id, obs = placement_observations(knowledge)
        result = pl.place(graph, items, obs, self._cfg)
        if obs:
            status = "completed" if result.done else "in_progress"
            reason = None
        elif has_practice_history(knowledge):
            status, reason = "not_eligible", "has_history"
        elif result.next_item is None:
            status, reason = "unavailable", "no_published_items"
        else:
            status, reason = "available", None
        open_ = status in ("available", "in_progress")
        nxt = result.next_item if open_ else None
        item = _find_item(lessons, nxt) if nxt else None
        return {
            "student_ref": student_ref,
            "status": status,
            "reason": reason,
            "placement_id": placement_id,
            "items_used": result.items_used,
            "max_items": self._cfg.max_items,
            "stop_reason": result.stop_reason.value if obs and result.stop_reason else None,
            "placement_uncertainty": result.placement_uncertainty,
            "stop_uncertainty": self._cfg.stop_uncertainty,
            "chain_from_sequence": result.chain_from_sequence,
            "start_objective": (result.frontier[0] if result.frontier else None) if obs else None,
            "next_item": (
                {
                    "item_ref": item.item_ref,
                    "objective_code": item.objective_code,
                    "prompt": item.prompt,
                    "options": list(item.options),
                }
                if item is not None
                else None
            ),
            "objectives": (
                [
                    {
                        "objective_code": o.objective_code,
                        "status": o.status.value,
                        "prior": o.value,
                        "uncertainty": o.uncertainty,
                        "correct": o.correct,
                        "incorrect": o.incorrect,
                        "inferred_from": o.inferred_from,
                        "item_refs": list(o.item_refs),
                        "source": pl.PLACEMENT_SOURCE,
                        "recorded_at": o.observed_at,
                    }
                    for o in result.objectives
                ]
                if obs
                else []
            ),
        }


def _diagnostic_items(lesson: LessonView) -> tuple[ItemView, ...]:
    """Formative items first (they exist to check understanding), then practice; deduplicated."""
    seen: set[str] = set()
    out: list[ItemView] = []
    for item in (*lesson.assessment_formative, *lesson.practice_items):
        if item.item_ref and item.item_ref not in seen and item.options:
            seen.add(item.item_ref)
            out.append(item)
    return tuple(out)


def _item_refs(
    graph: CurriculumGraph, lessons: dict[str, LessonView]
) -> dict[str, tuple[str, ...]]:
    return {
        info.objective_code: tuple(
            i.item_ref for i in _diagnostic_items(lessons[info.objective_code])
        )
        for info in graph.objectives
        if info.objective_code in lessons
    }


def _find_item(lessons: dict[str, LessonView], nxt: pl.NextItem) -> ItemView | None:
    lesson = lessons.get(nxt.objective_code)
    if lesson is None:
        return None
    item = next((i for i in _diagnostic_items(lesson) if i.item_ref == nxt.item_ref), None)
    if item is None:
        return None
    # Projected items carry the lesson's objective; make sure the evidence names the placed one.
    return item if item.objective_code == nxt.objective_code else _with_objective(item, nxt)


def _with_objective(item: ItemView, nxt: pl.NextItem) -> ItemView:
    return replace(item, objective_code=nxt.objective_code)
