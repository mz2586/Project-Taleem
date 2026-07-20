"""Structured logging with runtime PII/secret redaction (pure-stdlib).

Implements the audit remediation AR-C-21: static log-statement scanning cannot catch PII that
arrives at runtime inside an object, so this uses **allow-list serialization** — only explicitly
declared fields are emitted; everything else is dropped. A secondary pattern scrub removes obvious
PII/secret shapes (phone, email, token) even from allow-listed string values as defence in depth.

No child PII or secrets may reach logs (docs/39-logging.md §3, 04-NFR OBS-05).
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Any, TextIO

from .correlation import get_correlation_id

# Fields that are always safe to emit from a log event's structured extras.
DEFAULT_ALLOW = frozenset(
    {
        "event",
        "outcome",
        "duration_ms",
        "status",
        "method",
        "path",
        "route",
        "service",
        "level",
        "trace_id",
        "span_id",
        "flag",
        "context",
        "count",
        "error_code",
    }
)

REDACTED = "[REDACTED]"

# Defence-in-depth pattern scrub (never rely on this alone; allow-list is primary).
_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"(?<!\d)(\+?\d[\d\s-]{7,}\d)(?!\d)"),  # phone-ish
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),  # JWT
    re.compile(r"(?i)(secret|password|token|api[_-]?key)\s*[:=]\s*\S+"),  # secret assignments
)


def scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        out = value
        for pat in _PATTERNS:
            out = pat.sub(REDACTED, out)
        return out
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    # Non-primitive, non-declared types are never emitted verbatim (could hide PII).
    return REDACTED


def redact(event: dict[str, Any], allow: frozenset[str] = DEFAULT_ALLOW) -> dict[str, Any]:
    """Return a dict containing only allow-listed keys, each value pattern-scrubbed."""
    out: dict[str, Any] = {}
    for key, value in event.items():
        if key not in allow:
            continue  # dropped by default — the core of allow-list serialization
        out[key] = scrub_value(value)
    return out


class StructuredLogger:
    """Minimal, dependency-free structured logger emitting one JSON object per line."""

    _LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def __init__(
        self,
        service: str,
        level: str = "INFO",
        stream: TextIO | None = None,
        allow: frozenset[str] = DEFAULT_ALLOW,
    ) -> None:
        self._service = service
        self._threshold = self._LEVELS.get(level.upper(), 20)
        self._stream = stream if stream is not None else sys.stdout
        self._allow = allow

    def _emit(self, level: str, message: str, **fields: Any) -> None:
        if self._LEVELS.get(level, 20) < self._threshold:
            return
        record: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "level": level,
            "service": self._service,
            "msg": scrub_value(message),
            "correlation_id": get_correlation_id(),
        }
        record.update(redact(fields, self._allow))
        self._stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def debug(self, message: str, **fields: Any) -> None:
        self._emit("DEBUG", message, **fields)

    def info(self, message: str, **fields: Any) -> None:
        self._emit("INFO", message, **fields)

    def warn(self, message: str, **fields: Any) -> None:
        self._emit("WARN", message, **fields)

    def error(self, message: str, **fields: Any) -> None:
        self._emit("ERROR", message, **fields)
