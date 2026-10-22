"use client";
// The interface-language choice for this device, for guardian and sign-in screens. Each language is
// named in itself, so a parent who cannot read the current one can still find their own.
import { useId } from "react";

import { isSupportedLocale, LOCALE_META, SUPPORTED_LOCALES } from "@/lib/i18n/config";
import { useLocale } from "@/lib/i18n/useLocale";

export function LanguagePicker() {
  const { t, locale, setLocale } = useLocale();
  const id = useId();
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: "var(--space-2)" }}>
      <label htmlFor={id} style={{ fontSize: "var(--font-size-body-min)" }}>
        {t("common.interfaceLanguage")}
      </label>
      <select
        id={id}
        value={locale}
        onChange={(e) => {
          const next = e.target.value;
          if (isSupportedLocale(next)) setLocale(next);
        }}
        style={{
          minHeight: "var(--size-touch-min)",
          minWidth: "var(--size-touch-min)",
          padding: "var(--space-1) var(--space-2)",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-focus-ring)",
          background: "var(--color-bg-canvas)",
          color: "var(--color-text-primary)",
          font: "inherit",
        }}
      >
        {SUPPORTED_LOCALES.map((code) => (
          <option key={code} value={code} lang={code} dir={LOCALE_META[code].dir}>
            {LOCALE_META[code].nativeName}
          </option>
        ))}
      </select>
    </span>
  );
}
