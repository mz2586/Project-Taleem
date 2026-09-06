"use client";
// The guardian's control room: the family code, the learners, consent, PIN resets, and the audit
// trail. Every control a guardian has over their child's account is reachable from this one screen.
//
// The consent form is the part that matters most, so it is deliberate rather than convenient:
//
// - `learning_data` is checked and disabled. It is the one scope without which there is nothing to
//   sign a child in for, and pretending it is optional would be dishonest.
// - The other three are unchecked by default. Consent is something a guardian gives, not something
//   they have to notice and remove.
// - The attestation sentence is displayed verbatim above the button and stored verbatim with the
//   record, so what was agreed is reconstructible afterwards rather than inferred from a timestamp.
// - Withdrawal is one press and needs no reason. A stop button that asks why is not a stop button.

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { GuardianShell } from "@/app/guardian/GuardianShell";
import { FormError, FormNotice, PinField, TextField } from "@/components/form";
import { RequireSession } from "@/components/RequireSession";
import { Button } from "@/design-system/Button";
import { createGuardianIdentityApi } from "@/lib/session/identityApi";
import { currentAccessToken, sessionStore, withSession } from "@/lib/session/store";
import type { AuditEvent, ConsentScope, GuardianProfile, Learner } from "@/lib/session/types";
import { ApiError } from "@/lib/student/types";

const api = createGuardianIdentityApi(currentAccessToken);

// Urdu labels plus a plain-language explanation of what each permission actually allows. A consent
// screen that lists machine keys is not consent.
const SCOPE_LABELS: Record<ConsentScope, { title: string; detail: string }> = {
  learning_data: {
    title: "سیکھنے کا ریکارڈ",
    detail: "آپ کے بچے کی پیش رفت اور مشقیں محفوظ کی جائیں گی۔ اس کے بغیر پڑھائی ممکن نہیں۔",
  },
  ai_teaching: {
    title: "خودکار استاد",
    detail: "نصاب کی بنیاد پر وضاحت اور مدد۔ آپ اسے کسی بھی وقت بند کر سکتے ہیں۔",
  },
  voice_audio: {
    title: "آواز اور سننا",
    detail: "سبق سنائے جائیں گے۔ کم پڑھنے والے بچوں کے لیے مددگار۔",
  },
  progress_sharing: {
    title: "استاد کے ساتھ اشتراک",
    detail: "مقرر کردہ استاد آپ کے بچے کی پیش رفت دیکھ سکے گا۔",
  },
};

const OPTIONAL_SCOPES: ConsentScope[] = ["ai_teaching", "voice_audio", "progress_sharing"];

const ATTESTATION =
  "میں اس بچے کا سرپرست ہوں اور میں اوپر دی گئی اجازتوں سے اتفاق کرتا/کرتی ہوں۔";

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "انٹرنیٹ دستیاب نہیں۔ دوبارہ کوشش کریں۔";
    if (error.status === 422) return error.problem.detail ?? "دی گئی معلومات درست نہیں۔";
    if (error.status === 404) return "یہ طالبِ علم نہیں ملا۔";
  }
  return "کچھ غلط ہو گیا۔ دوبارہ کوشش کریں۔";
}

function FamilyCodeCard({ code }: { code: string }) {
  return (
    <section
      style={{
        border: "1px solid var(--color-brand)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4)",
        display: "grid",
        gap: "var(--space-2)",
      }}
    >
      <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>گھر کا کوڈ</h2>
      <p style={{ margin: 0 }}>یہ کوڈ اپنے بچے کے فون پر ایک بار لکھیں۔ اسے محفوظ رکھیں۔</p>
      <strong
        // LTR because the code is Latin letters and digits: rendering it right-to-left would show
        // the groups in the wrong order to someone reading it aloud.
        dir="ltr"
        style={{
          fontFamily: "var(--font-latin)",
          fontSize: "28px",
          letterSpacing: "0.15em",
          textAlign: "center",
          padding: "var(--space-2)",
        }}
      >
        {code}
      </strong>
    </section>
  );
}

