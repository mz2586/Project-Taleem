# Student Component Catalog (Phase 5 Design)

Status: **Design only** — no implementation code. Companion to
[STUDENT_EXPERIENCE.md](STUDENT_EXPERIENCE.md) and [STUDENT_COMPONENT_CATALOG referenced screens].
Specifies every reusable component the Student Portal needs, organized by atomic-design layer. Each
entry gives **Purpose · Key props (design-level) · States · Accessibility contract · Used by**.

All components: **presentation-only** (no data fetching, no AI-content construction), **RTL-first**,
**theme-aware** (Early/Middle/Senior band presets + dark + high-contrast), consume the existing
`apps/web` design tokens, and meet **WCAG 2.2 AA**. A component that renders learning content accepts
**only approved `LessonView`-shaped data** — it is structurally impossible to render ungrounded AI
output.

Governance/safety rules that bind the whole catalog:

- No component renders external links, ads, third-party embeds, or open free-text chat.
- Every actionable icon is **icon + text** (or has a visible label); never icon-only for actions.
- Every content component pairs text with **audio** (`ReadAloud`) and never conveys state by color
  alone (add shape/label/text).

---

## 1. Foundations (design tokens — required)

Not components, but the contract everything depends on (extends `apps/web/design-system/tokens.css`):

- **Color:** AA-contrast pairs; semantic roles (surface, text, brand, success, warning, danger,
  info); light + dark + **high-contrast** variants; mastery-state palette that is **paired with
  shape/label** (never color-only).
- **Typography:** Urdu-capable font stack, RTL; readable base sizes with a **large-text** mode; short
  line lengths.
- **Space & size:** spacing scale; `--size-touch-min: 44px` (WCAG 2.5.8); radii; elevation.
- **Motion:** motion tokens **gated by `prefers-reduced-motion`**; nothing requires motion.
- **Bands:** `Early / Middle / Senior` token overlays (density, iconography, text amount).

---

## 2. Primitives (atoms)

| Component | Purpose | Key props | States | A11y contract | Used by |
| --- | --- | --- | --- | --- | --- |
| `AppShell` | App frame: header slot, content, bottom nav, offline badge, live-region host | `header`, `nav`, `children` | online/offline | landmark roles; single `aria-live` polite region; skip-link | all |
| `PrimaryButton` / `Button` | Actions; **icon+text**, never icon-only | `label`, `icon?`, `variant`, `size`, `onPress`, `disabled`, `loading` | default/hover/focus/active/disabled/loading | ≥44px; visible focus; `aria-busy` when loading; label always present | all |
| `Icon` | Decorative or labelled icon | `name`, `label?`, `decorative` | — | `aria-hidden` if decorative, else `aria-label` | many |
| `ReadAloud` | Play recorded audio for the adjacent content | `audioRef`, `label` | idle/playing/unavailable | **visible label** (not emoji-only), `aria-pressed`, keyboard operable | every content block |
| `LanguageToggle` | Switch Urdu/English, persists | `value`, `onChange` | ur/en | labelled toggle; announces change | shell |
| `Text` / `Heading` | Typographic primitives (RTL, band-aware) | `as`, `size`, `tone` | — | semantic heading levels; sufficient contrast | all |
| `Card` | Grouped content surface | `children`, `elevated?`, `onPress?` | default/pressable/focus | region/button semantics as appropriate | many |
| `Badge` / `Chip` | Small status/label (due, subject, count) | `label`, `tone`, `shape` | — | text label; not color-only (shape/label) | dashboard, lists |
| `ProgressRing` | Circular mastery/progress | `value`, `label` | — | **text percentage** alongside; `role=img` + label | dashboard, profile |
| `ProgressPips` | Steps in the current session | `total`, `current` | — | `aria-label` "step N of M" | session |
| `Skeleton` | Loading placeholder (preferred over spinners) | `variant` | — | `aria-busy`; not announced as content | slow-data screens |
| `Toast` / `FeedbackToast` | Transient, encouraging feedback | `tone`, `message`, `audioRef?` | enter/exit (reduced-motion aware) | `aria-live` polite/assertive by importance | session |
| `EmptyState` | Positive empty/first-run states | `title`, `body`, `action?`, `audioRef?` | — | text + audio; actionable | many |
| `ErrorBanner` | Calm, child-safe error | `message`, `action` | — | `role=alert`/`aria-live`; never shows status/stack | all |
| `OfflineBadge` | Persistent online/offline + sync count | `online`, `pendingCount` | online/offline/syncing | announced politely; not alarming | shell |
| `PinPad` / `PicturePassword` | Child-safe credential entry | `onComplete`, `mode` | default/error | ≥44px keys, labelled, keyboard/switch, audio prompts; picture alt for weak readers | sign-in |
| `LearnerAvatarPicker` | Choose/confirm the signed-in learner | `learners`, `onSelect` | — | labelled options; keyboard navigable | sign-in |

