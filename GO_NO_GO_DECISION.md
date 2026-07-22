# Go / No-Go Decision — Pilot 0

Status: **Phase 10 — Pilot Validation. Formal recommendation.** Based on
[PILOT_READINESS_REVIEW.md](PILOT_READINESS_REVIEW.md) and
[PILOT_RISK_REGISTER.md](PILOT_RISK_REGISTER.md). Scope: readiness to **run Pilot 0** (internal
end-to-end dry run — **no children**). Every conclusion is evidence-backed.

---

## Recommendation

## ✅ GO WITH CONDITIONS

**GO** on the platform's engineering and design readiness — the architecture, AI Teacher, offline
platform, and synchronization are **complete, tested (97% backend coverage; 169 + 78 tests; all gates
green), and their hardest guarantees are proven** (no data loss / no double-count; no hallucination /
no answer leak; no child PII). **No open Critical risk.**

**WITH CONDITIONS** because Pilot 0 cannot *execute* until a bounded set of **build + deploy + assurance
activities** land — the very work Pilot 0 exists to complete and exit on. These are engineering/content/
ops tasks, **not** architectural or safety-design failures.

> **Separate, unchanged verdict for Pilot 1 (real children): NO-GO until M-Gov + M-Safe.** Child-safe
> auth, guardian/child linkage, live safeguarding + mandatory-reporting, and consent are governance/
> safety gates — out of scope for Pilot 0, hard blockers for Pilot 1.

---

## 1. Why GO (evidence)

| Claim | Evidence |
| --- | --- |
| Architecture is production-grade + reversible | mypy `--strict` clean; 97% coverage; `test_learning_*`, `test_studio_*`, `test_schema_parity`, `test_hardening_4_2` |
| Sync loses no data + never double-counts | `test_sync_evidence` (duplicate + **crash-recovery**); FE `syncCrashRecovery` (120-attempt long session) |
| Offline content is authentic + tamper-evident | Ed25519 sign + verify with locked Python↔WebCrypto interop vector — `test_ed25519`, FE `signature`, `packagesHardening` |
| AI Teacher never hallucinates or leaks the answer | **invariants** in `test_ai_teacher` (grounded / non-generative / no-answer) |
| No child PII; IDOR-guarded; no generative AI to children | IDOR 403 tests; pseudonymous `student_ref`; capability matrix `disabled_offline` (AR-C-06) |
| Every pilot journey step is implemented + tested | [PILOT_READINESS_REVIEW.md](PILOT_READINESS_REVIEW.md) §2 (per-step evidence) |
| Ops, device, incident, metrics documented | [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md), [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md), [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md), [PILOT_SUCCESS_METRICS.md](PILOT_SUCCESS_METRICS.md) |
| No open Critical risk | [PILOT_RISK_REGISTER.md](PILOT_RISK_REGISTER.md) §5 (all Critical mitigated) |

## 2. The conditions (must be met to run + exit Pilot 0)

Pilot 0's success criteria (PILOT_PLAN) are the exit gate; these are the conditions:

| # | Condition | Gap | Owner | Exit check |
| --- | --- | --- | --- | --- |
| **C1** | Record + QA **Urdu audio** for the pilot content set | G-A | Content/Media | audio + captions play for every pilot lesson, offline |
| **C2** | Author + review + **publish a coherent content arc** (through the pipeline) + build signed packages | G-B | Content/Curriculum | a multi-lesson arc is published + packaged + verified |
| **C3** | Complete the **student-session UI** to run the full journey (offline lib already built + tested) | G-C | Frontend | a tester completes a session online **and** offline |
| **C4** | **Deploy** infra + monitoring + backups/DR + **kill-switch + rollback** | G-E | SRE/Ops | staging up; kill-switch + rollback **tested** |
| **C5** | Run the **assurance pass**: a11y audit, security review + pentest, load test | G-F | QA/Security | each passed; findings closed |
| **C6** | **Drill the safeguarding path** (distress → human within SLA) | G-F | Safeguarding | drill routes to a human within SLA |

**When C1–C6 are green, Pilot 0 has passed** — and its exit is the gate into Pilot 1 (which then needs
M-Gov + M-Safe).

## 3. Why not NO-GO

A NO-GO would imply an architectural, safety, or design failure that blocks the pilot regardless of
effort. **There is none:** the hard problems (offline correctness, content integrity, AI safety, no
data loss, no PII) are **solved and proven**. The open items are bounded, well-understood execution
tasks with clear owners and exit checks — the definition of "conditions," not "no-go."

## 4. Why not unconditional GO

An unconditional GO would claim Pilot 0 can run **today**. It cannot: there is **no recorded audio**, no
**published content arc** beyond one lesson, the **session UI** isn't complete enough to run the full
journey, and **infra + the assurance run + the safeguarding drill** haven't happened. Honesty requires
naming these as conditions.

## 5. Conditions vs governance gates (do not conflate)

- **Conditions (C1–C6):** engineering/content/ops — Pilot 0 completes them; they gate **running Pilot
  0**.
- **Governance gates (M-Gov, M-Safe):** consent, child-safe auth, live safeguarding — they gate **Pilot
  1 (children)**, not Pilot 0. Pilot 0 uses the dev stub + no children + a safeguarding **drill**.

## 6. Decision record

| Field | Value |
| --- | --- |
| Decision | **GO WITH CONDITIONS** (Pilot 0) |
| Scope | Internal end-to-end dry run, **no children** |
| Blocking conditions | C1–C6 (audio, content arc, session UI, infra + kill-switch, assurance run, safeguarding drill) |
| Open Critical risks | **None** |
| Pilot 1 (children) | **NO-GO** until M-Gov + M-Safe (unchanged) |
| Basis | [PILOT_READINESS_REVIEW.md](PILOT_READINESS_REVIEW.md), [PILOT_RISK_REGISTER.md](PILOT_RISK_REGISTER.md); 97% coverage, 169 + 78 tests, all gates green |
| Approver | *(human sign-off required)* |

**Recommendation to the approver:** authorize Pilot 0 preparation to proceed against conditions C1–C6;
hold the Pilot-0 dry run until C4–C6 are verified; keep Pilot 1 behind M-Gov + M-Safe.
