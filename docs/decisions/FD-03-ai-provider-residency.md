# Decision Brief FD-03 — AI Provider, Inference Residency, and Retention

**Status:** Open — owner decision required · **Recommendation:** Anthropic Claude Sonnet 5.5, first-party
API, `inference_geo: "us"`, under Zero Data Retention (re-verified against official sources 2026-11-17;
unchanged) · **Owners:** Founder + Legal (data protection) · **Prepared:** 2026-10-22, rewritten
2026-10-25, re-verified 2026-11-17 · **Register entry:** [`FOUNDER_DECISIONS.md` § FD-03](../../FOUNDER_DECISIONS.md)

## The decision

Which AI inference provider, in which region, under which retention and training terms, may receive
text derived from a child's learning session. And which categories of text may never leave our own
infrastructure.

### Re-verification 2026-11-17: what changed

The recommendation stands. No evidence found on 2026-11-17 changes the provider, model, region, price
or envelope. Sources and read dates are in §10.

- **Unchanged:** Sonnet 5.5 prices ($2 / $10, cache hit $0.10, 5-minute cache write $2.50), the 1.1×
  `us` multiplier, `inference_geo` values (`us`, `global` only), workspace geo (`us` only), the ZDR
  scope, the 512-token minimum cacheable prompt, the Commercial Terms no-training clause, the DPA
  (SCC Modules 2/3), and Anthropic's minors guidelines (last updated 2026-03-16). Google's terms still
  forbid under-18 services.
- **New, Anthropic:** the Usage Policy has a new version (effective 2026-11-12) with **High-risk Use
  Case Requirements**. "Education and credentials" covers admissions, outcome-determining grading,
  credentials and discipline. General educational content is excluded, so rephrasing lesson text is
  not high-risk. Using a model to grade an outcome-determining assessment would be (§6).
- **New, Anthropic:** the retention docs now state that **under ZDR the API does not block
  ZDR-ineligible features**. Using one steps outside ZDR for that data. The ineligible list now also
  names message threads, MCP connector, Agent Skills, Managed Agents and user profiles. The adapter
  uses none of them (§9.1).
- **New, OpenAI:** India (`in.api.openai.com`) now offers **in-region processing**, but only for
  `gpt-6-luna`, OpenAI's small tier ($0.10 / $0.50). The 2026-10-25 brief said India was storage only.
  The UAE processes only GPT-5.x models. There is still no current mid-tier model in-region in South
  Asia or the Gulf from any provider. See §3 for why this does not change the choice.
- **New, Azure:** `gpt-6.1-sol` is deployable from South India as *Data Zone Standard* (Asia Pacific:
  "any Asia Pacific nation") or *Global*. The UAE is Global only. There is no in-country (Standard or
  Regional) deployment of a 6.x model in India or the UAE.
- **New, Google:** Gemini 3.8 Flash is $0.75 / $3.75 on the Gemini API until 2026-12-31, rising to
  $1.50 / $7.50. This makes no difference, because the terms exclude Google.

## 1. What actually needs a provider

| Capability | Needs a real model? | Today |
| --- | --- | --- |
| Lesson teaching, worked steps, hints, mastery, path, homework marking against a key, unit checks, progression, report cards | No | Deterministic engine, live in production |
| "Ask the teacher": tap and typed questions answered by quoting the published lesson | No | In-house retrieval (`domain/lesson_qa.py`); typed questions behind `ai_teacher.ask_free_text` and the disclosure screen. Never sent to a provider |
| "Explain it another way": a child-level rephrase of the authored passages already chosen | **Yes** (explanation tier) | Built behind `LLMGateway`; flag `ai_teacher.generative_rephrase` off; the adapter refuses to construct without approval |
| Checking model output for grounding and age appropriateness with a second, cheap model | Optional (classification tier) | No call site; the lexical and semantic gate runs in our own code |
| Marking short written answers; generating replies to anything a child types | Yes, **but blocked separately**: child free text must first be screened by an in-house distress classifier (FD-03 option (b), AR-C-07) | Not built; not part of this approval |

This approval therefore covers **one** capability: rephrasing published lesson text.

## 2. What would be sent, measured

