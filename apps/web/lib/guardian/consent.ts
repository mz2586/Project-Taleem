// Consent journey — the pure rules behind the guardian's consent form. No React; unit-tested.
//
// What the backend does (verified against services/core-api identity/domain/consent.py):
//
// - Consent state is a FOLD over an append-only history. A grant ADDS its scopes; a withdrawal
//   REMOVES its scopes. So "save the boxes that are ticked" is not a grant of the ticked set — a
//   grant of {learning_data, voice_audio} leaves an earlier `ai_teaching` grant in place. Unticking
//   a box therefore has to become a withdrawal of that scope, which is what `planConsentChange`
//   computes. (The previous form sent only a grant, so unticking a box silently did nothing.)
// - A grant must include every required scope (today: `learning_data`), or it is a 422.
// - Withdrawing with no scope list withdraws everything — the guardian's stop button. When the
//   remaining consent no longer permits sign-in, the server ends every live session for the child
//   at once ("your child will be signed out"). Nothing is deleted: history is append-only.
// - Consent recorded under a superseded policy version does not permit sign-in; the guardian has to
//   agree again. That is a fresh grant, even when no box changed.
// - Only `learning_data` is enforced by the server today (the sign-in gate). The optional scopes are
//   recorded faithfully but no backend feature checks them yet, so the copy below describes what a
//   scope *covers* and never promises a behaviour the server does not implement.

import type { MessageKey } from "../i18n/messages";
import type { ConsentScope, ConsentState, PolicyDescriptor } from "../session/types";

/** Every scope this app can explain in plain language. */
export const KNOWN_SCOPES: readonly ConsentScope[] = [
  "learning_data",
  "ai_teaching",
  "voice_audio",
  "progress_sharing",
];

export function isKnownScope(value: string): value is ConsentScope {
  return (KNOWN_SCOPES as readonly string[]).includes(value);
}

/**
 * Used only when `GET /v1/identity/policy` cannot be reached. It mirrors the server's vocabulary
 * (learning_data required, the rest optional); `policy_version` is empty because this client does
 * not know which version is current — the server stamps the version on every grant.
 */
export const FALLBACK_POLICY: PolicyDescriptor = {
  policy_version: "",
  scopes: KNOWN_SCOPES.map((key) => ({ key, required: key === "learning_data" })),
};

export interface ScopeView {
  key: ConsentScope;
  required: boolean;
  granted: boolean;
  /** Short name of the permission. */
  title: MessageKey;
  /** One or two short sentences: what saying yes allows. */
  what: MessageKey;
  /** What changes if the guardian says no / takes it back. */
  ifOff: MessageKey;
}

export function scopeCopy(key: ConsentScope): Pick<ScopeView, "title" | "what" | "ifOff"> {
  return {
    title: `guardian.consent.scopes.${key}.title`,
    what: `guardian.consent.scopes.${key}.what`,
    ifOff: `guardian.consent.scopes.${key}.ifOff`,
  };
}

export type ConsentStatus =
  /** No consent has ever been recorded. The child cannot sign in yet. */
  | "not-given"
  /** Current-policy consent covering every required scope: the child can sign in. */
  | "given"
  /** Consent exists but under an older policy: the guardian must agree again. */
  | "policy-changed"
  /** Consent was given once and has been taken back. */
  | "withdrawn";

export interface ConsentViewModel {
  status: ConsentStatus;
  permitsSignIn: boolean;
  required: ScopeView[];
  optional: ScopeView[];
  /** Scopes the server's policy lists that this app has no explanation for. */
  unexplained: string[];
  /**
   * Whether the form may submit a grant. False when the policy REQUIRES a scope this app cannot
   * explain: asking a guardian to agree to something we cannot describe is not consent.
   */
  canGrant: boolean;
  /** The ticked set the form should start from. */
  initialSelection: ConsentScope[];
}

export function consentStatus(consent: ConsentState): ConsentStatus {
  if (consent.permits_sign_in) return "given";
  if (consent.granted_scopes.length > 0 && !consent.policy_current) return "policy-changed";
  if (consent.granted_scopes.length === 0 && consent.last_change_at > 0) return "withdrawn";
  if (consent.granted_scopes.length === 0) return "not-given";
  // Some scopes granted, policy current, yet no sign-in: a required scope is missing (e.g. only
  // the required one was withdrawn). For the guardian that is the same as taken back.
  return "withdrawn";
}

