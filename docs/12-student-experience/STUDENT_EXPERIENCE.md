# Student Experience — Design (Phase 5)

Status: **Design only** — no frontend implementation. Governance: the Student Portal is child-facing;
implementation is blocked by the Phase-1.5 governance gate (lawful basis, DPIA, safeguarding SLA,
child-identity decisions). This document designs *what* the experience is; it does not build it.

Companion documents: [STUDENT_PORTAL_ARCHITECTURE.md](STUDENT_PORTAL_ARCHITECTURE.md),
[STUDENT_UI_FLOW.md](STUDENT_UI_FLOW.md), [STUDENT_API_REQUIREMENTS.md](STUDENT_API_REQUIREMENTS.md),
[STUDENT_COMPONENT_CATALOG.md](STUDENT_COMPONENT_CATALOG.md).

Grounded in the built platform: the Learning Intelligence API (`/v1/learning/*` — sessions, knowledge,
progress), the decision engine (`diagnose · teach · continue · review · remediate · advance · revise ·
escalate · rest · complete`), the AI Teaching Runtime (authored, in-scope utterances), the offline
sync engine (`/v1/sync/batch`), and the design tokens in `apps/web`. This is the learner-facing
surface of everything Phases 3–4.2 built.

---

## 1. Who this is for (and what that forces)

**Primary learner:** a child (KG–Grade 10) in Pakistan who cannot access traditional schooling. The
design must assume the *hardest* case, because that is the mission:

- **Device:** low-end Android (Android Go, ~1–2 GB RAM, small screen), sometimes shared.
- **Network:** 3G or intermittent/offline; data is expensive.
- **Language & literacy:** **Urdu-first**, RTL; the child may be a *weak reader* → **audio-first**,
  icon+text, minimal on-screen text.
- **Support:** variable adult help; the UI must be usable by a child alone.
- **Age range is wide:** a KG child and a Grade-10 child need different densities, vocabularies, and
  autonomy. The design scales complexity by grade band (see §3 age-adaptation).

These are not preferences; they are **hard constraints** that decide every screen. A screen that
needs fluent reading, a fast connection, or a big screen has failed the mission before it ships.

**Design north stars (acceptance-level, apply to every screen):**

- **Audio-first, Urdu-first, RTL** — every instruction, question, and feedback has recorded Urdu
  audio (a `ReadAloud` affordance); text is short and supportive, never a wall.
- **One clear next action** — the child always sees the single most important thing to do now
  (driven by the decision engine), not a menu to reason about.
- **Works offline** — today's lessons and due revisions are usable with no connection; progress syncs
  later. Nothing critical requires being online.
- **WCAG 2.2 AA** — keyboard/switch operable, 44px targets, sufficient contrast, `prefers-reduced-
  motion`/`prefers-contrast` honored, screen-reader labelled, visible focus.
- **Child-safe by construction** — no ads, no open chat, no external links, no data collection beyond
  the pseudonymous learning model; the AI only ever teaches approved content; a wellbeing/help path is
  always reachable.
- **Encouraging, never punitive** — struggle is normal; the UI celebrates effort and progress, never
  shames a wrong answer.

---

## 2. The complete learning journey (login → completion)

The spine of the experience, end to end:

```text
Open app ─▶ Sign in (child-safe) ─▶ Dashboard "Today"
   │                                     │  one tap: "Start today's learning"
   │                                     ▼
   │                          Learning Session (Lesson Player)
   │        decision engine picks: diagnose / teach / review / remediate
   │                                     │
   │   ┌──────────── loop per objective ─┴───────────────┐
   │   │  AI teacher presents (audio+visual)             │
   │   │  asks a question ─▶ child answers               │
   │   │  correct ─▶ affirm & advance                    │
   │   │  wrong   ─▶ graduated hint ─▶ retry             │
   │   │  misconception ─▶ authored correction (remediate)│
   │   │  stuck / distress ─▶ escalate to mentor         │
   │   └─────────────────────────────────────────────────┘
   │                                     │  mastery reached / budget hit / Rest
   │                                     ▼
   │                          Session Complete (celebrate + what's next)
   │                                     │  revision scheduled automatically
   │                                     ▼
   └────────────────────────────▶ back to Dashboard (progress updated, sync queued)
```

