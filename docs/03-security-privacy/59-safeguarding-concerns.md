# 59 · Safeguarding Concerns: Reporting and Triage (implementation)

| | |
|---|---|
| **Document ID** | 59 |
| **Owner** | Safeguarding lead (policy, staffing, sign-off) · Engineering (implementation) |
| **Status** | **Software only.** Built and tested; **not approved, not staffed, not signed off.** Sign-off is M-Safe; the referral policy is FD-04; the SLA and staffing are FD-06 |
| **Last updated** | 2026-10-23 |
| **Related** | [15 Child Safety](./15-child-safety-framework.md) §5, §10 · [52 Crisis Protocol](./52-safeguarding-crisis-protocol.md) · [58 Export and erasure](./58-learner-export-and-erasure.md) · [INCIDENT_RESPONSE.md](../../INCIDENT_RESPONSE.md) · [MONITORING_RUNBOOK.md](../../MONITORING_RUNBOOK.md) · [FOUNDER_DECISIONS.md](../../FOUNDER_DECISIONS.md) FD-04, FD-06 · contract `packages/contracts/safeguarding.openapi.yaml` |

## Purpose

This records what the `contexts/safeguarding` bounded context does: a child or a guardian can raise
a safeguarding concern, and a safeguarding lead can triage it. It says plainly what is **not** in
place. Nothing here means the workflow is approved, staffed, or safe to rely on with real children.
That decision belongs to the safeguarding lead and the owner (M-Safe), not to engineering.

## 1. What is built

### 1.1 Raising a concern

- **A child**, from any student screen, taps **"Tell a grown-up"** in the header. A picture and
  words show on every screen that uses the student app shell. The lesson player's own "Help" button
  means "stuck on a question". Its card now also links to "Tell a grown-up" for anything wrong or
  upsetting.
- The child taps one of five pictures, then **Send**. Typing is optional and sits behind its own
  button (up to 500 characters).
- The categories are a fixed list, with the tiers from [52 §2](./52-safeguarding-crisis-protocol.md):

  | Category | Child wording | Tier |
  | --- | --- | --- |
  | `felt_unsafe` | Someone made me feel unsafe | T1 |
  | `very_sad` | I feel very sad or scared | T1 |
  | `bullying` | Someone is bullying me | T2 |
  | `upsetting_lesson` | Something in a lesson upset me | T2 |
  | `other` | Something else | T3 |

  No category is **T0**. T0 means imminent harm and needs a live human within minutes, 24/7. That is
  not staffed, so the software does not pretend otherwise. Every confirmation tells the child to tell
  a trusted grown-up near them straight away if they are in danger now.
- **What the child is told:** a trained grown-up at Taleem will read it, and what they sent is not
  shown on this device again. **No response time is promised** (FD-06).
- **A guardian** raises a concern from the portal (`/guardian/concerns`) about one of their own
  children: the category, optional details, and the child.
- **Stored:** pseudonymous refs only (`subject_ref`, `raised_by_ref`). No name is copied from
  identity. The context is a route-like screen token (`student/today`) and, inside a lesson, the
  lesson id. A path that carries anything else (a query string, a ref) is dropped, not stored.
- **Offline: online only, and the child is told so.** The offline sync queue is **deliberately not
  used**. It lives in the device's storage, and a family device is often shared, so a queued report
  could be read by the person it is about ([51 Threat Model](./51-threat-model.md), household as
  adversary). Offline, the child sees that nothing was sent and nothing was saved, and is told to
  find a trusted grown-up or try again when connected. Doc 15 §3 describes an offline crisis
  affordance that queues and fires on reconnect. Whether that trade-off is acceptable is a question
  for M-Safe.
- **The channel stays open:**
  - Raising is **not** behind the learner consent gate, so it works after a guardian withdraws
    consent.
  - Raising is **not** on the kill switch's child-facing list, so it works while learning is halted.
  - Both are pinned by tests.
- **Rate limit:** 20 concerns per hour per subject (shared across instances on PostgreSQL). It is
  generous so a flood cannot bury real reports. A child who hits it is told to find a grown-up.

### 1.2 Triage

- **Role:** `safeguarding_lead`. It is an operator-provisioned staff account, exactly like the
  Curriculum Studio roles: `POST /v1/identity/staff` by `system`, one role per account, and a DB
  CHECK on the role. It signs in with the same staff sign-in. The live staff gate refuses a
  suspended lead's token on the next request. The role holds **no** curriculum, learning, school,
  privacy or identity permission. It reads safeguarding concerns and nothing else.
