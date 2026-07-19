# 18 · Design Tokens

| | |
|---|---|
| **Document ID** | 18 |
| **Owner** | Head of Product Design / Design Systems Engineer |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [17 UI Design System](./17-ui-design-system.md) · [19 Component Library](./19-component-library.md) · [16 Accessibility](./16-accessibility-standards.md) · [Authoring Brief §7](../_meta/authoring-brief.md) |

## Purpose

This document defines **Taleem's design tokens** — the named, platform-agnostic values (colour, type,
space, radius, elevation, motion) that are the single source of visual truth. Components
([19](./19-component-library.md)) consume tokens only; themes and future languages are token swaps.
This expands the seed in [Authoring Brief §7](../_meta/authoring-brief.md).

## Scope

In scope: token taxonomy, the core token values (seed + semantic aliases), theming, and RTL/localisation
tokens. Out of scope: component composition ([19](./19-component-library.md)) and visual philosophy
([17](./17-ui-design-system.md)). All colour pairings referenced here must meet WCAG AA
([16](./16-accessibility-standards.md)); the final verified ramp is maintained in the token source of
truth (this doc + the tokens file it generates).

---

## 1. Token principles

1. **Two tiers:** **primitive** tokens (raw values) → **semantic** tokens (intent, e.g.
   `color.action.primary`). Components use **semantic** tokens only.
2. **Every visual value is a token** — no hardcoded hex, px, or ms in components ([17 §5](./17-ui-design-system.md)).
3. **Accessible by construction** — semantic colour pairs are contrast-verified ([16](./16-accessibility-standards.md)).
4. **Theme- and locale-swappable** — light/high-contrast/(dark later) and RTL are token/config swaps.
5. **Budget-aware** — token delivery (fonts, CSS vars) fits the payload budget ([04 NFR DATA](../01-product/04-non-functional-requirements.md)).

## 2. Colour tokens

**Primitives (seed — [Authoring Brief §7](../_meta/authoring-brief.md)):**

| Token | Value | Meaning |
|---|---|---|
| `color.green.600` (Ilm Green) | `#0E7C5A` | Learning / growth (brand) |
| `color.ink.900` | `#111827` | Primary text |
| `color.paper.50` | `#FAFAF7` | Background |
| `color.sky.600` | `#2563EB` | Interactive |
| `color.sun.500` | `#F59E0B` | Reward / celebration |
| `color.alert.600` | `#DC2626` | Error / danger |

Full ramps (50–900) are derived per hue in the token source. **Semantic aliases** (what components use):

| Semantic token | Light value | Use |
|---|---|---|
| `color.bg.canvas` | `color.paper.50` | Page background |
| `color.text.primary` | `color.ink.900` | Body text (AA on canvas) |
| `color.action.primary` | `color.sky.600` | Primary buttons/links |
| `color.brand` | `color.green.600` | Brand accents, progress |
| `color.feedback.reward` | `color.sun.500` | Celebrations |
| `color.feedback.danger` | `color.alert.600` | Errors, destructive |
| `color.border.default` | ink-200 (derived) | Dividers, inputs |
| `color.focus.ring` | sky-600 (derived) | Visible focus (AA) |

**Rule:** each semantic text/background pair is verified ≥ AA (4.5:1 body, 3:1 large) before use; colour
is never the sole signal ([16](./16-accessibility-standards.md)).

## 3. Typography tokens

| Token | Value |
|---|---|
| `font.family.urdu` | Noto Nastaliq Urdu / Noto Sans Arabic (primary) |
| `font.family.latin` | Inter (companion) |
| `font.size.100 … 900` | Fluid scale; body ≥ comfortable minimum for readability |
| `font.lineHeight.urdu` | Increased leading tuned for Nastaʿlīq |
| `font.weight.regular/medium/bold` | Managed for data cost (subset weights) |

Typography tokens are **direction-aware** — Urdu uses `font.family.urdu` and RTL leading by default.

## 4. Spacing, sizing, radius, elevation

| Token group | Definition |
|---|---|
| `space.*` | **4px base scale** (4, 8, 12, 16, 24, 32, 48…) ([Authoring Brief §7](../_meta/authoring-brief.md)) |
| `size.touchTarget.min` | `44px` ([04 NFR A11Y-03](../01-product/04-non-functional-requirements.md)) |
| `radius.*` | sm/md/lg/full — friendly, calm rounding |
| `elevation.*` | Subtle, few levels; cheap shadows (perf) |
| `size.container.*` | 360px baseline → tablet/desktop breakpoints |

## 5. Motion tokens

| Token | Value |
|---|---|
| `motion.duration.fast/base/slow` | Short, purposeful (perf-safe) |
| `motion.easing.standard` | Calm standard easing |
| `motion.reduced` | Honors `prefers-reduced-motion` (no essential motion) ([16](./16-accessibility-standards.md)) |

## 6. RTL & localisation tokens

- **Logical properties** (`inset-start/end`, `margin-start/end`) driven by direction token
  `dir = rtl|ltr`; layouts mirror automatically.
- **Directional icon** flag on icons that imply direction (arrows) so they mirror in RTL.
- Locale-aware number/date formatting is a config, not a component concern ([04 NFR L10N-04](../01-product/04-non-functional-requirements.md)).

## 7. Theming

- **Light** (default), **High-contrast** (accessibility), **Dark** (later) are alternate **semantic**
  value maps over the same primitives; components never change.
- Themes and direction are applied at the root; no component reads a raw hex.

## 8. Delivery & governance

- Tokens live in one source of truth and generate CSS custom properties / a Tailwind theme
  ([Authoring Brief §4](../_meta/authoring-brief.md)) consumed by components.
- **CI check:** components must not contain raw colour/space/motion literals (lint) — every value is a
  token ([37 CI/CD](../07-engineering/37-cicd-pipeline.md)).
- Contrast of semantic pairs is validated as part of design review.

## Open questions

- **Final colour ramps** (50–900 per hue) and verified AA pairs — to be locked in the token file.
- **Dark-theme value map** timing.
- **Urdu font weight budget** — how many weights we can afford on the reference device ([04 NFR DATA](../01-product/04-non-functional-requirements.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial tokens: two-tier taxonomy, seed colour primitives + semantic aliases, typography/space/radius/elevation/motion, RTL/locale tokens, theming, CI governance. | Design Systems Engineer |
