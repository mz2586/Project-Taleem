# Post-Pilot Backlog

Status: **Phase 10 — Pilot Validation.** Everything **not required for Pilot 0** becomes the backlog,
separated into **Must have before Pilot 1** · **Should have** · **Future enhancements**. Grounded in
[PILOT_READINESS_REVIEW.md](PILOT_READINESS_REVIEW.md) and the phase design docs. **No new features are
proposed here** — this is a triage of already-identified work (gaps G-A…G-G, the offline 6.2C plan, the
governance workstreams WS1–WS16, and the AI-strategy tiers).

> **Boundary.** *Conditions to run Pilot 0* (C1–C6, audio / content arc / session UI / infra +
> kill-switch / assurance / safeguarding drill) live in [GO_NO_GO_DECISION.md](GO_NO_GO_DECISION.md) —
> they are **not** backlog. This document is what comes **after** Pilot 0.

---

## A. Must have before Pilot 1 (real children)

These are **hard gates or MVP items** for putting the product in front of children — mostly
governance/safety, plus the assurance items Pilot 1 requires.

| Item | Source | Gate |
| --- | --- | --- |
| **M-Gov closure** — DPIA signed, lawful basis, **consent per child**, residency decided, mandatory-reporting policy | Master WS1 | **hard gate** |
| **Child-safe production auth** — device-linked, guardian-provisioned identity (replaces the dev stub); production JWKS/KMS (FD-14) | Master WS3; G-G | **hard gate** (M-Gov) |
| **M-Safe** — operational safeguarding live + staffed + **SLA-drilled**; mandatory-reporting workflow | Master WS2 | **hard gate** |
| **Guardian identity + child-linkage + `guardian` grant** — thin authz/linkage over existing derived reads | Phase 9; G-G | M-Gov |
| **Admin / enrolment** — cohort roster, mentor↔learner assignment, consent-before-enrolment, persisted mentor notes | Master WS8; G-G | M-Gov |
| **At-rest encryption of C2 IndexedDB (production keys)** — AES-GCM wrapper (mechanism designable now); keys per FD-14 | Offline 6.2C SG-2; G-G | FD-14 |
| **Data-residency pinning** — sync endpoint / package host / telemetry in-region | Offline 6.2C SG-4; G-G | FD-02 |
| **De-enrolment / consent-withdrawal purge trigger** — server signal (client purge mechanism already built, 6.2C-1) | Offline 6.2C SG-5 | M-Gov |
| **Independent child-safety review** passed | Master WS1 | **hard gate** |
| **Accessibility audit with disabled participants**; **security pentest** (if not already closed in Pilot 0) | Master WS11/WS14 | assurance |

## B. Should have (strengthens Pilot 1+, not a hard gate)

| Item | Source | Why |
| --- | --- | --- |
| **Durable server-side sessions** (off in-memory) | G-D; Master WS15/H1 | cleaner cross-device reconciliation (offline-lite already works via the client saga) |
| **Full offline sessions** (Option B: ported deterministic, LLM-free runtime) | Offline arch §11 (G2) | at-home offline adaptivity for Pilot 2 (offline-lite suffices for Pilot 1) |
| **Automated offline safety-flag routing** (`safety.flag` delta + server sink + priority) | Offline 6.2C B2 (M-Safe) | required for **unsupervised** at-home offline; Pilot 1 uses on-site supervision |
| **Consent-gated telemetry upload** — over the existing local diagnostics | Offline 6.2C B3 | operate the service at scale; measure efficacy (consent + residency) |
| **Durable server-side idempotency ledger** (persist `client_event_id` + cursor) | Offline sync §7 (G5) | non-attempt-delta idempotency across restart (attempts already durable via evidence) |
| **Content breadth** — the rest of Grade 4 authored to full depth + published + packaged | Phase 7; G-B | more content once the pilot arc is validated |
| **AI Teacher / guardian / mentor front-end screens** — the designed experiences as real UI | Phase 8/9; G-C | full product experience beyond the Pilot-0 session UI |
| **Real-device matrix automation** (low-end Android / storage / network / profile) | Offline 6.2C B5 | broader device coverage beyond the pilot device |
| **N+1 / performance hardening + read caching** | CTO/PRR (M3/H5) | scale readiness (fine at pilot scale) |
| **Web-manifest icons + Save-Data polish** | Offline G8 | minor UX/PWA completeness |

## C. Future enhancements (post-Pilot, scale + capability)

| Item | Source | Notes |
| --- | --- | --- |
| **Generative AI tiers** (small model → frontier, **rephrasing only**, behind `LLMGateway`) — off for children, off offline, independent safety review first | AI strategy; Phase 8 §5 | never sources curriculum; gated |
| **More grades (KG–10)** authored via the production system | Phase 7 framework | scale content after Grade 4 pilots |
| **Additional subjects / languages / curriculum variants** (multi-province) | Master (Pilot 5) | national-scale content |
| **Hardware-backed key storage / WebAuthn device binding** for the offline token | Offline 6.2C C4 | beyond FD-14 baseline |
| **National-scale infra** — multi-region, CDN, sharding proven under 5k+ load, cost model | Master (Pilot 3–5) | scale after supervised pilots |
| **Rich engagement / gamification, push notifications, full admin suite** | MVP "excluded" | intentionally deferred past the MVP |
| **Institutional integrations / partnerships (NCC/MoFEPT MoU)** | Master (Pilot 5) | accelerator for national scale + authoritative SLO ingestion |

---

## D. Triage rules applied

- **Anything gating children** (consent, child-safe auth, live safeguarding, residency, at-rest keys) →
  **A (must have before Pilot 1)**, mostly M-Gov/M-Safe/FD-14.
- **Anything that strengthens the product but has a working pilot-scale substitute** (durable sessions,
  full offline, telemetry, more content, full UI) → **B (should have)**.
- **Anything for scale or new capability** (generative tiers, more grades, national infra) → **C
  (future)**.
- **The MVP non-negotiables** (child safety first, approved-content-only AI, no child PII, mentor-
  mediated summative, audio-first, WCAG 2.2 AA, governance/consent before any child) are **not backlog**
  — they hold at every rung, always.

The backlog is deliberately a **triage of known work**, not a new roadmap: Pilot 0 validates the core;
Pilot 1 needs the **A** items (governance-led); **B/C** follow as the pilots scale.