- **Console:** `/safeguarding` uses staff sign-in, like `/studio`, but keeps its own tab session. It
  shows:
  - **The queue:** open concerns by priority, then age.
  - **The SLA banner.**
  - **A concern's page:** the raiser's own words, where the concern came from, notes, and the audit
    trail. Opening a concern is itself audited.
  - **The actions the status allows:** acknowledge, add a note, mark "external referral needed"
    (a reason is required), and resolve with an outcome.
- **Outcomes:** `no_further_action`, `support_given`, `duplicate`, and `referred_externally`. The
  last is accepted only after a recorded escalation, and it records that a *person* made a referral
  outside Taleem.
- **Escalation contacts nobody.** It records a decision. No referral channel exists in software
  (FD-04).
- **Audit:** every action (`concern.raised`, `.viewed`, `.acknowledged`, `.note_added`,
  `.escalated`, `.resolved`) is written in the same transaction as the change, with the actor's
  token subject and role. Audit detail carries statuses and enum values only, never free text. Logs
  and metrics carry tier and raiser role only.
- **Concurrency:** two leads acting at once get a retryable `409`, never a silent overwrite.

### 1.3 SLA: unset by default

`TALEEM_SAFEGUARDING_ACK_SLA_SECONDS` sets the "acknowledge within" threshold per tier, for example
`{"T1": 1800}`. **It defaults to unset, and no number is invented.** The values in doc 52 §2 are
planning assumptions awaiting clinical sign-off.

- **While any tier is unset:**
  - The console shows **"SLA not set — owner decision FD-06"**.
  - For that tier, a concern's overdue state is shown as *unknown*, not as "fine".
  - The `TaleemSafeguardingSlaNotSet` warning fires.
- **Once a threshold is set:** an unacknowledged concern past it is flagged overdue, and
  `TaleemSafeguardingConcernOverdue` fires.

### 1.4 Alerts

The `/metrics` gauges are read from the database at scrape time, so every instance agrees:

- `taleem_safeguarding_concerns_unacknowledged{priority}`
- `taleem_safeguarding_concerns_overdue{priority}`
- `taleem_safeguarding_sla_configured`

There is also a `taleem_safeguarding_concerns_raised_total{priority,raised_by}` counter and a
gauge-read error counter. The rules in `infra/monitoring/alerts.yml` (group `taleem-safeguarding`,
checked by promtool) carry `team: safeguarding`. **No receiver routes that label: the destination is
unconfigured until M-Safe.** An alert that fires today reaches nobody.

## 2. Visibility rules

These are enforced server-side against the token subject. Each one is pinned by a test in
`services/core-api/tests/test_safeguarding_api.py`, over SQLite and PostgreSQL.

