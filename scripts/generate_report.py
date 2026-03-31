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
COLORS = ["#4c72b0", "#dd8452", "#55a868", "#c44e52", "#8172b3",
          "#937860", "#da8bc3", "#8c8c8c", "#ccb974", "#64b5cd"]
MARKERS = ["o", "s", "D", "^", "v", "P", "X", "*", "h", "<"]

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
                # Skip files that look like top-level summaries (e.g. report/)
                if "scenarios" in sc_data and isinstance(sc_data["scenarios"], list):
                    continue
                sc_data["_dir_name"] = child.name
                scenario_summaries.append(sc_data)
            except (json.JSONDecodeError, OSError):
                continue

    if not scenario_summaries:
        return None

    first = scenario_summaries[0]
    scenarios = []
    for sc in scenario_summaries:
        name = sc.get("scenario") or sc.get("_dir_name", "")
        scenarios.append({
            "name": name,
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
    """Check if a directory is a valid run directory.

    A run directory either has:
    - A top-level summary.json with a "scenarios" list, OR
    - Subdirectories that contain per-scenario summary.json files (with "prompts" key)
    """
    top = d / "summary.json"
    if top.exists():
        try:
            data = json.loads(top.read_text(encoding="utf-8"))
            if "scenarios" in data and isinstance(data["scenarios"], list):
                return True
        except (json.JSONDecodeError, OSError):
            pass

    for child in d.iterdir():
        if child.is_dir():
            sc_summary = child / "summary.json"
            if sc_summary.exists():
                try:
                    data = json.loads(sc_summary.read_text(encoding="utf-8"))
                    if "prompts" in data and "scenarios" not in data:
                        return True
                except (json.JSONDecodeError, OSError):
                    pass
    return False


def _load_run(run_path: Path) -> dict | None:
    """Load a run summary, reconstructing from per-scenario summaries if needed."""
    top_level = run_path / "summary.json"
    data = None
    if top_level.exists():
        try:
            raw = json.loads(top_level.read_text(encoding="utf-8"))
            # Only accept if it has the top-level structure
            if "scenarios" in raw and isinstance(raw["scenarios"], list):
                data = raw
        except (json.JSONDecodeError, OSError):
            pass

    if not data:
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


def load_summaries(results_dir: Path) -> list[dict]:
    """Find and load all summary.json + evaluations.json files under results_dir."""
    summaries = []

    # Scan children first (the common case: results/ contains run_* dirs)
    for child in sorted(results_dir.iterdir()):
        if child.is_dir() and _is_run_dir(child):
            run = _load_run(child)
            if run:
                summaries.append(run)

    if summaries:
        return summaries

    # Fallback: results_dir itself is a run directory
    if _is_run_dir(results_dir):
        run = _load_run(results_dir)
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


def get_text_metrics(summary: dict) -> list[dict]:
    """Extract per-prompt text metrics from evaluations."""
    evals = summary.get("_evaluations", {})
    results = []
    for sc in evals.get("scenarios", []):
        for p in sc.get("prompts", []):
            tm = p.get("text_metrics")
            if tm:
                entry = {
                    "file": p["file"],
                    "category": p.get("category", extract_category(p["file"])),
                    "scenario": sc["name"],
                }
                entry.update(tm)
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
    """Bar chart: total run time per model (summed from individual prompt times)."""
    rows = []
    for s in summaries:
        total_ms = sum(
            p["processing_time_ms"]
            for sc in s["scenarios"]
            for p in sc["prompts"]
            if p.get("success")
        )
        rows.append({"Model": s["model"], "Time (s)": total_ms / 1000})

    df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(max(8, len(df) * 1.5), 5))
    sns.barplot(data=df, x="Model", y="Time (s)", palette=PALETTE, ax=ax)
    ax.set_title("Total Processing Time per Model")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=30)
    _bar_labels(ax, fmt="{:.0f}s")

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


def _extract_assignment(scenario_name: str) -> str:
    """Extract assignment name from scenario like 'course__assignment__042' -> 'assignment'."""
    parts = scenario_name.split("__")
    if len(parts) >= 2:
        return parts[1]
    return scenario_name


