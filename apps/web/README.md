# Web (PWA) — developer guide

Project Taleem's frontend, **M1 scaffold**. Urdu-first, RTL, offline-capable PWA (Next.js App Router).
Governance-safe: demonstrates the design system + component contract + offline shell only. No child data,
no product features.

## What's here

```text
apps/web/
├── app/                    Next.js App Router (layout.tsx, page.tsx) — RTL/Urdu-first
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
