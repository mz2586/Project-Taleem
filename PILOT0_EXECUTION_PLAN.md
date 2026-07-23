# Pilot 0 Execution Plan

Status: **Phase 11 — Pilot 0 Execution Readiness.** This phase exists **solely to satisfy conditions
C1–C6** from [GO_NO_GO_DECISION.md](GO_NO_GO_DECISION.md). It reviews each condition, completes the
engineering that directly satisfies them (automatable assurance), and packages the remaining
human/ops/content execution. **No architecture redesign, no new product features, no domain-model
changes.** Companions: [PILOT0_CHECKLIST.md](PILOT0_CHECKLIST.md),
[PILOT0_OPERATIONS.md](PILOT0_OPERATIONS.md), [FINAL_READINESS_REPORT.md](FINAL_READINESS_REPORT.md).

---

## 0. The conditions (from the approved Go/No-Go)

| ID | Condition | Type |
| --- | --- | --- |
| **C1** | Record + QA **Urdu audio** for the pilot content set | Content/Media |
| **C2** | Author + review + **publish a coherent content arc** + build signed packages | Content/Curriculum |
| **C3** | Complete the **student-session UI** to run the full journey | Frontend |
| **C4** | **Deploy** infra + monitoring + backups/DR + **kill-switch + rollback** | Infra/Ops |
| **C5** | Run the **assurance pass**: a11y audit, security review + pentest, load test | QA/Security |
| **C6** | **Drill the safeguarding path** (distress → human within SLA) | Safeguarding |

**Reality of a code-environment phase:** C1 (human recording), C4 (real cloud deployment), the
external a11y-audit + pentest in C5, and C6 (live human drill) **cannot be *executed* in code** — they
are inherently human/operational. This phase therefore (a) **completes the automatable engineering**
(C5 automation), and (b) **packages the rest turnkey** so a human team can execute quickly. Honest
per-condition status is in [FINAL_READINESS_REPORT.md](FINAL_READINESS_REPORT.md).

---

## 1. Condition review (WS1)

### C1 — Record + QA Urdu audio

- **Current status:** **Blocked (external).** The full audio **production spec** exists
  ([AUDIO_SCRIPT_GUIDE.md](AUDIO_SCRIPT_GUIDE.md)): voice/delivery spec, segmentation, timing metadata,
  asset spec, glossary, and the packaging path (audio ships inside the offline package). **No audio is
  recorded** — recording requires a human narrator.
- **Remaining work:** record + QA the Urdu narration (+ captions) for the pilot content set per the
  guide; fill `measured_duration_ms`; package + verify offline playback.
- **Dependencies:** an approved narrator; the pilot content arc (C2).
- **Owner:** Content/Media.
- **Exit criteria:** every pilot lesson has recorded Urdu audio + captions; plays offline on the pilot
  device; passes the content-QA audio checks.

### C2 — Publish a coherent content arc + signed packages

- **Current status:** **Partially complete.** The **production system** (framework, pipeline over the
  Curriculum Studio `Workflow`, standards, QA) is complete; the **whole chain is proven end-to-end** by
  the live fractions lesson (`MATH-G4-FR-01`): authored → reviewed through the five workflow gates →
  published → offline package **built + Ed25519-signed + verified**. Grade 4 is spine-complete.
- **Remaining work:** author a coherent multi-lesson arc to full depth, run each lesson through the
  **human review gates**, publish, and build signed packages.
- **Dependencies:** authors + human reviewers (subject-expert, instructional-design, a11y, language,
  safety); C1 audio.
- **Owner:** Content/Curriculum.
- **Exit criteria:** a published, packaged, signature-verified multi-lesson arc a tester can complete.

### C3 — Complete the student-session UI

- **Current status:** **Partially complete.** The engine underneath is done + tested — AI Teacher
  (`:explain`), session flow (`:next/:teach/:answer/:hint/:end`), offline lib (download/verify/resume/
  sync). The Student Portal exists as a governance-safe scaffold with the session/today/homework/
  progress pages; the **full session-flow screens** wired to the AI Teacher + offline are the remaining
  frontend build.
