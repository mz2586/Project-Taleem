// An objective as a learner sees it: the lesson title, marked with the language it was written in
// (an Urdu title in an English interface is still read by an Urdu voice, right to left). The code
// is shown only when no title is known — see lib/student/objectiveName.ts.
import { contentAttrs } from "@/lib/i18n/content";
import type { ObjectiveName as Name } from "@/lib/student/objectiveName";

export function ObjectiveName({ name }: { name: Name }) {
  if (name.kind === "title") {
    const attrs = contentAttrs({ locale: name.locale, text: name.text });
    return (
      <bdi lang={attrs.lang} dir={attrs.dir} data-objective={name.code}>
        {name.text}
      </bdi>
    );
  }
  return (
    <bdi dir="ltr" style={{ fontFamily: "var(--font-latin)" }}>
      {name.text}
    </bdi>
  );
}
