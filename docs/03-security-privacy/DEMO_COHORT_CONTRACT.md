# Demo Cohort Contract

**Status:** binding · **Adopted:** 2026-10-24 · **Owner:** Engineering

The owner explores the **real** deployed application (`taleem-web-phi.vercel.app` +
`taleem-api.vercel.app`, `TALEEM_ENV=production`) with designated synthetic demo accounts. There
is no separate demo site, database or environment. This contract defines the narrowly scoped
mechanism that makes that safe.

## 1. Principles

- Production stays production. No safeguard is relaxed globally, and the generic fixture seeder
  still refuses production.
- **Two-way isolation.** Real learners never see demo content. Demo accounts never see real
  learners' data (they never could: access is relationship-scoped).
- Demo content is labelled as demo everywhere it appears and is never presented as reviewed
  curriculum.
- Demo accounts are ordinary guardian and learner accounts with **no** extra privileges.

## 2. Accounts

- Guardian and learner accounts carry `cohort`: `""` (real) or `"demo"`. The flag is set
  **only** by the demo seeder, through an application-service method that is not exposed by any
  HTTP route. A learner's cohort is its guardian's. No API can set, clear or change it.
- The seeder flags exactly the reserved synthetic address `taleem.demo.guardian@example.org`
  (and its second synthetic family, `taleem.demo.family.b@example.org`). `example.org` is
  reserved and cannot belong to a real person. It adopts an existing account with that address
  rather than recreating it.
- Access tokens for demo accounts carry the claim `cohort: "demo"`. The claim is informational
  for the UI (a "Demo account" badge). Authorization reads the cohort from the account, never from
  the claim.

## 3. Content

- A lesson may set `metadata.audience = "demo"` (default `""` = everyone). This is included in the
  content hash.
- Every learner-facing read is filtered by the reader's cohort: catalogue, sessions
  (`:next`/`:teach`/`:answer`/`:hint`), placement, offline packages and manifests, homework, report
  cards and the teacher catalogue. A real-cohort reader **never** receives an `audience = "demo"`
  lesson or item. A demo reader sees demo lessons and any real published lessons.
- Demo lessons are built from the AI drafts. Every title starts with
  `[DEMO · unreviewed AI draft]` in both locales. Their review stages are recorded with the note
  `SYNTHETIC DEMO APPROVAL - not a human review`.
- Assets that do not exist yet (diagrams, offline package ids, recorded audio) use refs prefixed
  `demo-placeholder/`. The audio resolver accepts such a ref **only** for a lesson whose audience
  is `demo`, in every environment including production. A real lesson with a `demo-placeholder/`
  ref fails its gates.

## 4. Records

Learning evidence, sessions, placement, homework submissions and marks, and report cards for demo
learners are created through the application services with deterministic, fixed historical
timestamps (2026-09-01 to 2026-10-20). They live in the same tables as real records but belong only
to demo-cohort learners, so relationship-scoped access keeps them invisible to everyone else.

## 5. Seeding

The Vercel build step runs the demo-cohort seeder when `TALEEM_DEMO_SEED=1`. It is allowed in
production **because** it writes only demo-flagged accounts, `audience = "demo"` content and their
records. It is idempotent: re-running changes nothing. It prints counts only, never secrets.

## 6. Removal

`python -m taleem_core.tools.demo_cohort --erase` deletes every demo-cohort account (through the
privacy erasure path) and unpublishes every `audience = "demo"` lesson. Before any real child is
admitted, the demo cohort is either erased or kept under this same isolation.

## Change Log

| Date | Change | Author |
| --- | --- | --- |
| 2026-10-24 | Adopted: in-app demo cohort replaces the separate demo deployment. | Engineering |