Everything else (Timetable, Subjects, Homework, Assessments, Progress, Profile, Achievements,
Notifications, Revision queue) hangs off the Dashboard as **secondary navigation** — the child never
*needs* them to make progress, because the engine already knows the next best action.

---

## 3. Age adaptation (one product, three densities)

The same information architecture with grade-band presets applied by a `gradeBand` setting on the
learner profile:

| Band | Grades | Density / language | Autonomy |
| --- | --- | --- | --- |
| Early | KG–G2 | Big icons, near-zero text, audio narration mandatory, playful | Fully guided; one action at a time |
| Middle | G3–G7 | Icon+short text, audio available, light gamification | Some browsing (subjects, homework) |
| Senior | G8–G10 | Denser text ok, mastery map + goals foregrounded, study tools | Self-directed; timetable, assessments |

Age adaptation changes **presentation and vocabulary**, never the underlying model or the safety
rules. It is a theming/preset concern (design system), not a fork of the app.

---

## 4. The 12 design areas — where each is specified

| Area | Primarily specified in |
| --- | --- |
| 1. Student Dashboard | §6.2 (this doc) + components + APIs |
| 2. Learning Session UI | §6.3 (this doc) + UI_FLOW + components |
| 3. Navigation | §5 (this doc) + UI_FLOW |
| 4. Student Profile | §6.9 (this doc) |
| 5. Offline experience | §7 (this doc) + ARCHITECTURE |
| 6. Accessibility | §8 (this doc) + every screen's a11y block |
| 7. Mobile-first UX | §9 (this doc) + ARCHITECTURE |
| 8. Design system requirements | §10 (this doc) + COMPONENT_CATALOG |
| 9. API requirements | STUDENT_API_REQUIREMENTS |
| 10. State management | ARCHITECTURE §state |
| 11. Error handling | §11 (this doc) + ARCHITECTURE |
| 12. Security considerations | §12 (this doc) + ARCHITECTURE |

---

## 5. Navigation model

- **Primary surface = "Today" (Dashboard).** Bottom navigation bar (thumb-reachable, RTL-mirrored)
  with at most **5** destinations by band: `Today · Learn (Subjects) · Homework · Progress · Profile`.
  Early band collapses to `Today · Progress · Profile` (fewer choices).
- **The one-tap action** ("Start today's learning") is always the largest, highest-contrast element on
  Today — it launches the session the engine chose.
- **Timetable, Assessments, Achievements, Notifications, Revision queue** are reachable from Today
  (cards/links) and Profile, not from the bottom bar (kept to 5 max for clarity).
- **Back is always safe** — leaving a session pauses it (resumable), never loses progress.
- Navigation is **keyboard/switch operable** and screen-reader ordered; the current destination is
  programmatically indicated (`aria-current`).

The full screen map + navigation graph is in [STUDENT_UI_FLOW.md](STUDENT_UI_FLOW.md).

---

## 6. Screen specifications

Every screen below gives **Purpose · User journey · Components · Data required · APIs · Accessibility ·
Acceptance criteria**. Component names map to [STUDENT_COMPONENT_CATALOG.md](STUDENT_COMPONENT_CATALOG.md);
APIs map to [STUDENT_API_REQUIREMENTS.md](STUDENT_API_REQUIREMENTS.md) (endpoint IDs in `code`).

### 6.1 Sign-in (child-safe)

- **Purpose:** let a child securely resume *their* learning on a device, with the least friction and
  no PII entry by the child.
