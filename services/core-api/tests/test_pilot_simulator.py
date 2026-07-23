"""Pilot 0 simulator harness — Software Completion Mode.

Verifies the runnable synthetic-user simulator drives the real composed app to a PASS verdict:
complete journeys, mastery, misconception detection, offline signature verification, and safe
failure-injection + recovery. Guards against the harness silently regressing.
"""

from __future__ import annotations

from taleem_core.tools import pilot_simulator as sim


def test_simulation_passes_all_invariants() -> None:
    report = sim.run(sim.SimConfig(students=6, offline=True, fail_inject=True, seed=7))
    assert report.passed, report.to_dict()
    t = report.totals
    assert t["students"] == 6
    assert t["completed"] == 6
    assert t["mastered"] >= 3  # majority master at the default 0.8 accuracy
    assert t["misconceptions_detected"] >= 1  # forced student confirms one misconception
    assert t["offline_ok"] == 6  # every offline package Ed25519-verifies
    assert report.latency_ms["p95"] >= 0.0


def test_main_returns_zero_on_pass() -> None:
    code = sim.main(["--students", "4", "--quiet"])
    assert code == 0


def test_failure_injection_checks_present() -> None:
    report = sim.run(sim.SimConfig(students=3, fail_inject=True, seed=11))
    names = {i["name"] for i in report.invariants}
    assert {
        "failinject_idor_denied_403",
        "failinject_unauth_denied_401",
        "failinject_malformed_is_4xx",
        "failinject_recovers_after_failure",
    } <= names
    assert report.passed, report.to_dict()
