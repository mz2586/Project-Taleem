"use client";
// One unit-check question (PROGRESSION_AND_EXAMINATION_CONTRACT §2). Every kind is answered the
// same way the lesson player answers it (ITEM_INTERACTION_CONTRACT): choose here, fill / order /
// match / sort through components/student/ItemInteraction. A check gives no right/wrong feedback per
// question — the result comes at the end — so a choose item is picked first and then saved, which
// keeps a slip of a small finger from costing the child a question.
import { useId, useState } from "react";

import { ItemInteraction } from "@/components/student/ItemInteraction";
import { ReadAloud } from "@/components/student/ReadAloud";
import { Button, buttonStyle } from "@/design-system/Button";
import { contentAttrs } from "@/lib/i18n/content";
import type { Translator } from "@/lib/i18n/translate";
import type { CheckItemView } from "@/lib/progression/wire";
import { itemKind, type AnswerBody } from "@/lib/student/itemAnswer";

export interface CheckQuestionProps {
  item: CheckItemView;
  t: Translator;
  formatNumber: (value: number) => string;
  /** "Question n of N". */
  progress: string;
  /** Saving, or offline: nothing can be sent. */
  disabled: boolean;
  onAnswer: (answer: AnswerBody) => void;
}

export function CheckQuestion({ item, t, formatNumber, progress, disabled, onAnswer }: CheckQuestionProps) {
  const id = useId();
  const [picked, setPicked] = useState<number | null>(null);
  const prompt = item.prompt;
  const promptAttrs = prompt ? contentAttrs({ locale: prompt.locale || null, text: prompt.text }) : null;
  const headingId = `${id}-q`;
  const kind = itemKind(item);

  return (
    <section aria-labelledby={headingId} data-kind={kind} style={{ display: "grid", gap: "var(--space-3)", minWidth: 0 }}>
      <h2 id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {progress}
      </h2>
      {prompt && promptAttrs ? (
        <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
          <p lang={promptAttrs.lang} dir={promptAttrs.dir} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
            {prompt.text}
          </p>
          <ReadAloud text={prompt.text} lang={prompt.locale || null} label={t("student.session.questionAudio")} />
        </div>
      ) : null}

      {kind === "choose" ? (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (picked !== null && !disabled) onAnswer({ option: picked });
          }}
          style={{ display: "grid", gap: "var(--space-2)" }}
        >
          <div role="group" aria-label={t("progression.check.answers")} style={{ display: "grid", gap: "var(--space-2)" }}>
            {item.options.map((option, i) => {
              const on = picked === i;
              const attrs = contentAttrs({ text: option });
              return (
                <button
                  key={i}
                  type="button"
                  aria-pressed={on}
                  disabled={disabled}
                  onClick={() => setPicked(on ? null : i)}
                  style={{
                    ...buttonStyle("ghost", disabled),
                    width: "100%",
                    minHeight: "56px",
                    justifyContent: "space-between",
                    textAlign: "start",
                    border: on ? "4px solid var(--color-action-primary)" : "1px solid var(--color-focus-ring)",
                    fontSize: "var(--font-size-body-min-urdu)",
                  }}
                >
                  <span lang={attrs.lang} dir={attrs.dir}>
                    {option}
                  </span>
                  <span aria-hidden="true">{on ? "●" : "○"}</span>
                </button>
              );
            })}
          </div>
          <div>
            <Button type="submit" variant="brand" label={t("progression.check.save")} disabled={disabled || picked === null} />
          </div>
        </form>
      ) : (
        <ItemInteraction
          key={item.item_ref}
          item={item}
          t={t}
          formatNumber={formatNumber}
          disabled={disabled}
          submitLabel={t("progression.check.save")}
          onSubmit={onAnswer}
        />
      )}
    </section>
  );
}
