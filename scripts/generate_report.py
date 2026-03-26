#!/usr/bin/env python3
"""
Generate a markdown report with comparison plots from scenario runner results.

Reads summary.json files from one or more run directories and produces a
report with model comparisons, timing statistics, success rates, and
per-category breakdowns.

Usage:
    python scripts/generate_report.py ./results/
    python scripts/generate_report.py ./results/ -o ./report/
    python scripts/generate_report.py ./results/run_2026-03-25T14-30-00_mistral-7b/
    python scripts/generate_report.py ./results/ -v
"""

import argparse
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

COLORS = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
]

def setup_style():
    """Configure matplotlib for clean report plots."""
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.alpha": 0.3,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "font.size": 11,
        "figure.dpi": 150,
    })


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_summaries(results_dir: Path) -> list[dict]:
    """Find and load all summary.json + evaluations.json files under results_dir."""
    summaries = []

    def _load_run(run_path: Path) -> dict:
        data = json.loads((run_path / "summary.json").read_text(encoding="utf-8"))
        data["_run_dir"] = str(run_path)
        eval_path = run_path / "evaluations.json"
        if eval_path.exists():
            data["_evaluations"] = json.loads(eval_path.read_text(encoding="utf-8"))
        return data

    # If pointed directly at a run directory
    if (results_dir / "summary.json").exists():
        summaries.append(_load_run(results_dir))
        return summaries

    # Otherwise scan subdirectories
    for child in sorted(results_dir.iterdir()):
        if child.is_dir() and (child / "summary.json").exists():
            summaries.append(_load_run(child))

    return summaries


def extract_category(filename: str) -> str:
    """Extract category from prompt filename like '004_debug.md' -> 'debug'."""
    stem = Path(filename).stem
    match = re.match(r"\d+_(.*)", stem)
    if match:
        return match.group(1)
    return "unknown"


# ---------------------------------------------------------------------------
# Evaluation data helpers
# ---------------------------------------------------------------------------

def has_evaluations(summaries: list[dict]) -> bool:
    """Check if any summaries have evaluation data."""
    return any("_evaluations" in s for s in summaries)


def get_eval_metrics(summaries: list[dict]) -> list[str]:
    """Get the list of metric names from evaluation data."""
    for s in summaries:
        evals = s.get("_evaluations", {})
        for m in evals.get("metrics", []):
            pass
        metrics = evals.get("metrics", [])
        if metrics:
            return [m["name"] for m in metrics]
    return []


def get_prompt_scores(summary: dict) -> list[dict]:
    """Extract flat list of {file, category, scores...} from evaluations."""
    evals = summary.get("_evaluations", {})
    results = []
    for sc in evals.get("scenarios", []):
        for p in sc.get("prompts", []):
            if p.get("evaluated"):
                entry = {
                    "file": p["file"],
                    "category": p.get("category", extract_category(p["file"])),
                    "scenario": sc["name"],
                }
                entry.update(p.get("scores", {}))
                results.append(entry)
    return results


def get_prompt_score_details(summary: dict) -> list[dict]:
    """Extract detailed per-prompt data including all_scores and score_stats."""
    evals = summary.get("_evaluations", {})
    results = []
    for sc in evals.get("scenarios", []):
        for p in sc.get("prompts", []):
            if p.get("evaluated"):
                entry = {
                    "file": p["file"],
                    "category": p.get("category", extract_category(p["file"])),
                    "scenario": sc["name"],
                    "scores": p.get("scores", {}),
                    "score_stats": p.get("score_stats", {}),
                    "all_scores": p.get("all_scores", []),
                    "repeats": p.get("repeats", 1),
                    "repeats_succeeded": p.get("repeats_succeeded", 1),
                }
                results.append(entry)
    return results


def get_eval_repeats(summaries: list[dict]) -> int:
    """Get the number of evaluation repeats (from the first summary that has it)."""
    for s in summaries:
        evals = s.get("_evaluations", {})
        r = evals.get("repeats", 1)
        if r > 1:
            return r
    return 1


# ---------------------------------------------------------------------------
# Plot generators
# ---------------------------------------------------------------------------

