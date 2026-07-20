# Founder Decisions — Project Taleem

| | |
|---|---|
| **Track** | A — Founder Decisions (human approval required) |
| **Date** | 2026-07-19 |
| **Purpose** | Every decision that only a human (founder / counsel / clinician / business) can make, packaged for a clear yes/no. Engineering (Track C) and external validation (Track B) proceed in parallel; **Phase 2 build unblocks the moment the "Required by" decisions land.** |
| **Source** | [ARCHITECTURE_REVIEW.md](./ARCHITECTURE_REVIEW.md) · [BLUEPRINT_GAP_ANALYSIS.md](./BLUEPRINT_GAP_ANALYSIS.md) · [RISK_REMEDIATION_PLAN.md](./RISK_REMEDIATION_PLAN.md) |

## How to use this

Each decision has: **Background · Options · Recommendation · Consequences · Required by**. Record the
choice + date + approver in the "Decision" line. The **Phase-2 gate** (RISK_REMEDIATION_PLAN §5) requires
every decision marked **Required by: Phase 1.5** to be closed before build.

**Legend — Required by:** `Phase 1.5` = blocks build · `Pre-MVP` = blocks first pilot with children ·
`Pre-v1` = blocks full launch.

---

## Priority summary

| ID | Decision | Required by | Owner |
|---|---|---|---|
| FD-01 | Lawful basis for child-data processing | **Phase 1.5** | Privacy Counsel |
| FD-02 | Cloud provider + data-residency posture | **Phase 1.5** | Founder + Infra + Legal |
| FD-03 | LLM inference residency + zero-retention | **Phase 1.5** | Founder + Legal |
| FD-04 | Mandatory-reporting / external-referral policy | **Phase 1.5** | Counsel + Safeguarding |
| FD-05 | Unaccompanied-minor enrolment legality | **Phase 1.5** | Legal |
| FD-06 | Safeguarding SLA + 24/7 staffing + funding | **Phase 1.5** | Founder + Safeguarding |
| FD-07 | Per-student AI cost envelope + funding model | **Phase 1.5** | Founder + CFO |
| FD-08 | Commission independent external safety/security review | **Phase 1.5** | Founder |
| FD-09 | Mastery threshold sign-off | Pre-MVP | Learning Science |
| FD-10 | Attendance semantics | Pre-MVP | Product |
| FD-11 | Message broker technology | Phase 1.5 (unblocks eng) | Architecture |
| FD-12 | Vector store for RAG | Pre-MVP | Architecture |
| FD-13 | SMS/WhatsApp provider + PTA registration | Pre-MVP | Ops + Business |
| FD-14 | KMS/HSM topology | Phase 1.5 (unblocks eng) | Security |
| FD-15 | Numeral system per pedagogical context | Pre-MVP | Learning Science |
| FD-16 | "Out-of-school at enrolment" flag capture | Pre-MVP | DPO + Product |
| FD-17 | Report-card credential recognition | Pre-v1 | Business |

---

## FD-01 · Lawful basis for child-data processing

- **Background.** The blueprint makes consent a precondition of schooling ([14 §3](./docs/03-security-privacy/14-privacy-model.md)). Under the GDPR-K baseline the project adopts, consent that is a precondition is generally not "freely given" and is **invalid** — putting the lawful basis for *all* high-risk processing (child free-text through an LLM, safety monitoring) at risk (AR-C-08).
- **Options.** (a) Keep forced consent (legally fragile). (b) **Re-ground core-learning + safety-monitoring on a non-consent basis** (legal obligation / vital interests / substantial-public-interest) and reserve *consent* for genuinely optional scopes. (c) Obtain a specific legal opinion tailoring bases per processing purpose.
- **Recommendation.** (b) + (c): separate lawful bases per purpose, confirmed by a written counsel opinion; consent only for optional scopes (engagement messaging, media uploads).
- **Consequences.** If not fixed, every enrolled child's data may be unlawfully processed — a fatal compliance defect and a program-ending risk. Fixing it changes the consent UI and the DPIA (Track B).
- **Required by.** **Phase 1.5.** — **Decision:** _____ (approver / date)

