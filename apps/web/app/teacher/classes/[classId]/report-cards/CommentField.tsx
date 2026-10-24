// The teacher's optional note on one learner's card — the only free text on a report card (≤ 1000
// characters, counted as the server counts them). A real label, a hint, a live counter, and the
// error wired by aria-describedby. Presentational (no hooks) so it renders in the node suite.
import type { Translator } from "@/lib/i18n/translate";
import { COMMENT_MAX, commentLength, commentProblem } from "@/lib/reporting/teacher";

const textareaStyle = {
  width: "100%",
  boxSizing: "border-box" as const,
  minHeight: "5rem",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  font: "inherit",
  fontSize: "var(--font-size-body-min-urdu)",
  resize: "vertical" as const,
};

export function CommentField({
  id,
  value,
  onChange,
  t,
}: {
  id: string;
  value: string;
  onChange: (text: string) => void;
  t: Translator;
}) {
  const problem = commentProblem(value);
  const described = [`${id}-hint`, `${id}-count`, problem ? `${id}-error` : null].filter(Boolean).join(" ");
  return (
    <div style={{ display: "grid", gap: "var(--space-1)" }}>
      <label htmlFor={id}>{t("teacher.reportCards.commentLabel")}</label>
      <span id={`${id}-hint`} style={{ fontSize: "var(--font-size-body-min)" }}>
        {t("teacher.reportCards.commentHint", { max: COMMENT_MAX })}
      </span>
      <textarea
        id={id}
        dir="auto"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-invalid={problem ? true : undefined}
        aria-describedby={described}
        style={textareaStyle}
      />
      <span id={`${id}-count`} style={{ fontSize: "var(--font-size-body-min)" }}>
        {t("teacher.reportCards.commentCount", { count: commentLength(value), max: COMMENT_MAX })}
      </span>
      {problem ? (
        <span id={`${id}-error`} role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-body-min)" }}>
          {t(problem, { max: COMMENT_MAX })}
        </span>
      ) : null}
    </div>
  );
}
