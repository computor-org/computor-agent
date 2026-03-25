# Scenario Runner

Batch-runs the tutor agent against pre-defined scenarios to evaluate LLM response quality across different models and prompts.

## Usage

```bash
# Run all scenarios with model from config.yaml
python scripts/run_scenarios.py ./examples/scenarios/

# Override model
python scripts/run_scenarios.py ./examples/scenarios/ --model mistral:7b

# Only run a specific scenario
python scripts/run_scenarios.py ./examples/scenarios/ -s python-basics

# Custom output directory
python scripts/run_scenarios.py ./examples/scenarios/ -o ./results/

# Verbose logging
python scripts/run_scenarios.py ./examples/scenarios/ -v
```

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
        ├── 001_help_with_matrix.md
        ├── 002_logical_indexing.md
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
# prompts/001_help_with_matrix.md
I don't understand how to create the matrix M. Can you help me?
```

## Output

Results are written to `results/run_<timestamp>_<model>/`:

```
results/
└── run_2026-03-25T14-30-00_mistral-7b/
    ├── summary.json
    └── python-basics/
        ├── 001_help_with_matrix_response.md
        ├── 002_logical_indexing_response.md
        └── 003_solution_request_error.log
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
          "file": "001_help_with_matrix.md",
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

- The LLM provider stays open across all scenarios and prompts to avoid model reload overhead
- Each scenario gets a fresh agent/simulator (clean conversation state)
- The agent processes each prompt with full context: assignment description, student code, test results
- Security checks run as normal — blocked prompts are logged

## CLI Options

| Flag | Description |
|------|-------------|
| `scenarios_dir` | Directory containing scenario subdirectories (required) |
| `--config`, `-c` | Config file path (default: `config.yaml`) |
| `--model`, `-m` | Override LLM model from config |
| `--output`, `-o` | Output directory (default: `<scenarios_dir>/../results/`) |
| `--scenario`, `-s` | Filter: only run scenarios matching this name |
| `--verbose`, `-v` | Enable debug logging |
