"""Safeguarding domain rules (pure): categories, priority, lifecycle, text bounds, SLA config."""

from __future__ import annotations

import pytest

from taleem_core.contexts.safeguarding.domain.model import (
    CATEGORY_PRIORITY,
    MAX_FREE_TEXT,
    SLA_DECISION,
    Category,
    Concern,
    InvalidConcernError,
    Outcome,
    Priority,
    RaisedBy,
    SlaPolicy,
    Status,
    clean_screen,
    new_note,
)


def _concern(category: str = "felt_unsafe", **kw: object) -> Concern:
    options: dict[str, object] = {
        "subject_ref": "stu_a",
        "raised_by_ref": "stu_a",
        "raised_by_role": RaisedBy.STUDENT,
        "category": category,
        "free_text": None,
        "screen": "student/today",
        "lesson_id": None,
        "now": 100.0,
    }
    options.update(kw)
    return Concern.raise_new(**options)  # type: ignore[arg-type]


def test_every_category_has_a_tier_and_none_claims_t0() -> None:
    assert set(CATEGORY_PRIORITY) == set(Category)
    # T0 ("imminent harm", a live human within minutes, 24/7) is not staffed: no category claims it.
    assert {p.value for p in CATEGORY_PRIORITY.values()} <= {"T1", "T2", "T3"}
    assert _concern("felt_unsafe").priority is Priority.T1
    assert _concern("bullying").priority is Priority.T2
    assert _concern("other").priority is Priority.T3


def test_unknown_category_is_refused() -> None:
    with pytest.raises(InvalidConcernError) as exc:
        _concern("made_up")
    assert exc.value.field == "category"


def test_a_child_can_only_raise_about_themselves() -> None:
    with pytest.raises(InvalidConcernError):
        _concern(subject_ref="stu_other")


def test_free_text_is_optional_bounded_and_cleaned() -> None:
    assert _concern(free_text=None).free_text is None
    assert _concern(free_text="   ").free_text is None
    assert _concern(free_text=" hello\x00\x07 there ").free_text == "hello there"
    assert _concern(free_text="x" * MAX_FREE_TEXT).free_text == "x" * MAX_FREE_TEXT
    with pytest.raises(InvalidConcernError):
        _concern(free_text="x" * (MAX_FREE_TEXT + 1))


def test_screen_is_a_route_token_or_nothing() -> None:
    assert clean_screen("/student/today") == "student/today"
    assert clean_screen("/Student/Offline/Play/") == "student/offline/play"
    assert clean_screen("javascript:alert(1)") == ""
    assert clean_screen("student/today?ref=stu_1") == ""
    assert clean_screen(None) == ""
    with pytest.raises(InvalidConcernError):
        _concern(lesson_id="<script>")
    assert _concern(lesson_id="L-math-g4-intro-fractions").context_lesson_id is not None


def test_lifecycle_open_acknowledge_escalate_resolve() -> None:
    c = _concern()
    assert c.status is Status.OPEN and c.is_open
    assert c.acknowledge(actor_ref="stf_1", now=110.0) is True
    assert c.acknowledge(actor_ref="stf_1", now=111.0) is False  # idempotent
    assert c.escalate(actor_ref="stf_1", now=120.0) is True
    assert c.escalate(actor_ref="stf_1", now=121.0) is False
    c.resolve(actor_ref="stf_2", outcome="referred_externally", now=130.0)
    assert (c.status, c.outcome, c.resolved_by) == (
        Status.RESOLVED,
        Outcome.REFERRED_EXTERNALLY,
        "stf_2",
    )
    assert not c.is_open
    for act in (
        lambda: c.acknowledge(actor_ref="stf_1", now=140.0),
        lambda: c.escalate(actor_ref="stf_1", now=140.0),
        lambda: c.resolve(actor_ref="stf_1", outcome="duplicate", now=140.0),
    ):
        with pytest.raises(InvalidConcernError) as exc:
            act()
        assert exc.value.code == "CONCERN_CLOSED"


def test_escalating_from_open_also_acknowledges() -> None:
    c = _concern()
    c.escalate(actor_ref="stf_1", now=105.0)
    assert (c.acknowledged_at, c.acknowledged_by, c.status) == (105.0, "stf_1", Status.ESCALATED)


def test_referred_externally_needs_a_recorded_escalation() -> None:
    c = _concern()
    with pytest.raises(InvalidConcernError) as exc:
        c.resolve(actor_ref="stf_1", outcome="referred_externally", now=101.0)
    assert exc.value.code == "CONCERN_NOT_ESCALATED"
    c.resolve(actor_ref="stf_1", outcome="support_given", now=101.0)
    assert c.outcome is Outcome.SUPPORT_GIVEN


def test_notes_need_text() -> None:
    with pytest.raises(InvalidConcernError):
        new_note(concern_id="sgc_1", author_ref="stf_1", body="  ", now=1.0)
    assert new_note(concern_id="sgc_1", author_ref="stf_1", body=" ok ", now=1.0).body == "ok"


def test_sla_defaults_to_unset_and_never_flags_overdue() -> None:
    sla = SlaPolicy.from_json("")
    assert not sla.configured and not sla.fully_configured
    assert sla.describe()["notice"] == SLA_DECISION
    thresholds = sla.describe()["acknowledge_within_seconds"]
    assert isinstance(thresholds, dict) and all(v is None for v in thresholds.values())
    assert _concern().overdue(sla, now=10_000_000.0) is None


def test_configured_sla_flags_only_unacknowledged_concerns_past_their_tier() -> None:
    sla = SlaPolicy.from_json('{"T1": 60}')
    assert sla.configured and not sla.fully_configured  # T2/T3 unset: the banner still shows
    assert sla.describe()["notice"] == SLA_DECISION
    t1 = _concern("felt_unsafe")
    assert t1.overdue(sla, now=150.0) is False
    assert t1.overdue(sla, now=161.0) is True
    t1.acknowledge(actor_ref="stf_1", now=170.0)
    assert t1.overdue(sla, now=500.0) is False  # acknowledged: no longer waiting
    assert _concern("other").overdue(sla, now=10_000.0) is None  # T3 has no threshold
    full = SlaPolicy.from_json('{"T1": 1, "T2": 2, "T3": 3}')
    assert full.fully_configured and full.describe()["notice"] is None


@pytest.mark.parametrize(
    "raw", ['{"T0": 5}', '{"T1": -1}', '{"T1": "soon"}', '{"T1": true}', "[1]", "{not json"]
)
def test_sla_config_rejects_invented_or_invalid_values(raw: str) -> None:
    with pytest.raises(InvalidConcernError):
        SlaPolicy.from_json(raw)
