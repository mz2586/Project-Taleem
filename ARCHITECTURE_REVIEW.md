# Architecture Review & Blueprint Audit — Project Taleem

| | |
|---|---|
| **Review type** | External Principal-Engineer pre-production design review |
| **Scope** | All 50 blueprint documents + 2 ADRs + governance files |
| **Date** | 2026-07-19 |
| **Method** | Five independent adversarial review streams (product, architecture/data, security/privacy/child-safety, design/education, ops/delivery), cross-verified against source documents |
| **Posture** | Assume nothing is correct; challenge every major decision; weight child-safety, privacy, and legal findings up |
| **Companion docs** | [BLUEPRINT_GAP_ANALYSIS.md](./BLUEPRINT_GAP_ANALYSIS.md) · [RISK_REMEDIATION_PLAN.md](./RISK_REMEDIATION_PLAN.md) · [FINAL_RECOMMENDATIONS.md](./FINAL_RECOMMENDATIONS.md) |

## 1. Executive summary

Project Taleem's blueprint is, as a *design document*, unusually strong: coherent, deeply
cross-referenced, mission-aligned, and disciplined in its traceability (Vision → PRD → FR → NFR → spec).
Its instincts — safety-inline, offline-first, PII-concentration, contract-first, honesty-by-construction
— are the right ones and are above sector norm.

It is **not production-ready**, and it does not yet demonstrate that a child-safety platform can be
safely operated or funded at 1,000,000-student scale. The recurring failure mode across every cluster is
the same: **load-bearing decisions and life-critical controls are asserted as principles but left as
"open questions" — with no numbers, mechanisms, or owning artifacts — while simultaneously being wired
into release-blocking MVP requirements.** The blueprint repeatedly labels the hardest problems *solved*
when they are in fact *deferred*.

The audit produced **97 consolidated findings**: **24 Critical, 34 High, 27 Medium, 12 Low**. The
Critical findings cluster into eight themes, each of which is independently sufficient to block a
production build:

1. **The most vulnerable child is excluded and unprotected** — no enrolment path for guardian-less
   children (the literal target population); the household/guardian is never modeled as a threat, yet
   the guardian controls the device, receives all data, and may read the child's AI transcripts.
2. **Crisis response is undefined** — distress/self-harm escalation is scoped *after* the AI ships,
   has no numeric SLA, no 24/7 staffing model, no clinician-reviewed holding response, and no
   mandatory-reporting/external-referral policy.
3. **Two flagship principles collide unresolved** — "offline-first" vs. "moderate every AI output
   before a child sees it."
4. **Children's most sensitive data crosses the residency boundary** — abuse/self-harm disclosures are
   sent to a foreign LLM region before they can be classified; the cloud/residency decision is open.
5. **The lawful basis for processing is likely invalid** — consent is made a precondition of schooling
   (not "freely given"); the DPIA is declared required but does not exist.
6. **The 1M-scale claim is unquantified and structurally ceilinged** — no capacity model; a single
   unsharded Postgres primary is the universal writer; no cost model for a sponsorship-funded platform.
7. **The school cannot yet teach or certify honestly** — no mastery definition, no prerequisite
   knowledge graph, no assessment validity framework, no shared-device answer-authorship assurance.
8. **Core accessibility and operational guarantees are unverified** — the design-token contrast matrix
   is asserted-but-absent, Urdu audio/font is unproven on real low-end hardware, and audit-immutability,
   PII-in-logs, incident-response, BC/DR, and staffing are principles without mechanisms.

**Verdict:** A top-tier Phase-1 *design*; a not-yet-credible Phase-1 *engineering and safety plan*. See
[FINAL_RECOMMENDATIONS.md](./FINAL_RECOMMENDATIONS.md) for the Production Readiness Score and the
Phase-2 go/no-go.

## 2. Severity dashboard

| Severity | Count | Meaning | Gate |
|---|---:|---|---|
| **Critical** | 24 | A child could be harmed; a serious legal/compliance breach; a hard scaling/data-integrity ceiling below target | Blocks Phase 2; must be closed and independently reviewed |
| **High** | 34 | Major gap causing real harm, rework, or outage | Must be closed before pilot (MVP) |
| **Medium** | 27 | Meaningful weakness; resolve before v1 | Scheduled remediation |
| **Low** | 12 | Polish / hardening | Backlog |
| **Total** | **97** | | |