def plot_avg_time_per_model(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: average processing time per model."""
    models = [s["model"] for s in summaries]
    times = [s["avg_processing_time_ms"] / 1000 for s in summaries]

    fig, ax = plt.subplots(figsize=(max(8, len(models) * 1.5), 5))
    bars = ax.bar(range(len(models)), times, color=COLORS[:len(models)])
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, rotation=30, ha="right")
    ax.set_ylabel("Avg response time (s)")
    ax.set_title("Average Response Time per Model")

    for bar, t in zip(bars, times):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.1,
                f"{t:.1f}s", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    path = out_dir / "avg_time_per_model.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_total_time_per_model(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: total run time per model."""
    models = [s["model"] for s in summaries]
    times = [s["total_time_s"] for s in summaries]

    fig, ax = plt.subplots(figsize=(max(8, len(models) * 1.5), 5))
    bars = ax.bar(range(len(models)), times, color=COLORS[:len(models)])
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, rotation=30, ha="right")
    ax.set_ylabel("Total time (s)")
    ax.set_title("Total Run Time per Model")

    for bar, t in zip(bars, times):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.2,
                f"{t:.1f}s", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    path = out_dir / "total_time_per_model.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_success_rate(summaries: list[dict], out_dir: Path) -> str:
    """Stacked bar chart: success vs failure count per model."""
    models = [s["model"] for s in summaries]
    successes = [s["total_successes"] for s in summaries]
    failures = [s["total_failures"] for s in summaries]

    fig, ax = plt.subplots(figsize=(max(8, len(models) * 1.5), 5))
    x = range(len(models))
    ax.bar(x, successes, label="Success", color="#55A868")
    ax.bar(x, failures, bottom=successes, label="Failure", color="#C44E52")
    ax.set_xticks(x)
    ax.set_xticklabels(models, rotation=30, ha="right")
    ax.set_ylabel("Prompts")
    ax.set_title("Success / Failure per Model")
    ax.legend()

    for i, (s, f) in enumerate(zip(successes, failures)):
        total = s + f
        if total > 0:
            pct = s / total * 100
            ax.text(i, total + 0.2, f"{pct:.0f}%", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    path = out_dir / "success_rate.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_time_per_scenario(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: time per scenario across models."""
    # Collect all scenario names
    all_scenarios = []
    for s in summaries:
        for sc in s["scenarios"]:
            if sc["name"] not in all_scenarios:
                all_scenarios.append(sc["name"])

    if not all_scenarios:
        return None

    models = [s["model"] for s in summaries]
    n_models = len(models)
    n_scenarios = len(all_scenarios)

    # Build time matrix
    times = {}
    for s in summaries:
        scenario_map = {sc["name"]: sc["total_time_s"] for sc in s["scenarios"]}
        times[s["model"]] = [scenario_map.get(name, 0) for name in all_scenarios]

    fig, ax = plt.subplots(figsize=(max(10, n_scenarios * 2), 5))
    bar_width = 0.8 / n_models
    x = np.arange(n_scenarios)

    for i, model in enumerate(models):
        offset = (i - n_models / 2 + 0.5) * bar_width
        ax.bar(x + offset, times[model], bar_width,
               label=model, color=COLORS[i % len(COLORS)])

    ax.set_xticks(x)
    ax.set_xticklabels(all_scenarios, rotation=30, ha="right")
    ax.set_ylabel("Time (s)")
    ax.set_title("Time per Scenario by Model")
    ax.legend()

    fig.tight_layout()
    path = out_dir / "time_per_scenario.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_time_distribution(summaries: list[dict], out_dir: Path) -> str:
    """Box plot: response time distribution per model."""
    models = []
    all_times = []
    for s in summaries:
        prompt_times = []
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                if p["success"]:
                    prompt_times.append(p["processing_time_ms"] / 1000)
        if prompt_times:
            models.append(s["model"])
            all_times.append(prompt_times)

    if not models:
        return None

    fig, ax = plt.subplots(figsize=(max(8, len(models) * 1.5), 5))
    bp = ax.boxplot(all_times, labels=models, patch_artist=True)

    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(COLORS[i % len(COLORS)])
        patch.set_alpha(0.7)

    ax.set_ylabel("Response time (s)")
    ax.set_title("Response Time Distribution per Model")
    if len(models) > 3:
        ax.tick_params(axis="x", rotation=30)

    fig.tight_layout()
    path = out_dir / "time_distribution.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_category_success(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: success rate per prompt category across models."""
    # Collect category stats
    models = [s["model"] for s in summaries]
    cat_stats = {}  # model -> category -> (successes, total)
    all_categories = set()

    for s in summaries:
        model = s["model"]
        cat_stats[model] = defaultdict(lambda: [0, 0])
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                cat = extract_category(p["file"])
                all_categories.add(cat)
                cat_stats[model][cat][1] += 1
                if p["success"]:
                    cat_stats[model][cat][0] += 1

    all_categories = sorted(all_categories)
    if not all_categories or len(all_categories) <= 1:
        return None

    n_models = len(models)
    n_cats = len(all_categories)

    fig, ax = plt.subplots(figsize=(max(10, n_cats * 2), 5))
    bar_width = 0.8 / n_models
    x = np.arange(n_cats)

    for i, model in enumerate(models):
        rates = []
        for cat in all_categories:
            s, t = cat_stats[model].get(cat, [0, 0])
            rates.append((s / t * 100) if t > 0 else 0)
        offset = (i - n_models / 2 + 0.5) * bar_width
        ax.bar(x + offset, rates, bar_width,
               label=model, color=COLORS[i % len(COLORS)])

    ax.set_xticks(x)
    ax.set_xticklabels(all_categories, rotation=30, ha="right")
    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 110)
    ax.set_title("Success Rate per Category by Model")
    ax.legend()

    fig.tight_layout()
    path = out_dir / "category_success.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_category_time(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: average response time per category across models."""
    models = [s["model"] for s in summaries]
    cat_times = {}  # model -> category -> list of times
    all_categories = set()

    for s in summaries:
        model = s["model"]
        cat_times[model] = defaultdict(list)
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                if p["success"]:
                    cat = extract_category(p["file"])
                    all_categories.add(cat)
                    cat_times[model][cat].append(p["processing_time_ms"] / 1000)

    all_categories = sorted(all_categories)
    if not all_categories or len(all_categories) <= 1:
        return None

    n_models = len(models)
    n_cats = len(all_categories)

    fig, ax = plt.subplots(figsize=(max(10, n_cats * 2), 5))
    bar_width = 0.8 / n_models
    x = np.arange(n_cats)

    for i, model in enumerate(models):
        avgs = []
        for cat in all_categories:
            times = cat_times[model].get(cat, [])
            avgs.append(sum(times) / len(times) if times else 0)
        offset = (i - n_models / 2 + 0.5) * bar_width
        ax.bar(x + offset, avgs, bar_width,
               label=model, color=COLORS[i % len(COLORS)])

    ax.set_xticks(x)
    ax.set_xticklabels(all_categories, rotation=30, ha="right")
    ax.set_ylabel("Avg response time (s)")
    ax.set_title("Average Response Time per Category by Model")
    ax.legend()

    fig.tight_layout()
    path = out_dir / "category_time.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_response_length(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: average response length (chars) per model."""
    models = []
    avg_chars = []

    for s in summaries:
        chars = [p["response_chars"] for sc in s["scenarios"]
                 for p in sc["prompts"] if p["success"] and p["response_chars"] > 0]
        if chars:
            models.append(s["model"])
            avg_chars.append(sum(chars) / len(chars))

    if not models:
        return None

    fig, ax = plt.subplots(figsize=(max(8, len(models) * 1.5), 5))
    bars = ax.bar(range(len(models)), avg_chars, color=COLORS[:len(models)])
    ax.set_xticks(range(len(models)))
    ax.set_xticklabels(models, rotation=30, ha="right")
    ax.set_ylabel("Avg response length (chars)")
    ax.set_title("Average Response Length per Model")

    for bar, c in zip(bars, avg_chars):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                f"{c:.0f}", ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    path = out_dir / "response_length.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


