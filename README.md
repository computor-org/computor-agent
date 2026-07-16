# computor-agent

AI agents for the Computor system.

## Features

- **LLM Abstraction Layer**: Unified interface for multiple LLM providers
- **Multiple Providers**: Support for OpenAI, LM Studio, Ollama, and custom providers
- **Streaming Support**: Real-time response streaming
- **Highly Configurable**: Extensive configuration options via Pydantic models
- **Testing Support**: Dummy provider for testing without API calls
- **CLI Tool**: Interactive chat and single-query commands

## Running the tutor agent (Docker)

The production deployment needs only Docker, a config file, and the start
script:

```bash
./start.sh                  # first run creates config.yaml, then edit it
./start.sh --workers 8      # start the agent with 8 workers
./start.sh status           # container state + health snapshot
./start.sh logs             # follow logs
./start.sh down             # stop
```

The worker count is how many messages are processed concurrently. See
[docker/README.md](docker/README.md) for the full deployment guide
(environment overrides, health/restart semantics, troubleshooting).

## Development installation

```bash
# From the repository root
pip install -e .

# With development dependencies
pip install -e ".[dev]"

# Run the agent from the venv (instead of Docker)
computor-agent tutor messaging -c config.yaml --workers 4
```

## Quick Start

### As a Library

```python
from computor_agent import create_provider, LLMConfig, ProviderType

# Quick setup with defaults (LM Studio)
provider = create_provider(
    model="gpt-oss-120b",
    base_url="http://localhost:1234/v1",
)

# Complete response
response = await provider.complete("What is Python?")
print(response.content)

# Streaming response
async for chunk in provider.stream("Explain async/await"):
    print(chunk.content, end="", flush=True)

# Don't forget to close
await provider.close()
```

### With Full Configuration

```python
from computor_agent import LLMConfig, ProviderType, get_provider

config = LLMConfig(
    provider=ProviderType.OLLAMA,
    model="devstral-small",
    base_url="http://localhost:11434/v1",
    temperature=0.7,
    max_tokens=2000,
    system_prompt="You are a helpful coding tutor.",
)

async with get_provider(config) as provider:
    response = await provider.complete("How do I write a for loop?")
    print(response.content)
```

### CLI Usage

```bash
# Interactive chat (default: LM Studio with gpt-oss-120b)
computor-agent chat

# Chat with specific provider/model
computor-agent chat -p ollama -m devstral-small

# Single question
computor-agent ask "What is Python?"

# With streaming
computor-agent ask "Explain recursion" --stream

# List available models
computor-agent models

# List providers
computor-agent providers
```

## Supported Providers

| Provider | Type | Default URL |
|----------|------|-------------|
| LM Studio | Local | `http://localhost:1234/v1` |
| Ollama | Local | `http://localhost:11434/v1` |
| OpenAI | Cloud | `https://api.openai.com/v1` |
| Dummy | Testing | N/A |

All providers use the OpenAI-compatible API format.

## Setting Up Ollama (Linux)

Ollama is a lightweight tool for running LLMs locally. Here's how to get started:

### 1. Install Ollama

```bash
# One-line install script
curl -fsSL https://ollama.com/install.sh | sh
```

This installs Ollama and sets it up as a systemd service that starts automatically.

### 2. Verify Installation

```bash
# Check if Ollama is running
ollama --version

# Check the service status
systemctl status ollama
```

### 3. Pull a Model

Choose a model based on your hardware. Smaller models run faster and need less RAM:

```bash
# Small models (4-8GB RAM) - Fast, good for testing
ollama pull qwen2.5-coder:1.5b      # 1.5B params, ~1GB, coding focused
ollama pull llama3.2:1b              # 1B params, ~700MB, general purpose
ollama pull phi3:mini                # 3.8B params, ~2GB, good quality

# Medium models (8-16GB RAM) - Better quality
ollama pull qwen2.5-coder:7b         # 7B params, ~4GB, excellent for code
ollama pull llama3.2:3b              # 3B params, ~2GB, balanced
ollama pull mistral:7b               # 7B params, ~4GB, versatile

# Large models (16-32GB+ RAM) - Best quality
ollama pull llama3.1:8b              # 8B params, ~5GB
ollama pull codellama:13b            # 13B params, ~8GB, code specialist
```

### 4. Test the Model

```bash
# Interactive chat
ollama run qwen2.5-coder:1.5b

# Or via API
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:1.5b",
  "prompt": "Write a hello world in Python",
  "stream": false
}'
```

### 5. Use with Computor Agent

```bash
# Interactive chat with Ollama
computor-agent chat -p ollama -m qwen2.5-coder:1.5b

# Single question
computor-agent ask "Explain Python lists" -p ollama -m qwen2.5-coder:1.5b
```

Or in your configuration file (`config.yaml`):

```yaml
llm:
  provider: ollama
  model: qwen2.5-coder:1.5b
  base_url: http://localhost:11434/v1
  temperature: 0.7
```

### Ollama Commands Reference

```bash
# List downloaded models
ollama list

# Show model info
ollama show qwen2.5-coder:1.5b

# Remove a model
ollama rm qwen2.5-coder:1.5b

# Pull/update a model
ollama pull qwen2.5-coder:1.5b

# Run interactively
ollama run qwen2.5-coder:1.5b

# Start/stop the service
sudo systemctl start ollama
sudo systemctl stop ollama

# View logs
journalctl -u ollama -f
```

