"use client";
// Curriculum Studio staff sign-in form: the operator-provisioned account's email and passphrase.
//
// Integration point: StudioShell can render <StaffSignInForm /> in its signed-out branch in place of
// the paste-a-token form; on success the studio session updates and the shell re-renders signed in
// (useStudioActor subscribes to it). `onSignedIn` lets the standalone /studio/signin page navigate.
import { useId, useState, type FormEvent } from "react";

import { FormError, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { identityErrorKey } from "@/lib/guardian/errors";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { signInStaff } from "@/lib/studio/sessionSignIn";

export function StaffSignInForm({ onSignedIn }: { onSignedIn?: () => void }) {
  const { t } = useLocale();
  const emailId = useId();
  const passphraseId = useId();
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await signInStaff(email, passphrase);
      if (!result.ok) {
        setError("auth.errors.generic");
        return;
      }
      setPassphrase("");
      onSignedIn?.();
    } catch (e) {
      // Same uniform message for every 401, exactly as the server answers.
      setError(identityErrorKey(e, "guardian-sign-in"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 560, display: "grid", gap: "var(--space-4)" }}>
      <h1 style={{ margin: 0 }}>{t("studio.signIn.heading")}</h1>
      <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-3)" }}>
        <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
        <TextField
          id={emailId}
          label={t("auth.guardianSignIn.email")}
          type="email"
          dir="ltr"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
        <TextField
          id={passphraseId}
          label={t("auth.guardianSignIn.passphrase")}
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Button type="submit" variant="brand" label={t("studio.signIn.submit")} loading={busy} />
      </form>
    </main>
  );
}
