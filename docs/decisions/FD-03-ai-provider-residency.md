# Decision Brief FD-03 — AI Provider, Inference Residency, and Retention

**Status:** Open — owner decision required · **Recommendation:** Claude, region-pinned, ZDR (2026-10-24) · **Owners:** Founder + Legal (data protection) ·
**Prepared:** 2026-10-22 · **Register entry:** [`FOUNDER_DECISIONS.md` § FD-03](../../FOUNDER_DECISIONS.md)

## The decision

Which AI inference provider(s), in which region(s), under which retention and training terms, may
receive text derived from a child's learning session — and which categories of text may never leave
our own infrastructure.

## Why it blocks, and what it blocks

| Blocked | Not blocked (built and testable now) |
| --- | --- |
| Connecting any real model to the AI Teacher | `LLMGateway` port, feature flag (default off), `ai_teaching` consent check, kill-switch gating |
| Sending any learner-derived text off-platform | Grounding (prompt built only from a published `LessonView`) and the output safety gate |
| Measuring real tutoring quality or real cost | Stub gateway, golden-set evaluation of the gate, per-learner cost ledger and quotas |

Until this is decided the production AI path stays the deterministic, curriculum-only engine. That
is a complete, safe product behaviour, not a degraded one.

## What is sent, and what never is

Whatever is chosen, the gateway contract enforces the following regardless of provider:

- **Sent:** published lesson content (title, explanation, worked steps, the current item and its
  authored hints) and the learner's selected option for the current item.
- **Never sent:** names, family codes, guardian data, identifiers beyond a per-request opaque id,
  free-text the child typed (until a distress classifier runs *in our own infrastructure* first —
  FD-04/AR-C-07), or any other learner's data.

## Options

| | (a) Hosted frontier API, region-pinned, zero-retention | (b) Self-hosted open-weight model in our own region | (c) Hybrid: (b) for classification and routine turns, (a) for complex explanations |
| --- | --- | --- | --- |
| **Residency** | Depends on the provider offering a region acceptable under FD-02; often UAE/EU/US only | Fully under our control; follows the FD-02 hosting choice | Sensitive classification stays in-region; only lesson-grounded, non-sensitive prompts leave |
| **Retention / training** | Contractual zero-retention and no-training; needs audit rights; not technically enforceable by us | No third party at all | Contractual for the (a) share only |
| **Safety** | Strong base models and provider safety layers, plus our gate | Weaker models; our gate does more work; needs our own red-teaming | Best of both if the router is correct; most moving parts |
| **Urdu quality** | Generally strongest | Variable; must be measured on our golden set | Strong where it matters |
| **Cost** | Per-token; predictable with quotas; scales with use | Fixed GPU cost; cheap at scale, expensive at pilot scale | Mixed |
| **Operations** | Minimal | GPU hosting, model updates, on-call | Highest |

## Recommendation (updated 2026-10-24 for the AI-led mission)

The mission makes the AI the teacher, so this decision now gates the core product. The
deterministic engine stays as the safe floor, not the destination.

**Recommended: option (a) now, (c) later. Anthropic Claude, region-pinned, under a
zero-data-retention agreement, as two tiers behind the existing `LLMGateway`:**

| Tier | Model | Used for | Sent |
| --- | --- | --- | --- |
| Explanation | Claude Sonnet 5.5 (`claude-sonnet-5-5`, list price $2 / $10 per million input / output tokens) | Lesson-grounded explanations, alternative explanations, worked-example rephrasing, misconception-specific feedback | Published lesson content + the learner's selected answer (as today) |
| Routing / classification | Claude Haiku 5.5 (`claude-haiku-5-5`, $0.10 / $0.50) | Cheap checks on outputs (grounding, age appropriateness) before they reach a child; later, marking short written answers against a rubric | Model output, rubric and answer key, never identity |

Why this option:

1. **It matches the repository.** The authoring brief fixes a Claude-default gateway, and the
   golden-set, safety-gate and cost-ledger code is built around it.