function EnrolForm({ onEnrolled }: { onEnrolled: () => Promise<void> }) {
  const [displayName, setDisplayName] = useState("");
  const [pin, setPin] = useState("");
  const [gradeLevel, setGradeLevel] = useState(4);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await withSession(() =>
        api.enrolLearner({
          displayName,
          pin,
          gradeLevel,
          gradeBand: gradeLevel <= 2 ? "early" : gradeLevel <= 5 ? "middle" : "senior",
        }),
      );
      setDisplayName("");
      setPin("");
      await onEnrolled();
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-3)" }}>
      <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>نیا طالبِ علم شامل کریں</h2>
      {error ? <FormError message={error} /> : null}
      <TextField
        id="learner-name"
        label="بچے کا نام"
        hint="وہی نام جو آپ کا بچہ داخل ہوتے وقت چنے گا۔"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        required
      />
      <PinField
        id="learner-pin"
        label="بچے کا پن"
        hint="چار سے چھ ہندسے۔ 1234 جیسے آسان پن قبول نہیں ہوں گے۔"
        value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
        required
      />
      <label htmlFor="grade" style={{ fontSize: "var(--font-size-body-min-urdu)" }}>
        جماعت
      </label>
      <select
        id="grade"
        value={gradeLevel}
        onChange={(e) => setGradeLevel(Number(e.target.value))}
        style={{
          minHeight: "var(--size-touch-min)",
          padding: "var(--space-2)",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-focus-ring)",
          background: "var(--color-bg-canvas)",
          color: "var(--color-text-primary)",
          font: "inherit",
          fontSize: "var(--font-size-body-min-urdu)",
        }}
      >
        {Array.from({ length: 11 }, (_, i) => i).map((g) => (
          <option key={g} value={g}>
            {g === 0 ? "کے جی" : `جماعت ${g}`}
          </option>
        ))}
      </select>
      <Button type="submit" variant="brand" label="شامل کریں" loading={busy} disabled={pin.length < 4} />
    </form>
  );
}

function ConsentPanel({ learner, onChanged }: { learner: Learner; onChanged: () => Promise<void> }) {
  const granted = useMemo(() => new Set(learner.consent.granted_scopes), [learner]);
  const [selected, setSelected] = useState<Set<ConsentScope>>(new Set(granted));
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSelected(new Set(learner.consent.granted_scopes));
  }, [learner]);

  function toggle(scope: ConsentScope) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(scope)) next.delete(scope);
      else next.add(scope);
      return next;
    });
  }

  async function grant() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await withSession(() =>
        api.grantConsent({
          studentRef: learner.student_ref,
          scopes: ["learning_data", ...OPTIONAL_SCOPES.filter((s) => selected.has(s))],
          attestation: ATTESTATION,
        }),
      );
      setNotice("اجازت محفوظ ہو گئی۔");
      await onChanged();
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  async function withdraw() {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await withSession(() => api.withdrawConsent({ studentRef: learner.student_ref }));
      setNotice("اجازت واپس لے لی گئی۔ آپ کا بچہ اب داخل نہیں ہو سکتا۔");
      await onChanged();
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }}>
      {error ? <FormError message={error} /> : null}
      {notice ? <FormNotice message={notice} /> : null}

      <fieldset style={{ border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
        <legend style={{ fontSize: "var(--font-size-body-min-urdu)" }}>اجازتیں</legend>
        {(["learning_data", ...OPTIONAL_SCOPES] as ConsentScope[]).map((scope) => {
          const required = scope === "learning_data";
          const meta = SCOPE_LABELS[scope];
          return (
            <label
              key={scope}
              htmlFor={`${learner.student_ref}-${scope}`}
              style={{
                display: "flex",
                gap: "var(--space-3)",
                alignItems: "start",
                padding: "var(--space-2)",
                border: "1px solid var(--color-focus-ring)",
                borderRadius: "var(--radius-md)",
              }}
            >
              <input
                id={`${learner.student_ref}-${scope}`}
                type="checkbox"
                checked={required || selected.has(scope)}
                disabled={required}
                onChange={() => toggle(scope)}
                style={{ width: 24, height: 24, marginTop: 2, flexShrink: 0 }}
              />
              <span style={{ display: "grid", gap: 2 }}>
                <strong>
                  {meta.title}
                  {required ? " (لازمی)" : ""}
                </strong>
                <span style={{ fontSize: "var(--font-size-body-min)" }}>{meta.detail}</span>
              </span>
            </label>
          );
        })}
      </fieldset>

      <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{ATTESTATION}</p>

      <div style={{ display: "flex", gap: "var(--space-2)", flexWrap: "wrap" }}>
        <Button
          variant="brand"
          label={learner.consent.permits_sign_in ? "اجازتیں محفوظ کریں" : "اجازت دیں"}
          onClick={() => void grant()}
          loading={busy}
        />
        {learner.consent.permits_sign_in ? (
          <Button variant="danger" label="اجازت واپس لیں" onClick={() => void withdraw()} loading={busy} />
        ) : null}
      </div>

      {!learner.consent.policy_current && learner.consent.policy_version ? (
        <FormNotice message="ہماری پالیسی تبدیل ہو گئی ہے۔ براہِ کرم دوبارہ اجازت دیں۔" />
      ) : null}
    </div>
  );
}

function PinResetPanel({ learner }: { learner: Learner }) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await withSession(() => api.resetPin(learner.student_ref, pin));
      setPin("");
      setNotice("نیا پن محفوظ ہو گیا۔ پرانے فون خود بخود بند ہو جائیں گے۔");
    } catch (e) {
      setError(messageFor(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-2)" }}>
      {error ? <FormError message={error} /> : null}
      {notice ? <FormNotice message={notice} /> : null}
      <PinField
        id={`reset-${learner.student_ref}`}
        label="نیا پن"
        hint={
          learner.status === "locked"
            ? "آپ کا بچہ بند ہے۔ نیا پن دینے سے وہ دوبارہ کھل جائے گا۔"
            : "بھول جانے پر نیا پن دیں۔"
        }
        value={pin}
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
      />
      <Button type="submit" variant="ghost" label="پن بدلیں" loading={busy} disabled={pin.length < 4} />
    </form>
  );
}

