# 50 · Definition of Done

| | |
|---|---|
| **Document ID** | 50 |
| **Owner** | Head of Quality / Principal Engineer |
| **Status** | Approved (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [03 FR](../01-product/03-functional-requirements.md) · [04 NFR](../01-product/04-non-functional-requirements.md) · [15 Child Safety](../03-security-privacy/15-child-safety-framework.md) · [16 Accessibility](../04-design/16-accessibility-standards.md) · [14 Privacy](../03-security-privacy/14-privacy-model.md) · [40 Testing](./40-testing-strategy.md) · [37 CI/CD](./37-cicd-pipeline.md) |

## Purpose

This document is the **Definition of Done (DoD)** — the single checklist every change must satisfy to
ship. It turns the mission's non-negotiables (child safety, reach at the bottom of the curve,
accessibility, privacy, honesty, scale) into concrete, verifiable release gates. **A change is not
"done" until every applicable item is met.**

## Scope

In scope: the DoD checklist for code changes (and the doc-DoD for Phase 1), and how it is enforced. Out
of scope: the individual standards it references (each owned by its doc). The DoD **aggregates** those
gates; it does not redefine them.

---

## 1. Principles

1. **Safety, reach, accessibility, privacy are pass/fail** — never "we'll add it later"
   ([01 Vision §7](../00-overview/01-vision.md), [15 §1](../03-security-privacy/15-child-safety-framework.md)).
2. **Done means verified**, not "works on my machine" — every claim has evidence ([40](./40-testing-strategy.md)).
3. **The gate is automated where possible**, enforced in CI ([37](./37-cicd-pipeline.md)).

## 2. Definition of Done — code change

A change ships only when **all applicable** items are ✅:

### Correctness & tests
- [ ] Implements the referenced FR(s); acceptance criteria met ([03](../01-product/03-functional-requirements.md)).
- [ ] Unit/integration/contract tests added; domain coverage ≥ target ([40](./40-testing-strategy.md), [04 NFR MNT-02](../01-product/04-non-functional-requirements.md)).
- [ ] All CI checks green ([37](./37-cicd-pipeline.md)).

### Child safety (SAC — [15 §11](../03-security-privacy/15-child-safety-framework.md))
- [ ] No path exposes a child to unmoderated AI output or user content (SAC-1).
- [ ] Any AI interaction passes input+output guardrails; transcript logged (SAC-3).
- [ ] Distress/safeguarding signals escalate to a human within SLA (SAC-4).
- [ ] No unsupervised high-stakes AI decision about a child (SAC-5).
- [ ] Age-appropriate; safety help + one-tap reporting reachable (SAC-6/7).
- [ ] AI safety **red-team eval green** (release-blocking) ([40 §3](./40-testing-strategy.md)).

### Reach (bottom of the curve — [04 NFR](../01-product/04-non-functional-requirements.md))
- [ ] Works offline/lite on the reference baseline where user-facing (OFFL/COMPAT).
- [ ] Within payload/data budgets; bundle budget met (DATA-01/02).
- [ ] Performance budgets met on 3G (PERF-02/03).

### Accessibility ([16](../04-design/16-accessibility-standards.md))
- [ ] WCAG 2.2 AA (axe + manual); RTL-complete; Urdu-first; ≥44px; keyboard + screen-reader.

### Privacy & security ([14](../03-security-privacy/14-privacy-model.md), [13](../03-security-privacy/13-security-model.md))
- [ ] Data minimisation; correct data-class handling; no child PII/secrets in logs.
- [ ] Consent enforced where child data is processed; least-privilege authz; every route has a policy binding.
- [ ] Security scans clean of criticals; secrets not committed.

### Honesty & integrity ([01 Vision §7](../00-overview/01-vision.md))
- [ ] No fabricated grades/progress; figures derive from immutable sources ([23](../05-education/23-assessment-engine.md)).

### Scale & operability ([04 NFR](../01-product/04-non-functional-requirements.md))
- [ ] No decision caps growth < 1M; idempotent/retry-safe critical writes; observability + runbook for new alerts.

### Docs
- [ ] Owning spec/docs updated; cross-refs valid ([42](./42-documentation-standards.md)).

## 3. Definition of Done — documentation (Phase 1)

For blueprint docs (current phase):
- [ ] Metadata block, Purpose/Scope, Open Questions, Change log present ([42 §2](./42-documentation-standards.md)).
- [ ] Consistent with the [Authoring Brief](../_meta/authoring-brief.md); no silent divergence (ADR if needed).
- [ ] Canonical cross-references; **markdownlint + link-check + mermaid green** ([37](./37-cicd-pipeline.md)).
- [ ] Decision-dense; no fabricated stats (planning assumptions labelled).

## 4. Enforcement

- **Automated gates** in CI ([37](./37-cicd-pipeline.md), [40](./40-testing-strategy.md)) cover most items;
  the **PR checklist** ([48](./48-repository-standards.md)) covers the rest with reviewer/CODEOWNERS
  sign-off.
- **Release gates** ([02 PRD §10](../01-product/02-prd.md)) aggregate the DoD at the release level.
- A change failing any applicable gate is **not done** and does not merge/ship.

## 5. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | DoD treated as optional | Unsafe/low-quality ship | Automated gates + required checklist + CODEOWNERS. |
| R-2 | Safety/a11y checked late | Rework or unsafe release | Pass/fail gates, red-team release-blocking. |
| R-3 | "Done" without evidence | False confidence | Verified-with-evidence principle. |

## Open questions

- **Per-change applicability** — a lightweight way to mark which gates apply to a given change without
  weakening the non-negotiables.
- **DoD automation coverage** — which checklist items can be fully automated vs. need human sign-off.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial approved Definition of Done: aggregated release gates for correctness, child safety (SAC), reach, accessibility, privacy/security, honesty, scale; doc-DoD for Phase 1; enforcement. | Head of Quality |
