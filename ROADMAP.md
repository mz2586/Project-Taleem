# Roadmap — Phase 6 (Platform → Pilot → Scale)

Status: **Plan only.** Companion to [MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md) (workstreams
WS1–WS16), [CRITICAL_PATH.md](CRITICAL_PATH.md), [PILOT_PLAN.md](PILOT_PLAN.md),
[RISK_REGISTER.md](RISK_REGISTER.md). Durations are **relative planning bands** in weeks (team-level),
not commitments; actual calendar time depends on staffing, legal timelines, and content velocity.

Sequencing principle: **governance and safety gate everything; content + audio are the long pole;
engineering is mostly parallel and largely already done.** Do not run children before WS1/WS2 close.

---

## 1. Phase structure (Phase 6 sub-phases)

| Sub-phase | Theme | Primary workstreams | Ends at |
| --- | --- | --- | --- |
| **6.0 Foundations & Gates** | Unblock legally + safely; scope content | WS1, WS2 (start), WS4 (start), WS5 (start), WS14 (start), WS15 | Governance sign-off + pilot content scoped |
| **6.1 Build (parallel)** | Build the human + child surfaces | WS3, WS6, WS7, WS8, WS12, WS13, WS9(a/b), WS10, WS11(tokens) | Surfaces feature-complete for pilot scope |
| **6.2 Content & Audio** | Author + narrate the pilot set | WS4, WS5 (bulk), WS10 (content review) | Pilot lessons published with audio (quality-gate green) |
| **6.3 Integration & Assurance** | Wire, audit, harden | WS11 (audit), WS13 (sync), WS14 (review/pentest), WS15, WS16 (QA) | All pilot journeys pass QA/a11y/safety/security |
| **6.4 Pilot Prep & Pilot 0** | Deploy, train, dry-run | WS16 (infra/ops/pilot prep), WS2 (staffing/drills) | Pilot 0 internal test passed; devices/site/staff/consent ready |
| **Pilot ladder** | Pilot 1 → 5 | operate + iterate + scale (per PILOT_PLAN) | National scale |

---

## 2. Timeline view (relative weeks; parallel tracks)

Bands are indicative and overlap; the **governance→safeguarding→content/audio→integration→pilot-prep**
chain sets the floor (see CRITICAL_PATH).

```text
 track \ week   0    4    8    12   16   20   24
 Governance     ██████████ (WS1, external sign-off gate)
 Safeguarding      ████████████ (WS2 build+staff+drills)
 Auth/Onboard        ██████ (WS3)
 Content           ████████████████████ (WS4 — long pole)
 Audio/Media           ████████████████ (WS5, trails WS4)
 Parent/Mentor/Admin    ████████████ (WS6/7/8)
 Portal/UX             ████████████ (WS12)
 Offline                  ██████████ (WS13; offline-lite for pilot 1)
 AI (pilot-scope)         ██████ (WS9 a/b)
 Security                ██████████ (WS14 + pentest)
 Eng hardening          ██████ (WS15)
 Accessibility               ████████ (WS11 audit after screens)
 Infra/Ops/QA               ████████████ (WS16)
 Pilot 0 (internal)                        ████ (gate)
 Pilot 1 (20–50)                               ▶ start
```

Reading it: engineering/content/audio/portals run **in parallel** from early; the **serial floor** is
Governance → Safeguarding operational → (content authored → audio recorded) → integration/QA →
Pilot 0 → Pilot 1.

---

## 3. Milestones & gates

| Milestone | Definition (exit) | Gates |
| --- | --- | --- |
| **M-Gov** | WS1 exit: DPIA signed, consent model, mandatory-reporting policy, external safety review passed, residency decided | Hard gate for any child data |
| **M-Safe** | WS2 exit: distress→human within SLA in a drill; reporting workflow tested; on-call staffed | Hard gate for any child use |
| **M-Content** | WS4/WS5 exit: pilot lesson set published, quality-gates green, audio verified, educational + child-safety review signed | Gate for a real learning pilot |
| **M-Surfaces** | WS3/6/7/8/12 exit: onboarding + student journeys + parent/mentor/admin minimal complete | Gate for supervised operation |
| **M-Assure** | WS11/14/15/16-QA exit: a11y audit, security review + pentest, durable sessions, load test, all pilot journeys pass | Gate for Pilot 0 |
| **M-Pilot0** | WS16 exit: internal end-to-end pilot passes; devices/site/staff/consent ready; kill-switch + runbooks tested | Gate for Pilot 1 |
| **M-Pilot1…5** | Per-pilot success criteria met (PILOT_PLAN) | Each gates the next |

---

## 4. Recommended build order (high level)

1. **Start now, in parallel:** WS1 (governance — longest external dependency), WS4 (content authoring
   — long pole), WS15 (durable sessions + N+1, pure engineering, no gate), WS5 audio pipeline setup,
   WS14 security hardening, WS3 auth build.
2. **As soon as WS1 policy drafts exist:** WS2 (safeguarding build + staffing + runbook), WS6/WS7/WS8
   (parent/mentor/admin), WS12 (portal completion), WS9(a/b), WS10.
3. **As content lands (WS4 per lesson):** WS5 records audio per lesson; WS13 packages offline.
4. **After screens land:** WS11 accessibility audit; WS16 QA passes (load, cross-device, safety,
   offline, security).
5. **Serial gate:** M-Gov + M-Safe + M-Content + M-Assure → **Pilot 0 (internal)** → **Pilot 1**.

Detailed dependency chain, parallelization, and the longest chain are in
[CRITICAL_PATH.md](CRITICAL_PATH.md).

---

## 5. Post-pilot scaling arc (beyond Pilot 1)

| Stage | Focus | Adds |
| --- | --- | --- |
| Pilot 2 (100) | Harden + iterate on Pilot-1 learnings | Full at-home offline (WS13 full); more content; refined pedagogy params (WS9/WS7 data) |
| Pilot 3 (500) | Multi-site operations | Admin suite; mentor scaling; regional model tier (WS9 LLM, if approved); infra scale-out (sessions/persistence) |
| Pilot 4 (5000) | Scale + cost | Sharding/partitioning proven under load; CDN for content/audio; cost model validated; SRE maturity |
| Pilot 5 (National) | Institutionalize | Partnerships (NCC/MoFEPT), multi-province content variants, national infra + support org |

The engineering scaling foundations (shard-by-`student_ref`, event-sourced analytics, schema-per-
context) already exist; the scaling work is operational maturity, content breadth, and validated
pedagogy — not a core redesign.
