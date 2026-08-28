# ── Stage 1: Build virtualenv ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# ── Stage 2: Runtime ────────────────────────────────────────────────────────
FROM python:3.12-slim

RUN apt-get update -qq \
 && apt-get install -y -qq --no-install-recommends fonts-dejavu-core git curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY app     /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/
COPY scripts /app/scripts
COPY static  /app/static

RUN mkdir -p /app/uploads /app/cognee_data/data /app/cognee_data/system \
                           /app/cognee_data/cache /app/cognee_data/logs

ENV PYTHONUNBUFFERED=1 \
    COGNEE_DATA_DIR=/app/cognee_data \
    UPLOAD_DIR=/app/uploads

CMD ["sh", "-c", "uvicorn ${OPENHUMAN_API_MODULE:-app.main:app} --host 0.0.0.0 --port ${PORT:-8000}"]
