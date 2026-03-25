# Development Mode

Run the tutor agent locally without API calls for rapid iteration on prompts, scenarios, and LLM behavior.

## Quick Start

```bash
# Interactive mode — type messages, get AI responses
computor-agent tutor messaging --dev

# With a scenario (assignment context, student code, test results)
computor-agent tutor messaging --dev --scenario ./examples/scenarios/python-basics

# Single prompt — process one message and exit
computor-agent tutor messaging --dev --scenario ./examples/scenarios/python-basics \
  -p "I don't understand how to create the matrix M"
```

## Modes

### Interactive Mode

Starts a REPL where you type student messages and see the agent's responses in real time.

```
✓ Config loaded
✓ LLM ready (ollama/mistral:7b @ http://localhost:11434/v1)
✓ Prompts loaded (~/.computor/prompts)
✓ Scenario loaded: Python Basics 1 - NumPy Matrix Operations

You: How do I create the matrix M?

Processing message...
╭─ Response ──────────────────────────────────────────────╮
│ To create the matrix M, you need to use np.arange...    │
╰─────────────────────────────────────────────────────────╯
✓ Response sent

You: /show
```

Features:
- **Hot reload**: Edit `.md` prompt files in `~/.computor/prompts/` and changes are picked up instantly
- **Conversation threading**: Each message is automatically threaded as a follow-up to the previous one
- **Full agent pipeline**: Security checks, context building, and LLM calls all run as in production

### Single-Shot Mode (`--prompt`)

Process one message and exit. Useful for scripting and quick tests.

```bash
computor-agent tutor messaging --dev \
  --scenario ./examples/scenarios/python-basics \
  -p "What is np.where used for?"
```

No interactive loop, no hot reload, no info panel — just the response.

## Commands (Interactive Mode)

| Command | Description |
|---------|-------------|
| `/new` | Start a new conversation (breaks the thread chain) |
| `/show` | Show conversation history as a table |
| `/assignment` | Show loaded assignment details |
| `/reload` | Manually reload all prompt files |
| `/clear` | Clear all messages |
| `/exit` | Exit development mode |

## Context Sources

Dev mode simulates the full agent context. Data can come from several sources:

### Scenario (`--scenario`)

A directory with all context pre-defined. See [Scenario Runner](scenario-runner.md) for the full directory structure.

```bash
computor-agent tutor messaging --dev --scenario ./examples/scenarios/python-basics
```

Provides:
- Assignment description (`assignment/description.md`)
- Student submission code (`submission/` → served as ZIP via mock API)
- Reference solution (`reference/`)
- Test results (`test-results.json`)
- Student name from `scenario.yaml`

### Assignment Directory (`--assignment`)

Load just an assignment from a reference solution directory (legacy, predates scenarios):

```bash
computor-agent tutor messaging --dev --assignment /path/to/assignment
```

The directory must contain `meta.yaml` and a `content/` subdirectory with `index.md`.

### No Context

```bash
computor-agent tutor messaging --dev
```

Runs with no assignment context — the agent responds with general guidance.

## Configuration

Dev mode uses the same `config.yaml` as production. The LLM settings (provider, model, base_url) are read from it.

```yaml
llm:
  provider: ollama
  model: mistral:7b
  base_url: http://localhost:11434/v1
```

If no config file exists and `--dev` is used, defaults to `ollama/devstral-small` at `localhost:11434`.

Override the config path:

```bash
computor-agent tutor messaging --dev -c my-config.yaml --scenario ./examples/scenarios/python-basics
```

## Init Sequence

Dev mode initializes in order, with status output:

```
✓ Config loaded
  Checking LLM connectivity (ollama/mistral:7b)...
✓ LLM ready (ollama/mistral:7b @ http://localhost:11434/v1)
✓ Prompts loaded (~/.computor/prompts)
✓ Scenario loaded: Python Basics 1 - NumPy Matrix Operations
    Description: 628 chars
    Submission: solution.py
    Reference: solution.py
    Tests: 0/10 passed
```

If the LLM health check fails, dev mode exits with a helpful error message suggesting how to start the LLM server.

## CLI Options

| Flag | Description |
|------|-------------|
| `--dev` | Enable development mode (required) |
| `--config`, `-c` | Config file path (default: `config.yaml`) |
| `--scenario` | Path to scenario directory |
| `--assignment` | Path to assignment directory (legacy) |
| `--prompt`, `-p` | Single message to process and exit |
| `--prompts-dir` | Custom prompts directory (default: `~/.computor/prompts`) |
| `--verbose`, `-v` | Enable debug logging |
| `--log-file`, `-l` | Log to file |

## How It Differs From Production

| Aspect | Dev Mode | Production |
|--------|----------|------------|
| API calls | Mock client (no network) | Real computor-backend API |
| Messages | Local simulator | WebSocket + REST |
| Submissions | From scenario ZIP or none | Downloaded from MinIO via API |
| Authentication | None | API token |
| Typing indicator | Not sent | Sent via WebSocket |
| Hot reload | Enabled (interactive) | Not available |

## Creating Scenarios

See [Scenario Runner](scenario-runner.md) for the scenario directory structure.

To extract real scenarios from the database, use [Extract Scenarios](extract-scenarios.md).