### 2.1 Coverage across the 20 audit dimensions

| # | Dimension | Worst finding | # findings |
|---|---|---|---:|
| 1 | Missing requirements | Critical | 9 |
| 2 | Architectural weaknesses | Critical | 6 |
| 3 | Scalability (1M+) | Critical | 8 |
| 4 | Security risks | Critical | 9 |
| 5 | Child-safety risks | Critical | 12 |
| 6 | Privacy issues | Critical | 9 |
| 7 | Accessibility gaps | Critical | 6 |
| 8 | AI-safety concerns | Critical | 7 |
| 9 | Curriculum design | Critical | 6 |
| 10 | Database issues | Critical | 6 |
| 11 | API inconsistencies | Medium | 4 |
| 12 | UX problems | High | 6 |
| 13 | Operational risks | Critical | 8 |
| 14 | Disaster recovery | Critical | 3 |
| 15 | Cost optimization | High | 4 |
| 16 | Offline-first | Critical | 5 |
| 17 | Low-bandwidth performance | High | 4 |
| 18 | Internationalization | High | 5 |
| 19 | Maintainability | Medium | 4 |
| 20 | Technical debt | Medium | 3 |

(A finding may touch multiple dimensions; it is counted under its primary dimension.)

## 3. Critical findings (must be closed before Phase 2)

Each has a stable ID used across all four deliverables. "Human-gated" = requires a legal, business,
clinical, or infrastructure decision this review cannot make unilaterally.

