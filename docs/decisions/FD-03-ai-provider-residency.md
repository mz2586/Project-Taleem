# Decision Brief FD-03 — AI Provider, Inference Residency, and Retention

**Status:** Open — owner decision required · **Recommendation:** Anthropic Claude Sonnet 5.5, first-party
API, `inference_geo: "us"`, under Zero Data Retention (re-verified against official sources 2026-10-25) ·
**Owners:** Founder + Legal (data protection) · **Prepared:** 2026-10-22, rewritten 2026-10-25 ·
**Register entry:** [`FOUNDER_DECISIONS.md` § FD-03](../../FOUNDER_DECISIONS.md)

## The decision

Which AI inference provider, in which region, under which retention and training terms, may receive
text derived from a child's learning session. And which categories of text may never leave our own
infrastructure.

## 1. What actually needs a provider

| Capability | Needs a real model? | Today |
| --- | --- | --- |
| Lesson teaching, worked steps, hints, mastery, path, homework marking against a key, unit checks, progression, report cards | No | Deterministic engine, live in production |
| "Explain it another way": a child-level rephrase of the authored passages already chosen | **Yes** (explanation tier) | Built behind `LLMGateway`; flag `ai_teacher.generative_rephrase` off; the adapter refuses to construct without approval |
| Checking model output for grounding and age appropriateness with a second, cheap model | Optional (classification tier) | No call site; the lexical and semantic gate runs in our own code |
| Marking short written answers; replying to anything a child types | Yes, **but blocked separately**: child free text must first be screened by an in-house distress classifier (FD-04, AR-C-07) | Not built; not part of this approval |

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
  text, other learners' data.

Counsel should confirm a judgement we hold but cannot make ourselves: that this payload is not
personal data of the child. The rest of this brief is written as if it were, to stay conservative.

## 3. Providers compared (official sources, read 2026-10-25)

