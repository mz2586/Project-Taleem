# Web (PWA) — developer guide

Project Taleem's frontend, **M1 scaffold**. Urdu-first, RTL, offline-capable PWA (Next.js App Router).
Governance-safe: demonstrates the design system + component contract + offline shell only. No child data,
no product features.

## Student Portal (Phase 5 — governance-safe scaffold)

`app/student/*` implements the core learner journey (Today → Session → Profile/Progress) over the real
`/v1/learning` API, per `docs/12-student-experience/`. **Governance-safe:** a synthetic pseudonymous
learner + a dev-stub bearer token (`NEXT_PUBLIC_DEV_STUDENT_TOKEN`); **no real child identity, no PII,
no production deployment.** Child-safe production auth, safeguarding integration, and the secondary
screens (which need new backend APIs) are **blocked by the Phase-1.5 governance gate**. Set
`NEXT_PUBLIC_API_URL` + `NEXT_PUBLIC_DEV_STUDENT_TOKEN` for local dev against a running core-api.

## What's here

```text
apps/web/
├── app/                    Next.js App Router (layout.tsx, page.tsx) — RTL/Urdu-first
│   └── student/            student portal (today, session, profile, progress, subjects, homework)
├── components/student/     student UI (AppShell, BottomNav, ReadAloud, ui primitives)
├── lib/student/            learning API client + types + dev auth config
├── design-system/
│   ├── tokens.css          verified tokens from docs/59 (computed WCAG ratios; Sun constraint; 18px Urdu floor)
│   ├── Button.tsx          token-only primitive; ≥44px; icon+text
│   └── ReadAloud.tsx       the mandated low-literacy read-aloud primitive (audit AR-C-19)
├── public/
│   ├── manifest.webmanifest  PWA manifest (RTL, ur)
│   └── sw.js                 offline app-shell service worker (no generative AI offline)
├── next.config.mjs         security headers, minimal client JS
└── tsconfig.json           strict TS
```

## Run (needs Node 20 + `npm install`, i.e. network)

```bash
cd apps/web
npm install
npm run typecheck
npm run dev      # http://localhost:3000
npm run build
```

> Note: in the review sandbox `npm install` was not executed (no registry access), so the web build is
> **structured but not run here**. The CI `web-build` job builds it on every push.

## Deliberately excluded

Student app screens, enrolment, child accounts, AI chat, safeguarding — all Phase 2, gated on governance
([FOUNDER_DECISIONS.md](../../FOUNDER_DECISIONS.md)).
