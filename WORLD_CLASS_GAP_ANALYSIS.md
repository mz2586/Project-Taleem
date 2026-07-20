# World-Class Gap Analysis — Project Taleem

| | |
|---|---|
| **Companion to** | [EXECUTIVE_REVIEW.md](./EXECUTIVE_REVIEW.md) · [FINAL_ROADMAP.md](./FINAL_ROADMAP.md) · [FINAL_MILESTONE_PLAN.md](./FINAL_MILESTONE_PLAN.md) |
| **Date** | 2026-07-20 |
| **Purpose** | Define the "world-class" bar per area, measure the current gap, and specify the concrete delta to close it — including redesigns where a better approach exists. |

## 1. What "world-class" means here

A world-class AI-powered digital school is one that: (a) a family living on the poverty line can actually
use on a shared Android Go phone in Urdu, offline; (b) demonstrably *teaches* (validated mastery, not
content consumption); (c) is *provably* safe for children, operationally, 24/7; (d) is *lawful* where it
operates; (e) is *economically sustainable* at national scale; and (f) issues a credential that is
*recognized*. Taleem's blueprint aims at exactly this bar — the gap is turning the aim into evidence.

## 2. Gap register (current → world-class → delta)

Delta size: **S** (weeks), **M** (1–2 quarters), **L** (multi-quarter/partnership).

| Area | Current | World-class bar | Delta / action | Size |
|---|---|---|---|---|
| **Curriculum data** | SNC modeled as data; **dataset does not exist** | Full machine-readable SNC KG–10, board-mapped, expert-validated | Acquire/licence SNC via partnership (not hand-encode); validate one provincial variance | L |
| **AI cost** | Tiered LLM + cache + cap (planning) | Proven $/student sustainable; frontier model rarely needed | **Redesign to LLM-as-last-resort** (§3.1); prove unit economics on pilot data | M |
| **AI residency/safety** | Cross-border frontier calls; Urdu safety unproven | In-region inference for child data; measured Urdu recall on distress/grooming | **In-region small/on-device model default** (§3.1); Urdu red-team with numeric bar | M–L |
| **Lawful basis / DPIA** | Consent-as-precondition; DPIA absent | Valid non-consent basis for core+safety; completed DPIA | Counsel opinion (FD-01) + DPIA before build | M |
| **Child-safety ops** | Framework + protocol; SLA/staffing open | 24/7 funded responders; numeric SLA; mandatory-reporting live | Fund/staff (FD-06); reporting policy w/ NGO+counsel (FD-04) | L |
| **Assessment validity** | Immutable attempts; mastery rule (doc 58) | Psychometrically valid, reliable, standard-set; identity-assured summative | Psychometric review; mentor-mediated summative (§3.2); item-bank supply plan | L |
| **Android Go reality** | Budgets set; **untested on device** | Proven Urdu+Nastaʿlīq+audio within budget on a real Go handset | On-device validation lab as a hard gate (EV-06) | S–M |
| **Localization** | Urdu i18n framework | Real TMS/ICU pipeline; Sindhi/Pashto as first-class data | Author localization-pipeline spec; validate overlay on real scripts | M |
| **Scale evidence** | Capacity model + sharding (paper) | Load-validated to ≥150k concurrent; no ceilings | Staged load tests against the skeleton (10k→150k) | M |
| **DR** | Plan; single-region | Cross-region, tested restore, proven RTO/RPO | DR region (FD-02) + timed restore drill | M |
| **Observability** | Wired; no backend | Live SLO dashboards incl. safety-escalation SLO | OTel→collector+dashboards in staging | S–M |
| **Design breadth** | 2 components; contract | Full a11y/RTL-tested library; child-usability-validated flows | Grow library + child usability testing | M |
| **Credential recognition** | Intent only | Board/government-recognized transcript | MoU + verifiable-credential signing | L |
| **Competitive moat** | Differentiated on paper | A shipped pilot proving safety + reach + recognition | Ship the Phase-8 pilot | L |

## 3. Redesigns recommended (challenging existing decisions)

