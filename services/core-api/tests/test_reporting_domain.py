"""Reporting domain + service, without a database (REPORT_CARD_CONTRACT.md §1-§2).

The derivation is a pure function over snapshots, so its rules are tested directly: period
boundaries, what counts as an attempt, mastery as of the period end, version pins, the honest
no-evidence card, canonical JSON + hash re-verification — and a property-style check that a
card's totals reconcile with the underlying evidence for many sampled learners.
"""

from __future__ import annotations

import dataclasses
import json
import random
from typing import Any

import pytest

from taleem_core.contexts.reporting.adapters.context_ports import (
    CallableLearnerDirectory,
    CallableLearningRecords,
    CallablePublishedLessons,
    CallableSchoolDirectory,
)
from taleem_core.contexts.reporting.adapters.memory import (
    InMemoryReportingStore,
    InMemoryReportingUnitOfWork,
)
from taleem_core.contexts.reporting.application.ports import ClassRoster, LearnerVisibility
from taleem_core.contexts.reporting.application.service import ReportingService
from taleem_core.contexts.reporting.domain.report_card import (
    DERIVATION,
    DEVELOPING,
    MASTERED,
    NOT_STARTED,
    OTHER_SUBJECT,
    PREVIOUS_DERIVATIONS,
    VERSION_FROM_EVIDENCE,
    VERSION_MIXED,
    VERSION_UNRECORDED,
    ClassContext,
    EvidenceRecord,
    HomeworkOutcome,
    InvalidReportError,
    LearnerRecords,
    LessonPin,
    MasteryEvent,
    Period,
    ReportCard,
    ReportConflictError,
    canonical_json,
    check_supersedes,
    clean_comment,
    content_hash,
    current_card,
    derive_body,
    mastery_state_at,
    new_card_id,
)
from taleem_core.platform.concurrency import ConcurrencyConflictError
from taleem_core.platform.errors import Problem

NOW = 10_000.0
CTX = ClassContext("cls_1", "org_1", "4 Blue", "School", "PK-NCP", "Ms Ayesha")
PIN = LessonPin("OBJ-A", "L-a", 3, "PK-NCP", "math", {"en": "A", "ur": "ا"}, {"en": "Maths"})


def _ev(
    code: str, at: float, outcome: str = "correct", ctx: str = "practice", eid: str = ""
) -> Any:
    return EvidenceRecord(eid or f"ev-{code}-{at}-{outcome}", code, outcome, ctx, at)