2. **Urdu quality.** Hosted frontier models are the strongest option for Urdu. A self-hosted
   open-weight model would need our own red-teaming before it is safe for children.
3. **Residency is available.** The first-party API and Claude Platform on AWS support an
   `inference_geo` setting for data residency, priced at a premium. Amazon Bedrock and Google
   Vertex AI pin inference to a cloud region instead. Pick whichever matches the FD-02 hosting
   region.
4. **Retention.** Zero-data-retention is a contractual arrangement with Anthropic. **The founder
   must confirm it is in place for these models before go-live.** Note that Claude Fable-tier
   models are excluded from ZDR unless Anthropic expressly authorizes them, so they are **not**
   recommended here.
5. **Cost fits a free school.** Prompts are mostly the cached lesson body, which is cheap with
   prompt caching. The per-learner ledger and quotas (FD-07) cap spend.

**Still not sent, regardless of provider:** names, family codes, guardian data, identifiers beyond
a per-request opaque id, and **child free text** until an in-region distress classifier screens it
first (option (b) component, FD-04). Written homework answers are child free text: AI marking of
them waits for that classifier. Until then they are marked automatically only where an exact
answer key exists, and otherwise wait for review.

## What approval must include before any learner-derived text is transmitted

1. The provider and region named, with the lawful cross-border-transfer basis (FD-01/FD-02).
2. A signed zero-retention / no-training addendum with audit rights.
3. A DPIA covering the AI path (EV-03).
4. An external AI red-team review of the gate (EV-08).
5. The per-learner cost envelope set (FD-07), so quotas have real values.
6. Golden-set results on the chosen model meeting [`AI_TEACHER_EVALUATION.md`](../../AI_TEACHER_EVALUATION.md) thresholds.

Until all six are recorded, the provider adapter stays inert. It refuses to construct without
explicit configuration, and that configuration is not set in any environment.

### Switching it on once approved: configuration only

The Claude adapter is built and tested (`services/core-api/src/taleem_core/ports/llm_anthropic.py`,
`tests/test_ai_teacher_anthropic_adapter.py`). No code change is needed after approval. Set these in
the target environment's secret store, never in the repository:

| Setting | Value | Why |
| --- | --- | --- |
| `TALEEM_AI_PROVIDER` | `anthropic` | Selects the Claude adapter. |
| `TALEEM_AI_ANTHROPIC_API_KEY` | the workspace API key | A dedicated variable. The SDK's own `ANTHROPIC_API_KEY`, profile and federation discovery are never used, so a key already on a machine cannot switch this on. |
| `TALEEM_AI_INFERENCE_GEO` | `us` | Explicit residency pin (first-party API `inference_geo`, billed at a premium). `global` is refused because it is not a pin. Supporting another geography is a reviewed code change (`ALLOWED_INFERENCE_GEOS`). If FD-02 picks Bedrock or Vertex instead, that needs a separate adapter. |
| `TALEEM_AI_ZDR_CONFIRMED` | `true` | The founder's attestation that the zero-retention / no-training addendum (item 2) covers `claude-sonnet-5-5` and `claude-haiku-5-5`. |
| `TALEEM_AI_FD03_APPROVAL_REF` | the approval record id, e.g. `FD-03/2026-11-01` | Ties the running configuration to the recorded approval of all six items. 3 to 64 characters from `A-Z a-z 0-9 . _ : / -`. |
| `TALEEM_AI_LEARNER_DAILY_COST_MICROS` | the FD-07 envelope, in micro-USD per learner per UTC day | Required in production with this provider (item 5). |
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
- **Item 6 evidence.** With the settings above present, run
  `python -m taleem_core.tools.ai_teacher_eval --provider anthropic --json fd03-golden.json` from
  `services/core-api`. It refuses (exit 2, nothing sent) without the configuration. The thresholds
  are in [`AI_TEACHER_EVALUATION.md` §9](../../AI_TEACHER_EVALUATION.md). The accepted outputs in
  the JSON need human transcript review before the flag is enabled for children.
