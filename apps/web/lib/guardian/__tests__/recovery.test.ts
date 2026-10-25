// Guardian recovery codes on the web: the view model (code checking, status copy, the copy/print
// sheet), the error mapping, and the markup of the codes panel and the "Forgot password?" form,
// rendered to static HTML in the node suite (react-dom/server; no jsdom) in Urdu and English.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { RecoverPassphraseForm } from "@/components/guardian/RecoverPassphraseForm";
import { RecoveryCodesPanel } from "@/components/guardian/RecoveryCodesPanel";

import { createTranslator, translate } from "../../i18n/translate";
import { ApiError } from "../../student/types";
import { auditEntry } from "../audit";
import { identityErrorKey } from "../errors";
import {
  RECOVERY_CODE_ALPHABET,
  newPassphraseProblem,
  normaliseRecoveryCode,
  recoveryCodeProblem,
  recoverySheetText,
  recoveryStatusView,
} from "../recovery";

const CODES = [
  "K7QM-3XPZ-H4TA",
  "ABCD-EFGH-JKMN",
  "PQRS-TUVW-XYZ2",
  "3456-789A-BCDE",
  "FGHJ-KMNP-QRST",
  "UVWX-YZ23-4567",
  "89AB-CDEF-GHJK",
  "MNPQ-RSTU-VWXY",
];

type Locale = "ur" | "en";

function panel(locale: Locale): string {
  const t = createTranslator(locale);
  const html = renderToStaticMarkup(
    createElement(RecoveryCodesPanel, {
      codes: CODES,
      t,
      email: "parent@example.com",
      madeAt: "25 Oct 2026",
      doneLabel: t("guardian.recovery.continue"),
      onDone: () => undefined,
    }),
  );
  return `<div dir="${locale === "ur" ? "rtl" : "ltr"}">${html}</div>`;
}

function form(locale: Locale, error: Parameters<typeof RecoverPassphraseForm>[0]["error"] = null): string {
  return renderToStaticMarkup(
    createElement(RecoverPassphraseForm, { t: createTranslator(locale), busy: false, error, onSubmit: () => undefined }),
  );
}

describe("normaliseRecoveryCode", () => {
  it("accepts what a guardian types and canonicalises it", () => {
    expect(normaliseRecoveryCode("k7qm-3xpz-h4ta")).toBe("K7QM-3XPZ-H4TA");
    expect(normaliseRecoveryCode("K7QM 3XPZ H4TA")).toBe("K7QM-3XPZ-H4TA");
    expect(normaliseRecoveryCode(" k7qm3xpzh4ta ")).toBe("K7QM-3XPZ-H4TA");
  });

  it("refuses the wrong length and characters outside the alphabet", () => {
    expect(normaliseRecoveryCode("K7QM-3XPZ")).toBeNull();
    expect(normaliseRecoveryCode("K7QM-3XPZ-H4TA-X")).toBeNull();
    expect(normaliseRecoveryCode("K7QM-3XPZ-H4T0")).toBeNull(); // zero is not in the alphabet
    expect(normaliseRecoveryCode("K7QM-3XPZ-H4TO")).toBeNull(); // nor is O
  });

  it("matches the server's alphabet (identity/domain/accounts.py)", () => {
    expect(RECOVERY_CODE_ALPHABET).toBe("ABCDEFGHJKMNPQRSTUVWXYZ23456789");
    for (const code of CODES) expect(normaliseRecoveryCode(code)).toBe(code);
  });
});

describe("form checks", () => {
  it("catch an empty or malformed code before any request", () => {
    expect(recoveryCodeProblem("")).toBe("auth.recover.codeEmpty");
    expect(recoveryCodeProblem(" - ")).toBe("auth.recover.codeEmpty");
    expect(recoveryCodeProblem("abc")).toBe("auth.recover.codeFormat");
    expect(recoveryCodeProblem("k7qm3xpzh4ta")).toBeNull();
  });

  it("need a 10-letter password typed the same twice", () => {
    expect(newPassphraseProblem("short", "short")).toBe("auth.errors.passphraseShort");
    expect(newPassphraseProblem("a long sentence", "a long sentenc")).toBe("auth.recover.mismatch");
    expect(newPassphraseProblem("a long sentence", "a long sentence")).toBeNull();
  });
});

describe("recoveryStatusView", () => {
  it("counts, nudges when low, and demands new codes when none are left", () => {
    const at = { generated_at: 1, last_used_at: null };
    expect(recoveryStatusView({ total: 8, remaining: 8, ...at })).toEqual({
      key: "guardian.recovery.statusOk",
      params: { count: 8, total: 8 },
      tone: "ok",
    });
    expect(recoveryStatusView({ total: 8, remaining: 2, ...at }).tone).toBe("low");
    expect(recoveryStatusView({ total: 8, remaining: 0, ...at }).key).toBe("guardian.recovery.statusUsedUp");
    expect(recoveryStatusView({ total: 0, remaining: 0, generated_at: null, last_used_at: null }).key).toBe(
      "guardian.recovery.statusNone",
    );
    expect(recoveryStatusView(undefined).tone).toBe("none");
  });

  it("reads well in both languages", () => {
    const view = recoveryStatusView({ total: 8, remaining: 5, generated_at: 1, last_used_at: 2 });
    expect(translate("en", view.key, view.params)).toBe("You have 5 of 8 recovery codes left.");
    expect(translate("ur", view.key, view.params)).toContain("بحالی کوڈ");
  });
});

