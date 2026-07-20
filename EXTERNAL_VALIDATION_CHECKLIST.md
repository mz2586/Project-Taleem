# External Validation Checklist — Project Taleem

| | |
|---|---|
| **Track** | B — External Validation (independent third-party sign-off) |
| **Date** | 2026-07-19 |
| **Purpose** | A child-safety platform must not self-certify. This checklist enumerates the independent reviews required before real children are onboarded, what each must cover, its inputs, and its exit criteria. Runs in parallel with Track A (decisions) and Track C (engineering). |
| **Source** | [ARCHITECTURE_REVIEW.md](./ARCHITECTURE_REVIEW.md) · [FOUNDER_DECISIONS.md](./FOUNDER_DECISIONS.md) |

## Legend

**Status:** ☐ Not started · ◐ In progress · ☑ Passed · ✗ Failed/Blocked.
**Gate:** `Phase 1.5` = before build · `Pre-MVP` = before pilot with children.

---

## Overview

| ID | Validation | Reviewer type | Gate | Status |
|---|---|---|---|---|
| EV-01 | Legal review (lawful basis, consent, residency) | External data-protection counsel (PK + intl.) | Phase 1.5 | ☐ |
| EV-02 | Child-safeguarding review | Accredited child-protection / safeguarding body | Phase 1.5 | ☐ |
| EV-03 | Privacy review + **DPIA** | External DPO / privacy firm | Phase 1.5 | ☐ |
| EV-04 | Security review (pentest + threat-model) | Independent security firm | Phase 1.5 | ☐ |
| EV-05 | Accessibility audit (WCAG 2.2 AA + COGA) | Accredited accessibility auditor (RTL/Urdu) | Pre-MVP | ☐ |
| EV-06 | Android Go real-device validation | Engineering + field testers (Pakistan) | Pre-MVP | ☐ |
| EV-07 | Independent architecture review | External principal architect | Phase 1.5 | ☐ |
| EV-08 | AI-safety / red-team review | External AI-safety evaluators (Urdu-capable) | Phase 1.5 | ☐ |
| EV-09 | Pedagogical / psychometric review | Independent learning scientist | Pre-MVP | ☐ |

---

## EV-01 · Legal review

- **Must cover.** Lawful basis per processing purpose (FD-01); validity of guardian + institutional +
  unaccompanied-minor consent (FD-05); data-residency obligations under PDPB/PECA (FD-02/FD-03);
  cross-border transfer basis for LLM inference; mandatory-reporting obligations (FD-04); age of digital
  consent; retention/erasure lawfulness.
- **Inputs.** [14 Privacy](./docs/03-security-privacy/14-privacy-model.md), [11 Auth §3](./docs/03-security-privacy/11-authentication-strategy.md),
  [57 Retention](./docs/03-security-privacy/57-data-retention-schedule.md), FOUNDER_DECISIONS FD-01/02/03/04/05.
- **Exit criteria.** Written opinion confirming a valid lawful basis for every processing purpose; consent
  UI/flow signed off; residency posture legally cleared; **zero unresolved legal Criticals.**

## EV-02 · Child-safeguarding review

- **Must cover.** Crisis-response protocol + SLAs + 24/7 staffing (FD-06); mandatory-reporting/referral
  do-no-harm (FD-04); household-adversary controls ([51 Threat Model](./docs/03-security-privacy/51-threat-model.md));
  transcript-confidentiality carve-out; mentor vetting standard (AR-H-19); grooming-prevention (bounded
  monitored messaging); age-appropriate design; peer-interaction scope.
- **Inputs.** [15 Child Safety](./docs/03-security-privacy/15-child-safety-framework.md), [52 Crisis Protocol](./docs/03-security-privacy/52-safeguarding-crisis-protocol.md),
  [53 Incident Response](./docs/07-engineering/53-incident-response-plan.md).
- **Exit criteria.** Independent sign-off that the design + staffing + referral pathways are adequate to
  build for real children; red-team of the household-adversary countermeasures passed.

## EV-03 · Privacy review + DPIA

- **Must cover.** A full **Data Protection Impact Assessment** (declared required, was absent — AR-H-23);
  data-map + processor register; minimisation; subject rights + erasure completeness (crypto-shred across
  backups/processors/devices); analytics PII posture; the "out-of-school" flag (FD-16).
- **Inputs.** [14 Privacy](./docs/03-security-privacy/14-privacy-model.md), [57 Retention](./docs/03-security-privacy/57-data-retention-schedule.md),
  [31 Analytics](./docs/06-portals/31-analytics-platform.md).
- **Exit criteria.** Completed DPIA whose residual-risk findings are fed back into the specs; sign-off that
  privacy-by-design is met.

## EV-04 · Security review (pentest + threat-model validation)

