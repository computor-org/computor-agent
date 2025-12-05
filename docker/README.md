# Docker Setup for Computor Agent

The Docker container runs the Computor Agent (Tutor AI, etc.) and connects to:
- An LLM server running on your **host machine** (Ollama, LM Studio, etc.)
- The Computor backend API

## Quick Start

### 1. Configure Environment

```bash
# Copy the example environment file
cp docker/.env.example docker/.env

# Edit with your settings
nano docker/.env
```

**Required settings:**
- `COMPUTOR_BACKEND_URL` - Backend API URL
- `COMPUTOR_BACKEND_USERNAME` - API username
- `COMPUTOR_BACKEND_PASSWORD` - API password
- Git credentials file (see below)

### 2. Start LLM Server

The agent needs an LLM server. If using Ollama:

```bash
# Install Ollama (Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull devstral-small

# Start the server
ollama serve
```

### 3. Start the Agent

```bash
# Using Docker Compose (recommended)
docker-compose -f docker/docker-compose.yml up -d

# Attach to container
docker-compose -f docker/docker-compose.yml exec computor-agent bash

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Stop
docker-compose -f docker/docker-compose.yml down
```

## Configuration Reference

### Git Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GIT_USER_NAME` | `Computor Agent` | Git commit author name |
| `GIT_USER_EMAIL` | `agent@computor.local` | Git commit author email |

### LLM Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | Provider: ollama, lmstudio, openai, anthropic, dummy |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | LLM API base URL |
| `LLM_MODEL` | `devstral-small` | Model name |
| `LLM_TEMPERATURE` | `0.7` | Sampling temperature (0.0-2.0) |
| `LLM_API_KEY` | - | API key (for OpenAI, Anthropic, etc.) |

### Backend Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPUTOR_BACKEND_URL` | **required** | Backend API URL |
| `COMPUTOR_BACKEND_USERNAME` | **required** | API username |
| `COMPUTOR_BACKEND_PASSWORD` | **required** | API password |
| `COMPUTOR_BACKEND_TIMEOUT` | `30` | Request timeout (seconds) |

### Agent Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPUTOR_AGENT_NAME` | `Tutor AI` | Agent display name |
| `COMPUTOR_AGENT_DESCRIPTION` | - | Agent description |

### Tutor Configuration

#### Personality

| Variable | Default | Description |
|----------|---------|-------------|
| `TUTOR_PERSONALITY_TONE` | `friendly_professional` | Tone: friendly_professional, strict, casual, encouraging |
| `TUTOR_LANGUAGE` | `en` | Language (ISO 639-1 code) |

#### Security Gate

| Variable | Default | Description |
|----------|---------|-------------|
| `TUTOR_SECURITY_ENABLED` | `true` | Enable security checks |
| `TUTOR_SECURITY_REQUIRE_CONFIRMATION` | `true` | 2-phase threat detection |
| `TUTOR_SECURITY_BLOCK_ON_THREAT` | `true` | Block on confirmed threat |
| `TUTOR_SECURITY_CHECK_MESSAGES` | `true` | Check messages for prompt injection |
| `TUTOR_SECURITY_CHECK_CODE` | `true` | Check code for malicious content |

#### Context

| Variable | Default | Description |
|----------|---------|-------------|
| `TUTOR_CONTEXT_PREVIOUS_MESSAGES` | `3` | Previous messages to include (0-20) |
| `TUTOR_CONTEXT_INCLUDE_COMMENTS` | `true` | Include tutor/lecturer comments |
| `TUTOR_CONTEXT_INCLUDE_REFERENCE` | `false` | Include reference solution |
| `TUTOR_CONTEXT_MAX_CODE_LINES` | `1000` | Max code lines in context |
| `TUTOR_CONTEXT_STUDENT_NOTES_ENABLED` | `false` | Enable student notes storage |

#### Grading

