# computor-agent
#
# Build:  docker build -t computor-agent -f docker/Dockerfile .
# Run:    see docker-compose.yml / start.sh (recommended)

FROM python:3.11-slim-bookworm

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

# Dependencies from the computor-backend repo (not on PyPI). They change
# rarely, so install them in their own layer to keep rebuilds fast.
RUN pip install --upgrade pip \
    && pip install \
        "computor-types @ git+https://github.com/computor-org/computor-backend.git@release/2026.10#subdirectory=computor-types" \
        "computor-client @ git+https://github.com/computor-org/computor-backend.git@release/2026.10#subdirectory=computor-client"

COPY pyproject.toml README.md ./
COPY src/ ./src/

# Non-editable install; the [api] extra provides the dashboard that also
# serves the /healthz endpoint used by the HEALTHCHECK below.
RUN pip install ".[api]"

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
