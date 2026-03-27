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
    ├── prompt_count_by_category.png
    ├── avg_time_per_model.png
    ├── total_time_per_model.png
    ├── success_rate.png
    ├── time_distribution.png
    ├── time_by_category_box.png
    ├── category_time.png
    ├── category_success.png
    ├── response_length.png
    ├── length_by_category.png
    ├── time_per_scenario.png
    ├── scores_per_model.png         # if evaluations.json present
    ├── metric_heatmap.png           #
    ├── radar_chart.png              #
    ├── metric_boxplots.png          #
    ├── scores_per_category.png      #
    ├── category_score_comparison.png #
    ├── score_distribution.png       #
    ├── time_vs_quality.png          #
    ├── length_vs_quality.png        #
    ├── boundary_vs_helpfulness.png  #
    └── text_style.png               #
```

## Plots

### Performance plots (always generated)

| Plot | Type | Description |
|------|------|-------------|
| Dataset: Prompts by Category | Bar | Number of prompts per intent category |
| Average Response Time | Bar | Mean response time per model |
| Total Run Time | Bar | Wall-clock time per model |
| Success / Failure Rate | Stacked bar | Success vs failure counts per model |
| Response Time Distribution | Box | Time spread per model |
| Response Time by Category | Box | Time distribution per intent category |
| Avg Response Time by Category | Grouped bar | Average time per category across models |
| Success Rate by Category | Grouped bar | Success rate per category across models |
| Response Length | Bar | Average character count per model |
| Response Length by Category | Box | Length distribution per intent category |
| Time per Scenario | Grouped bar | Per-scenario timing across models |

### Evaluation plots (when `evaluations.json` present)

| Plot | Type | Description |
|------|------|-------------|
| Scores per Model | Grouped bar | Per-metric averages with error bars (when `repeats > 1`) |
| Score Matrix | Heatmap | Full model x metric score matrix at a glance |
| Model Metric Profiles | Radar/spider | Each model's strengths and weaknesses across all metrics |
| Per-Metric Score Distribution | Box (subplots) | Score consistency per metric per model |
| Scores by Prompt Category | Heatmap | Overall score per model x prompt category |
| Category Score Comparison | Grouped bar | Quality per intent type across models |
| Overall Score Distribution | Box | Score spread per model |
| Response Time vs Quality | Scatter | Are slower models better? Each point is one model |
| Response Length vs Quality | Scatter | Do more verbose models score higher? |
| Safety vs Helpfulness | Scatter | Boundary adherence (adversarial) vs helpfulness (legitimate) |
| Response Style | Grouped bar | Questions asked, code blocks, sentence length per model |

When evaluations used `--repeats N`, the report automatically detects this and:
- Displays the number of repeats in the evaluation scores table header
- Adds min/max error bars to the scores-per-model chart
- Uses all individual repeat scores (not just per-prompt means) for the score distribution box plot

Category breakdowns use the `<index>_<category>.md` naming convention from [generate_prompts.py](generate-prompts.md).

## Report Sections

The markdown report includes:

1. **Overview table** — model, prompt count, success rate, avg/total time
2. **Per-category statistics table** — prompts, success rate, avg/median time, avg length per category
3. **Evaluation scores table** — average per-metric scores per model, with evaluator model and repeat count (if evaluations present)
4. **Plots** — all charts embedded via `![](media/...)`
5. **Per-scenario details** — breakdown table per scenario with a collapsible per-prompt detail view showing timing and scores across models

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