def plot_time_per_scenario(summaries: list[dict], out_dir: Path) -> list[str]:
    """Per-model horizontal bar charts of *assignment* times (aggregated).

    Scenarios are grouped by assignment (stripping the trailing numeric ID),
    producing one manageable chart per model instead of 170+ bars.
    """
    scenarios_dir = out_dir / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    paths = []

    for s in summaries:
        # Aggregate times by assignment
        assignment_times: dict[str, list[float]] = defaultdict(list)
        for sc in s["scenarios"]:
            assignment = _extract_assignment(sc["name"])
            for p in sc["prompts"]:
                if p.get("success"):
                    assignment_times[assignment].append(p["processing_time_ms"] / 1000)

        if not assignment_times:
            continue

        rows = []
        for assignment, times in assignment_times.items():
            rows.append({
                "Assignment": assignment,
                "Avg Time (s)": sum(times) / len(times),
                "Total Time (s)": sum(times),
                "Count": len(times),
            })

        df = pd.DataFrame(rows).sort_values("Avg Time (s)", ascending=True)
        n = len(df)
        fig_height = max(4, n * 0.35 + 1.5)

        fig, ax = plt.subplots(figsize=(10, fig_height))
        bars = ax.barh(range(n), df["Avg Time (s)"].values,
                       color=sns.color_palette(PALETTE, n))
        ax.set_yticks(range(n))
        ax.set_yticklabels(df["Assignment"].values, fontsize=8)
        ax.set_xlabel("Avg response time (s)")
        ax.set_title(f"Avg Response Time per Assignment — {s['model']}")

        # Label bars with count
        for bar, count in zip(bars, df["Count"].values):
            ax.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                    f"n={count}", va="center", fontsize=7, color="gray")

        fig.tight_layout()
        slug = s["model"].replace(":", "-").replace("/", "-")
        filename = f"scenario_time_{slug}.png"
        fig.savefig(scenarios_dir / filename, dpi=120)
        plt.close(fig)
        paths.append(f"scenarios/{filename}")

    return paths if paths else None


def plot_assignment_comparison(summaries: list[dict], out_dir: Path,
                               n_assignments: int = 5) -> str:
    """Cleveland dot plot: top-N assignments by variance, all models on one chart.

    Y-axis: assignment names, X-axis: avg response time (s).
    Each model is a line+marker series with legend.
    """
    # Gather per-model, per-assignment avg times
    model_assignment_times: dict[str, dict[str, list[float]]] = {}
    for s in summaries:
        model = s["model"]
        agg: dict[str, list[float]] = defaultdict(list)
        for sc in s["scenarios"]:
            assignment = _extract_assignment(sc["name"])
            for p in sc["prompts"]:
                if p.get("success"):
                    agg[assignment].append(p["processing_time_ms"] / 1000)
        model_assignment_times[model] = {a: sum(t) / len(t) for a, t in agg.items() if t}

    if len(model_assignment_times) < 2:
        return None

    # Find assignments present in all models
    all_assignments = set.intersection(
        *(set(d.keys()) for d in model_assignment_times.values())
    )
    if len(all_assignments) < 2:
        return None

    # Pick assignments with highest cross-model variance (most interesting)
    variances = {}
    for a in all_assignments:
        vals = [model_assignment_times[m][a] for m in model_assignment_times]
        variances[a] = np.var(vals)

    selected = sorted(variances, key=variances.get, reverse=True)[:n_assignments]

    models = list(model_assignment_times.keys())

    fig, ax = plt.subplots(figsize=(max(8, len(selected) * 1.5 + 1), 6))
    x_pos = np.arange(len(selected))

    for i, model in enumerate(models):
        times = [model_assignment_times[model][a] for a in selected]
        ax.plot(x_pos, times, marker=MARKERS[i % len(MARKERS)],
                color=COLORS[i % len(COLORS)], linewidth=1.5, markersize=8,
                label=model, linestyle="--", alpha=0.85)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(selected, fontsize=9, rotation=30, ha="right")
    ax.set_ylabel("Avg response time (s)")
    ax.set_title("Response Time Comparison — Selected Assignments")
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()
    path = out_dir / "assignment_comparison.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path.name


