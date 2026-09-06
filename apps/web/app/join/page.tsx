"use client";
// Guardian registration. The first screen an adult meets, and the one that decides whether a family
// ever gets started, so it asks for exactly three things and explains what each is for.
//
// The family code is shown immediately afterwards rather than emailed: this product is used by
// families who may not have reliable email, and the code is what their child needs to sign in.

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
    if (error.status === 409) return "اس ای میل کے ساتھ اکاؤنٹ پہلے سے موجود ہے۔";
    if (error.status === 429) return "بہت زیادہ کوششیں۔ تھوڑی دیر بعد کوشش کریں۔";
    if (error.status === 422) return error.problem.detail ?? "دی گئی معلومات درست نہیں۔";
  }
  return "کچھ غلط ہو گیا۔ دوبارہ کوشش کریں۔";
}

export default function JoinPage() {
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const envelope = await publicIdentityApi.registerGuardian({
        email,
        passphrase,
        displayName,
      });
      sessionStore.adopt(envelope);
      router.replace("/guardian/family");
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="اپنے بچے کو داخل کروائیں"
      subtitle="پہلے آپ اپنا سرپرست اکاؤنٹ بنائیں۔ پھر آپ اپنے بچوں کو شامل کریں گے۔"
      footer={
        <p style={{ margin: 0 }}>
          پہلے سے اکاؤنٹ ہے؟{" "}
          <Link href="/guardian/signin" style={{ color: "var(--color-action-primary)" }}>
            داخل ہوں
          </Link>
        </p>
      }
    >
      <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-4)" }}>
        {error ? <FormError message={error} /> : null}
        <TextField
          id="display-name"
          label="آپ کا نام"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          autoComplete="name"
          required
        />
        <TextField
          id="email"
          label="ای میل"
          hint="صرف آپ کے اکاؤنٹ کے لیے۔ آپ کے بچے کی کوئی ای میل نہیں ہوتی۔"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <TextField
          id="passphrase"
          label="خفیہ جملہ"
          hint="کم از کم دس حروف۔ ایک جملہ یاد رکھنا آسان اور محفوظ ہوتا ہے۔"
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          autoComplete="new-password"
          minLength={10}
          required
        />
        <Button type="submit" variant="brand" label="اکاؤنٹ بنائیں" loading={busy} />
      </form>
    </AuthShell>
  );
}
