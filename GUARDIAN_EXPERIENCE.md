# Guardian Experience

Status: **Phase 9 — Pilot Operations & Guardian Experience.** Designs the guardian (parent/guardian)
experience for the first supervised pilot as a **composition of surfaces that already exist** — the
Student Platform's derived read models, the Learning analytics, the AI Teacher plan, and the offline
sync visibility. **No architecture is redesigned; no new child-data table.** Companion to
[MENTOR_WORKFLOWS.md](MENTOR_WORKFLOWS.md), [END_TO_END_VALIDATION.md](END_TO_END_VALIDATION.md),
[PILOT_SUCCESS_METRICS.md](PILOT_SUCCESS_METRICS.md).

> **Governance gate (honest).** A guardian **reading their own child's data** requires a guardian
> identity + guardian↔child linkage + a `guardian` authorization grant. Guardian provisioning is
> **blocked by the Phase-1.5 governance gate (M-Gov)** (child identity, consent). This document
> therefore designs the guardian *experience over data surfaces that already exist* — every panel maps
> to an existing derived read model. When M-Gov closes (WS1/WS3 of the Master Plan), the guardian role
> is a **thin authorization + linkage layer** over these same reads — not new data, not a redesign.
> For Pilot 1 (on-site, supervised), guardian reporting can also be delivered by the **mentor**
> (a privileged reader) as a compensating path.

---

## 0. Reuse map — every guardian panel is an existing surface

| Guardian panel | Existing surface reused |
| --- | --- |
| Dashboard (today) | `GET /v1/learning/students/{ref}/today` (next action + mastery summary + due reviews) |
| Progress timeline | `GET …/history` (sessions + lessons) + `GET …/progress` (mastery summary) |
| Weekly learning summary | derived rollup over `history` + append-only `AssessmentEvidence` (no new table) |
| Attendance & activity | `history.sessions` (session_id, at) → attendance; evidence → activity |
| Learning recommendations | `GET …/recommendations` + `GET …/ai-teacher/plan` (weak topics, revision) |
| Offline sync visibility | client sync diagnostics (6.2B/6.2C-1) + queue depth + `last_sync_at` |
| Notifications | `GET …/notifications` (+ device-local read-state) |

All are **read-only, derived, pseudonymous** (`student_ref` only — no child PII), authenticated,
authorized, and IDOR-guarded (a guardian sees only their linked child; a mentor may read any).

---

## 1. Guardian dashboard

- **Purpose:** a calm, at-a-glance view of how the child is doing today.
- **Content (from `today`):** the next recommended action + objective, a mastery summary
  (mastered / in-progress / total), and the count of due reviews — plus the offline status and any
  unread notifications.
- **Data:** `today` aggregate + `notifications.unread` + sync status. No PII; Urdu-first.
- **Message tone:** encouraging, non-comparative; effort over cleverness (the platform's guardian
  guidance ethos, [PARENT_GUIDE.md](PARENT_GUIDE.md)).

## 2. Student progress timeline

- **Purpose:** how the child has progressed over time.
- **Content (from `history` + `progress`):** a chronological list of sessions (date, objectives
  practised, attempts, correct) and per-objective mastery movement (mastery summary, achievements).
- **Data:** `history.sessions`, `history.lessons`, `progress.mastery`, `achievements`. Derived from
  the append-only evidence + outbox — the same source of truth mentors see.

## 3. Weekly learning summary

- **Purpose:** a once-a-week digest a guardian can absorb in a minute.
- **Content:** objectives worked this week, new masteries, time-on-task (session count), the current
  focus (next action), and one encouragement line.
- **Data:** a **derived weekly rollup** over `history` + `AssessmentEvidence` for the last 7 days —
  computed from existing data, **no new child-data table** (a derived read model, like `today`).
- **Delivery:** shown in-app; optionally summarized by the mentor for guardians without app access
  (pilot).

## 4. Attendance & activity view

- **Purpose:** did the child show up + engage?
- **Content:** attendance (days with ≥ 1 session, from `history.sessions[].at`) and activity (attempts,
  lessons opened) per day.