def plot_assignment_quality_comparison(summaries: list[dict], out_dir: Path,
                                       n_assignments: int = 5) -> str:
    """Cleveland dot plot: top-N assignments by quality variance, all models on one chart.

    X-axis: assignment names, Y-axis: avg overall quality score (0-5).
    Each model is a line+marker series with legend.
    """
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    # Gather per-model, per-assignment avg quality scores
    model_assignment_scores: dict[str, dict[str, list[float]]] = {}
    for s in summaries:
        scores = get_prompt_scores(s)
        if not scores:
            continue
        model = s["model"]
        agg: dict[str, list[float]] = defaultdict(list)
        for sc in scores:
            assignment = _extract_assignment(sc["scenario"])
            vals = [sc[m] for m in metric_names if sc.get(m) is not None]
            if vals:
                agg[assignment].append(sum(vals) / len(vals))
        model_assignment_scores[model] = {a: sum(v) / len(v) for a, v in agg.items() if v}

    if len(model_assignment_scores) < 2:
        return None

    # Find assignments present in all models
    all_assignments = set.intersection(
        *(set(d.keys()) for d in model_assignment_scores.values())
    )
    if len(all_assignments) < 2:
        return None

    # Pick assignments with highest cross-model variance
    variances = {}
    for a in all_assignments:
        vals = [model_assignment_scores[m][a] for m in model_assignment_scores]
        variances[a] = np.var(vals)

    selected = sorted(variances, key=variances.get, reverse=True)[:n_assignments]

    models = list(model_assignment_scores.keys())

    fig, ax = plt.subplots(figsize=(max(8, len(selected) * 1.5 + 1), 6))
    x_pos = np.arange(len(selected))

    for i, model in enumerate(models):
        scores = [model_assignment_scores[model][a] for a in selected]
        ax.plot(x_pos, scores, marker=MARKERS[i % len(MARKERS)],
                color=COLORS[i % len(COLORS)], linewidth=1.5, markersize=8,
                label=model, linestyle="--", alpha=0.85)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(selected, fontsize=9, rotation=30, ha="right")
    ax.set_ylabel("Avg quality score")
    ax.set_title("Quality Score Comparison — Selected Assignments")
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)

    # Zoom Y-axis to data range in 0.5 steps, clamped to [0, 5.5]
    all_vals = [model_assignment_scores[m][a] for m in models for a in selected]
    y_min = max(0, np.floor(min(all_vals) * 2) / 2 - 0.5)
    y_max = min(5.5, np.ceil(max(all_vals) * 2) / 2 + 0.5)
    ax.set_ylim(y_min, y_max)
    ax.set_yticks(np.arange(y_min, y_max + 0.01, 0.5))

    fig.tight_layout()
    path = out_dir / "assignment_quality_comparison.png"
    fig.savefig(path, dpi=120)
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


