# 19 · Component Library

| | |
|---|---|
| **Document ID** | 19 |
| **Owner** | Design Systems Engineer / Frontend Lead |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [17 UI Design System](./17-ui-design-system.md) · [18 Design Tokens](./18-design-tokens.md) · [16 Accessibility](./16-accessibility-standards.md) · [20 Navigation](./20-navigation-structure.md) · [04 NFR](../01-product/04-non-functional-requirements.md) |

## Purpose

This document specifies the **shared component library** that implements the design system
([17](./17-ui-design-system.md)) from tokens ([18](./18-design-tokens.md)): the component inventory,
the contract every component must meet (states, RTL, accessibility, performance), and the composition
patterns the seven surfaces build from. It is the bridge between design and code.

## Scope

In scope: component inventory, per-component contract, key component specs, and library governance. Out
of scope: token values ([18](./18-design-tokens.md)), page-level IA/navigation ([20](./20-navigation-structure.md)),
and portal screens ([06-portals/*](../06-portals/25-parent-portal.md)) — which compose these
components.

---

## 1. Principles

1. **Compose the system, don't fork it** — surfaces use these components; they never restyle with raw
   values ([17 §5](./17-ui-design-system.md)).
2. **Accessible & RTL by construction** — a component ships only when AA + RTL + keyboard are verified
   ([16](./16-accessibility-standards.md)).
3. **Lightweight** — minimal client JS; Server Components by default; each component respects the
   payload budget ([04 NFR DATA-01](../01-product/04-non-functional-requirements.md)).
4. **Every state defined** — default/hover/focus/active/disabled/loading/empty/error/offline
   ([17 §3](./17-ui-design-system.md)).
5. **Localisable** — no hardcoded copy; direction-aware ([04 NFR L10N](../01-product/04-non-functional-requirements.md)).

## 2. Component contract (every component must)

| Requirement | Detail |
|---|---|
| **Token-only styling** | No raw hex/px/ms; semantic tokens only ([18](./18-design-tokens.md)). |
| **All states** | Implements every state in [17 §3](./17-ui-design-system.md). |
| **Keyboard operable** | Full keyboard support; **visible focus** ([16](./16-accessibility-standards.md)). |
| **Screen-reader labelled** | Correct roles/names; Urdu + English ([04 NFR A11Y-04](../01-product/04-non-functional-requirements.md)). |
| **RTL-complete** | Logical properties; mirrors correctly; directional icons flip. |
| **Touch ≥ 44px** | Meets target size ([04 NFR A11Y-03](../01-product/04-non-functional-requirements.md)). |
| **Budget-safe** | Minimal JS; no layout thrash on reference device. |
| **Documented** | Usage, props, a11y notes, do/don't. |

## 3. Component inventory

| Category | Components |
|---|---|
| **Primitives** | Button, Icon, Text/Heading, Link, Badge, Avatar, Spinner, Divider |
| **Forms** | Input, PIN/Picture-PIN entry, Select, Checkbox, Radio, Toggle, OTP input, FieldError, Form |
| **Feedback** | Toast, Alert/Banner, EmptyState, ErrorState, OfflineBanner, ProgressBar, SkeletonLoader |
| **Layout** | AppShell, Card, List/ListItem, Tabs, Accordion, BottomSheet, Modal/Dialog, Section |
| **Navigation** | BottomNav, TopBar, Breadcrumb, ProfilePicker, Menu ([20](./20-navigation-structure.md)) |
| **Learning** | LessonBlock (text/image/audio), AudioPlayer, FormativeCheck, AttemptCard, MasteryMeter, StreakBadge, ReportCardView |
| **AI Teacher** | AITeacherLabelChip, AIMessage, StreamingResponse (labelled AI, [FR-AIT-006](../01-product/03-functional-requirements.md)) |
| **Media** | ResponsiveImage, DownloadPackTile (with size), Transcript |

## 4. Key component specs (illustrative)

| Component | Notable requirements |
|---|---|
| **Button** | Primary/secondary/ghost/danger via semantic tokens; loading + disabled states; ≥44px; label always visible (icon+text). |
| **Picture-PIN entry** | Randomised grid render; large tap targets; no PIN echoed; screen-reader accessible without leaking the secret ([11 §5](../03-security-privacy/11-authentication-strategy.md)). |
| **AudioPlayer** | Low-data variant, transcript toggle, keyboard controls, works offline for packaged audio ([34 Media §4](../02-architecture/34-media-architecture.md)). |
| **DownloadPackTile** | Shows pack size **before** download; respects Save-Data ([04 NFR DATA-04](../01-product/04-non-functional-requirements.md)). |
| **AIMessage** | Always shows the AI Teacher label; distinct from human/mentor messages; safe-content only ([15 §3](../03-security-privacy/15-child-safety-framework.md)). |
| **OfflineBanner** | Honest offline/queued/syncing state ([33](../02-architecture/33-offline-architecture.md)). |
| **ReportCardView** | Renders/export; cites curriculum version; no fabricated data ([FR-GRD-002/003](../01-product/03-functional-requirements.md)). |
| **MasteryMeter** | Not colour-only; icon+label; celebrates without dark patterns ([15 §8](../03-security-privacy/15-child-safety-framework.md)). |

## 5. Composition patterns

- **AppShell + BottomNav** for child/guardian apps (≤5 destinations, [20](./20-navigation-structure.md)).
- **Card lists** for cohorts/children/lessons (scannable, low-literacy).
- **FormativeCheck** composes Form + FieldError + Button with sealed-submission semantics
  ([FR-ASM-002](../01-product/03-functional-requirements.md)).
- **LessonBlock** sequence renders a lesson from ordered blocks ([22 Lesson Engine](../05-education/22-lesson-engine.md)).

## 6. Governance

- Components live in one library; versioned; changes reviewed by design + a11y + frontend.
- **CI gates:** token-only lint, axe accessibility checks, RTL visual regression, bundle-size budget
  ([37 CI/CD](../07-engineering/37-cicd-pipeline.md), [04 NFR](../01-product/04-non-functional-requirements.md)).
- A component is "done" only when its contract (§2) is fully met ([50 DoD](../07-engineering/50-definition-of-done.md)).

## Open questions

- **Headless base vs. bespoke** — build on an accessible headless primitive set or fully bespoke for
  bundle control.
- **Storybook/docs tooling** within the data/perf and tooling budget.
- **Age-tiered component variants** (KG vs. Grade 10) ([15 §8](../03-security-privacy/15-child-safety-framework.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial component library: contract, inventory, key specs (Picture-PIN, AudioPlayer, AIMessage, DownloadPackTile, ReportCardView…), composition patterns, CI governance. | Design Systems Engineer |
