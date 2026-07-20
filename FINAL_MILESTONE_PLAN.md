# Final Milestone Plan — Project Taleem

| | |
|---|---|
| **Supersedes** | [docs/08-delivery/45-milestone-plan.md](./docs/08-delivery/45-milestone-plan.md) (extends M0–M7 into the 10-phase structure) |
| **Companions** | [FINAL_ROADMAP.md](./FINAL_ROADMAP.md) · [EXECUTIVE_REVIEW.md](./EXECUTIVE_REVIEW.md) |
| **Date** | 2026-07-20 |

## Principles

- Every milestone has a **binary exit criterion** (met / not met — no partial credit) and a **quality
  gate**. Dates are assigned when team + funding are confirmed; sequence is fixed, cadence is not.
- **Status legend:** ✅ done · ▶ next · ☐ future.

## Completed to date

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **M0 · Foundation blueprint** | 50 docs + 2 ADRs authored; docs CI green | Authoring brief conformance | ✅ |
| **M0.5 · Architecture review + remediation** | 97 findings; 9 remediation artifacts; 12 docs corrected | Independent adversarial review | ✅ |
| **M1 · Walking skeleton (verified)** | 57 tests / 96% coverage; build+docker+compose green; Eng readiness 91 | [BUILD_VERIFICATION_REPORT](./BUILD_VERIFICATION_REPORT.md) | ✅ |

## Phase 1.5 — Governance & Validation

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **G1 · Lawful basis + DPIA** | Counsel opinion issued; DPIA complete + fed back into 11–15/24 | Legal sign-off (EV-01/03) | ▶ |
| **G2 · Residency + infra ADRs** | Cloud/region + KMS + broker + vector-store decided (FD-02/03/14) | Architecture ADR + counsel | ▶ |
| **G3 · Child-safety operations** | 24/7 safeguarding staffed + funded; numeric SLAs set; mandatory-reporting policy signed | Safeguarding sign-off (EV-02) | ▶ |
| **G4 · Unaccompanied-minor pathway** | Legal-validated no-guardian enrolment design | Legal sign-off | ▶ |
| **G5 · Android Go device validation** | Urdu+Nastaʿlīq+audio proven within budget on a real Go handset | On-device lab (EV-06) | ▶ |
| **G6 · AI unit-economics spike** | Measured $/student against the LLM-as-last-resort design | Cost gate (FD-07) | ▶ |
| **G7 · Independent external review** | Security + safeguarding + privacy reviews passed | EV-04/07/08 | ▶ |
| **Phase-1.5 exit** | **Zero open Critical findings**; all above ✅ | [RISK_REMEDIATION §5](./RISK_REMEDIATION_PLAN.md) | ☐ |

## Phase 2 — Core Platform

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P2.1 · Persistence + migrations** | Sharded Postgres + Alembic + RLS live in staging; migration rehearsed on realistic-skew data | DoD + migration gate | ☐ |
| **P2.2 · Event backbone** | Outbox/CDC → broker → warehouse; schema registry + CI compat green | Fitness functions | ☐ |
| **P2.3 · Identity & Access** | Guardian-anchored identity w/ JWKS+KMS (no child onboarding) | ASVS L2 on spine | ☐ |
| **P2.4 · Observability live** | OTel→collector + SLO dashboards incl. safeguarding-escalation SLO | Alerting game-day | ☐ |
| **P2.5 · Scale L2 + DR drill** | 100k-concurrent synthetic load held; timed prod-scale restore passed | Load L2 + DR gate | ☐ |
| **Phase-2 exit** | Spine runs at L2 with DR proven; fitness functions green | DoD | ☐ |

## Phase 3 — Curriculum Engine

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P3.1 · SNC ingested (KG–G5)** | Partner-sourced SNC KG–G5 loaded as versioned data | Standards-coverage report clean | ☐ |
| **P3.2 · Prerequisite graph** | Acyclic objective DAG authored; remediation routing works | Curriculum review | ☐ |
| **P3.3 · Content-QA + tracks** | Bias/age/neutrality rubric + Islamiat↔Ethics track; sign-off | Content-safety sign-off | ☐ |
| **Phase-3 exit** | KG–G5 curriculum validated, mapped, mastery-criteria machine-readable | Psychometric + safety sign-off | ☐ |

