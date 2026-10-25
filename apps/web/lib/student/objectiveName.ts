// What a learner (or guardian) sees for an objective: the lesson's title in the content's own
// language, never the curriculum code ("ETH-G4-HON-01" means nothing to a nine-year-old). Pure.
//
// Titles come from the server's cohort-filtered read models (`objective_titles`, a manifest's
// `title`, …): a real learner is only ever sent real lessons' titles. The code is used only when the
// server sent no title at all (an older server, or an objective whose lesson is no longer
// published), so the screen still says something rather than nothing.

import { pickLocalized } from "../i18n/content";
import { INSTRUCTION_LOCALE_PREFERENCE } from "./journey";

/** `{objective_code: {locale: title}}` as the read models send it. */
export type ObjectiveTitles = Record<string, Record<string, string> | null | undefined>;

export type ObjectiveName =
  /** The lesson title, with the locale it was authored in (drives lang/dir). */
  | { kind: "title"; text: string; locale: string; code: string }
  /** No title known: the bare code, shown as an isolated Latin token. */
  | { kind: "code"; text: string; code: string };

export function objectiveName(
  code: string,
  titles: ObjectiveTitles | null | undefined,
  preference: readonly string[] = INSTRUCTION_LOCALE_PREFERENCE,
): ObjectiveName {
  const picked = pickLocalized(titles?.[code] ?? null, preference);
  return picked ? { kind: "title", text: picked.text, locale: picked.locale, code } : { kind: "code", text: code, code };
}

/** Merge title maps (later maps win), skipping empty entries. */
export function mergeTitles(...maps: Array<ObjectiveTitles | null | undefined>): Record<string, Record<string, string>> {
  const out: Record<string, Record<string, string>> = {};
  for (const map of maps) {
    for (const [code, title] of Object.entries(map ?? {})) {
      if (title && Object.values(title).some((v) => v && v.trim() !== "")) out[code] = title;
    }
  }
  return out;
}