Each call sends a fixed system instruction (288 characters) plus the grounded passages for the item in
front of the child. This was measured on the published fractions lesson: **562–1,213 characters** per
prompt in English and Urdu (3 passages to all 14–18). That is roughly 200–700 tokens; Urdu costs more
tokens per character. The call also carries a fresh random request id. The adapter refuses to send
anything else, and checks this itself before every request:

- **Sent:** published lesson passages, the learner's selected *authored* option for the current item,
  and the locale and grade band.
- **Never sent:** names, learner refs, family codes, guardian data, contact details, the child's free
  text (including typed "ask the teacher" questions), other learners' data.

Counsel should confirm a judgement we hold but cannot make ourselves: that this payload is not
personal data of the child. The rest of this brief is written as if it were, to stay conservative.

## 3. Providers compared (official sources, read 2026-11-17)

| | **Anthropic Claude** (first-party API) | OpenAI API / Azure OpenAI | Google Gemini (Vertex / Gemini API) |
| --- | --- | --- | --- |
| Model for this job | `claude-sonnet-5-5` | `gpt-6.1-sol` (OpenAI's mid-tier) | Gemini 3.8 Flash |
| List price, per 1M tokens in / out | $2 / $10 (cache hit $0.10); ×1.1 with `inference_geo: "us"` | $2 / $10 (cached $0.10); +10% on data-residency endpoints for models released on or after 2026-03-05 | $0.75 / $3.75 on the Gemini API until 2026-12-31, then $1.50 / $7.50. Vertex regional price UNVERIFIED (page did not render) |
| Use by children | **Permitted** with safeguards: products serving minors must follow the [Guidelines for Organizations Serving Minors](https://support.claude.com/en/articles/9307344) and applicable law ([Usage Policy](https://www.anthropic.com/legal/aup), effective 2026-11-12) | Permitted with conditions: no under-13 personal data "without first implementing zero data retention"; age-appropriate filters, monitoring and escalation ([Under-18 guidance](https://developers.openai.com/api/docs/guides/safety-checks/under-18-api-guidance)). The parental-consent clause in the Services Agreement is UNVERIFIED on 2026-11-17 (page returned 403) | **Prohibited**: no service "directed towards or is likely to be accessed by individuals under the age of 18" ([Service Terms §20(d)](https://cloud.google.com/terms/service-terms); same wording in the [Gemini API terms](https://aistudio.google.com/docs/terms), effective 2026-03-23) |
| Processing region options | `us` or `global` only; workspace data at rest `us` only ([data residency](https://platform.claude.com/docs/en/manage-claude/data-residency.md)) | US and EU: broad. India, Japan, Australia: `gpt-6-luna` only. UAE: GPT-5.x only, via sales ([data residency](https://developers.openai.com/api/docs/guides/data-residency)). Azure: `gpt-6.1-sol` in South India via Data Zone (any APAC nation) or Global; UAE Global only | Sonnet 5.5 on Vertex: global or `us`/`eu` multi-region only. No Gulf or South Asia commitment verified for Gemini |
| Training on our data | No ("may not train models on Customer Content", [Commercial Terms](https://www.anthropic.com/legal/commercial-terms)) | No, unless opted in | No, without permission |
| Zero retention | Per-org ZDR via sales. Prompt caching is eligible. **Batch, Files, code execution, message threads, MCP, Skills, Managed Agents are not, and the API does not block them** ([retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention.md)) | Sales-approved ZDR; `/v1/files`, `/v1/batches`, `/v1/conversations` are not ZDR-eligible | Disable caching, `store=false`, no grounding, plus a negotiated Master Agreement (not re-verified: excluded on terms) |
| What is kept even under ZDR | Content flagged by trust and safety: up to 2 years. Classification scores: up to 7 years ([privacy centre](https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data), updated 2026-07-01) | Abuse-monitoring logs are excluded under ZDR; default retention is up to 30 days | Not re-verified |
| Processor DPA with SCCs | Yes ([DPA](https://www.anthropic.com/legal/data-processing-addendum), Modules 2 and 3) | Yes | Yes |
| In our code today | Adapter built, 86 tests, inert | Nothing | Nothing |

**Google is excluded.** Its terms forbid the use outright. **No provider processes inside Pakistan**, and
no provider offers a current mid-tier model in-region anywhere in South Asia or the Gulf. Bedrock routes
Sonnet 5.5 from Mumbai, Hyderabad and the UAE through the *global* endpoint only. Vertex serves Sonnet
5.5 only globally or from the US/EU multi-regions. Azure reaches `gpt-6.1-sol` from India only through a
zone spanning every Asia-Pacific nation. Whatever is chosen, child-session text crosses a border. The
real choice is between a **named jurisdiction** and **anywhere**.

**The new India option (OpenAI `gpt-6-luna`) does not change this.** It is a small-tier model: the
Haiku-tier equivalent, not the explanation tier this approval covers, and its Urdu and child-safety
quality are unmeasured. India is still a foreign jurisdiction for a Pakistani learner. No source shows
that India offers Pakistan a legal advantage over the US. Using it would also need a new adapter and a
new evaluation. If counsel concludes that proximity carries legal weight, raise it then as a separate
FD-03 option. This brief does not recommend it.

## 4. Recommendation

**Anthropic, first-party Claude API. `claude-sonnet-5-5` for explanations. A dedicated workspace with
`allowed_inference_geos: ["us"]` and `default_inference_geo: "us"`. Zero Data Retention for the
organisation. No ZDR-ineligible feature (Batch, Files, code execution, message threads, MCP, Skills,
Managed Agents) and no Console use with this workspace.**

Why this, for Taleem:

1. **The terms allow a children's school.** Anthropic sets out the safeguards it requires for products
   serving minors: technical safety measures, AI disclosure, monitoring and reporting, and a public
   statement of child-privacy-law compliance. It may also provide a child-safety system prompt. Taleem
   already meets most of these by design: consent-gated enrolment, an AI-teacher label on every surface,
   generated text marked `generated: true`, an output gate and safeguarding review. OpenAI also allows
   it, with ZDR before any under-13 data. Google does not.
2. **One named jurisdiction instead of "anywhere".** `inference_geo: "us"` pins inference to the US, and
   the workspace stores at rest in the US. That gives counsel one country and one processor DPA for
   the transfer assessment. `global`, and every Bedrock, Vertex or Azure route reachable from the region,
   gives an unknown set of countries.
3. **ZDR fits the design.** Prompt caching stays usable under ZDR. The features ZDR excludes are ones
   Taleem does not need, and the adapter cannot reach them. Default retention without ZDR is still
   stated two ways: the API docs say conversation content is "not retained by default", while the
   privacy centre says it is deleted "within 30 days". ZDR removes the question.
4. **Same price as the alternative, and already built.** Sonnet 5.5 and GPT-6.1 Sol have the same list
   price. The Claude adapter, its data-minimisation guard, cost ledger, fail-closed boot and
   evaluation harness exist and are tested. Choosing OpenAI would mean a new adapter, new tests and a
   new evaluation for no residency gain: in-region processing near Pakistan covers only its small model
   (India) or older models (UAE).
5. **Urdu quality is not assumed.** It is a release gate (§9.5), measured on our golden set.
   If Sonnet 5.5 fails it, the decision is reopened rather than lowered.

**Rejected:** self-hosting an open-weight model (option b) *for explanations*. Its Urdu quality and child
safety are unmeasured, and it puts GPU operations and on-call into a free school before the first
pilot. Option (b) stays the plan for the **in-house distress classifier** that must screen child free
text. That is a different capability, and this approval does not cover it.

## 5. Expected cost per learner

Re-checked 2026-11-17: no price changed, so the numbers stand.

Assumptions, labelled. The prompt is about 700 input tokens (upper end of the measurement). The output
is about 300 tokens, capped at 1,024. Prices are Sonnet 5.5 list prices × 1.1 for the `us` pin. Assume no
cache benefit: the prompts sit around Sonnet 5.5's 512-token minimum. The month has 20 school
days. Calls the gate rejects are still billed.

| Scenario | Rephrase calls per school day | Cost per call | **Per learner per month** | Per 10,000 learners per month |
| --- | --- | --- | --- | --- |
| Light | 2 | $0.0048 | **$0.19** | $1,900 |
| Typical | 6 | $0.0048 | **$0.58** | $5,800 |
| Heavy, at the call quota | 20 | $0.0048 | **$1.94** | $19,400 |
| Worst case (quota, every reply at the 1,024 cap) | 20 | $0.0128 | **$5.12** | $51,200 |

**Recommended envelope (FD-07): `TALEEM_AI_LEARNER_DAILY_COST_MICROS=100000`, which is $0.10 per learner
per day.** This caps the quota rows above it (up to $0.26 a day in the worst case). That bounds the heavy
month at $2.00 over 20 days, and the theoretical maximum at $3.10 if used on all 31 days. On exhaustion
the child gets the authored explanation, which is the same lesson with no AI rephrase.

Uncertain costs:

- Urdu token counts. The first real run measures them exactly from `usage`.
- How often children actually press "explain it another way". The pilot measures this.
- Gate-rejected calls, which are billed.
- Future price changes. The constants in the adapter were checked on 2026-11-17 and must be re-checked
  at approval.

Using Haiku 5.5 ($0.10 / $0.50) for this tier would cost about 1/20th as much. That is worth
evaluating once Sonnet passes, not before.

## 6. Privacy and child-safety implications

- **Cross-border transfer to the US**, under Anthropic's DPA (Anthropic as processor; SCC Modules 2/3
  incorporated). Pakistan's data-protection bill is still a draft. Counsel must record the lawful
  basis (FD-01/FD-02), even if the payload is judged non-personal.
- **What residency does not cover.** `inference_geo` controls where inference runs, not where trust and
  safety review happens. No official statement says where flagged content is logged, so assume it
  may be outside the US. Under ZDR the only content kept is trust-and-safety-flagged content (up to
  2 years; scores up to 7 years). Because Taleem sends only authored lesson text, flagging should be
  rare. The ledger records the request id, so any flag can be traced to one call and one lesson, never
  to a child.
- **The model never talks to the child.** It rephrases authored text. The gate checks grounding,
  answer leaks, age band, disallowed content, locale and arithmetic/polarity consistency. A
  rejection serves the authored text. There is no model call offline, and no model call without live
  `ai_teaching` consent.
- **The model never decides anything about a child.** Under the Usage Policy (effective 2026-11-12),
  grading "an exam or assessment that determines admission, graduation, licensure, or certification"
  is high-risk: it needs a qualified human who reviews and can change each result, and the affected
  person must be told AI was used. Progression, unit checks and report cards stay deterministic. Any
  future AI marking of an outcome-determining assessment needs those controls and a new FD-03 approval.
- **Anthropic's obligations on us** (Guidelines for Organizations Serving Minors):
  - technical safety measures and age-appropriate moderation (the gate);
  - AI disclosure (in place);
  - monitoring and reporting (safeguarding queue, audit log);
  - **a public statement of child-privacy-law compliance on the website (not yet published, needs
    counsel)**;
  - adopting Anthropic's child-safety system prompt (to request at signing).

  Anthropic may audit, and may suspend or terminate the account for non-compliance.

## 7. The exact approval required

**What the owner signs.** One dated FD-03 record in `FOUNDER_DECISIONS.md` § FD-03 containing the six
items below. Each item names its signer, its date and its evidence (a contract, an email, or a report
file). The record's id (for example `FD-03/2026-12-01`) becomes `TALEEM_AI_FD03_APPROVAL_REF`. The
adapter stays inert until that setting names the record, and item 6 cannot start until items 1–4 are
signed.

1. **Founder:** approve Anthropic as provider, with model `claude-sonnet-5-5` and the workspace
   configuration in §4.
2. **Founder, with Anthropic sales:** ZDR for the organisation, confirmed in writing. The confirmation
   must cover:
   - that ZDR covers `claude-sonnet-5-5` (and `claude-haiku-5-5`);
   - that Anthropic accepts a product for ages 6–12 under its minors guidelines;
   - Anthropic's child-safety system prompt.
3. **Legal:**
   - the transfer basis to the US;
   - the DPIA for the AI path (EV-03);
   - the public child-privacy compliance statement.
4. **Founder (FD-07):** the per-learner envelope. The recommendation is $0.10 per day, 20 calls and
   20,000 tokens.
5. **External:** an AI red-team review of the gate (EV-08).
6. **Engineering, after items 1–4:** run the golden set against the real model and complete the human
   transcript review, with the thresholds in §9.5. Only then is the flag turned on, for a pilot cohort
   first.

**Not sent until all six are recorded:** any request to any provider from any environment that has
learners. The golden-set run (item 6) uses only the synthetic published lesson and authored
contexts. No child data is involved.

## 8. What continues without approval

- Semantic consistency check in the gate (arithmetic, polarity, number provenance).
- Red-team golden set across ten unsafe-output categories, in English and Urdu.
- Price constants kept current. They were last checked on 2026-11-17, with no change.
- Adopting the child-safety system prompt into `SYSTEM_PROMPT` once Anthropic provides it. This is a
  reviewed change.
- In-house distress classifier design, which is the prerequisite for any free-text AI feature.
- Pilot measurement plan: rephrase-request rate, gate rejection rate, cost per learner from the
  ledger.

## 9. Implementation

Everything below is built and tested unless marked **GAP**. No code change is needed to switch on
after approval: it is configuration plus the operational steps marked here.

### 9.1 Secure provider integration

Code: `services/core-api/src/taleem_core/ports/llm_anthropic.py`, `platform/config.py`,
`tests/test_ai_teacher_anthropic_adapter.py`. Set these in the target environment's secret store,
never in the repository:

| Setting | Value | Why |
| --- | --- | --- |
| `TALEEM_AI_PROVIDER` | `anthropic` | Selects the Claude adapter. |
| `TALEEM_AI_ANTHROPIC_API_KEY` | the workspace API key | A dedicated variable. The SDK's own `ANTHROPIC_API_KEY`, profile and federation discovery are never used, so a key already on a machine cannot switch this on. |
| `TALEEM_AI_INFERENCE_GEO` | `us` | Sent as `inference_geo` on every request. `global` is refused because it is not a pin. Another geography is a reviewed code change (`ALLOWED_INFERENCE_GEOS`). |
| `TALEEM_AI_ZDR_CONFIRMED` | `true` | The founder's attestation of §7 item 2. |
| `TALEEM_AI_FD03_APPROVAL_REF` | the §7 record id, e.g. `FD-03/2026-12-01` | 3 to 64 characters from `A-Z a-z 0-9 . _ : / -`. |
| `TALEEM_AI_LEARNER_DAILY_COST_MICROS` | the FD-07 envelope, in micro-USD per learner per UTC day | Required in production with this provider. |
| `TALEEM_AI_LEARNER_DAILY_CALLS` / `_TOKENS` | FD-07 values | Defaults 20 calls / 20,000 tokens. |
| `TALEEM_AI_TIMEOUT_SECONDS` | optional, default `15` | Per-call timeout. |
| `TALEEM_ENABLED_FLAGS` | add `ai_teacher.generative_rephrase` | The tier stays off until this flag is on. It can be rolled out per learner. |

- **Fail closed.** In production the app refuses to boot if `TALEEM_AI_PROVIDER=anthropic` is set
  without every setting above. Elsewhere it logs `ai_provider_not_approved` and stays deterministic.
- **Endpoint and surface.** The base URL is pinned to `https://api.anthropic.com`, so
  `ANTHROPIC_BASE_URL` cannot redirect traffic. Only `messages.create` is called: no Batch, Files, code
  execution, threads, tools, MCP or Skills. This matters because ZDR does not block them (§3).
- **Models.** `claude-sonnet-5-5` with thinking off (`between_tools`) and effort `medium`;
  `claude-haiku-5-5` is reserved for the classification tier. Covered Models (Fable/Mythos), which
  require 30-day retention, are never used. The server-side refusal `fallbacks` parameter is
  deliberately not used, because it would run the request on a model this approval does not cover.
- **Operational steps at setup (not code):** create a dedicated workspace with
  `allowed_inference_geos: ["us"]` and `default_inference_geo: "us"`; no Console or playground use with
  it.
- **GAP:** key rotation is a manual secret-store operation, with no runbook yet.

### 9.2 Curriculum grounding

- The prompt is built only from the published `LessonView` passages for the current item, each with its
  field path as provenance (`domain/ai_teacher_gate.py`). With no grounding, no call is made
  (`unverifiable`).
- An objective with no published lesson returns `404`. Answer keys and answer options are never
  passages.
- An accepted rephrase is returned only in a separate `generation` block (`generated: true`,
  `verified: false`, `grounded_on`, `notice_key`). The verified authored `utterances` are unchanged
  beside it.
- Ask the teacher quotes the lesson verbatim, excluding item prompts, hints and answer keys, and is
  checked by `is_grounded_excerpt` before serving. No model is involved.

### 9.3 Learner-data minimisation

- `assert_minimised` runs inside the adapter before any network call. A request is sent only if the
  prompt is exactly the grounded rephrase template plus an authored selected option. Identifiers,
  family codes, emails, phone numbers, free text and `never_send` values are refused.
- The only identifier sent is a fresh random `metadata.user_id` per request. The learner's pseudonymous
  ref stays in our ledger (`learning.ai_usage_ledger`: counts and ref only, no text).
- Typed child questions (ask the teacher) never reach the adapter.
- **GAP:** the ledger retention period is not set (`purge_older_than` exists). It must be set in the
  DPIA (§7 item 3).

### 9.4 Child-safety controls

Order of checks on every `:explain` (`application/ai_teacher_service.py`): flag → kill switch → no
pending escalation → live `ai_teaching` consent → quota → grounded prompt → adapter → output gate.
Each fails closed to the authored response.

- **Output gate** (`domain/ai_teacher_gate.py`): grounding, semantic consistency, answer leak, age band,
  safety vocabulary/contact/secrecy/injection, locale. Any one violation refuses.
- **Kill switch** (`platform/kill_switch.py`) halts every child-facing route.
- **Disclosure screen** on homework and typed questions raises a safeguarding concern into the lead-only
  triage queue and serves a fixed holding message
  ([52 crisis protocol](../03-security-privacy/52-safeguarding-crisis-protocol.md)).
- **Audit:** one structured, text-free safety event per generative decision.
- **GAPs:**
  - the child-safety system prompt (awaiting Anthropic, §7 item 2);
  - the public child-privacy statement (§7 item 3);
  - no trained distress classifier;
  - the holding-message wording and staffing await M-Safe / FD-06;
  - no per-turn transcript store, by design (no child text is kept). Review relies on the item-6
    transcripts and on pilot sampling of gate decisions.

### 9.5 Model evaluation before children see output

Harness: `python -m taleem_core.tools.ai_teacher_eval --provider anthropic --json fd03-golden.json` from
`services/core-api`. Without the §9.1 configuration it refuses (exit 2, nothing sent). It sends only
synthetic, published lesson contexts through the production path. All of these must pass, in this order:

| Step | Pass threshold | Source / status |
| --- | --- | --- |
| Scripted gate set (unsafe refused / safe accepted) | 100% / 100% | [`AI_TEACHER_EVALUATION.md` §8](../../AI_TEACHER_EVALUATION.md); built |
| Real outputs the gate accepts, on safe authored content | ≥ 90%, **in each locale (en, ur)** | §9 sets ≥ 90% overall (`REAL_MODEL_ACCEPT_MIN`). **GAP:** the harness reports one combined rate, so the per-locale split must be computed from the JSON or added |
| Real calls refused, truncated or errored | 0 | §9; built |
| Human transcript review of every accepted output | All reviewed; zero factual errors, answer leaks or age-inappropriate outputs | §9 requires review of all. The zero-defect bar is proposed here; the founder records it at item 6 |
| External red team (EV-08) against the real model with the gate | Zero unsafe outputs reach the `generation` block | Proposed here. **GAP:** the real-model red-team run is not scripted (the red-team set runs on scripted outputs only) |
| Pilot cohort | Gate rejection rate, cost per learner and rephrase rate tracked from the ledger and safety events | §8 measurement plan |

The founder may tighten any threshold when recording item 6. A failure reopens FD-03. It never lowers
a threshold.

### 9.6 Rate limits and cost controls

- **Per learner:** calls, tokens and cost per UTC day (`LearnerQuota`), counted in the shared ledger
  across instances. The cost is computed from the response `usage` at the constant list prices × 1.1.
  Refused and truncated calls are billed and counted. Exhaustion, or an unreadable ledger, serves the
  authored engine.
- **Recommended envelope:** $0.10 per learner per day; 20 calls; 20,000 tokens (§5).
- **Provider limits:** a 429 maps to `ProviderRateLimitedError` and serves the authored response.
  Anthropic rate limits are shared across geos.
- **GAPs:**
  - The quota is checked before the call, so concurrent instances can overshoot by at most
    instances − 1 calls for one learner.
  - There is no platform-wide daily spend cap in code. Set a workspace spend limit at setup if the
    Console offers one (UNVERIFIED for this organisation), and alert on ledger totals.

### 9.7 Failure handling and offline fallback

- Timeout (15 s), connection error, 429, API error, refusal (`stop_reason: "refusal"`) or truncation
  leads to the authored response labelled `fallback: "authored"`. The SDK retries a transport error or
  429 at most once (`max_retries=1`). Refusals and truncations are not retried. The child sees the same
  lesson, never an error.
- With the flag off, the kill switch engaged, no consent, an exhausted quota or no provider, the
  response is byte-identical to the deterministic teacher.
- **Offline:** generative rephrasing is `disabled_offline`, always (`ai_teacher.offline_capabilities()`;
  [`AI_TEACHER_OFFLINE.md`](../../AI_TEACHER_OFFLINE.md)). Explanation, guided teaching, hints and
  misconception correction work offline from the packaged lesson. Grading and mentor escalation queue
  until reconnection.

## 10. Sources and re-verification log

All read on **2026-11-17**. The 2026-10-25 reads are superseded where they differ.

| Fact | Source |
| --- | --- |
| Sonnet 5.5 / Haiku 5.5 prices; Haiku 5.5 price rises over 100,000 tokens; 1.1× `us`; Bedrock and Vertex regional +10% | <https://platform.claude.com/docs/en/about-claude/pricing.md> |
| `inference_geo` `us`/`global` only; workspace geo `us` only; Claude Platform on AWS and Google Cloud (Anthropic managed) also `us`/`global` | <https://platform.claude.com/docs/en/manage-claude/data-residency.md> |
| ZDR scope, ineligible features not blocked, Covered Models, flagged content kept 2 years, default "not retained" | <https://platform.claude.com/docs/en/manage-claude/api-and-data-retention.md> |
| 30-day default deletion; 2-year flagged content; 7-year classification scores (updated 2026-07-01) | <https://privacy.claude.com/en/articles/7996866-how-long-do-you-store-my-organization-s-data> |
| 512-token minimum cacheable prompt for Sonnet 5.5 and Haiku 5.5 | <https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md> |
| Minors guidelines (updated 2026-03-16) | <https://support.claude.com/en/articles/9307344> |
| Usage Policy effective 2026-11-12: products serving minors; high-risk education area; educational-content exclusion | <https://www.anthropic.com/legal/aup> |
| No training on Customer Content (effective 2025-06-17) | <https://www.anthropic.com/legal/commercial-terms> |
| DPA: processor role, SCC Modules 2/3 (effective 2025-02-24) | <https://www.anthropic.com/legal/data-processing-addendum> |
| Bedrock: Sonnet 5.5 is Global only from ap-south-1, ap-south-2 and me-central-1 | <https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock> |
| Vertex (Google managed): regional endpoints serve Sonnet 4.6 and earlier only | <https://platform.claude.com/docs/en/build-with-claude/claude-models-on-google-cloud/google-managed> |
| OpenAI regions and models for regional processing; +10% uplift | <https://developers.openai.com/api/docs/guides/data-residency> |
| OpenAI ZDR, ineligible endpoints, 30-day abuse logs | <https://developers.openai.com/api/docs/guides/your-data> |
| OpenAI prices (`gpt-6.1-sol` $2 / $10, `gpt-6-luna` $0.10 / $0.50) and tiers | <https://developers.openai.com/api/docs/pricing>, <https://developers.openai.com/api/docs/models> |
| OpenAI under-18 guidance | <https://developers.openai.com/api/docs/guides/safety-checks/under-18-api-guidance> |
| OpenAI Services Agreement parental-consent clause | <https://openai.com/policies/services-agreement/>: **UNVERIFIED** (HTTP 403) |
| Azure `gpt-6.1-sol` deployment types by region (page updated 2026-10-19) | <https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability> |
| Google Service Terms §20(d) under-18 restriction | <https://cloud.google.com/terms/service-terms> |
| Gemini API: 18+ and no under-18 services (effective 2026-03-23); Gemini 3.8 Flash prices | <https://aistudio.google.com/docs/terms>, <https://aistudio.google.com/docs/pricing> |
| Vertex Gemini regional pricing and South Asia / Gulf regions | <https://cloud.google.com/vertex-ai/generative-ai/pricing>: **UNVERIFIED** (page did not render). Not decision-relevant: Google is excluded on terms |