- **User journey:** open app → see their name/avatar (if device-remembered) → enter a simple
  credential (PIN or picture-password) → land on Today. First-time setup is guardian/mentor-assisted
  (out of the child's flow) and is governance-gated.
- **Components:** `AppShell`, `LearnerAvatarPicker`, `PinPad` / `PicturePassword`, `ReadAloud`,
  `LanguageToggle`, `OfflineBadge`, `PrimaryButton`, `ErrorBanner`.
- **Data required:** device-linked learner handle (pseudonymous `student_ref`), display name/avatar,
  grade band, locale. **No** email/phone/DOB from the child.
- **APIs:** `auth.login` (exchange device+credential → short-lived session token bound to
  `student_ref`, role `student`); `auth.refresh`. (Identity provisioning is a mentor/guardian flow,
  not here.)
- **Accessibility:** PIN pad keys ≥44px, labelled, keyboard/switch operable; audio prompt for each
  step; picture-password as a non-text alternative for weak readers; visible focus; errors announced
  via `aria-live`.
- **Acceptance criteria:**
  - A remembered learner can sign in in ≤2 taps + credential, fully offline if a valid cached session
    exists.
  - The child never types PII; only a PIN/picture credential.
  - Wrong credential shows a calm, audio-supported retry (no lockout shaming); repeated failures route
    to a guardian/mentor recovery path, not a dead end.
  - The issued token is scoped to this learner (`sub == student_ref`, role `student`) — the API's IDOR
    guard rejects any cross-learner access.

### 6.2 Dashboard — "Today"

- **Purpose:** answer one question instantly — *"what should I do now?"* — and show encouraging
  progress. It is the home base and the launcher.
- **User journey:** land after sign-in → hear/see a short greeting → see the big **Start today's
  learning** action (the engine's chosen next step) → optionally glance at progress, revision due,
  achievements, attendance, notifications → tap Start.
- **Components:** `AppShell`, `GreetingHeader` (audio), `PrimaryActionCard` ("Start today's learning"
  with objective title + estimated time), `TodayLessonsList`, `RevisionDueCard` (count + due-now),
  `ProgressRing` (subject/overall mastery), `StreakBadge` / `AchievementsStrip`, `AttendanceStrip`,
  `NotificationBell`, `BottomNav`, `OfflineBadge`, `SyncStatus`.
- **Data required:** today's plan (next decision + queued objectives), due-revision count, mastery
  summary, streak/achievements, attendance summary, unread notifications, offline/sync state.
- **APIs:** `dashboard.today` (aggregated: next action, today's objectives, revision-due count,
  mastery summary, attendance, achievements, notifications badge — one call for a slow link);
  falls back to composing `learning.progress` + `learning.reviews` + `learning.knowledge` if the
  aggregate is unavailable. `sync.status` (local).
- **Accessibility:** the primary action is the first focusable, largest, highest-contrast element and
  is announced first; all cards have text + audio; icons carry `aria-label`; the ring shows a text
  percentage, not color alone; `prefers-reduced-motion` disables celebratory animation.
- **Acceptance criteria:**
  - The single most important next action is visually and programmatically first, and launches the
    correct session type (matches the engine's `:next` decision).
  - Renders fully from cache when offline (last-synced plan), with an honest "offline — showing your
    saved plan" indicator.
  - No numeric grade/rank shaming; progress is framed as growth ("you mastered 3 new ideas").
  - Loads to interactive in ≤3 s on a low-end device / 3G (measured), skeletons for slow data.

### 6.3 Learning Session (Lesson Player + AI teacher)

- **Purpose:** deliver the actual tutoring — the AI teacher presents, questions, hints, corrects, and
  the child learns to mastery. This is the heart of the product.
- **User journey:** tap Start → session opens → the engine decides (`teach`/`review`/`remediate`/
  `diagnose`) → the AI teacher **presents** the concept (audio + visual, one step at a time) → **asks**
  a question → child **answers** (tap/voice/choose) → **correct**: affirm + advance; **wrong**: a
  **graduated hint**, then retry; **misconception**: an authored **correction**; repeat per objective
  → on mastery or effort-budget, the session **completes**.
- **Components:** `SessionShell` (minimal chrome, big content area), `TeacherTurn` (renders an
  utterance: present/ask/hint/feedback/remediate, always with `ReadAloud`), `ConceptVisual`
  (SVG/diagram/animation with alt text), `WorkedExampleStepper`, `QuestionCard` (MCQ / tap / order /
  match / short), `AnswerInput` (multi-modal: tap options, voice-answer, draw, choose),
  `HintButton` with `HintLadder`, `FeedbackToast` (affirm/correct), `MisconceptionCorrectionCard`,
  `ProgressPips` (this session's steps), `PauseButton`, `HelpButton` (wellbeing/mentor), `OfflineBadge`.
- **Data required:** the session's decisions and, per objective, the published `LessonView`
  (approved teacher utterances, worked examples, practice items with authored hints, misconception
  corrections, media refs) — **fetched only from approved published content**; the running attempt
  outcomes and mastery.
- **APIs:** `learning.session.start` → `learning.session.next` (decision) → `learning.session.teach`
  (utterances + items) → `learning.session.answer` (scored → outcome, feedback, next decision) →
  `learning.session.hint` (next authored hint — **new**, see API doc) → `learning.session.end`. All
  answer/interaction events are queued offline and synced via `sync.batch`.
- **Accessibility:** audio-first (every teacher turn narratable and auto-narrated in Early band);
  questions answerable without reading via audio + icon options; hints and feedback announced via
  `aria-live`; large targets; no time pressure by default (timers optional, never punitive); reduced-
  motion respected; full keyboard/switch operation; captions for any spoken media.
- **Acceptance criteria:**
  - The AI teacher only ever renders **approved, in-scope content** (utterances/items from the
    published lesson) — the client cannot request or display ungrounded generation.
  - A wrong answer yields the **next authored hint** (never the answer first), and never a shaming
    message; hints are capped, after which the child is offered re-explanation or help.
  - A confirmed misconception surfaces its **authored correction**, then a targeted retry.
  - A distress/help signal (explicit `HelpButton` or detected) **immediately** pauses teaching and
    routes to the safeguarding/mentor path — never overridden by "finish the lesson."
  - The full teach→answer→hint→feedback loop works **offline** from a cached lesson package; attempts
    sync on reconnect with **no double-counting** (idempotent client event ids).
  - Leaving mid-session **pauses** (resumable at the same step); nothing is lost.

### 6.4 Session Complete

- **Purpose:** close the loop positively — celebrate what was learned, show mastery gained, and make
  the next step obvious (including that revision is scheduled).
- **User journey:** session ends → a calm celebration (respecting reduced-motion) → "You mastered X"
  summary → "Next: we'll review this in a few days" (revision scheduled automatically) → return to
  Today or continue if energy remains.
- **Components:** `SessionSummaryCard` (objectives touched, mastery delta, misconceptions cleared),
  `CelebrationBurst` (reduced-motion aware), `NextStepCard`, `RevisionScheduledNote`, `PrimaryButton`
  ("Back to Today" / "Keep going").
- **Data required:** the session result (from the final `:end` + the last `:answer` deltas), updated
  mastery, next-review note.
- **APIs:** `learning.session.end` (returns summary state); the mastery/next-review reflect the
  `ObjectiveMastered`/`ReviewScheduled` events already emitted server-side.
- **Accessibility:** celebration is optional/reduced-motion aware and never audio-only; summary is
  text + audio; the primary action is first-focus.
- **Acceptance criteria:**
  - Framing is growth-oriented ("you learned…"), never a score/pass-fail.
  - The next action is unambiguous and correct.
  - Renders offline; the summary derives from locally-recorded attempts if sync is pending.

### 6.5 Timetable

- **Purpose:** give structure — a lightweight daily/weekly plan so learning feels like "school," while
  the engine still drives the actual next step.
- **User journey:** open Timetable → see today's suggested blocks (subjects/objectives + est. time) →
  tap a block to start that session, or just use Today's one-tap.
- **Components:** `TimetableWeek`/`TimetableDay`, `TimetableBlock`, `SubjectChip`, `PrimaryButton`.
- **Data required:** the suggested schedule (derived from the plan + subject rotation + pace).
- **APIs:** `timetable.get` (**new** — derived from the learning plan; not free-form calendar entry).
- **Accessibility:** blocks labelled with subject + time; not color-only; keyboard navigable list;
  audio labels.
- **Acceptance criteria:** the timetable reflects the same plan the engine uses (no divergence);
  starting a block launches the correct session; usable offline from cache.

### 6.6 Subjects (Learn)

- **Purpose:** let middle/senior learners browse subjects and see where they are, without breaking the
  "guided" default.
- **User journey:** open Learn → grid of subjects (with mastery/progress) → pick a subject → see its
  chapters/topics and per-objective mastery → start an eligible objective (respecting prerequisites).
- **Components:** `SubjectGrid`, `SubjectCard` (progress), `ChapterList`, `TopicRow` (mastery state),
  `LockedIndicator` (prerequisite not met), `PrimaryButton`.
- **Data required:** subject roster for the learner's grade, per-objective mastery + eligibility
  (prerequisites), lesson availability.
- **APIs:** `learning.knowledge` (mastery per objective), `curriculum.hierarchy`/`curriculum.subject`
  (grades × subjects × chapters × topics — read model), `learning.eligibility` (**new** — which
  objectives are startable given prerequisites).
- **Accessibility:** locked items explain *why* (prerequisite) in text + audio, not just a lock icon;
  mastery shown as state text + shape, not color alone.
- **Acceptance criteria:** a learner cannot start an objective whose prerequisites are unmet (matches
  the engine's eligibility); browsing never overrides safety or the mastery gate.

### 6.7 Homework

- **Purpose:** surface assigned/auto-generated practice to do outside a taught session.
- **User journey:** open Homework → list of items (due, subject, est. time) → open one → complete it in
  the same player interaction model → it records as practice evidence.
- **Components:** `HomeworkList`, `HomeworkItemCard`, `QuestionCard` (reuses the player), `DueChip`.
- **Data required:** homework items (from the published lesson's `homework` set + engine assignment),
  due state, completion state.
- **APIs:** `homework.list` (**new**), `homework.submit` (routes through the same
  `learning.session.answer` evidence path).
- **Accessibility:** same player a11y; due status in text.
- **Acceptance criteria:** homework completion updates the Student Model (evidence recorded) and can be
  done offline; nothing is high-stakes/promotion-bearing (that path is mentor-mediated).

### 6.8 Assessments

- **Purpose:** show formative checks and (mentor-mediated) summative readiness — **without** turning
  learning into high-stakes testing.
- **User journey:** open Assessments → see upcoming/available checks → take a **formative** check in
  the player model → see supportive results. **Summative/promotion** assessments are clearly marked as
  mentor-supervised and are **not** auto-graded or auto-promoting.
- **Components:** `AssessmentList`, `AssessmentCard` (type: formative/summative badge), `QuestionCard`,
  `ResultSummaryCard` (formative, supportive), `MentorSupervisedNote` (summative).
- **Data required:** available assessments (formative from the engine; summative flagged
  `mentor_mediated`), results (formative only client-visible).
- **APIs:** `assessment.list` (**new**), formative attempts via `learning.session.answer`; summative
  is initiated only under a mentor-supervised, identity-assured flow (**out of the autonomous student
  surface** — a deliberate boundary, per doc 58).
- **Accessibility:** results framed supportively; no leaderboards; audio + text.
- **Acceptance criteria:** the student surface exposes **no** autonomous promotion/summative grading;
  formative results are non-punitive; summative is visibly mentor-gated.

### 6.9 Profile (stats · mastery map · goals · history)

- **Purpose:** the learner's own view of their journey — where they are strong, what they're working
  on, their goals, and what they've done. Motivating, honest, private.
- **User journey:** open Profile → see learning statistics (velocity, consistency, mastery breadth) →
  explore the **mastery map** (a visual of objectives by state across subjects) → view/set simple
  **goals** → scroll **learning history** (sessions, achievements).
- **Components:** `ProfileHeader` (avatar, name, grade band, streak), `StatTileRow` (velocity,
  consistency, mastery count — supportive framing), `MasteryMap` (grid/tree of objectives colored *and
  shaped/labelled* by state: not-started/in-progress/mastered/needs-review), `GoalList` + `GoalCard`
  (child-set, simple, e.g. "learn fractions"), `LearningHistoryTimeline`, `AchievementsGrid`.
- **Data required:** aggregated stats (velocity, consistency, completion), per-objective mastery
  (for the map), goals, session/achievement history.
- **APIs:** `learning.progress` (stats), `learning.knowledge` (mastery map), `profile.goals.get/set`
  (**new**), `learning.history` (**new** — de-identified session/achievement history for *self*).
- **Accessibility:** the mastery map is **not** color-only (state via label + shape + text summary);
  keyboard-navigable; an audio/text summary ("You've mastered 40 of 120 ideas in Math") complements
  the visual; stats avoid anxiety-inducing precision.
- **Acceptance criteria:** the learner sees only **their own** data (IDOR-guarded to `sub`); the
  mastery map matches `learning.knowledge`; goals are simple and non-binding (motivational, not
  gatekeeping); no comparison/ranking against other children.

### 6.10 Revision Queue

- **Purpose:** make spaced review a first-class, low-friction habit — the due reviews the engine
  scheduled.
- **User journey:** from Today's `RevisionDueCard` (or Profile) → open the queue → start a
  **retrieval-first** review session for due objectives.
- **Components:** `RevisionQueueList`, `RevisionItemCard` (objective, last-seen, why due), player
  interaction.
- **Data required:** due objectives (`needs_review`/`at_risk`, `next_review_at <= now`), prioritized.
- **APIs:** `learning.reviews` (**new/needed** — due-review list; the domain model defines it) →
  session runs via `learning.session.*` in `review` mode.
- **Accessibility:** "why due" explained in text + audio; audio-first retrieval.
- **Acceptance criteria:** reviews are retrieval-first (recall before re-teach); the queue reflects the
  engine's schedule; capped daily so it never overwhelms; works offline.

### 6.11 Achievements

- **Purpose:** recognize effort and milestones intrinsically (not competitively) to sustain
  motivation.
- **User journey:** earn a badge (mastery milestone, streak, misconception cleared) → see it
  celebrated at session complete and collected in Achievements.
- **Components:** `AchievementsGrid`, `AchievementBadge`, `StreakBadge`.
- **Data required:** earned achievements + criteria progress.
- **APIs:** `achievements.list` (**new** — derived from learning events: ObjectiveMastered, streaks,
  MisconceptionCleared).
- **Accessibility:** badges have text names + descriptions, not icon-only; reduced-motion aware.
- **Acceptance criteria:** achievements reward **effort and mastery**, never speed or beating others;
  no scarcity/pressure mechanics; fully derivable from existing learning events.

### 6.12 Notifications

- **Purpose:** gentle, useful nudges — "revision due," "new lesson ready," "mentor replied," "great
  streak" — never spammy or anxiety-inducing.
- **User journey:** a small bell on Today shows unread count → open → a simple list → tap to act.
- **Components:** `NotificationBell`, `NotificationList`, `NotificationItem`, `EmptyState`.
- **Data required:** notifications (type, message, action, read state).
- **APIs:** `notifications.list`, `notifications.markRead` (**new**). Push is optional and
  low-frequency; in-app first.
- **Accessibility:** unread count announced; items are text + audio; actions labelled.
- **Acceptance criteria:** frequency is capped and calm; every notification maps to a safe in-app
  action; no external links; can be fully disabled.

---

## 7. Offline experience

Offline is a **first-class mode**, not a fallback (mission-critical for 3G/intermittent learners).

- **Cached for offline use:** the current sign-in session, Today's plan, the **offline lesson
  packages** for planned + due-revision objectives (approved content + media + checksums, from
  Curriculum Studio's `offline_package`), the mastery/progress snapshot, and the design assets.
- **Fully usable offline:** sign-in (cached session), Dashboard (saved plan), a complete **learning
  session** (teach → answer → hint → feedback → complete) from a cached package, the **revision
  queue**, homework, and Profile (snapshot).
- **Queued and synced later:** every interaction/attempt is written to a durable local log with a
  **client-generated idempotent id** and synced via `sync.batch` on reconnect; the server applies
  them idempotently (no double-counting), recomputes mastery from evidence, and returns an updated
  plan.
- **Honest status:** a persistent, non-alarming indicator shows online/offline and "N items waiting to
  sync"; the learner is never blocked or scolded for being offline.
- **Conflict policy:** evidence is append-only and never conflicts; derived state (mastery, schedule)
  is recomputed server-side from merged evidence — no "last write wins" on learning state.
- **Storage discipline:** bounded cache with LRU eviction of old packages; the learner (or guardian)
  can pre-download upcoming lessons on Wi-Fi.

Details of the sync engine and local store are in [STUDENT_PORTAL_ARCHITECTURE.md](STUDENT_PORTAL_ARCHITECTURE.md).

---

## 8. Accessibility (WCAG 2.2 AA, applied)

Cross-cutting requirements, tested on every screen:

- **Perceivable:** every non-text (icons, media, mastery colors) has a text/`aria` equivalent; state
  is never color-alone (add shape/label/text); contrast ≥ AA; audio narration for all core content;
  captions for spoken media.
- **Operable:** all interactive elements keyboard/switch operable with visible focus (WCAG 2.2 §2.4.11
  focus-not-obscured, §2.4.13 focus-appearance); targets ≥ 44×44 CSS px (§2.5.8 target size); no
  motion required; timers avoidable/adjustable; no keyboard traps.
- **Understandable:** short, plain, Urdu-first language; consistent navigation; predictable actions;
  errors explained calmly with a way forward; **no redundant entry** (§3.3.7) and no cognitive-heavy
  auth (§3.3.8 — picture-password/PIN, not puzzles).
- **Robust:** semantic HTML, correct roles/names, `aria-live` for dynamic teacher turns/feedback,
  tested with a screen reader and RTL.
- **RTL & i18n:** Urdu-first, logical CSS properties, mirrored layout/nav/icons where directional;
  language toggle (Urdu/English) persists.

A per-screen a11y acceptance line is included in each §6 spec; the component catalog states each
component's a11y contract.

---

## 9. Mobile-first UX

- **Design for the smallest, slowest first;** enhance up. One-column, thumb-reachable primary actions,
  bottom nav, large touch targets, minimal chrome in the session.
- **Performance budgets (acceptance):** initial interactive ≤ 3 s on low-end Android/3G; JS payload
  tightly budgeted (see ARCHITECTURE); images/media lazy + WebP/compressed; skeletons over spinners;
  60 fps not required — smoothness on low-end devices matters more than flourish.
- **Resilient input:** works with touch, external keyboard/switch, and voice; tolerant of mis-taps
  (large targets, undo).
- **Battery/data aware:** no background polling on cellular; media pre-fetch only on Wi-Fi by default;
  respects data-saver.

---

## 10. Design system requirements

The portal consumes and extends the existing `apps/web` design system (tokens, Button, ReadAloud).
Requirements (detailed in [STUDENT_COMPONENT_CATALOG.md](STUDENT_COMPONENT_CATALOG.md)):

- **Tokens:** colors (AA pairs, light/dark, high-contrast variant), spacing, radii, typography
  (Urdu-capable font, readable sizes with a large-text mode), `--size-touch-min: 44px`, motion tokens
  gated by `prefers-reduced-motion`, elevation.
- **Primitives:** Button (icon+text, variants, never icon-only for actions), ReadAloud (audio),
  Icon (labelled), Input primitives, Card, ProgressRing/Pips, Badge, Toast, Skeleton, EmptyState,
  ErrorBanner, OfflineBadge, BottomNav.
- **Learning-specific organisms:** TeacherTurn, QuestionCard + AnswerInput variants, HintLadder,
  FeedbackToast, MasteryMap, ConceptVisual, WorkedExampleStepper.
- **Theming:** grade-band presets (Early/Middle/Senior) as token overlays; RTL by default; dark + high-
  contrast modes.
- **Governance:** components must make it *impossible* to render ungrounded AI content (the player only
  accepts approved `LessonView` data) and must never expose external links/ads/open input.

---

## 11. Error handling (learner-facing)

Errors must be **calm, brief, audio-supported, and always offer a way forward** — a child must never
hit a dead end or a scary message.

| Situation | Experience | Recovery |
| --- | --- | --- |
| Offline | Persistent friendly badge; content served from cache | Continue offline; auto-sync later |
| Sync pending/failed | "N saved, will send when online" | Retry in background; never blocks learning |
| Content not cached & offline | "This lesson isn't saved yet — here's what you *can* do" | Offer cached alternatives / download on Wi-Fi |
| API/server error | Gentle "let's try again in a moment," never a stack/status | Auto-retry with backoff; fall back to cache |
| Auth expired | Silent refresh; if impossible, simple re-sign-in | Preserve place; resume after |
| Session/lesson load fails | Skeleton → graceful message → safe return to Today | No lost progress |
| Wellbeing/distress | Not an "error": immediate calm help path | Route to safeguarding/mentor |

Principles: fail safe (never lose learning progress), fail closed on security, fail *kind* (child-
appropriate tone), and make errors recoverable without adult help wherever possible.

---

## 12. Security considerations (learner-facing)

- **AuthN/Z:** short-lived bearer token scoped to the learner (`role: student`, `sub == student_ref`);
  the API already **IDOR-guards** every learner endpoint — a child can only ever see their own data.
- **No PII from the child:** the portal collects none; the learning model is pseudonymous; raw AI
  session content is not stored client-side beyond what's needed to sync de-identified evidence.
- **Child-safe surface:** no open chat, no external links, no ads, no third-party embeds/trackers; the
  AI only renders approved, in-scope content (unground­ed generation is unreachable by construction).
- **Safeguarding path always present:** an explicit help/wellbeing affordance is reachable from the
  session and dashboard; distress signals short-circuit teaching to the safeguarding pipeline.
- **Local data protection:** cached learning data is stored in the device's protected app storage,
  encrypted where the platform allows; a shared-device "switch learner" flow clears the previous
  learner's view.
- **Transport & content:** HTTPS only, strict CSP, no inline third-party scripts; content integrity via
  the offline-package checksums.
- **Governance gate:** none of this ships to a real child until the Phase-1.5 decisions (lawful basis,
  DPIA, residency, safeguarding SLA, child-identity) are resolved and independently reviewed. This
  design is built to *satisfy* those, not to bypass them.

---

## 13. Acceptance criteria for the milestone (design-level)

This design is complete and ready for implementation planning when:

- Every screen in §6 has Purpose, Journey, Components, Data, APIs, A11y, and Acceptance criteria
  (met).
- Every new API the portal needs is enumerated with shape + auth + offline behavior
  ([STUDENT_API_REQUIREMENTS.md](STUDENT_API_REQUIREMENTS.md)).
- The offline, accessibility, mobile-first, state, error, and security models are specified and
  internally consistent with the built `/v1/learning` API and the platform non-negotiables.
- The component catalog covers every component referenced by the screens, each with an a11y contract.
- The design contains **no** path that (a) exposes a child to ungrounded AI content, (b) lets a child
  reach another learner's data, (c) collects child PII, or (d) makes learning high-stakes/punitive.

Implementation remains blocked on the Phase-1.5 governance gate and on this design's approval.