def plot_time_by_category_box(summaries: list[dict], out_dir: Path) -> str:
    """Box plot: response time distribution per category (across all models)."""
    cat_times = defaultdict(list)

    for s in summaries:
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                if p["success"]:
                    cat = extract_category(p["file"])
                    cat_times[cat].append(p["processing_time_ms"] / 1000)

    categories = sorted(cat_times.keys())
    if len(categories) < 2:
        return None

    fig, ax = plt.subplots(figsize=(max(8, len(categories) * 1.2), 5))
    data = [cat_times[c] for c in categories]
    bp = ax.boxplot(data, labels=categories, patch_artist=True)

    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(COLORS[i % len(COLORS)])
        patch.set_alpha(0.7)

    ax.set_ylabel("Response time (s)")
    ax.set_title("Response Time Distribution by Category")
    ax.tick_params(axis="x", rotation=30)

    fig.tight_layout()
    path = out_dir / "time_by_category_box.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_length_by_category(summaries: list[dict], out_dir: Path) -> str:
    """Box plot: response length distribution per category."""
    cat_lengths = defaultdict(list)

    for s in summaries:
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                if p["success"] and p["response_chars"] > 0:
                    cat = extract_category(p["file"])
                    cat_lengths[cat].append(p["response_chars"])

    categories = sorted(cat_lengths.keys())
    if len(categories) < 2:
        return None

    fig, ax = plt.subplots(figsize=(max(8, len(categories) * 1.2), 5))
    data = [cat_lengths[c] for c in categories]
    bp = ax.boxplot(data, labels=categories, patch_artist=True)

    for i, patch in enumerate(bp["boxes"]):
        patch.set_facecolor(COLORS[i % len(COLORS)])
        patch.set_alpha(0.7)

    ax.set_ylabel("Response length (chars)")
    ax.set_title("Response Length Distribution by Category")
    ax.tick_params(axis="x", rotation=30)

    fig.tight_layout()
    path = out_dir / "length_by_category.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_prompt_count_by_category(summaries: list[dict], out_dir: Path) -> str:
    """Bar chart: number of prompts per category (dataset overview)."""
    cat_counts = defaultdict(int)

    for s in summaries:
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                cat = extract_category(p["file"])
                cat_counts[cat] += 1

    categories = sorted(cat_counts.keys())
    if len(categories) < 2:
        return None

    counts = [cat_counts[c] for c in categories]

    fig, ax = plt.subplots(figsize=(max(8, len(categories) * 1.2), 5))
    bars = ax.bar(range(len(categories)), counts,
                  color=[COLORS[i % len(COLORS)] for i in range(len(categories))])
    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories, rotation=30, ha="right")
    ax.set_ylabel("Number of prompts")
    ax.set_title("Prompt Count by Category")

    for bar, c in zip(bars, counts):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                str(c), ha="center", va="bottom", fontsize=10)

    fig.tight_layout()
    path = out_dir / "prompt_count_by_category.png"
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