| ID | Dimension | Location | Finding | Recommendation | Human-gated? |
|---|---|---|---|---|:--:|
| **AR-C-01** | Child safety / inclusion | 03 §2 FR-IDN-001; 05 §3; 06 §1 | **Guardian-less children are structurally excluded.** Enrolment requires a guardian consent record; the target population *is* orphans, displaced, street, and working children. The most vulnerable child — "the whole game" — cannot enrol. | Add a first-class unaccompanied-minor enrolment pathway (institutional/NGO guardianship + independent attestation + heightened safety envelope) with its own persona, journey, FR, and legal analysis. MVP, not edge case. | Legal |
| **AR-C-02** | Child safety | 07 §4/§5; 06 §6 | **The household/guardian is never modeled as a threat.** Guardian owns the shared device, receives all report cards/notifications, and has a full portal into the child's data; there is no child-private channel and no discreet safety exit. Much child abuse originates in the home. | Add a threat model where the household is the adversary: discreet/disguised safety exit, quick-exit with no shared-history trace, a child-private disclosure channel that bypasses the guardian, and rules on suppressing guardian-visible data when a safeguarding case is open. | No |
| **AR-C-03** | Child safety / privacy / authz | 12 §3/§8; 15 OQ | **Transcript-access policy is undefined**, so the default can route a child's abuse disclosure to the guardian they are disclosing *about*. | Make transcript confidentiality the default; any turn touched by the distress/safeguarding classifier is invisible to guardian/mentor and reachable only via the C4 Safety-Officer path. Author the policy as a release blocker. | No |
| **AR-C-04** | Child safety | 03 §6 FR-AIT-007 (v1); 15 §5/§9; 24 §7 | **Crisis response is undefined and mis-sequenced.** Distress escalation is v1 while the AI ships at MVP; the escalation SLA has no number; no 24/7 staffing; the crisis "holding response" is not a deterministic, clinician-reviewed template. | Promote distress detection + escalation to MVP MUST; define tiered numeric SLAs (imminent-harm ≤ minutes, 24/7); mandate deterministic clinician-reviewed holding templates served outside the LLM path; publish a staffing ratio. | Clinical + staffing |
| **AR-C-05** | Child safety / legal | 15 §5 OQ | **No mandatory-reporting / external-referral policy exists** (it is referenced but absent). The platform is designed to detect abuse disclosures with nowhere safe to route them; a naïve referral can itself endanger a child. | Author a standalone mandatory-reporting/referral policy naming concrete Pakistani channels, decision criteria, authorizer, child-protection-from-retaliation, and a "do-no-harm" test — before build. | Legal |
| **AR-C-06** | AI safety / offline | 03 §6 FR-AIT-002 vs 33 §8; 24 §3 | **Offline-first vs. moderate-before-exposure collide.** Offline "cached hints" bypass per-input moderation; a child in crisis offline gets neither detection nor escalation. | Decide and document the offline-safety contract: only static, pre-moderated, input-independent content offline; **no generative AI offline, ever**; an always-available offline crisis affordance + queued safety flag that fires on reconnect. Make it an FR. | No |
| **AR-C-07** | Privacy / AI safety / residency | 14 §10 O-3; 24 §3; 13 §3 | **Children's most sensitive utterances cross the residency boundary.** A disclosure's C4-ness is only known *after* the model sees it, yet text is forwarded to a foreign LLM region before/without classification; no-training is contractual only, unenforced. | Run distress/safeguarding classification and the holding response fully in-region (local/region-pinned model); never forward pre-classified-C4 text out of region; require technical zero-retention inference; resolve the residency/cloud ADR. | Infra + legal |
| **AR-C-08** | Privacy / legal | 14 §3; 11 §3.2; 14 §11 | **Lawful basis likely invalid + DPIA absent.** Consent to AI-processing and safety-monitoring is a precondition of schooling (not "freely given" under the GDPR-K baseline); assisted-consent legality is open yet an MVP MUST; the declared DPIA does not exist. | Re-ground core-learning + safety-monitoring on a non-consent lawful basis (legal obligation / vital interests) with counsel; reserve consent for optional scopes; produce the DPIA as a gating Phase-1 deliverable and feed it back into 11–15/24. | Legal |
| **AR-C-09** | Security / child safety | 11 §9; 11 §3.2 | **Guardian-number-change is a grooming/account-takeover vector.** A knowledge-based recovery alternative contradicts the doc's own "no knowledge-only recovery" rule; the notify-old-number control is void when the phone is lost/stolen; a single institutional guardian holds unchecked account power over parentless cohorts. | Delete the knowledge-based path; require independent in-person re-verification + mandatory safeguarding review for number changes on child-anchoring guardians; two-person control for institutional guardianship; freeze transcript/oversight access until re-verified. | No |
| **AR-C-10** | Security / child safety | 11 §5/§8; R-3 | **Device-binding does not protect against the in-household abuser.** A low-entropy picture-PIN on a shared, already-bound phone lets a household member log in *as the child* and read the child's own AI transcripts (including disclosures about that abuser). | Never expose distress-classified transcript content in the child's own session UI; add anti-shoulder-surf/liveness on PIN entry; raise the entropy floor; explicitly drop the "binding makes AAL1 safe" claim for the in-home adversary. | No |
| **AR-C-11** | Scalability / database | 08 §9; 09 §2/§7; 04 SCAL-03; 36 | **No capacity model + single unsharded Postgres write ceiling.** "1M concurrent-capable" is never disambiguated (enrolled vs. concurrent); every write funnels to one primary; there is no sharding plan; every "scales horizontally" claim is unfalsifiable. | Produce a quantitative capacity model (enrolled vs. peak-concurrent, QPS/write-TPS/WS/events/AI-turns/storage/cost, per-node budgets, node counts); commit a sharding strategy now (shard high-volume contexts by `student_ref`/`school_id`; Citus or app-routing) with shard key, resharding runbook, and cross-shard policy. | No (infra sizing) |
| **AR-C-12** | Cost / sustainability | 01 §2; 04 COST-02; 24 §9 | **No cost model for a sponsorship-funded platform.** The dominant variable cost (frontier-LLM inference, multi-call per turn) has an *open* envelope while Vision claims "marginal cost approaching zero"; SMS spend is uncapped. | Produce a cost model: per-student monthly envelope (AI with tier-mix + hard cap, infra, media, SMS), target cache-hit rates, and a gateway spend circuit-breaker; rewrite Vision §2's "approaching zero" to "bounded and sponsorship-viable." | Business |
| **AR-C-13** | Disaster recovery / data integrity | 35 §7; 36 §9; (BC/DR absent) | **No BC/DR plan; DR claims a single-region topology cannot honor.** RPO ≤5m/RTO ≤30m are asserted with multi-AZ-only; a TB-scale restore is not 30 min; report-card/attempt data is "sacrosanct" but has no tested backup/restore. | Author a BC/DR plan: per-context RPO/RTO split by AZ-loss vs region-loss, PITR + crypto-shreddable backups, a defined DR region + failover runbook, and a **timed, production-scale restore drill** as a gate. | Infra |
| **AR-C-14** | Curriculum / assessment | 21 §3 OQ; 23 §5 OQ; 02 §6 | **Mastery threshold is undefined**, yet the north-star, promotion, and report cards all derive from it. Success is currently unmeasurable. | Define the v1 mastery rule concretely (accuracy + spaced-retention on distinct items + no-hint final attempt), the calibration method, and formative-vs-summative difference. Remove "per agreed rule" placeholders from acceptance criteria. | No |
| **AR-C-15** | Curriculum | 21 OQ; 22 OQ | **No prerequisite/knowledge graph** → "mastery-based progression" is unimplementable; the system cannot diagnose why a child is stuck or sequence remediation; it degrades to linear seat-order. | Promote the objective DAG (`prerequisite_of` edges) to a v1 core entity; gate the coverage report on acyclic connectivity; specify the routing/remediation algorithm the Lesson Engine runs. | No |
| **AR-C-16** | Assessment | 23 (no validity section) | **No assessment validity/reliability framework.** Immutable storage of scores is not valid *measurement*; a "report card" over unvalidated items is data-integrity theatre; item-bank sizing and authoring/QA pipeline are absent. | Add an assessment-validity framework (item difficulty/discrimination, reliability targets, construct/standard coverage, standard-setting for cut scores) and a minimum-items-per-objective + authoring/AI-generation QA pipeline with throughput model. | No |
| **AR-C-17** | Assessment / integrity | 23 §7; 20 §2; 19 §4 | **Shared-device answer-authorship is unassured.** Auto-grading needs on-device keys (extractable); nothing verifies *who* answered; a sibling/guardian can farm the credential, corrupting mastery data. | Score server-side on sync (never ship keys offline); specify the cryptographic attempt seal; separate low-stakes formative from promotion-bearing summative and require human-corroborated identity assurance for the latter; state offline summative cannot be identity-assured. | No |
| **AR-C-18** | Accessibility | 18 §2; 16 §3 | **The design-token contrast matrix is asserted-but-absent.** Doc 18 has only 6 seed hexes and "(derived)" placeholders; doc 16 claims "the token contrast table is validated in CI." Every AA/high-contrast/focus-ring promise is currently unverifiable. | Produce the real token file (full ramps, every semantic pair's computed ratio vs. target, high-contrast map, focus-ring ratios) and wire the validator; until then mark 16 §3's "validated in CI" as aspirational. | No |
| **AR-C-19** | Accessibility / i18n / performance | 16 §5/§7; 18 §3; brief §7 | **Urdu audio/read-aloud and Nastaʿlīq are unproven on real low-end hardware.** Audio-first pedagogy is load-bearing but "TTS fallback" is a footnote; on Android Go a quality Urdu TTS voice is often absent/undownloadable and Nastaʿlīq is heavy and janky in old WebViews — colliding with the ≤500KB budget. | Make professionally pre-recorded Urdu audio mandatory for core-path text (packaged offline) with a defined production pipeline; ship a vetted on-device TTS fallback; decide Nastaʿlīq-vs-Naskh per surface with a hard font byte-budget — all **tested on a real Android Go handset** before audio-first is promised. | No (needs device test) |
| **AR-C-20** | Curriculum / inclusion | brief §3; 21 §1.5/§8 | **Islamiat-as-core contradicts religion-neutrality.** Non-Muslim children take Ethics/Akhlaqiat instead; no such track exists, so a religious-minority child is forced or excluded. | Model religious education as a student-attribute-driven track (Islamiat ↔ Ethics/Akhlaqiat); capture the choice at enrolment; reflect it on the report card; add minority representation to the content-review rubric. | No |
| **AR-C-21** | Security / privacy / ops | 39 §3/§4; 41 §4 | **Audit-immutability and PII-in-logs enforcement are asserted with no mechanism.** "Tamper-evident" has no hash-chaining/WORM; static log-statement scanning cannot catch runtime PII (interpolated objects, exceptions, ORM echoes, library logs). | Specify audit immutability (append-only + object-lock/WORM + hash-chaining + externally-anchored digests + verification job) and a runtime allow-list serialization logging pipeline + staging PII-canary scan; choose the redaction library. | No |
| **AR-C-22** | Operational / child safety | (IR absent); 38 §5; 28 §5; 30 | **No Incident Response Plan, no on-call rotation, and no message-monitoring-at-scale design.** Safeguarding events are 24/7; "monitored" adult↔child messaging (the grooming control) has no chosen mechanism at 1M scale. | Author an IR plan (SEV1 = child in danger, IC roles, comms tree, safeguarding runbook, regulator/guardian notification); define separate eng + Trust-&-Safety 24/7 on-call; specify automated grooming/abuse message classification with precision/recall targets + human-review sizing. | Staffing |
| **AR-C-23** | Requirements / testability | 03 FR-ENR-003/CUR-006/ASM-007; 02 §6 | **Undefined definitions are wired into release-blocking MUSTs.** Attendance semantics, mastery bar, and multiple "within SLA" gates are Open Questions whose acceptance criteria literally say "per the agreed rule (see Open Questions)" — so the gates are untestable and the north-star is unmeasurable at MVP. | Define attendance, mastery, and all safety/privacy SLA numbers before these are MUSTs; where undefinable, downgrade dependent KPIs from "measurable at MVP" to "instrumented, calibrated in pilot" and remove placeholder acceptance criteria. | Partly (some need pilot) |
| **AR-C-24** | Governance | 13/14/15/40 (referenced, absent) | **The safety/compliance backbone artifacts do not exist.** DPIA, formal threat model, mandatory-reporting policy, retention schedule, red-team methodology, staffing/capacity model, and IR plan are all referenced as if they exist but are absent — several are legal/clinical preconditions to building. | Produce each as a gating Phase-1.5 deliverable (see [BLUEPRINT_GAP_ANALYSIS.md](./BLUEPRINT_GAP_ANALYSIS.md)); feed findings back into the specs before build. | Legal/clinical for several |

## 4. High-severity findings (must be closed before pilot/MVP)

| ID | Dimension | Location | Finding | Recommendation |
|---|---|---|---|---|
| AR-H-01 | Child safety | 06 §7; 03 §9 | Mentor↔child direct message/call ("as policy allows") is an unmoderated grooming vector; no MUST that all such contact is in-platform, logged, moderated, rate-limited, off-personal-phone. | Add MUST requirements binding all Mentor↔Student comms to the moderated in-platform pipeline; ban off-platform contact-info exchange. |
| AR-H-02 | North-star gaming | 01 §6; 02 §6 OQ | North-star claimed "impossible to game" but is gameable 3 ways (self-declared OOS flag by incentivized party; low mastery bar; sibling farming on shared device). | Make the OOS flag independently verifiable; require spaced-retention in mastery; add anti-farming signals; stop asserting un-gameability until controls exist. |
| AR-H-03 | Data integrity | 03 §7 FR-ASM-003/005 | Offline auto-grading implies on-device answer keys; "sealed, tamper-proof" has no mechanism. | Server-side scoring on sync; specify the seal; see AR-C-17. |
| AR-H-04 | NFR realism | 04 PERF-05; 24 §3 | AI first-token <2.5s p95 is unattainable given the mandated input-classify → RAG → generate → output-classify pipeline over a 400ms-RTT/packet-loss reference network. | Re-baseline PERF-05 from a prototype; stream a pre-moderated safe-holding token; separate network RTT from compute; never weaken safety to hit latency. |
| AR-H-05 | MoSCoW / safety | 07 §2; 03 §10 FR-TNS-005 | Safeguarding escalation is MVP MUST but the Mentor Portal (its responder UI) is v1 — no MVP tool to action escalations. | Bring a minimal Mentor/Safety escalation surface into MVP or route MVP escalations solely to the Safety-Officer console; reconcile the IA release column. |
| AR-H-06 | MoSCoW / pedagogy | 02 §4.1; 03 §7 FR-ASM-004 | MVP targets KG–G5 but ships auto-grading only; the youngest band's real learning (letter formation, reading aloud, oral number sense) is inherently subjective and cannot be auto-graded. | Move minimal human grading into MVP for KG–G5, or narrow the MVP band to grades where objective auto-grading is valid; state honestly what "assessed fairly" means for pre-literate learners. |
| AR-H-07 | UX / MoSCoW | 03 §2 FR-IDN-007 | PIN recovery is v1/SHOULD, but the primary persona (no email, shared device, sibling PINs) will be locked out day one at MVP with no recourse. | Provide a safe guardian-phone/Mentor-assisted recovery at MVP. |
| AR-H-08 | i18n / pedagogy | 01 §7.3; 05 §2 | The two design-centre children speak Sindhi/Saraiki at home but must learn in Urdu from day one; L1 scaffolding is deferred to v2 — a documented learning barrier for pre-literate children. | Commit to defined home-language audio scaffolding/glossing in MVP/v1 for the primary personas' languages. |
| AR-H-09 | Availability scoping | 04 §7 AVAIL-01; REL-03 | The 99.9% SLO excludes the AI Teacher (the differentiating help mechanism); "AI down is acceptable" leaves the struggling child with no help while the SLO reports "available." | Add a separate AI-Teacher availability SLO and a genuine degraded-help fallback (Mentor async, pre-authored hint packs). |
| AR-H-10 | Privacy (lawful basis) | 14 §3 | (See AR-C-08.) Forced "consent" as a service precondition is invalid under GDPR-K. | Separate lawful bases; ground core processing on legal obligation/vital interests. |
| AR-H-11 | AI safety | 14 §7/§9 R-3; 24 R-4 | No-training guarantee is contract-only; no technical zero-retention mode, provider attestation, sub-processor allow-list, or breach detection. | Require technical zero-retention inference, audit rights, named sub-processor allow-list; forbid child inference on providers that cannot guarantee it. |
| AR-H-12 | Security (threat model) | 13 §2 | STRIDE is a one-line-per-category summary; no per-boundary decomposition or attack trees for the named adversaries. | Produce a standalone threat-model doc (per-boundary STRIDE + attacker-goal trees centered on reaching/contacting/de-anonymizing a child). |
| AR-H-13 | Security (offline token) | 11 §5/§7/§8 O-2 | Offline tokens live 24–72h; a large population falls back to a *software* keystore (extractable on a lost/rooted device); revocation only "on next sync." | Quantify the software-keystore population; sharply shorten offline TTL for it; absolute max-age expiry without sync; treat non-hardware-keystore devices as a lower-trust tier. |
| AR-H-14 | Security (key mgmt) | 11 §6; 13 §6 OQ | Per-profile cache key derivation input is unspecified; if derived from the picture-PIN, at-rest cache is brute-forceable from a stolen device. | Mandate high-entropy hardware-backed keys, never PIN-derived; document KDF inputs; resolve the KMS/HSM ADR before any offline data is written. |
| AR-H-15 | AI safety (injection) | 24 §6; 13 R-3 | Prompt-injection resistance is asserted with no mechanism; RAG curriculum (insider/poisoning surface) and child input both flow into the prompt. | Structural instruction/content separation, RAG-corpus signing + review, injection red-team evals, an output guard independent of the generation prompt. |
| AR-H-16 | AI safety (tiering) | 24 §5 | The cheapest model (Haiku) handles the highest-volume child turns with no requirement that every tier clears the same safety bar; small models are more jailbreakable and weaker at distress detection. | Require all tiers to pass an identical safety-eval threshold; route any distress-adjacent turn to the strongest tier regardless of cost. |
| AR-H-17 | AI safety (provider drift) | 24 §5/§10 | Red-team gates Taleem *releases*, but a provider-side silent model change is not gated. | Run the safety eval continuously (canary) against live endpoints; pin model versions where possible; fail-safe to cached content on regression. |
| AR-H-18 | AI safety (Urdu coverage) | 24 §6/§10 | Moderation/distress/injection classifiers' efficacy in Urdu/Roman-Urdu/code-switch is never addressed; classifiers are weaker in low-resource/transliterated text. | Add an Urdu/Roman-Urdu/code-switch safety-eval with measured recall on distress/grooming/self-harm; gate launch on it; localize red-team sets. |
| AR-H-19 | Child safety (vetting) | 15 §6 OQ | A CNIC check proves identity, not safeguarding history; Pakistan lacks a robust working-with-children check; vetting capacity is open, creating pressure to onboard faster than vetting. | Define real vetting content (references, safeguarding interview, probationary supervised access, re-vetting cadence); hard-cap onboarding on vetting throughput; system-enforced "no access before vetting." |
| AR-H-20 | Privacy (retention) | 14 §6 (all placeholders) | Every retention period is a placeholder; distress-bearing transcripts have "short retention" with no value; no schedule. | Produce a numeric retention-schedule artifact with legal basis per class and automated expiry. |
| AR-H-21 | Privacy (erasure) | 14 §6 R-4; 09 §10 | Erasure "across backups and processors" has no mechanism; immutable snapshots can't be surgically edited; LLM-provider copies are unreachable. | Crypto-shredding (per-subject data keys destroyed on erasure) + zero-retention providers + a documented erasure-orchestration saga across every store/device cache. |
| AR-H-22 | Privacy (abusive guardian) | 14 §6 | Guardian access/export of the child's full record (incl. transcripts) has no safeguarding carve-out — a surveillance tool for an abusive guardian. | Apply the distress/safeguarding carve-out to guardian access/export; safeguarding check before bulk export where C4-adjacent signals exist. |
| AR-H-23 | Privacy (DPIA) | 14 §11 | DPIA declared "required" but absent; building high-risk child processing before the DPIA inverts the required order. | Produce the DPIA as a gating deliverable; feed findings into 11–15/24. |
| AR-H-24 | Child safety (offline crisis) | 11 §5/§6; 24 §3 | (See AR-C-06.) Offline child in crisis gets no detection/escalation; any offline AI content bypasses guardrails. | No generative AI offline; always-available offline crisis affordance + queued flag. |
| AR-H-25 | Scalability (realtime) | 08 §8; 35 §3 | Redis Pub/Sub backplane is non-durable and O(pods) fan-out; ~1M concurrent WebSockets are undesigned (conns/pod, memory, LB limits, presence cost). | Durable partitioned backplane (JetStream/Kafka keyed per connection) or sharded Redis; specify conns/pod, LB, presence sizing, and pod count; consider a Go/Elixir gateway. |
| AR-H-26 | Scalability (event backbone) | 08 §6.2; 09 §7 | Polling outbox + analytics re-landed into an OLTP `analytics_ingest` Postgres means every event hits Postgres 2–3×, competing with the learning path. | CDC/logical-decoding relay (Debezium) with batched mark-published; analytics straight from broker → warehouse; delete the OLTP analytics hop. |
| AR-H-27 | Scalability (synchronized load) | 08 §9.4; 35 §5 | Bell-time thundering herds hit the *synchronous* path; "queue leveling" only helps async work; reactive HPA lags the spike; cold caches stampede the primary. | Scheduled pre-scaling (KEDA cron) tied to the timetable; pre-warm read-model caches; request-coalescing/singleflight on hot keys; model the arrival curve. |
| AR-H-28 | Offline correctness | 33 §6; 09 §9 | LWW keyed on client wall-clock on shared phones with no reliable NTP; a skewed clock silently overwrites a correct newer value. | Server-incremented version counters + HLC/Lamport; server-receive time as tiebreaker, never client wall-clock; attempts merge by union not overwrite. |
| AR-H-29 | Cost / FinOps | (absent); 43 PR-4/PR-11 | No cost model; AI + infra (1M WS, ClickHouse, media, SMS) unmodeled; funding sufficiency depends on the missing cost-per-student number. | Produce the cost model + FinOps guardrails; set the AI envelope as a hard design constraint. |
| AR-H-30 | Operational (SMS dependency) | 30 §2/§5 OQ | SMS/WA provider undecided; no multi-*provider* failover; PTA sender-ID/masking and per-operator routing (Jazz/Telenor/Zong/Ufone) unaddressed; OTP is on the critical path. | Multi-provider SMS with failover + per-operator deliverability monitoring; complete PTA registration as a launch dependency; delivery-rate SLO. |
| AR-H-31 | Operational (SMS cost/fraud) | 30 §5; 43 PR-4 | No spend circuit-breaker or per-day cap; SMS-pumping at 1M scale is a financial DoS. | Aggregate spend circuit-breaker, prefix allow-listing, artificially-inflated-traffic detection, monthly SMS cost envelope. |
| AR-H-32 | Testing (load/capacity) | 40 §3 OQ | "Load tests toward 1M" with no concurrency target, staged milestones, or soak/spike/breakpoint methodology. | Define peak-concurrency planning assumption; staged milestones (10k→100k→1M); soak/spike/breakpoint tests; derive capacity model. |
| AR-H-33 | Testing (AI red-team rigor) | 40 §3/§5 OQ | Red-team is "release-gating" with no eval-set size, numeric pass bar, adversary model, cadence, or owner. | Versioned growing adversarial corpus with category coverage, a zero-criticals numeric bar with confidence, a named owner, and continuous re-runs. |
| AR-H-34 | Testing (chaos/DR) | 40 (absent) | No chaos/fault-injection or DR/failover/restore testing beyond "game-days." | Add scheduled dependency fault injection, degraded-mode verification, region-failover and restore drills as readiness gates. |

## 5. Medium & Low findings (summary)

Recorded in full in [RISK_REMEDIATION_PLAN.md](./RISK_REMEDIATION_PLAN.md). Highlights:

**Medium (27):** UUIDv7 index bloat on billion-row tables; Meilisearch HA/sharding maturity for a 1M-doc
PII index; idempotency-store growth with no TTL; read-after-write pin-list unresolved; RLS overhead +
tenant-cardinality unstated; single-Redis blast radius (cache+sessions+streams+presence+pub/sub); event
schema-registry undecided (blocks parallel context dev); search ACL staleness on child-PII; per-profile
connection isolation not mandated (nullifies DB-grant defense); bidi math/mixed-script rendering
unaddressed; numeral policy (Eastern vs Western) as a formatting toggle over a pedagogy decision;
localization pipeline absent; spaced-retrieval unbuilt in v1; content-QA/bias rubric absent; verifiable
report-card signing absent; DoD applicability loophole (self-declared "not applicable"); coverage-target
inconsistency (80/85/90/100 across docs) with a flat CI floor; migration realism (synthetic data won't
reproduce lock contention); "extraction is just moving a folder" understates service-boundary cost;
at-risk model undefined but drives the safety queue; SMS safety-message delivery has no read-confirmation;
admin deprovisioning/break-glass/recertification unmechanized; minimum type-size unspecified; power-loss
mid-submission unhandled; multi-child session attribution/integrity undefined; consent-attestation
integrity (self-attested paper consent) forgeable; PDP fail-closed scoped only to "sensitive."

**Low (12):** API inbound-webhook contract (SMS/WA receipts) + `Retry-After` + upload-size limits;
command-vs-subresource convention unset; fitness-function tooling unnamed; interrupted AI-stream/partial
transcript handling; re-enrolment/graduation/consent-revocation lifecycle journeys missing;
security-assurance program (pentest cadence, bug-bounty, disclosure policy); doc approval-workflow tooling
(the Phase-1 exit gate itself); mixed-content bidi test cases; cognitive-accessibility (COGA) mapping
beyond AA; classroom-device roster enumeration; icon-comprehension testing protocol; "one primary action"
vs. lesson multi-affordance reconciliation.

## 6. What the blueprint gets genuinely right (to preserve)

An honest review records strengths, because the remediation must not regress them:

- **Traceability discipline** (Vision→PRD→FR→NFR→spec→test→backlog) is excellent and rare.
- **Safety-inline architecture** (moderation as a non-bypassable pipeline stage, not an async audit).
- **PII-concentration in Identity** with opaque cross-context refs — shrinks breach + erasure surface.
- **Contract-first, event-driven, bounded-context** design with the outbox pattern and a sensible
  modulith-with-carve-outs choice ([ADR-0001](./docs/02-architecture/adr/ADR-0001-architecture-style.md)).
- **Honesty-by-construction** (immutable attempts, append-only grades, no fabricated progress).
- **Reach-first empathy** (data budgets, offline-first, WCAG 2.2 AA, Urdu-first) as *stated intent*.
- **Child-safety acceptance criteria** (the 10 SACs in doc 15) as a per-feature gate concept.

The gap is not vision or values — it is that the hardest 20% (the load-bearing numbers, mechanisms, and
legal/clinical decisions) is undone and mislabeled as done.

## 7. Method note & confidence

Five independent reviewers examined the corpus in parallel from distinct expert lenses; their findings
converged strongly (e.g., the capacity-model absence, cross-border child inference, undefined mastery
bar, and missing crisis protocol were each surfaced independently by multiple streams), which raises
confidence that these are real, not artifacts of one perspective. Every Critical finding was
cross-checked against the cited source document. Where a finding depends on a factual claim about the
world (e.g., Nastaʿlīq font weight, Urdu TTS availability on Android Go, hyperscaler regions near
Pakistan, PTA sender-ID rules), it is flagged as requiring engineering validation on real hardware/in
the target market before it is treated as settled.

---

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-19 | Initial external architecture review & blueprint audit: 97 findings (24 Critical, 34 High, 27 Medium, 12 Low) across 20 dimensions, from five independent adversarial review streams cross-verified against source. | External Principal Engineer (review) |