The brief says do not protect prior decisions. Four are worth genuinely reconsidering:

### 3.1 AI: "LLM-as-last-resort" with an in-region default (replaces frontier-first tiering)

- **Current:** every AI turn routes to a Claude tier (Haiku→Sonnet→Opus) via a cross-border gateway.
- **Problem:** this is simultaneously the top cost risk, the residency risk, the latency risk (multi-call
  pipeline over 3G), and the offline gap.
- **Redesign:** make the default path **(1) cached/RAG deterministic answers → (2) a small in-region or
  on-device model for routine turns and distress classification → (3) a frontier LLM only for genuinely
  hard explanations**, with a hard per-student budget. This single change improves cost, residency,
  latency, offline, and safety-in-Urdu at once. Keep the provider abstraction (already built) — this is a
  routing-policy change, not a re-architecture.
- **Verdict:** adopt as the target AI architecture; it is strictly better for this user.

### 3.2 Assessment: mentor-mediated summative (replaces device-trust for high-stakes)

- **Current:** attempts sealed on-device; proctoring-lite; server-side scoring.
- **Problem:** on a *shared* family device, authorship is unassurable; a credential earned by a sibling is
  worthless.
- **Redesign:** split assessment cleanly — **formative = device, identity-relaxed** (fine); **summative =
  mentor-mediated / synchronous check-in / occasional oral verification**, and state plainly that offline
  summative is not credential-bearing. Stop trying to make device-based high-stakes trustworthy.
- **Verdict:** adopt; it is the only honest path to a defensible credential.

### 3.3 Realtime: async-first for v1 (defer the WebSocket gateway)

- **Current:** a WebSocket realtime gateway is a day-one carve-out (live class, presence, AI streaming,
  notifications).
- **Problem:** 150k+ concurrent WebSockets is one of the most expensive, complex infra problems here, and
  it fits the 3G/2h-power reference user poorly.
- **Redesign:** for v1, use **HTTP + short polling for notifications and non-streamed (or SSE) AI
  responses**; defer the persistent-connection realtime gateway until a feature genuinely requires it.
  This removes a large fixed cost and a scale ceiling from the critical path.
- **Verdict:** adopt for v1; revisit realtime when live-class demand is proven.

### 3.4 Curriculum: partnership-sourced SNC (replaces in-house encoding)

- **Current:** "model SNC as data" with the dataset to be produced.
- **Problem:** hand-encoding KG–10 × subjects × provincial variants is a hidden multi-quarter cost and a
  correctness/recognition risk.
- **Redesign:** treat SNC acquisition as **procurement/partnership** (board, ministry, or an existing
  curriculum provider) with expert validation; build the engine to ingest it.
- **Verdict:** adopt; de-risks the single largest hidden content cost.

## 4. The shortest path to world-class

1. **Close the 8 governance Criticals** ([FOUNDER_DECISIONS.md](./FOUNDER_DECISIONS.md)) — nothing else
   matters if legality/residency/safety-ops don't land.
2. **Prove the four realities** that no document can assert: Android Go device validation, AI unit
   economics, Urdu safety-classifier recall, and a real intermittent-network field test.
3. **Adopt the four redesigns** (§3) before building the corresponding engines.
4. **Ship a small, safe, real pilot** (Phase 8) — evidence beats blueprint.
5. **Hold the quality bar** the project has already demonstrated.

## 5. Honest scoring of the gap

The gap between Taleem-today (70/100) and world-class (≥90) is **not a design gap** — the designs are
mostly right and the discipline is exceptional. It is an **evidence-and-governance gap**: legal sign-off,
proven unit economics, funded safety operations, real-device proof, and a shipped pilot. Those are
closable in ~3–5 quarters of well-governed execution — which is why the verdict is "capable," not
"unlikely."

---

## Change log

| Date | Change | Author |
|---|---|---|
| 2026-07-20 | World-class gap register (14 areas), 4 redesign recommendations (AI last-resort, mentor summative, async-first realtime, partnership SNC), shortest-path plan. | Executive panel |
