// One report card, presentational (no hooks, so it renders to static markup in the node suite).
// The words come from lib/reporting/view.ts; this file only lays them out:
// - mastery is three dots AND a word (the dots are decorative; the word is the meaning);
// - a card with no evidence shows a plain sentence and no figures at all;
// - who issued it ("Issued by Taleem" or the teacher) is a line under the dates; a teacher's note
//   appears only when there is one;
// - a card that failed the server's hash re-check carries a visible warning at the top;
// - authored curriculum text and codes keep their own lang/dir; the teacher's note is dir="auto";
// - the version pin and the card reference are small print at the end of each row / the card.
import Link from "next/link";
import type { ReactNode } from "react";

import { contentAttrs, type LocalizedText } from "@/lib/i18n/content";
import type { Translator } from "@/lib/i18n/translate";
import type { Mastery } from "@/lib/reporting/types";
import { masteryDots, MASTERY_META, type CardView, type ObjectiveView, type SubjectView } from "@/lib/reporting/view";

const small = { margin: 0, fontSize: "var(--font-size-body-min)", opacity: 0.85 } as const;

function Heading({ level, id, children }: { level: 2 | 3 | 4 | 5; id?: string; children: ReactNode }) {
  const style = { margin: 0, fontSize: "var(--font-size-body-min-urdu)" };
  if (level === 2)
    return (
      <h2 id={id} style={style}>
        {children}
      </h2>
    );
  if (level === 3)
    return (
      <h3 id={id} style={style}>
        {children}
      </h3>
    );
  if (level === 4)
    return (
      <h4 id={id} style={style}>
        {children}
      </h4>
    );
  return (
    <h5 id={id} style={style}>
      {children}
    </h5>
  );
}

/** Authored text with its own language and direction. */
function Authored({ value }: { value: LocalizedText }) {
  const attrs = contentAttrs(value);
  return <bdi {...attrs}>{value.text}</bdi>;
}

function Code({ children }: { children: string }) {
  return (
    <bdi dir="ltr" style={{ fontFamily: "var(--font-latin)" }}>
      {children}
    </bdi>
  );
}

/** Three dots filled by how far along, plus the word. Never colour alone. */
export function MasteryIndicator({ mastery, label }: { mastery: Mastery; label: string }) {
  const meta = MASTERY_META[mastery];
  return (
    <span data-mastery={mastery} style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)", flexWrap: "wrap" }}>
      <span aria-hidden="true" style={{ letterSpacing: "0.15em", fontSize: "1.2em", lineHeight: 1 }}>
        {masteryDots(mastery)}
      </span>
      <strong>
        <span aria-hidden="true">{meta.symbol} </span>
        {label}
      </strong>
    </span>
  );
}

function ObjectiveRow({ o }: { o: ObjectiveView }) {
  return (
    <li
      data-print="keep"
      style={{ display: "grid", gap: "var(--space-1)", paddingBlock: "var(--space-2)", borderBottom: "1px solid var(--color-focus-ring)", minWidth: 0 }}
    >
      <span>
        {o.title ? <Authored value={o.title} /> : null}
        {o.title ? " " : null}
        <span style={small}>
          (<Code>{o.code}</Code>)
        </span>
      </span>
      <MasteryIndicator mastery={o.mastery} label={o.masteryLabel} />
      {o.practice ? <span>{o.practice}</span> : null}
      {o.homework ? <span>{o.homework}</span> : null}
      {o.noPractice ? <span>{o.noPractice}</span> : null}
      {o.pin ? <span style={small}>{o.pin}</span> : null}
    </li>
  );
}

