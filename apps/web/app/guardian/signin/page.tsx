"use client";
// Guardian sign-in.

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AuthShell, FormError, TextField } from "@/components/form";
import { Button } from "@/design-system/Button";
import { publicIdentityApi } from "@/lib/session/identityApi";
import { sessionStore } from "@/lib/session/store";
import { ApiError } from "@/lib/student/types";

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "انٹرنیٹ دستیاب نہیں۔ دوبارہ کوشش کریں۔";
    if (error.status === 429) return "بہت زیادہ کوششیں۔ تھوڑی دیر بعد کوشش کریں۔";
    // The server answers an unknown address and a wrong passphrase identically, and so does this
    // screen — telling a stranger which one it was would confirm the address is registered.
    if (error.status === 401) return "ای میل یا خفیہ جملہ درست نہیں۔";
  }
  return "کچھ غلط ہو گیا۔ دوبارہ کوشش کریں۔";
}

export default function GuardianSignInPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const envelope = await publicIdentityApi.signInGuardian({ email, passphrase });
      sessionStore.adopt(envelope);
      router.replace("/guardian");
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="سرپرست کا داخلہ"
      footer={
        <p style={{ margin: 0 }}>
          نیا اکاؤنٹ چاہیے؟{" "}
          <Link href="/join" style={{ color: "var(--color-action-primary)" }}>
            یہاں بنائیں
          </Link>
        </p>
      }
    >
      <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-4)" }}>
        {error ? <FormError message={error} /> : null}
        <TextField
          id="email"
          label="ای میل"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <TextField
          id="passphrase"
          label="خفیہ جملہ"
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="current-password"
          required
        />
        <Button type="submit" variant="brand" label="داخل ہوں" loading={busy} />
      </form>
    </AuthShell>
  );
}
