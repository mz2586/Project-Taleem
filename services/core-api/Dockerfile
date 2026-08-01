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
 && pip install -r requirements.lock \
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
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENV PATH="/opt/venv/bin:$PATH" \
    TALEEM_ENV=production \
    PYTHONPATH=/app/src \
    PORT=8000
USER taleem
EXPOSE 8000

# Container-level liveness probe (port-aware; the app binds $PORT on PaaS platforms).
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import os,urllib.request,sys; p=os.environ.get('PORT','8000'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+p+'/health').status==200 else 1)"

# Default: normalise the DB URL, run migrations, serve on $PORT. Platforms that pass their own start
# command (docker-compose, the Render/Koyeb blueprints) still override this.
CMD ["/usr/local/bin/docker-entrypoint.sh"]
