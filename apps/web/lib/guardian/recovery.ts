// Guardian recovery codes — the email-free way back in after a forgotten password. Pure; unit-tested.
//
// The server makes eight one-time codes (`XXXX-XXXX-XXXX`), returns them in exactly one response
// (registration, or "make new codes" in Family settings) and keeps only digests. So this screen is
// the only chance a guardian has to keep them: the view model below decides what the guardian is
// told about their codes, how a typed code is checked before it is sent, and the plain text that
// "Copy" and "Print" produce. The server stays the authority — a code that passes here can still be
// wrong, used, or locked, and the server says so with the same answer as a wrong password.

import type { MessageKey } from "../i18n/messages";
import type { MessageParams, Translator } from "../i18n/translate";
import type { RecoveryStatus } from "../session/types";

/** The family-code alphabet: no 0/O, 1/I/L, so a code survives being read aloud or handwritten. */
export const RECOVERY_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789";
export const RECOVERY_CODE_LENGTH = 12;
export const RECOVERY_CODE_COUNT = 8;
/** At or below this many unused codes the guardian is nudged to make a new set. */
export const RECOVERY_LOW_AT = 2;

const STRIP = /[\s\-_.]/g;

/** Canonical `XXXX-XXXX-XXXX` for what a guardian typed (any case, spaces, no dashes), or null. */
export function normaliseRecoveryCode(raw: string): string | null {
  const compact = raw.replace(STRIP, "").toUpperCase();
  if (compact.length !== RECOVERY_CODE_LENGTH) return null;
  for (const ch of compact) if (!RECOVERY_CODE_ALPHABET.includes(ch)) return null;
  return `${compact.slice(0, 4)}-${compact.slice(4, 8)}-${compact.slice(8, 12)}`;
}

/** Why a typed code cannot be sent yet (checked before the request, so a typo costs no attempt). */
export function recoveryCodeProblem(raw: string): MessageKey | null {
  if (!raw.replace(STRIP, "")) return "auth.recover.codeEmpty";
  return normaliseRecoveryCode(raw) ? null : "auth.recover.codeFormat";
}

/** The new password and its repeat must match; the server enforces the rest of the policy. */
export function newPassphraseProblem(passphrase: string, repeat: string): MessageKey | null {
  if (passphrase.length < 10) return "auth.errors.passphraseShort";
  if (passphrase !== repeat) return "auth.recover.mismatch";
  return null;
}

export type RecoveryTone = "ok" | "low" | "none";

export interface RecoveryStatusView {
  key: MessageKey;
  params: MessageParams;
  tone: RecoveryTone;
}

/** What Family settings says about the guardian's codes. Never a code — the server has none to give. */
export function recoveryStatusView(status: RecoveryStatus | undefined | null): RecoveryStatusView {
  if (!status || status.total === 0) return { key: "guardian.recovery.statusNone", params: {}, tone: "none" };
  if (status.remaining === 0) return { key: "guardian.recovery.statusUsedUp", params: {}, tone: "none" };
  if (status.remaining <= RECOVERY_LOW_AT) {
    return { key: "guardian.recovery.statusLow", params: { count: status.remaining }, tone: "low" };
  }
  return {
    key: "guardian.recovery.statusOk",
    params: { count: status.remaining, total: status.total },
    tone: "ok",
  };
}

/**
 * The sheet that "Copy" puts on the clipboard: title, the instructions, numbered codes, the email
 * the codes belong to (a code is useless without it, and a guardian with two accounts must know
 * which), and when it was made. Plain text so it pastes anywhere — a notes app, a message to self.
 */
export function recoverySheetText(
  codes: readonly string[],
  t: Translator,
  options: { email?: string; madeAt?: string } = {},
): string {
  const lines = [
    t("guardian.recovery.sheetTitle"),
    "",
    t("guardian.recovery.instructionsOnce"),
    t("guardian.recovery.instructionsUse"),
    t("guardian.recovery.instructionsSafe"),
    "",
    ...codes.map((code, i) => `${i + 1}. ${code}`),
  ];
  if (options.email) lines.push("", t("guardian.recovery.sheetEmail", { email: options.email }));
  if (options.madeAt) lines.push(t("guardian.recovery.sheetMadeAt", { date: options.madeAt }));
  return lines.join("\n");
}
