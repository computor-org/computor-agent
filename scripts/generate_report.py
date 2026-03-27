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
import pandas as pd
import seaborn as sns

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

PALETTE = "deep"

def setup_style():
    """Configure seaborn + matplotlib for publication-quality plots."""
    sns.set_theme(
        style="whitegrid",
        context="paper",
        font_scale=1.3,
        rc={
            "figure.dpi": 150,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "grid.alpha": 0.3,
        },
    )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _reconstruct_summary_from_scenarios(run_dir: Path) -> dict | None:
    """Reconstruct a top-level summary from per-scenario summary.json files."""
    scenario_summaries = []
    for child in sorted(run_dir.iterdir()):
        sc_summary_path = child / "summary.json"
        if child.is_dir() and sc_summary_path.exists():
            try:
                sc_data = json.loads(sc_summary_path.read_text(encoding="utf-8"))
                scenario_summaries.append(sc_data)
            except (json.JSONDecodeError, OSError):
                continue

    if not scenario_summaries:
        return None

    first = scenario_summaries[0]
    scenarios = []
    for sc in scenario_summaries:
        scenarios.append({
            "name": sc.get("scenario", ""),
            "assignment": sc.get("assignment", ""),
            "total_time_s": sc.get("total_time_s", 0),
            "prompts": sc.get("prompts", []),
        })

    all_prompts = [p for sc in scenarios for p in sc["prompts"]]
    all_times = [p["processing_time_ms"] for p in all_prompts if p.get("success")]

    return {
        "model": first.get("model", "unknown"),
        "provider": first.get("provider", "unknown"),
        "timestamp": first.get("timestamp", ""),
        "total_scenarios": len(scenarios),
        "total_prompts": len(all_prompts),
        "total_successes": sum(1 for p in all_prompts if p.get("success")),
        "total_failures": sum(1 for p in all_prompts if not p.get("success")),
        "total_time_s": round(sum(sc.get("total_time_s", 0) for sc in scenario_summaries), 2),
        "avg_processing_time_ms": round(sum(all_times) / len(all_times), 1) if all_times else 0.0,
        "scenarios": scenarios,
    }


def _is_run_dir(d: Path) -> bool:
    """Check if a directory is a valid run directory."""
    if (d / "summary.json").exists():
        return True
    return any(
        (child / "summary.json").exists()
        for child in d.iterdir()
        if child.is_dir()
    )


