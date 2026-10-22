import { describe, expect, it } from "vitest";

import { CATALOGS } from "../../i18n/messages";
import { translate } from "../../i18n/translate";
import type { PolicyDescriptor } from "../../session/types";
import {
  confirmationCopy,
  consentFlow,
  consentStatus,
  consentStatusKey,
  consentViewModel,
  doneNotice,
  FALLBACK_POLICY,
  IDLE,
  KNOWN_SCOPES,
  planConsentChange,
  planWithdrawAll,
  type ConsentFlowState,
} from "../consent";
import { consent, granted, POLICY_VERSION } from "./fixtures";

// What GET /v1/identity/policy returns today.
const POLICY: PolicyDescriptor = {
  policy_version: POLICY_VERSION,
  scopes: [
    { key: "learning_data", required: true },
    { key: "ai_teaching", required: false },
    { key: "voice_audio", required: false },
    { key: "progress_sharing", required: false },
  ],
};

describe("consentStatus", () => {
  it("is not-given before any consent record", () => {
    expect(consentStatus(consent())).toBe("not-given");
  });
  it("is given for live current-policy consent", () => {
    expect(consentStatus(granted(["learning_data"]))).toBe("given");
  });
  it("is policy-changed when consent predates the current policy", () => {
    expect(
      consentStatus(granted(["learning_data"], { policy_current: false, permits_sign_in: false, policy_version: "old" })),
    ).toBe("policy-changed");
  });
  it("is withdrawn when everything was taken back", () => {
    expect(consentStatus(consent({ last_change_at: 1_700_000_100 }))).toBe("withdrawn");
  });
  it("treats optional scopes left without the required one as withdrawn", () => {
    expect(consentStatus(granted(["voice_audio"]))).toBe("withdrawn");
  });
  it("has a status line for every status in both languages", () => {
    for (const status of ["not-given", "given", "policy-changed", "withdrawn"] as const) {
      expect(translate("en", consentStatusKey(status))).not.toContain("guardian.");
      expect(translate("ur", consentStatusKey(status))).not.toContain("guardian.");
    }
  });
});

describe("consentViewModel", () => {
  it("splits required from optional scopes, from the server policy", () => {
    const vm = consentViewModel(POLICY, consent());
    expect(vm.required.map((s) => s.key)).toEqual(["learning_data"]);
    expect(vm.optional.map((s) => s.key)).toEqual(["ai_teaching", "voice_audio", "progress_sharing"]);
    expect(vm.canGrant).toBe(true);
    expect(vm.unexplained).toEqual([]);
  });

  it("starts a new child with only the required scope ticked (consent is given, not assumed)", () => {
    expect(consentViewModel(POLICY, consent()).initialSelection).toEqual(["learning_data"]);
  });

  it("starts from what was agreed when consent is live", () => {
    const vm = consentViewModel(POLICY, granted(["learning_data", "voice_audio"]));
    expect(vm.initialSelection).toEqual(["learning_data", "voice_audio"]);
    expect(vm.optional.find((s) => s.key === "voice_audio")?.granted).toBe(true);
  });

  it("falls back to the built-in vocabulary when the policy is unavailable", () => {
    const vm = consentViewModel(null, consent());
    expect(vm.required.map((s) => s.key)).toEqual(["learning_data"]);
    expect(vm.optional).toHaveLength(3);
    expect(FALLBACK_POLICY.scopes.filter((s) => s.required).map((s) => s.key)).toEqual(["learning_data"]);
  });

  it("refuses to ask for consent to a required scope it cannot explain", () => {
    const policy = { ...POLICY, scopes: [...POLICY.scopes, { key: "biometrics" as never, required: true }] };
    const vm = consentViewModel(policy, consent());
    expect(vm.unexplained).toEqual(["biometrics"]);
    expect(vm.canGrant).toBe(false);
  });

  it("lists an unknown optional scope as unexplained but still allows the rest", () => {
    const policy = { ...POLICY, scopes: [...POLICY.scopes, { key: "camera" as never, required: false }] };
    const vm = consentViewModel(policy, consent());
    expect(vm.unexplained).toEqual(["camera"]);
    expect(vm.canGrant).toBe(true);
  });

  it("explains every known scope — title, what it allows, and what turning it off does — in every locale", () => {
    const vm = consentViewModel(POLICY, consent());
    for (const scope of [...vm.required, ...vm.optional]) {
      for (const locale of ["en", "ur"] as const) {
        for (const key of [scope.title, scope.what, scope.ifOff]) {
          const text = translate(locale, key);
          expect(text).not.toBe(key);
          // Limited-literacy copy: short sentences.
          for (const sentence of text.split(/[.۔]/)) expect(sentence.trim().split(/\s+/).length).toBeLessThanOrEqual(20);
        }
      }
    }
    expect(KNOWN_SCOPES.every((s) => s in CATALOGS.ur.guardian.consent.scopes)).toBe(true);
  });

  it("says withdrawing the required scope signs the child out", () => {
    const required = consentViewModel(POLICY, consent()).required[0]!;
    expect(translate("en", required.ifOff)).toMatch(/signed out/);
  });
});

