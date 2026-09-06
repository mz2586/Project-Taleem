"""The operator kill switch must be shared by every instance — it must never fail open.

A halt flag held in process memory is correct only while exactly one process serves traffic. On a
second replica or a fresh serverless invocation, an operator engaging the switch would see
``/v1/ops/kill-switch`` report "engaged" while other instances kept serving children. These tests
pin the shared-state behaviour: two independently constructed ``KillSwitch`` objects backed by the
same database — the closest in-process analogue of two instances — must agree.
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy.orm import Session, sessionmaker

from taleem_core.contexts.ops.adapters.persistence.base import (
    OpsBase,
    create_ops_engine,
    create_ops_session_factory,
)
from taleem_core.contexts.ops.adapters.persistence.kill_switch_store import SqlKillSwitchState
from taleem_core.platform.kill_switch import (
    InMemoryKillSwitchState,
    KillSwitch,
    is_child_facing,
)


@pytest.fixture()
def session_factory() -> sessionmaker[Session]:
    engine = create_ops_engine("sqlite://")
    OpsBase.metadata.create_all(engine)
    return create_ops_session_factory(engine)


def _switch(sf: sessionmaker[Session]) -> KillSwitch:
    """A KillSwitch as a separate 'instance' would build it: new object, same shared state."""
    return KillSwitch(time.time, SqlKillSwitchState(sf))


def test_engage_on_one_instance_halts_every_other_instance(
    session_factory: sessionmaker[Session],
) -> None:
    instance_a = _switch(session_factory)
    instance_b = _switch(session_factory)

    assert instance_a.engaged is False
    assert instance_b.engaged is False

    instance_a.engage("safeguarding incident")

    # The regression this guards: instance_b used to keep serving children.
    assert instance_b.engaged is True
    assert instance_b.status().reason == "safeguarding incident"


def test_disengage_on_one_instance_resumes_every_other_instance(
    session_factory: sessionmaker[Session],
) -> None:
    instance_a = _switch(session_factory)
    instance_b = _switch(session_factory)

    instance_a.engage("incident")
    assert instance_b.engaged is True

    instance_b.disengage()

    assert instance_a.engaged is False
    assert instance_a.status().reason == ""


def test_status_is_readable_by_an_instance_that_never_wrote_it(
    session_factory: sessionmaker[Session],
) -> None:
    _switch(session_factory).engage("power cut at the centre")

    fresh = _switch(session_factory)  # e.g. a cold start after the operator engaged it
    status = fresh.status()

    assert status.engaged is True
    assert status.reason == "power cut at the centre"
    assert status.changed_at > 0


def test_read_failure_fails_closed(session_factory: sessionmaker[Session]) -> None:
    """If the shared state cannot be read, report engaged — never keep serving children."""

    class BrokenFactory:
        def __call__(self) -> Session:
            raise RuntimeError("database unreachable")

    switch = KillSwitch(time.time, SqlKillSwitchState(BrokenFactory()))  # type: ignore[arg-type]

    assert switch.engaged is True
    assert "failing closed" in switch.status().reason


def test_in_memory_state_still_supported_for_single_process_use() -> None:
    """Local/dev/tests keep the process-local flag; the default constructor is unchanged."""
    switch = KillSwitch(time.time, InMemoryKillSwitchState())
    assert switch.engaged is False
    switch.engage("local test")
    assert switch.engaged is True
    switch.disengage()
    assert switch.engaged is False


def test_default_constructor_is_process_local() -> None:
    switch = KillSwitch(time.time)
    switch.engage("x")
    assert switch.engaged is True
    assert KillSwitch(time.time).engaged is False  # a separate default switch shares nothing


@pytest.mark.parametrize(
    "path",
    [
        "/v1/learning/sessions",
        "/v1/learning/students/S1/today",
        "/v1/offline/packages",
        "/v1/sync/batch",
    ],
)
def test_child_facing_paths_are_halted(path: str) -> None:
    assert is_child_facing(path) is True


@pytest.mark.parametrize("path", ["/health", "/metrics", "/v1/ops/status", "/v1/ops/kill-switch"])
def test_operator_and_health_paths_stay_up(path: str) -> None:
    assert is_child_facing(path) is False
