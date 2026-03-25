# Scenario Runner

Batch-runs the tutor agent against pre-defined scenarios to evaluate LLM response quality across different models and prompts.

## Usage

```bash
# Run from a config file (recommended)
python scripts/run_scenarios.py scenarios.yaml

# Or pass a scenarios directory directly
python scripts/run_scenarios.py ./examples/scenarios/

# Override model
python scripts/run_scenarios.py ./examples/scenarios/ --model mistral:7b

# Multiple models (comma-separated)
python scripts/run_scenarios.py ./examples/scenarios/ -m 'mistral:7b,qwen2.5-coder:7b,llama3.1:8b'

# Only run a specific scenario
python scripts/run_scenarios.py ./examples/scenarios/ -s python-basics

# Custom output directory
python scripts/run_scenarios.py ./examples/scenarios/ -o ./results/

# Verbose logging
python scripts/run_scenarios.py ./examples/scenarios/ -v
```

## Configuration File

Instead of passing models and options via CLI, use a config file:

```yaml
# scenarios.yaml
models:
  - mistral:7b
  - qwen2.5-coder:7b
  - llama3.1:8b

scenarios_dir: ./examples/scenarios/
# output: ./results/
# scenario_filter: python-basics
# config: config.yaml
```

```bash
python scripts/run_scenarios.py scenarios.yaml
```

The target is auto-detected: `.yaml`/`.yml` files are loaded as run configs, directories are used as scenarios directories directly. CLI arguments always take precedence over the config file. See [examples/scenarios.example.yaml](../examples/scenarios.example.yaml) for a full template.

## Scenario Directory Structure

Each scenario is a subdirectory containing:

```
scenarios/
└── python-basics/
    ├── scenario.yaml              # Student info, assignment metadata
    ├── assignment/
    │   └── description.md         # Assignment description (README)
    ├── submission/                 # Student's current code (optional)
    │   └── solution.py
    ├── reference/                  # Reference solution (optional)
    │   └── solution.py
    ├── test-results.json           # Test output (optional)
    └── prompts/                    # One .md file per prompt to test
        ├── 001_help.md             # Named <index>_<category>.md
        ├── 002_help.md
        └── 003_solution_request.md
```

### scenario.yaml

```yaml
student:
  name: "Max Mustermann"

assignment:
  title: "Python Basics 1 - NumPy Matrix Operations"
  language: "en"
```

### Prompt Files

Each `.md` file in `prompts/` contains a single student message. The file content is the message body — no frontmatter needed.

```
# prompts/001_help.md
I don't understand how to create the matrix M. Can you help me?
```

## Output

Results are written to `results/run_<timestamp>_<model>/` — one directory per model:

```
results/
├── run_2026-03-25T14-30-00_mistral-7b/
│   ├── summary.json
│   └── python-basics/
│       ├── 001_help_response.md
│       ├── 002_help_response.md
│       └── 003_solution_request_error.log
└── run_2026-03-25T14-30-00_qwen2.5-coder-7b/
    ├── summary.json
    └── python-basics/
        └── ...
```

### summary.json

```json
{
  "model": "mistral:7b",
  "provider": "ollama",
  "timestamp": "2026-03-25T14-30-00",
  "total_scenarios": 1,
  "total_prompts": 3,
  "total_successes": 2,
  "total_failures": 1,
  "total_time_s": 45.2,
  "avg_processing_time_ms": 12300,
  "scenarios": [
    {
      "name": "python-basics",
      "assignment": "Python Basics 1",
      "total_time_s": 45.2,
      "prompts": [
        {
          "file": "001_help.md",
          "success": true,
          "processing_time_ms": 11200,
          "response_chars": 450,
          "blocked": false,
          "error": null
        }
      ]
    }
  ]
}
```

## How It Works

- Each model runs **all scenarios** before the next model starts — this keeps the model loaded in memory and avoids repeated cold-start overhead
- Before timing begins for each model, a **warmup prompt** is sent to force model loading into memory so the first real prompt isn't penalized
- The LLM provider stays open across all scenarios and prompts for a given model
- Each scenario gets a fresh agent/simulator (clean conversation state)
- The agent processes each prompt with full context: assignment description, student code, test results
- Security checks run as normal — blocked prompts are logged

## CLI Options

| Flag | Description |
|------|-------------|
| `target` | Config file (`.yaml`) or scenarios directory (required) |
| `--config`, `-c` | Config file path (default: `config.yaml`) |
| `--model`, `-m` | Override LLM model(s). Comma-separated for multiple: `-m 'a:7b,b:7b'` |
| `--output`, `-o` | Output directory (default: `<scenarios_dir>/../results/`) |
| `--scenario`, `-s` | Filter: only run scenarios matching this name |
| `--verbose`, `-v` | Enable debug logging |