const AUDIT_LABELS: Record<string, string> = {
  "guardian.registered": "سرپرست اکاؤنٹ بنا",
  "guardian.signed_in": "سرپرست داخل ہوا",
  "guardian.sign_in_failed": "سرپرست کا داخلہ ناکام",
  "guardian.locked": "سرپرست اکاؤنٹ بند",
  "learner.created": "طالبِ علم شامل ہوا",
  "learner.signed_in": "طالبِ علم داخل ہوا",
  "learner.sign_in_failed": "غلط پن",
  "learner.sign_in_denied_no_consent": "اجازت نہ ہونے پر داخلہ روکا گیا",
  "learner.locked": "بار بار غلط پن — اکاؤنٹ بند",
  "learner.pin_reset": "پن تبدیل ہوا",
  "consent.granted": "اجازت دی گئی",
  "consent.withdrawn": "اجازت واپس لی گئی",
  "session.refreshed": "سیشن جاری رہا",
  "session.signed_out": "باہر نکلے",
  "session.revoked": "سیشن ختم کیا گیا",
  "session.reuse_detected": "مشکوک سرگرمی — تمام سیشن بند",
};

function AuditList({ events, names }: { events: AuditEvent[]; names: Map<string, string> }) {
  if (events.length === 0) return <p style={{ margin: 0 }}>ابھی کوئی سرگرمی نہیں۔</p>;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
      {events.map((event) => (
        <li
          key={event.event_id}
          style={{
            display: "flex",
            justifyContent: "space-between",
            gap: "var(--space-2)",
            flexWrap: "wrap",
            paddingBottom: "var(--space-2)",
            borderBottom: "1px solid var(--color-focus-ring)",
          }}
        >
          <span>
            {AUDIT_LABELS[event.action] ?? event.action}
            {names.has(event.subject_ref) ? ` — ${names.get(event.subject_ref)}` : ""}
          </span>
          <time dateTime={new Date(event.at * 1000).toISOString()} style={{ opacity: 0.8 }}>
            {new Date(event.at * 1000).toLocaleString("ur-PK")}
          </time>
        </li>
      ))}
    </ul>
  );
}

function FamilyPage() {
  const [profile, setProfile] = useState<GuardianProfile | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [me, audit] = await Promise.all([
        withSession(() => api.me()),
        withSession(() => api.audit()),
      ]);
      setProfile(me);
      setEvents(audit.events);
      setError("");
    } catch (e) {
      setError(messageFor(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const names = useMemo(
    () => new Map((profile?.learners ?? []).map((l) => [l.student_ref, l.display_name])),
    [profile],
  );

  return (
    <GuardianShell title="میرا گھرانہ" back={{ href: "/guardian", label: "واپس" }}>
      {error ? <FormError message={error} /> : null}
      {!profile ? (
        <p aria-busy="true" aria-live="polite">
          …
        </p>
      ) : (
        <>
          <FamilyCodeCard code={profile.guardian.family_code} />

          {profile.learners.map((learner) => (
            <section
              key={learner.student_ref}
              style={{
                border: "1px solid var(--color-focus-ring)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-4)",
                display: "grid",
                gap: "var(--space-3)",
              }}
            >
              <header style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
                <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                  {learner.display_name}
                </h2>
                <span style={{ color: learner.can_sign_in ? "var(--color-brand)" : "var(--color-danger)" }}>
                  <span aria-hidden="true">{learner.can_sign_in ? "●" : "○"}</span>{" "}
                  {learner.can_sign_in ? "پڑھ سکتے ہیں" : "اجازت درکار"}
                </span>
              </header>
              <ConsentPanel learner={learner} onChanged={load} />
              <PinResetPanel learner={learner} />
              <Link
                href={`/guardian/children/${encodeURIComponent(learner.student_ref)}`}
                style={{ color: "var(--color-action-primary)" }}
              >
                پیش رفت دیکھیں →
              </Link>
            </section>
          ))}

          <section
            style={{
              border: "1px solid var(--color-focus-ring)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-4)",
            }}
          >
            <EnrolForm onEnrolled={load} />
          </section>

          <section style={{ display: "grid", gap: "var(--space-2)" }}>
            <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>سرگرمی کا ریکارڈ</h2>
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
              یہ ریکارڈ تبدیل نہیں کیا جا سکتا۔
            </p>
            <AuditList events={events} names={names} />
          </section>

          <Button variant="ghost" label="باہر نکلیں" onClick={() => void sessionStore.signOut()} />
        </>
      )}
    </GuardianShell>
  );
}

export default function GuardedFamilyPage() {
  return (
    <RequireSession role="guardian" signInPath="/guardian/signin">
      <FamilyPage />
    </RequireSession>
  );
}
