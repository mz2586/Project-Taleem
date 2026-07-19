# 59 · Design Token Values & Contrast Matrix

| | |
|---|---|
| **Document ID** | 59 (Phase 1.5 remediation) |
| **Owner** | Design Systems Engineer |
| **Status** | Draft — semantic pairs verified; full 50–900 ramps pending |
| **Last updated** | 2026-07-19 |
| **Closes** | AR-C-18 (the contrast matrix asserted in [16 §3](./16-accessibility-standards.md)/[18 §2](./18-design-tokens.md) but absent) |
| **Related** | [18 Design Tokens](./18-design-tokens.md) · [16 Accessibility](./16-accessibility-standards.md) · [17 UI Design System](./17-ui-design-system.md) |

## Purpose

[18 Design Tokens](./18-design-tokens.md) contained only 6 seed hexes and "(derived)" placeholders, while
[16 §3](./16-accessibility-standards.md) claimed the contrast table "is validated in CI." This document
provides the **actual computed WCAG 2.1 contrast ratios** for the load-bearing semantic pairs, so the AA
claims are verifiable rather than asserted.

## Scope

In scope: verified contrast for the primary semantic pairs, usage constraints derived from them, minimum
type sizes, and the high-contrast direction. Out of scope: the full per-hue 50–900 ramp generation (a
follow-up task; the seed hues below are the `600`/base anchors).

---

## 1. Verified contrast matrix (WCAG 2.1; sRGB relative luminance)

Ratios computed for the seed palette ([Authoring Brief §7](../_meta/authoring-brief.md)). **AA thresholds:
normal text ≥ 4.5:1, large text/UI ≥ 3:1.**

| Foreground | Background | Ratio | Normal text (4.5) | Large/UI (3.0) | Verdict |
|---|---|---:|:--:|:--:|---|
| Ink `#111827` | Paper `#FAFAF7` | **16.98** | ✅ | ✅ | Body text — AAA |
| Sky `#2563EB` | Paper `#FAFAF7` | **4.94** | ✅ | ✅ | Links/interactive text OK |
| White `#FFFFFF` | Sky `#2563EB` | **5.17** | ✅ | ✅ | Primary button text OK |
| White `#FFFFFF` | Ilm Green `#0E7C5A` | **5.19** | ✅ | ✅ | Brand button text OK |
| Ilm Green `#0E7C5A` | Paper `#FAFAF7` | **4.96** | ✅ | ✅ | Brand text/accents OK |
| White `#FFFFFF` | Alert `#DC2626` | **4.83** | ✅ | ✅ | Danger button text OK |
| Alert `#DC2626` | Paper `#FAFAF7` | **4.62** | ✅ | ✅ | Error text OK |
| Ink `#111827` | Sun `#F59E0B` | **8.27** | ✅ | ✅ | Reward chip = Ink-on-Sun OK |
| **Sun `#F59E0B`** | **Paper `#FAFAF7`** | **2.05** | ❌ | ❌ | **Sun is NOT a text/essential-UI colour on paper** |
| Sky (focus ring) | Paper `#FAFAF7` | **4.94** | — | ✅ | Focus indicator ≥ 3:1 OK |

## 2. Usage constraints derived from the matrix

- **Sun `#F59E0B` must never carry text or essential UI on Paper** (2.05:1). Use Sun only as a fill with
  **Ink text on it** (8.27:1), or as a decorative reward accent — never colour-only signalling
  ([16](./16-accessibility-standards.md)).
- All other primary semantic pairs pass AA for normal text — but several (Sky 4.94, Green 4.96, Alert
  4.62) are **close to the 4.5 floor**, so their exact ramp shades must be re-verified when the full ramp
  is generated, and must not be lightened.
- **Focus ring** uses Sky (4.94:1 vs Paper) — meets the 3:1 non-text requirement.

## 3. Minimum type sizes (closes the "comfortable minimum" gap)

| Token | Value (planning assumption) |
|---|---|
| `font.size.body.min` (Latin) | 16px |
| `font.size.body.min.urdu` (Nastaʿlīq/Naskh) | **18px floor** (Urdu needs a larger minimum for legibility) |
| `font.size.caption.min` | 14px (non-essential only) |

These replace "large minimum body size" ([17 §2.2](./17-ui-design-system.md)) / "comfortable minimum"
([18 §3](./18-design-tokens.md)) with numbers, verified for legibility on the low-DPI reference screen
(pending device test).

## 4. High-contrast direction

The high-contrast theme raises every semantic text pair to **≥ 7:1** (AAA). Because Ink-on-Paper is
already 16.98:1, high-contrast primarily strengthens the mid-tone pairs (Sky/Green/Alert) toward darker
shades and increases border/focus weight. The high-contrast value map is a v1 deliverable; it must be
re-checked against Nastaʿlīq legibility (thin strokes can fail perceptually even at a high numeric ratio).

## 5. CI validator

A contrast-validation script re-computes every semantic pair's ratio against its target on each change
([37 CI/CD](../07-engineering/37-cicd-pipeline.md)); the build fails if any pair regresses below its
threshold. Until the full ramps exist, [16 §3](./16-accessibility-standards.md)'s "validated in CI" claim
applies to the pairs in §1 only.

## Open questions

- Full 50–900 ramp generation per hue with each shade's computed ratio.
- Real-device legibility of the 18px Urdu floor on Android Go.
- High-contrast value map + Nastaʿlīq perceptual check.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial verified token values (Phase 1.5): computed WCAG ratios for all primary semantic pairs, Sun usage constraint, numeric minimum type sizes (18px Urdu floor), high-contrast direction, CI validator scope. | Design Systems Engineer |
