"use client";
// "Forgot your password?" — email, one recovery code, and the new password twice. A typo in the
// code or a mismatch is caught here, before the request, so it costs the guardian no attempt; the
// server is still the authority and answers every other failure with one message.
//
// Takes `t` rather than calling useLocale(), so the node test suite can render it to static markup.
import { useState } from "react";

import { FormError, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { newPassphraseProblem, normaliseRecoveryCode, recoveryCodeProblem } from "@/lib/guardian/recovery";
import type { MessageKey } from "@/lib/i18n/messages";
import type { Translator } from "@/lib/i18n/translate";

export interface RecoverValues {
  email: string;
  code: string;
  newPassphrase: string;
}

export interface RecoverPassphraseFormProps {
  t: Translator;
  busy: boolean;
  /** The server's answer to the last attempt, already mapped to a catalog key. */
  error: MessageKey | null;
  onSubmit: (values: RecoverValues) => void;
}

export function RecoverPassphraseForm({ t, busy, error, onSubmit }: RecoverPassphraseFormProps) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [repeat, setRepeat] = useState("");
  const [fieldErrors, setFieldErrors] = useState<{ code?: MessageKey; passphrase?: MessageKey }>({});

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const next = {
      code: recoveryCodeProblem(code) ?? undefined,
      passphrase: newPassphraseProblem(passphrase, repeat) ?? undefined,
    };
    setFieldErrors(next);
    if (next.code || next.passphrase) return;
    onSubmit({ email: email.trim(), code: normaliseRecoveryCode(code) ?? code, newPassphrase: passphrase });
  }

  return (
    <form onSubmit={submit} noValidate style={{ display: "grid", gap: "var(--space-4)" }}>
      <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
      <TextField
        id="recover-email"
        label={t("auth.recover.email")}
        type="email"
        dir="ltr"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        autoComplete="email"
        required
      />
      <TextField
        id="recover-code"
        label={t("auth.recover.code")}
        hint={t("auth.recover.codeHint")}
        error={fieldErrors.code ? t(fieldErrors.code) : undefined}
        dir="ltr"
        lang="en"
        value={code}
        onChange={(e) => setCode(e.target.value)}
        autoComplete="one-time-code"
        autoCapitalize="characters"
        spellCheck={false}
        maxLength={20}
        required
      />
      <TextField
        id="recover-new"
        label={t("auth.recover.newPassphrase")}
        hint={t("auth.recover.newPassphraseHint")}
        error={fieldErrors.passphrase ? t(fieldErrors.passphrase) : undefined}
        type="password"
        value={passphrase}
        onChange={(e) => setPassphrase(e.target.value)}
        autoComplete="new-password"
        minLength={10}
        required
      />
      <TextField
        id="recover-repeat"
        label={t("auth.recover.repeat")}
        type="password"
        value={repeat}
        onChange={(e) => setRepeat(e.target.value)}
        autoComplete="new-password"
        required
      />
      <Button type="submit" variant="brand" label={t("auth.recover.submit")} loading={busy} />
    </form>
  );
}
