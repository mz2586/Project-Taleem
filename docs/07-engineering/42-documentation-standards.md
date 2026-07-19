# 42 · Documentation Standards

| | |
|---|---|
| **Document ID** | 42 |
| **Owner** | Principal Engineer / Docs Guild |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [Authoring Brief §8](../_meta/authoring-brief.md) · [37 CI/CD](./37-cicd-pipeline.md) · [48 Repository Standards](./48-repository-standards.md) · [CONTRIBUTING](../../CONTRIBUTING.md) |

## Purpose

This document codifies **how Taleem documentation is written and maintained** so that ~50 blueprint
documents (and future code docs) read as one coherent work. It formalises the format seeded in
[Authoring Brief §8](../_meta/authoring-brief.md) and the CI checks that keep docs lint-clean and
link-valid.

## Scope

In scope: document format, structure, diagram/table conventions, cross-referencing, tone, and CI doc
governance. Out of scope: content of any specific doc, and code-comment style ([41 Coding Standards](./41-coding-standards.md)).

---

## 1. Principles

1. **One coherent work** — every doc follows the same format and canonical vocabulary ([Authoring Brief](../_meta/authoring-brief.md)).
2. **Decision-dense, no fluff** — state the decision, rationale, alternatives, trade-offs; no marketing
   language; no fabricated statistics (label planning assumptions).
3. **Diagram + table over prose** for structure, flows, schemas, state machines.
4. **Cross-referenced, never duplicated** — link sibling docs by relative path; single source of truth
   per topic.
5. **CI-validated** — docs pass markdownlint, link-check, and Mermaid validation ([37](./37-cicd-pipeline.md)).

## 2. Required document structure

Every blueprint doc has ([Authoring Brief §8](../_meta/authoring-brief.md)):

1. **H1 title** `NN · Title`.
2. **Metadata block** — Document ID, Owner, Status (`Draft`/`Reviewed`/`Approved`), Last updated, Related.
3. **Purpose** (2–4 sentences) and **Scope / Out-of-scope**.
4. Body — numbered sections, tables, and Mermaid diagrams.
5. **Open questions** and **Change log** at the end.

## 3. Conventions

| Element | Convention |
|---|---|
| **Headings** | Sentence case; numbered top-level sections. |
| **Diagrams** | ```mermaid fenced blocks; validated in CI ([37](./37-cicd-pipeline.md)). |
| **Tables** | For structured data, matrices, decisions. |
| **Cross-refs** | Relative paths (`../cluster/NN-name.md`); use canonical filenames from the [README](../../README.md). |
| **Requirements** | RFC-2119 MUST/SHOULD/MAY; stable IDs. |
| **Assumptions** | Label "(planning assumption)"; never fabricate numbers. |
| **Vocabulary** | Canonical role/context names only ([Authoring Brief §2/§5](../_meta/authoring-brief.md)). |
| **ADRs** | MADR-style in `docs/02-architecture/adr/ADR-NNNN-title.md`. |

## 4. Cross-referencing & no-duplication

- A topic has **one owning document**; others link to it. If two docs disagree, resolve against the
  owner and the [Authoring Brief](../_meta/authoring-brief.md); to change a fixed decision, raise an
  **ADR** — never silently diverge.
- **Canonical filenames** (from the [README](../../README.md) index) are the only valid link targets;
  the CI link-check fails on broken/renamed references.

## 5. CI documentation governance

Per [37 CI/CD](./37-cicd-pipeline.md) and [.markdownlint-cli2.jsonc](../../.markdownlint-cli2.jsonc):

- **markdownlint** — style consistency.
- **Link-check** (offline, incl. fragments) — every relative cross-reference resolves.
- **Mermaid validation** — every diagram compiles.

Green CI on all three is the objective completeness signal for the blueprint.

## 6. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | Docs drift out of sync | Confusion, wrong decisions | Single-owner topics, cross-refs, ADRs for changes. |
| R-2 | Broken links | Blueprint incoherent / red CI | Canonical filenames + link-check gate. |
| R-3 | Duplication | Contradictions | No-duplication rule; link don't copy. |
| R-4 | Fabricated stats | Loss of trust | "Planning assumption" labelling; no invented numbers. |

## Open questions

- **Rendered docs site** (e.g. static site) for non-engineer stakeholders — post-Phase-1.
- **Doc status workflow** (Draft → Reviewed → Approved) tooling.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial documentation standards: required structure, conventions, no-duplication/cross-ref rules, CI doc governance (markdownlint/link-check/mermaid). | Docs Guild |
