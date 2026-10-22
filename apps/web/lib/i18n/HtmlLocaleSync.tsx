"use client";
// Keeps <html lang dir> in step with the resolved interface locale.
//
// The server renders the deployment default (root layout); the person's own locale is only known
// after mount (session and device choice live in localStorage), so this corrects the document
// attributes then. Renders nothing.
import { useEffect } from "react";

import { useLocale } from "./useLocale";

export function HtmlLocaleSync() {
  const { locale, dir } = useLocale();
  useEffect(() => {
    const root = document.documentElement;
    if (root.lang !== locale) root.lang = locale;
    if (root.dir !== dir) root.dir = dir;
  }, [locale, dir]);
  return null;
}
