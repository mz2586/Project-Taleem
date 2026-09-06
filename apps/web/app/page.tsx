// Landing page. Replaces the M1 placeholder that said, in its own words, "Governance-safe
// scaffolding only".
//
// Two doors, and the child's is first. That ordering is the whole design: the person who opens this
// most often is a child on a shared phone, and they should not have to read past an adult's
// onboarding to reach their lesson. A server component — nothing here needs a session, and a static
// first paint is what a 2G connection deserves.

import Link from "next/link";

const linkCard = {
  display: "grid",
  gap: "var(--space-1)",
  padding: "var(--space-4)",
  borderRadius: "var(--radius-md)",
  textDecoration: "none",
  color: "var(--color-text-primary)",
  minHeight: "var(--size-touch-min)",
} as const;

export default function Home() {
  return (
    <main
      style={{
        maxWidth: 460,
        margin: "0 auto",
        padding: "var(--space-6) var(--space-4)",
        display: "grid",
        gap: "var(--space-6)",
        alignContent: "start",
        minHeight: "100vh",
      }}
    >
      <header style={{ display: "grid", gap: "var(--space-2)" }}>
        <h1 style={{ margin: 0, color: "var(--color-brand)", fontSize: "40px" }}>تعلیم</h1>
        <p style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
          ہر بچے کے لیے ایک حقیقی اسکول — آپ کے فون پر، انٹرنیٹ کے بغیر بھی۔
        </p>
      </header>

      <nav aria-label="داخلہ" style={{ display: "grid", gap: "var(--space-3)" }}>
        <Link
          href="/signin"
          style={{
            ...linkCard,
            background: "var(--color-brand)",
            color: "var(--color-on-brand)",
          }}
        >
          <strong style={{ fontSize: "22px" }}>میں طالبِ علم ہوں</strong>
          <span>اپنے گھر کا کوڈ اور پن سے داخل ہوں</span>
        </Link>

        <Link
          href="/guardian/signin"
          style={{ ...linkCard, border: "1px solid var(--color-focus-ring)" }}
        >
          <strong style={{ fontSize: "22px" }}>میں سرپرست ہوں</strong>
          <span>اپنے بچے کی پیش رفت اور اجازتیں دیکھیں</span>
        </Link>

        <Link
          href="/join"
          style={{ ...linkCard, border: "1px solid var(--color-focus-ring)" }}
        >
          <strong style={{ fontSize: "22px" }}>نیا داخلہ</strong>
          <span>اپنے بچے کو داخل کروائیں — مفت</span>
        </Link>
      </nav>

      <section style={{ display: "grid", gap: "var(--space-3)" }}>
        <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>تعلیم کیا ہے؟</h2>
        <ul style={{ margin: 0, paddingInlineStart: "1.2em", display: "grid", gap: "var(--space-2)" }}>
          <li>اردو میں مکمل نصاب — جماعت کے حساب سے۔</li>
          <li>ایک استاد جو آپ کے بچے کی رفتار سے پڑھاتا ہے۔</li>
          <li>انٹرنیٹ نہ ہو تو بھی سبق چلتا رہتا ہے۔</li>
          <li>سرپرست ہر وقت پیش رفت دیکھ سکتے ہیں۔</li>
        </ul>
      </section>

      <section
        style={{
          border: "1px solid var(--color-focus-ring)",
          borderRadius: "var(--radius-md)",
          padding: "var(--space-4)",
          display: "grid",
          gap: "var(--space-2)",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>بچوں کی حفاظت</h2>
        <p style={{ margin: 0 }}>
          کوئی بچہ اپنے سرپرست کی اجازت کے بغیر داخل نہیں ہو سکتا۔ ہم بچوں کی ای میل، فون نمبر یا پتہ
          محفوظ نہیں کرتے۔ سرپرست جب چاہیں اجازت واپس لے سکتے ہیں۔
        </p>
      </section>
    </main>
  );
}