### Recommended Models for Tutoring

The minimum recommended model for the Tutor AI Agent is `mistral:7b` (~4.4GB). Larger models generally produce better pedagogical guidance but require more resources. A formal benchmark of multiple models is ongoing — final recommendations will be updated once results are available.

| Model | Size | RAM Needed | Notes |
|-------|------|------------|-------|
| `mistral:7b` | ~4.4GB | 8GB | Minimum recommended; decent tutoring quality |
| `qwen3.5:35b-a3b` | ~23GB | 16GB | MoE (3B active); good quality/speed trade-off |
| `qwen3.5:122b-a10b` | ~81GB | 48GB | MoE (10B active); strong tutoring quality |

## Tutor AI Agent

The Tutor AI Agent is an autonomous agent that monitors student messages and submissions, responding automatically using an LLM. It has two modes: **messaging** (help conversations) and **grading** (submission review).

### Commands

```bash
# Messaging agent - responds to student questions
computor-agent tutor messaging
computor-agent tutor messaging -c config.yaml -v
computor-agent tutor messaging --dry-run

# Grading agent - grades student submissions
computor-agent tutor grading --dev --reference ./assignment --student ./submission

# Development mode - interactive testing without API calls
computor-agent tutor messaging --dev
computor-agent tutor messaging --dev --assignment ./my-assignment
```

### CLI Reference

#### `computor-agent tutor messaging`

Responds to student messages tagged with `#ai::request`.

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Config file (default: `config.yaml`) |
| `-v, --verbose` | Enable verbose logging |
| `--dry-run` | Log actions without sending responses |
| `--dev` | Development mode (interactive shell, no API calls) |
| `--prompts-dir PATH` | Custom prompts directory |
| `--assignment PATH` | [Dev mode] Assignment directory with `meta.yaml` |

#### `computor-agent tutor grading`

Reviews and grades student submissions.

| Option | Description |
|--------|-------------|
| `-c, --config PATH` | Config file (default: `config.yaml`) |
| `-v, --verbose` | Enable verbose logging |
| `--dev` | Development mode (local files only) |
| `--prompts-dir PATH` | Custom prompts directory |
| `--reference PATH` | [Dev mode] Reference solution directory |
| `--student PATH` | [Dev mode] Student submission directory |
| `-l, --language` | Language for assignment (e.g., `en`, `de`) |

### Configuration

All settings are in a single `config.yaml` file:

```yaml
# Backend API connection
backend:
  url: https://api.computor.example.com
  api_token: ctp_your_api_token_here  # or use username/password

# LLM provider settings
llm:
  provider: ollama
  model: qwen2.5-coder:7b
  base_url: http://localhost:11434/v1

# Git credentials for accessing repositories
credentials:
  - pattern: https://gitlab.example.com
    token: glpat-your-token

# Tutor agent behavior
tutor:
  personality:
    name: "Tutor AI"
    tone: "friendly_professional"

  triggers:
    request_tags:
      - scope: "ai"
        value: "request"
```

### How It Works

**Messaging Mode:**
1. Student creates message with `#ai::request` tag
2. Agent detects tag and classifies intent (question, debug, review, etc.)
3. Agent generates response using LLM
4. Student can reply without tag for follow-ups

**Grading Mode (Dev):**
1. Point to reference solution and student submission directories
2. Agent compares code against requirements in `meta.yaml`
3. Agent generates grade and feedback

See [docs/tutor-agent.md](docs/tutor-agent.md) for detailed documentation.

## Configuration

### Environment Variables

```bash
# API key (for OpenAI or authenticated endpoints)
export OPENAI_API_KEY=sk-...
# or
export LLM_API_KEY=your-key
```

### LLMConfig Options

```python
LLMConfig(
    # Provider settings
    provider=ProviderType.LMSTUDIO,  # lmstudio, ollama, openai, dummy
    model="gpt-oss-120b",            # Model identifier
    base_url="http://localhost:1234/v1",
    api_key=None,                    # Optional API key

    # Generation parameters
    temperature=0.7,                 # 0.0-2.0
    max_tokens=None,                 # Max tokens to generate
    top_p=None,                      # Nucleus sampling
    frequency_penalty=None,          # Repetition penalty
    presence_penalty=None,           # Topic penalty
    stop_sequences=None,             # Stop strings
    seed=None,                       # For reproducibility

    # Request settings
    timeout=120.0,                   # Request timeout (seconds)
    max_retries=3,                   # Retry attempts

    # System prompt
    system_prompt=None,              # Default system prompt
)
```

## Testing with DummyProvider

```python
from computor_agent import DummyProvider, DummyProviderConfig, LLMConfig, ProviderType

config = LLMConfig(provider=ProviderType.DUMMY)
dummy_config = DummyProviderConfig(
    response_text="This is a test response",
    stream_chunks=["Hello ", "World!"],
    delay_seconds=0.1,  # Simulate latency
)

provider = DummyProvider(config, dummy_config)

# Test complete
response = await provider.complete("Any prompt")
assert response.content == "This is a test response"

# Test streaming
chunks = []
async for chunk in provider.stream("Any prompt"):
    chunks.append(chunk.content)
assert "".join(chunks) == "Hello World!"

# Test error handling
provider.set_should_fail(True, "Simulated error")
# Now all calls will raise LLMError
```

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=computor_agent
```

## License

MIT