- **Data:** `history.sessions` + local progress events (`item_attempted`, `lesson_opened` — 6.2A).
  Attendance is derived from session records; no separate attendance table.

## 5. Learning recommendations

- **Purpose:** what the child should focus on + how a guardian can help.
- **Content:** the top recommendations (`recommendations`) and the AI Teacher's weak topics + revision
  plan (`ai-teacher/plan`), each with a plain-language reason, plus the per-subject "2-minute help at
  home" tips from the curriculum guides.
- **Data:** `recommendations` + `ai-teacher/plan.weak_topics/revision_due` (all derived + explainable;
  the AI Teacher is templated — no generative content).

## 6. Offline sync visibility

- **Purpose:** reassure the guardian that offline work is safe + will sync.
- **Content:** current connectivity, pending-to-sync count, last successful sync time, and a plain
  message ("Your child's answers are saved and will update when back online").
- **Data:** the client sync diagnostics + queue depth (6.2B) — local, C1-only counters, **no student
  PII**. Mirrors the `OfflineBadge` honest-status ethos.

## 7. Notifications

- **Purpose:** timely, gentle nudges (a mastery earned, a review due, "come back tomorrow").
- **Content:** the derived notifications feed (`notifications`), with device-local read-state (the
  server keeps **no** read-state table by design, `notifications/{id}:read` is a server no-op).
- **Rules:** rate-limited, purposeful, never alarming or comparative; no PII; opt-out honored.

---

## 8. Privacy, safety, and consent (guardian-facing)

- **No child PII** in any panel — pseudonymous `student_ref` only; guardians see learning data (C2),
  never raw identity.