describe("recoverySheetText", () => {
  it("numbers every code and carries the instructions, the account and the date", () => {
    const text = recoverySheetText(CODES, createTranslator("en"), { email: "parent@example.com", madeAt: "25 Oct 2026" });
    CODES.forEach((code, i) => expect(text).toContain(`${i + 1}. ${code}`));
    expect(text).toContain("shown only once");
    expect(text).toContain("Each code works only once");
    expect(text).toContain("Account: parent@example.com");
    expect(text).toContain("Made: 25 Oct 2026");
  });

  it("is written in Urdu for an Urdu reader", () => {
    const text = recoverySheetText(CODES, createTranslator("ur"));
    expect(text).toContain("صرف ایک بار");
    expect(text).toContain("1. K7QM-3XPZ-H4TA");
  });
});

describe("identityErrorKey for recovery", () => {
  it("answers every recovery failure with one message", () => {
    expect(identityErrorKey(new ApiError(401, { code: "UNAUTHORIZED" }), "recover")).toBe("auth.errors.recoveryFailed");
    expect(identityErrorKey(new ApiError(429, {}), "recover")).toBe("auth.errors.tooMany");
    expect(identityErrorKey(new ApiError(422, { detail: "passphrase must be at least 10 characters" }), "recover")).toBe(
      "auth.errors.passphraseShort",
    );
  });

  it("says a wrong current password, not 'signed out', when making new codes", () => {
    expect(identityErrorKey(new ApiError(403, { code: "PASSPHRASE_INCORRECT" }), "recovery-codes")).toBe(
      "auth.errors.passphraseIncorrect",
    );
    expect(identityErrorKey(new ApiError(401, {}), "recovery-codes")).toBe("auth.errors.signedOut");
  });

  it("has copy for every key in both catalogs", () => {
    for (const key of ["auth.errors.recoveryFailed", "auth.errors.passphraseIncorrect"] as const) {
      expect(translate("en", key)).not.toBe(key);
      expect(translate("ur", key)).not.toBe(key);
    }
  });
});

describe("recovery audit entries", () => {
  it("are readable, and a reset with a code is flagged for the guardian to check", () => {
    const base = { event_id: "e", at: 1, actor_ref: "g", actor_role: "guardian", subject_ref: "g", correlation_id: "", detail: {} };
    const recovered = auditEntry({ ...base, action: "guardian.recovered" }, new Map());
    expect(translate("en", recovered.key)).toContain("recovery code");
    expect(recovered.warning).toBe(true);
    expect(auditEntry({ ...base, action: "guardian.recovery_codes_generated" }, new Map()).warning).toBe(false);
  });
});

describe("RecoveryCodesPanel markup", () => {
  it("lists all eight codes in an LTR, Latin, labelled list", () => {
    const html = panel("en");
    for (const code of CODES) expect(html).toContain(`<code>${code}</code>`);
    expect(html).toMatch(/<ol[^>]*aria-label="Recovery codes"[^>]*dir="ltr"[^>]*lang="en"/);
    expect((html.match(/<li><code>/g) ?? []).length).toBe(8);
  });

  it("says plainly that they are shown once, how to use them, and to keep them private", () => {
    const html = panel("en");
    expect(html).toContain("These codes are shown only once.");
    expect(html).toContain("Forgot password?");
    expect(html).toContain("Do not share them");
    expect(html).toContain("Account: parent@example.com");
  });

  it("offers copy and print, and keeps Continue disabled until the guardian ticks 'saved'", () => {
    const html = panel("en");
    expect(html).toContain("Copy codes");
    expect(html).toContain("Print codes");
    expect(html).toMatch(/<input id="([^"]+)" type="checkbox"[^>]*\/?>.*<label for="\1">I have written down or printed these codes<\/label>/s);
    const done = /<button[^>]*>(?:(?!<\/button>).)*Continue to my family.*?<\/button>/s.exec(html)?.[0] ?? "";
    expect(done).toContain("disabled");
    expect(done).toMatch(/aria-describedby="[^"]+-why"/);
    expect(html).toContain("Tick the box when your codes are saved.");
  });

  it("prints only the sheet, without its buttons", () => {
    const html = panel("en");
    expect(html).toContain("data-recovery-sheet");
    expect(html).toContain("@media print");
    expect(html).toContain("data-screen-only");
  });

  it("renders in Urdu with the codes still LTR", () => {
    const html = panel("ur");
    expect(html).toContain("آپ کے تعلیم بحالی کوڈ");
    expect(html).toContain("یہ کوڈ صرف ایک بار دکھائے جاتے ہیں");
    expect(html).toContain("کوڈ کاپی کریں");
    expect(html).toContain("کوڈ پرنٹ کریں");
    expect(html).toMatch(/dir="ltr"[^>]*lang="en"/);
    expect(html).toContain("<code>K7QM-3XPZ-H4TA</code>");
  });
});

describe("RecoverPassphraseForm markup", () => {
  it("has labelled email, code, and two new-password fields", () => {
    const html = form("en");
    for (const [id, label] of [
      ["recover-email", "Email"],
      ["recover-code", "Recovery code"],
      ["recover-new", "New password"],
      ["recover-repeat", "New password again"],
    ]) {
      expect(html).toMatch(new RegExp(`<label for="${id}"[^>]*>${label}</label>`));
    }
    expect(html).toMatch(/id="recover-code"[^>]*autoComplete="one-time-code"|autocomplete="one-time-code"[^>]*id="recover-code"|id="recover-code"[^>]*autocomplete="one-time-code"/i);
    expect(html).toMatch(/type="password"[^>]*autoComplete="new-password"|autocomplete="new-password"/i);
    expect(html).toContain("Change my password");
  });

  it("shows the server's one recovery message, in Urdu too", () => {
    expect(form("en", "auth.errors.recoveryFailed")).toContain("The email or recovery code is not right");
    const ur = form("ur", "auth.errors.recoveryFailed");
    expect(ur).toContain("بحالی کوڈ درست نہیں");
    expect(ur).toContain("نیا خفیہ جملہ");
  });
});