## FD-02 · Cloud provider + data-residency posture

- **Background.** No hyperscaler region exists *inside* Pakistan (nearest: UAE/India/Singapore). Pakistan's PDPB (draft) may require in-country storage of child data. The blueprint treats "close to Pakistan" as if residency is solved (AR-C-07, D-01). This decision gates capacity, cost, DR, and the managed-service strategy.
- **Options.** (a) UAE/Bahrain hyperscaler region with a documented cross-border-transfer legal basis. (b) In-country Pakistani IaaS/colo (Tier-3 DC) with self-managed Postgres/K8s if the law mandates residency. (c) Hybrid: child PII in-country, non-PII in a nearby hyperscaler.
- **Recommendation.** Obtain the PDPB residency determination first (couples to FD-01/FD-03); default to (c) hybrid if residency is mandated, else (a) with a lawful-transfer basis.
- **Consequences.** If the law mandates residency and it's discovered post-build, the entire managed-service architecture must be re-platformed. Choosing early lets Track C target the right infra.
- **Required by.** **Phase 1.5.** — **Decision:** _____

## FD-03 · LLM inference residency + zero-retention

- **Background.** Children's most sensitive utterances (abuse/self-harm disclosures) are sent to a foreign LLM region *before* they can be classified (AR-C-07). "No-training" is contractual only, with no technical enforcement.
- **Options.** (a) Region-pinned inference near Pakistan with a zero-retention endpoint + no-training contract + audit rights. (b) In-region/self-hosted small model for routine (Haiku-tier) + distress classification, escalating only non-sensitive turns cross-border. (c) Status quo (unacceptable for children).
- **Recommendation.** (b) for distress classification + the holding response in-region; (a) for the rest, under a technically-enforced zero-retention contract; never forward pre-classified-C4 text out of region.
- **Consequences.** Determines the AI provider contract, cost (FD-07), and whether the residency posture (FD-02) holds. Blocks the production AI path (already excluded from Track C).
- **Required by.** **Phase 1.5.** — **Decision:** _____

## FD-04 · Mandatory-reporting / external-referral policy

- **Background.** The platform detects abuse disclosures but has **nowhere safe to route them** — the referenced safeguarding-escalation policy did not exist (AR-C-05). A naïve referral can itself endanger a child in the Pakistani context.
- **Options.** (a) Author a policy naming concrete provincial child-protection / law-enforcement channels with a do-no-harm test and dual-control authorization. (b) Partner with an established Pakistani child-protection NGO to receive referrals. (c) Both.
- **Recommendation.** (c). [52 Crisis Protocol](./docs/03-security-privacy/52-safeguarding-crisis-protocol.md) scaffolds the decision structure; counsel + safeguarding fill in channels and obligations.
- **Consequences.** Without it, detection is negligent. It shapes the crisis protocol, IR plan, and staffing.
- **Required by.** **Phase 1.5.** — **Decision:** _____

## FD-05 · Unaccompanied-minor enrolment legality

- **Background.** The target population *is* guardian-less children (orphans, displaced, street children), but enrolment requires a guardian consent record — structurally excluding them (AR-C-01). Institutional guardianship's legal sufficiency under PDPB is open.
- **Options.** (a) Institutional/NGO guardianship with independent attestation + two-person control. (b) Verified-adult attestation with a heightened safety envelope. (c) Supervised self-enrolment above a defined age with safeguarding review.
- **Recommendation.** (a) as the primary path, legally validated; (b)/(c) as documented alternatives per context — all with the household-adversary controls ([51 Threat Model](./docs/03-security-privacy/51-threat-model.md)).
- **Consequences.** Without it the mission's core users are excluded; with it, a new persona/journey/FR (FR-IDN-008) and legal analysis are needed.
- **Required by.** **Phase 1.5.** — **Decision:** _____

## FD-06 · Safeguarding SLA + 24/7 staffing + funding

