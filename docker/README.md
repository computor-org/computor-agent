# Docker Setup for computor-agent

The Docker container runs `computor-agent` and connects to an LLM server running on your **host machine**.

## Prerequisites

You need an LLM server running on your host. See [docs/local-llm-setup.md](../docs/local-llm-setup.md) for installation instructions.

**Quick start with Ollama:**
```bash
# Install Ollama (Linux)
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull devstral-small

# Start the server
ollama serve
```

## Build and Run

### Using Docker directly

```bash
# Build the image
docker build -t computor-agent -f docker/Dockerfile .

# Run (Linux - uses host-gateway)
docker run -it --rm \
  --add-host=host.docker.internal:host-gateway \
  computor-agent

# Run (macOS/Windows - host.docker.internal works automatically)
docker run -it --rm computor-agent
```

### Using Docker Compose

```bash
# Start container
docker-compose -f docker/docker-compose.yml up -d

# Attach to container
docker-compose -f docker/docker-compose.yml exec computor-agent bash

# Stop container
docker-compose -f docker/docker-compose.yml down
```

## Configuration

Configure via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | Provider type (ollama, lmstudio, openai) |
| `LLM_BASE_URL` | `http://host.docker.internal:11434/v1` | LLM server URL |
| `LLM_MODEL` | `devstral-small` | Model to use |

**Example with custom settings:**
```bash
docker run -it --rm \
  --add-host=host.docker.internal:host-gateway \
  -e LLM_PROVIDER=lmstudio \
  -e LLM_BASE_URL=http://host.docker.internal:1234/v1 \
  -e LLM_MODEL=gpt-oss-120b \
  computor-agent
```

## Usage Inside Container

```bash
# Interactive chat
computor-agent chat

# Single question
computor-agent ask "What is Python?"

# With streaming
computor-agent ask "Explain recursion" --stream

# List providers
computor-agent providers

# Use dummy provider (no LLM needed)
computor-agent ask "Hello" -p dummy
```

## Connecting to Host LLM

The container uses `host.docker.internal` to reach the host machine:

| Platform | How it works |
|----------|--------------|
| **Linux** | Requires `--add-host=host.docker.internal:host-gateway` |
| **macOS** | Works automatically |
| **Windows** | Works automatically |

**Alternative: Use host IP directly:**
```bash
# Find your host IP
ip addr show docker0  # Linux
ifconfig en0          # macOS

# Use it in the container
docker run -it --rm \
  -e LLM_BASE_URL=http://192.168.1.100:11434/v1 \
  computor-agent
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

2. Check if the server allows external connections (Ollama does by default)

3. On Linux, ensure you're using `--add-host`:
   ```bash
   docker run -it --rm \
     --add-host=host.docker.internal:host-gateway \
     computor-agent
   ```

### "Model not found"

Make sure the model is pulled on the host:
```bash
ollama pull devstral-small
ollama list
```

### Network issues on Linux

If `host.docker.internal` doesn't work, use the Docker bridge IP:
```bash
# Find Docker bridge IP
docker network inspect bridge | grep Gateway

# Usually 172.17.0.1
docker run -it --rm \
  -e LLM_BASE_URL=http://172.17.0.1:11434/v1 \
  computor-agent
```