def load_summaries(results_dir: Path) -> list[dict]:
    """Find and load all summary.json + evaluations.json files under results_dir."""
    summaries = []

    def _load_run(run_path: Path) -> dict | None:
        top_level = run_path / "summary.json"
        if top_level.exists():
            try:
                data = json.loads(top_level.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = _reconstruct_summary_from_scenarios(run_path)
        else:
            data = _reconstruct_summary_from_scenarios(run_path)

        if not data:
            return None

        data["_run_dir"] = str(run_path)
        eval_path = run_path / "evaluations.json"
        if eval_path.exists():
            try:
                data["_evaluations"] = json.loads(eval_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return data

    # If pointed directly at a run directory
    if _is_run_dir(results_dir):
        run = _load_run(results_dir)
        if run:
            summaries.append(run)
        return summaries

    # Otherwise scan subdirectories
    for child in sorted(results_dir.iterdir()):
        if child.is_dir() and _is_run_dir(child):
            run = _load_run(child)
            if run:
                summaries.append(run)

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

def _bar_labels(ax, fmt="{:.1f}"):
    """Add value labels on top of bars."""
    for container in ax.containers:
        ax.bar_label(container, fmt=fmt, fontsize=9, padding=3)


def plot_avg_time_per_model(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: average processing time per model."""
    df = pd.DataFrame({
        "Model": [s["model"] for s in summaries],
        "Time (s)": [s["avg_processing_time_ms"] / 1000 for s in summaries],
    })

    fig, ax = plt.subplots(figsize=(max(8, len(df) * 1.5), 5))
    sns.barplot(data=df, x="Model", y="Time (s)", palette=PALETTE, ax=ax)
    ax.set_title("Average Response Time per Model")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    _bar_labels(ax, fmt="{:.1f}s")

    fig.tight_layout()
    path = out_dir / "avg_time_per_model.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_total_time_per_model(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: total run time per model."""
    df = pd.DataFrame({
        "Model": [s["model"] for s in summaries],
        "Time (s)": [s["total_time_s"] for s in summaries],
    })

    fig, ax = plt.subplots(figsize=(max(8, len(df) * 1.5), 5))
    sns.barplot(data=df, x="Model", y="Time (s)", palette=PALETTE, ax=ax)
    ax.set_title("Total Run Time per Model")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    _bar_labels(ax, fmt="{:.1f}s")

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
    palette = sns.color_palette(PALETTE, 2)

    fig, ax = plt.subplots(figsize=(max(8, len(models) * 1.5), 5))
    x = range(len(models))
    ax.bar(x, successes, label="Success", color=palette[0])
    ax.bar(x, failures, bottom=successes, label="Failure", color=palette[1])
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
    rows = []
    for s in summaries:
        for sc in s["scenarios"]:
            rows.append({"Model": s["model"], "Scenario": sc["name"], "Time (s)": sc["total_time_s"]})

    if not rows:
        return None

    df = pd.DataFrame(rows)
    n_scenarios = df["Scenario"].nunique()

    fig, ax = plt.subplots(figsize=(max(10, n_scenarios * 2), 5))
    sns.barplot(data=df, x="Scenario", y="Time (s)", hue="Model", palette=PALETTE, ax=ax)
    ax.set_title("Time per Scenario by Model")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    sns.move_legend(ax, "upper right")

    fig.tight_layout()
    path = out_dir / "time_per_scenario.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_time_distribution(summaries: list[dict], out_dir: Path) -> str:
    """Box plot: response time distribution per model."""
    rows = []
    for s in summaries:
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                if p["success"]:
                    rows.append({"Model": s["model"], "Time (s)": p["processing_time_ms"] / 1000})

    if not rows:
        return None

    df = pd.DataFrame(rows)
    n_models = df["Model"].nunique()

    fig, ax = plt.subplots(figsize=(max(8, n_models * 1.5), 5))
    sns.boxplot(data=df, x="Model", y="Time (s)", palette=PALETTE, ax=ax)
    ax.set_title("Response Time Distribution per Model")
    ax.set_xlabel("")
    if n_models > 3:
        ax.tick_params(axis="x", rotation=30)

    fig.tight_layout()
    path = out_dir / "time_distribution.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_category_success(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: success rate per prompt category across models."""
    cat_stats: dict[str, dict[str, list[int]]] = {}
    all_categories: set[str] = set()

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

    all_categories_sorted = sorted(all_categories)
    if len(all_categories_sorted) <= 1:
        return None

    rows = []
    for model in cat_stats:
        for cat in all_categories_sorted:
            s, t = cat_stats[model].get(cat, [0, 0])
            rows.append({"Model": model, "Category": cat, "Success Rate (%)": (s / t * 100) if t > 0 else 0})

    df = pd.DataFrame(rows)
    n_cats = len(all_categories_sorted)

    fig, ax = plt.subplots(figsize=(max(10, n_cats * 2), 5))
    sns.barplot(data=df, x="Category", y="Success Rate (%)", hue="Model", palette=PALETTE, ax=ax)
    ax.set_ylim(0, 110)
    ax.set_title("Success Rate per Category by Model")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    sns.move_legend(ax, "upper right")

    fig.tight_layout()
    path = out_dir / "category_success.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_category_time(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: average response time per category across models."""
    rows = []
    for s in summaries:
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                if p["success"]:
                    cat = extract_category(p["file"])
                    rows.append({"Model": s["model"], "Category": cat, "Time (s)": p["processing_time_ms"] / 1000})

    if not rows:
        return None

    df = pd.DataFrame(rows)
    if df["Category"].nunique() <= 1:
        return None

    n_cats = df["Category"].nunique()

    fig, ax = plt.subplots(figsize=(max(10, n_cats * 2), 5))
    sns.barplot(data=df, x="Category", y="Time (s)", hue="Model", palette=PALETTE, estimator="mean", ax=ax)
    ax.set_title("Average Response Time per Category by Model")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    sns.move_legend(ax, "upper right")

    fig.tight_layout()
    path = out_dir / "category_time.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_response_length(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: average response length (chars) per model."""
    rows = []
    for s in summaries:
        chars = [p["response_chars"] for sc in s["scenarios"]
                 for p in sc["prompts"] if p["success"] and p["response_chars"] > 0]
        if chars:
            rows.append({"Model": s["model"], "Avg Length (chars)": sum(chars) / len(chars)})

    if not rows:
        return None

    df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(max(8, len(df) * 1.5), 5))
    sns.barplot(data=df, x="Model", y="Avg Length (chars)", palette=PALETTE, ax=ax)
    ax.set_title("Average Response Length per Model")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    _bar_labels(ax, fmt="{:.0f}")

    fig.tight_layout()
    path = out_dir / "response_length.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


# ---------------------------------------------------------------------------
# Evaluation plot generators
# ---------------------------------------------------------------------------

def plot_scores_per_model(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: average score per metric per model."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    rows = []
    for s in summaries:
        details = get_prompt_score_details(s)
        if not details:
            continue
        for m in metric_names:
            vals = [d["scores"].get(m) for d in details if d["scores"].get(m) is not None]
            if vals:
                rows.append({"Model": s["model"], "Metric": m, "Score": sum(vals) / len(vals)})

    if not rows:
        return None

    df = pd.DataFrame(rows)
    n_metrics = len(metric_names)

    fig, ax = plt.subplots(figsize=(max(10, n_metrics * 1.5), 5))
    sns.barplot(data=df, x="Metric", y="Score", hue="Model", palette=PALETTE, ax=ax)
    ax.set_ylim(0, 5.5)
    has_repeats = get_eval_repeats(summaries) > 1
    title = "Average Evaluation Scores per Model"
    if has_repeats:
        title += f" ({get_eval_repeats(summaries)} repeats)"
    ax.set_title(title)
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    sns.move_legend(ax, "upper right")

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
    all_categories: set[str] = set()
    model_cat_scores: dict[str, dict[str, list[float]]] = {}

    for s in summaries:
        scores = get_prompt_scores(s)
        if not scores:
            continue
        model = s["model"]
        models.append(model)
        cat_scores: dict[str, list[float]] = defaultdict(list)
        for sc in scores:
            cat = sc["category"]
            all_categories.add(cat)
            vals = [sc[m] for m in metric_names if sc.get(m) is not None]
            if vals:
                cat_scores[cat].append(sum(vals) / len(vals))
        model_cat_scores[model] = cat_scores

    all_categories_sorted = sorted(all_categories)
    if not models or not all_categories_sorted:
        return None

    # Build DataFrame for heatmap
    matrix_data = {}
    for model in models:
        row = {}
        for cat in all_categories_sorted:
            vals = model_cat_scores[model].get(cat, [])
            row[cat] = sum(vals) / len(vals) if vals else 0
        matrix_data[model] = row

    df = pd.DataFrame(matrix_data).T
    df.columns.name = "Category"

    fig, ax = plt.subplots(figsize=(max(8, len(all_categories_sorted) * 1.5),
                                     max(4, len(models) * 0.8 + 2)))
    sns.heatmap(
        df, annot=True, fmt=".1f", cmap="RdYlGn",
        vmin=0, vmax=5, linewidths=0.5, linecolor="white",
        cbar_kws={"label": "Score (0-5)"},
        annot_kws={"fontsize": 11, "fontweight": "bold"},
        ax=ax,
    )
    ax.set_title("Average Score per Model and Category")
    ax.tick_params(axis="x", rotation=30)
    ax.tick_params(axis="y", rotation=0)

    fig.tight_layout()
    path = out_dir / "scores_per_category.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_score_distribution(summaries: list[dict], out_dir: Path) -> str:
    """Box plot: distribution of overall scores per model."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    has_repeats = get_eval_repeats(summaries) > 1
    rows = []

    for s in summaries:
        details = get_prompt_score_details(s)
        if not details:
            continue
        if has_repeats:
            for d in details:
                for repeat_scores in d.get("all_scores", []):
                    vals = [repeat_scores.get(m) for m in metric_names
                            if repeat_scores.get(m) is not None]
                    if vals:
                        rows.append({"Model": s["model"], "Score": sum(vals) / len(vals)})
        if not any(r["Model"] == s["model"] for r in rows):
            scores = get_prompt_scores(s)
            for sc in scores:
                vals = [sc[m] for m in metric_names if sc.get(m) is not None]
                if vals:
                    rows.append({"Model": s["model"], "Score": sum(vals) / len(vals)})

    if not rows:
        return None

    df = pd.DataFrame(rows)
    n_models = df["Model"].nunique()

    fig, ax = plt.subplots(figsize=(max(8, n_models * 1.5), 5))
    sns.boxplot(data=df, x="Model", y="Score", palette=PALETTE, ax=ax)
    ax.set_ylim(0, 5.5)
    ax.set_ylabel("Overall score (avg across metrics)")
    title = "Score Distribution per Model"
    if has_repeats:
        title += f" (from {get_eval_repeats(summaries)} repeats per response)"
    ax.set_title(title)
    ax.set_xlabel("")
    if n_models > 3:
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
