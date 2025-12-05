# Local LLM Server Setup Guide

This guide explains how to set up local LLM servers to use with `computor-agent`.

## Overview

`computor-agent` supports multiple LLM backends via the OpenAI-compatible API format:

| Provider | Best For | Resource Usage |
|----------|----------|----------------|
| **Ollama** | Easy setup, CLI-first | Medium |
| **LM Studio** | GUI, easy model management | Medium |
| **vLLM** | Production, high throughput | High |

---

## Option 1: Ollama (Recommended for Development)

Ollama is the easiest way to run LLMs locally. It handles model downloads and serves an OpenAI-compatible API.

### Ubuntu/Linux

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start the service (runs automatically after install)
ollama serve

# Pull a model
ollama pull devstral-small
# or
ollama pull qwen2.5-coder:7b
# or
ollama pull llama3.1:8b

# Verify it's running
curl http://localhost:11434/v1/models
```

### macOS

```bash
# Install via Homebrew
brew install ollama

# Or download from https://ollama.com/download/mac

# Start Ollama (runs as menu bar app)
ollama serve

# Pull a model
ollama pull devstral-small
```

### Windows

1. Download installer from https://ollama.com/download/windows
2. Run the installer
3. Ollama starts automatically as a system service
4. Open PowerShell:
   ```powershell
   ollama pull devstral-small
   ```

### Using with computor-agent

```bash
# Default Ollama endpoint
computor-agent chat -p ollama -m devstral-small

# Or specify explicitly
computor-agent chat -u http://localhost:11434/v1 -m devstral-small
```

### Available Models for Ollama

```bash
# Code-focused models (recommended for tutor AI)
ollama pull devstral-small          # Mistral's code model
ollama pull qwen2.5-coder:7b        # Alibaba's code model
ollama pull codellama:13b           # Meta's code model
ollama pull deepseek-coder:6.7b     # DeepSeek code model

# General purpose
ollama pull llama3.1:8b             # Meta's latest
ollama pull mistral:7b              # Mistral 7B
ollama pull gemma2:9b               # Google's Gemma

# List installed models
ollama list
```

---

## Option 2: LM Studio (GUI-based)

LM Studio provides a graphical interface for managing and running models.

### All Platforms (Ubuntu, macOS, Windows)

1. Download from https://lmstudio.ai/
2. Install and launch LM Studio
3. Go to the **Discover** tab and download a model:
   - Search for "devstral" or "qwen2.5-coder"
   - Click download
4. Go to the **Local Server** tab (left sidebar)
5. Select your model and click **Start Server**
6. Server runs on `http://localhost:1234/v1`

### Using with computor-agent

```bash
# LM Studio is the default
computor-agent chat -m <model-name>

# Or specify explicitly
computor-agent chat -p lmstudio -u http://localhost:1234/v1 -m <model-name>
```

### Recommended Models in LM Studio

Search for these in the Discover tab:
- `TheBloke/Mistral-7B-Instruct-v0.2-GGUF`
- `TheBloke/CodeLlama-13B-Instruct-GGUF`
- `Qwen/Qwen2.5-Coder-7B-Instruct-GGUF`

---

## Option 3: vLLM (Production/High Performance)

vLLM offers high throughput and is ideal for production deployments.

### Ubuntu/Linux (requires NVIDIA GPU)

```bash
# Install vLLM
pip install vllm

# Run server with a model
python -m vllm.entrypoints.openai.api_server \
    --model mistralai/Devstral-Small-2505 \
    --port 8000

# Or with Docker
docker run --runtime nvidia --gpus all \
    -v ~/.cache/huggingface:/root/.cache/huggingface \
    -p 8000:8000 \
    vllm/vllm-openai:latest \
    --model mistralai/Devstral-Small-2505
```

### Using with computor-agent

```bash
computor-agent chat -u http://localhost:8000/v1 -m mistralai/Devstral-Small-2505
```

---

## Option 4: Text Generation Inference (TGI)

Hugging Face's inference server, good for production.

### Docker (All Platforms)

```bash
# Run with Docker (requires NVIDIA GPU)
docker run --gpus all --shm-size 1g \
    -p 8080:80 \
    -v ~/.cache/huggingface:/data \
    ghcr.io/huggingface/text-generation-inference:latest \
    --model-id mistralai/Devstral-Small-2505

# TGI uses a different API format, but has OpenAI compatibility
```

---

## Hardware Requirements

### Minimum Requirements

| Model Size | RAM Required | GPU VRAM |
|------------|--------------|----------|
| 7B params  | 8GB          | 6GB      |
| 13B params | 16GB         | 10GB     |
| 30B params | 32GB         | 24GB     |
| 70B+ params| 64GB+        | 48GB+    |

### Recommended Setup

- **Development**: 16GB RAM, any modern CPU (Ollama with 7B model)
- **Production**: 32GB+ RAM, NVIDIA GPU with 24GB+ VRAM

### Running on CPU Only

All tools support CPU inference (slower but works):

```bash
# Ollama automatically uses CPU if no GPU
ollama pull llama3.1:8b

# LM Studio: Select CPU in settings

# vLLM: Not recommended for CPU
```

---

## Troubleshooting

### Connection Refused

```
LLM Error: Failed to connect to http://localhost:1234/v1
```

**Solutions:**
1. Check if the server is running:
   ```bash
   # For Ollama
   curl http://localhost:11434/v1/models

   # For LM Studio
   curl http://localhost:1234/v1/models
   ```
2. Start the server if not running
3. Check if the port is correct

### Model Not Found

```
LLM Error: Model 'xyz' not found
```

**Solutions:**
1. List available models:
   ```bash
   # Ollama
   ollama list

   # LM Studio: Check Local Server tab

   # API
   curl http://localhost:11434/v1/models
   ```
2. Pull/download the model first

### Out of Memory

**Solutions:**
1. Use a smaller model (7B instead of 13B)
2. Use quantized models (Q4_K_M, Q5_K_M)
3. Close other applications
4. For Ollama, set memory limit:
   ```bash
   OLLAMA_MAX_LOADED_MODELS=1 ollama serve
   ```

### Slow Inference

**Solutions:**
1. Use GPU if available
2. Use smaller/quantized models
3. For Ollama on macOS, enable Metal:
   ```bash
   OLLAMA_METAL=1 ollama serve
   ```

---

## Quick Reference

### Default Endpoints

| Provider   | URL                           |
|------------|-------------------------------|
| Ollama     | `http://localhost:11434/v1`   |
| LM Studio  | `http://localhost:1234/v1`    |
| vLLM       | `http://localhost:8000/v1`    |
| OpenAI     | `https://api.openai.com/v1`   |

### computor-agent Commands

```bash
# Interactive chat
computor-agent chat -p ollama -m devstral-small

# Single question
computor-agent ask "What is Python?" -p ollama -m devstral-small

# List models from server
computor-agent models -p ollama

# Use streaming
computor-agent ask "Explain recursion" -p ollama -m llama3.1:8b --stream
```

---

## Next Steps

Once your LLM server is running:

1. Test the connection:
   ```bash
   computor-agent ask "Hello, world!" -p ollama -m devstral-small
   ```

2. Start an interactive session:
   ```bash
   computor-agent chat -p ollama -m devstral-small
   ```

3. Configure defaults in your environment:
   ```bash
   export LLM_PROVIDER=ollama
   export LLM_MODEL=devstral-small
   export LLM_BASE_URL=http://localhost:11434/v1
   ```
