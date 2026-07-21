# Student Experience (Phase 5 — Design)

The complete learner-facing experience design: the journey from sign-in to lesson completion for a
child (KG–10) on a low-end Android device, 3G/offline, Urdu-first, over the built `/v1/learning` API.

Status: **design milestone only.** No frontend code. Child-facing implementation is blocked by the
Phase-1.5 governance gate and by approval of this design.

## Documents

1. [STUDENT_EXPERIENCE.md](STUDENT_EXPERIENCE.md) — the anchor: personas, principles, the complete
   journey, and per-screen specs (Purpose · Journey · Components · Data · APIs · A11y · Acceptance)
   for all 12 areas (dashboard, session, navigation, profile, offline, accessibility, mobile-first,
   design system, APIs, state, errors, security).
2. [STUDENT_PORTAL_ARCHITECTURE.md](STUDENT_PORTAL_ARCHITECTURE.md) — how it's built: PWA rendering,
   state management, offline (service worker + IndexedDB + sync engine), API client, auth, error
   handling, security, performance budgets.
3. [STUDENT_UI_FLOW.md](STUDENT_UI_FLOW.md) — screen map, navigation graph, journeys, and the session
   UI mapped to the real session state machine + decision engine.
4. [STUDENT_API_REQUIREMENTS.md](STUDENT_API_REQUIREMENTS.md) — existing vs new endpoints, each with
   shape, auth, and offline behavior.
5. [STUDENT_COMPONENT_CATALOG.md](STUDENT_COMPONENT_CATALOG.md) — every component (atoms → templates)
   with props, states, and an accessibility/governance contract.

## Non-negotiables threaded through every document

- Audio-first, Urdu-first, RTL · WCAG 2.2 AA · offline-first · mobile-first (Android-Go/3G).
- Child-safe by construction: the AI renders only approved content; no PII from the child; a
  wellbeing/help path is always reachable; a learner reaches only their own data (IDOR-guarded).
- One clear next action, driven by the decision engine; encouraging, never punitive.
