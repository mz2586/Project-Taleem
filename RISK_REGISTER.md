# Risk Register — Phase 6 to Pilot

Status: **Plan only.** Companion to [MASTER_EXECUTION_PLAN.md](MASTER_EXECUTION_PLAN.md),
[ROADMAP.md](ROADMAP.md), [CRITICAL_PATH.md](CRITICAL_PATH.md), [PILOT_PLAN.md](PILOT_PLAN.md).
Top 50 remaining risks to taking Project Taleem from platform to a real school, ranked by **exposure
(Impact × Probability)**. Grounded in the CTO review, PHASE_4_2 / PHASE_5_5 reports, and the Product
Readiness Review.

**Scales.** Impact: **C**atastrophic / **H**igh / **M**edium / **L**ow. Probability: **H**igh /
**M**edium / **L**ow. Exposure ranks the register; category `[WSn]` links the owning workstream.
**Any child-safety risk is treated as top-priority regardless of computed exposure** — safety never
trades against schedule (Engineering Constitution).

---

## Tier 1 — Critical (address before any child touches the product)

| # | Risk | Impact | Prob | Category | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 1 | **A child in distress is not routed to a human** (no operational safeguarding live) | C | H | Safety [WS2] | Build + staff + drill escalation before Pilot 0; distress→human SLA; on-call safeguarding lead; block child use until M-Safe |
| 2 | **Child harmed via unsafe AI output** (generative tier enabled without review) | C | M | AI/Safety [WS9/WS10] | Pilot stays **templated/approved-content only**; no LLM to children until independent safety review; multi-layer safety per AI strategy |
| 3 | **Operating on children without lawful basis / valid consent** (governance unresolved) | C | H | Governance [WS1] | Close M-Gov: DPIA, lawful basis, per-child guardian consent, mandatory-reporting policy before Pilot 1 |
| 4 | **Child PII breach / leakage** | C | M | Security [WS14] | Deny-by-default PDP, IDOR guards, encryption, residency, pentest, minimal data, no child PII in tokens/logs |
| 5 | **Grooming/predator contact through any interaction surface** | C | L | Safety [WS2/WS10] | No open child-to-child/adult messaging in MVP; mentor-mediated only; monitored + audited channels; safeguarding review |
| 6 | **Fabricated / pedagogically wrong content taught to children** | C | M | Content [WS4/WS10] | Educational review + child-safety review sign-off per lesson (M-Content); no placeholder content in pilot; SME authorship |
| 7 | **Accessibility exclusion** (disabled / low-literacy children can't use it) | H | M | Accessibility [WS11] | Audio-first, WCAG 2.2 AA audit, screen-reader/RTL testing before pilot; test with disabled participants |
| 8 | **No Urdu audio → non-readers can't learn** (B4) | H | H | Media [WS5] | Record + QA Urdu narration for all pilot lessons; audio-first is a gate (M-Content) |
| 9 | **Child-safe identity/auth not built** (dev stub only, B3) | H | H | Auth [WS3] | Build age-appropriate onboarding + guardian-linked identity; retire dev JWT stub; production JWKS (FD-14) |
| 10 | **Independent child-safety review fails late**, invalidating design | C | L | Governance [WS1] | Engage reviewer early in 6.0; iterate against findings before build hardens; treat as zero-float gate |

## Tier 2 — High

| # | Risk | Impact | Prob | Category | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 11 | **Governance timeline slips** (external legal/DPIA), slipping everything | H | H | Governance [WS1] | Start day 0, escalate, own the critical path; parallelize all buildable work into its shadow |
| 12 | **Content authoring underestimated** (long pole overruns) | H | H | Content [WS4] | Staff multiple authors in parallel; scope pilot to one subject/1–2 grades; track velocity weekly |
| 13 | **Offline sync data loss / double-count** on intermittent networks | H | M | Offline [WS13] | Idempotent sync, conflict resolution, transactional outbox; offline-lite for Pilot 1, full offline proven in Pilot 2 |
| 14 | **Parents/mentors have no trustworthy visibility** (B7) → no trust | H | H | Parent/Mentor [WS6/WS7] | Ship minimal parent (progress/attendance/wellbeing) + mentor (assigned learners/escalation) for pilot |
| 15 | **Durable sessions incomplete** → progress lost on restart/deploy | H | M | Engineering [WS15] | Persist session state; recover mid-session; load/chaos test before pilot |
| 16 | **Pilot content too thin** to show learning gains | H | M | Content [WS4] | Scope a coherent multi-lesson learning arc, not isolated samples; define mastery-gain success metric |
| 17 | **Security review/pentest finds late blockers** | H | M | Security [WS14] | Start hardening day 0; continuous review; pentest with buffer before M-Assure |
| 18 | **Mentor supply/training insufficient** for safe ratios | H | M | Operations [WS16/WS2] | Recruit + train mentors early; keep Pilot-1 ratio tight (≈1:10); training pipeline before scale |
| 19 | **Kill-switch / rollback unproven** in an incident | H | L | Ops [WS16] | Build + test kill-switch and rollback in Pilot 0; runbooks drilled |
| 20 | **Data residency / cross-border non-compliance** | H | M | Governance/Sec [WS1/WS14] | Decide residency in M-Gov; host in-region; contractually bind processors |
| 21 | **Consent workflow fails / incomplete for some children** | H | M | Governance [WS1] | Enforce consent-before-enrolment in WS8 admin; no session without verified consent |
| 22 | **QA convergence bottleneck** (a11y + load + safety + security all land at once) | H | M | QA [WS16/WS11] | Run audits/tests continuously through 6.1–6.3; no big-bang final pass |
| 23 | **Detection signals (distress/abuse) miss or false-negative** | H | M | AI/Safety [WS9] | Conservative thresholds favoring escalation; human-in-loop; tune on Pilot-0 drills; never sole gate |
| 24 | **Device/connectivity reality at site worse than assumed** | H | M | Ops [WS16] | Provided devices + MDM + guaranteed Wi-Fi for Pilot 1; measure real conditions before at-home (Pilot 2) |
| 25 | **Admin/enrolment (cohorts, mentor assignment) not ready** | H | M | Admin [WS8] | Build minimal admin for pilot scale; consent + assignment flows first |

## Tier 3 — Medium

| # | Risk | Impact | Prob | Category | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 26 | **Pedagogy parameters (BKT/spacing) mis-tuned** for real children | M | M | AI [WS9] | Validate on Pilot-1 data before Pilot 2; conservative defaults; human-mediated promotion |
| 27 | **Child disengagement / low retention** | M | H | UX [WS12] | Age-appropriate engagement (streaks/achievements), short sessions, measure return rate |
| 28 | **N+1 / performance regressions under load** | M | M | Engineering [WS15] | Fix known N+1; load test; read replicas/cache before Pilot 3 |
| 29 | **Learning treated as high-stakes** (auto-promotion pressure) | M | M | Governance [WS1] | Keep promotion human-mediated; learning signals are formative, not gatekeeping (MVP non-negotiable) |
| 30 | **Portal journeys incomplete** (edge/error/empty states) | M | M | UX [WS12] | Complete journeys per STUDENT_UI_FLOW; no dead ends; error/empty-state coverage in QA |
| 31 | **Audio production quality/consistency** poor | M | M | Media [WS5] | Voice guidelines, QA per clip, consistent narrators, pronunciation review |
| 32 | **Notification system spams or fails to re-engage** | M | M | UX [WS12] | Rate-limit; purposeful nudges (return-next-day); measure effect |
| 33 | **Backup/DR untested** → recovery fails when needed | M | L | Infra [WS16] | Configure + exercise backups/PITR in Pilot 0; RPO/RTO per doc 56 |
| 34 | **Monitoring/alerting gaps** → incidents unseen | M | M | Ops [WS16] | Observability + on-call alerting live before Pilot 0; safety + system dashboards |
| 35 | **Analytics under-instrumented** → can't measure pilot success | M | M | QA/Analytics [WS16] | Instrument mastery-gain, engagement, safety-incident, a11y metrics before Pilot 1 |
| 36 | **Content localization/dialect mismatch** (Urdu register for children) | M | M | Content [WS4] | Child-appropriate language review; regional review before scale |
| 37 | **Mentor tooling insufficient** to act on escalations quickly | M | M | Mentor [WS7] | Escalation queue + learner context in mentor portal; drill response time |
| 38 | **Cost-per-learner unknown / unsustainable** | M | M | Finance/Infra [WS16] | Track cost from Pilot 3; validate unit economics before Pilot 4 |
| 39 | **Cross-device/browser inconsistencies** | M | M | QA [WS16] | Cross-device matrix testing; target real pilot devices |
| 40 | **Scope creep** beyond MVP delays pilot | M | H | Program [all] | Enforce MVP boundary (§2 excluded list); defer non-essential to post-pilot |

## Tier 4 — Lower (monitor; can be accepted for pilot)

| # | Risk | Impact | Prob | Category | Mitigation |
| --- | --- | --- | --- | --- | --- |
| 41 | **Key-person / bus-factor** on core engine knowledge | M | M | Program | Documentation (50 blueprint docs), pairing, cross-training |
| 42 | **Local-only git → single machine data-loss** of project history | M | L | Ops | Encrypted local backups of the repo; user owns remote decision (no remote per instruction) |
| 43 | **Third-party dependency vuln / supply chain** | M | L | Security [WS14] | Pinned tooling, dependency scanning, minimal deps |
| 44 | **Curriculum drift from national standards** | M | L | Content [WS4] | Map lessons to NCC objectives; periodic alignment review |
| 45 | **Partnership/regulatory dependency for scale (Pilot 5)** | M | L | Governance [WS1] | Begin gov-relations early; MoU as accelerator, not blocker for early pilots |
| 46 | **Reputational harm from any early incident** | H | L | Program | Slow, supervised ramp; zero-unhandled-safety target; transparent incident handling |
| 47 | **Facilitator/site-coordinator turnover** mid-pilot | L | M | Ops [WS16] | Redundant coverage; documented runbooks; training pipeline |
| 48 | **Over-reliance on AI vs human teaching** erodes learning | M | L | Pedagogy [WS9] | AI assists, humans teach; mentor-mediated model; measure outcomes |
| 49 | **Documentation drifts from implementation** | L | M | Program | Docs-as-code gates already green; update docs with every change |
| 50 | **Feature-flag / config error exposes unfinished surface** | M | L | Eng [WS15] | Deny-by-default flags; governance-gated features off by default; release checklist |

---

## Register management

- **Owners:** each row's `[WSn]` maps to the workstream owner in MASTER_EXECUTION_PLAN; safety/governance
  rows escalate to the safeguarding lead + program lead.
- **Cadence:** re-score weekly through Phase 6; re-validate the whole register at each pilot gate
  (assumptions true at 50 learners are re-checked at 500 and 5,000).
- **Hard rule:** any **Tier 1 safety/governance risk open ⇒ NO-GO** for the next pilot rung, regardless
  of other progress. Safety and child wellbeing outrank schedule, always.
