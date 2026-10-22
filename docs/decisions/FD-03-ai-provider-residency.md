# Decision Brief FD-03 — AI Provider, Inference Residency, and Retention

**Status:** Open — owner decision required · **Owners:** Founder + Legal (data protection) ·
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

## Recommendation

**(c) hybrid, staged.** For pilot scale, start with **(a)** for lesson-grounded explanation only. It
must be region-pinned to the FD-02 region (or the nearest lawful one), with a signed zero-retention
and no-training addendum and audit rights. No child free-text is sent; only lesson content and option
choices. Add the in-region (b) component when free-text tutoring or distress classification enters
scope. This keeps the first real integration's data exposure to curriculum content the platform
already publishes.

## What approval must include before any learner-derived text is transmitted

1. The provider and region named, with the lawful cross-border-transfer basis (FD-01/FD-02).
2. A signed zero-retention / no-training addendum with audit rights.
3. A DPIA covering the AI path (EV-03).
4. An external AI red-team review of the gate (EV-08).
5. The per-learner cost envelope set (FD-07), so quotas have real values.
6. Golden-set results on the chosen model meeting [`AI_TEACHER_EVALUATION.md`](../../AI_TEACHER_EVALUATION.md) thresholds.

Until all six are recorded, the provider adapter stays inert. It refuses to construct without
explicit configuration, and that configuration is not set in any environment.
