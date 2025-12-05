# computor-agent
#
# Docker image for running the Computor Agent (Tutor AI, etc.)
#
# Build:
#   docker build -t computor-agent -f docker/Dockerfile .
#
# Run:
#   docker run -it --rm --env-file docker/.env computor-agent
#

FROM python:3.11-slim

LABEL maintainer="Computor Team"
LABEL description="computor-agent - AI agents for the Computor system"

# =============================================================================
# System Configuration
# =============================================================================

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# =============================================================================
# Git Configuration (required for repository operations)
# =============================================================================

# Git user identity - MUST be set for commits
ENV GIT_USER_NAME="Computor Agent"
ENV GIT_USER_EMAIL="agent@computor.local"

# Configure Git (done at runtime in entrypoint)

# =============================================================================
# Application Setup
# =============================================================================

WORKDIR /app

# Copy package files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install package
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -e .

# Create directories for agent data
RUN mkdir -p /data/workspace /data/config /data/notes /data/logs

# =============================================================================
# LLM Provider Configuration
# =============================================================================

# LLM provider settings (connects to host by default)
ENV LLM_PROVIDER=ollama
ENV LLM_BASE_URL=http://host.docker.internal:11434/v1
ENV LLM_MODEL=devstral-small
ENV LLM_TEMPERATURE=0.7
# LLM_API_KEY - set in .env file if needed (for OpenAI, etc.)

# =============================================================================
# Computor Backend Configuration
# =============================================================================

# Backend API settings - MUST be configured via environment
# COMPUTOR_BACKEND_URL=https://api.computor.example.com
# COMPUTOR_BACKEND_USERNAME=agent-user
# COMPUTOR_BACKEND_PASSWORD=secret

ENV COMPUTOR_BACKEND_TIMEOUT=30

# =============================================================================
# Agent Configuration
# =============================================================================

ENV COMPUTOR_AGENT_NAME="Tutor AI"
# COMPUTOR_AGENT_DESCRIPTION - optional

# =============================================================================
# Tutor Configuration
# =============================================================================

# Personality
ENV TUTOR_PERSONALITY_TONE=friendly_professional
ENV TUTOR_LANGUAGE=en

# Security gate
ENV TUTOR_SECURITY_ENABLED=true
ENV TUTOR_SECURITY_REQUIRE_CONFIRMATION=true
ENV TUTOR_SECURITY_BLOCK_ON_THREAT=true
ENV TUTOR_SECURITY_CHECK_MESSAGES=true
ENV TUTOR_SECURITY_CHECK_CODE=true

# Context
ENV TUTOR_CONTEXT_PREVIOUS_MESSAGES=3
ENV TUTOR_CONTEXT_INCLUDE_COMMENTS=true
ENV TUTOR_CONTEXT_INCLUDE_REFERENCE=false
ENV TUTOR_CONTEXT_MAX_CODE_LINES=1000
ENV TUTOR_CONTEXT_STUDENT_NOTES_ENABLED=false
ENV TUTOR_CONTEXT_STUDENT_NOTES_DIR=/data/notes

# Grading
ENV TUTOR_GRADING_ENABLED=false
ENV TUTOR_GRADING_AUTO_SUBMIT=false

# Scheduler
ENV TUTOR_SCHEDULER_ENABLED=true
ENV TUTOR_SCHEDULER_POLL_INTERVAL=30
ENV TUTOR_SCHEDULER_MAX_CONCURRENT=5
ENV TUTOR_SCHEDULER_COOLDOWN=60

# =============================================================================
# Git Credentials (for repository access)
# =============================================================================

# Credentials are stored in a YAML file (not environment variables):
#   /data/config/credentials.yaml
#
# File format:
#   credentials:
#     - pattern: https://gitlab.example.com
#       token: glpat-xxxx
#     - pattern: https://github.com/org/repo
#       token: ghp_yyyy

# =============================================================================
# Workspace Configuration
# =============================================================================

ENV WORKSPACE_ROOT=/data/workspace
ENV CONFIG_DIR=/data/config
ENV LOG_DIR=/data/logs

# =============================================================================
# Volumes
# =============================================================================

# Mount points for persistent data:
# - /data/workspace: Repository clones (student, review, reference)
# - /data/config: Configuration files (tutor.yaml, credentials.yaml)
# - /data/notes: Student notes (per-user UUID files)
# - /data/logs: Log files (threat logs, etc.)

VOLUME ["/data/workspace", "/data/config", "/data/notes", "/data/logs"]

# =============================================================================
# Entrypoint
# =============================================================================

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