describe("planConsentChange", () => {
  it("grants the required scope plus ticked optional scopes for a new child", () => {
    const vm = consentViewModel(POLICY, consent());
    const change = planConsentChange(vm, ["learning_data", "voice_audio"]);
    expect(change).toMatchObject({ kind: "grant", grant: ["learning_data", "voice_audio"], withdraw: null, needsConfirmation: false });
  });

  it("grants just the required scope when nothing optional is ticked", () => {
    const change = planConsentChange(consentViewModel(POLICY, consent()), ["learning_data"]);
    expect(change.grant).toEqual(["learning_data"]);
  });

  it("turns an unticked, previously granted scope into a withdrawal (grants are additive)", () => {
    const vm = consentViewModel(POLICY, granted(["learning_data", "ai_teaching", "voice_audio"]));
    const change = planConsentChange(vm, ["learning_data", "voice_audio"]);
    expect(change).toMatchObject({
      kind: "withdraw-some",
      grant: null,
      withdraw: ["ai_teaching"],
      withdrawAll: false,
      signsOut: false,
      needsConfirmation: true,
    });
  });

  it("can add one scope and remove another in one save", () => {
    const vm = consentViewModel(POLICY, granted(["learning_data", "ai_teaching"]));
    const change = planConsentChange(vm, ["learning_data", "progress_sharing"]);
    expect(change.kind).toBe("grant-and-withdraw");
    expect(change.grant).toEqual(["learning_data", "progress_sharing"]);
    expect(change.withdraw).toEqual(["ai_teaching"]);
    expect(change.needsConfirmation).toBe(true);
  });

  it("does nothing when nothing changed", () => {
    const vm = consentViewModel(POLICY, granted(["learning_data", "voice_audio"]));
    expect(planConsentChange(vm, ["learning_data", "voice_audio"]).kind).toBe("none");
  });

  it("re-grants under a changed policy even when no box changed", () => {
    const vm = consentViewModel(
      POLICY,
      granted(["learning_data", "voice_audio"], { policy_current: false, permits_sign_in: false, policy_version: "old" }),
    );
    const change = planConsentChange(vm, ["learning_data", "voice_audio"]);
    expect(change).toMatchObject({ kind: "grant", grant: ["learning_data", "voice_audio"] });
  });

  it("treats leaving out the required scope as stopping everything", () => {
    const vm = consentViewModel(POLICY, granted(["learning_data", "voice_audio"]));
    const change = planConsentChange(vm, ["voice_audio"]);
    expect(change).toMatchObject({ kind: "withdraw-all", withdrawAll: true, signsOut: true, needsConfirmation: true });
  });

  it("never asks for a scope the form does not offer", () => {
    const vm = consentViewModel(POLICY, consent());
    expect(planConsentChange(vm, ["learning_data", "nonsense" as never]).grant).toEqual(["learning_data"]);
  });

  it("does not send a grant the app cannot explain", () => {
    const policy = { ...POLICY, scopes: [...POLICY.scopes, { key: "biometrics" as never, required: true }] };
    expect(planConsentChange(consentViewModel(policy, consent()), ["learning_data"]).kind).toBe("none");
  });
});

describe("planWithdrawAll", () => {
  it("withdraws everything and signs the child out", () => {
    const change = planWithdrawAll(consentViewModel(POLICY, granted(["learning_data"])));
    expect(change).toMatchObject({ kind: "withdraw-all", withdrawAll: true, signsOut: true, needsConfirmation: true });
  });
  it("is a no-op when nothing is granted", () => {
    expect(planWithdrawAll(consentViewModel(POLICY, consent())).kind).toBe("none");
  });
});

