# syntax=docker/dockerfile:1
# Project Taleem — Core API.
# Multi-stage, non-root, minimal. Reproducible: deps are pinned via requirements.lock.

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS builder
COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
# Reproducible install: pin the full runtime closure from the lock, then install the app itself
# WITHOUT re-resolving deps. A rebuild pulls identical versions regardless of upstream releases.
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --upgrade pip \
 && pip install --require-hashes=false -r requirements.lock \
 && pip install --no-deps .

FROM base AS runtime
# Non-root user (least privilege).
RUN useradd --create-home --uid 10001 taleem
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src /app/src
# Alembic config + migrations so the container can run `alembic upgrade head` against PostgreSQL
# (the app never create_all()s on a non-SQLite engine — the migrations are the authoritative schema).
COPY alembic.ini ./
COPY alembic ./alembic
ENV PATH="/opt/venv/bin:$PATH" \
    TALEEM_ENV=production \
    PYTHONPATH=/app/src
USER taleem
EXPOSE 8000

# Container-level liveness probe hitting the app's health endpoint.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "taleem_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
