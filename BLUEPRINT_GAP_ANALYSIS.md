# Blueprint Gap Analysis — Project Taleem

| | |
|---|---|
| **Companion to** | [ARCHITECTURE_REVIEW.md](./ARCHITECTURE_REVIEW.md) · [RISK_REMEDIATION_PLAN.md](./RISK_REMEDIATION_PLAN.md) · [FINAL_RECOMMENDATIONS.md](./FINAL_RECOMMENDATIONS.md) |
| **Date** | 2026-07-19 |
| **Purpose** | Enumerate what a world-class blueprint should contain but the current one lacks — missing documents/artifacts, undefined decisions, and open-questions wired into release gates — mapped to the findings they close. |

## 1. How to read this

Three gap classes:

- **§2 Missing artifacts** — documents/specs a production-grade child-platform blueprint must have that
  are *referenced but absent* or *never created*.
- **§3 Blocking open decisions** — decisions parked in "Open Questions" that actually gate design, cost,
  legality, or safety and cannot be deferred.
- **§4 Open-questions wired into MUSTs** — release-blocking requirements whose acceptance criteria
  depend on something still undefined (so the gate is untestable today).

Each row maps to the finding IDs in [ARCHITECTURE_REVIEW.md](./ARCHITECTURE_REVIEW.md) and a remediation
owner. "Authorable now" = can be drafted as a blueprint doc with labeled planning assumptions.
"Decision-gated" = needs a human/legal/business/infra decision first.

## 2. Missing artifacts (the blueprint's biggest gaps)

