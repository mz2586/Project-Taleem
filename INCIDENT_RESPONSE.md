# Incident Response Guide

Status: **Phase 9 — Pilot Operations.** How the pilot responds to incidents — **safety first**, then
data, then availability. For Pilot 1 (on-site, supervised). Reuses the existing platform controls
(kill-switch, rollback, signed packages, durable queue, safeguarding runbook); no new architecture.
Companions: [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md), [DEVICE_PREPARATION.md](DEVICE_PREPARATION.md).

> **Overriding rule:** a **child-safety incident outranks everything**. When in doubt, protect the
> child, pause the activity, and escalate to the on-site safeguarding lead — never handle a serious
> concern alone, never delay to investigate technically first.

---

## 1. Incident classes + severity

| Class | Example | Severity | Primary owner |
| --- | --- | --- | --- |
| **Child safety / wellbeing** | a child in distress; a safeguarding disclosure | **S0 (highest)** | Safeguarding lead |
| **Child-data / privacy** | suspected exposure of learning data; wrong-learner data shown | **S1** | Engineering + safeguarding + DPO |
| **Content safety** | an unsafe/incorrect/inappropriate item reached a child | **S1** | Content + safety officer |
| **Sync/data-integrity** | attempts appear lost or double-counted | **S2** | Engineering |
| **Availability** | app won't open / packages won't install offline | **S2/S3** | Engineering + site coordinator |
| **Device** | lost/stolen/broken device | **S2** | Site coordinator (MDM wipe) |

---

## 2. S0 — Child safety / wellbeing (the priority)

1. **Protect + reassure the child** immediately; the **present mentor/safeguarding lead** responds (in
   Pilot 1 the human is on-site — the primary safety layer, the compensating control for offline).
2. **Pause** the child's activity if needed; the child's wellbeing comes before any lesson.
3. **Follow the safeguarding runbook + mandatory-reporting policy** (M-Safe). Escalate to the
   safeguarding lead; if warranted, the mandatory-reporting channel is followed (policy-defined,
   clinician + legal sign-off — the M-Safe substance).
4. **Record** per the safeguarding process (C4, strictest handling, least-privilege, no logging of
   sensitive detail).
5. **Offline note:** if the child triggered the offline crisis affordance, the queued **safety flag**
   syncs on reconnect; the immediate response is the present human.

**Never:** never delay a safety response to debug software; never let a technical incident deprioritize
a child.

## 3. S1 — Child-data / privacy

1. **Contain:** if a learner's data is exposed or the wrong learner's data is shown, **switch/clear**
   the profile (per-profile namespacing + clear-on-switch), and if needed **kill-switch** the affected
   surface.
2. **Assess:** what data (C2 learning only — there is **no child PII/C3** on the pilot surfaces),
   scope, and cause.
3. **Notify:** DPO + safeguarding lead; follow the breach process (residency/PDPB obligations, M-Gov).
4. **Remediate:** fix + verify; if a learner is de-enrolled, the **purge** clears on-device C2 at next
   connect (6.2C-1).

## 4. S1 — Content safety

1. **Remove from delivery:** archive/rollback the offending lesson (Curriculum Studio `ARCHIVE`/
   `ROLLBACK`); rebuild packages without it.
2. **Verify:** the AI Teacher is grounded — it can only emit authored content, so a content fix is the
   fix (no generative path to also patch). Re-run the batch-grounding scan.
3. **Root-cause** through the review gates: which gate should have caught it (subject-expert / a11y /
   language / **child-safety**)? Strengthen it.

## 5. S2 — Sync / data-integrity

1. **Reassure:** the durable queue means offline work is **not lost**; grading is queued by design.
2. **Verify no double-count:** the sync engine is idempotent (evidence dedup by `evidence_id` +
   `client_event_id`, 6.2B) — a replay is a `duplicate`, never a second record. Confirm via the sync
   diagnostics.
3. **Drain:** confirm the queue drains on reconnect; a poison delta dead-letters without blocking the
   rest (surface to engineering).

## 6. S2/S3 — Availability + device

- **App won't open offline:** re-verify SW registration + shell precache; re-download + **verify**
  packages (never bypass signature/hash).
- **Packages won't install:** check pinned signing key + storage; LRU-evict disposable packages
  (never the queue).
- **Lost/stolen device:** MDM **remote wipe**; the device holds only C0 curriculum + pseudonymous C2
  (no PII); rotate if needed.

## 7. Kill-switch + rollback (platform controls)

- **Kill-switch:** halt child-facing use immediately for any S0/S1 (a serious safety/data incident
  **pauses the pilot**).
- **Rollback:** roll back app/content/package versions; offline packages are **signed + content-hashed**
  so a rollback is a *verified* older package, never an unsigned one.

## 8. Communication + escalation ladder

```text
Mentor / site coordinator  →  Safeguarding lead (S0/S1 safety)  →  DPO (S1 data)
                            →  Engineering on-call (S1–S3 technical)  →  Program lead
```

- **S0:** immediate, in person, then safeguarding lead — within the safeguarding SLA.
- **S1:** within the incident SLA; DPO/safeguarding informed.
- **S2/S3:** engineering on-call; site continues if safe.

## 9. Post-incident

- **Blameless review** for every S0–S2: timeline, root cause, which gate/control should have caught it,
  and the fix.
- **Register update:** feed the learning into the risk register + the next production/QA cycle.
- **Hard rule:** any **open S0/S1** ⇒ **NO-GO** to continue the pilot rung until resolved — safety and
  child wellbeing outrank schedule, always.
