# 48 · Repository Standards

| | |
|---|---|
| **Document ID** | 48 |
| **Owner** | Principal Engineer / Head of Platform Engineering |
| **Status** | Draft (Phase 1) |
| **Last updated** | 2026-07-19 |
| **Related** | [47 Folder Structure](./47-folder-structure.md) · [49 Development Workflow](./49-development-workflow.md) · [37 CI/CD](./37-cicd-pipeline.md) · [50 Definition of Done](./50-definition-of-done.md) · [CONTRIBUTING](../../CONTRIBUTING.md) · [13 Security](../03-security-privacy/13-security-model.md) |

## Purpose

This document defines **how the Taleem repository is governed**: branching, commits, PRs, reviews,
protected branches, ownership, and the CI checks that gate every change. It makes enterprise-grade
quality the default path.

## Scope

In scope: repo conventions (branching, commits, PRs, CODEOWNERS, protections). Out of scope: folder
layout ([47](./47-folder-structure.md)), the step-by-step dev loop ([49](./49-development-workflow.md)),
and pipeline internals ([37](./37-cicd-pipeline.md)).

---

## 1. Principles

1. **Small, focused, reviewed changes** — every change is a PR; nothing lands unreviewed
   ([CONTRIBUTING](../../CONTRIBUTING.md)).
2. **Green CI is mandatory** — no merge with failing checks.
3. **Attributable & auditable history** — Conventional Commits, signed where required.
4. **Ownership is explicit** — CODEOWNERS gate sensitive areas ([.github/CODEOWNERS](../../.github/CODEOWNERS)).

## 2. Branching & commits

- **Trunk-based** with short-lived feature branches off `main`; no long-lived divergent branches.
- **Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` …) ([CONTRIBUTING](../../CONTRIBUTING.md)).
- Link the backlog item (`EP-NN`/`ST-NNN`, [46 Backlog](../08-delivery/46-project-backlog.md)).

## 3. Pull requests & review

- **PR template** ([.github/pull_request_template.md](../../.github/pull_request_template.md)) captures
  intent, testing, and the safety/privacy/a11y checklist ([50 DoD](./50-definition-of-done.md)).
- **Required reviews per CODEOWNERS**; changes touching AI/safety/privacy require the relevant owner.
- Small PRs; all CI checks green before merge.

## 4. Protected `main`

- No direct pushes; PR + passing checks + required approvals only.
- **Required status checks:** markdownlint, link-check, mermaid (docs); plus (when code begins) tests,
  coverage, security scans, accessibility, bundle budgets ([37](./37-cicd-pipeline.md), [40](./40-testing-strategy.md)).
- Linear, auditable history.

## 5. Security & supply chain

- **Secret-scanning + SCA + image scanning** gates ([13 §8](../03-security-privacy/13-security-model.md)).
- Dependencies pinned/reviewed; least-privilege CI; signed artifacts/provenance ([13 §8](../03-security-privacy/13-security-model.md)).
- No secrets in the repo — enforced by scanning ([04 NFR SEC-05](../01-product/04-non-functional-requirements.md)).

## 6. Repository hygiene

- `.gitignore`, `LICENSE`, `README`, `CONTRIBUTING` maintained (present).
- Docs governance per [42](./42-documentation-standards.md); code layout per [47](./47-folder-structure.md).

## Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R-1 | Unreviewed change lands | Quality/safety regression | Protected main + required reviews. |
| R-2 | Secret committed | Credential leak | Secret-scanning gate + rotation. |
| R-3 | Ownership gaps on sensitive code | Unsafe change slips | CODEOWNERS on AI/safety/privacy. |

## Open questions

- **Monorepo tooling** and per-package CI targeting ([47](./47-folder-structure.md)).
- **Commit signing** enforcement scope.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial repository standards: trunk-based branching, Conventional Commits, PR/review, protected main + required checks, supply-chain gates, hygiene. | Principal Engineer |
