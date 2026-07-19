# 17 · UI Design System

| | |
|---|---|
| **Document ID** | 17 |
| **Owner** | Head of Product Design |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [16 Accessibility](./16-accessibility-standards.md) · [18 Design Tokens](./18-design-tokens.md) · [19 Component Library](./19-component-library.md) · [20 Navigation](./20-navigation-structure.md) · [07 IA](../01-product/07-information-architecture.md) · [04 NFR](../01-product/04-non-functional-requirements.md) · [Authoring Brief §7](../_meta/authoring-brief.md) |

## Purpose

This document defines the **Taleem design system** — the shared visual and interaction language that
makes seven surfaces feel like one warm, calm, Urdu-first school, usable by a low-literacy child on a
360px screen. It sets the design philosophy, layout and grid, typography and RTL rules, colour and
theming, imagery/iconography, motion, and the states/patterns that the component library
([19](./19-component-library.md)) implements from the tokens ([18](./18-design-tokens.md)).

## Scope

In scope: design philosophy, foundations (layout, type, colour, motion, imagery), interaction states,
and system governance. Out of scope: the raw token values ([18](./18-design-tokens.md)), individual
component specs ([19](./19-component-library.md)), navigation structure ([20](./20-navigation-structure.md)),
and accessibility criteria ([16](./16-accessibility-standards.md)) — this system must satisfy them.

---

## 1. Design principles

1. **Warm, calm, never patronising** ([Authoring Brief §7](../_meta/authoring-brief.md)) — a school
   that encourages, not a toy that overstimulates.
2. **Clarity over decoration** — a child under stress needs the next action obvious; every screen has
   one clear primary action.
3. **Urdu-first, RTL-complete** — design in Urdu/RTL first, Latin/LTR second ([16 §RTL](./16-accessibility-standards.md)).
4. **Low-literacy friendly** — icon + text always, plain language, audio support, generous imagery.
5. **Reach-first** — lightweight, low-data, works on a 360px low-end screen; design never exceeds the
   payload budget ([04 NFR DATA](../01-product/04-non-functional-requirements.md)).
6. **Accessible by construction** — WCAG 2.2 AA is the floor, designed in, not retrofitted ([16](./16-accessibility-standards.md)).
7. **One system, tokenised** — every visual value comes from a token so themes and future languages
   change data, not components.

## 2. Foundations

### 2.1 Layout & grid

- **Mobile-first, 360px baseline**; fluid up to tablet/desktop for staff surfaces.
- **4px spacing base** ([Authoring Brief §7](../_meta/authoring-brief.md)); a simple, generous spacing
  scale ([18 §spacing](./18-design-tokens.md)).
- **One-handed reach:** primary actions in the thumb zone; bottom navigation on child/guardian apps
  ([07 §4](../01-product/07-information-architecture.md)).
- **Touch targets ≥ 44px** with adequate spacing ([04 NFR A11Y-03](../01-product/04-non-functional-requirements.md)).

### 2.2 Typography & RTL

- **Urdu-first typeface** with excellent Nastaʿlīq/Naskh rendering (Noto Nastaliq Urdu / Noto Sans
  Arabic) + a clean Latin companion (Inter) ([Authoring Brief §7](../_meta/authoring-brief.md)).
- **Fluid type scale**, large minimum body size for readability; line height tuned for Nastaʿlīq.
- **Full RTL:** mirrored layout, logical properties (`start`/`end`), correct bidi handling; icons that
  imply direction are mirrored ([16](./16-accessibility-standards.md)).
- **Font loading is budget-aware** — subset, `font-display: swap`, cached; Urdu font weight managed for
  data cost ([04 NFR DATA](../01-product/04-non-functional-requirements.md)).

### 2.3 Colour & theming

- **Seed palette** ([Authoring Brief §7](../_meta/authoring-brief.md)): Deep Ilm Green `#0E7C5A`
  (learning/growth), Ink `#111827`, Paper `#FAFAF7`, Sky `#2563EB` (interactive), Sun `#F59E0B`
  (reward), Alert `#DC2626`. Final ramps in [18 Tokens](./18-design-tokens.md).
- **All pairings meet WCAG AA contrast**; colour is **never the sole signal** (icon/text/shape too)
  ([16](./16-accessibility-standards.md), [04 NFR A11Y-05](../01-product/04-non-functional-requirements.md)).
- **Theming via tokens** — light default; high-contrast and (later) dark are token swaps.

### 2.4 Iconography & imagery

- **Icon + text**, never icon-only, for low literacy ([07 §8](../01-product/07-information-architecture.md)).
- Culturally grounded, respectful, gender/religion-neutral imagery ([Authoring Brief §3](../_meta/authoring-brief.md));
  optimised and lite-mode-aware ([34 Media](../02-architecture/34-media-architecture.md)).
- A consistent, lightweight icon set delivered efficiently (sprite/inline SVG within budget).

### 2.5 Motion

- **Minimal, purposeful motion** — orientation and feedback, not spectacle; respects
  `prefers-reduced-motion` ([16](./16-accessibility-standards.md)).
- Cheap on low-end devices (transform/opacity only); no jank on the reference baseline
  ([04 NFR PERF-04](../01-product/04-non-functional-requirements.md)).

## 3. Interaction states & patterns

Every interactive element defines all states, tokenised and accessible:

| State | Rule |
|---|---|
| **Default / Hover / Focus / Active / Disabled** | Focus is always **visibly** indicated (keyboard + AA); disabled communicates why. |
| **Loading** | Skeletons/spinners with honest progress; never a frozen screen. |
| **Empty** | Always a helpful next step; never a dead end ([07 §9](../01-product/07-information-architecture.md)). |
| **Error** | Plain-language, in-Urdu, recoverable; uses the uniform error shape from the API ([10 §4](../02-architecture/10-api-design.md)). |
| **Offline** | Explicit offline/queued affordances ([33](../02-architecture/33-offline-architecture.md)). |
| **Success/celebration** | Warm, non-exploitative reward ([15 §8](../03-security-privacy/15-child-safety-framework.md)). |

## 4. Content & tone

- Warm, encouraging microcopy; short sentences; plain Urdu; second person ("you can do this").
- The **AI Teacher is always visually and textually labelled as AI**, never styled to impersonate a
  human ([FR-AIT-006](../01-product/03-functional-requirements.md)).
- Localisable strings only — no baked-in copy ([04 NFR L10N-02](../01-product/04-non-functional-requirements.md)).

## 5. Governance

- The design system is the **single source of visual truth**; surfaces compose it, never fork it.
- Changes go through design review + accessibility review; token changes ripple everywhere by design.
- Every component ships with states, RTL, and AA verified ([19](./19-component-library.md), [50 DoD](../07-engineering/50-definition-of-done.md)).

## Open questions

- **Dark mode** timing vs. Phase-1 scope (token-ready now, ship later).
- **Illustration style** and sourcing that is culturally grounded and low-data.
- **Age-tiered visual treatment** (KG vs. Grade 10) within one system ([15 §8](../03-security-privacy/15-child-safety-framework.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial design system: principles, foundations (layout/type/RTL/colour/imagery/motion), interaction states, tone, governance. | Head of Product Design |