| # | Missing artifact | Referenced by | Closes | Severity | Status |
|---|---|---|---|---|---|
| G-01 | **Threat Model** (per-boundary STRIDE + attacker-goal/attack trees; household-as-adversary) | 13 §2 | AR-C-02, AR-H-12 | Critical | Authorable now |
| G-02 | **DPIA** (Data Protection Impact Assessment) | 14 §11 | AR-C-08, AR-H-23 | Critical | Decision-gated (legal) |
| G-03 | **Mandatory-Reporting / External-Referral Policy** (Pakistani channels, do-no-harm) | 15 §5 | AR-C-05 | Critical | Decision-gated (legal) |
| G-04 | **Safeguarding Escalation & Crisis-Response Protocol** (numeric SLAs, 24/7, deterministic holding templates) | 15 §5/§9; 24 §7 | AR-C-04, AR-C-22 | Critical | Authorable now (values need clinical/staffing sign-off) |
| G-05 | **Incident Response Plan** (SEV taxonomy, IC roles, comms, safeguarding IR, regulator/guardian notification) | 13 §10; 38 §5 | AR-C-22 | Critical | Authorable now |
| G-06 | **Capacity Model** (enrolled vs concurrent; QPS/TPS/WS/events/AI-turns/storage; per-node budgets; sharding plan) | 04 SCAL-03; 08 §9; 36 | AR-C-11, AR-H-25/26/27/32 | Critical | Authorable now (infra confirms) |
| G-07 | **Cost Model / FinOps** (per-student envelope: AI+infra+media+SMS; guardrails; spend breakers) | 04 §14; 43 PR-4/PR-11 | AR-C-12, AR-H-29/31 | Critical | Authorable now (business confirms) |
| G-08 | **Business-Continuity / DR Plan** (RPO/RTO by AZ-vs-region; PITR; DR region; tested restore) | 35 §7 | AR-C-13, AR-H-34 | Critical | Decision-gated (infra) |
| G-09 | **Data-Retention & Deletion Schedule** (numeric per class + legal basis + automated expiry) | 14 §6; 39 §5 | AR-H-20/21 | High | Authorable now (legal confirms) |
| G-10 | **Mastery Definition & Assessment-Validity Framework** (threshold, calibration, reliability, standard-setting, prerequisite DAG) | 21 §3; 23 §5 | AR-C-14/15/16 | Critical | Authorable now (psychometric review) |
| G-11 | **Unaccompanied-Minor / No-Guardian Enrolment Pathway** (persona, journey, FR, legal) | 05; 06; 11 §3.2 | AR-C-01 | Critical | Decision-gated (legal) |
| G-12 | **Design-Token File + Contrast Matrix** (full ramps, computed ratios, high-contrast map, focus ratios) | 18 §2; 16 §3 | AR-C-18, AR-H (a11y) | Critical | Authorable now |
| G-13 | **AI Red-Team Methodology** (corpus, category coverage, numeric bar, Urdu coverage, cadence, owner) | 24 §10; 40 §5 | AR-H-16/17/18/33 | High | Authorable now |
| G-14 | **Localization Pipeline Spec** (TMS, ICU messages, per-language font/shaping/TTS/audio, pseudo-loc) | brief §3; 21 §1.4 | AR-H-08, AR-C-19 | High | Authorable now |
| G-15 | **Audio-Production Pipeline + Urdu TTS decision** (recorded-audio coverage; on-device TTS; Android Go test) | 16 §7 | AR-C-19 | Critical | Decision-gated (device test) |
| G-16 | **Content-QA & Bias-Review Process** (rubric, reviewer roles, minority/gender checklist, AI-content review) | 21 §6 | AR-H (curriculum) | High | Authorable now |
| G-17 | **Shared-Device Assessment Integrity / Identity-Assurance Model** | 23 §7 | AR-C-17, AR-H-03 | Critical | Authorable now |
| G-18 | **Item-Bank Sizing + Authoring/AI-Generation QA Pipeline** (throughput vs KG–10 scope) | 23 §2 | AR-C-16 | Critical | Authorable now |
| G-19 | **SNC Standards Dataset + Provincial-Variance Encoding Plan** (worked example) | 21 §4 | AR-H (curriculum) | High | Decision-gated (content) |
| G-20 | **Religious-Education Track Model** (Islamiat ↔ Ethics/Akhlaqiat) + minority-inclusion policy | 21 §1.5/§8 | AR-C-20 | Critical | Authorable now |
| G-21 | **Early-Literacy (Reading-Acquisition) Pedagogy** + audio-crutch fade-out | 21; 22 | AR-C (curriculum) | High | Authorable now |
| G-22 | **On-Call & Escalation Policy** (separate eng + T&S rotations, 24/7, ack/escalation timeouts) | 38 §5 | AR-C-22 | Critical | Decision-gated (staffing) |
| G-23 | **Staffing / Human-Capacity Model** (mentor + Safety-Officer headcount from ratio + queue math) | 28 OQ; 43 PR-5 | AR-C-04/22 | Critical | Decision-gated (business) |
| G-24 | **SLO/SLA + Error-Budget Policy doc** (multi-burn-rate; safety-pipeline SLO; budget-exhaustion consequence) | 38 §4 | AR-H (ops) | High | Authorable now |
| G-25 | **Chaos/Resilience & DR Test Plan** (fault injection, degraded-mode, failover/restore drills) | 40 | AR-H-34 | High | Authorable now |
| G-26 | **Runbook Catalog + Template** ("runbook per alert" asserted, none exist) | 38 §5; 04 MNT-05 | AR-H (ops) | High | Authorable now |
| G-27 | **Event Schema Registry Spec + concrete schemas** (format, compatibility, envelope, examples) | 08 §6.3; 10 §9 | AR-M (arch) | Medium | Decision-gated (tech) |
| G-28 | **Realtime (WebSocket) Scale Design** (conns/pod, backplane, degradation, cost) | 08 §8 | AR-H-25 | High | Authorable now |
| G-29 | **Message-Monitoring-at-Scale Design** (grooming/abuse classification precision/recall + review sizing) | 28 §5; 30 | AR-C-22, AR-H-01 | Critical | Authorable now |
| G-30 | **Verifiable-Credential / Report-Card Signing Design** (digital signature + verification endpoint) | 29 §3 | AR-M (reporting) | Medium | Authorable now |
| G-31 | **Non-Reader Onboarding / Enrolment / Consent Flow** (audio+photo-guided) | 16 §7; 20 §2 | AR-H (UX/a11y) | High | Authorable now |
| G-32 | **Security-Assurance Program** (pentest cadence, external safety/privacy audit, vuln-disclosure policy) | 43 OQ; 48 §5 | AR-L (security) | Low | Decision-gated (procurement) |
| G-33 | **Usability-Testing-with-Children & Disability-User-Testing Plan** | 16 | AR-H (a11y) | High | Authorable now |
| G-34 | **Data-Processing / Processor Register** (per-processor data classes, purpose, residency, erasure) | 14 §8 | AR-H-21 | High | Authorable now |
| G-35 | **Math-Rendering + RTL/Bidi Spec** (mixed Urdu/expression content) | 16 §6; 22 | AR-M (i18n) | Medium | Authorable now |

**Total: 35 missing artifacts** — of which **14 are Critical**. Nine are decision-gated (legal,
staffing, infra, procurement, content); the remaining 26 are authorable now as blueprint documents.

## 3. Blocking open decisions (parked in "Open Questions", actually gating)