## Phase 4 — AI Teaching Engine

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P4.1 · LLM-last-resort pipeline** | Cache/RAG → in-region model → frontier escalation, behind the gateway | Cost + residency gate | ☐ |
| **P4.2 · Safety guardrails + crisis** | Two-sided guardrails; deterministic crisis templates; transcript carve-out | SACs | ☐ |
| **P4.3 · Urdu red-team eval** | Numeric child-safety bar met in Urdu/Roman-Urdu; continuous canary live | AI red-team (release-blocking) | ☐ |
| **Phase-4 exit** | Red-team + groundedness + cost + residency gates all green; independent AI-safety review passed | EV-08 | ☐ |

## Phase 5 — Student Portal

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P5.1 · Lesson runtime + resume** | Content-block lesson runs + resumes on-device | DoD | ☐ |
| **P5.2 · Offline day-pack + sync** | Full lesson completed offline on 3G; idempotent sync (built on M1 engine) | Offline replay gate | ☐ |
| **P5.3 · Non-reader onboarding + a11y** | Audio-guided first-run; AA+RTL audited; child usability-tested | EV-05/06 + usability | ☐ |
| **Phase-5 exit** | Child completes lesson→AI→formative→resume **offline on a real Go device within budget** | SACs + AA + data-budget | ☐ |

## Phase 6 — Parent & Mentor Portals

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P6.1 · Guardian Portal** | Consent/revoke + report card + safety concern + discreet exit | Privacy + safeguarding | ☐ |
| **P6.2 · Mentor Portal** | AI escalation actioned within SLA; moderated messaging; vetting enforced | Grooming-vector red-team | ☐ |
| **Phase-6 exit** | Human safeguarding loop operational end-to-end within SLA | Escalation-SLA SLO live | ☐ |

## Phase 7 — Assessment & Analytics

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P7.1 · Assessment + mentor summative** | Immutable attempts + server scoring; mentor-mediated summative | Psychometric sign-off | ☐ |
| **P7.2 · Verifiable report card** | Signed, version-pinned report card derivable from attempts | Honesty/integrity gate | ☐ |
| **P7.3 · North-star analytics** | North-star event flows (offline-safe, deduped); no PII in analytics | Privacy scan | ☐ |
| **Phase-7 exit** | Fair, valid, verifiable assessment + honest impact metrics | Psychometric + privacy | ☐ |

## Phase 8 — Pilot Programme

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P8.1 · Pilot live (thin complete school)** | Consented cohort learning KG–G5 Urdu on real devices; 24/7 safeguarding live | All release gates ([PRD §10](./docs/01-product/02-prd.md)) | ☐ |
| **P8.2 · Evaluation** | Pre-registered outcomes: mastery + reach + trust + unit economics measured | Ethics/evaluation sign-off | ☐ |
| **Phase-8 exit** | End-to-end learning proven; **zero unresolved safety incidents**; lawful; go/no-go passed | Independent safeguarding monitor | ☐ |

## Phase 9 — Production Launch

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P9.1 · Full school KG–G10** | Full loop incl. human grading + promotion + transcripts | Full DoD + release gates | ☐ |
| **P9.2 · Scale L3 + multi-region DR** | L3 load held; cross-region DR proven | Load L3 + DR | ☐ |
| **P9.3 · Assurance program** | Recurring pentest + disclosure policy live | External audit | ☐ |
| **Phase-9 exit** | Full school live, hardened, AA across portals, ASVS L2 across surfaces | Full DoD | ☐ |

## Phase 10 — National Scale

| Milestone | Binary exit criterion | Gate | Status |
|---|---|---|---|
| **P10.1 · 1M load validation** | Core-path SLOs held at 1M-enrolled / ~150k-concurrent load | 1M load gate | ☐ |
| **P10.2 · Recognized credential** | Board/government MoU; verifiable, recognized transcript | Recognition secured | ☐ |
| **P10.3 · Additional languages** | Sindhi/Pashto/Punjabi/Balochi live via localization pipeline | Per-language safety+a11y evals | ☐ |
| **Phase-10 exit** | Serving toward 1M sustainably with a recognized credential | Cost-per-student guardrail | ☐ |

---

## Milestone governance

- A milestone is **not done** until its binary criterion and quality gate are both green — no exceptions
  for schedule.
- Child-safety and lawfulness gates apply to **every** milestone, not only the safety-named ones.
- Each completed milestone re-scores the affected [Executive Review](./EXECUTIVE_REVIEW.md) categories, so
  the 70/100 is a living number that must climb toward ≥90 before "world-class" is claimed.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | 10-phase milestone plan with binary exit criteria + quality gates; M0/M0.5/M1 marked done; Phase-1.5 G1–G7 next. Supersedes doc 45's M0–M7. | Executive panel |
