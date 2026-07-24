"""RFC 9457 Problem Details error contract (pure-stdlib).

One error shape everywhere; never leak stack traces or PII to clients — only a traceId
(docs/10-api-design.md §4, docs/13-security-model.md §4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .correlation import get_correlation_id


@dataclass
class Problem(Exception):
    """A Problem Details error. Carries an app error code and a client-safe message."""

    status: int
    code: str
    title: str
    detail: str = ""
    type: str = "about:blank"
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self, instance: str | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "code": self.code,
        }
        if self.detail:
            body["detail"] = self.detail
        if instance:
            body["instance"] = instance
        if self.errors:
            body["errors"] = self.errors
        trace = get_correlation_id()
        if trace:
            body["traceId"] = trace
        return body


def validation_error(detail: str, errors: list[dict[str, str]] | None = None) -> Problem:
    return Problem(422, "VALIDATION_FAILED", "Validation failed", detail, errors=errors or [])


def not_found(detail: str = "Resource not found") -> Problem:
    return Problem(404, "NOT_FOUND", "Not found", detail)


def forbidden(detail: str = "Not permitted") -> Problem:
    # Uniform, non-enumerating (docs/11 §10). Do not reveal existence.
    return Problem(403, "FORBIDDEN", "Forbidden", detail)


def unauthorized(detail: str = "Authentication required") -> Problem:
    return Problem(401, "UNAUTHORIZED", "Unauthorized", detail)


def conflict(detail: str = "Concurrent modification; please retry") -> Problem:
    # 409: an optimistic-lock conflict the caller may safely retry. Never leaks the losing writer.
    return Problem(409, "CONFLICT", "Conflict", detail)
