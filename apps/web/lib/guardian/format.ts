// Locale-aware dates for the guardian screens. Pure (Intl only).
//
// Audit events and sessions carry Unix seconds. The old pages printed `toLocaleString("ur-PK")`
// whatever the interface language, and ISO dates ("2026-10-22") for sessions; these format in the
// guardian's interface locale with the same digit choice as every other number.
import type { Locale } from "../i18n/config";
import { intlLocale, type DigitStyle } from "../i18n/format";

export interface DateFormatOptions {
  digits?: DigitStyle;
  /** For tests and for a deployment that pins a zone; the device's zone otherwise. */
  timeZone?: string;
}

function format(
  epochSeconds: number,
  locale: Locale,
  intl: Intl.DateTimeFormatOptions,
  options: DateFormatOptions,
): string {
  if (!Number.isFinite(epochSeconds)) return "";
  const date = new Date(epochSeconds * 1000);
  const settings = { ...intl, ...(options.timeZone ? { timeZone: options.timeZone } : {}) };
  try {
    return new Intl.DateTimeFormat(intlLocale(locale, options.digits ?? "western"), settings).format(date);
  } catch {
    return new Intl.DateTimeFormat("en-u-nu-latn", settings).format(date);
  }
}

/** "22 Oct 2026, 14:05" in the guardian's language. */
export function formatDateTime(epochSeconds: number, locale: Locale, options: DateFormatOptions = {}): string {
  return format(epochSeconds, locale, { dateStyle: "medium", timeStyle: "short" }, options);
}

/** "22 Oct 2026". */
export function formatDate(epochSeconds: number, locale: Locale, options: DateFormatOptions = {}): string {
  return format(epochSeconds, locale, { dateStyle: "medium" }, options);
}

/** "A, B and C" in the guardian's language (Intl.ListFormat), with a plain fallback. */
export function formatList(items: readonly string[], locale: Locale): string {
  try {
    return new Intl.ListFormat(locale, { style: "long", type: "conjunction" }).format(items);
  } catch {
    return items.join(locale === "ur" ? "، " : ", ");
  }
}

/** ISO string for a `<time dateTime>` attribute. */
export function isoDateTime(epochSeconds: number): string | undefined {
  return Number.isFinite(epochSeconds) ? new Date(epochSeconds * 1000).toISOString() : undefined;
}