export function consentViewModel(
  policy: PolicyDescriptor | null,
  consent: ConsentState,
): ConsentViewModel {
  const source = policy && policy.scopes.length > 0 ? policy : FALLBACK_POLICY;
  const granted = new Set(consent.granted_scopes);
  const required: ScopeView[] = [];
  const optional: ScopeView[] = [];
  const unexplained: string[] = [];
  let requiredUnexplained = false;

  for (const scope of source.scopes) {
    if (!isKnownScope(scope.key)) {
      unexplained.push(scope.key);
      if (scope.required) requiredUnexplained = true;
      continue;
    }
    const view: ScopeView = {
      key: scope.key,
      required: scope.required,
      granted: granted.has(scope.key),
      ...scopeCopy(scope.key),
    };
    (scope.required ? required : optional).push(view);
  }

  const status = consentStatus(consent);
  // A form for a child with no live consent starts with only the required scopes ticked: consent
  // is something a guardian gives, not something they must notice and remove. With live (or
  // superseded) consent it starts from what was agreed.
  const initialSelection: ConsentScope[] = [
    ...required.map((s) => s.key),
    ...optional.filter((s) => s.granted && status !== "withdrawn").map((s) => s.key),
  ];

  return {
    status,
    permitsSignIn: consent.permits_sign_in,
    required,
    optional,
    unexplained,
    canGrant: !requiredUnexplained && required.length > 0,
    initialSelection,
  };
}

// ---- turning ticked boxes into API calls -------------------------------------------------------

export type ConsentChangeKind =
  | "none"
  | "grant"
  | "withdraw-some"
  | "grant-and-withdraw"
  | "withdraw-all";

export interface ConsentChange {
  kind: ConsentChangeKind;
  /** Body `scopes` for `POST /consents` (always includes every required scope), or null. */
  grant: ConsentScope[] | null;
  /** Body `scopes` for `POST /consents:withdraw`, or null. Ignored when `withdrawAll`. */
  withdraw: ConsentScope[] | null;
  /** Send `POST /consents:withdraw` with no scope list: everything. */
  withdrawAll: boolean;
  /** Whether this change leaves the child unable to sign in (and signs them out now). */
  signsOut: boolean;
  /** Any withdrawal is confirmed first; a pure grant is not. */
  needsConfirmation: boolean;
}

const NO_CHANGE: ConsentChange = {
  kind: "none",
  grant: null,
  withdraw: null,
  withdrawAll: false,
  signsOut: false,
  needsConfirmation: false,
};

function ordered(scopes: Iterable<ConsentScope>): ConsentScope[] {
  const set = new Set(scopes);
  return KNOWN_SCOPES.filter((s) => set.has(s));
}

/** The guardian's stop button: withdraw every scope. */
export function planWithdrawAll(vm: ConsentViewModel): ConsentChange {
  const anyGranted = [...vm.required, ...vm.optional].some((s) => s.granted);
  if (!anyGranted) return NO_CHANGE;
  return {
    kind: "withdraw-all",
    grant: null,
    withdraw: null,
    withdrawAll: true,
    signsOut: true,
    needsConfirmation: true,
  };
}

/**
 * What to send so that the child's consent ends up exactly `desired`.
 *
 * - Leaving out a required scope means "stop": withdraw everything.
 * - Optional scopes that were granted and are now unticked are withdrawn by name.
 * - A grant is sent when something new is ticked, when there is no live consent yet, or when the
 *   policy changed (agreeing again) — always with the full desired set, which is harmless because
 *   grants are additive.
 */
export function planConsentChange(
  vm: ConsentViewModel,
  desired: Iterable<ConsentScope>,
): ConsentChange {
  const want = new Set(desired);
  const all = [...vm.required, ...vm.optional];
  const granted = new Set(all.filter((s) => s.granted).map((s) => s.key));

  if (vm.required.some((s) => !want.has(s.key))) return planWithdrawAll(vm);

  // Only scopes the form offers can be asked for.
  const offered = new Set(all.map((s) => s.key));
  for (const scope of [...want]) if (!offered.has(scope)) want.delete(scope);

  const toWithdraw = ordered([...granted].filter((s) => !want.has(s)));
  const toAdd = [...want].filter((s) => !granted.has(s));
  const mustReagree = vm.status === "policy-changed" || !vm.permitsSignIn;
  const grant = vm.canGrant && (toAdd.length > 0 || mustReagree) ? ordered(want) : null;
  const withdraw = toWithdraw.length > 0 ? toWithdraw : null;

  if (!grant && !withdraw) return NO_CHANGE;
  return {
    kind: grant && withdraw ? "grant-and-withdraw" : grant ? "grant" : "withdraw-some",
    grant,
    withdraw,
    withdrawAll: false,
    // Withdrawing optional scopes never removes a required one, so sign-in is unaffected.
    signsOut: false,
    needsConfirmation: withdraw !== null,
  };
}