| # | Decision | Parked in | Blocks | Owner |
|---|---|---|---|---|
| D-01 | **Cloud provider + data-residency posture** ("close to Pakistan" ≠ "in Pakistan"; PDPB may require in-country) | 36 OQ; 08 §9.6 | Capacity, cost, DR, LLM residency, managed-service strategy | Infra + Legal (ADR) |
| D-02 | **Lawful basis for core + safety processing** (consent-as-precondition likely invalid) | 14 §2/§3 | All child-data processing legality | Privacy Counsel |
| D-03 | **LLM inference residency + zero-retention guarantee** | 14 O-3; 24 | Cross-border child-disclosure exposure | Infra + Legal |
| D-04 | **Mastery threshold** | 21; 23 | North-star, promotion, report cards | Learning Science |
| D-05 | **Attendance semantics** (async/offline school) | 02; 03 | FR-ENR-003, KPIs | Product |
| D-06 | **Safeguarding SLA numbers + 24/7 model** | 15; 38 | Crisis response, staffing, monitoring | Safeguarding + Ops |
| D-07 | **Message broker** (Kafka/Redpanda vs JetStream vs Rabbit) | 08 OQ | Event backbone, analytics, realtime | Architecture (ADR) |
| D-08 | **Vector store for RAG** (Meilisearch hybrid vs dedicated) | 08; 24 | AI grounding scale | Architecture (ADR) |
| D-09 | **Sharding key + strategy** | 09 | Postgres write ceiling to 1M | Architecture (ADR) |
| D-10 | **SMS/WhatsApp provider(s) + PTA registration** | 30 OQ | Enrolment/consent/safety notices | Ops + Business |
| D-11 | **Per-student AI cost envelope** | 04; 24 | Sustainability, tiering targets | Business + AI |
| D-12 | **Numeral system per pedagogical context** | 16 OQ | Early-math learning content | Learning Science |
| D-13 | **KMS/HSM topology + per-data-class keys** | 13 OQ | At-rest encryption, offline cache, crypto-shredding | Security (ADR) |
| D-14 | **"Out-of-school at enrolment" flag** (lawful, non-stigmatising) | 14 O-4; 31 | North-star denominator | DPO + Product |

## 4. Open questions wired into release-blocking MUSTs (untestable gates)

These are the most dangerous: a MUST whose acceptance criterion depends on an undefined value cannot
gate a release, so the gate is currently theatre.

| MUST | Depends on (undefined) | Effect |
|---|---|---|
| FR-ENR-003 (attendance) MVP | Attendance semantics (D-05) | Acceptance says "per the agreed rule (see Open Questions)" — untestable |
| FR-CUR-006 / FR-ASM-007 (mastery/north-star) MVP | Mastery threshold (D-04) | North-star unmeasurable at MVP; report cards uncomputable |
| FR-TNS-003/005 (triage/escalation SLA) MVP | Safeguarding SLA (D-06) | "100% within SLA" with no SLA value — unenforceable safety gate |
| FR-IDN-001 (consent) MVP | Lawful basis / assisted-consent legality (D-02) | Release-blocking MUST whose legality is admittedly open |
| SAC-4 (DoD safety gate) | Escalation SLA (D-06) | Definition-of-Done gate references an undefined number |
| PERF-05 (AI latency) gate | Prototype baseline (AR-H-04) | Target set by aspiration, unattainable with mandated pipeline |
| M5 MVP exit / M7 scale exit | Capacity/concurrency model (D-01, G-06) | "SLOs held under load" untestable without a target |

## 5. Gap-closure sequencing

The gaps are not equal. Recommended order (detail in [RISK_REMEDIATION_PLAN.md](./RISK_REMEDIATION_PLAN.md)):

1. **Legal/clinical preconditions** (cannot build without): D-02, D-03, G-02, G-03, G-11, D-06 →
   these gate whether the platform can lawfully and safely exist.
2. **Safety mechanisms** (authorable now): G-01, G-04, G-05, G-17, G-20, G-29, AR-C-03/06/09/10 fixes.
3. **Feasibility proof** (authorable now): G-06 capacity, G-07 cost, G-08 DR, D-09 sharding, D-01 infra.
4. **Teach-and-certify honesty** (authorable now): G-10, G-12, G-15, G-18, D-04, D-12.
5. **Operational readiness** (authorable now): G-05/22/23/24/25/26, G-09, G-34.
6. Remaining High/Medium/Low.

---

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial gap analysis: 35 missing artifacts (14 Critical), 14 blocking open decisions, 7 open-questions-wired-into-MUSTs, closure sequencing. | External Principal Engineer (review) |
