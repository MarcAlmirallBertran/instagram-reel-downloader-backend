# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv:python3.11-trixie-slim AS build

ENV PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_CACHE_DIR=/opt/uv

WORKDIR /app

# Copy dependency files first for layer caching
COPY pyproject.toml uv.lock ./

# Install production dependencies only
RUN --mount=type=cache,target=/opt/uv \
    uv sync --no-dev --compile-bytecode --locked

FROM debian:trixie-slim AS ffmpeg
ARG TARGETARCH
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates xz-utils wget \
    && rm -rf /var/lib/apt/lists/* \
    && case "$TARGETARCH" in \
         amd64) ARCH=amd64 ;; \
         arm64) ARCH=arm64 ;; \
         *) echo "unsupported arch $TARGETARCH" && exit 1 ;; \
       esac \
    && wget -O /tmp/ffmpeg.tar.xz \
         "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-${ARCH}-static.tar.xz" \
    && mkdir -p /opt/ffmpeg \
    && tar -xJf /tmp/ffmpeg.tar.xz -C /opt/ffmpeg --strip-components=1 \
    && rm /tmp/ffmpeg.tar.xz

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

COPY --from=ffmpeg /opt/ffmpeg/ffmpeg  /usr/local/bin/ffmpeg
COPY --from=ffmpeg /opt/ffmpeg/ffprobe /usr/local/bin/ffprobe

EXPOSE 8000

COPY --from=build /app/.venv /app/.venv
COPY app/ /app/app

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