def plot_radar_chart(summaries: list[dict], out_dir: Path) -> str:
    """Radar/spider chart: metric profile per model."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names or len(metric_names) < 3:
        return None

    models = []
    model_avgs = []
    for s in summaries:
        scores = get_prompt_scores(s)
        if not scores:
            continue
        models.append(s["model"])
        avgs = []
        for m in metric_names:
            vals = [sc[m] for sc in scores if sc.get(m) is not None]
            avgs.append(sum(vals) / len(vals) if vals else 0)
        model_avgs.append(avgs)

    if not models:
        return None

    n = len(metric_names)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))

    for i, (model, avgs) in enumerate(zip(models, model_avgs)):
        values = avgs + avgs[:1]
        ax.plot(angles, values, linewidth=2, label=model,
                color=COLORS[i % len(COLORS)])
        ax.fill(angles, values, alpha=0.1, color=COLORS[i % len(COLORS)])

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metric_names, fontsize=10)
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_title("Model Metric Profiles", y=1.08, fontsize=13)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)

    fig.tight_layout()
    path = out_dir / "radar_chart.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path.name


def plot_time_vs_quality(summaries: list[dict], out_dir: Path) -> str:
    """Scatter: average response time vs overall quality score per model."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    models, times, scores = [], [], []
    for s in summaries:
        prompt_scores = get_prompt_scores(s)
        if not prompt_scores:
            continue
        avg_time = s["avg_processing_time_ms"] / 1000
        avgs = []
        for m in metric_names:
            vals = [sc[m] for sc in prompt_scores if sc.get(m) is not None]
            avgs.append(sum(vals) / len(vals) if vals else 0)
        overall = sum(avgs) / len(avgs) if avgs else 0
        models.append(s["model"])
        times.append(avg_time)
        scores.append(overall)

    if len(models) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 6))
    for i, (model, t, sc) in enumerate(zip(models, times, scores)):
        ax.scatter(t, sc, s=120, color=COLORS[i % len(COLORS)], zorder=5)
        ax.annotate(model, (t, sc), textcoords="offset points",
                    xytext=(8, 5), fontsize=9)

    ax.set_xlabel("Avg response time (s)")
    ax.set_ylabel("Overall quality score (0-5)")
    ax.set_ylim(0, 5.5)
    ax.set_title("Response Time vs Quality")

    fig.tight_layout()
    path = out_dir / "time_vs_quality.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_length_vs_quality(summaries: list[dict], out_dir: Path) -> str:
    """Scatter: average response length vs overall quality score per model."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    models, lengths, scores = [], [], []
    for s in summaries:
        prompt_scores = get_prompt_scores(s)
        if not prompt_scores:
            continue
        chars = [p["response_chars"] for sc in s["scenarios"]
                 for p in sc["prompts"] if p["success"] and p["response_chars"] > 0]
        if not chars:
            continue
        avg_len = sum(chars) / len(chars)
        avgs = []
        for m in metric_names:
            vals = [sc[m] for sc in prompt_scores if sc.get(m) is not None]
            avgs.append(sum(vals) / len(vals) if vals else 0)
        overall = sum(avgs) / len(avgs) if avgs else 0
        models.append(s["model"])
        lengths.append(avg_len)
        scores.append(overall)

    if len(models) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 6))
    for i, (model, l, sc) in enumerate(zip(models, lengths, scores)):
        ax.scatter(l, sc, s=120, color=COLORS[i % len(COLORS)], zorder=5)
        ax.annotate(model, (l, sc), textcoords="offset points",
                    xytext=(8, 5), fontsize=9)

    ax.set_xlabel("Avg response length (chars)")
    ax.set_ylabel("Overall quality score (0-5)")

    # Dynamic Y-axis zoom based on actual data (0.5 steps)
    y_min = max(0, np.floor(min(scores) * 2) / 2 - 0.5)
    y_max = min(5.5, np.ceil(max(scores) * 2) / 2 + 0.5)
    ax.set_ylim(y_min, y_max)
    ax.set_yticks(np.arange(y_min, y_max + 0.01, 0.5))

    ax.set_title("Response Length vs Quality")

    fig.tight_layout()
    path = out_dir / "length_vs_quality.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_metric_heatmap(summaries: list[dict], out_dir: Path) -> str:
    """Heatmap: model x metric score matrix."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    models = []
    matrix = []
    for s in summaries:
        scores = get_prompt_scores(s)
        if not scores:
            continue
        models.append(s["model"])
        row = []
        for m in metric_names:
            vals = [sc[m] for sc in scores if sc.get(m) is not None]
            row.append(sum(vals) / len(vals) if vals else 0)
        matrix.append(row)

    if len(models) < 1:
        return None

    matrix = np.array(matrix)

    fig, ax = plt.subplots(figsize=(max(8, len(metric_names) * 1.5),
                                     max(4, len(models) * 0.8 + 2)))
    im = ax.imshow(matrix, cmap="RdYlGn", aspect="auto", vmin=0, vmax=5)

    ax.set_xticks(range(len(metric_names)))
    ax.set_xticklabels(metric_names, rotation=30, ha="right")
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels(models)
    ax.set_title("Score Matrix: Model x Metric")

    for i in range(len(models)):
        for j in range(len(metric_names)):
            val = matrix[i, j]
            color = "white" if val < 2.5 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    fontsize=11, fontweight="bold", color=color)

    fig.colorbar(im, ax=ax, label="Score (0-5)")
    fig.tight_layout()
    path = out_dir / "metric_heatmap.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_metric_boxplots(summaries: list[dict], out_dir: Path) -> str:
    """Box plots: per-metric score distribution, one subplot per metric."""
    metric_names = get_eval_metrics(summaries)
    if not metric_names:
        return None

    models = []
    model_data = {}  # model -> metric -> list of scores
    for s in summaries:
        scores = get_prompt_scores(s)
        if not scores:
            continue
        model = s["model"]
        models.append(model)
        model_data[model] = {}
        for m in metric_names:
            model_data[model][m] = [sc[m] for sc in scores if sc.get(m) is not None]

    if len(models) < 1:
        return None

    n_metrics = len(metric_names)
    fig, axes = plt.subplots(1, n_metrics, figsize=(n_metrics * 3.5, 5), sharey=True)
    if n_metrics == 1:
        axes = [axes]

    for j, metric in enumerate(metric_names):
        ax = axes[j]
        data = [model_data[m].get(metric, []) for m in models]
        bp = ax.boxplot(data, labels=models, patch_artist=True)
        for i, patch in enumerate(bp["boxes"]):
            patch.set_facecolor(COLORS[i % len(COLORS)])
            patch.set_alpha(0.7)
        ax.set_title(metric, fontsize=10)
        ax.set_ylim(0, 5.5)
        ax.tick_params(axis="x", rotation=45)
        if j == 0:
            ax.set_ylabel("Score")

    fig.suptitle("Score Distribution per Metric", fontsize=13, y=1.02)
    fig.tight_layout()
    path = out_dir / "metric_boxplots.png"
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path.name


