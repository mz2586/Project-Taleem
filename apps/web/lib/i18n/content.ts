// Content language and direction — independent of the interface locale. Pure.
//
// A lesson is shown in the language it was authored in, whatever language the app's chrome is in.
// An English interface showing an Urdu lesson must still mark that lesson block `lang="ur"
// dir="rtl"`, or a screen reader reads Urdu with an English voice and the Nastaliq lines run the
// wrong way. These helpers produce the attributes for a content container from the content itself;
// they never consult the interface locale.

import { directionOf, type Direction } from "./config";

export interface LocalizedText {
  text: string;
  /** The locale the text was authored in, when the source says. */
  locale: string;
}

/**
 * Pick one rendition of a `{locale: text}` map: the first non-empty entry in `preference`, else the
 * first non-empty entry of any locale. Null when there is no text at all.
 */
export function pickLocalized(
  texts: Record<string, string> | null | undefined,
  preference: readonly string[],
): LocalizedText | null {
  if (!texts) return null;
  for (const locale of preference) {
    const text = texts[locale];
    if (text && text.trim() !== "") return { text, locale };
  }
  for (const [locale, text] of Object.entries(texts)) {
    if (text && text.trim() !== "") return { text, locale };
  }
  return null;
}

// First strong directional character decides, as the Unicode bidi algorithm does for `dir="auto"`.
// Hebrew, Arabic (incl. Supplement/Extended), Syriac, Thaana, NKo, and the Arabic presentation forms.
const RTL_CHAR = /[֐-ࣿיִ-﷿ﹰ-﻿]/;
const LTR_CHAR = /[A-Za-zÀ-ɏͰ-ϿЀ-ӿऀ-෿぀-鿿]/;

/** Direction implied by the text's first strong character, or null for text with none (digits…). */
export function scriptDirection(text: string): Direction | null {
  for (const ch of text) {
    if (RTL_CHAR.test(ch)) return "rtl";
    if (LTR_CHAR.test(ch)) return "ltr";
  }
  return null;
}

export interface ContentAttrs {
  lang?: string;
  dir: Direction | "auto";
}

/**
 * `lang`/`dir` for a block of content. A known content locale wins (it is what the author declared);
 * without one, the direction is read from the text and `lang` is left unset rather than guessed.
 */
export function contentAttrs(source: { locale?: string | null; text?: string | null }): ContentAttrs {
  if (source.locale) return { lang: source.locale, dir: directionOf(source.locale) };
  const detected = source.text ? scriptDirection(source.text) : null;
  return { dir: detected ?? "auto" };
}

/** Whether a content block runs against the surrounding interface direction (needs isolation). */
export function opposesInterface(uiDir: Direction, content: ContentAttrs): boolean {
  return content.dir !== "auto" && content.dir !== uiDir;
}
