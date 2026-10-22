"""School domain rules (pure)."""

from __future__ import annotations

import pytest

from taleem_core.contexts.school.adapters.context_ports import KnowledgeProgressReader
from taleem_core.contexts.school.domain.model import (
    MAX_FAILED_SIGN_INS,
    Assignment,
    Classroom,
    InvalidSchoolDataError,
    Organization,
    Teacher,
    TeacherStatus,
    new_join_code,
    normalise_join_code,
)


def test_organization_validates_country_pack_and_locale() -> None:
    org = Organization.create(
        name="  Model   School ",
        country="pk",
        curriculum_pack_id="pk-g4",
        default_locale="ur",
        now=1,
    )
    assert (org.name, org.country) == ("Model School", "PK")
    assert org.organization_id.startswith("org_")
    for kwargs in (
        {"country": "PAK"},
        {"curriculum_pack_id": "Bad Pack!"},
        {"default_locale": "urdu"},
        {"name": ""},
    ):
        base = {"name": "S", "country": "PK", "curriculum_pack_id": "p", "default_locale": "ur"}
        with pytest.raises(InvalidSchoolDataError):
            Organization.create(**{**base, **kwargs}, now=1)  # type: ignore[arg-type]


def test_join_codes_are_well_formed_and_normalised() -> None:
    code = new_join_code()
    assert len(code) == 9 and code[4] == "-"
    assert normalise_join_code(code.lower().replace("-", " ")) == code
    for bad in ("ABCD-EFG0", "SHORT", "ABCD-EFGHI"):  # 0 is excluded from the alphabet
        with pytest.raises(InvalidSchoolDataError):
            normalise_join_code(bad)


def test_teacher_locks_after_repeated_failures() -> None:
    t = Teacher.create(
        organization_id="org_1",
        email="T@X.example",
        display_name="T",
        passphrase_hash="h",  # noqa: S106 (a placeholder, not a credential)
        now=1,
    )
    assert t.email == "t@x.example" and t.can_sign_in
    for _ in range(MAX_FAILED_SIGN_INS):
        t.record_failure()
    assert t.status is TeacherStatus.LOCKED and not t.can_sign_in


def test_assignment_inherits_the_class_tenant_and_needs_a_future_due_date() -> None:
    c = Classroom.create(organization_id="org_1", teacher_ref="t", name="C", join_code="X", now=1)
    a = Assignment.create(classroom=c, objective_code="G4.F.1", due_at=100, assigned_by="t", now=1)
    assert (a.organization_id, a.class_id) == ("org_1", c.class_id)
    with pytest.raises(InvalidSchoolDataError):
        Assignment.create(classroom=c, objective_code="G4.F.1", due_at=1, assigned_by="t", now=1)
    with pytest.raises(InvalidSchoolDataError):
        Assignment.create(
            classroom=c, objective_code="bad code", due_at=100, assigned_by="t", now=1
        )


class _Obj:
    def __init__(self, value: float, state: str) -> None:
        self.mastery = type("M", (), {"value": value})()
        self.state = state


class _Ev:
    def __init__(self, code: str, at: float) -> None:
        self.objective_code = code
        self.occurred_at = at


def test_progress_reader_counts_only_attempts_since_assignment() -> None:
    knowledge = type(
        "K",
        (),
        {
            "objectives": {"O1": _Obj(0.71234, "in_progress")},
            "evidence": [_Ev("O1", 5), _Ev("O1", 15), _Ev("O2", 20)],
        },
    )()
    reader = KnowledgeProgressReader(lambda ref: knowledge if ref == "S1" else None)
    p = reader.objective_progress("S1", "O1", since=10)
    assert (p.mastery, p.state, p.attempts_since) == (0.7123, "in_progress", 1)
    none = reader.objective_progress("S2", "O1", since=0)
    assert (none.mastery, none.attempts_since) == (None, 0)
    untouched = reader.objective_progress("S1", "O9", since=0)
    assert (untouched.mastery, untouched.state) == (None, "not_started")
