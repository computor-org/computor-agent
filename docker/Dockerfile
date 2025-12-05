# computor-agent
#
# This Dockerfile creates an image with computor-agent installed.
# The LLM server (Ollama, LM Studio, etc.) runs on the host machine.
#
# Build:
#   docker build -t computor-agent -f docker/Dockerfile .
#
# Run (connects to LLM on host):
#   docker run -it --rm --add-host=host.docker.internal:host-gateway computor-agent
#
# Or with explicit host IP:
#   docker run -it --rm -e LLM_BASE_URL=http://192.168.1.100:11434/v1 computor-agent

FROM python:3.11-slim

LABEL maintainer="Computor Team"
LABEL description="computor-agent - AI agents for the Computor system"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy package files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install package
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Default environment - connects to LLM server on host
# Use host.docker.internal to reach host machine from container
ENV LLM_PROVIDER=ollama
ENV LLM_BASE_URL=http://host.docker.internal:11434/v1
ENV LLM_MODEL=devstral-small

# Copy entrypoint script
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
