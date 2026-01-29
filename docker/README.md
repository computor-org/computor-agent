# Docker Setup

Run the Computor Agent in a Docker container.

## Quick Start

### 1. Configure

```bash
cp config.example.yaml config.yaml
# Edit config.yaml with your settings
```

**Required settings in config.yaml:**
- `backend.url` - Backend API URL
- `backend.api_token` or `backend.username`/`password` - Authentication
- `llm.provider`, `llm.model`, `llm.base_url` - LLM settings

### 2. Start LLM Server

The agent needs an LLM server running on your host machine:

```bash
# Ollama
ollama pull devstral-small
ollama serve

# Or LM Studio - start server on port 1234
```

### 3. Run

```bash
# Start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

## Configuration

All configuration is in `config.yaml` at the project root. See [config.example.yaml](../config.example.yaml) for all options.

### LLM Connection

The container uses `host.docker.internal` to reach services on your host machine:

```yaml
llm:
  provider: ollama
  model: devstral-small
  base_url: http://host.docker.internal:11434/v1  # Ollama on host
```

| Provider | Host URL |
|----------|----------|
| Ollama | `http://host.docker.internal:11434/v1` |
| LM Studio | `http://host.docker.internal:1234/v1` |

### Git Credentials

Add credentials for repository access:

```yaml
credentials:
  - pattern: https://gitlab.example.com
    token: glpat-xxxxxxxxxxxx
```

## Commands

```bash
# Messaging agent (default)
docker compose up -d

# Interactive shell
docker compose run --rm computor-agent bash

# Single command
docker compose run --rm computor-agent \
    computor-agent ask "Hello" -p ollama -m devstral-small
```

### Override Command

Edit `docker-compose.yml` to change the default command:

```yaml
command: ["computor-agent", "tutor", "messaging", "-c", "/app/config.yaml", "-v"]
```

## Building

```bash
# Build image
docker build -t computor-agent -f docker/Dockerfile .

# Run manually
docker run -it --rm \
    -v ./config.yaml:/app/config.yaml:ro \
    --add-host=host.docker.internal:host-gateway \
    computor-agent
```

## Troubleshooting

### Cannot reach LLM server

1. Check LLM is running on host:
   ```bash
   curl http://localhost:11434/v1/models
   ```

2. Verify `base_url` uses `host.docker.internal`:
   ```yaml
   llm:
     base_url: http://host.docker.internal:11434/v1
   ```

### Config file not found

Ensure `config.yaml` exists in the project root:
```bash
cp config.example.yaml config.yaml
```

### Authentication failed

Check your `backend` settings in config.yaml:
```yaml
backend:
  url: https://api.computor.example.com
  api_token: ctp_your_token_here
```