# ---------------------------------------------------------------------------
# Evaluation plot generators
# ---------------------------------------------------------------------------

def plot_scores_per_model(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: average score per metric per model, with min/max error bars when repeats > 1."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    has_repeats = get_eval_repeats(summaries) > 1
    models = []
    model_avgs = []
    model_mins = []
    model_maxs = []

    for s in summaries:
        details = get_prompt_score_details(s)
        if not details:
            continue
        models.append(s["model"])
        avgs, mins, maxs = [], [], []
        for m in metric_names:
            vals = [d["scores"].get(m) for d in details if d["scores"].get(m) is not None]
            avgs.append(sum(vals) / len(vals) if vals else 0)
            if has_repeats:
                # Aggregate min/max across all prompts from score_stats
                m_mins = [d["score_stats"].get(m, {}).get("min")
                          for d in details if d["score_stats"].get(m, {}).get("min") is not None]
                m_maxs = [d["score_stats"].get(m, {}).get("max")
                          for d in details if d["score_stats"].get(m, {}).get("max") is not None]
                mins.append(sum(m_mins) / len(m_mins) if m_mins else avgs[-1])
                maxs.append(sum(m_maxs) / len(m_maxs) if m_maxs else avgs[-1])
        model_avgs.append(avgs)
        if has_repeats:
            model_mins.append(mins)
            model_maxs.append(maxs)

    if not models:
        return None

    n_metrics = len(metric_names)
    n_models = len(models)

    fig, ax = plt.subplots(figsize=(max(10, n_metrics * 1.5), 5))
    bar_width = 0.8 / n_models
    x = np.arange(n_metrics)

    for i, model in enumerate(models):
        avgs = model_avgs[i]
        offset = (i - n_models / 2 + 0.5) * bar_width
        if has_repeats:
            yerr_lo = [a - mn for a, mn in zip(avgs, model_mins[i])]
            yerr_hi = [mx - a for a, mx in zip(avgs, model_maxs[i])]
            bars = ax.bar(x + offset, avgs, bar_width,
                          label=model, color=COLORS[i % len(COLORS)],
                          yerr=[yerr_lo, yerr_hi], capsize=3,
                          error_kw={"elinewidth": 1, "capthick": 1})
        else:
            bars = ax.bar(x + offset, avgs, bar_width,
                          label=model, color=COLORS[i % len(COLORS)])
        for bar, val in zip(bars, avgs):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(metric_names, rotation=30, ha="right")
    ax.set_ylabel("Score")
    ax.set_ylim(0, 5.5)
    title = "Average Evaluation Scores per Model"
    if has_repeats:
        title += f" (error bars: avg min/max across {get_eval_repeats(summaries)} repeats)"
    ax.set_title(title)
    ax.legend()

    fig.tight_layout()
    path = out_dir / "scores_per_model.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_scores_per_category(summaries: list[dict], out_dir: Path) -> str:
    """Heatmap: average overall score per model x category."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    models = []
    all_categories = set()
    model_cat_scores = {}

    for s in summaries:
        scores = get_prompt_scores(s)
        if not scores:
            continue
        model = s["model"]
        models.append(model)
        cat_scores = defaultdict(list)
        for sc in scores:
            cat = sc["category"]
            all_categories.add(cat)
            vals = [sc[m] for m in metric_names if sc.get(m) is not None]
            if vals:
                cat_scores[cat].append(sum(vals) / len(vals))
        model_cat_scores[model] = cat_scores

    all_categories = sorted(all_categories)
    if not models or not all_categories:
        return None

    # Build matrix
    matrix = []
    for model in models:
        row = []
        for cat in all_categories:
            vals = model_cat_scores[model].get(cat, [])
            row.append(sum(vals) / len(vals) if vals else 0)
        matrix.append(row)

    matrix = np.array(matrix)

    fig, ax = plt.subplots(figsize=(max(8, len(all_categories) * 1.5),
                                     max(4, len(models) * 0.8 + 2)))
    im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=5)

    ax.set_xticks(range(len(all_categories)))
    ax.set_xticklabels(all_categories, rotation=30, ha="right")
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models)
    ax.set_title("Average Score per Model and Category")

    # Annotate cells
    for i in range(len(models)):
        for j in range(len(all_categories)):
            val = matrix[i, j]
            color = "white" if val < 2.5 else "black"
            ax.text(j, i, f"{val:.1f}", ha="center", va="center",
                    fontsize=11, fontweight="bold", color=color)

    fig.colorbar(im, ax=ax, label="Score (0-5)")
    fig.tight_layout()
    path = out_dir / "scores_per_category.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_score_distribution(summaries: list[dict], out_dir: Path) -> str:
    """Box plot: distribution of overall scores per model.

    When repeats > 1, uses individual repeat scores for richer data points
    instead of just per-prompt mean scores.
    """
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    has_repeats = get_eval_repeats(summaries) > 1
    models = []
    all_scores = []

    for s in summaries:
        details = get_prompt_score_details(s)
        if not details:
            continue
        model_scores = []
        if has_repeats:
            # Use individual repeat scores for more data points
            for d in details:
                for repeat_scores in d.get("all_scores", []):
                    vals = [repeat_scores.get(m) for m in metric_names
                            if repeat_scores.get(m) is not None]
                    if vals:
                        model_scores.append(sum(vals) / len(vals))
        if not model_scores:
            # Fallback to mean scores (no repeats or no all_scores data)
            scores = get_prompt_scores(s)
            for sc in scores:
                vals = [sc[m] for m in metric_names if sc.get(m) is not None]
                if vals:
                    model_scores.append(sum(vals) / len(vals))
        if model_scores:
            models.append(s["model"])
            all_scores.append(model_scores)

    if not models:
        return None

    fig, ax = plt.subplots(figsize=(max(8, len(models) * 1.5), 5))
    bp = ax.boxplot(all_scores, labels=models, patch_artist=True)

    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(COLORS[i % len(COLORS)])
        patch.set_alpha(0.7)

    ax.set_ylabel("Overall score (avg across metrics)")
    ax.set_ylim(0, 5.5)
    title = "Score Distribution per Model"
    if has_repeats:
        title += f" (from {get_eval_repeats(summaries)} repeats per response)"
    ax.set_title(title)
    if len(models) > 3:
        ax.tick_params(axis="x", rotation=30)

    fig.tight_layout()
    path = out_dir / "score_distribution.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

def generate_report(summaries: list[dict], output_dir: Path, media_dir: Path) -> Path:
    """Generate the full markdown report."""
    plots = []
    has_evals = has_evaluations(summaries)

    # Generate all plots
    plot_funcs = [
        ("avg_time", plot_avg_time_per_model),
        ("total_time", plot_total_time_per_model),
        ("success", plot_success_rate),
        ("time_dist", plot_time_distribution),
        ("scenario_time", plot_time_per_scenario),
        ("cat_success", plot_category_success),
        ("cat_time", plot_category_time),
        ("resp_length", plot_response_length),
    ]

    if has_evals:
        plot_funcs.extend([
            ("scores_model", plot_scores_per_model),
            ("scores_category", plot_scores_per_category),
            ("scores_dist", plot_score_distribution),
        ])

    for name, func in plot_funcs:
        try:
            result = func(summaries, media_dir)
            if result:
                plots.append((name, result))
        except Exception as e:
            logger.warning(f"Failed to generate plot '{name}': {e}")

    # Build markdown
    lines = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    models = [s["model"] for s in summaries]

    lines.append("# Scenario Runner Report")
    lines.append("")
    lines.append(f"Generated: {timestamp}")
    lines.append("")
    lines.append(f"Models: {', '.join(f'`{m}`' for m in models)}")
    lines.append("")

    # --- Overview table ---
    lines.append("## Overview")
    lines.append("")
    lines.append("| Model | Prompts | Success | Failed | Avg Time | Total Time |")
    lines.append("|-------|---------|---------|--------|----------|------------|")
    for s in summaries:
        total = s["total_prompts"]
        rate = (s["total_successes"] / total * 100) if total > 0 else 0
        lines.append(
            f"| `{s['model']}` "
            f"| {total} "
            f"| {s['total_successes']} ({rate:.0f}%) "
            f"| {s['total_failures']} "
            f"| {s['avg_processing_time_ms'] / 1000:.1f}s "
            f"| {s['total_time_s']:.1f}s |"
        )
    lines.append("")

    # --- Evaluation scores overview ---
    if has_evals:
        metric_names = get_eval_metrics(summaries)
        if metric_names:
            evaluator = None
            for s in summaries:
                e = s.get("_evaluations", {}).get("evaluator")
                if e:
                    evaluator = e
                    break

            lines.append("## Evaluation Scores")
            lines.append("")
            repeats = get_eval_repeats(summaries)
            eval_info_parts = []
            if evaluator:
                eval_info_parts.append(f"Evaluator model: `{evaluator}`")
            if repeats > 1:
                eval_info_parts.append(f"Repeats per response: **{repeats}** (scores are means)")
            if eval_info_parts:
                lines.append(" | ".join(eval_info_parts))
                lines.append("")

            header = "| Model | " + " | ".join(metric_names) + " | Overall |"
            sep = "|-------|" + "|".join("---" for _ in metric_names) + "|---------|"
            lines.append(header)
            lines.append(sep)

            for s in summaries:
                scores = get_prompt_scores(s)
                if not scores:
                    cells = ["-"] * (len(metric_names) + 1)
                    lines.append(f"| `{s['model']}` | " + " | ".join(cells) + " |")
                    continue

                avgs = []
                for m in metric_names:
                    vals = [sc[m] for sc in scores if sc.get(m) is not None]
                    avgs.append(sum(vals) / len(vals) if vals else 0)

                overall = sum(avgs) / len(avgs) if avgs else 0
                cells = [f"{a:.2f}" for a in avgs]
                cells.append(f"**{overall:.2f}**")
                lines.append(f"| `{s['model']}` | " + " | ".join(cells) + " |")

            lines.append("")

    # --- Plots ---
    media_rel = media_dir.name

    plot_sections = {
        "avg_time": ("Average Response Time", "Average time the model takes to respond to a single prompt."),
        "total_time": ("Total Run Time", "Wall-clock time for each model to complete all scenarios."),
        "success": ("Success / Failure Rate", "Number of successful vs failed prompts per model."),
        "time_dist": ("Response Time Distribution", "Spread of individual response times per model."),
        "scenario_time": ("Time per Scenario", "How long each scenario takes across models."),
        "cat_success": ("Success Rate by Category", "Success rate broken down by prompt category (help, injection, etc.)."),
        "cat_time": ("Response Time by Category", "Average response time broken down by prompt category."),
        "resp_length": ("Response Length", "Average character count of model responses."),
        "scores_model": ("Evaluation Scores per Model", "Average LLM-judged scores per metric for each model."),
        "scores_category": ("Scores by Category", "Heatmap of average overall score per model and prompt category."),
        "scores_dist": ("Score Distribution", "Spread of overall scores (averaged across metrics) per model."),
    }

    for name, filename in plots:
        title, desc = plot_sections.get(name, (name, ""))
        lines.append(f"## {title}")
        lines.append("")
        lines.append(desc)
        lines.append("")
        lines.append(f"![{title}]({media_rel}/{filename})")
        lines.append("")

    # --- Per-scenario details ---
    lines.append("## Per-Scenario Details")
    lines.append("")

    all_scenarios = []
    for s in summaries:
        for sc in s["scenarios"]:
            if sc["name"] not in all_scenarios:
                all_scenarios.append(sc["name"])

    for scenario_name in all_scenarios:
        lines.append(f"### {scenario_name}")
        lines.append("")
        lines.append("| Model | Time | Prompts | Successes | Failures | Blocked |")
        lines.append("|-------|------|---------|-----------|----------|---------|")

        for s in summaries:
            for sc in s["scenarios"]:
                if sc["name"] == scenario_name:
                    n_success = sum(1 for p in sc["prompts"] if p["success"])
                    n_fail = sum(1 for p in sc["prompts"] if not p["success"])
                    n_blocked = sum(1 for p in sc["prompts"] if p.get("blocked"))
                    lines.append(
                        f"| `{s['model']}` "
                        f"| {sc['total_time_s']:.1f}s "
                        f"| {len(sc['prompts'])} "
                        f"| {n_success} "
                        f"| {n_fail} "
                        f"| {n_blocked} |"
                    )

        lines.append("")

        # Collect prompt files for this scenario
        prompt_files = []
        for s in summaries:
            for sc in s["scenarios"]:
                if sc["name"] == scenario_name:
                    for p in sc["prompts"]:
                        if p["file"] not in prompt_files:
                            prompt_files.append(p["file"])

        # Build per-model evaluation lookup: model -> file -> scores dict
        eval_lookup = {}
        if has_evals:
            for s in summaries:
                model_scores = {}
                for sc_eval in s.get("_evaluations", {}).get("scenarios", []):
                    if sc_eval["name"] == scenario_name:
                        for pe in sc_eval.get("prompts", []):
                            if pe.get("evaluated"):
                                model_scores[pe["file"]] = pe.get("scores", {})
                eval_lookup[s["model"]] = model_scores

        # Per-prompt detail table
        lines.append("<details>")
        lines.append(f"<summary>Prompt details</summary>")
        lines.append("")
        lines.append("| Prompt | Category | " + " | ".join(f"`{s['model']}`" for s in summaries) + " |")
        lines.append("|--------|----------|" + "|".join("---" for _ in summaries) + "|")

        eval_metric_names = get_eval_metrics(summaries) if has_evals else []

        for pf in prompt_files:
            cat = extract_category(pf)
            cells = []
            for s in summaries:
                for sc in s["scenarios"]:
                    if sc["name"] == scenario_name:
                        found = False
                        for p in sc["prompts"]:
                            if p["file"] == pf:
                                if p["success"]:
                                    cell = f"{p['processing_time_ms']/1000:.1f}s"
                                    # Append overall score if available
                                    model_eval = eval_lookup.get(s["model"], {})
                                    pf_scores = model_eval.get(pf, {})
                                    if pf_scores:
                                        vals = [pf_scores[m] for m in eval_metric_names
                                                if pf_scores.get(m) is not None]
                                        if vals:
                                            cell += f" ({sum(vals)/len(vals):.1f})"
                                    cells.append(cell)
                                elif p.get("blocked"):
                                    cells.append("blocked")
                                else:
                                    cells.append("failed")
                                found = True
                                break
                        if not found:
                            cells.append("-")
            lines.append(f"| {pf} | {cat} | " + " | ".join(cells) + " |")

        lines.append("")
        lines.append("</details>")
        lines.append("")

    # --- Footer ---
    lines.append("---")
    lines.append("")
    lines.append("*Generated by `scripts/generate_report.py`*")
    lines.append("")

    report_path = output_dir / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate a markdown report with plots from scenario runner results",
    )
    parser.add_argument(
        "results_dir",
        help="Results directory containing run_* subdirectories (or a single run directory)",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for report (default: <results_dir>/report/)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
    )

    setup_style()

    results_dir = Path(args.results_dir).resolve()
    if not results_dir.is_dir():
        logger.error(f"Results directory does not exist: {results_dir}")
        sys.exit(1)

    summaries = load_summaries(results_dir)
    if not summaries:
        logger.error(f"No summary.json files found in {results_dir}")
        sys.exit(1)

    logger.info(f"Loaded {len(summaries)} run(s): {', '.join(s['model'] for s in summaries)}")

    # Output directory
    if args.output:
        output_dir = Path(args.output).resolve()
    else:
        output_dir = results_dir / "report"

    media_dir = output_dir / "media"
    media_dir.mkdir(parents=True, exist_ok=True)

    report_path = generate_report(summaries, output_dir, media_dir)

    logger.info(f"Report: {report_path}")
    logger.info(f"Plots:  {media_dir}/")


if __name__ == "__main__":
    main()
