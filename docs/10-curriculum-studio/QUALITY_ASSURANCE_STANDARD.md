# Quality Assurance Standard

| | |
|---|---|
| **Status** | Phase 3 · The 9 quality gates every lesson must pass · Related: [AUTHORING_WORKFLOW](./AUTHORING_WORKFLOW.md) · [LESSON_STANDARD](./LESSON_STANDARD.md) |
| **Date** | 2026-07-20 |

## 1. The nine quality gates

Every lesson must pass **all nine** before publish. Each gate returns `pass|fail` + findings; a fail
returns the lesson to Draft. Gates are a mix of **automated checks** and **human review** ([AUTHORING_WORKFLOW §2](./AUTHORING_WORKFLOW.md)).

| # | Gate | Auto/Human | Checks |
|---|---|---|---|
| 1 | **Educational Review** | Human | Pedagogically sound: scaffolding, formative-first, mastery-based, misconception-aware |
| 2 | **Curriculum Alignment** | Auto+Human | Every outcome maps to a public NCP SLO `standard_code`; prerequisite DAG acyclic; coverage report clean |
| 3 | **Technical Accuracy** | Human (subject expert) | Facts, worked examples, and answers are correct |
| 4 | **Language Review** | Human | Urdu + English correctness, tone, register; translation parity ([TRANSLATION_STANDARD](./TRANSLATION_STANDARD.md)) |
| 5 | **Accessibility** | Auto+Human | WCAG 2.2 AA; alt text; audio present; contrast; RTL ([ACCESSIBILITY_STANDARD](./ACCESSIBILITY_STANDARD.md)) |
| 6 | **AI Safety** | Human (Safety Officer) | AI teaching object safe; `forbidden_behaviours`/`escalation_rules` present; no unsafe content ([AI_TEACHING_STANDARD](./AI_TEACHING_STANDARD.md), [15](../03-security-privacy/15-child-safety-framework.md)) |
| 7 | **Age Appropriateness** | Human | Content, tone, examples fit the grade band |
| 8 | **Readability** | Auto+Human | Sentence length, vocabulary load, grade-appropriate ([CONTENT_STYLE_GUIDE](./CONTENT_STYLE_GUIDE.md)) |
| 9 | **Performance** | Auto | Offline package + media within data budget; renders on the reference device ([04 NFR DATA](../01-product/04-non-functional-requirements.md)) |

## 2. Automated pre-checks (run on `:validate`, before human review)

The Studio validator runs the machine-checkable parts of gates 2, 5, 8, 9 plus the structural
[LESSON_STANDARD §2](./LESSON_STANDARD.md) checks and the **provenance gate**. Human reviewers only see
lessons that pass the automated pre-checks — reviewer time is spent on judgment, not on catching missing
fields.

| Automated check | Gate |
|---|---|
| All required fields present + typed | Structural |
| Provenance clean (original / permitted; no prohibited source) | Provenance |
| Every outcome has a `standard_code`; DAG acyclic | 2 |
| Alt text on every visual; audio present; contrast tokens valid | 5 |
| Readability metric within grade band | 8 |
| Offline package + media within data budget | 9 |
| AI teaching object complete; forbidden/escalation non-empty | 6 (pre) |

## 3. Gate result record

```json
{ "gate": "accessibility", "result": "pass|fail",
  "mode": "auto|human", "reviewer_role": "a11y_specialist",
  "findings": [{ "severity": "blocker|major|minor", "message": "...", "field": "..." }],
  "at": "..." }
```

A gate with any `blocker` finding is a **fail**. Results attach to the lesson and to its published version
(audit).

## 4. Governance

- **No gate may be skipped or self-approved.** Publish is blocked until all nine are green.
- Gate definitions are versioned; changing a gate is a reviewed change.
- Sampled **post-publish audits** re-check a fraction of published lessons.
- A published lesson found defective is rolled back ([AUTHORING_WORKFLOW §4](./AUTHORING_WORKFLOW.md)).

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | QA standard: 9 quality gates (auto/human), automated pre-checks, gate-result record, governance (no skip/self-approve, post-publish audit). | Curriculum Studio |