---

## 3. Molecules

| Component | Purpose | Key props | States | A11y contract | Used by |
| --- | --- | --- | --- | --- | --- |
| `BottomNav` | ≤5 thumb-reachable destinations (band-aware, RTL) | `items`, `active` | active/inactive | `aria-current` on active; labelled; keyboard | shell |
| `GreetingHeader` | Warm, audio greeting + status | `name`, `audioRef` | — | text + audio; heading semantics | dashboard |
| `PrimaryActionCard` | The one big "Start today's learning" launcher | `objectiveTitle`, `estMinutes`, `onStart` | ready/loading | first-focus, largest target, announced first | dashboard |
| `TodayLessonsList` | Today's queued objectives | `items`, `onOpen` | — | list semantics; each item labelled | dashboard |
| `RevisionDueCard` | Count + due-now review launcher | `count`, `onStart` | none-due/due | "why review" summarized; not count-only | dashboard, revision |
| `StreakBadge` / `AttendanceStrip` | Consistency, non-punitive | `streakDays`, `week` | — | text + audio; positive framing | dashboard, profile |
| `AchievementsStrip` | Recent recognitions | `items` | — | named badges (not icon-only) | dashboard |
| `NotificationBell` | Unread indicator + open | `unread`, `onOpen` | zero/some | count announced; labelled | dashboard |
| `SubjectCard` | A subject with progress | `subject`, `progress` | — | progress as text + ring; not color-only | subjects |
| `TopicRow` / `LockedIndicator` | Objective row with mastery/lock | `topic`, `masteryState`, `lockedReason?` | mastered/in-progress/needs-review/locked | state via label+shape; lock explains *why* in text+audio | subjects |
| `HomeworkItemCard` / `AssessmentCard` | List item with due/type | `item`, `onOpen`, `badge` | due/overdue/done; formative/summative | status text; summative shows mentor-supervised note | homework, assessments |
| `TimetableBlock` | A scheduled block | `subject`, `objective`, `minutes`, `onStart` | — | labelled with subject+time; keyboard | timetable |
| `GoalCard` | A simple learner goal + progress | `goal`, `progress`, `onEdit` | — | plain language; non-binding framing | profile |
| `StatTile` | One supportive statistic | `label`, `value`, `hint` | — | avoids anxiety-inducing precision; text | profile, progress |
| `NotificationItem` | A single calm nudge | `notification`, `onAction`, `onRead` | read/unread | actionable; no external links | notifications |

---

## 4. Organisms (learning-specific — the heart)

These render the AI teaching interaction. They accept **only approved `LessonView` data** and are the
structural guarantee that a child never sees ungrounded content.

### `SessionShell`

- **Purpose:** minimal-chrome session frame (big content area, progress pips, pause, help).
- **Key props:** `progress`, `onPause`, `onHelp`, `children`.
- **States:** loading/teaching/interacting/paused/escalated.
- **A11y:** `Help` and `Pause` always reachable/labelled; live-region for teacher turns; focus managed
  between turns; reduced-motion.
- **Used by:** Session player.

### `TeacherTurn`

- **Purpose:** render one AI-teacher utterance (present / ask / hint / feedback / remediate), always
  with audio.
- **Key props:** `kind`, `text`, `audioRef`, `visual?` (`ConceptVisual`), `autoNarrate` (Early band).
- **States:** narrating/idle.
- **A11y:** `aria-live` polite for new turns; `ReadAloud` present; text short; captions for media;
  **cannot render arbitrary HTML** (plain, sanitized, approved text only).
- **Used by:** Session player. **Governance:** input restricted to approved utterance data.

### `ConceptVisual`

- **Purpose:** show a concept's SVG/diagram/animation/image with alt text.
- **Key props:** `mediaRef`, `altText`, `kind`.
- **States:** loading/loaded/unavailable-offline.
- **A11y:** mandatory alt text; decorative vs meaningful distinguished; reduced-motion for animation;
  offline fallback.
- **Used by:** TeacherTurn, WorkedExampleStepper.

### `WorkedExampleStepper`

- **Purpose:** present a worked example one step at a time (CLT), then fade to a problem.
- **Key props:** `steps[]`, `onNext`, `fadeLevel`.
- **States:** step index; example → completion → independent.
- **A11y:** one step focus at a time; audio per step; "step N of M".
- **Used by:** Session player (teach).

### `QuestionCard` + `AnswerInput` (variants)

- **Purpose:** pose an authored practice item and capture a multi-modal answer.
- **Key props:** `item` (approved `ItemView`), `onAnswer`, `mode` (mcq/tap/order/match/short).
- **AnswerInput variants:** `TapOptions` (labelled, audio each), `VoiceAnswer`, `DrawAnswer`,
  `ChooseImage`, `ShortText` (senior only).
