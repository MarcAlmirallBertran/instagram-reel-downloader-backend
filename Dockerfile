FROM ghcr.io/astral-sh/uv:python3.11-trixie-slim AS build

ENV PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/opt/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN uv sync --no-dev --compile-bytecode --locked

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# System dependencies: ffmpeg required by pydub for audio extraction
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

COPY --from=build /app/.venv /app/.venv
COPY app/ /app/app

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
