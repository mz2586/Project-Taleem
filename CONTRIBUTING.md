# Contributing to Project Taleem

Thank you for helping build a school for children who have none. Because the stakes are children's
education and safety, our contribution bar is deliberately high.

## Ground rules (non-negotiable)

1. **Child safety first.** Any change touching AI output, user content, messaging, or data must pass
   the child-safety review in the [Definition of Done](docs/07-engineering/50-definition-of-done.md).
   When in doubt, escalate to a Safety Officer.
2. **Design for the bottom of the curve.** Every user-facing change must meet the low-bandwidth and
   low-end-device budgets in [04 Non-Functional Requirements](docs/01-product/04-non-functional-requirements.md).
3. **Accessible & Urdu-first.** WCAG 2.2 AA and complete RTL support are acceptance criteria, not
   nice-to-haves. See [16 Accessibility](docs/04-design/16-accessibility-standards.md).
4. **Privacy by design.** Collect the least child data necessary. See
   [14 Privacy](docs/03-security-privacy/14-privacy-model.md).

## Before you start

- Read the **[Authoring Brief](docs/_meta/authoring-brief.md)** — the single source of truth for
  names, scope, and fixed technical decisions.
- Read the relevant specification document(s) for the area you're touching.
- For any decision that contradicts a fixed decision in the brief, open an **ADR**
  (see [docs/02-architecture/adr/](docs/02-architecture/adr/)) — do not diverge silently.

## Phase 1 (current): documentation

We are in **Phase 1 — Foundation**. The deliverables are the 50 blueprint documents indexed in the
[README](README.md). Production code does **not** begin until the blueprint is approved.

Documentation contributions must:

- Follow the metadata block + format defined in
  [42 Documentation Standards](docs/07-engineering/42-documentation-standards.md) and seeded in the
  [Authoring Brief §8](docs/_meta/authoring-brief.md).
- Use Mermaid for diagrams, tables for structured data, and cross-reference sibling docs by relative
  path.
- Pass `markdownlint` and the link checker in CI.

## When code begins (Phase 1+)

Follow [41 Coding Standards](docs/07-engineering/41-coding-standards.md),
[48 Repository Standards](docs/07-engineering/48-repository-standards.md), and
[49 Development Workflow](docs/07-engineering/49-development-workflow.md). Every PR must satisfy the
[Definition of Done](docs/07-engineering/50-definition-of-done.md).

## Commit & PR conventions

- **Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:` …).
- Small, focused PRs. Link the backlog item (`EP-NN` / `ST-NNN`).
- All CI checks green; required reviews per [CODEOWNERS](.github/CODEOWNERS).

## Code of conduct

Be kind, be rigorous, and remember there is a child on the other end of every decision.