- **Must cover.** Validate [51 Threat Model](./docs/03-security-privacy/51-threat-model.md) (per-boundary
  STRIDE + attacker trees); auth/session/token; PDP fail-closed + tenancy isolation; crypto/key mgmt
  (FD-14); supply chain; the walking-skeleton scaffold (Track C) for ASVS L2 posture; offline token theft.
- **Inputs.** [11](./docs/03-security-privacy/11-authentication-strategy.md)–[13](./docs/03-security-privacy/13-security-model.md),
  [51](./docs/03-security-privacy/51-threat-model.md), Track C code.
- **Exit criteria.** Pentest report with zero unresolved criticals/highs; threat model validated; ASVS L2
  gap-list closed or scheduled.

## EV-05 · Accessibility audit

- **Must cover.** WCAG 2.2 AA on the core path **and** WCAG COGA cognitive-accessibility guidance (beyond
  AA, for child users — AR-L); RTL-complete Nastaʿlīq; screen-reader operability in Urdu; the verified
  contrast matrix ([59 Token Values](./docs/04-design/59-design-token-values.md)); non-reader onboarding;
  captions/transcripts on audio; multi-modal degrade (audio-first vs icon-first reconciliation).
- **Inputs.** [16 Accessibility](./docs/04-design/16-accessibility-standards.md), [59](./docs/04-design/59-design-token-values.md),
  Track C design system.
- **Exit criteria.** Auditor confirms AA + COGA conformance on the core path with real assistive tech.

## EV-06 · Android Go real-device validation

- **Must cover.** Urdu audio/read-aloud availability + Nastaʿlīq rendering/perf on a real low-end handset
  (AR-C-19); the ≤500KB lesson budget with audio + font; offline pack + sync on 3G; WebAuthn/software-
  keystore population (AR-H-13); picture-PIN UX with children; battery/power behaviour.
- **Inputs.** [59](./docs/04-design/59-design-token-values.md), [33 Offline](./docs/02-architecture/33-offline-architecture.md),
  [04 NFR](./docs/01-product/04-non-functional-requirements.md), Track C PWA + offline-sync prototype.
- **Exit criteria.** Measured evidence on real hardware that audio-first + Urdu + offline work within
  budget; assumptions confirmed or specs revised.

## EV-07 · Independent architecture review

- **Must cover.** Validate the capacity model + sharding ([54](./docs/02-architecture/54-capacity-and-scale-model.md));
  DR/BC ([56](./docs/02-architecture/56-bcdr-plan.md)); the modulith→services boundaries; event backbone;
  the Track C walking skeleton against the blueprint.
- **Inputs.** [08](./docs/02-architecture/08-system-architecture.md)–[10](./docs/02-architecture/10-api-design.md),
  [54](./docs/02-architecture/54-capacity-and-scale-model.md), [56](./docs/02-architecture/56-bcdr-plan.md), Track C.
- **Exit criteria.** Independent confirmation that the design + skeleton can reach 1M without re-platforming.

## EV-08 · AI-safety / red-team review

- **Must cover.** The red-team methodology + numeric bar; **Urdu/Roman-Urdu/code-switch** safety-classifier
  recall (AR-H-18); prompt-injection resistance (AR-H-15); tier-safety parity + provider-drift canary
  (AR-H-16/17); deterministic crisis templates; no-training enforceability.
- **Inputs.** [24 AI Teacher](./docs/05-education/24-ai-teacher-specification.md), [15 §3](./docs/03-security-privacy/15-child-safety-framework.md),
  [40 Testing](./docs/07-engineering/40-testing-strategy.md).
- **Exit criteria.** External evaluators confirm the eval set + thresholds + Urdu coverage are adequate and
  the pipeline resists the tested attacks.

## EV-09 · Pedagogical / psychometric review

- **Must cover.** Mastery threshold (FD-09); assessment validity/reliability + item-bank ([58](./docs/05-education/58-mastery-and-assessment-validity.md));
  prerequisite graph; SNC standards mapping fidelity; early-literacy pedagogy; cultural/gender/religion
  neutrality + minority inclusion (Ethics track).
- **Inputs.** [21](./docs/05-education/21-curriculum-engine.md)–[23](./docs/05-education/23-assessment-engine.md),
  [58](./docs/05-education/58-mastery-and-assessment-validity.md).
- **Exit criteria.** Learning scientist confirms the assessment measures what it claims and the pedagogy is
  sound for the target learners.

---

## Aggregate exit gate

Real children may be onboarded only when **EV-01 through EV-09 are ☑**, all **Phase-1.5 founder decisions**
([FOUNDER_DECISIONS.md](./FOUNDER_DECISIONS.md)) are closed, and the [RISK_REMEDIATION_PLAN §5](./RISK_REMEDIATION_PLAN.md)
Phase-2 gate shows **zero open Critical findings**.

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial external-validation checklist: 9 independent reviews with coverage, inputs, and exit criteria; aggregate onboarding gate. | Review team |
