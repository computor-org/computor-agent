# computor-agent
#
# Build:  docker build -t computor-agent -f docker/Dockerfile .
# Run:    docker run -it --rm -v ./config.yaml:/app/config.yaml computor-agent

FROM python:3.11-slim

LABEL maintainer="Computor Team"
LABEL description="Computor Agent - AI tutor for educational platforms"

# System setup
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Application setup
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install dependencies from computor-backend repo (not on PyPI)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
        "computor-types @ git+https://github.com/computor-org/computor-backend.git#subdirectory=computor-types" \
        "computor-client @ git+https://github.com/computor-org/computor-backend.git#subdirectory=computor-client" \
    && pip install --no-cache-dir -e .

# Create workspace directory
RUN mkdir -p /data/workspace

# Git configuration
RUN git config --global user.name "Computor Agent" \
    && git config --global user.email "agent@computor.local" \
    && git config --global init.defaultBranch main

CMD ["computor-agent", "tutor", "messaging", "-c", "/app/config.yaml"]
