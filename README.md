# computor-agent

AI agents for the Computor system.

## Features

- **LLM Abstraction Layer**: Unified interface for multiple LLM providers
- **Multiple Providers**: Support for OpenAI, LM Studio, Ollama, and custom providers
- **Streaming Support**: Real-time response streaming
- **Highly Configurable**: Extensive configuration options via Pydantic models
- **Testing Support**: Dummy provider for testing without API calls
- **CLI Tool**: Interactive chat and single-query commands

## Installation

```bash
# From the repository root
pip install -e .

# With development dependencies
pip install -e ".[dev]"
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

For the Tutor AI Agent, we recommend these models based on your use case:

| Model | Size | RAM Needed | Best For |
|-------|------|------------|----------|
| `qwen2.5-coder:1.5b` | ~1GB | 4GB | Quick responses, basic code help |
| `qwen2.5-coder:7b` | ~4GB | 8GB | Good code understanding, detailed explanations |
| `llama3.1:8b` | ~5GB | 12GB | General tutoring, longer explanations |

Start with a smaller model to test, then upgrade if you need better quality responses.

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
