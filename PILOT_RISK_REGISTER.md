# Pilot Risk Register — Pilot 0

Status: **Phase 10 — Pilot Validation.** Risks to running **Pilot 0** (internal dry run, no children),
reviewed across **technical, operational, educational, and safeguarding** dimensions and ranked
**Critical / High / Medium / Low**. Grounded in the validated platform state
([PILOT_READINESS_REVIEW.md](PILOT_READINESS_REVIEW.md)). Distinct from the pre-pilot strategy register
([RISK_REGISTER.md](RISK_REGISTER.md), which spans the whole road to national scale) — this one is
scoped to **executing Pilot 0**.

> **Rule:** any **Critical** safeguarding or child-data risk open ⇒ **NO-GO**. For Pilot 0 (no
> children) the safeguarding risks are about **drilling** the safety net, not live child exposure — but
> they are still treated with the highest seriousness because Pilot 0 exists to prove the net works
> before Pilot 1.

Each row: **risk · rank · likelihood · impact · mitigation · evidence/status.**

---

## 1. Technical risks

| Risk | Rank | L | I | Mitigation | Evidence / status |
| --- | --- | --- | --- | --- | --- |
| Offline data loss / double-count on sync | **Critical** (if unproven) → **Mitigated** | Low | High | Idempotent durable consumer (dedupe on `evidence_id` + `client_event_id`); durable queue | **Proven** — `test_sync_evidence` (duplicate + crash-recovery), FE `syncCrashRecovery` (120-attempt) |
| Tampered/unapproved content reaching a tester | **High** → **Mitigated** | Low | High | Ed25519 signing + client verify before install | **Proven** — `test_ed25519`, `signature`, `packagesHardening` |
| Durable sessions in-memory → progress loss on restart | **Medium** | Med | Med | Client-side session saga is the durability layer (offline-lite); resume tested | FE `checkpoint`/`idb`; gap G-D (backlog) |
| Low-end device storage exhaustion | **Medium** → **Mitigated** | Med | Med | LRU eviction of disposable packages; never evicts the queue; `persist()` | FE `packagesHardening` (eviction) |
| Cross-language signing interop breaks | **Medium** → **Mitigated** | Low | Med | Locked interop vector asserted in both suites | `test_ed25519` + FE `signature` (same vector) |
| Frontend session UI incomplete → cannot run the journey | **High** | Med | High | Complete the student-session screens (offline lib already built + tested) | Gap G-C (Pilot-0 activity) |

## 2. Operational risks

| Risk | Rank | L | I | Mitigation | Evidence / status |
| --- | --- | --- | --- | --- | --- |
| Infra/monitoring/backups/kill-switch not deployed | **High** | High | High | Deploy IaC + monitoring + backups + kill-switch before the dry run (Pilot-0 exit) | Docs exist (Phase 9); deployment pending — gap G-E |
| Pilot device not verified end-to-end | **High** | Med | High | Run the device-prep checklist on the actual device model | [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md); pending — gap G-F |
| Kill-switch / rollback unproven in an incident | **High** | Low | High | Build + **test** kill-switch + rollback in Pilot 0 | [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md); pending drill |
| No load test at Pilot-1 scale + headroom | **Medium** | Med | Med | Load test as a Pilot-0 exit criterion | Pending — gap G-F |
| Support/runbook gaps surface mid-dry-run | **Low** | Med | Low | Support runbook + on-call; Pilot 0 refines them | [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md) §5 |

## 3. Educational risks

| Risk | Rank | L | I | Mitigation | Evidence / status |
| --- | --- | --- | --- | --- | --- |
| No recorded Urdu audio → audio-first path not exercisable | **High** | High | High | Record + QA Urdu audio for the pilot content set | Scripts/spec exist ([AUDIO_SCRIPT_GUIDE.md](AUDIO_SCRIPT_GUIDE.md)); pending — gap G-A |
| Content arc too thin to exercise a real journey | **High** | High | Med | Author + review + publish a coherent multi-lesson arc through the pipeline | Grade 4 spine-complete; 1 lesson live — gap G-B |
| AI Teacher gives wrong/ungrounded content | **Critical** (if possible) → **Mitigated** | Low | High | Templated, structurally grounded; invariants proven | `test_ai_teacher` (grounded / no-answer / non-generative) |
| AI auto-promotes a learner | **High** → **Mitigated** | Low | High | Summative mentor-mediated; never auto-graded by sync | `test_sync_evidence` (summative ignored), `assessments.mentor_mediated` |
| Mis-tuned pedagogy params on real learners | **Medium** | Med | Med | Validate on Pilot-1 data; conservative defaults; human-mediated | Not applicable to Pilot 0 (no children) |

## 4. Safeguarding risks

| Risk | Rank | L | I | Mitigation | Evidence / status |
| --- | --- | --- | --- | --- | --- |
| Safeguarding escalation not exercised before children | **High** | — | High | **Drill** distress→human within SLA in Pilot 0; on-call safeguarding lead | [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md); Pilot-0 drill pending |
| Offline distress can't reach a remote human immediately | **High** (Pilot 1) / **N/A** (Pilot 0) | — | High | Pilot 1 on-site supervision; offline crisis affordance queues a flag; automated routing is M-Safe | Design ([AI_TEACHER_OFFLINE.md](AI_TEACHER_OFFLINE.md)); not exercised with children in Pilot 0 |
| Any child PII leaks | **Critical** → **Mitigated** | Low | High | Pseudonymous `student_ref` only; no PII in stores/tokens/telemetry/logs; IDOR-guarded | `test_ai_teacher`/`test_student_api` (IDOR 403); no C3 on pilot surfaces |
| Generative AI reaches a child | **Critical** → **Mitigated** | Very low | High | No generative model in the tier; disabled offline (AR-C-06) | `test_ai_teacher` (non-generative invariant); capability matrix `disabled_offline` |

---

## 5. Ranked summary (Pilot 0)

- **Critical — all MITIGATED (none open):** offline data loss, ungrounded/hallucinated AI, child-PII
  leak, generative-to-child — each closed by proven engineering + invariants. **No open Critical
  risk.**
- **High — open, all Pilot-0 *activities* (not design failures):** deploy infra + kill-switch (G-E);
  device verification + assurance run (G-F); record Urdu audio (G-A); publish a content arc (G-B);
  complete the session UI (G-C); **run the safeguarding drill**.
- **Medium:** durable sessions (G-D, backlog); load test; storage/eviction (mitigated); interop
  (mitigated).
- **Low:** support-runbook refinement (Pilot 0 will polish it).

**Bottom line:** **no open Critical risk**; the open **High** risks are the **bounded execution items
Pilot 0 is designed to complete and exit on** — not architectural or safety-design failures. This is the
basis for a **GO WITH CONDITIONS** ([GO_NO_GO_DECISION.md](GO_NO_GO_DECISION.md)).
