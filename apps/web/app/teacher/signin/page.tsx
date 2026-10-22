"use client";
// Teacher sign-in. One uniform failure message (the server answers an unknown email, a wrong
// passphrase and a locked or suspended account identically); the session goes into the shared
// session store as a `teacher` session — see lib/teacher/session.ts.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthShell, FormError, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import { sessionStore } from "@/lib/session/store";
import { publicTeacherApi } from "@/lib/teacher/api";
import { signInErrorKey } from "@/lib/teacher/errors";
import { teacherEnvelope } from "@/lib/teacher/session";

import { LanguagePicker } from "../../guardian/LanguagePicker";

export default function TeacherSignInPage() {
  const router = useRouter();
  const { t } = useLocale();
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await publicTeacherApi.signIn({ email: email.trim(), passphrase });
      sessionStore.adopt(teacherEnvelope(response));
      router.replace("/teacher");
    } catch (e) {
      setError(signInErrorKey(e));
      // Never keep a rejected passphrase in the field.
      setPassphrase("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title={t("teacher.signIn.title")}
      subtitle={t("teacher.signIn.subtitle")}
      footer={
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <p style={{ margin: 0 }}>
            {t("teacher.signIn.guardianPrompt")}{" "}
            <Link href="/guardian/signin" style={{ color: "var(--color-action-primary)" }}>
              {t("teacher.signIn.guardianLink")}
            </Link>
          </p>
          <LanguagePicker />
        </div>
      }
    >
      <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-4)" }}>
        <div aria-live="polite">{error ? <FormError message={t(error)} /> : null}</div>
        <TextField
          id="teacher-email"
          label={t("teacher.signIn.email")}
          type="email"
          dir="ltr"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="username"
          required
        />
        <TextField
          id="teacher-passphrase"
          label={t("teacher.signIn.passphrase")}
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Button type="submit" variant="brand" label={t("teacher.signIn.submit")} loading={busy} />
      </form>
    </AuthShell>
  );
}
