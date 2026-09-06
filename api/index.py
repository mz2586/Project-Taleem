"""Vercel Python Function entrypoint for the Project Taleem core API.

Vercel's Python runtime serves any module-level ASGI application named ``app``. The FastAPI
application is built by the existing composition root, so this file adds no behaviour of its own —
it exists only so a serverless platform can find the app.

Two deployment facts this entrypoint depends on:

- **Migrations do not run here.** A serverless invocation must not migrate, because concurrent
  cold starts would race. They run once per deployment in the Vercel build step
  (``scripts/vercel_migrate.py``, wired via ``buildCommand``), which also keeps the database
  credential inside the platform. The ``Migrate database`` workflow remains available for
  out-of-band runs.
- **The kill switch is shared state.** It reads ``ops.kill_switch`` from the database on every
  request, so an operator halt takes effect across every instance. Instances are otherwise
  stateless.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# The application package lives in services/core-api/src; Vercel builds from the repository root.
_SRC = Path(__file__).resolve().parents[1] / "services" / "core-api" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _normalise_database_url() -> None:
    """Accept the platform's ``postgres://``/``postgresql://`` URL and set the SQLAlchemy dialect.

    Mirrors ``services/core-api/docker-entrypoint.sh`` so the container and the serverless function
    read the same environment contract.
    """
    if os.environ.get("TALEEM_DATABASE_URL"):
        return
    raw = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
    if raw:
        os.environ["TALEEM_DATABASE_URL"] = re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", raw)


_normalise_database_url()

from taleem_core.main import create_app  # noqa: E402  (import after sys.path/env setup)

app = create_app()