def _body(records: LearnerRecords, **kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {
        "records": records,
        "lessons": {"OBJ-A": PIN},
        "period": Period(100, 200),
        "context": CTX,
        "learner_display_name": "Zara",
        "issued_by": "tch_1",
        "issued_by_name": "Ms Ayesha",
        "issued_at": 300.0,
        "card_id": "rpc_1",
        "supersedes": None,
        "comment": None,
    }
    args.update(kw)
    return derive_body(**args)


def _objectives(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {o["objective_code"]: o for s in body["subjects"] for o in s["objectives"]}


# -------------------------------------------------------------------------------- period


def test_period_validation_and_boundaries() -> None:
    assert Period.of(0, 10, now=10) == Period(0, 10)
    for start, end in ((5, 5), (6, 5), (-1, 5), (True, 5), (0, 11)):
        with pytest.raises(InvalidReportError):
            Period.of(start, end, now=10)
    p = Period(100, 200)
    assert p.contains(100) and p.contains(199.999) and not p.contains(200) and not p.contains(99)


def test_records_at_the_boundaries_count_once_across_adjacent_periods() -> None:
    records = LearnerRecords("stu", evidence=(_ev("OBJ-A", 100), _ev("OBJ-A", 200)))
    first = _body(records, period=Period(0, 100))
    middle = _body(records, period=Period(100, 200))
    last = _body(records, period=Period(200, 300))
    counts = [b["totals"]["attempts"] if b["totals"] else 0 for b in (first, middle, last)]
    assert counts == [0, 1, 1]


# ----------------------------------------------------------------------------- derivation


def test_attempts_exclude_diagnostics_and_marked_homework_evidence() -> None:
    hw = HomeworkOutcome("sub_1", "cls_1", "OBJ-A", "met", 150)
    other_class = HomeworkOutcome("sub_2", "cls_9", "OBJ-A", "not_yet", 150)
    records = LearnerRecords(
        "stu",
        evidence=(
            _ev("OBJ-A", 110),
            _ev("OBJ-A", 120, "incorrect"),
            _ev("OBJ-A", 125, "partial"),
            _ev("OBJ-A", 130, ctx="diagnostic"),
            _ev("OBJ-A", 150, eid="sub_1"),
            _ev("OBJ-A", 151, eid="sub_2"),
        ),
        homework=(hw, other_class),
    )
    obj = _objectives(_body(records))["OBJ-A"]
    assert (obj["attempts"], obj["correct"]) == (3, 1)
    assert (obj["homework_met"], obj["homework_not_yet"]) == (1, 0)  # only this class
    system = _objectives(_body(records, context=None, issued_by="system"))["OBJ-A"]
    assert (system["homework_met"], system["homework_not_yet"]) == (1, 1)  # every class


def test_mastery_state_is_as_of_the_period_end() -> None:
    records = LearnerRecords(
        "stu",
        evidence=(_ev("OBJ-A", 150), _ev("OBJ-B", 150, ctx="diagnostic")),
        mastery_events=(MasteryEvent("OBJ-A", 250),),
        homework=(HomeworkOutcome("sub_9", "cls_1", "OBJ-C", "not_yet", 120),),
    )
    assert mastery_state_at(records, "OBJ-A", 200) == DEVELOPING
    assert mastery_state_at(records, "OBJ-A", 251) == MASTERED
    assert mastery_state_at(records, "OBJ-A", 150) == NOT_STARTED  # end is exclusive
    assert mastery_state_at(records, "OBJ-B", 999) == NOT_STARTED  # a diagnostic is no practice
    assert mastery_state_at(records, "OBJ-C", 200) == DEVELOPING  # marked homework is
    assert _objectives(_body(records, period=Period(100, 300)))["OBJ-A"]["mastery"] == MASTERED


def _vev(
    code: str, at: float, version: int | None, lesson: str = "L-a", eid: str = ""
) -> EvidenceRecord:
    return EvidenceRecord(
        eid or f"ev-{code}-{at}-{version}", code, "correct", "practice", at, lesson, version
    )


def test_version_pins_subjects_and_unpublished_objectives() -> None:
    records = LearnerRecords("stu", evidence=(_vev("OBJ-A", 150, 3), _vev("OBJ-Z", 150, 1, "L-z")))
    body = _body(records)
    assert body["derivation"] == DERIVATION == "taleem.reporting.derive/2"
    by_key = {s["subject_key"]: s for s in body["subjects"]}
    assert by_key["math"]["subject_name"] == {"en": "Maths"}
    a = by_key["math"]["objectives"][0]
    assert (a["lesson_id"], a["lesson_version"], a["title"]) == ("L-a", 3, {"en": "A", "ur": "ا"})
    assert (a["lesson_versions"], a["version_source"], a["unversioned_evidence"]) == (
        [3],
        VERSION_FROM_EVIDENCE,
        0,
    )
    # No published lesson now: titled {} under "other", but the evidence's pin is still cited.
    z = by_key[OTHER_SUBJECT]["objectives"][0]
    assert (z["lesson_id"], z["lesson_version"], z["title"]) == ("L-z", 1, {})
    assert by_key[OTHER_SUBJECT]["subject_name"] == {"ur": "other", "en": "other"}
    # A later publish never changes the pin: it comes from the evidence, not the published pin.
    old = ReportCard.issue(body)
    newer = dataclasses.replace(PIN, version=4)
    assert _objectives(_body(records, lessons={"OBJ-A": newer}))["OBJ-A"]["lesson_version"] == 3
    assert _objectives(old.body)["OBJ-A"]["lesson_version"] == 3 and old.verify()


def test_republish_between_learning_and_issue_keeps_the_version_learned_from() -> None:
    """The bug this derivation fixes: the work was done on v2, v5 is published at issue time."""
    records = LearnerRecords("stu", evidence=(_vev("OBJ-A", 120, 2), _vev("OBJ-A", 130, 2)))
    published_now = dataclasses.replace(PIN, version=5)
    a = _objectives(_body(records, lessons={"OBJ-A": published_now}))["OBJ-A"]
    assert (a["lesson_version"], a["lesson_versions"], a["version_source"]) == (
        2,
        [2],
        VERSION_FROM_EVIDENCE,
    )
    # A rollback (published version number goes DOWN) is just as irrelevant.
    rolled_back = dataclasses.replace(PIN, version=1)
    assert (
        _objectives(_body(records, lessons={"OBJ-A": rolled_back}))["OBJ-A"]["lesson_version"] == 2
    )


def test_several_versions_are_listed_sorted_and_no_single_version_is_claimed() -> None:
    records = LearnerRecords(
        "stu", evidence=(_vev("OBJ-A", 150, 4), _vev("OBJ-A", 110, 2), _vev("OBJ-A", 120, 4))
    )
    a = _objectives(_body(records))["OBJ-A"]
    assert a["lesson_versions"] == [2, 4] and a["lesson_version"] is None
    assert a["version_source"] == VERSION_FROM_EVIDENCE and a["lesson_id"] == "L-a"


def test_unrecorded_versions_are_reported_never_replaced_by_the_current_pin() -> None:
    unrecorded = LearnerRecords("stu", evidence=(_ev("OBJ-A", 150), _ev("OBJ-A", 160)))
    a = _objectives(_body(unrecorded))["OBJ-A"]  # PIN (v3) is published, but never used
    assert (a["lesson_id"], a["lesson_version"], a["lesson_versions"]) == (None, None, [])
    assert (a["version_source"], a["unversioned_evidence"]) == (VERSION_UNRECORDED, 2)
    mixed = LearnerRecords("stu", evidence=(_vev("OBJ-A", 150, 3), _ev("OBJ-A", 160)))
    m = _objectives(_body(mixed))["OBJ-A"]
    assert (m["lesson_version"], m["lesson_versions"], m["version_source"]) == (
        None,
        [3],
        VERSION_MIXED,
    )
    assert m["unversioned_evidence"] == 1 and m["lesson_id"] == "L-a"
    # An offline attempt that named the lesson but no version is still unrecorded for the version.
    no_version = LearnerRecords("stu", evidence=(_vev("OBJ-A", 150, None),))
    n = _objectives(_body(no_version))["OBJ-A"]
    assert (n["lesson_id"], n["lesson_version"], n["version_source"]) == (
        "L-a",
        None,
        VERSION_UNRECORDED,
    )


def test_two_lessons_for_one_objective_name_neither() -> None:
    records = LearnerRecords(
        "stu", evidence=(_vev("OBJ-A", 150, 1, "L-a"), _vev("OBJ-A", 160, 1, "L-b"))
    )
    a = _objectives(_body(records))["OBJ-A"]
    assert a["lesson_id"] is None and a["lesson_ids"] == ["L-a", "L-b"]
    assert a["lesson_version"] is None and a["lesson_versions"] == [1]


def test_the_pin_counts_listed_homework_evidence_but_not_diagnostics() -> None:
    hw = HomeworkOutcome("sub_1", "cls_1", "OBJ-H", "met", 150)
    other_class = HomeworkOutcome("sub_2", "cls_9", "OBJ-H", "met", 150)
    records = LearnerRecords(
        "stu",
        evidence=(
            _vev("OBJ-H", 150, 7, eid="sub_1"),  # the listed mark's evidence
            _vev("OBJ-H", 150, 9, eid="sub_2"),  # another class's mark: not on this card
            EvidenceRecord("d1", "OBJ-H", "correct", "diagnostic", 150, "L-a", 8),
        ),
        homework=(hw, other_class),
    )
    h = _objectives(_body(records))["OBJ-H"]
    assert (h["attempts"], h["homework_met"]) == (0, 1)
    assert (h["lesson_version"], h["lesson_versions"], h["version_source"]) == (
        7,
        [7],
        VERSION_FROM_EVIDENCE,
    )
    # Homework whose mark recorded no evidence row: nothing to pin from, said so.
    bare = LearnerRecords("stu", homework=(hw,))
    b = _objectives(_body(bare))["OBJ-H"]
    assert (b["version_source"], b["unversioned_evidence"], b["lesson_versions"]) == (
        VERSION_UNRECORDED,
        0,
        [],
    )


def test_a_stored_v1_card_still_verifies_with_its_stored_hash() -> None:
    v1 = _body(LearnerRecords("stu", evidence=(_ev("OBJ-A", 150),)))
    v1["derivation"] = "taleem.reporting.derive/1"
    for subject in v1["subjects"]:  # the v1 objective shape: the issue-time published pin
        for obj in subject["objectives"]:
            for key in ("lesson_ids", "lesson_versions", "version_source", "unversioned_evidence"):
                obj.pop(key)
            obj["lesson_id"], obj["lesson_version"] = "L-a", 3
    card = ReportCard.issue(v1)
    stored = dataclasses.replace(card)  # as read back from the store
    assert stored.verify() and stored.body["derivation"] in PREVIOUS_DERIVATIONS
    assert _objectives(stored.body)["OBJ-A"]["lesson_version"] == 3


def test_a_card_with_no_evidence_says_so() -> None:
    body = _body(LearnerRecords("stu", evidence=(_ev("OBJ-A", 50),)))
    assert body["has_evidence"] is False and body["notice"] == "no_evidence_in_period"
    assert body["totals"] is None and body["subjects"] == []


def test_system_cards_have_no_class_and_no_comment() -> None:
    records = LearnerRecords("stu", evidence=(_ev("OBJ-A", 150),))
    body = _body(records, context=None, issued_by="system", issued_by_name="Taleem")
    assert body["class_id"] is None and body["organization_id"] is None
    assert body["curriculum_pack"] == "PK-NCP" and body["comment"] is None
    other = dataclasses.replace(PIN, objective_code="OBJ-B", curriculum_pack="GB-X")
    two = _body(
        LearnerRecords("stu", evidence=(_ev("OBJ-A", 150), _ev("OBJ-B", 150))),
        lessons={"OBJ-A": PIN, "OBJ-B": other},
        context=None,
        issued_by="system",
    )
    assert two["curriculum_pack"] == "GB-X,PK-NCP"
    assert _body(LearnerRecords("stu"), context=None, issued_by="system")["curriculum_pack"] is None
    with pytest.raises(InvalidReportError):
        _body(records, context=None, issued_by="system", comment="hello")
    card = ReportCard.issue(body)
    assert (card.class_id, card.organization_id) == ("", "") and card.verify()


def test_comment_is_cleaned_and_bounded() -> None:
    assert clean_comment("  hi\x00 there \n") == "hi there"
    assert clean_comment("   ") is None and clean_comment(None) is None
    assert clean_comment("x" * 1000) == "x" * 1000
    with pytest.raises(InvalidReportError):
        clean_comment("x" * 1001)


def test_totals_reconcile_with_the_underlying_evidence_for_sampled_learners() -> None:
    rng = random.Random(2026)  # noqa: S311 (deterministic sampling, not crypto)
    codes = ["OBJ-A", "OBJ-B", "OBJ-C", "OBJ-D"]
    for n in range(200):
        evidence = tuple(
            _ev(
                rng.choice(codes),
                rng.uniform(0, 400),
                rng.choice(["correct", "incorrect", "partial"]),
                rng.choice(["practice", "spaced_review", "diagnostic", "remediation"]),
                eid=f"e{n}-{i}",
            )
            for i in range(rng.randint(0, 40))
        )
        homework = tuple(
            HomeworkOutcome(
                f"sub_{n}_{i}",
                rng.choice(["cls_1", "cls_2"]),
                rng.choice(codes),
                rng.choice(["met", "not_yet"]),
                rng.uniform(0, 400),
            )
            for i in range(rng.randint(0, 6))
        )
        records = LearnerRecords(f"stu{n}", evidence=evidence, homework=homework)
        period = Period(rng.randint(0, 200), rng.randint(201, 400))
        body = _body(records, period=period)
        objectives = _objectives(body).values()
        auto = [e for e in evidence if e.context != "diagnostic" and period.contains(e.occurred_at)]
        marks = [h for h in homework if h.class_id == "cls_1" and period.contains(h.marked_at)]
        if not auto and not marks:
            assert body["totals"] is None and body["subjects"] == []
            continue
        t = body["totals"]
        assert t["attempts"] == len(auto) == sum(o["attempts"] for o in objectives)
        assert t["correct"] == sum(e.outcome == "correct" for e in auto)
        assert t["correct"] == sum(o["correct"] for o in objectives)
        assert t["homework_met"] == sum(h.outcome == "met" for h in marks)
        assert t["homework_not_yet"] == sum(o["homework_not_yet"] for o in objectives)
        assert t["objectives"] == len(
            {e.objective_code for e in auto} | {h.objective_code for h in marks}
        )
        assert ReportCard.issue({**body, "card_id": new_card_id()}).verify()


# --------------------------------------------------------------------------- hash + card


def test_canonical_json_hash_and_re_verification() -> None:
    body = _body(LearnerRecords("stu", evidence=(_ev("OBJ-A", 150),)), comment="شاباش")
    text = canonical_json(body)
    assert text == json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    card = ReportCard.issue(body)
    assert card.content_hash == content_hash(text) and card.verify() and card.body == body
    assert "شاباش" in card.body_json  # UTF-8, not \\u escapes
    forged = dataclasses.replace(card, body_json=text.replace('"Zara"', '"Ali"'))
    assert not forged.verify()
    rehashed = dataclasses.replace(forged, content_hash=content_hash(forged.body_json))
    assert rehashed.verify()  # a valid hash over a consistent body…
    assert not dataclasses.replace(rehashed, student_ref="stu_other").verify()  # …not this row
    spaced = json.dumps(body, sort_keys=True)  # not canonical
    assert not dataclasses.replace(
        card, body_json=spaced, content_hash=content_hash(spaced)
    ).verify()
    broken = dataclasses.replace(card, body_json="{oops", content_hash=content_hash("{oops"))
    assert not broken.verify() and broken.body == {}
    listed = dataclasses.replace(card, body_json="[]", content_hash=content_hash("[]"))
    assert not listed.verify() and listed.body == {}
    with pytest.raises(InvalidReportError):
        ReportCard.issue({**body, "card_id": None})


def test_supersede_rules_current_card_and_acknowledge_once() -> None:
    period = Period(100, 200)
    body = _body(LearnerRecords("stu"))
    a = ReportCard.issue(body)
    b = ReportCard.issue({**body, "card_id": "rpc_2", "supersedes": "rpc_1", "issued_at": 301.0})
    assert current_card([a, b]) == b and current_card([]) is None
    ok = check_supersedes(a, student_ref="stu", class_id="cls_1", period=period, successor=None)
    assert ok == a
    with pytest.raises(ReportConflictError) as exc:
        check_supersedes(a, student_ref="stu", class_id="cls_1", period=period, successor="rpc_2")
    assert exc.value.code == "ALREADY_SUPERSEDED"
    for kwargs in (
        {"student_ref": "x", "class_id": "cls_1", "period": period},
        {"student_ref": "stu", "class_id": "cls_9", "period": period},
        {"student_ref": "stu", "class_id": "cls_1", "period": Period(100, 201)},
    ):
        with pytest.raises(InvalidReportError):
            check_supersedes(a, successor=None, **kwargs)
    with pytest.raises(InvalidReportError):
        check_supersedes(None, student_ref="stu", class_id="cls_1", period=period, successor=None)
    seen = a.acknowledged(guardian_ref="g1", at=5.0)
    assert (seen.acknowledged_at, seen.acknowledged_by) == (5.0, "g1")
    with pytest.raises(ReportConflictError) as again:
        seen.acknowledged(guardian_ref="g1", at=6.0)
    assert again.value.code == "ALREADY_ACKNOWLEDGED"


# --------------------------------------------------------------------- in-memory adapters


def test_in_memory_store_enforces_the_unique_rules_on_commit() -> None:
    store = InMemoryReportingStore()
    body = _body(LearnerRecords("stu"))
    a = ReportCard.issue(body)
    with InMemoryReportingUnitOfWork(store) as uow:
        uow.cards.add(a)
        assert uow.cards.get(a.card_id) is None  # not visible before commit
        uow.commit()
    for dup in (
        a,
        ReportCard.issue({**body, "card_id": "rpc_9"}),  # a second original for the slot
    ):
        with InMemoryReportingUnitOfWork(store) as uow, pytest.raises(ConcurrencyConflictError):
            uow.cards.add(dup)
            uow.commit()
    fix = ReportCard.issue({**body, "card_id": "rpc_2", "supersedes": a.card_id})
    fork = ReportCard.issue({**body, "card_id": "rpc_3", "supersedes": a.card_id})
    with InMemoryReportingUnitOfWork(store) as uow:
        uow.cards.add(fix)
        uow.commit()
    with InMemoryReportingUnitOfWork(store) as uow, pytest.raises(ConcurrencyConflictError):
        uow.cards.add(fork)
        uow.commit()
    with InMemoryReportingUnitOfWork(store) as uow:
        assert uow.cards.successors([a.card_id, "x"]) == {a.card_id: fix.card_id}
        assert len(uow.cards.for_class("org_1", "cls_1")) == 2
        assert uow.cards.acknowledge(a.card_id, "g", 1.0) is True
        assert uow.cards.acknowledge(a.card_id, "g", 2.0) is False  # pending in this UoW
        assert uow.cards.acknowledge("rpc_none", "g", 2.0) is False
        uow.commit()
        assert uow.cards.acknowledge(a.card_id, "g", 3.0) is False
    assert store.cards[a.card_id].acknowledged_at == 1.0


# ------------------------------------------------------------------- service (fakes)


class _Fakes:
    def __init__(self) -> None:
        self.rosters = {
            "cls_1": {
                "class_id": "cls_1",
                "organization_id": "org_1",
                "class_name": "4 Blue",
                "organization_name": "School",
                "curriculum_pack_id": "PK-NCP",
                "teacher_name": "Ms Ayesha",
                "student_refs": ["stu_a", "stu_b", "stu_c"],
            }
        }
        self.hidden = {"stu_b": "consent_withdrawn", "stu_c": "inactive"}
        self.evidence: dict[str, list[dict[str, Any]]] = {
            "stu_a": [
                {
                    "evidence_id": "e1",
                    "objective_code": "OBJ-A",
                    "outcome": "correct",
                    "context": "practice",
                    "occurred_at": 150.0,
                    "lesson_id": "L-a",
                    "lesson_version": 2,
                },
            ]
        }

    def roster(self, teacher_ref: str, class_id: str) -> dict[str, Any]:
        if teacher_ref != "tch_1" or class_id not in self.rosters:
            raise Problem(404, "NOT_FOUND", "Not found", "class not found")
        return self.rosters[class_id]

    def rosters_of(self, teacher_ref: str) -> list[dict[str, Any]]:
        return list(self.rosters.values()) if teacher_ref == "tch_1" else []

    def visibility(self, refs: list[str]) -> dict[str, dict[str, Any]]:
        return {
            r: {
                "display_name": None if r in self.hidden else r.upper(),
                "reason": self.hidden.get(r),
            }
            for r in refs
            if r != "stu_gone"
        }

    def learner(self, ref: str) -> dict[str, Any] | None:
        if ref == "stu_gone":
            return None
        return {"display_name": ref.upper(), "refusal": self.hidden.get(ref)}


def _service(fakes: _Fakes) -> tuple[ReportingService, InMemoryReportingStore]:
    store = InMemoryReportingStore()
    clock = iter(float(NOW + i) for i in range(10_000))
    service = ReportingService(
        lambda: InMemoryReportingUnitOfWork(store),
        school=CallableSchoolDirectory(
            fakes.roster,
            fakes.rosters_of,
            lambda ref: [
                {
                    "submission_id": "sub_1",
                    "class_id": "cls_1",
                    "objective_code": "OBJ-A",
                    "outcome": "met",
                    "marked_at": 160.0,
                },
                {
                    "submission_id": "sub_x",
                    "class_id": "cls_1",
                    "objective_code": "OBJ-A",
                    "outcome": None,
                    "marked_at": None,
                },
            ],
        ),
        learners=CallableLearnerDirectory(lambda ref: "g_" + ref, fakes.visibility, fakes.learner),
        records=CallableLearningRecords(
            lambda ref: {
                "evidence": fakes.evidence.get(ref, []),
                "mastered": [{"objective_code": "OBJ-A", "at": 170.0}, {"objective_code": ""}],
            }
        ),
        lessons=CallablePublishedLessons(
            lambda: [
                {
                    "objective_code": "OBJ-A",
                    "lesson_id": "L-a",
                    "version": 2,
                    "curriculum_pack": "PK-NCP",
                    "subject_key": "math",
                    "title": {"en": "A"},
                    "subject_name": {"en": "Maths", "ur": ""},
                },
                {"objective_code": "OBJ-A", "lesson_id": "L-dup", "version": 9},
            ]
        ),
        clock=lambda: next(clock),
    )
    return service, store


def test_service_issue_skips_with_stable_reasons_and_writes_atomically() -> None:
    fakes = _Fakes()
    service, store = _service(fakes)
    out = service.issue(
        teacher_ref="tch_1",
        class_id="cls_1",
        period_start=100,
        period_end=200,
        student_refs=["stu_a", "stu_b", "stu_c", "stu_x", "stu_a"],
    )
    reasons = {s["student_ref"]: s["reason"] for s in out["skipped"]}
    assert reasons == {"stu_b": "consent_withdrawn", "stu_c": "inactive", "stu_x": "not_in_class"}
    (card,) = out["report_cards"]
    obj = card["subjects"][0]["objectives"][0]
    assert (obj["attempts"], obj["homework_met"], obj["mastery"]) == (1, 1, MASTERED)
    assert obj["lesson_id"] == "L-a" and card["subjects"][0]["subject_name"] == {"en": "Maths"}
    # The pin is the adapter-mapped evidence's (v2); homework sub_1 recorded no evidence row.
    assert (obj["lesson_version"], obj["version_source"]) == (2, "evidence")
    assert len(store.cards) == len(store.audit) == len(store.outbox) == 1
    assert store.outbox[0]["payload"]["guardian_ref"] == "g_stu_a"
    with pytest.raises(Problem) as too_many:
        service.preview(
            teacher_ref="tch_1",
            class_id="cls_1",
            period_start=100,
            period_end=200,
            student_refs=[f"s{i}" for i in range(201)],
        )
    assert too_many.value.status == 422
    with pytest.raises(Problem) as nf:
        service.issue(teacher_ref="tch_9", class_id="cls_1", period_start=100, period_end=200)
    assert nf.value.status == 404


def test_service_system_issuance_and_reads() -> None:
    fakes = _Fakes()
    service, store = _service(fakes)
    card = service.issue_for_learner("stu_a", 100, 200)
    assert card["issued_by"] == "system" and card["class_id"] is None and card["hash_verified"]
    with pytest.raises(Problem) as dup:
        service.issue_for_learner("stu_a", 100, 200)
    assert (dup.value.status, dup.value.code) == (409, "REPORT_CARD_EXISTS")
    for ref, status in (("stu_b", 403), ("stu_gone", 403)):
        with pytest.raises(Problem) as refused:
            service.issue_for_learner(ref, 100, 200)
        assert refused.value.status == status
    with pytest.raises(Problem) as bad:
        service.issue_for_learner("stu_a", 200, 100)
    assert bad.value.status == 422
    with pytest.raises(Problem):
        service.generate_for_child(
            guardian_ref="g_other", student_ref="stu_a", period_start=1, period_end=2
        )
    # A role with no relationship never reads a card, whatever the PDP allowed.
    with pytest.raises(Problem) as nobody:
        service.get_card(actor_ref="x", role="mentor", card_id=card["card_id"])
    assert nobody.value.status == 404
    assert service.learner_cards_for_teacher(teacher_ref="tch_1", student_ref="stu_a") == []
    with pytest.raises(Problem):
        service.learner_cards_for_teacher(teacher_ref="tch_1", student_ref="stu_b")
    assert service.class_cards(teacher_ref="tch_1", class_id="cls_1") == []
    # A concurrent duplicate that slips past the read loses on the unique rule: still a 409.
    store.cards.clear()
    original = service._store

    def racing(cards: list[ReportCard], **kw: Any) -> None:
        raise ConcurrencyConflictError("lost")

    service._store = racing  # type: ignore[method-assign]
    with pytest.raises(Problem) as race:
        service.issue_for_learner("stu_a", 100, 200)
    assert race.value.code == "REPORT_CARD_EXISTS"
    service._store = original  # type: ignore[method-assign]


def test_service_acknowledge_race_is_a_conflict() -> None:
    fakes = _Fakes()
    service, store = _service(fakes)
    card = service.issue_for_learner("stu_a", 100, 200)

    class _Raced(InMemoryReportingUnitOfWork):
        def __init__(self) -> None:
            super().__init__(store)
            self.cards.acknowledge = lambda *a: False  # type: ignore[method-assign]

    service._uow = _Raced  # type: ignore[assignment]
    with pytest.raises(Problem) as exc:
        service.acknowledge(guardian_ref="g_stu_a", card_id=card["card_id"])
    assert (exc.value.status, exc.value.code) == (409, "ALREADY_ACKNOWLEDGED")


def test_learner_visibility_defaults_to_hidden() -> None:
    directory = CallableLearnerDirectory(lambda r: None, lambda refs: {}, lambda r: None)
    assert directory.teacher_visibility(["a", "", "a"]) == {
        "a": LearnerVisibility(display_name=None, reason="inactive")
    }
    assert directory.teacher_visibility([]) == {}
    assert directory.display_name("a") is None and directory.learning_refusal("a") == "inactive"
    roster = CallableSchoolDirectory(
        lambda t, c: {"class_id": c, "organization_id": "o"}, lambda t: [], lambda s: []
    ).teacher_class(teacher_ref="t", class_id="c")
    assert roster == ClassRoster("c", "o", "", "", "", ())
