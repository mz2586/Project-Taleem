// Subjects → Units → Lessons (PROGRESSION_AND_EXAMINATION_CONTRACT §1), presentational and
// server-safe. Each unit is a native <details> (keyboard and screen-reader friendly, no script
// needed), open when the child is working in it. Every state is a shape plus words; "Practice done"
// and "Mastered" never look or read the same. A "Unit check" entry appears only when the server says
// the unit's check is available.
import { ButtonLink } from "@/design-system/ButtonLink";
import type { PathView, UnitView } from "@/lib/progression/wire";
import {
  checkEntry,
  checkHref,
  gradeText,
  lessonBadge,
  lessonLegend,
  lessonTitle,
  titleOr,
  unitBadge,
  unitProgress,
  type ViewContext,
} from "@/lib/progression/view";

import { ClaimLine, LocalText, StateMark } from "./parts";

const card = {
  display: "grid",
  gap: "var(--space-2)",
  padding: "var(--space-3)",
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  background: "var(--color-bg-canvas)",
} as const;

export interface PathBrowserProps {
  path: PathView;
  ctx: ViewContext;
  /** Units with a sitting remembered on this phone (so the entry says "Continue"). */
  storedSittings?: ReadonlySet<string>;
}

export function PathBrowser({ path, ctx, storedSittings }: PathBrowserProps) {
  const { t } = ctx;
  const grade = gradeText(path.grade, t);
  const next = path.nextStep;
  return (
    <div style={{ display: "grid", gap: "var(--space-4)", minWidth: 0 }}>
      <p style={{ margin: 0 }}>{grade ? t("progression.path.intro", { grade }) : t("progression.path.introNoGrade")}</p>

      {path.gradeCompleted && grade ? (
        <p data-grade-complete="" style={{ margin: 0, fontWeight: 700 }}>
          <span aria-hidden="true">★ </span>
          {t("progression.path.gradeCompleted", { grade })}
        </p>
      ) : null}

      {next ? (
        <section aria-labelledby="path-next" style={{ ...card, border: "2px solid var(--color-action-primary)" }}>
          <h2 id="path-next" style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
            {t("progression.path.nextTitle")}
          </h2>
          {next.title ? (
            <p style={{ margin: 0 }}>
              <LocalText value={next.title} />
            </p>
          ) : null}
          <div>
            {next.kind === "unit_check" && next.unitKey ? (
              <ButtonLink href={checkHref(next.unitKey)} variant="brand" label={t("progression.path.nextCheck")} />
            ) : (
              <ButtonLink href="/student/session" variant="brand" label={t("progression.path.nextLesson")} icon={<span aria-hidden="true">▶</span>} />
            )}
          </div>
        </section>
      ) : null}

      {path.subjects.map((subject) => {
        const headingId = `subject-${subject.key}`;
        const name = titleOr(subject.title, t("progression.path.untitledSubject"));
        return (
          <section key={subject.key} aria-labelledby={headingId} style={{ display: "grid", gap: "var(--space-2)" }}>
            <h2 id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              <LocalText value={name} />
            </h2>
            <ul aria-label={t("progression.path.unitsLabel", { subject: name.text })} style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
              {subject.units.map((unit) => (
                <li key={unit.key}>
                  <UnitBlock unit={unit} ctx={ctx} stored={storedSittings?.has(unit.key) ?? false} />
                </li>
              ))}
            </ul>
          </section>
        );
      })}

      <details style={card}>
        <summary style={{ cursor: "pointer", fontWeight: 700 }}>{t("progression.path.legendTitle")}</summary>
        <dl style={{ margin: 0, display: "grid", gap: "var(--space-2)" }}>
          {lessonLegend(t).map((entry) => (
            <div key={entry.state}>
              <dt>
                <StateMark badge={entry} />
              </dt>
              <dd style={{ margin: 0 }}>{entry.meaning}</dd>
            </div>
          ))}
        </dl>
      </details>
    </div>
  );
}

function UnitBlock({ unit, ctx, stored }: { unit: UnitView; ctx: ViewContext; stored: boolean }) {
  const { t } = ctx;
  const entry = checkEntry(unit, ctx, stored);
  const open = unit.state === "in_progress" || unit.state === "ready_for_check" || stored;
  const title = titleOr(unit.title, t("progression.path.untitledUnit"));
  return (
    <details open={open} data-unit={unit.key} data-state={unit.state} style={card}>
      <summary style={{ cursor: "pointer", display: "grid", gap: "var(--space-1)" }}>
        <strong style={{ fontSize: "var(--font-size-body-min-urdu)" }}>
          <LocalText value={title} />
        </strong>
        <span>
          <StateMark badge={unitBadge(unit.state, t)} />
        </span>
      </summary>
      <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{unitProgress(unit, t)}</p>
      {unit.lessons.length === 0 ? (
        <p style={{ margin: 0 }}>{t("progression.path.noLessons")}</p>
      ) : (
        <ol aria-label={t("progression.path.lessonsLabel")} style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-2)" }}>
          {unit.lessons.map((lesson) => (
            <li key={lesson.lessonId} data-lesson-state={lesson.state} style={{ display: "grid", gap: "var(--space-1)" }}>
              <LocalText value={lessonTitle(lesson, t)} />
              <span>
                <StateMark badge={lessonBadge(lesson.state, t)} />
              </span>
            </li>
          ))}
        </ol>
      )}
      {entry ? (
        <div data-check-entry="" style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
          <ButtonLink href={entry.href} variant="brand" label={entry.label} icon={<span aria-hidden="true">📝</span>} />
          {entry.best ? <p style={{ margin: 0 }}>{entry.best}</p> : null}
          {entry.note ? <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{entry.note}</p> : null}
          <ClaimLine text={entry.claim} />
        </div>
      ) : null}
    </details>
  );
}
