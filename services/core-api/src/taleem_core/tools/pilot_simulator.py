"""Pilot 0 simulator — synthetic students, offline verification, failure injection, recovery.

A runnable operational harness for the **Pilot 0 internal dry run** (no children, dev-stub auth). It
spins up the *real* composed application in-process (against a temp SQLite DB), publishes the sample
lesson through the real Curriculum Studio workflow, then drives N synthetic students through full
learning journeys via the real HTTP surface (start → next → teach → answer → end). It measures
throughput/latency, checks platform invariants, optionally verifies signed offline packages, and
optionally injects failures to prove the system degrades safely and *recovers*.

This complements ``tests/test_pilot0_assurance.py`` (which asserts invariants under pytest): the
simulator is an operator-facing dry-run tool that produces a citable report for the pilot runbook.

Usage:
    python -m taleem_core.tools.pilot_simulator --students 20 --offline --fail-inject
    python -m taleem_core.tools.pilot_simulator --students 50 --json report.json --quiet

Exit code is non-zero if any invariant fails, so it can gate a pilot go/no-go dry run in CI.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ..auth.jwt_verifier import sign_hs256
from ..contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from ..contexts.curriculum_studio.application.service import CurriculumStudioService
from ..contexts.curriculum_studio.domain.workflow import ReviewAction
from ..contexts.learning.domain.offline_package import signing_payload
from ..main import create_app
from ..platform import ed25519
from ..platform.config import Settings
from ..vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

_SECRET = "dev-only-not-secret"  # noqa: S105 (Pilot 0 uses the documented dev stub, no children)
_REVIEW_ROLES = (
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
)
# Response keys that would indicate raw child PII leaking — must never appear (child-safety).
_PII_KEYS = ("full_name", "email", "phone", "dob", "birth", "guardian_name")


@dataclass
class ItemSpec:
    """What a synthetic student needs to know to answer an item at a target accuracy."""

    item_ref: str
    correct_option: int
    n_options: int
    misconception_option: int | None  # a wrong option that triggers a known misconception


@dataclass
class SimConfig:
    students: int = 20
    seed: int = 1234
    accuracy: float = 0.8  # probability a synthetic student answers each item correctly
    offline: bool = False  # verify a signed offline package per student
    fail_inject: bool = False  # inject failures + verify safe degradation and recovery


@dataclass
class SimReport:
    config: dict[str, Any]
    totals: dict[str, int] = field(default_factory=dict)
    latency_ms: dict[str, float] = field(default_factory=dict)
    invariants: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(i["ok"] for i in self.invariants) and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "verdict": "PASS" if self.passed else "FAIL",
            "totals": self.totals,
            "latency_ms": self.latency_ms,
            "invariants": self.invariants,
            "errors": self.errors,
        }


def _auth(role: str, sub: str) -> dict[str, str]:
    exp = int(time.time()) + 3600
    tok = sign_hs256({"sub": sub, "role": role, "exp": exp}, _SECRET)
    return {"Authorization": f"Bearer {tok}"}


def _publish_sample_lesson(app: FastAPI) -> None:
    """Publish the sample lesson through the real authoring workflow (author→review→publish)."""
    sf = app.state.studio_session_factory
    clock = lambda: 1000.0  # noqa: E731

    def op(fn: Any) -> None:
        with cs_uow(sf) as uow:
            svc = CurriculumStudioService(uow.lessons, uow.publish, clock=clock)
            fn(svc)
            uow.commit()

    op(lambda s: s.create(build_fractions_lesson()))
    op(lambda s: s.submit(LESSON_KEY, "subject_author"))
    for role in _REVIEW_ROLES:
        op(lambda s, role=role: s.review(LESSON_KEY, ReviewAction.APPROVE, role))
    op(lambda s: s.publish(LESSON_KEY, "curriculum_architect", "v1"))


def _item_specs() -> list[ItemSpec]:
    """Derive per-item answer knowledge from the source lesson (a trusted internal harness)."""
    specs: list[ItemSpec] = []
    for it in build_fractions_lesson().practice_questions:
        key: dict[str, Any] = dict(it.answer_key)
        correct = int(key.get("correct_option", 0) or 0)
        misc_raw = key.get("option_misconceptions") or {}
        misc_map: dict[str, Any] = dict(misc_raw) if isinstance(misc_raw, dict) else {}
        misc_opt = next((int(k) for k in misc_map), None)
        specs.append(ItemSpec(it.item_id, correct, len(it.options), misc_opt))
    return specs


class _Timer:
    """Accumulates per-request latencies for percentile reporting."""

    def __init__(self) -> None:
        self.samples: list[float] = []

    def timed(self, fn: Any) -> Any:
        start = time.perf_counter()
        result = fn()
        self.samples.append((time.perf_counter() - start) * 1000.0)
        return result

    def percentiles(self) -> dict[str, float]:
        if not self.samples:
            return {"p50": 0.0, "p95": 0.0, "max": 0.0}
        s = sorted(self.samples)

        def pct(p: float) -> float:
            idx = min(len(s) - 1, int(p * len(s)))
            return round(s[idx], 2)

        return {"p50": pct(0.50), "p95": pct(0.95), "max": round(s[-1], 2)}


def _run_student(
    client: TestClient,
    student: str,
    specs: list[ItemSpec],
    rng: random.Random,
    accuracy: float,
    timer: _Timer,
    report: SimReport,
    force_misconception: bool = False,
) -> dict[str, int]:
    """Drive one synthetic student through a full journey. Returns per-student counters."""
    counters = {"mastered": 0, "misconceptions": 0, "completed": 0}
    h = _auth("student", student)

    started = timer.timed(
        lambda: client.post("/v1/learning/sessions", json={"student_ref": student}, headers=h)
    )
    if started.status_code != 201:
        report.errors.append(f"{student}: start session -> {started.status_code}")
        return counters
    session_id = started.json()["session_id"]

    timer.timed(lambda: client.post(f"/v1/learning/sessions/{session_id}:next", headers=h))
    timer.timed(
        lambda: client.post(
            f"/v1/learning/sessions/{session_id}:teach",
            json={"objective_code": OBJECTIVE_CODE},
            headers=h,
        )
    )

    for spec in specs:
        # One student deterministically triggers each known misconception so detection is exercised
        # regardless of the RNG/accuracy setting.
        if force_misconception and spec.misconception_option is not None:
            correct = False
        else:
            correct = rng.random() < accuracy
        if correct:
            option = spec.correct_option
        elif spec.misconception_option is not None:
            option = spec.misconception_option  # exercise misconception detection
        else:
            wrong = [o for o in range(spec.n_options) if o != spec.correct_option]
            option = rng.choice(wrong) if wrong else spec.correct_option
        resp = timer.timed(
            lambda spec=spec, option=option: client.post(
                f"/v1/learning/sessions/{session_id}:answer",
                json={
                    "objective_code": OBJECTIVE_CODE,
                    "item_ref": spec.item_ref,
                    "option": option,
                    "hints_used": 0,
                },
                headers=h,
            )
        )
        if resp.status_code != 200:
            report.errors.append(f"{student}: answer {spec.item_ref} -> {resp.status_code}")
            continue
        body = resp.json()
        if body.get("state") == "mastered":
            counters["mastered"] = 1
        counters["misconceptions"] += len(body.get("confirmed_misconceptions") or [])

    # Deterministically *confirm* a misconception: it is SUSPECTED on the first hit and CONFIRMED on
    # a second consecutive hit (a correct answer in between clears it). One student hits the
    # misconception item wrong twice in a row so the detection pipeline fires end-to-end.
    if force_misconception:
        misc_spec = next((s for s in specs if s.misconception_option is not None), None)
        if misc_spec is not None:
            for _ in range(2):
                r = timer.timed(
                    lambda spec=misc_spec: client.post(
                        f"/v1/learning/sessions/{session_id}:answer",
                        json={
                            "objective_code": OBJECTIVE_CODE,
                            "item_ref": spec.item_ref,
                            "option": spec.misconception_option,
                            "hints_used": 0,
                        },
                        headers=h,
                    )
                )
                if r.status_code == 200:
                    counters["misconceptions"] += len(
                        r.json().get("confirmed_misconceptions") or []
                    )

    ended = timer.timed(lambda: client.post(f"/v1/learning/sessions/{session_id}:end", headers=h))
    if ended.status_code == 200:
        counters["completed"] = 1
    else:
        report.errors.append(f"{student}: end -> {ended.status_code}")
    return counters


def _verify_offline(client: TestClient, student: str, report: SimReport) -> bool:
    """Download the signed offline package; verify the Ed25519 signature + no answer keys ship."""
    h = _auth("student", student)
    pkg = client.get(f"/v1/offline/packages/{LESSON_KEY}", headers=h)
    if pkg.status_code != 200:
        report.errors.append(f"{student}: offline package -> {pkg.status_code}")
        return False
    m = pkg.json()["manifest"]
    keys = client.get("/v1/offline/signing-keys", headers=h).json()["keys"]
    key = next((k for k in keys if k["key_id"] == m["signing_key_id"]), None)
    if key is None:
        report.errors.append(f"{student}: signing key {m['signing_key_id']} not found")
        return False
    payload = signing_payload(m["package_id"], m["version"], m["content_hash"])
    verified = ed25519.verify(
        bytes.fromhex(m["signature"]), payload, bytes.fromhex(key["public_key_hex"])
    )
    no_answers = "correct_option" not in str(pkg.json()["content"])
    if not (verified and no_answers):
        report.errors.append(
            f"{student}: offline verify failed (sig={verified} clean={no_answers})"
        )
    return verified and no_answers


def _inject_failures(client: TestClient, report: SimReport) -> dict[str, bool]:
    """Inject hostile/malformed requests; each must fail *safely*. Then prove normal use recovers.

    Returns a name→bool map of the safe-degradation checks (all must be True).
    """
    victim = "fi-victim"
    attacker = _auth("student", "fi-attacker")
    checks: dict[str, bool] = {}

    # 1. Cross-student access is denied (IDOR guard) — not a 500.
    checks["idor_denied_403"] = (
        client.get(f"/v1/learning/students/{victim}/today", headers=attacker).status_code == 403
    )
    # 2. Unauthenticated protected read is rejected (deny-by-default).
    checks["unauth_denied_401"] = (
        client.get(f"/v1/learning/students/{victim}/today").status_code == 401
    )
    # 3. Malformed answer body is a clean 4xx, never a 5xx crash.
    h = _auth("student", "fi-recover")
    started = client.post("/v1/learning/sessions", json={"student_ref": "fi-recover"}, headers=h)
    sid = started.json()["session_id"]
    bad = client.post(
        f"/v1/learning/sessions/{sid}:answer", json={"objective_code": "nope"}, headers=h
    )
    checks["malformed_is_4xx"] = 400 <= bad.status_code < 500
    # 4. Recovery: after the bad request, a well-formed request on the same session still succeeds
    #    (plan → teach → answer, the real journey order).
    client.post(f"/v1/learning/sessions/{sid}:next", headers=h)
    client.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h
    )
    good = client.post(
        f"/v1/learning/sessions/{sid}:answer",
        json={"objective_code": OBJECTIVE_CODE, "item_ref": "p1-one-of-four", "option": 0},
        headers=h,
    )
    checks["recovers_after_failure"] = good.status_code == 200
    for name, ok in checks.items():
        if not ok:
            report.errors.append(f"fail-injection check '{name}' did not hold")
    return checks


def run(config: SimConfig) -> SimReport:
    """Run the full simulation against the real composed app and return a structured report."""
    report = SimReport(config=config.__dict__.copy())
    app = create_app(Settings(database_url=""))
    _publish_sample_lesson(app)
    client = TestClient(app)
    specs = _item_specs()
    rng = random.Random(config.seed)  # noqa: S311 (synthetic test data, not cryptographic)
    timer = _Timer()

    totals = {"students": 0, "completed": 0, "mastered": 0, "misconceptions": 0, "offline_ok": 0}
    for i in range(config.students):
        student = f"sim-stu-{i:04d}"
        c = _run_student(
            client,
            student,
            specs,
            rng,
            config.accuracy,
            timer,
            report,
            force_misconception=(i == 0),
        )
        totals["students"] += 1
        totals["completed"] += c["completed"]
        totals["mastered"] += c["mastered"]
        totals["misconceptions"] += c["misconceptions"]
        if config.offline and _verify_offline(client, student, report):
            totals["offline_ok"] += 1

    # Read the real platform counters (the detection pipeline's own signal) from the ops surface.
    ops = client.get("/v1/ops/status", headers=_auth("system", "sim-operator")).json()
    counters = ops.get("counters", {})
    totals["misconceptions_detected"] = int(counters.get("misconceptions_detected", 0))
    totals["objectives_mastered"] = int(counters.get("objectives_mastered", 0))
    report.totals = totals
    report.latency_ms = timer.percentiles()

    # Child-safety invariant: no PII in any student-facing read for a sampled student.
    pii_clean = True
    if config.students:
        h = _auth("student", "sim-stu-0000")
        for path in ("today", "history", "knowledge"):
            body = client.get(f"/v1/learning/students/sim-stu-0000/{path}", headers=h).text.lower()
            if any(f'"{k}"' in body for k in _PII_KEYS):
                pii_clean = False

    fail_checks: dict[str, bool] = {}
    if config.fail_inject:
        fail_checks = _inject_failures(client, report)

    # Invariants the dry run must satisfy.
    inv = report.invariants
    inv.append(_check("all_sessions_completed", totals["completed"] == totals["students"]))
    inv.append(_check("majority_mastered", totals["mastered"] >= max(1, totals["students"] // 2)))
    inv.append(_check("misconceptions_detected", totals["misconceptions_detected"] >= 1))
    inv.append(_check("no_child_pii_leaked", pii_clean))
    inv.append(_check("no_request_errors", not report.errors or config.fail_inject))
    if config.offline:
        inv.append(_check("offline_packages_verified", totals["offline_ok"] == totals["students"]))
    if config.fail_inject:
        for name, ok in fail_checks.items():
            inv.append(_check(f"failinject_{name}", ok))
    return report


def _check(name: str, ok: bool) -> dict[str, Any]:
    return {"name": name, "ok": bool(ok)}


def _print_summary(report: SimReport) -> None:
    d = report.to_dict()
    print(f"\n=== Pilot 0 Simulation — {d['verdict']} ===")
    t = d["totals"]
    print(
        f"students={t['students']} completed={t['completed']} mastered={t['mastered']} "
        f"misconceptions={t['misconceptions']} offline_ok={t['offline_ok']}"
    )
    lat = d["latency_ms"]
    print(f"latency ms: p50={lat['p50']} p95={lat['p95']} max={lat['max']}")
    print("invariants:")
    for i in d["invariants"]:
        print(f"  [{'PASS' if i['ok'] else 'FAIL'}] {i['name']}")
    if d["errors"]:
        print(f"errors ({len(d['errors'])}):")
        for e in d["errors"][:10]:
            print(f"  - {e}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Project Taleem — Pilot 0 synthetic-user simulator"
    )
    parser.add_argument("--students", type=int, default=20)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--accuracy", type=float, default=0.8)
    parser.add_argument(
        "--offline", action="store_true", help="verify a signed package per student"
    )
    parser.add_argument(
        "--fail-inject", action="store_true", help="inject failures + verify recovery"
    )
    parser.add_argument("--json", dest="json_path", default=None, help="write the report as JSON")
    parser.add_argument("--quiet", action="store_true", help="suppress the human summary")
    ns = parser.parse_args(argv)

    config = SimConfig(
        students=ns.students,
        seed=ns.seed,
        accuracy=ns.accuracy,
        offline=ns.offline,
        fail_inject=ns.fail_inject,
    )
    report = run(config)
    if ns.json_path:
        with open(ns.json_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2)
    if not ns.quiet:
        _print_summary(report)
    return 0 if report.passed else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