describe("consentFlow (withdrawal confirmation)", () => {
  const vm = consentViewModel(POLICY, granted(["learning_data", "ai_teaching"]));
  const withdrawal = planWithdrawAll(vm);
  const grant = planConsentChange(consentViewModel(POLICY, consent()), ["learning_data"]);

  function run(events: Parameters<typeof consentFlow>[1][], from: ConsentFlowState = IDLE) {
    return events.reduce(consentFlow, from);
  }

  it("asks for confirmation before any withdrawal", () => {
    expect(run([{ type: "request", change: withdrawal }])).toEqual({ phase: "confirming", change: withdrawal });
  });

  it("submits a pure grant without a confirmation step", () => {
    expect(run([{ type: "request", change: grant }]).phase).toBe("submitting");
  });

  it("sends nothing when the guardian cancels", () => {
    expect(run([{ type: "request", change: withdrawal }, { type: "cancel" }])).toEqual(IDLE);
  });

  it("confirm -> submitting -> done", () => {
    const state = run([{ type: "request", change: withdrawal }, { type: "confirm" }, { type: "succeeded" }]);
    expect(state).toEqual({ phase: "done", change: withdrawal });
  });

  it("keeps the change on failure so it can be retried or abandoned", () => {
    const failed = run([
      { type: "request", change: withdrawal },
      { type: "confirm" },
      { type: "failed", error: "auth.errors.offline" },
    ]);
    expect(failed).toEqual({ phase: "failed", change: withdrawal, error: "auth.errors.offline" });
    expect(consentFlow(failed, { type: "retry" })).toEqual({ phase: "submitting", change: withdrawal });
    expect(consentFlow(failed, { type: "cancel" })).toEqual(IDLE);
  });

  it("ignores a double confirm and stray events", () => {
    const submitting = run([{ type: "request", change: withdrawal }, { type: "confirm" }]);
    expect(consentFlow(submitting, { type: "confirm" })).toBe(submitting);
    expect(consentFlow(submitting, { type: "cancel" })).toBe(submitting);
    expect(consentFlow(submitting, { type: "request", change: grant })).toBe(submitting);
    expect(consentFlow(IDLE, { type: "succeeded" })).toBe(IDLE);
    expect(consentFlow(IDLE, { type: "confirm" })).toBe(IDLE);
  });

  it("returns to idle for a no-change request and after dismissing a result", () => {
    expect(consentFlow(IDLE, { type: "request", change: planWithdrawAll(consentViewModel(POLICY, consent())) })).toEqual(IDLE);
    expect(consentFlow({ phase: "done", change: grant }, { type: "dismiss" })).toEqual(IDLE);
  });

  it("allows a new request after a previous one finished", () => {
    expect(consentFlow({ phase: "done", change: grant }, { type: "request", change: withdrawal }).phase).toBe("confirming");
  });
});

describe("confirmationCopy", () => {
  it("tells the guardian a full withdrawal signs the child out, deletes nothing, and can be undone", () => {
    const copy = confirmationCopy(planWithdrawAll(consentViewModel(POLICY, granted(["learning_data"]))));
    const text = copy.lines.map((k) => translate("en", k)).join(" ");
    expect(text).toMatch(/signed out/);
    expect(text).toMatch(/cannot sign in/);
    expect(text).toMatch(/Nothing is deleted/);
    expect(translate("en", copy.title, { name: "Ali" })).toBe("Stop all permissions for Ali?");
    expect(translate("ur", copy.title, { name: "علی" })).toContain("علی");
  });

  it("names each scope being taken back and says the child can still learn", () => {
    const vm = consentViewModel(POLICY, granted(["learning_data", "ai_teaching", "voice_audio"]));
    const copy = confirmationCopy(planConsentChange(vm, ["learning_data"]));
    expect(copy.scopeLines).toEqual(["guardian.consent.scopes.ai_teaching.ifOff", "guardian.consent.scopes.voice_audio.ifOff"]);
    expect(copy.lines.map((k) => translate("en", k)).join(" ")).toMatch(/can still sign in/);
  });

  it("picks the right notice after saving", () => {
    const vm = consentViewModel(POLICY, granted(["learning_data", "ai_teaching"]));
    expect(doneNotice(planWithdrawAll(vm))).toBe("guardian.consent.doneWithdrawnAll");
    expect(doneNotice(planConsentChange(vm, ["learning_data"]))).toBe("guardian.consent.doneWithdrawnSome");
    expect(doneNotice(planConsentChange(vm, ["learning_data", "progress_sharing"]))).toBe("guardian.consent.doneUpdated");
    expect(doneNotice(planConsentChange(consentViewModel(POLICY, consent()), ["learning_data"]))).toBe(
      "guardian.consent.doneGranted",
    );
  });
});
