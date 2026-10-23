"""Seed SYNTHETIC families and teachers for the k6 scenarios (setup only; never timed).

Drives the real public API of a running Core API, exactly as a guardian and an operator would:

    operator (system token) creates one organization and T teachers
    each teacher signs in, creates a class, assigns the synthetic fixture lesson's objective
    each family: guardian registers -> enrols one learner -> grants learning_data consent ->
                 joins the learner to a class (records progress_sharing)

Every family and teacher gets its own RFC 5737 documentation address (192.0.2.0/24,
198.51.100.0/24, 203.0.113.0/24 — never routable) sent as X-Real-IP, so the production sign-in rate
limits stay untouched and each address spends at most one attempt here.

The system token is minted with the DEVELOPMENT HS256 secret, so this only works against a dev
server; it refuses TALEEM_ENV=production. Output is a JSON file of synthetic credentials for k6; it
is written outside the repository (run.sh puts it in the run's output directory).

    python tests/perf/seed.py --base-url http://127.0.0.1:8790 --families 110 --teachers 3 \
        --out /tmp/taleem-perf/seed.json
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.tools.e2e_journey import (
    FIXTURE_LESSON_ID,
    fixture_answer_key,
    synthetic_pin,
)
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE

_PREFIXES = ("192.0.2", "198.51.100", "203.0.113")
ADDRESS_SPACE = len(_PREFIXES) * 254  # 762 synthetic client addresses
_ATTEST = "Synthetic performance test - no real child."


def synthetic_ip(index: int) -> str:
    """The index-th RFC 5737 address (0 <= index < 762)."""
    if not 0 <= index < ADDRESS_SPACE:
        raise ValueError(f"only {ADDRESS_SPACE} RFC 5737 addresses exist; got index {index}")
    return f"{_PREFIXES[index // 254]}.{index % 254 + 1}"


def _expect(response: httpx.Response, status: int, what: str) -> dict[str, Any]:
    if response.status_code != status:
        raise RuntimeError(f"{what}: expected {status}, got {response.status_code}: {response.text}")
    body = response.json()
    return body if isinstance(body, dict) else {}


def _h(ip: str, token: str | None = None) -> dict[str, str]:
    headers = {"X-Real-IP": ip}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def seed_teachers(client: httpx.Client, count: int, system: str) -> list[dict[str, Any]]:
    org = _expect(
        client.post(
            "/v1/school/organizations",
            json={
                "name": f"Synthetic Perf School {uuid.uuid4().hex[:6]}",
                "country": "PK",
                "curriculumPackId": "pk-g4-math",
                "defaultLocale": "ur",
            },
            headers={"Authorization": f"Bearer {system}"},
        ),
        201,
        "create organization",
    )
    org_id = org["organization_id"]
    teachers = []
    for j in range(count):
        ip = synthetic_ip(ADDRESS_SPACE - 1 - j)  # teachers take addresses from the top
        email = f"perf-teacher-{uuid.uuid4().hex[:10]}@example.invalid"
        passphrase = secrets.token_urlsafe(18)
        _expect(
            client.post(
                f"/v1/school/organizations/{org_id}/teachers",
                json={"email": email, "displayName": f"Synthetic Teacher {j}", "passphrase": passphrase},
                headers={"Authorization": f"Bearer {system}"},
            ),
            201,
            "create teacher",
        )
        session = _expect(
            client.post(
                "/v1/school/teachers:signin",
                json={"email": email, "passphrase": passphrase, "deviceId": "perf-seed"},
                headers=_h(ip),
            ),
            200,
            "teacher sign-in",
        )
        token = session["session"]["access_token"]
        klass = _expect(
            client.post("/v1/school/classes", json={"name": f"Perf Class {j}"}, headers=_h(ip, token)),
            201,
            "create class",
        )
        assignment = _expect(
            client.post(
                f"/v1/school/classes/{klass['class_id']}/assignments",
                json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 7 * 86400},
                headers=_h(ip, token),
            ),
            201,
            "create assignment",
        )
        teachers.append(
            {
                "email": email,
                "passphrase": passphrase,
                "ip": ip,
                "class_id": klass["class_id"],
                "join_code": klass["join_code"],
                "assignment_id": assignment["assignment_id"],
            }
        )
    return teachers


def seed_family(client: httpx.Client, index: int, join_code: str) -> dict[str, Any]:
    ip = synthetic_ip(index)
    email = f"perf-guardian-{uuid.uuid4().hex[:12]}@example.invalid"
    passphrase = secrets.token_urlsafe(18)
    pin = synthetic_pin()
    name = f"Synthetic Learner {index:03d}"
    reg = _expect(
        client.post(
            "/v1/identity/guardians",
            json={"email": email, "passphrase": passphrase, "displayName": "Synthetic Guardian"},
            headers=_h(ip),
        ),
        201,
        "guardian registers",
    )
    token = reg["session"]["access_token"]
    learner = _expect(
        client.post(
            "/v1/identity/learners",
            json={"displayName": name, "pin": pin, "gradeLevel": 4},
            headers=_h(ip, token),
        ),
        201,
        "enrol learner",
    )
    ref = learner["student_ref"]
    _expect(
        client.post(
            "/v1/identity/consents",
            json={"studentRef": ref, "scopes": ["learning_data"], "attestation": _ATTEST},
            headers=_h(ip, token),
        ),
        200,
        "grant consent",
    )
    _expect(
        client.post(
            "/v1/school/classes:join",
            json={"classCode": join_code, "studentRef": ref, "attestation": _ATTEST},
            headers=_h(ip, token),
        ),
        200,
        "join class",
    )
    return {
        "index": index,
        "ip": ip,
        "email": email,
        "passphrase": passphrase,
        "family_code": reg["guardian"]["family_code"],
        "display_name": name,
        "pin": pin,
        "student_ref": ref,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8790")
    parser.add_argument("--families", type=int, default=110)
    parser.add_argument("--teachers", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if os.environ.get("TALEEM_ENV", "").strip().lower() == "production":
        print("refusing: TALEEM_ENV=production (synthetic seeding only)", file=sys.stderr)
        return 1
    if args.families + args.teachers > ADDRESS_SPACE:
        print(f"families + teachers must be <= {ADDRESS_SPACE}", file=sys.stderr)
        return 1
    secret = os.environ.get("TALEEM_JWT_DEV_SECRET", "dev-only-not-secret")
    system = sign_hs256(
        {"sub": "perf-seed-operator", "role": "system", "exp": int(time.time()) + 3600}, secret
    )
    started = time.perf_counter()
    with httpx.Client(base_url=args.base_url, timeout=120.0) as client:
        teachers = seed_teachers(client, args.teachers, system)
        codes = [t["join_code"] for t in teachers]
        with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            families = list(
                pool.map(
                    lambda i: seed_family(client, i, codes[i % len(codes)]), range(args.families)
                )
            )
    seed = {
        "synthetic": True,
        "lesson_id": FIXTURE_LESSON_ID,
        "objective_code": OBJECTIVE_CODE,
        "answer_key": fixture_answer_key(),
        "item_refs": sorted(fixture_answer_key()),
        "teachers": teachers,
        "families": families,
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(seed, fh)
    os.chmod(args.out, 0o600)
    elapsed = time.perf_counter() - started
    print(
        f"seeded {len(families)} synthetic families + {len(teachers)} teachers "
        f"in {elapsed:.1f}s (setup, not timed)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