- **Remaining work:** complete the session-flow UI so a tester runs a full journey **online and
  offline**; surface the AI Teacher explanation/confidence + offline status.
- **Dependencies:** C1 audio (for the audio-first UI), C2 content.
- **Owner:** Frontend.
- **Exit criteria:** a tester completes a session end-to-end, online and offline, with audio.

### C4 — Deploy infra + monitoring + kill-switch

- **Current status:** **Blocked (external).** The operational design exists ([PILOT_RUNBOOK.md](PILOT_RUNBOOK.md),
  [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md), [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)) and this
  phase adds the go-live/rollback/support procedures ([PILOT0_OPERATIONS.md](PILOT0_OPERATIONS.md)). The
  actual **deployment** (provision IaC, monitoring, backups/DR, kill-switch) is an ops activity.
- **Remaining work:** deploy the staging environment; wire monitoring + alerting + backups; deploy +
  **test** the kill-switch + rollback.
- **Dependencies:** FD-02 residency host decision; ops team.
- **Owner:** SRE/Ops.
- **Exit criteria:** staging up; monitoring + backups live; kill-switch + rollback **tested**.

### C5 — Assurance pass

- **Current status:** **Partially complete.** The **automatable assurance is now COMPLETE** (this phase)
  — a repeatable [tests/test_pilot0_assurance.py](services/core-api/tests/test_pilot0_assurance.py)
  suite validates **security** (auth-required, IDOR, no child PII), **offline** (signed package verify,
  no answer keys), **load/integrity** (100-attempt batch applied exactly once + idempotent replay,
  no double-count), and **AI safety** (grounded / non-generative / no-answer / disabled-offline). The
  **human/external** portions — on-device **a11y audit** with disabled participants and an **external
  pentest** — remain.
- **Remaining work:** run the on-device a11y audit + external pentest; a real-device load test.
- **Dependencies:** the deployed environment (C4); a11y participants; a pentest vendor.
- **Owner:** QA/Security.
- **Exit criteria:** automated assurance green (**done**); a11y audit + pentest + real-device load pass.

### C6 — Safeguarding drill

- **Current status:** **Blocked (external).** The procedure exists ([INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md)
  §2, [PILOT0_OPERATIONS.md](PILOT0_OPERATIONS.md)). The **live drill** is a human activity.
- **Remaining work:** run a drill — a simulated distress signal routes to a human within the SLA;
  verify the reporting workflow.
- **Dependencies:** safeguarding lead staffed + on-call; the deployed environment (C4).
- **Owner:** Safeguarding.
- **Exit criteria:** distress → human within SLA in the drill; reporting workflow verified.

---

## 2. Implementation done this phase (WS2)

**Only engineering that directly satisfies an approved condition, fits the architecture, and is
completable in code:**

- **C5 automatable assurance — DONE.** `tests/test_pilot0_assurance.py`: a consolidated, repeatable
  Pilot-0 assurance validation over the composed app — security / offline / load-integrity / AI-safety.
  Runs on SQLite + PostgreSQL-gated. **No new features, no domain changes.**

Not done (deliberately, per instructions): no post-pilot features; no redesign; the human/ops/content
execution items (C1, C4, C6, and the human parts of C2/C3/C5) are packaged, not performed — see the
checklists.

---

## 3. Dependency + sequencing view

```text
FD-02 residency ─┐
                 ├─► C4 deploy ─┬─► C5 (a11y+pentest+load, on the env) ─┐
narrator ─► C1 audio ─┐        └─► C6 safeguarding drill ───────────────┤
authors+reviewers ─► C2 content ─► (C1 packaged) ─► C3 session UI ───────┴─► Pilot 0 dry run
```

Critical execution path to *starting* the dry run: **C4 (deploy) + C1 (audio) + C2 (content) + C3
(UI)**; the dry run then *performs* **C5 (a11y/pentest/load) + C6 (drill)** as its exit criteria.

---

## 4. What "ready" requires (summary)

The platform + automated assurance + operational package are ready. **Starting** the Pilot 0 dry run
needs the human/ops/content items above. The formal per-condition re-evaluation + recommendation is in
[FINAL_READINESS_REPORT.md](FINAL_READINESS_REPORT.md).
