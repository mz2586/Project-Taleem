"""Security response headers — defence-in-depth hardening (pure-stdlib).

Project Taleem's core-api is a JSON API (it renders no HTML), so it can send a strict, conservative
header set on every response: deny framing, forbid MIME sniffing, send no referrer, lock the CSP to
``default-src 'none'``, and never cache API responses (learner data must not persist in shared
caches). HSTS is included because production is HTTPS-only (04-NFR SEC). Applied uniformly by the
observability middleware to both the normal and the fail-closed (kill-switch / Problem) response
paths, so a hardening header can never be dropped on an error path.
"""

from __future__ import annotations

from typing import Protocol

# Static, conservative header set for a JSON-only API. Values are intentionally strict; if a future
# surface needs to relax one (e.g. an HTML export), it should override per-route, not weaken this.
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Cache-Control": "no-store",
}


class _Headers(Protocol):
    """Minimal structural type covering both a plain dict and Starlette's ``MutableHeaders``."""

    def setdefault(self, key: str, value: str) -> object: ...


def apply_security_headers(headers: _Headers) -> None:
    """Set the hardening headers on a response's header map (idempotent; never overwrites a
    route-specific value that is already present)."""
    for name, value in SECURITY_HEADERS.items():
        headers.setdefault(name, value)
