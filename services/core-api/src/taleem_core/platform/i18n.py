"""Localization framework (pure-stdlib), Urdu-first.

All user-facing strings are externalized (docs/04-NFR L10N-02); no hardcoded copy.
Supports message catalogs per locale with fallback, and numeral rendering per pedagogical
context (Eastern-Arabic vs Western — FOUNDER_DECISIONS FD-15).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Eastern-Arabic (Urdu) digits ۰-۹
_EASTERN = "۰۱۲۳۴۵۶۷۸۹"
_WESTERN = "0123456789"
_TO_EASTERN = dict(zip(_WESTERN, _EASTERN, strict=True))


class NumeralSystem:
    WESTERN = "western"
    EASTERN = "eastern"


def render_numerals(text: str, system: str) -> str:
    """Render digits in the given system. Default content stays Western for IDs/board docs."""
    if system == NumeralSystem.EASTERN:
        return "".join(_TO_EASTERN.get(ch, ch) for ch in text)
    return text


@dataclass
class Catalog:
    """A message catalog keyed by locale, e.g. {'ur': {...}, 'en': {...}}."""

    default_locale: str = "ur"
    fallback_locale: str = "en"
    messages: dict[str, dict[str, str]] = field(default_factory=dict)

    def add(self, locale: str, key: str, value: str) -> None:
        self.messages.setdefault(locale, {})[key] = value

    def translate(self, key: str, locale: str | None = None, **params: object) -> str:
        loc = locale or self.default_locale
        table = self.messages.get(loc, {})
        template = table.get(key)
        if template is None:
            template = self.messages.get(self.fallback_locale, {}).get(key)
        if template is None:
            # Never crash on a missing string; surface the key so it is caught in QA.
            return f"⟪{key}⟫"
        try:
            return template.format(**params) if params else template
        except (KeyError, IndexError):
            return template


def default_catalog() -> Catalog:
    """Seed catalog for the walking skeleton (nav/system strings only — no child content)."""
    c = Catalog(default_locale="ur", fallback_locale="en")
    c.add("en", "app.name", "Taleem")
    c.add("ur", "app.name", "تعلیم")
    c.add("en", "health.ok", "Service healthy")
    c.add("ur", "health.ok", "سروس درست ہے")
    c.add("en", "error.generic", "Something went wrong")
    c.add("ur", "error.generic", "کچھ غلط ہو گیا")
    return c