- **Background.** Crisis response needs numeric SLAs and 24/7 human coverage ([52](./docs/03-security-privacy/52-safeguarding-crisis-protocol.md)); the SLA values and staffing are unfunded planning assumptions (AR-C-04/22).
- **Options.** (a) Adopt the proposed tiered SLAs (T0 ≤ 5 min 24/7) and fund the roster. (b) Narrow the initial cohort so a smaller safeguarding team can hold 24/7. (c) Contract a 24/7 safeguarding partner.
- **Recommendation.** (b) at pilot + (c) for after-hours coverage; commit funding; **gate cohort growth on safeguarding-responder capacity** — never enrol a child you cannot protect 24/7.
- **Consequences.** Determines staffing cost, cohort-growth rate, and whether the safety promise is real.
- **Required by.** **Phase 1.5.** — **Decision:** _____

## FD-07 · Per-student AI cost envelope + funding model

- **Background.** The dominant variable cost (frontier-LLM inference) had an open envelope while Vision claimed "marginal cost approaching zero" (AR-C-12). For a sponsorship-funded platform this is existential.
- **Options.** (a) Set a hard per-student monthly AI budget enforced in the gateway ([55 Cost Model](./docs/08-delivery/55-cost-model.md)) with degrade-to-cached on exhaustion. (b) Negotiate provider pricing/committed-use. (c) Both.
- **Recommendation.** (c): adopt the [55](./docs/08-delivery/55-cost-model.md) envelope + tier-mix targets as a design constraint; validate against real pricing; set the sponsorship ask from it.
- **Consequences.** Determines sustainability and the sponsorship pitch; unbounded AI cost is a financial DoS.
- **Required by.** **Phase 1.5.** — **Decision:** _____

## FD-08 · Commission independent external safety/security review

- **Background.** A child-safety platform must not self-certify its safety (AR-C-24). The Phase-2 gate requires an independent review of the remediated blueprint.
- **Options.** (a) Independent pentest + safeguarding audit + privacy/DPIA review by accredited third parties. (b) Advisory board only (insufficient).
- **Recommendation.** (a). See Track B [EXTERNAL_VALIDATION_CHECKLIST.md](./EXTERNAL_VALIDATION_CHECKLIST.md).
- **Consequences.** Cost + timeline, but non-negotiable for credibility with UNICEF/enterprise partners.
- **Required by.** **Phase 1.5.** — **Decision:** _____

## FD-09 · Mastery threshold sign-off

- **Background.** "Mastered" — the north-star's unit — was undefined (AR-C-14). [58 Mastery & Validity](./docs/05-education/58-mastery-and-assessment-validity.md) proposes a v1 rule (accuracy + spaced retention on distinct items).
- **Options.** (a) Adopt the proposed rule pending pilot calibration. (b) Commission a psychometric review first.
- **Recommendation.** (a) + (b): adopt provisionally; validate on pilot data with a psychometrician.
- **Consequences.** Sets the north-star, promotion, and report-card semantics.
- **Required by.** **Pre-MVP.** — **Decision:** _____

## FD-10 · Attendance semantics

- **Background.** What counts as "attending" in an async, offline-capable school is undefined yet wired into FR-ENR-003 (AR-C-23).
- **Options.** (a) Lesson-engagement-based (≥1 meaningful lesson interaction/day). (b) Time-based. (c) Objective-progress-based.
- **Recommendation.** (a), tuned in pilot; keep it offline-queue-safe.
- **Consequences.** Affects report cards, KPIs, and guardian expectations.
- **Required by.** **Pre-MVP.** — **Decision:** _____

## FD-11 · Message broker technology

- **Background.** The event backbone + analytics + realtime depend on a broker; it was an open question ([08 OQ](./docs/02-architecture/08-system-architecture.md), D-07). Blocks safe parallel context development.
- **Options.** (a) Kafka/Redpanda (log-based; best for analytics fan-out + CDC). (b) NATS JetStream (lighter ops). (c) RabbitMQ (simplest, weaker for high-throughput logs).
- **Recommendation.** (a) Redpanda (Kafka-API, lower ops) — matches CDC outbox + warehouse ingestion in [54 Capacity](./docs/02-architecture/54-capacity-and-scale-model.md).
- **Consequences.** Unblocks the event API + Track C messaging abstraction (already abstracted behind a port).
- **Required by.** **Phase 1.5** (to unblock engineering). — **Decision:** _____