| | **Anthropic Claude** (first-party API) | OpenAI API / Azure OpenAI | Google Gemini (Vertex / "Gemini Enterprise Agent Platform") |
| --- | --- | --- | --- |
| Model for this job | `claude-sonnet-5-5` | `gpt-6.1-sol` | Gemini 3.5 Flash / 3.8 Flash |
| List price, per 1M tokens in / out | $2 / $10 (cache hit $0.10); ×1.1 with `inference_geo: "us"` | $2 / $10 (cached $0.10); +10% regional | $1.65 / $9.90 (3.5 Flash, regional) |
| Use by children | **Permitted** with safeguards: "Products serving minors … must comply with the additional guidelines outlined in our Support article and all applicable laws" ([AUP](https://www.anthropic.com/legal/aup), [Guidelines for Organizations Serving Minors](https://support.claude.com/en/articles/9307344)) | Permitted with conditions: no minors "without consent from their parent or guardian" ([Services Agreement §3.3(c)](https://openai.com/policies/services-agreement/)); ZDR required before processing under-13 personal data | **Prohibited**: no service "directed towards or is likely to be accessed by individuals under the age of 18" ([Service Specific Terms, Generative AI §(d)](https://cloud.google.com/terms/service-terms)) |
| Processing region options | `us` or `global` only; workspace data at rest `us` only ([data residency](https://platform.claude.com/docs/en/manage-claude/data-residency.md)) | US, EEA, UAE processing (UAE: older models only, extra approval); India is storage only ([your data](https://platform.openai.com/docs/guides/your-data)) | Per-model commitments; India (asia-south1) for 3.5 Flash; no Gulf region |
| Training on our data | No ("may not train models on Customer Content", [Commercial Terms](https://www.anthropic.com/legal/commercial-terms)) | No, unless opted in | No, without permission |
| Zero retention | Per-org ZDR via sales. Prompt caching is ZDR-eligible; **Batch, Files and code execution are not** ([retention](https://platform.claude.com/docs/en/manage-claude/api-and-data-retention.md)) | Sales-approved ZDR | Disable caching, `store=false`, no grounding, plus a negotiated Master Agreement |
| What is kept even under ZDR | Content flagged by trust and safety: up to 2 years; classification scores up to 7 years | CSAM-flagged images and files | Flagged prompts up to 90 days, unless a Master Agreement exempts them |
| Processor DPA with SCCs | Yes ([DPA](https://www.anthropic.com/legal/data-processing-addendum)) | Yes | Yes |
| In our code today | Adapter built, 86 tests, inert | Nothing | Nothing |

**Google is excluded.** Its terms forbid the use outright. **No provider processes inside Pakistan**, and
no provider offers a current mid-tier model in-region anywhere in South Asia or the Gulf. Bedrock and
Azure route Sonnet 5.5 / GPT-6.1 from Mumbai or the UAE only through *global* profiles, which may
process anywhere. Whatever is chosen, child-session text crosses a border. The real choice is between
a **named jurisdiction** and **anywhere**.

## 4. Recommendation

**Anthropic, first-party Claude API. `claude-sonnet-5-5` for explanations. A dedicated workspace with
`allowed_inference_geos: ["us"]` and `default_inference_geo: "us"`. Zero Data Retention for the
organisation. No Batch, Files, code execution or Console use with this workspace.**

Why this, for Taleem:

1. **The terms allow a children's school.** Anthropic sets out the safeguards it requires for products
   serving minors: age-appropriate moderation, AI disclosure, monitoring and reporting, and published
   compliance with child-privacy law. It also offers a child-safety system prompt. Taleem already
   meets most of these by design: consent-gated enrolment, an AI-teacher label on every surface,
   generated text marked `generated: true`, an output gate and safeguarding review. OpenAI also allows
   it, but needs parental consent for every minor and ZDR for under-13s. Taleem's model consent
   (`ai_teaching`) would satisfy the first, and ZDR the second. Either works. Google does not.
2. **One named jurisdiction instead of "anywhere".** `inference_geo: "us"` pins inference to the US, and
   the workspace stores at rest in the US. That gives counsel one country and one processor DPA for
   the transfer assessment. `global` (and every Bedrock or Azure route reachable from the region)
   gives an unknown set of countries.
3. **ZDR fits the design.** Prompt caching stays usable under ZDR. The features ZDR excludes (Batch,
   Files, code execution) are ones Taleem does not need. Default retention without ZDR is unclear:
   the docs say "not retained by default", while the privacy centre says deleted "within 30 days".
   ZDR removes the question.
4. **Same price as the alternative, and already built.** Sonnet 5.5 and GPT-6.1 Sol have the same list
   price. The Claude adapter, its data-minimisation guard, cost ledger, fail-closed boot and
   evaluation harness exist and are tested. Choosing OpenAI would mean a new adapter, new tests and a
   new evaluation, for no residency gain: the OpenAI UAE option covers only older models.
5. **Urdu quality is not assumed.** It is a release gate (§7 item 6), measured on our golden set.
   If Sonnet 5.5 fails it, the decision is reopened rather than lowered.

**Rejected:** self-hosting an open-weight model (option b) *for explanations*. Its Urdu quality and child
safety are unmeasured, and it puts GPU operations and on-call into a free school before the first
pilot. Option (b) stays the plan for the **in-house distress classifier** that must screen child free
text (FD-04). That is a different capability, and this approval does not cover it.

## 5. Expected cost per learner

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
per day.** The quota rows above that ($0.26 a day in the worst case) are therefore capped. That bounds the heavy month at $2.00 over 20 days, and the theoretical maximum at $3.10 if
used on all 31 days. On exhaustion the child gets the authored explanation, which is the same lesson
with no AI rephrase.

Uncertain costs:

- Urdu token counts. The first real run measures them exactly from `usage`.
- How often children actually press "explain it another way". The pilot measures this.
- Gate-rejected calls, which are billed.
- Future price changes. The constants in the adapter were checked 2026-10-25 and must be re-checked
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
  2 years). Because Taleem sends only authored lesson text, flagging should be rare. The ledger
  records the request id, so any flag can be traced to one call and one lesson, never to a child.
- **The model never talks to the child.** It rephrases authored text. The gate checks grounding,
  answer leaks, age band, disallowed content, locale and arithmetic/polarity consistency. A
  rejection serves the authored text. There is no model call offline, and no model call without live
  `ai_teaching` consent.
- **Anthropic's obligations on us** (Guidelines for Organizations Serving Minors):
  - age-appropriate moderation (the gate);
  - AI disclosure (in place);
  - monitoring and reporting (safeguarding queue, audit log);
  - **a public statement of child-privacy-law compliance on the website (not yet published, needs
    counsel)**;
  - adopting Anthropic's child-safety system prompt (to request at signing).
  Anthropic may audit, and may suspend the account for non-compliance.

## 7. The exact approval required

Record each item, with its date and reference, in `FOUNDER_DECISIONS.md` § FD-03. The adapter stays
inert until `TALEEM_AI_FD03_APPROVAL_REF` names that record.

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
6. **Engineering, after items 1–4:** run the golden set against the real model (thresholds in
   [`AI_TEACHER_EVALUATION.md` §9](../../AI_TEACHER_EVALUATION.md)), then a human transcript review.
   Only then is the flag turned on, for a pilot cohort first.

**Not sent until all six are recorded:** any request to any provider from any environment that has
learners. The golden-set run (item 6) uses only the synthetic published lesson and authored
contexts. No child data is involved.

## 8. What continues without approval

- Semantic consistency check in the gate (arithmetic, polarity, number provenance).
- Red-team golden set across ten unsafe-output categories, in English and Urdu.
- Price constants kept current. The Sonnet 5.5 cache-read price was corrected to $0.10 on 2026-10-25.
- Adopting the child-safety system prompt into `SYSTEM_PROMPT` once Anthropic provides it. This is a
  reviewed change.
- In-house distress classifier design (FD-04), which is the prerequisite for any free-text AI feature.
- Pilot measurement plan: rephrase-request rate, gate rejection rate, cost per learner from the
  ledger.

### Switching it on once approved: configuration only

The Claude adapter is built and tested (`services/core-api/src/taleem_core/ports/llm_anthropic.py`,
`tests/test_ai_teacher_anthropic_adapter.py`). No code change is needed after approval. Set these in
the target environment's secret store, never in the repository:

| Setting | Value | Why |
| --- | --- | --- |
| `TALEEM_AI_PROVIDER` | `anthropic` | Selects the Claude adapter. |
| `TALEEM_AI_ANTHROPIC_API_KEY` | the workspace API key | A dedicated variable. The SDK's own `ANTHROPIC_API_KEY`, profile and federation discovery are never used, so a key already on a machine cannot switch this on. |
| `TALEEM_AI_INFERENCE_GEO` | `us` | Explicit residency pin (first-party API `inference_geo`, billed at a premium). `global` is refused because it is not a pin. Supporting another geography is a reviewed code change (`ALLOWED_INFERENCE_GEOS`). Bedrock offers no in-region Sonnet 5.5 near Pakistan (global routing only), and Google's terms forbid under-18 services, so neither is an alternative route. |
| `TALEEM_AI_ZDR_CONFIRMED` | `true` | The founder's attestation that the zero-retention / no-training addendum covers `claude-sonnet-5-5` and `claude-haiku-5-5` (§7 item 2). |
| `TALEEM_AI_FD03_APPROVAL_REF` | the approval record id, e.g. `FD-03/2026-11-01` | Ties the running configuration to the recorded approval of all six items in §7. 3 to 64 characters from `A-Z a-z 0-9 . _ : / -`. |
| `TALEEM_AI_LEARNER_DAILY_COST_MICROS` | the FD-07 envelope, in micro-USD per learner per UTC day | Required in production with this provider (§7 item 4). |
| `TALEEM_AI_LEARNER_DAILY_CALLS` / `_TOKENS` | FD-07 values | Existing per-learner quotas (defaults 20 calls / 20,000 tokens). |
| `TALEEM_AI_TIMEOUT_SECONDS` | optional, default `15` | Per-call timeout; one retry, then the authored response. |
| `TALEEM_ENABLED_FLAGS` | add `ai_teacher.generative_rephrase` | The tier stays off until this flag is on. It can be rolled out per learner. |

Behaviour:

- **Partial configuration fails closed.** In production the app refuses to boot if
  `TALEEM_AI_PROVIDER=anthropic` is set without every setting above. In other environments it logs
  `ai_provider_not_approved` and stays on the deterministic engine.
- **Models.** Explanations use `claude-sonnet-5-5` with thinking off (`between_tools`) and effort
  `medium`. `claude-haiku-5-5` is reserved for the classification tier, which has no call site yet.
  The server-side refusal `fallbacks` parameter is deliberately not used, because it would run the
  request on a model this approval does not cover. A refusal serves the authored response instead.
- **Sent.** Only the grounded rephrase prompt (fixed instructions plus published `LessonView`
  passages), an authored selected option when one is supplied, and a fresh random request id
  (`metadata.user_id`). The adapter checks this itself before sending. Child free text,
  identifiers, family codes, contact details, and the learner's ref are refused.
- **Prompt caching.** The system prompt and the lesson prompt carry `cache_control`, so learners on
  the same lesson share the cached prefix. Prompts shorter than the model's minimum cacheable
  length are not cached; the request is otherwise the same.
- **Cost.** The adapter records each call's cost in the usage ledger from the response `usage`
  tokens. That includes refused or truncated calls, because they are billed. The list prices and
  the `us` residency multiplier (1.1×) are constants in the adapter: **check them against the
  pricing page at approval.**
- **§7 item 6 evidence.** With the settings above present, run
  `python -m taleem_core.tools.ai_teacher_eval --provider anthropic --json fd03-golden.json` from
  `services/core-api`. It refuses (exit 2, nothing sent) without the configuration. The thresholds
  are in [`AI_TEACHER_EVALUATION.md` §9](../../AI_TEACHER_EVALUATION.md). The accepted outputs in
  the JSON need human transcript review before the flag is enabled for children.