- **Consent + rights:** the guardian is told plainly what is collected (only what's needed), gives
  **informed consent** before the child takes part (M-Gov), and can ask questions or **opt out** via
  the mentor/coordinator; a de-enrolment purges the child's on-device data at next connect (6.2C-1).
- **A human is always reachable:** wellbeing/safety concerns route to the on-site safeguarding lead
  (Pilot 1) — the guardian is told how.
- **Residency + retention:** guardian-visible data lives in-region and follows the retention schedule
  (governance/config, WS1).

---

## 9. Phase C — the guardian portal as built (2026-10-22)

The guardian identity, consent, and child-linkage layer that §0–§8 anticipated now exists
(`/v1/identity`, FD-14), and the web portal is the screen over it. A guardian can run their family
from it without an engineer. Every guardian screen reads its text from the typed i18n catalog
(`apps/web/lib/i18n/messages`, `guardian` and `auth` namespaces, Urdu and English), so an English
interface is English and left-to-right, and an Urdu interface is Urdu and right-to-left. Curriculum
codes and any server-generated sentence keep their own `lang`/`dir` (`contentAttrs`).

### 9.1 Screens

| Route | What a guardian does there |
| --- | --- |
| `/join` | Create the guardian account (in the language they are reading) |
| `/guardian/signin` | Sign in |
| `/guardian` | See every child: can they sign in, a progress summary, what needs attention |
| `/guardian/family` | Family code; add a child; per child: permissions, permission history, PIN reset / unlock; the activity record |
| `/guardian/children/{ref}` | One child's progress: this week, overview, attention, recommendations, the AI Teacher's next step, learning days, ideas, sessions, checks, achievements, phone sync |
| `/signin` | The child's sign-in (family code, tap name, PIN) |

### 9.2 Capability map — every `/v1/identity` and `/v1/guardian` operation

| Operation | Reached from |
| --- | --- |
| `registerGuardian` | `/join` |
| `signInGuardian` | `/guardian/signin` |
| `getFamilyRoster`, `signInLearner` | `/signin` |
| `refreshSession` | Automatic: every guardian call runs inside `withSession` |
| `signOut` | "Sign out" in the guardian header |
| `getConsentPolicy` | `/guardian/family` renders the consent form from it (built-in fallback if unreachable) |
| `getGuardianIdentityProfile` | `/guardian` (names, consent status) and `/guardian/family` |
| `listLearners` | `/guardian/family`, refreshing the list after each change |
| `enrolLearner` | `/guardian/family` → "Add a child" (name, PIN, class, the child's app language) |
| `resetLearnerPin` | `/guardian/family` → PIN (also unlocks a locked child) |
| `grantConsent` | `/guardian/family` → Permissions, per scope |
| `withdrawConsent` | `/guardian/family` → untick a scope (that scope only) or "Stop all permissions" (everything); both confirmed first |
| `getConsentState` | `/guardian/family` → "Permission history" |
| `getIdentityAuditTrail` | `/guardian/family` → Activity record, with "show older" (`limit` up to 500) |
| `getGuardianDashboard` | `/guardian` |
| `getGuardianChild` | `/guardian/children/{ref}` |
| `getGuardianProfile` (`/v1/guardian/me`) | Not called: its fields (display name, linked refs) are a subset of `getGuardianIdentityProfile` + `getGuardianDashboard`, which the screens already read |

### 9.3 The consent form

- Rendered from `GET /v1/identity/policy`: one `<fieldset>`/`<legend>` for "needed to learn"
  (`learning_data`, shown ticked and disabled) and one for "your choice" (the optional scopes, unticked
  for a child without live consent).
- Each scope has a plain-language title, a one- or two-sentence explanation of what saying yes allows,
  and a Listen button, as the student screens have.
- The attestation sentence is shown above the button in the guardian's language and is stored
  verbatim with the record.
- Grants are additive on the server, so unticking a scope is sent as a withdrawal of that scope (the
  previous form only ever sent grants, so unticking did nothing). `lib/guardian/consent.ts`
  `planConsentChange` computes the calls.
- Any withdrawal stops at a confirmation that says what will happen. "Stop all permissions" says the
  child will be signed out on every phone now, cannot sign in until permission is given again, and
  that nothing is deleted. Focus moves to the confirmation; Escape or "No, go back" returns it.
- Errors are `role="alert"`; saved notices are polite status messages.
- A policy that requires a scope this app cannot explain disables the grant: agreeing to something
  the screen cannot describe is not consent.

### 9.4 Honest states

`lib/guardian/dashboard.ts`, unit-tested: a newly registered guardian sees "add your first child"; a
child with no answered question shows "no progress yet" (never zeros and a 0% accuracy); if the
learning service is down the dashboard still shows names and permissions; if both services are down
it says so (offline, signed out, or an error, each with the right next step). A child's detail answers
404 ("no learning data yet") with "no progress yet", not an error.

### 9.5 Not surfaced, and the backend changes that would surface them

| Capability | Why not | Backend change needed |
| --- | --- | --- |
| Rename a child's display name | No operation in `identity.openapi.yaml` | `PATCH /v1/identity/learners/{ref}` with `displayName` (unique within the family, audited) |
| Disable / pause a child's account | No guardian-facing operation; `learner.suspended` exists only as an audit action | `POST /v1/identity/learners/{ref}:suspend` and `:reinstate`, owner-only. Today "Stop all permissions" is the guardian's equivalent: it blocks sign-in and ends sessions |
| Optional scopes taking effect | Only `learning_data` is enforced (the sign-in gate). `ai_teaching`, `voice_audio`, and `progress_sharing` are recorded but no feature checks them, so the copy describes what each covers and does not promise behaviour | Enforce each optional scope where its feature runs |
| Localised validation messages | Every identity 422 is `VALIDATION_FAILED` with an English `detail`; the client matches known sentences to catalog keys (`lib/guardian/errors.ts`) | A stable per-error `code` (e.g. `PIN_TOO_EASY`, `DUPLICATE_NAME`) |
| Objective titles in progress text | Achievements and notifications carry English sentences built from objective codes | Machine-readable kinds and objective titles in the guardian read model |
| Notification preferences, data export / deletion | Not implemented in the backend (§18 of the master scope) | New endpoints |

## 10. What lands with M-Gov (not built here)

The guardian **role, identity, and child-linkage** (a thin authorization + linkage layer over the same
reads) land with the child-safe auth work (WS3) once M-Gov closes. The **data surfaces already exist**;
Phase 9 designs the experience over them and validates the end-to-end journey
([END_TO_END_VALIDATION.md](END_TO_END_VALIDATION.md)). Nothing here requires new architecture.
