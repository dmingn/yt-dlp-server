FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim AS builder

WORKDIR /workdir

ARG SETUPTOOLS_SCM_PRETEND_VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${SETUPTOOLS_SCM_PRETEND_VERSION}

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev --no-install-project

COPY yt_dlp_server ./yt_dlp_server

RUN uv sync --locked --no-dev --no-editable

FROM alpine:latest AS ffmpeg-downloader

WORKDIR /workdir

RUN apk add --no-cache curl xz

ARG TARGETARCH
RUN arch="${TARGETARCH:-amd64}" && \
    case "$arch" in \
    amd64) ffmpeg_flavor="linux64" ;; \
    arm64) ffmpeg_flavor="linuxarm64" ;; \
    *) echo "Unsupported TARGETARCH: $arch" >&2; exit 1 ;; \
    esac && \
    mkdir -p /workdir/ffmpeg && \
    curl -fsSL "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-${ffmpeg_flavor}-gpl.tar.xz" | tar -Jxf - -C /workdir/ffmpeg --strip-components=1

FROM python:3.14-slim

RUN groupadd -g 1000 appgroup && \
    useradd -m -u 1000 -g appgroup appuser && \
    mkdir -p /out /data && \
    chown appuser:appgroup /out /data

WORKDIR /workdir

COPY --from=ffmpeg-downloader --chown=appuser:appgroup /workdir/ffmpeg/bin /usr/local/bin

COPY --from=builder --chown=appuser:appgroup /workdir/.venv /workdir/.venv

ENV PATH="/workdir/.venv/bin:$PATH"

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

ENTRYPOINT ["python", "-m", "yt_dlp_server"]
