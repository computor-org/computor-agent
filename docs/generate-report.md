# Generate Report

Generates a markdown report with comparison plots from [Scenario Runner](scenario-runner.md) results.

## Prerequisites

```bash
pip install -e ".[report]"
```

## Usage

```bash
# Generate report from a results directory (scans all run_* subdirectories)
python scripts/generate_report.py ./results/

# Generate from a single run directory
python scripts/generate_report.py ./results/run_2026-03-25T14-30-00_mistral-7b/

# Custom output directory
python scripts/generate_report.py ./results/ -o ./my-report/

# Verbose logging
python scripts/generate_report.py ./results/ -v
```

## Output

```
results/report/
├── report.md
└── media/
    ├── avg_time_per_model.png
    ├── total_time_per_model.png
    ├── success_rate.png
    ├── time_distribution.png
    ├── time_per_scenario.png
    ├── category_success.png
    ├── category_time.png
    ├── response_length.png
    ├── scores_per_model.png       # if evaluations.json present
    ├── scores_per_category.png    # if evaluations.json present
    └── score_distribution.png     # if evaluations.json present
```

## Plots

| Plot | Description |
|------|-------------|
| Average Response Time | Bar chart of mean response time per model |
| Total Run Time | Bar chart of wall-clock time per model |
| Success / Failure Rate | Stacked bar chart of success vs failure counts |
| Response Time Distribution | Box plot showing time spread per model |
| Time per Scenario | Grouped bars comparing scenario times across models |
| Success Rate by Category | Success rate per prompt category (help, injection, etc.) |
| Response Time by Category | Average time per prompt category |
| Response Length | Average character count of responses |

If `evaluations.json` files are present (from [evaluate_responses.py](evaluate-responses.md)):

| Plot | Description |
|------|-------------|
| Evaluation Scores per Model | Grouped bars of average score per metric |
| Scores by Category | Heatmap of overall score per model x category |
| Score Distribution | Box plot of overall scores per model |

Category breakdowns use the `<index>_<category>.md` naming convention from [generate_prompts.py](generate-prompts.md).

## Report Sections

The markdown report includes:

1. **Overview table** — model, prompt count, success rate, avg/total time
2. **Evaluation scores table** — average per-metric scores per model (if evaluations present)
3. **Plots** — all charts embedded via `![](media/...)`
3. **Per-scenario details** — breakdown table per scenario with a collapsible per-prompt detail view showing timing across models

## Workflow

```
extract_scenarios.py  -->  generate_prompts.py  -->  run_scenarios.py  -->  evaluate_responses.py  -->  generate_report.py
                                                     results/               results/                    results/report/
                                                     └── run_*_model/       └── run_*_model/            ├── report.md
                                                         └── summary.json       ├── summary.json        └── media/*.png
                                                                                └── evaluations.json
```

The evaluation step is optional — `generate_report.py` works with or without `evaluations.json`.

## CLI Options

| Flag | Description |
|------|-------------|
| `results_dir` | Results directory with `run_*` subdirs or a single run directory (required) |
| `--output`, `-o` | Output directory (default: `<results_dir>/report/`) |
| `--verbose`, `-v` | Enable debug logging |
