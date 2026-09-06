#!/usr/bin/env python3
"""Apply Alembic migrations during the Vercel build.

Runs **once per deployment**, in the build container, before any function is served. That is the
right place for a schema change on a serverless platform:

- A migration must not run inside the request path — concurrent cold starts would race each other.
- The database credential stays inside Vercel. Nothing has to copy it into another secret store.

Idempotent: ``alembic upgrade head`` on an already-current database is a no-op, so redeploying is
safe. If no database URL is present (e.g. a preview build before the store is connected) the script
exits 0 without touching anything, so it cannot break a build.

Accepts the URL Vercel's Neon integration injects, preferring the **unpooled** endpoint — poolers
can reject the session-level DDL Alembic needs.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

CORE_API = Path(__file__).resolve().parents[1] / "services" / "core-api"

# Preference order: unpooled first (DDL-safe), then the pooled/default URLs.
URL_ENV_KEYS = (
    "CS_DATABASE_URL",
    "DATABASE_URL_UNPOOLED",
    "POSTGRES_URL_NON_POOLING",
    "DATABASE_URL",
    "POSTGRES_URL",
)


def _resolve_url() -> str | None:
    for key in URL_ENV_KEYS:
        raw = os.environ.get(key)
        if raw:
            return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", raw)
    return None


def main() -> int:
    url = _resolve_url()
    if not url:
        print("[migrate] no database URL in the environment — skipping migrations")
        return 0

    # Never print the URL: host only, so a build log shows what was targeted without leaking
    # credentials.
    host = url.split("@")[-1].split("/")[0] if "@" in url else "(unparsed)"
    print(f"[migrate] applying migrations to {host}")

    os.environ["CS_DATABASE_URL"] = url
    os.environ["TALEEM_DATABASE_URL"] = url
    os.chdir(CORE_API)
    sys.path.insert(0, str(CORE_API / "src"))

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(CORE_API / "alembic.ini"))
    cfg.set_main_option("script_location", str(CORE_API / "alembic"))
    command.upgrade(cfg, "head")
    command.current(cfg)
    print("[migrate] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
