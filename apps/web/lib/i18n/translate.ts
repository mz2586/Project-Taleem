// `t()` — typed lookup with `{placeholder}` interpolation. Pure, so it works in server components and
// tests; the React binding is `useLocale()`.
import { BUILTIN_DEFAULT_LOCALE, type Locale } from "./config";
import { formatNumber, type DigitStyle } from "./format";
import { CATALOGS, type MessageKey } from "./messages";

export type MessageParams = Record<string, string | number>;
export type Translator = (key: MessageKey, params?: MessageParams) => string;

function lookup(locale: Locale, key: string): string | undefined {
  let node: unknown = CATALOGS[locale];
  for (const part of key.split(".")) {
    if (node === null || typeof node !== "object") return undefined;
    node = (node as Record<string, unknown>)[part];
  }
  return typeof node === "string" ? node : undefined;
}

/**
 * Translate `key` for `locale`. The types make a missing key impossible at compile time; at run time
 * a missing string falls back to the built-in default locale, then to the key itself — never to an
 * empty string, which would render an invisible button. Numbers in `params` are formatted for the
 * locale.
 */
export function translate(
  locale: Locale,
  key: MessageKey,
  params?: MessageParams,
  digits: DigitStyle = "western",
): string {
  const template = lookup(locale, key) ?? lookup(BUILTIN_DEFAULT_LOCALE, key) ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    if (value === undefined) return match;
    return typeof value === "number" ? formatNumber(value, locale, { digits }) : value;
  });
}

export function createTranslator(locale: Locale, digits: DigitStyle = "western"): Translator {
  return (key, params) => translate(locale, key, params, digits);
}
