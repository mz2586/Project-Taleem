"""Create (or re-verify) the synthetic demo accounts on a running Taleem API, through real flows.

Nothing here bypasses authentication: the guardian registers with ``POST /v1/identity/guardians``,
enrols a learner, grants consent, and the child signs in with the family code + PIN exactly as the
app does. If published lessons exist, the child then plays a short live session (some right, some
wrong answers) so progress screens show real evidence.

Every account is unmistakably synthetic: an ``@example.org`` address (reserved, undeliverable),
display names that say "Demo", and a learner who is not a real child. Re-running is safe: an
existing demo guardian signs in instead of registering, and an existing demo learner is reused.

Credentials are written only to ``--out`` (a local file, never the repository) and never logged.

    python -m taleem_core.tools.demo_accounts --base-url https://<api> --out /path/demo.json
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path
from typing import Any

import httpx

DEMO_EMAIL = "taleem.demo.guardian@example.org"
DEMO_GUARDIAN_NAME = "Demo Guardian (synthetic)"
DEMO_LEARNER_NAME = "Demo Learner"
DEMO_DEVICE = "demo-device-1"
CONSENT_SCOPES = ["learning_data", "progress_sharing"]
ATTESTATION = "Synthetic demo account for product exploration. Not a real child."


class DemoError(RuntimeError):
    pass


def _check(r: httpx.Response, *ok: int) -> Any:
    if r.status_code not in ok:
        raise DemoError(
            f"{r.request.method} {r.request.url.path} -> {r.status_code}: {r.text[:300]}"
        )
    return r.json() if r.content else {}


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def ensure_guardian(c: httpx.Client, passphrase: str) -> tuple[str, str]:
    """(guardian access token, family code). Registers on first run, signs in afterwards."""
    r = c.post(
        "/v1/identity/guardians:signin", json={"email": DEMO_EMAIL, "passphrase": passphrase}
    )
    if r.status_code == 200:
        body = r.json()
        return str(body["session"]["access_token"]), str(body["guardian"]["family_code"])
    body = _check(
        c.post(
            "/v1/identity/guardians",
            json={"email": DEMO_EMAIL, "passphrase": passphrase, "displayName": DEMO_GUARDIAN_NAME},
        ),
        201,
    )
    return str(body["session"]["access_token"]), str(body["guardian"]["family_code"])


def ensure_learner(c: httpx.Client, token: str, pin: str) -> str:
    listed = _check(c.get("/v1/identity/learners", headers=_bearer(token)), 200)
    for learner in listed.get("learners", []):
        if learner.get("display_name") == DEMO_LEARNER_NAME:
            return str(learner["student_ref"])
    body = _check(
        c.post(
            "/v1/identity/learners",
            headers=_bearer(token),
            json={"displayName": DEMO_LEARNER_NAME, "pin": pin, "gradeLevel": 4},
        ),
        201,
    )
    return str(body["student_ref"])


def grant_consent(c: httpx.Client, token: str, student_ref: str) -> None:
    _check(
        c.post(
            "/v1/identity/consents",
            headers=_bearer(token),
            json={"studentRef": student_ref, "scopes": CONSENT_SCOPES, "attestation": ATTESTATION},
        ),
        200,
    )


def child_signin(c: httpx.Client, family_code: str, pin: str) -> str:
    body = _check(
        c.post(
            "/v1/identity/learners:signin",
            json={
                "familyCode": family_code,
                "displayName": DEMO_LEARNER_NAME,
                "pin": pin,
                "deviceId": DEMO_DEVICE,
            },
        ),
        200,
    )
    if body.get("session", {}).get("role") != "student":
        raise DemoError("child sign-in did not return a student session")
    return str(body["session"]["access_token"])


def play_session(c: httpx.Client, child_token: str, student_ref: str) -> dict[str, Any]:
    """Play one live session if any lesson is published; answers vary so evidence is mixed."""
    h = _bearer(child_token)
    started = c.post("/v1/learning/sessions", headers=h, json={"student_ref": student_ref})
    if started.status_code != 201:
        return {"played": False, "reason": f"no session ({started.status_code})"}
    sid = started.json()["session_id"]
    nxt = c.post(f"/v1/learning/sessions/{sid}:next", headers=h, json={})
    objective = (nxt.json() or {}).get("objective_code") if nxt.status_code == 200 else None
    if not objective:
        return {"played": False, "reason": "no objective to teach (no published lesson)"}
    teach = c.post(
        f"/v1/learning/sessions/{sid}:teach", headers=h, json={"objective_code": objective}
    )
    if teach.status_code != 200:
        return {"played": False, "reason": f"teach {teach.status_code}"}
    answered = 0
    for turn, item in enumerate(teach.json().get("items", [])[:6]):
        if (item.get("kind") or "choose") != "choose" or not item.get("options"):
            continue
        option = 0 if turn % 3 else min(1, len(item["options"]) - 1)  # some wrong on purpose
        r = c.post(
            f"/v1/learning/sessions/{sid}:answer",
            headers=h,
            json={"objective_code": objective, "item_ref": item["item_ref"], "option": option},
        )
        if r.status_code == 200:
            answered += 1
    c.post(f"/v1/learning/sessions/{sid}:end", headers=h, json={})
    return {"played": answered > 0, "answers": answered}


def run(base_url: str, out: Path) -> dict[str, Any]:
    existing: dict[str, Any] = {}
    if out.exists():
        existing = json.loads(out.read_text(encoding="utf-8"))
    passphrase = existing.get("guardian_passphrase") or secrets.token_urlsafe(18)
    pin = existing.get("learner_pin") or f"{secrets.randbelow(10**4):04d}"
    with httpx.Client(base_url=base_url, timeout=60.0) as c:
        token, family_code = ensure_guardian(c, passphrase)
        student_ref = ensure_learner(c, token, pin)
        grant_consent(c, token, student_ref)
        child_token = child_signin(c, family_code, pin)
        session = play_session(c, child_token, student_ref)
        progress = c.get(
            f"/v1/learning/students/{student_ref}/progress", headers=_bearer(child_token)
        )
        # Isolation: the child's token must not read guardian-only data.
        isolation = c.get("/v1/identity/learners", headers=_bearer(child_token)).status_code
    result = {
        "api": base_url,
        "guardian_email": DEMO_EMAIL,
        "guardian_passphrase": passphrase,
        "family_code": family_code,
        "learner_display_name": DEMO_LEARNER_NAME,
        "learner_pin": pin,
        "student_ref": student_ref,
        "session": session,
        "progress_status": progress.status_code,
        "child_token_on_guardian_route": isolation,
    }
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    out.chmod(0o600)
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m taleem_core.tools.demo_accounts")
    p.add_argument("--base-url", required=True)
    p.add_argument("--out", type=Path, required=True, help="local credentials file (not in git)")
    args = p.parse_args(argv)
    try:
        result = run(args.base_url.rstrip("/"), args.out)
    except DemoError as exc:
        print(f"demo setup failed: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in {"guardian_passphrase", "learner_pin"}},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