## FD-12 · Vector store for RAG

- **Background.** AI grounding needs a vector/retrieval store; undecided (D-08).
- **Options.** (a) Meilisearch hybrid search (reuse existing). (b) Dedicated vector DB (pgvector / Qdrant).
- **Recommendation.** Start (a) for content-scale; evaluate (b) pgvector if recall/scale demands. Behind the LLM/RAG port (Track C) so it's swappable.
- **Consequences.** Affects AI quality + infra; low lock-in due to abstraction.
- **Required by.** **Pre-MVP.** — **Decision:** _____

## FD-13 · SMS/WhatsApp provider + PTA registration

- **Background.** Provider undecided; no multi-provider failover; PTA sender-ID/masking + per-operator routing unaddressed (AR-H-30); OTP is on the critical enrolment path.
- **Options.** (a) Single aggregator (fragile). (b) **Multi-provider with failover** + per-operator deliverability monitoring; complete PTA registration as a launch dependency.
- **Recommendation.** (b). Behind the notification port (Track C).
- **Consequences.** A provider outage or PTA rejection blocks all enrolment/consent/safety notices.
- **Required by.** **Pre-MVP.** — **Decision:** _____

## FD-14 · KMS/HSM topology

- **Background.** At-rest encryption, offline-cache keys, and crypto-shred erasure depend on a KMS/HSM + per-data-class keys; undecided (D-13, AR-H-14/AR-H-21).
- **Options.** (a) Cloud KMS (region-bound to FD-02). (b) Dedicated HSM for C4 keys + cloud KMS for the rest.
- **Recommendation.** (b): HSM-backed keys for safeguarding + per-subject data keys (crypto-shred); resolve alongside FD-02.
- **Consequences.** Unblocks the storage/crypto abstraction (Track C) and the retention/erasure mechanism.
- **Required by.** **Phase 1.5** (to unblock engineering). — **Decision:** _____

## FD-15 · Numeral system per pedagogical context

- **Background.** Eastern-Arabic (۰۱۲۳) vs Western (0-9) was treated as a formatting toggle over a pedagogy decision (AR-M i18n).
- **Options.** (a) Global Western. (b) **Per pedagogical context** — Eastern for Urdu-medium early-math content, Western for IDs/board-facing docs.
- **Recommendation.** (b), owned by the localization framework (Track C) as a content decision.
- **Consequences.** Affects early-math learning validity.
- **Required by.** **Pre-MVP.** — **Decision:** _____

## FD-16 · "Out-of-school at enrolment" flag capture

- **Background.** The north-star denominator needs a lawful, non-stigmatising flag; capture method open (D-14). For some children (a girl not in school, a working child) the flag is dangerous if exposed.
- **Options.** (a) Self-declared at enrolment with clear purpose + strict access (classify C3+). (b) Privacy-preserving proxy. (c) Drop the segmentation.
- **Recommendation.** (a) with DPO review + tight access; define a fallback north-star measure if uncapturable.
- **Consequences.** Determines whether mission impact is measurable and how it's reported to sponsors.
- **Required by.** **Pre-MVP.** — **Decision:** _____

## FD-17 · Report-card credential recognition

- **Background.** The report card's headline value is external recognition, but no board/government partnership exists (AR-M).
- **Options.** (a) Pursue board/government recognition partnership. (b) Position MVP report card as "internal verifiable progress evidence" and gate recognition language behind a secured partnership.
- **Recommendation.** (b) now + (a) as a business track; add verifiable-credential signing (Track C-adjacent, [29](./docs/06-portals/29-reporting-system.md)).
- **Consequences.** Over-promising recognition to poor families is an ethical/reputational risk.
- **Required by.** **Pre-v1.** — **Decision:** _____

---

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial founder-decision pack: 17 decisions with options, recommendations, consequences, and milestone gates; 8 marked Phase-1.5 (build-blocking). | Review team |
