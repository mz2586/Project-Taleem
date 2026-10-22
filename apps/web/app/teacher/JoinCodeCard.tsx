"use client";
// A class's join code with the plain explanation a teacher passes on: guardians enter it for their
// own child, entering it is how they agree to share progress, and they can stop at any time.
import { useLocale } from "@/lib/i18n/useLocale";

export function JoinCodeCard({
  code,
  className,
  headingLevel = 2,
  headingId,
}: {
  code: string;
  className: string;
  headingLevel?: 2 | 3;
  headingId: string;
}) {
  const { t } = useLocale();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section
      aria-labelledby={headingId}
      style={{
        border: "1px solid var(--color-brand)",
        borderRadius: "var(--radius-md)",
        padding: "var(--space-4)",
        display: "grid",
        gap: "var(--space-2)",
      }}
    >
      <Heading id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        <bdi>{t("teacher.code.label", { name: className })}</bdi>
      </Heading>
      <strong
        // LTR: Latin letters and digits whose groups must be read out in order.
        dir="ltr"
        lang="en"
        style={{ fontFamily: "var(--font-latin)", fontSize: "28px", letterSpacing: "0.15em", textAlign: "center", padding: "var(--space-2)" }}
      >
        {code}
      </strong>
      <p style={{ margin: 0 }}>{t("teacher.code.body")}</p>
      <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("teacher.code.stop")}</p>
    </section>
  );
}