| Variable | Default | Description |
|----------|---------|-------------|
| `TUTOR_GRADING_ENABLED` | `false` | Enable automated grading |
| `TUTOR_GRADING_AUTO_SUBMIT` | `false` | Auto-submit grades to API |

#### Scheduler

| Variable | Default | Description |
|----------|---------|-------------|
| `TUTOR_SCHEDULER_ENABLED` | `true` | Enable scheduler |
| `TUTOR_SCHEDULER_POLL_INTERVAL` | `30` | Poll interval (seconds) |
| `TUTOR_SCHEDULER_MAX_CONCURRENT` | `5` | Max concurrent processing |
| `TUTOR_SCHEDULER_COOLDOWN` | `60` | Cooldown per submission group (seconds) |

### Git Credentials

Git credentials are stored in a **YAML file** (not environment variables) for security.

Create the credentials file at `/data/config/credentials.yaml`:

```yaml
credentials:
  # Host-level (matches all repos on host)
  - pattern: https://gitlab.example.com
    token: glpat-xxxxxxxxxxxx

  # Group-level (matches repos in group)
  - pattern: https://gitlab.example.com/courses
    token: glpat-yyyyyyyyyyyy

  # Project-level (exact match)
  - pattern: https://github.com/org/repo
    token: ghp_zzzzzzzzzzzz
    provider: github  # optional: gitlab, github, generic

  # With optional fields
  - pattern: https://git.internal.com
    token: token123
    provider: gitlab
    username: deploy-bot
    description: Internal server
```

More specific patterns take precedence (project > group > host).

**Important:** The credentials file is stored in the `/data/config` volume which persists across container restarts.

## Volumes

The container uses these persistent volumes:

| Path | Volume Name | Description |
|------|-------------|-------------|
| `/data/workspace` | `computor-agent-workspace` | Repository clones |
| `/data/config` | `computor-agent-config` | Configuration files |
| `/data/notes` | `computor-agent-notes` | Student notes |
| `/data/logs` | `computor-agent-logs` | Log files |

## Building Manually

```bash
# Build
docker build -t computor-agent -f docker/Dockerfile .

# Run (Linux)
docker run -it --rm \
  --add-host=host.docker.internal:host-gateway \
  --env-file docker/.env \
  computor-agent

# Run (macOS/Windows - host.docker.internal works automatically)
docker run -it --rm \
  --env-file docker/.env \
  computor-agent
```

## Usage Inside Container

```bash
# Interactive chat with LLM
computor-agent chat

# Single question
computor-agent ask "What is Python?"

# List providers
computor-agent providers

# Start tutor agent (when backend is configured)
python -m computor_agent.tutor
```

## Troubleshooting

### "Cannot reach LLM server"

1. Make sure your LLM server is running on the host:
   ```bash
   # For Ollama
   curl http://localhost:11434/api/tags

   # For LM Studio
   curl http://localhost:1234/v1/models
   ```

2. On Linux, the container uses `host.docker.internal:host-gateway` (configured in docker-compose)

3. Alternative: Use the Docker bridge IP directly:
   ```bash
   docker network inspect bridge | grep Gateway
   # Usually 172.17.0.1
   ```

### "Backend not configured"

Make sure `.env` file exists and contains:
```
COMPUTOR_BACKEND_URL=https://...
COMPUTOR_BACKEND_USERNAME=...
COMPUTOR_BACKEND_PASSWORD=...
```

### "No credentials configured"

Create the credentials file at `/data/config/credentials.yaml`:
```yaml
credentials:
  - pattern: https://gitlab.example.com
    token: glpat-xxxxxxxxxxxx
```

Or copy an existing file into the container:
```bash
docker cp /path/to/credentials.yaml computor-agent:/data/config/credentials.yaml
```

### Git commit fails

Check Git configuration:
```bash
git config --global user.name
git config --global user.email
```

Set via environment:
```
GIT_USER_NAME=My Agent
GIT_USER_EMAIL=agent@example.com
```