| Who | Can raise | Can see |
| --- | --- | --- |
| Child (`student`) | About themselves only | A receipt with no id. There is no list, no history, and no way to see it again |
| Guardian | About their own learner only (another family's learner is a `404`) | **Only the concerns they raised themselves**, with a coarse status: received, being looked at, or closed. Never notes, escalation or outcome |
| `safeguarding_lead` | — | The queue, free text, notes, audit |
| Teacher, mentor, operator (`system`), every Studio role | Nothing (`403`) | Nothing (`403`) |

**A concern a child raised is never visible to any guardian.** This includes a guardian the concern
is about. The rule does not depend on knowing who the concern is about. The guardian list matches on
who *raised* the concern, never on which learner it concerns, so a child's report about their own
household cannot reach that household. Specifically:

- The guardian list leaves it out.
- The guardian portal never mentions it.
- The **privacy export** leaves it out. The export's "withheld" notice is the same text whether or
  not the child raised anything, so the export does not reveal that a child spoke up.

The lead's view of a concern a child raised carries a **household caution**. It says the guardian
has not been told and cannot see the concern, and that the guardian must not be contacted until
they are ruled out ([52 §4](./52-safeguarding-crisis-protocol.md)).

## 3. Privacy: export and erasure

The `contexts/privacy` completeness gate covers all four tables (`safeguarding.concern`,
`.concern_note`, `.concern_evidence`, `.concern_audit`) through `adapters/safeguarding_data.py`.

**Evidence snapshots** (`safeguarding.concern_evidence`, migration `0018_concern_evidence`): a
concern raised from a homework submission (the disclosure screen, or a teacher's `:concern` from a
marking row) stores, in the same transaction, the flagged text, its attempt, `submitted_at`,
`item_ref`, `objective_code`, the SHA-256 of the text and `created_at` — one row per concern. A
resubmission changes the submission, never the snapshot, so the lead's context read always shows
what was flagged (`flagged`), plus the latest text only when it differs (`current`). On PostgreSQL
a trigger refuses UPDATE, DELETE and TRUNCATE except inside the privacy erasure's transaction
(`taleem.privacy_erasure`). Only `safeguarding_lead` reads it, on demand and audited; no teacher
queue, guardian or learner view, report, export, log line or audit row carries its text (or hash).
Concerns raised before 0018 have no snapshot; the API and console say so rather than presenting the
latest text as the flagged one.

- **Export** (requested by the guardian): it contains the concerns that guardian raised about the
  learner. Concerns the learner, a teacher or the screen raised, and every triage note, evidence
  snapshot and audit row, are **withheld** under
  a safeguarding exemption, **PENDING M-Gov**. How a child might get their own safeguarding records
  is an open question for M-Gov.
- **Erasure** (requested by the guardian) follows an **explicit retained-set entry**,
  `safeguarding_concerns`, set by `TALEEM_PRIVACY_SAFEGUARDING_CONCERNS`. It is marked **PENDING
  M-Gov approval and FD-04**, and the erasure receipt states it:
  - `retain_pseudonymised` (**default**): every row is kept. Every occurrence of the learner's ref is
    replaced by the one-way tombstone ref: the subject, the raiser, an audit actor, and the ref as a
    word inside free text or a note. The record survives; the ref does not. The reason for this
    default: the person requesting erasure is the guardian, and a child's concern may be about that
    guardian. Deleting the child's report at the guardian's request could destroy the record of a
    disclosure.
    Evidence snapshots are kept with their concern (they carry no learner ref; a ref written inside
    the flagged text is replaced and its SHA-256 recomputed for the stored text). This mirrors the
    concern's own free text, which is kept too; it is the same PENDING M-Gov decision.
  - `erase`: the concerns, their evidence snapshots, their notes and their audit rows are deleted.

  Either way the verification sweep finds no row naming the learner. The data is never kept
  silently.

## 4. What is NOT done, and who decides

| Item | Status | Owner |
| --- | --- | --- |
| Approval of this workflow, and a recorded drill (a concern reaching a human within the SLA) | ⚫ Not done | Safeguarding lead (M-Safe) |
| A staffed lead rota, including out-of-hours and T0/T1 coverage | ⚫ Not staffed | Owner + safeguarding lead (FD-06) |
| SLA values per tier | ⚫ Unset by design | Owner + clinician (FD-06) |
| External referral channels, mandatory-reporting obligations, dual-control authorisation, the do-no-harm test | ⚫ None exist; escalation contacts nobody | Counsel + safeguarding (FD-04) |
| Alert destination for `team: safeguarding` | ⚫ Unconfigured | Safeguarding lead (M-Safe), MONITORING_RUNBOOK §6 |
| Whether safeguarding records outlive a guardian-requested erasure (the default keeps them pseudonymised), and a retention period for them | ⚫ PENDING | DPO + counsel (M-Gov), FD-04 |
| Whether a guardian's export may withhold the child's concerns, and how a child obtains their own records | ⚫ PENDING | DPO + counsel (M-Gov) |
| Lawful basis for recording a concern from a child whose consent was withdrawn (the channel stays open by design) | ⚫ PENDING | DPO + counsel (M-Gov) |
| Offline reporting (doc 15 §3's offline crisis affordance) against the shared-device risk | ⚫ Online only for now | Safeguarding lead (M-Safe) |
| Clinician-reviewed child wording, and in-language crisis resources (no helpline number is shown, because none is approved) | ⚫ Not reviewed | Safeguarding lead + clinician |
| Doc 15 §5's C4 zone controls: field encryption, hardware-key and dual-control access for leads | ⚫ Not built | Engineering, after M-Safe sets the requirement |
| Automated distress detection feeding this queue | ⚫ Not built | Engineering, after M-Gov (FD-03) |

## Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-25 | Immutable evidence snapshots for concerns raised from a submission (`safeguarding.concern_evidence`, 0018); context read returns `flagged` + `current`; export withholds them; erasure follows the safeguarding retained set. | Engineering |
| 2026-10-23 | Initial implementation record: raise (child, guardian), triage console, visibility rules, audit, SLA unset by default, alerts, privacy coverage. Workflow not approved or staffed. | Engineering |
