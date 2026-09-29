# computor-agent
#
# Build:  docker build -t computor-agent -f docker/Dockerfile .
# Run:    see docker-compose.yml / start.sh (recommended)

FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

LABEL maintainer="Computor Team"
LABEL description="Computor Agent - AI tutor for educational platforms"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user
RUN useradd --create-home --uid 1000 agent

WORKDIR /app

# Pinned uv binary (digest-pinned image; Dependabot docker updates move it).
COPY --from=ghcr.io/astral-sh/uv:0.12.15@sha256:62f8c047d0a0e9ece6b53fc63df902585a67a47a7f318ddec4a37db586edc8e3 /uv /usr/local/bin/uv

ENV UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH

# Dependencies exactly as locked in uv.lock (hash-verified; the
# computor-backend packages are pinned to a commit SHA there). Installed in
# their own layer before the sources to keep rebuilds fast.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --extra api --no-install-project

COPY src/ ./src/

# Non-editable install of the project itself; the [api] extra provides the
# dashboard that also serves the /healthz endpoint used by the HEALTHCHECK.
RUN uv sync --frozen --no-dev --extra api --no-editable

# Workspace for cloned student repositories
RUN mkdir -p /data/workspace && chown -R agent:agent /data/workspace

USER agent

# Git identity used when working with student repositories
RUN git config --global user.name "Computor Agent" \
    && git config --global user.email "agent@computor.local" \
    && git config --global init.defaultBranch main

# Strict liveness probe: 200 only when the scheduler runs AND the WebSocket
# is connected. Generous retries (10 x 30s) so a reconnect backoff during a
# brief backend outage doesn't flap the health state.
# NOTE: Docker restarts containers on process EXIT, not on unhealthy status;
# the agent exits nonzero on unrecoverable errors, which triggers the
# restart policy. The healthcheck feeds `docker ps` and optional watchdogs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=10 \
    CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

CMD ["computor-agent", "tutor", "messaging", "-c", "/app/config.yaml", \
     "--api-port", "8080", "--api-host", "0.0.0.0"]