// ---- the confirmation step -----------------------------------------------------------------------

export type ConsentFlowState =
  | { phase: "idle" }
  | { phase: "confirming"; change: ConsentChange }
  | { phase: "submitting"; change: ConsentChange }
  | { phase: "done"; change: ConsentChange }
  | { phase: "failed"; change: ConsentChange; error: MessageKey };

export type ConsentFlowEvent =
  | { type: "request"; change: ConsentChange }
  | { type: "confirm" }
  | { type: "cancel" }
  | { type: "succeeded" }
  | { type: "failed"; error: MessageKey }
  | { type: "retry" }
  | { type: "dismiss" };

export const IDLE: ConsentFlowState = { phase: "idle" };

/**
 * The consent-change state machine. A withdrawal always passes through `confirming`, where the
 * guardian is told what will happen; nothing is sent until they confirm. Events that make no sense
 * in the current phase (a double click on confirm, a stray cancel while submitting) are ignored
 * rather than corrupting the state.
 */
export function consentFlow(state: ConsentFlowState, event: ConsentFlowEvent): ConsentFlowState {
  switch (event.type) {
    case "request":
      if (state.phase === "submitting" || state.phase === "confirming") return state;
      if (event.change.kind === "none") return IDLE;
      return event.change.needsConfirmation
        ? { phase: "confirming", change: event.change }
        : { phase: "submitting", change: event.change };
    case "confirm":
      return state.phase === "confirming" ? { phase: "submitting", change: state.change } : state;
    case "cancel":
      return state.phase === "confirming" || state.phase === "failed" ? IDLE : state;
    case "succeeded":
      return state.phase === "submitting" ? { phase: "done", change: state.change } : state;
    case "failed":
      return state.phase === "submitting"
        ? { phase: "failed", change: state.change, error: event.error }
        : state;
    case "retry":
      return state.phase === "failed" ? { phase: "submitting", change: state.change } : state;
    case "dismiss":
      return state.phase === "done" ? IDLE : state;
  }
}

export interface ConfirmationCopy {
  title: MessageKey;
  /** Short sentences, read in order. */
  lines: MessageKey[];
  /** One line per scope being taken back (the scope's `ifOff`). */
  scopeLines: MessageKey[];
  confirm: MessageKey;
}

/** What the confirmation step says for a change. Short sentences for a limited-literacy reader. */
export function confirmationCopy(change: ConsentChange): ConfirmationCopy {
  if (change.withdrawAll) {
    return {
      title: "guardian.consent.confirm.allTitle",
      lines: [
        "guardian.consent.confirm.allSignedOut",
        "guardian.consent.confirm.allCannotSignIn",
        "guardian.consent.confirm.nothingDeleted",
        "guardian.consent.confirm.canUndo",
      ],
      scopeLines: [],
      confirm: "guardian.consent.confirm.allConfirm",
    };
  }
  return {
    title: "guardian.consent.confirm.someTitle",
    lines: ["guardian.consent.confirm.someStillLearns", "guardian.consent.confirm.canUndo"],
    scopeLines: (change.withdraw ?? []).map((s) => scopeCopy(s).ifOff),
    confirm: "guardian.consent.confirm.someConfirm",
  };
}

/** The polite notice after a change has been saved. */
export function doneNotice(change: ConsentChange): MessageKey {
  if (change.withdrawAll) return "guardian.consent.doneWithdrawnAll";
  if (change.withdraw && change.grant) return "guardian.consent.doneUpdated";
  if (change.withdraw) return "guardian.consent.doneWithdrawnSome";
  return "guardian.consent.doneGranted";
}

const STATUS_KEYS: Record<ConsentStatus, MessageKey> = {
  "not-given": "guardian.consent.status.notGiven",
  given: "guardian.consent.status.given",
  "policy-changed": "guardian.consent.status.policyChanged",
  withdrawn: "guardian.consent.status.withdrawn",
};

/** Status line for a learner's consent, for the family list and the dashboard. */
export function consentStatusKey(status: ConsentStatus): MessageKey {
  return STATUS_KEYS[status];
}
