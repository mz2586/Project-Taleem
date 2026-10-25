// The academic record (PROGRESSION_AND_EXAMINATION_CONTRACT §3), shared by the learner's "My record"
// and the guardian's child "Record". Presentational and server-safe; every string comes from
// lib/progression/view.ts `recordView`. Grade completion is labelled "not an accredited certificate";
// an unfinished sitting reads "not finished (not a fail)".
import Link from "next/link";

import { ButtonLink } from "@/design-system/ButtonLink";
import { isoDateTime } from "@/lib/guardian/format";
import type { Translator } from "@/lib/i18n/translate";
import type { RecordView } from "@/lib/progression/view";

import { ClaimLine, LocalText, StateMark } from "./parts";

const card = {
  display: "grid",
  gap: "var(--space-2)",
  padding: "var(--space-3)",
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-bg-canvas)",
  minWidth: 0,
} as const;

const SITTING_SYMBOL = { passed: "★", not_yet: "◐", incomplete: "…" } as const;

export function RecordSections({ view, t }: { view: RecordView; t: Translator }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-4)", minWidth: 0 }}>
      <p style={{ margin: 0 }}>{t("progression.record.intro")}</p>
      {view.grade ? (
        <p data-grade="" style={{ margin: 0, fontWeight: 700, fontSize: "var(--font-size-body-min-urdu)" }}>
          {view.grade}
        </p>
      ) : null}

      {view.gradeCompletion ? (
        <section aria-labelledby="record-grade-complete" data-grade-complete="" style={{ ...card, border: "2px solid var(--color-brand)" }}>
          <h2 id="record-grade-complete" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
            <span aria-hidden="true">★ </span>
            {t("progression.record.gradeCompleteTitle")}
          </h2>
          <p style={{ margin: 0 }}>{view.gradeCompletion.text}</p>
          {view.gradeCompletion.date ? <p style={{ margin: 0 }}>{view.gradeCompletion.date}</p> : null}
        </section>
      ) : null}

      <section aria-labelledby="record-units" style={{ display: "grid", gap: "var(--space-2)" }}>
        <h2 id="record-units" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
          {t("progression.record.unitsTitle")}
        </h2>
        {view.subjects.map((subject) => (
          <section key={subject.key} aria-labelledby={`record-subject-${subject.key}`} style={{ display: "grid", gap: "var(--space-2)" }}>
            <h3 id={`record-subject-${subject.key}`} style={{ margin: 0 }}>
              <LocalText value={subject.title} />
            </h3>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
              {subject.units.map((unit) => (
                <li key={unit.key} data-unit={unit.key} style={card}>
                  <strong>
                    <LocalText value={unit.title} />
                  </strong>
                  <span>
                    <StateMark badge={unit.badge} />
                  </span>
                  <p style={{ margin: 0 }}>{unit.best}</p>
                  {unit.sittings.length > 0 ? (
                    <ol aria-label={t("progression.record.historyLabel")} style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                      {unit.sittings.map((s) => (
                        <li key={s.key} data-sitting-state={s.state}>
                          <span aria-hidden="true">{SITTING_SYMBOL[s.state]} </span>
                          {s.at !== null ? <time dateTime={isoDateTime(s.at)}>{s.text}</time> : s.text}
                        </li>
                      ))}
                    </ol>
                  ) : null}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </section>

      <section aria-labelledby="record-lessons" style={card}>
        <h2 id="record-lessons" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
          {t("progression.record.lessonsMasteredTitle")}
        </h2>
        <p style={{ margin: 0 }}>{view.lessonsMastered.count}</p>
        {view.lessonsMastered.titles.length > 0 ? (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
            {view.lessonsMastered.titles.map((title, i) => (
              <li key={i}>
                <span aria-hidden="true">★ </span>
                <LocalText value={title} />
              </li>
            ))}
          </ul>
        ) : view.lessonsMastered.none ? (
          <p style={{ margin: 0 }}>{t("progression.record.noLessonsMastered")}</p>
        ) : null}
      </section>

      <section aria-labelledby="record-cards" style={card}>
        <h2 id="record-cards" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
          {t("progression.record.reportCardsTitle")}
        </h2>
        {view.reportCards.length > 0 ? (
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
            {view.reportCards.map((c) => (
              <li key={c.href}>
                <Link href={c.href}>{c.label}</Link>
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ margin: 0 }}>{t("progression.record.noReportCards")}</p>
        )}
        <div>
          <ButtonLink href={view.reportCardsHref} variant="ghost" label={t("progression.record.reportCardsLink")} />
        </div>
      </section>

      <ClaimLine text={view.claim} />
      {view.derivedAt ? <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{view.derivedAt}</p> : null}
    </div>
  );
}
