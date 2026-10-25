// "You chose this lesson" — shown above a lesson the child picked themself, with any prerequisites
// not finished yet as a gentle hint (links to those lessons), never a block. No hooks: server-safe,
// so the node suite renders it with react-dom/server. View model: lib/student/chosenLesson.ts.
import Link from "next/link";

import { LocalText } from "@/components/progression/parts";
import type { ChoiceNoticeView } from "@/lib/student/chosenLesson";

export function ChosenLessonNotice({ notice }: { notice: ChoiceNoticeView }) {
  return (
    <section
      data-chosen-lesson=""
      aria-label={notice.title}
      style={{
        display: "grid",
        gap: "var(--space-2)",
        padding: "var(--space-3)",
        border: "1px solid var(--color-focus-ring)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-bg-canvas)",
      }}
    >
      <strong>
        <span aria-hidden="true">👆 </span>
        {notice.title}
      </strong>
      <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{notice.body}</p>
      {notice.hint ? (
        <div data-prerequisite-hint="" style={{ display: "grid", gap: "var(--space-1)" }}>
          <p style={{ margin: 0 }}>
            <span aria-hidden="true">💡 </span>
            {notice.hint.intro}
          </p>
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
            {notice.hint.prerequisites.map((p) => (
              <li key={p.code}>
                <Link href={p.href}>
                  <LocalText value={p.title} />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