def plot_boundary_vs_helpfulness(summaries: list[dict], out_dir: Path) -> str:
    """Scatter: boundary_adherence (on adversarial) vs helpfulness (on help) per model."""
    metric_names = get_eval_metrics(summaries)
    if "boundary_adherence" not in metric_names or "helpfulness" not in metric_names:
        return None

    adversarial_cats = {"injection", "solution_request"}
    help_cats = {"help", "debug", "conceptual"}

    models, boundary_scores, help_scores = [], [], []
    for s in summaries:
        scores = get_prompt_scores(s)
        if not scores:
            continue
        b_vals = [sc["boundary_adherence"] for sc in scores
                  if sc["category"] in adversarial_cats
                  and sc.get("boundary_adherence") is not None]
        h_vals = [sc["helpfulness"] for sc in scores
                  if sc["category"] in help_cats
                  and sc.get("helpfulness") is not None]
        if b_vals and h_vals:
            models.append(s["model"])
            boundary_scores.append(sum(b_vals) / len(b_vals))
            help_scores.append(sum(h_vals) / len(h_vals))

    if len(models) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 6))
    for i, (model, b, h) in enumerate(zip(models, boundary_scores, help_scores)):
        ax.scatter(h, b, s=120, color=COLORS[i % len(COLORS)], zorder=5)
        ax.annotate(model, (h, b), textcoords="offset points",
                    xytext=(8, 5), fontsize=9)

    ax.set_xlabel("Helpfulness (on help/debug/conceptual prompts)")
    ax.set_ylabel("Boundary Adherence (on injection/solution_request)")
    ax.set_xlim(0, 5.5)
    ax.set_ylim(0, 5.5)
    ax.set_title("Safety vs Helpfulness Trade-off")
    # Draw quadrant lines
    ax.axhline(y=2.5, color="gray", linestyle="--", alpha=0.3)
    ax.axvline(x=2.5, color="gray", linestyle="--", alpha=0.3)

    fig.tight_layout()
    path = out_dir / "boundary_vs_helpfulness.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_text_style(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: text style metrics (questions, code blocks, avg sentence length) per model."""
    style_metrics = ["question_count", "code_block_count", "avg_sentence_length"]
    style_labels = ["Avg Questions\nper Response", "Avg Code Blocks\nper Response", "Avg Sentence\nLength (words)"]

    models = []
    model_avgs = []
    for s in summaries:
        tm = get_text_metrics(s)
        if not tm:
            continue
        models.append(s["model"])
        avgs = []
        for metric in style_metrics:
            vals = [t[metric] for t in tm if t.get(metric) is not None]
            avgs.append(sum(vals) / len(vals) if vals else 0)
        model_avgs.append(avgs)

    if len(models) < 1:
        return None

    n_metrics = len(style_metrics)
    n_models = len(models)

    fig, ax = plt.subplots(figsize=(max(8, n_metrics * 2.5), 5))
    bar_width = 0.8 / n_models
    x = np.arange(n_metrics)

    for i, (model, avgs) in enumerate(zip(models, model_avgs)):
        offset = (i - n_models / 2 + 0.5) * bar_width
        bars = ax.bar(x + offset, avgs, bar_width,
                      label=model, color=COLORS[i % len(COLORS)])
        for bar, val in zip(bars, avgs):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(style_labels)
    ax.set_ylabel("Value")
    ax.set_title("Response Style Comparison")
    ax.legend(fontsize=8)

    fig.tight_layout()
    path = out_dir / "text_style.png"
    fig.savefig(path)
    plt.close(fig)
    return path.name