function Subject({ s, level, compact, idBase }: { s: SubjectView; level: 3 | 4 | 5; compact: boolean; idBase: string }) {
  const id = `${idBase}-subject-${s.key}`;
  return (
    <section data-print="keep" aria-labelledby={id} style={{ display: "grid", gap: "var(--space-1)", minWidth: 0 }}>
      <Heading level={level} id={id}>
        {s.nameText ? <Authored value={s.nameText} /> : <Code>{s.name}</Code>}
      </Heading>
      <p style={{ margin: 0 }}>{s.summary}</p>
      {compact ? null : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid" }}>
          {s.objectives.map((o) => (
            <ObjectiveRow key={o.code} o={o} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function ReportCardView({
  view,
  t,
  headingLevel = 2,
  compact = false,
  newerHref = null,
  idBase = "card",
}: {
  view: CardView;
  t: Translator;
  /** The card's own heading; subjects sit one level below. */
  headingLevel?: 2 | 3 | 4;
  /** Teacher preview: subject summaries only. */
  compact?: boolean;
  /** Where the newer card lives, when this one was superseded. */
  newerHref?: string | null;
  idBase?: string;
}) {
  const titleId = `${idBase}-title`;
  const sub = (headingLevel + 1) as 3 | 4 | 5;
  return (
    <article
      data-print-card=""
      aria-labelledby={titleId}
      style={{
        display: "grid",
        gap: "var(--space-3)",
        padding: "var(--space-4)",
        border: "1px solid var(--color-focus-ring)",
        borderRadius: "var(--radius-md)",
        minWidth: 0,
        overflowWrap: "anywhere",
      }}
    >
      <div style={{ display: "grid", gap: "var(--space-1)" }}>
        <Heading level={headingLevel} id={titleId}>
          {t("common.reportCard.title")}: <bdi>{view.learnerName}</bdi>
        </Heading>
        {view.isPreview ? <p style={{ margin: 0, fontWeight: 700 }}>{t("common.reportCard.previewBadge")}</p> : null}
        {view.className ? <p style={{ margin: 0 }}>{view.className}</p> : null}
        <p style={{ margin: 0 }}>{view.period}</p>
        {view.issued ? (
          <p data-issuer={view.isSystem ? "system" : "teacher"} style={small}>
            {view.issued}
          </p>
        ) : null}
      </div>

      {view.integrityWarning ? (
        <div
          role="alert"
          data-integrity="failed"
          style={{ display: "grid", gap: "var(--space-1)", padding: "var(--space-3)", border: "2px solid var(--color-danger)", borderRadius: "var(--radius-md)" }}
        >
          <strong>
            <span aria-hidden="true">⚠ </span>
            {t("common.reportCard.integrityTitle")}
          </strong>
          <span>{t("common.reportCard.integrityBody")}</span>
        </div>
      ) : null}

      {view.superseded ? (
        <div role="note" style={{ display: "grid", gap: "var(--space-1)", padding: "var(--space-3)", border: "2px dashed var(--color-danger)", borderRadius: "var(--radius-md)" }}>
          <strong>
            <span aria-hidden="true">⚠ </span>
            {t("common.reportCard.supersededTitle")}
          </strong>
          <span>{t("common.reportCard.supersededBody")}</span>
          {newerHref ? (
            <span data-print="hide">
              <Link
                href={newerHref}
                style={{ color: "var(--color-action-primary)", display: "inline-flex", alignItems: "center", minHeight: "var(--size-touch-min)" }}
              >
                {t("common.reportCard.viewNewer")}
              </Link>
            </span>
          ) : null}
        </div>
      ) : null}
      {view.corrects ? <p style={small}>{t("common.reportCard.corrects")}</p> : null}

      {!view.hasEvidence ? (
        <section data-no-evidence="" aria-labelledby={`${idBase}-none`} style={{ display: "grid", gap: "var(--space-1)" }}>
          <Heading level={sub} id={`${idBase}-none`}>
            {t("common.reportCard.noEvidenceTitle")}
          </Heading>
          <p style={{ margin: 0 }}>{t("common.reportCard.noEvidenceBody")}</p>
        </section>
      ) : (
        <>
          {view.totals.length > 0 ? (
            <section data-totals="" aria-labelledby={`${idBase}-totals`} style={{ display: "grid", gap: "var(--space-1)" }}>
              <Heading level={sub} id={`${idBase}-totals`}>
                {t("common.reportCard.totalsTitle")}
              </Heading>
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                {view.totals.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ) : null}
          <div role="group" aria-label={t("common.reportCard.subjectsLabel")} style={{ display: "grid", gap: "var(--space-4)" }}>
            {view.subjects.map((s) => (
              <Subject key={s.key} s={s} level={sub} compact={compact} idBase={idBase} />
            ))}
          </div>
        </>
      )}

      {view.comment ? (
        <section data-print="keep" aria-labelledby={`${idBase}-comment`} style={{ display: "grid", gap: "var(--space-1)" }}>
          <Heading level={sub} id={`${idBase}-comment`}>
            {t("common.reportCard.commentTitle")}
          </Heading>
          <p dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap" }}>
            {view.comment}
          </p>
          {view.commentBy ? <p style={small}>{view.commentBy}</p> : null}
        </section>
      ) : null}

      {view.curriculum || view.reference ? (
        <div style={{ display: "grid", gap: "var(--space-1)" }}>
          {view.curriculum ? <p style={small}>{view.curriculum}</p> : null}
          {view.reference ? <p style={small}>{view.reference}</p> : null}
        </div>
      ) : null}
    </article>
  );
}