- **States:** unanswered/answering/submitted; correct/incorrect (post-score, via FeedbackToast).
- **A11y:** answerable **without reading** (audio + icon options); options ≥44px; no time pressure by
  default; keyboard/switch/voice; error/feedback announced.
- **Used by:** Session, Homework, Assessments (formative). **Governance:** items come only from the
  approved lesson package.

### `HintButton` + `HintLadder`

- **Purpose:** request the next **authored** graduated hint (never the answer first; capped).
- **Key props:** `level`, `maxLevel`, `onRequestHint`, `exhausted`.
- **States:** available/exhausted (→ re-explain/help).
- **A11y:** clearly labelled; hint text + audio; announces when hints are exhausted and offers help.
- **Used by:** Session player. **Governance:** hints from the authored ladder only.

### `MisconceptionCorrectionCard`

- **Purpose:** deliver the **authored** correction for a detected misconception, then a targeted retry.
- **Key props:** `misconceptionRef`, `correctionText`, `audioRef`, `onRetry`.
- **A11y:** supportive tone; text + audio; not shaming.
- **Used by:** Session (remediate).

### `FeedbackToast`

- **Purpose:** encouraging affirm/correct feedback after an answer.
- **Key props:** `outcome`, `message`, `audioRef`.
- **A11y:** `aria-live`; never punitive language; reduced-motion.
- **Used by:** Session, Homework.

### `SessionSummaryCard` + `CelebrationBurst` + `NextStepCard`

- **Purpose:** close the session positively (what was learned, mastery gained, next step, revision
  scheduled).
- **Key props:** `summary`, `masteryDelta`, `nextStep`, `revisionNote`.
- **A11y:** celebration optional + reduced-motion + never audio-only; summary text + audio; next action
  first-focus.
- **Used by:** Session complete.

### `MasteryMap`

- **Purpose:** visualize objectives by mastery state across subjects (the learner's map of what they
  know).
- **Key props:** `nodes` (objective + state), `onSelect`.
- **States:** not-started / in-progress / mastered / needs-review / at-risk.
- **A11y:** state via **label + shape + text**, never color alone; keyboard-navigable; an audio/text
  summary complements the visual ("40 of 120 ideas mastered in Math"); large targets.
- **Used by:** Profile.

### `HelpAffordance` (safety)

- **Purpose:** an always-reachable, calm help/wellbeing route from session + dashboard.
- **Key props:** `onHelp`.
- **A11y:** persistent, labelled, keyboard/switch; high-priority focus target.
- **Used by:** Session, Dashboard. **Governance:** triggers the real-time safeguarding path; pauses
  teaching immediately; never overridden.

---

## 5. Templates / shells (page-level compositions)

| Template | Composition | Screens |
| --- | --- | --- |
| `DashboardTemplate` | AppShell + GreetingHeader + PrimaryActionCard + status cards + BottomNav | Today |
| `SessionTemplate` | SessionShell + TeacherTurn/QuestionCard/Hint/Feedback + Help/Pause | Learning session |
| `ListTemplate` | AppShell + titled list (Homework/Assessments/Revision/Notifications/Achievements) | list screens |
| `SubjectsTemplate` | AppShell + SubjectGrid → ChapterList → TopicRow | Subjects |
| `ProfileTemplate` | AppShell + ProfileHeader + StatTiles + MasteryMap + Goals + History | Profile |
| `SignInTemplate` | AppShell (minimal) + LearnerAvatarPicker + PinPad/PicturePassword | Sign-in |

---

## 6. Coverage check (every referenced component is catalogued)

Every component named in [STUDENT_EXPERIENCE.md](STUDENT_EXPERIENCE.md) §6 and
[STUDENT_UI_FLOW.md](STUDENT_UI_FLOW.md) appears above with an a11y contract and a governance note
where it renders learning content. New primitives not already in `apps/web/design-system` (PinPad,
PicturePassword, ProgressRing/Pips, MasteryMap, TeacherTurn, QuestionCard/AnswerInput, HintLadder,
OfflineBadge, ReadAloud-with-visible-label) are flagged as **net-new** and must be built to the a11y +
governance contracts here.

## 7. Acceptance criteria (catalog-level)

- Every component: RTL-correct, theme-aware (bands + dark + high-contrast), keyboard/switch operable,
  visible focus, ≥44px targets, state not color-only, and (for content components) text paired with
  audio.
- No component can render ungrounded AI content, external links, ads, or open chat.
- The Help/safety affordance is reachable from the session and dashboard at all times.
- Net-new primitives are specified well enough to build without further design (props, states, a11y).