def plot_category_score_comparison(summaries: list[dict], out_dir: Path) -> str:
    """Grouped bar chart: overall score per category per model (side by side)."""
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
    if not models or len(all_categories) < 2:
        return None

    n_models = len(models)
    n_cats = len(all_categories)

    fig, ax = plt.subplots(figsize=(max(10, n_cats * 2), 5))
    bar_width = 0.8 / n_models
    x = np.arange(n_cats)

    for i, model in enumerate(models):
        avgs = []
        for cat in all_categories:
            vals = model_cat_scores[model].get(cat, [])
            avgs.append(sum(vals) / len(vals) if vals else 0)
        offset = (i - n_models / 2 + 0.5) * bar_width
        ax.bar(x + offset, avgs, bar_width,
               label=model, color=COLORS[i % len(COLORS)])

    ax.set_xticks(x)
    ax.set_xticklabels(all_categories, rotation=30, ha="right")
    ax.set_ylabel("Overall score (0-5)")
    ax.set_ylim(0, 5.5)
    ax.set_title("Overall Score per Category by Model")
    ax.legend(fontsize=8)

    fig.tight_layout()
    path = out_dir / "category_score_comparison.png"
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
        ("prompt_counts", plot_prompt_count_by_category),
        ("avg_time", plot_avg_time_per_model),
        ("total_time", plot_total_time_per_model),
        ("success", plot_success_rate),
        ("time_dist", plot_time_distribution),
        ("time_by_cat_box", plot_time_by_category_box),
        ("cat_time", plot_category_time),
        ("cat_success", plot_category_success),
        ("resp_length", plot_response_length),
        ("length_by_cat", plot_length_by_category),
        ("assignment_compare", plot_assignment_comparison),
    ]

    if has_evals:
        plot_funcs.extend([
            ("scores_model", plot_scores_per_model),
            ("metric_heatmap", plot_metric_heatmap),
            ("radar", plot_radar_chart),
            ("metric_boxplots", plot_metric_boxplots),
            ("scores_category", plot_scores_per_category),
            ("cat_score_compare", plot_category_score_comparison),
            ("scores_dist", plot_score_distribution),
            ("time_vs_quality", plot_time_vs_quality),
            ("length_vs_quality", plot_length_vs_quality),
            ("boundary_vs_help", plot_boundary_vs_helpfulness),
            ("text_style", plot_text_style),
            ("assignment_quality", plot_assignment_quality_comparison),
        ])

    for name, func in plot_funcs:
        try:
            result = func(summaries, media_dir)
            if result:
                plots.append((name, result))
        except Exception as e:
            logger.warning(f"Failed to generate plot '{name}': {e}")

    # Scenario time plots (returns a list of paths, one per model)
    scenario_time_plots = []
    try:
        result = plot_time_per_scenario(summaries, media_dir)
        if result:
            scenario_time_plots = result
    except Exception as e:
        logger.warning(f"Failed to generate scenario time plots: {e}")

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
        # Sum individual prompt times (more reliable than summary total_time_s)
        total_processing_ms = sum(
            p["processing_time_ms"]
            for sc in s["scenarios"]
            for p in sc["prompts"]
            if p.get("success")
        )
        lines.append(
            f"| `{s['model']}` "
            f"| {total} "
            f"| {s['total_successes']} ({rate:.0f}%) "
            f"| {s['total_failures']} "
            f"| {s['avg_processing_time_ms'] / 1000:.1f}s "
            f"| {total_processing_ms / 1000:.1f}s |"
        )
    lines.append("")

    # --- Per-category summary table ---
    cat_data = defaultdict(lambda: {"count": 0, "success": 0, "times": [], "lengths": []})
    for s in summaries:
        for sc in s["scenarios"]:
            for p in sc["prompts"]:
                cat = extract_category(p["file"])
                cat_data[cat]["count"] += 1
                if p["success"]:
                    cat_data[cat]["success"] += 1
                    cat_data[cat]["times"].append(p["processing_time_ms"] / 1000)
                    if p["response_chars"] > 0:
                        cat_data[cat]["lengths"].append(p["response_chars"])

    if len(cat_data) >= 2:
        lines.append("## Per-Category Statistics")
        lines.append("")
        lines.append("| Category | Prompts | Success | Avg Time (s) | Median Time (s) | Avg Length (chars) |")
        lines.append("|----------|---------|---------|-------------|----------------|-------------------|")
        for cat in sorted(cat_data.keys()):
            d = cat_data[cat]
            rate = (d["success"] / d["count"] * 100) if d["count"] > 0 else 0
            avg_t = sum(d["times"]) / len(d["times"]) if d["times"] else 0
            med_t = sorted(d["times"])[len(d["times"]) // 2] if d["times"] else 0
            avg_l = sum(d["lengths"]) / len(d["lengths"]) if d["lengths"] else 0
            lines.append(
                f"| {cat} | {d['count']} | {d['success']} ({rate:.0f}%) "
                f"| {avg_t:.1f} | {med_t:.1f} | {avg_l:.0f} |"
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
        "prompt_counts": ("Dataset: Prompts by Category", "Number of prompts per intent category in the dataset."),
        "avg_time": ("Average Response Time", "Average time the model takes to respond to a single prompt."),
        "total_time": ("Total Run Time", "Wall-clock time for each model to complete all scenarios."),
        "success": ("Success / Failure Rate", "Number of successful vs failed prompts per model."),
        "time_dist": ("Response Time Distribution", "Spread of individual response times per model."),
        "time_by_cat_box": ("Response Time by Category", "How response time varies across intent categories (box plot showing median, quartiles, outliers)."),
        "cat_time": ("Average Response Time by Category", "Average response time per category, compared across models."),
        "cat_success": ("Success Rate by Category", "Success rate broken down by prompt category (help, injection, etc.)."),
        "resp_length": ("Response Length", "Average character count of model responses."),
        "length_by_cat": ("Response Length by Category", "How response length varies across intent categories (box plot)."),
        "assignment_compare": ("Assignment Time Comparison", "Top-5 most variable assignments compared across all models (Cleveland dot plot)."),
        "assignment_quality": ("Assignment Quality Comparison", "Top-5 most variable assignments by quality score across all models (Cleveland dot plot)."),
        "scenario_time": ("Time per Scenario", "Processing time per scenario (one chart per model)."),
        "scores_model": ("Evaluation Scores per Model", "Average LLM-judged scores per metric for each model."),
        "metric_heatmap": ("Score Matrix", "Full model x metric score matrix at a glance."),
        "radar": ("Model Metric Profiles", "Radar chart showing each model's strengths and weaknesses across all metrics."),
        "metric_boxplots": ("Per-Metric Score Distribution", "Score spread per metric per model — how consistent is each model?"),
        "scores_category": ("Scores by Prompt Category", "Heatmap of average overall score per model and prompt category."),
        "cat_score_compare": ("Category Score Comparison", "Overall quality score per category, compared across models."),
        "scores_dist": ("Overall Score Distribution", "Spread of overall scores (averaged across metrics) per model."),
        "time_vs_quality": ("Response Time vs Quality", "Are slower models better? Each point is one model."),
        "length_vs_quality": ("Response Length vs Quality", "Do more verbose models score higher?"),
        "boundary_vs_help": ("Safety vs Helpfulness", "Trade-off: boundary adherence on adversarial prompts vs helpfulness on legitimate ones."),
        "text_style": ("Response Style", "How models differ in writing style: questions asked, code blocks used, sentence length."),
    }

    for name, filename in plots:
        title, desc = plot_sections.get(name, (name, ""))
        lines.append(f"## {title}")
        lines.append("")
        lines.append(desc)
        lines.append("")
        lines.append(f"![{title}]({media_rel}/{filename})")
        lines.append("")

    # --- Scenario time plots (one per model) ---
    if scenario_time_plots:
        title, desc = plot_sections["scenario_time"]
        lines.append(f"## {title}")
        lines.append("")
        lines.append(desc)
        lines.append("")
        for rel_path in scenario_time_plots:
            lines.append(f"![{title}]({media_rel}/{rel_path})")
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
