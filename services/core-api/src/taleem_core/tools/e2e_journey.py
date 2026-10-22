"""Recorded end-to-end journey against a *running* Core API (Phase A completion evidence).

Unlike ``pilot_simulator`` (which composes the app in-process), this tool is an HTTP client and
nothing else: it drives a real server — normally ``uvicorn`` backed by PostgreSQL — through the
public routes a guardian and a child would use, and prints a numbered transcript of every request
and its status code.

The journey:

    guardian registers → signs in → enrols a learner → (child sign-in refused before consent) →
    guardian grants consent → child taps their name on the roster and signs in with family code +
    PIN → refresh-token rotation → learning session (completes a published lesson, or — when no
    curriculum is published — asserts the honest "nothing to learn" decision) → guardian views
    progress → guardian withdraws consent → the child's refresh, re-sign-in and next request are
    refused → the guardian's audit trail holds every event.

Outcomes per step:

- ``PASS`` — the API behaved as the product promises.
- ``FAIL`` — it did not; the journey stops and the process exits 1.
- ``GAP``  — a *known* product gap (the behaviour is recorded honestly, not hidden). Gaps exit 0 so
  CI stays a regression gate for everything else; ``--strict`` turns them into exit 2.

Data is synthetic only: a random ``@example.invalid`` guardian, a random passphrase and PIN that
exist for one run. Secrets (tokens, passphrase, PIN, family code) are never printed; every rendered
line passes through a redactor that knows them.

Synthetic fixture content. A fresh database has no published curriculum, so ``--seed-fixture``
publishes one clearly labelled **synthetic test fixture** lesson (lesson id
``E2E-SYNTHETIC-FIXTURE-fractions``) through the real Curriculum Studio workflow, directly into the
database named by ``TALEEM_DATABASE_URL``. It refuses to run when ``TALEEM_ENV=production``. The
transcript labels any run that used it.

Usage::

    python -m taleem_core.tools.e2e_journey --base-url http://127.0.0.1:8765 --expect empty
    python -m taleem_core.tools.e2e_journey --seed-fixture
    python -m taleem_core.tools.e2e_journey --base-url http://127.0.0.1:8765 --expect content
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx

FIXTURE_LESSON_ID = "E2E-SYNTHETIC-FIXTURE-fractions"
FIXTURE_TITLE_PREFIX = "[SYNTHETIC E2E FIXTURE - not curriculum] "
# Decisions that honestly mean "there is nothing for you to learn right now".
NOTHING_TO_LEARN = frozenset({"rest", "complete"})
# Every one of these must appear in the guardian's audit trail by the end of the journey.
REQUIRED_AUDIT_ACTIONS = (
    "guardian.registered",
    "guardian.signed_in",
    "learner.created",
    "learner.sign_in_denied_no_consent",
    "consent.granted",
    "learner.signed_in",
    "session.refreshed",
    "consent.withdrawn",
)
MAX_RATE_LIMIT_WAIT_SECONDS = 130.0
# The header the server under test is told to trust for the client address
# (TALEEM_CLIENT_IP_HEADER=x-real-ip, as on Vercel). Each run sends its own synthetic address from
# the RFC 5737 documentation ranges, so back-to-back runs do not share one sign-in budget.
CLIENT_IP_HEADER = "X-Real-IP"
DEVICE_ID = "e2e-synthetic-device"
_RETRY_AFTER_TEXT = re.compile(r"try again in (\d+) seconds")
_WEAK_PINS = frozenset({"1234", "4321", "1212", "0123"})

PASS, FAIL, GAP = "PASS", "FAIL", "GAP"
_DESCRIPTION = "Recorded end-to-end journey against a running Core API (synthetic data only)."


class JourneyStepError(Exception):
    """A step did not behave as promised; the journey cannot meaningfully continue."""


@dataclass
class StepRecord:
    index: int
    outcome: str
    method: str
    path: str
    status: int | None
    title: str
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "outcome": self.outcome,
            "method": self.method,
            "path": self.path,
            "status": self.status,
            "title": self.title,
            "note": self.note,
        }


@dataclass
class Transcript:
    """The recorded journey. Everything it renders is scrubbed of the run's secrets."""

    steps: list[StepRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    _secrets: set[str] = field(default_factory=set)

    def protect(self, *values: str) -> None:
        """Register values that must never appear in any rendered output."""
        self._secrets.update(v for v in values if v and len(v) >= 4)

    def scrub(self, text: str) -> str:
        for value in sorted(self._secrets, key=len, reverse=True):
            text = text.replace(value, "[redacted]")
        return text

    def record(
        self,
        outcome: str,
        method: str,
        path: str,
        status: int | None,
        title: str,
        note: str = "",
    ) -> StepRecord:
        step = StepRecord(
            len(self.steps) + 1,
            outcome,
            method,
            self.scrub(path),
            status,
            self.scrub(title),
            self.scrub(note),
        )
        self.steps.append(step)
        return step

    def note(self, text: str) -> None:
        self.notes.append(self.scrub(text))

    @property
    def failures(self) -> list[StepRecord]:
        return [s for s in self.steps if s.outcome == FAIL]

    @property
    def gaps(self) -> list[StepRecord]:
        return [s for s in self.steps if s.outcome == GAP]

    def verdict(self, *, strict: bool = False) -> str:
        if self.failures:
            return FAIL
        if self.gaps and strict:
            return "FAIL (strict: known gaps)"
        return PASS

    @staticmethod
    def format_step(step: StepRecord) -> str:
        status = "---" if step.status is None else str(step.status)
        line = f"{step.index:02d} {step.outcome:<4} {step.method:<5} {step.path:<48} -> {status}"
        line += f"  {step.title}"
        if step.note:
            line += f"  [{step.note}]"
        return line

    def render(self, *, strict: bool = False) -> str:
        steps = "\n".join(self.format_step(s) for s in self.steps)
        return self.scrub(steps + "\n" + self.render_summary(strict=strict))

    def render_summary(self, *, strict: bool = False) -> str:
        lines = [f"   note: {n}" for n in self.notes]
        if self.gaps:
            lines.append("known gaps (recorded, not hidden):")
            lines += [f"   - step {g.index:02d}: {g.note}" for g in self.gaps]
        passed = sum(1 for s in self.steps if s.outcome == PASS)
        lines.append(
            f"verdict: {self.verdict(strict=strict)}  "
            f"({passed} pass, {len(self.failures)} fail, {len(self.gaps)} gap)"
        )
        return self.scrub("\n".join(lines))

    def to_dict(self, *, strict: bool = False) -> dict[str, Any]:
        return {
            "verdict": self.verdict(strict=strict),
            "steps": [s.to_dict() for s in self.steps],
            "notes": list(self.notes),
        }


def retry_after_seconds(response: httpx.Response) -> float | None:
    """How long a 429 asks us to wait — the ``Retry-After`` header, else the problem detail."""
    header = response.headers.get("retry-after")
    if header and header.strip().isdigit():
        return float(header.strip())
    try:
        detail = str(response.json().get("detail", ""))
    except (ValueError, AttributeError):
        return None
    match = _RETRY_AFTER_TEXT.search(detail)
    return float(match.group(1)) if match else None


def synthetic_pin(rand: Callable[[int], int] = secrets.randbelow) -> str:
    """A random four-digit PIN with four distinct digits (never a most-guessed sequence)."""
    while True:
        pin = f"{rand(10000):04d}"
        if len(set(pin)) == 4 and pin not in _WEAK_PINS:
            return pin


def synthetic_client_ip(rand: Callable[[int], int] = secrets.randbelow) -> str:
    """A random RFC 5737 documentation address (never routable, never a real client)."""
    prefix = ("192.0.2", "198.51.100", "203.0.113")[rand(3)]
    return f"{prefix}.{rand(254) + 1}"


def fixture_answer_key() -> dict[str, int]:
    """item_ref → correct option for the synthetic fixture lesson (the harness authored it)."""
    from ..vertical_slice.fractions_lesson import build_fractions_lesson

    key: dict[str, int] = {}
    for item in build_fractions_lesson().practice_questions:
        correct = dict(item.answer_key).get("correct_option", 0)
        key[item.item_id] = correct if isinstance(correct, int) else 0
    return key


def _json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {}


class Journey:
    """Drives one complete guardian → child → withdrawal journey over HTTP."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        expect: str = "auto",
        sleep: Callable[[float], None] = time.sleep,
        echo: Callable[[str], None] | None = None,
        max_rate_limit_wait: float = MAX_RATE_LIMIT_WAIT_SECONDS,
        client_ip: str | None = None,
    ) -> None:
        if expect not in {"auto", "empty", "content"}:
            raise ValueError(f"unknown expectation: {expect}")
        self.client = client
        self.expect = expect
        self.sleep = sleep
        self.echo = echo
        self.max_rate_limit_wait = max_rate_limit_wait
        self.client_ip = client_ip
        self.transcript = Transcript()
        self.branch = "unknown"

    # ------------------------------------------------------------------------------ plumbing

    def _send(
        self, method: str, path: str, token: str | None, body: dict[str, Any] | None
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        if self.client_ip:
            headers[CLIENT_IP_HEADER] = self.client_ip
        waited = 0.0
        while True:
            response = self.client.request(method, path, json=body, headers=headers)
            if response.status_code != 429:
                return response
            # The shared limiter counts refused attempts too, so wait out the window (plus a
            # second) rather than probing it.
            delay = (retry_after_seconds(response) or 5.0) + 1.0
            if waited + delay > self.max_rate_limit_wait:
                return response
            # The sign-in limiter is a product control, not a defect: honour it and say so.
            message = f"{method} {path} rate limited (429); waiting {delay:.0f}s"
            self.transcript.note(message)
            if self.echo:
                self.echo(f"   note: {self.transcript.scrub(message)}")
            self.sleep(delay)
            waited += delay

    def step(
        self,
        title: str,
        method: str,
        path: str,
        *,
        expect: int | Iterable[int],
        token: str | None = None,
        body: dict[str, Any] | None = None,
        check: Callable[[Any], str | None] | None = None,
        gap: str | None = None,
        note: Callable[[Any], str] | None = None,
    ) -> Any:
        """Run one request. A mismatch is a FAIL (raises), or a GAP if ``gap`` names it."""
        wanted = {expect} if isinstance(expect, int) else set(expect)
        response = self._send(method, path, token, body)
        payload = _json(response)
        problem: str | None = None
        if response.status_code not in wanted:
            code = payload.get("code") if isinstance(payload, dict) else None
            problem = f"expected {sorted(wanted)}, got {response.status_code}" + (
                f" ({code})" if code else ""
            )
        elif check is not None:
            problem = check(payload)
        if problem is None:
            record = self.transcript.record(
                PASS, method, path, response.status_code, title, note(payload) if note else ""
            )
        elif gap is not None:
            record = self.transcript.record(
                GAP, method, path, response.status_code, title, f"{gap}; observed: {problem}"
            )
        else:
            record = self.transcript.record(
                FAIL, method, path, response.status_code, title, problem
            )
        if self.echo:
            self.echo(self.transcript.scrub(Transcript.format_step(record)))
        if record.outcome == FAIL:
            raise JourneyStepError(record.note)
        return payload

    # ------------------------------------------------------------------------------- journey

    def run(self) -> Transcript:
        try:
            self._run()
        except JourneyStepError:
            pass
        except httpx.HTTPError as exc:
            self._record_failure("transport error", type(exc).__name__, raise_=False)
        except (KeyError, TypeError) as exc:
            self._record_failure("unexpected response shape", repr(exc), raise_=False)
        return self.transcript

    def _record_failure(self, title: str, note: str, *, raise_: bool = True) -> None:
        record = self.transcript.record(FAIL, "-", "-", None, title, note)
        if self.echo:
            self.echo(Transcript.format_step(record))
        if raise_:
            raise JourneyStepError(note)

    def _run(self) -> None:
        email = f"e2e-{uuid.uuid4().hex[:16]}@example.invalid"
        passphrase = secrets.token_urlsafe(24)
        pin = synthetic_pin()
        learner_name = f"Synthetic Learner {uuid.uuid4().hex[:6]}"
        self.transcript.protect(email, passphrase, pin)

        self.step("liveness probe", "GET", "/health", expect=200)
        self.step(
            "consent vocabulary (public)",
            "GET",
            "/v1/identity/policy",
            expect=200,
            check=lambda b: None if b.get("policy_version") else "no policy_version",
            note=lambda b: f"policy {b.get('policy_version')}",
        )

        registered = self.step(
            "guardian registers (synthetic @example.invalid)",
            "POST",
            "/v1/identity/guardians",
            expect=201,
            body={"email": email, "passphrase": passphrase, "displayName": "Synthetic Guardian"},
            check=lambda b: None if b.get("session", {}).get("access_token") else "no session",
        )
        family_code = str(registered["guardian"]["family_code"])
        self.transcript.protect(
            family_code,
            str(registered["session"]["access_token"]),
            str(registered.get("refresh_token", "")),
        )

        signed_in = self.step(
            "guardian signs in",
            "POST",
            "/v1/identity/guardians:signin",
            expect=200,
            body={"email": email, "passphrase": passphrase},
            check=lambda b: None if b.get("session", {}).get("role") == "guardian" else "role",
        )
        guardian_token = str(signed_in["session"]["access_token"])
        self.transcript.protect(guardian_token, str(signed_in.get("refresh_token", "")))

        learner = self.step(
            "guardian enrols a learner",
            "POST",
            "/v1/identity/learners",
            expect=201,
            token=guardian_token,
            body={"displayName": learner_name, "pin": pin, "gradeLevel": 4},
            check=lambda b: None if b.get("can_sign_in") is False else "sign-in before consent",
            note=lambda b: "can_sign_in=false until consent",
        )
        student_ref = str(learner["student_ref"])
        child_credentials = {
            "familyCode": family_code,
            "displayName": learner_name,
            "pin": pin,
            "deviceId": DEVICE_ID,
        }

        self.step(
            "child sign-in before consent is refused",
            "POST",
            "/v1/identity/learners:signin",
            expect=403,
            body=child_credentials,
            check=_problem_code("CONSENT_REQUIRED"),
        )
        self.step(
            "guardian grants consent (learning_data)",
            "POST",
            "/v1/identity/consents",
            expect=200,
            token=guardian_token,
            body={
                "studentRef": student_ref,
                "scopes": ["learning_data"],
                "attestation": "Synthetic e2e journey - no real child.",
            },
            check=lambda b: None if b.get("permits_sign_in") else "consent does not permit sign-in",
        )
        self.step(
            "child taps their name on the family roster",
            "POST",
            "/v1/identity/learners:roster",
            expect=200,
            body={"familyCode": family_code},
            check=lambda b: (
                None
                if any(e.get("display_name") == learner_name for e in b.get("learners", []))
                else "learner missing from roster"
            ),
        )
        child = self.step(
            "child signs in with family code + PIN",
            "POST",
            "/v1/identity/learners:signin",
            expect=200,
            body=child_credentials,
            check=lambda b: None if b.get("session", {}).get("role") == "student" else "role",
        )
        child_token = str(child["session"]["access_token"])
        child_refresh = str(child["refresh_token"])
        self.transcript.protect(child_token, child_refresh)

        rotated = self.step(
            "refresh token rotation",
            "POST",
            "/v1/identity/sessions:refresh",
            expect=200,
            body={"refreshToken": child_refresh, "deviceId": DEVICE_ID},
            check=lambda b: (
                None
                if b.get("refresh_token") and b["refresh_token"] != child_refresh
                else "refresh token did not rotate"
            ),
            note=lambda b: "successor issued; predecessor consumed",
        )
        child_token = str(rotated["session"]["access_token"])
        child_refresh = str(rotated["refresh_token"])
        self.transcript.protect(child_token, child_refresh)

        self._learning(child_token, student_ref)
        self._guardian_views(guardian_token, child_token, student_ref)

        self.step(
            "guardian withdraws consent (stop button)",
            "POST",
            "/v1/identity/consents:withdraw",
            expect=200,
            token=guardian_token,
            body={"studentRef": student_ref, "attestation": "Synthetic e2e journey - stop."},
            check=lambda b: None if b.get("permits_sign_in") is False else "still permits sign-in",
        )
        self.step(
            "child's refresh after withdrawal is refused",
            "POST",
            "/v1/identity/sessions:refresh",
            # Withdrawal revokes every live refresh token for the learner (uniform 401); a token
            # that somehow survived would meet the consent gate instead (403 CONSENT_REQUIRED).
            expect=(401, 403),
            body={"refreshToken": child_refresh, "deviceId": DEVICE_ID},
            note=lambda b: f"denied: {b.get('code')}",
        )
        self.step(
            "child's re-sign-in after withdrawal is refused",
            "POST",
            "/v1/identity/learners:signin",
            expect=403,
            body=child_credentials,
            check=_problem_code("CONSENT_REQUIRED"),
        )
        self.step(
            "child's next request with the still-unexpired access token",
            "POST",
            "/v1/learning/sessions",
            expect=(401, 403),
            token=child_token,
            body={"student_ref": student_ref},
            gap=(
                "learner access tokens are not consent-checked per request; withdrawal takes "
                "effect at the next refresh (access token TTL bounds the window)"
            ),
        )
        audit = self.step(
            "guardian reads the audit trail",
            "GET",
            "/v1/identity/audit?limit=200",
            expect=200,
            token=guardian_token,
            check=_audit_contains(REQUIRED_AUDIT_ACTIONS),
        )
        actions = sorted({str(e.get("action")) for e in audit.get("events", [])})
        self.transcript.note(f"audit actions observed: {', '.join(actions)}")

    def _learning(self, child_token: str, student_ref: str) -> None:
        packages = self.step(
            "child lists published lesson packages",
            "GET",
            "/v1/offline/packages",
            expect=200,
            token=child_token,
            note=lambda b: f"{len(b.get('packages', []))} published",
        )
        published = packages.get("packages", [])
        fixture = any(p.get("lesson_id") == FIXTURE_LESSON_ID for p in published)
        has_content = bool(published)
        self.branch = "content" if has_content else "empty"
        if fixture:
            self.transcript.note(
                f"content branch uses the SYNTHETIC TEST FIXTURE lesson {FIXTURE_LESSON_ID} "
                "(seeded by --seed-fixture; not curriculum)"
            )
        if self.expect != "auto" and self.expect != self.branch:
            self._record_failure(
                "curriculum expectation",
                f"expected '{self.expect}' but the API reports '{self.branch}'",
            )

        session = self.step(
            "child starts a learning session",
            "POST",
            "/v1/learning/sessions",
            expect=201,
            token=child_token,
            body={"student_ref": student_ref},
        )
        sid = str(session["session_id"])
        base = f"/v1/learning/sessions/{sid}"
        if not has_content:
            self.step(
                "planner gives the honest 'nothing to learn' decision",
                "POST",
                f"{base}:next",
                expect=200,
                token=child_token,
                check=lambda b: (
                    None
                    if b.get("decision") in NOTHING_TO_LEARN and not b.get("objective_code")
                    else f"decision {b.get('decision')!r} with no published curriculum"
                ),
                note=lambda b: f"decision={b.get('decision')}",
            )
            self.step(
                "child ends the session", "POST", f"{base}:end", expect=200, token=child_token
            )
            return

        decision = self.step(
            "planner chooses an objective",
            "POST",
            f"{base}:next",
            expect=200,
            token=child_token,
            check=lambda b: None if b.get("objective_code") else f"no objective: {b}",
            note=lambda b: f"decision={b.get('decision')} objective={b.get('objective_code')}",
        )
        objective = str(decision["objective_code"])
        taught = self.step(
            "lesson is taught from published content",
            "POST",
            f"{base}:teach",
            expect=200,
            token=child_token,
            body={"objective_code": objective},
            check=lambda b: None if b.get("items") else "no practice items",
            note=lambda b: f"{len(b.get('items', []))} practice items",
        )
        answers = fixture_answer_key()
        for item in taught["items"]:
            ref = str(item["item_ref"])
            self.step(
                f"child answers item {ref}",
                "POST",
                f"{base}:answer",
                expect=200,
                token=child_token,
                body={
                    "objective_code": objective,
                    "item_ref": ref,
                    "option": answers.get(ref, 0),
                    "hints_used": 0,
                },
                note=lambda b: f"outcome={b.get('outcome')} mastery={b.get('mastery')}",
            )
        self.step(
            "child completes the lesson (session ends)",
            "POST",
            f"{base}:end",
            expect=200,
            token=child_token,
            check=lambda b: None if str(b.get("state", "")).startswith("ended") else "not ended",
            note=lambda b: f"state={b.get('state')}",
        )
        self.step(
            "child's own progress reflects the attempts",
            "GET",
            f"/v1/learning/students/{student_ref}/progress",
            expect=200,
            token=child_token,
        )

    def _guardian_views(self, guardian_token: str, child_token: str, student_ref: str) -> None:
        self.step(
            "guardian views enrolled learners + consent state",
            "GET",
            "/v1/identity/learners",
            expect=200,
            token=guardian_token,
            check=lambda b: (
                None
                if any(
                    x.get("student_ref") == student_ref and x.get("can_sign_in")
                    for x in b.get("learners", [])
                )
                else "learner not listed as able to sign in"
            ),
        )
        self.step(
            "guardian views the child's learning progress (portal)",
            "GET",
            f"/v1/guardian/children/{student_ref}",
            expect=200,
            token=guardian_token,
            gap=(
                "the guardian portal links children from TALEEM_GUARDIAN_LINKS, not from "
                "identity enrolments, so a self-registered guardian cannot see progress"
            ),
        )


def _problem_code(code: str) -> Callable[[Any], str | None]:
    def check(body: Any) -> str | None:
        got = body.get("code") if isinstance(body, dict) else None
        return None if got == code else f"expected problem code {code}, got {got}"

    return check


def _audit_contains(required: Iterable[str]) -> Callable[[Any], str | None]:
    def check(body: Any) -> str | None:
        seen = {str(e.get("action")) for e in body.get("events", [])}
        missing = [a for a in required if a not in seen]
        return None if not missing else f"missing audit events: {', '.join(missing)}"

    return check


# ----------------------------------------------------------------------- synthetic fixture seeding


def seed_fixture_lesson(session_factory: Any) -> str:
    """Publish the synthetic fixture lesson through the real Curriculum Studio workflow.

    Returns ``"seeded"`` or ``"already-present"``. Idempotent. The lesson reuses the vertical-slice
    content (an authored original) under a fixture id and an unmistakable fixture title.
    """
    from ..contexts.curriculum_studio.adapters.persistence import unit_of_work
    from ..contexts.curriculum_studio.application.service import CurriculumStudioService
    from ..contexts.curriculum_studio.domain.content import Locale, LocalizedText
    from ..contexts.curriculum_studio.domain.workflow import ReviewAction
    from ..vertical_slice.fractions_lesson import build_fractions_lesson
    from ..vertical_slice.runner import REVIEW_ROLES

    def op(fn: Callable[[CurriculumStudioService], Any]) -> Any:
        with unit_of_work(session_factory) as uow:
            result = fn(CurriculumStudioService(uow.lessons, uow.publish, clock=time.time))
            uow.commit()
            return result

    if op(lambda s: s.find(FIXTURE_LESSON_ID)) is not None:
        return "already-present"
    lesson = build_fractions_lesson()
    lesson.lesson_id = FIXTURE_LESSON_ID
    lesson.title = LocalizedText(
        text={
            Locale.UR: lesson.title.text.get(Locale.UR, ""),
            Locale.EN: FIXTURE_TITLE_PREFIX + lesson.title.text.get(Locale.EN, ""),
        },
        audio_ref=dict(lesson.title.audio_ref),
    )
    op(lambda s: s.create(lesson))
    op(lambda s: s.submit(FIXTURE_LESSON_ID, "subject_author", "synthetic e2e fixture"))
    for role in REVIEW_ROLES:

        def approve(s: CurriculumStudioService, role: str = role) -> Any:
            return s.review(FIXTURE_LESSON_ID, ReviewAction.APPROVE, role)

        op(approve)
    op(lambda s: s.publish(FIXTURE_LESSON_ID, "curriculum_architect", "synthetic e2e fixture"))
    return "seeded"


def _seed_from_environment() -> int:
    from ..contexts.curriculum_studio.adapters.persistence import (
        create_db_engine,
        create_session_factory,
    )

    if os.environ.get("TALEEM_ENV", "").strip().lower() == "production":
        print("refusing to seed a synthetic fixture: TALEEM_ENV=production", file=sys.stderr)
        return 1
    url = os.environ.get("TALEEM_DATABASE_URL", "").strip()
    if not url:
        print("refusing to seed: TALEEM_DATABASE_URL is unset", file=sys.stderr)
        return 1
    engine = create_db_engine(url)
    try:
        result = seed_fixture_lesson(create_session_factory(engine))
    finally:
        engine.dispose()
    host = url.split("@")[-1] if "@" in url else "(local)"
    print(f"synthetic fixture lesson {FIXTURE_LESSON_ID}: {result} (database {host})")
    return 0


# --------------------------------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=_DESCRIPTION)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--expect", choices=("auto", "empty", "content"), default="auto")
    parser.add_argument("--strict", action="store_true", help="known gaps fail the run (exit 2)")
    parser.add_argument("--json", dest="json_path", help="also write the transcript as JSON")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--client-ip",
        help=f"send this client address as {CLIENT_IP_HEADER} ('auto': a random RFC 5737 address)",
    )
    parser.add_argument(
        "--seed-fixture",
        action="store_true",
        help="publish the synthetic fixture lesson into TALEEM_DATABASE_URL and exit",
    )
    args = parser.parse_args(argv)
    if args.seed_fixture:
        return _seed_from_environment()

    print("=" * 100)
    print(f"PROJECT TALEEM - END-TO-END JOURNEY (synthetic data) against {args.base_url}")
    started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    print(f"expectation: {args.expect}   started: {started}   client: {args.client_ip or 'direct'}")
    print("=" * 100)
    with httpx.Client(base_url=args.base_url, timeout=args.timeout) as client:
        client_ip = synthetic_client_ip() if args.client_ip == "auto" else args.client_ip
        journey = Journey(client, expect=args.expect, echo=print, client_ip=client_ip)
        transcript = journey.run()
    print("-" * 100)
    print(transcript.render_summary(strict=args.strict))
    print(f"curriculum branch: {journey.branch}")
    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            payload = {**transcript.to_dict(strict=args.strict), "branch": journey.branch}
            json.dump(payload, fh, indent=2)
    if transcript.failures:
        return 1
    if transcript.gaps and args.strict:
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
