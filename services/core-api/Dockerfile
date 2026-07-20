# syntax=docker/dockerfile:1
# Project Taleem — Core API (M1 walking skeleton).
# Multi-stage, non-root, minimal. Production build; not executed in the review sandbox (no registry access).

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

FROM base AS builder
COPY pyproject.toml README.md ./
COPY src ./src
# Install into a venv we can copy to the runtime layer.
RUN python -m venv /opt/venv \
 && . /opt/venv/bin/activate \
 && pip install --upgrade pip \
 && pip install .

FROM base AS runtime
# Non-root user (least privilege).
RUN useradd --create-home --uid 10001 taleem
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src /app/src
ENV PATH="/opt/venv/bin:$PATH" \
    TALEEM_ENV=production \
    PYTHONPATH=/app/src
USER taleem
EXPOSE 8000

# Container-level liveness probe hitting the app's health endpoint.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "taleem_core.main:app", "--host", "0.0.0.0", "--port", "8000"]
