"""Generate benchmark plots from headless run outputs.

Expected input files in the benchmark directory:
- benchmark_runs.csv
- benchmark_scenarios.csv
- benchmark_timeseries.csv (optional)
"""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

PARAM_KEYS = [
    "width",
    "height",
    "n_green_robots",
    "n_yellow_robots",
    "n_red_robots",
    "initial_green_waste",
    "initial_yellow_waste",
    "initial_red_waste",
    "max_steps",
]

MESSAGE_KIND_FIELDS = [
    "messages_handoff_ready",
    "messages_handoff_claim",
    "messages_target_claim",
    "messages_target_found",
    "messages_congestion_alert",
    "messages_zone_clear",
]

MODE_LABELS = {
    "with_comm": "With Communication",
    "no_comm": "No Communication",
}


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _to_int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _load_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def _run_is_ok(row: dict[str, str]) -> bool:
    return row.get("status", "") == "ok"


def _run_completed(row: dict[str, str]) -> bool:
    return _run_is_ok(row) and _to_int(row.get("completed", "0")) == 1


def _mode_of(row: dict[str, str]) -> str:
    mode = row.get("communication_mode", "with_comm")
    if mode not in MODE_LABELS:
        return "with_comm"
    return mode


def _mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return float("nan"), float("nan")
    array = np.array(values, dtype=float)
    return float(np.mean(array)), float(np.std(array))


def _group_mean_std(
    rows: list[dict[str, str]],
    group_key: str,
    metric_key: str,
    row_filter=None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        if row_filter is not None and not row_filter(row):
            continue
        x = _to_int(row.get(group_key, ""))
        y = _to_float(row.get(metric_key, ""))
        if x is None or math.isnan(y):
            continue
        grouped[x].append(y)

    if not grouped:
        return np.array([]), np.array([]), np.array([])

    xs = np.array(sorted(grouped.keys()), dtype=float)
    means = np.array([np.mean(grouped[int(x)]) for x in xs], dtype=float)
    stds = np.array([np.std(grouped[int(x)]) for x in xs], dtype=float)
    return xs, means, stds


def _style_axis(ax, title: str, xlabel: str, ylabel: str):
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)


def plot_run_distributions(runs_rows: list[dict[str, str]], output_dir: Path, dpi: int):
    ok_rows = [r for r in runs_rows if _run_is_ok(r)]
    if not ok_rows:
        return

    steps = np.array([_to_float(r["steps_executed"]) for r in ok_rows], dtype=float)
    efficiency = np.array([_to_float(r["final_efficiency"]) for r in ok_rows], dtype=float)
    distance = np.array([_to_float(r["final_total_distance"]) for r in ok_rows], dtype=float)
    elapsed = np.array([_to_float(r["elapsed_seconds"]) for r in ok_rows], dtype=float)

    completed_count = sum(1 for r in ok_rows if _run_completed(r))
    not_completed_count = len(ok_rows) - completed_count

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    axes[0, 0].hist(steps[~np.isnan(steps)], bins=30, color="#1f77b4", alpha=0.85)
    _style_axis(axes[0, 0], "Distribution of Steps", "steps_executed", "count")

    axes[0, 1].hist(efficiency[~np.isnan(efficiency)], bins=30, color="#2ca02c", alpha=0.85)
    _style_axis(axes[0, 1], "Distribution of Efficiency", "final_efficiency", "count")

    axes[1, 0].hist(distance[~np.isnan(distance)], bins=30, color="#ff7f0e", alpha=0.85)
    _style_axis(axes[1, 0], "Distribution of Distance", "final_total_distance", "count")

    axes[1, 1].pie(
        [completed_count, not_completed_count],
        labels=["completed", "not completed"],
        autopct="%1.1f%%",
        colors=["#2ca02c", "#d62728"],
        startangle=90,
    )
    axes[1, 1].set_title("Completion Ratio")

    fig.suptitle("Benchmark Run-Level KPIs", fontsize=14)
    fig.tight_layout()
    fig.savefig(output_dir / "run_level_distributions.png", dpi=dpi)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(elapsed[~np.isnan(elapsed)], bins=30, color="#9467bd", alpha=0.85)
    _style_axis(ax, "Runtime per Run", "elapsed_seconds", "count")
    fig.tight_layout()
    fig.savefig(output_dir / "runtime_distribution.png", dpi=dpi)
    plt.close(fig)


def plot_parameter_impact(
    runs_rows: list[dict[str, str]],
    metric_key: str,
    title: str,
    ylabel: str,
    output_path: Path,
    dpi: int,
    row_filter=None,
):
    fig, axes = plt.subplots(3, 3, figsize=(15, 11))
    axes_flat = axes.ravel()

    for idx, param in enumerate(PARAM_KEYS):
        ax = axes_flat[idx]
        xs, means, stds = _group_mean_std(runs_rows, param, metric_key, row_filter=row_filter)
        if len(xs) == 0:
            ax.text(0.5, 0.5, "no data", ha="center", va="center")
            _style_axis(ax, param, param, ylabel)
            continue

        ax.plot(xs, means, marker="o", linewidth=1.7, color="#1f77b4")
        lower = np.maximum(means - stds, 0.0)
        upper = means + stds
        ax.fill_between(xs, lower, upper, alpha=0.2, color="#1f77b4", label="mean +/- std")
        _style_axis(ax, f"{param}", param, ylabel)

    fig.suptitle(title, fontsize=14)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_scenario_frontier(
    scenario_rows: list[dict[str, str]],
    output_path: Path,
    dpi: int,
    top_n_labels: int = 15,
):
    valid = []
    for row in scenario_rows:
        steps_mean = _to_float(row.get("steps_mean", ""))
        efficiency_mean = _to_float(row.get("efficiency_mean", ""))
        completion_rate = _to_float(row.get("completion_rate", ""))
        if math.isnan(steps_mean) or math.isnan(efficiency_mean) or math.isnan(completion_rate):
            continue
        valid.append(row)

    if not valid:
        return

    xs = np.array([_to_float(r["steps_mean"]) for r in valid], dtype=float)
    ys = np.array([_to_float(r["efficiency_mean"]) for r in valid], dtype=float)
    colors = np.array([_to_float(r["completion_rate"]) for r in valid], dtype=float)

    fig, ax = plt.subplots(figsize=(11, 7))
    scatter = ax.scatter(
        xs,
        ys,
        c=colors,
        cmap="viridis",
        alpha=0.75,
        s=28,
        edgecolors="none",
    )
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("completion_rate")

    ranked = sorted(
        valid,
        key=lambda r: (
            -_to_float(r["completion_rate"]),
            _to_float(r["steps_mean"]),
            -_to_float(r["efficiency_mean"]),
        ),
    )
    for row in ranked[:top_n_labels]:
        x = _to_float(row["steps_mean"])
        y = _to_float(row["efficiency_mean"])
        scenario_id = row.get("scenario_id", "?")
        mode = _mode_of(row)
        mode_prefix = "C" if mode == "with_comm" else "N"
        ax.annotate(f"{mode_prefix}S{scenario_id}", (x, y), xytext=(5, 4), textcoords="offset points", fontsize=8)

    _style_axis(ax, "Scenario Frontier", "steps_mean (lower is better)", "efficiency_mean (higher is better)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    return float(np.quantile(np.array(values, dtype=float), q))


def plot_timeseries_trends(
    timeseries_path: Path,
    runs_rows: list[dict[str, str]],
    output_path: Path,
    dpi: int,
):
    if not timeseries_path.exists():
        return

    valid_run_ids: set[int] = set()
    for row in runs_rows:
        if not _run_is_ok(row):
            continue
        run_id = _to_int(row.get("run_id", ""))
        if run_id is not None:
            valid_run_ids.add(run_id)
    if not valid_run_ids:
        return

    remaining_by_step: dict[int, list[float]] = defaultdict(list)
    disposed_by_step: dict[int, list[float]] = defaultdict(list)

    with timeseries_path.open("r", encoding="utf-8", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            run_id = _to_int(row.get("run_id", ""))
            step = _to_int(row.get("step", ""))
            remaining = _to_float(row.get("remaining_waste", ""))
            disposed = _to_float(row.get("disposed_waste", ""))
            if run_id is None or step is None:
                continue
            if run_id not in valid_run_ids:
                continue
            if not math.isnan(remaining):
                remaining_by_step[step].append(remaining)
            if not math.isnan(disposed):
                disposed_by_step[step].append(disposed)

    if not remaining_by_step:
        return

    steps = np.array(sorted(remaining_by_step.keys()), dtype=float)
    rem_mean = np.array([np.mean(remaining_by_step[int(s)]) for s in steps], dtype=float)
    rem_q10 = np.array([_quantile(remaining_by_step[int(s)], 0.10) for s in steps], dtype=float)
    rem_q90 = np.array([_quantile(remaining_by_step[int(s)], 0.90) for s in steps], dtype=float)

    disp_mean = np.array([np.mean(disposed_by_step.get(int(s), [float("nan")])) for s in steps], dtype=float)
    disp_q10 = np.array([_quantile(disposed_by_step.get(int(s), []), 0.10) for s in steps], dtype=float)
    disp_q90 = np.array([_quantile(disposed_by_step.get(int(s), []), 0.90) for s in steps], dtype=float)

    fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True)

    axes[0].plot(steps, rem_mean, color="#d62728", linewidth=1.8, label="mean")
    axes[0].fill_between(steps, rem_q10, rem_q90, color="#d62728", alpha=0.2, label="p10-p90")
    _style_axis(axes[0], "Remaining Waste Over Time", "", "remaining_waste")
    axes[0].legend(loc="upper right")

    axes[1].plot(steps, disp_mean, color="#2ca02c", linewidth=1.8, label="mean")
    axes[1].fill_between(steps, disp_q10, disp_q90, color="#2ca02c", alpha=0.2, label="p10-p90")
    _style_axis(axes[1], "Disposed Waste Over Time", "step", "disposed_waste")
    axes[1].legend(loc="upper left")

    fig.suptitle("Benchmark Time Series Summary (run-level aggregation)", fontsize=14)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_communication_mode_comparison(
    runs_rows: list[dict[str, str]],
    output_path: Path,
    dpi: int,
):
    ok_rows = [r for r in runs_rows if _run_is_ok(r)]
    if not ok_rows:
        return

    modes = [mode for mode in MODE_LABELS if any(_mode_of(r) == mode for r in ok_rows)]
    if not modes:
        return

    steps_means, steps_stds = [], []
    eff_means, eff_stds = [], []
    msg_means, msg_stds = [], []
    completion_rates = []

    for mode in modes:
        mode_rows = [r for r in ok_rows if _mode_of(r) == mode]
        step_values = [_to_float(r.get("steps_executed", "")) for r in mode_rows]
        step_values = [v for v in step_values if not math.isnan(v)]
        eff_values = [_to_float(r.get("final_efficiency", "")) for r in mode_rows]
        eff_values = [v for v in eff_values if not math.isnan(v)]
        msg_values = [_to_float(r.get("messages_total", "")) for r in mode_rows]
        msg_values = [v for v in msg_values if not math.isnan(v)]
        completion = [_to_float(r.get("completed", "")) for r in mode_rows]
        completion = [v for v in completion if not math.isnan(v)]

        m, s = _mean_std(step_values)
        steps_means.append(m)
        steps_stds.append(s)
        m, s = _mean_std(eff_values)
        eff_means.append(m)
        eff_stds.append(s)
        m, s = _mean_std(msg_values)
        msg_means.append(m)
        msg_stds.append(s)
        completion_rates.append(float(np.mean(np.array(completion, dtype=float))) if completion else float("nan"))

    x = np.arange(len(modes))
    labels = [MODE_LABELS[m] for m in modes]

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes_flat = axes.ravel()

    axes_flat[0].bar(x, steps_means, yerr=steps_stds, color="#1f77b4", alpha=0.85, capsize=4)
    axes_flat[0].set_xticks(x, labels, rotation=10)
    _style_axis(axes_flat[0], "Steps Executed", "mode", "steps")

    axes_flat[1].bar(x, eff_means, yerr=eff_stds, color="#2ca02c", alpha=0.85, capsize=4)
    axes_flat[1].set_xticks(x, labels, rotation=10)
    _style_axis(axes_flat[1], "Final Efficiency", "mode", "efficiency")

    axes_flat[2].bar(x, completion_rates, color="#9467bd", alpha=0.85)
    axes_flat[2].set_xticks(x, labels, rotation=10)
    _style_axis(axes_flat[2], "Completion Rate", "mode", "rate")
    axes_flat[2].set_ylim(0, 1.0)

    axes_flat[3].bar(x, msg_means, yerr=msg_stds, color="#ff7f0e", alpha=0.85, capsize=4)
    axes_flat[3].set_xticks(x, labels, rotation=10)
    _style_axis(axes_flat[3], "Messages per Run", "mode", "messages_total")

    fig.suptitle("Communication Mode Comparison", fontsize=14)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_zone_clear_steps_by_mode(
    runs_rows: list[dict[str, str]],
    output_path: Path,
    dpi: int,
):
    ok_rows = [r for r in runs_rows if _run_is_ok(r)]
    if not ok_rows:
        return

    modes = [mode for mode in MODE_LABELS if any(_mode_of(r) == mode for r in ok_rows)]
    if not modes:
        return

    metrics = [
        ("zone_clear_step_green", "Green clear"),
        ("zone_clear_step_yellow", "Yellow clear"),
        ("zone_clear_step_red", "Red clear"),
    ]

    x = np.arange(len(metrics))
    width = 0.35 if len(modes) == 2 else 0.6

    fig, ax = plt.subplots(figsize=(11, 6))
    for idx, mode in enumerate(modes):
        mode_rows = [r for r in ok_rows if _mode_of(r) == mode]
        means = []
        for metric_key, _ in metrics:
            values = [_to_float(r.get(metric_key, "")) for r in mode_rows]
            values = [v for v in values if not math.isnan(v) and v >= 0]
            means.append(float(np.mean(values)) if values else float("nan"))
        offset = (idx - (len(modes) - 1) / 2.0) * width
        ax.bar(x + offset, means, width=width, label=MODE_LABELS.get(mode, mode), alpha=0.85)

    ax.set_xticks(x, [label for _, label in metrics])
    _style_axis(ax, "Steps Until Zone Clear", "zone", "step")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_message_kind_breakdown(
    runs_rows: list[dict[str, str]],
    output_path: Path,
    dpi: int,
):
    ok_rows = [r for r in runs_rows if _run_is_ok(r)]
    if not ok_rows:
        return

    modes = [mode for mode in MODE_LABELS if any(_mode_of(r) == mode for r in ok_rows)]
    if not modes:
        return

    x = np.arange(len(MESSAGE_KIND_FIELDS))
    width = 0.35 if len(modes) == 2 else 0.6

    fig, ax = plt.subplots(figsize=(13, 6))
    for idx, mode in enumerate(modes):
        mode_rows = [r for r in ok_rows if _mode_of(r) == mode]
        means = []
        for field in MESSAGE_KIND_FIELDS:
            values = [_to_float(r.get(field, "")) for r in mode_rows]
            values = [v for v in values if not math.isnan(v)]
            means.append(float(np.mean(values)) if values else 0.0)
        offset = (idx - (len(modes) - 1) / 2.0) * width
        ax.bar(x + offset, means, width=width, label=MODE_LABELS.get(mode, mode), alpha=0.85)

    labels = [field.replace("messages_", "") for field in MESSAGE_KIND_FIELDS]
    ax.set_xticks(x, labels, rotation=20)
    _style_axis(ax, "Mean Message Count by Kind", "message kind", "messages per run")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate plots from benchmark CSV outputs.")
    parser.add_argument(
        "--input-dir",
        default="benchmark_results",
        help="Directory containing benchmark CSV files.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to save figures. Default: <input-dir>/plots",
    )
    parser.add_argument("--dpi", type=int, default=140, help="PNG dpi.")
    parser.add_argument(
        "--top-scenario-labels",
        type=int,
        default=15,
        help="How many top scenarios to annotate in frontier plot.",
    )
    parser.add_argument(
        "--skip-timeseries",
        action="store_true",
        help="Skip plots that depend on benchmark_timeseries.csv.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir) if args.output_dir else input_dir / "plots"
    output_dir.mkdir(parents=True, exist_ok=True)

    runs_path = input_dir / "benchmark_runs.csv"
    scenarios_path = input_dir / "benchmark_scenarios.csv"
    timeseries_path = input_dir / "benchmark_timeseries.csv"

    if not runs_path.exists():
        raise FileNotFoundError(f"Missing file: {runs_path}")
    if not scenarios_path.exists():
        raise FileNotFoundError(f"Missing file: {scenarios_path}")

    runs_rows = _load_csv_rows(runs_path)
    scenario_rows = _load_csv_rows(scenarios_path)

    plot_run_distributions(runs_rows, output_dir, dpi=args.dpi)

    plot_parameter_impact(
        runs_rows,
        metric_key="completed",
        title="Parameter Impact on Completion Rate (run-level mean)",
        ylabel="completion_rate",
        output_path=output_dir / "parameter_impact_completion.png",
        dpi=args.dpi,
        row_filter=_run_is_ok,
    )
    plot_parameter_impact(
        runs_rows,
        metric_key="steps_executed",
        title="Parameter Impact on Steps (run-level mean)",
        ylabel="steps_executed",
        output_path=output_dir / "parameter_impact_steps.png",
        dpi=args.dpi,
        row_filter=_run_is_ok,
    )
    plot_parameter_impact(
        runs_rows,
        metric_key="final_efficiency",
        title="Parameter Impact on Efficiency (run-level mean)",
        ylabel="final_efficiency",
        output_path=output_dir / "parameter_impact_efficiency.png",
        dpi=args.dpi,
        row_filter=_run_is_ok,
    )

    plot_scenario_frontier(
        scenario_rows,
        output_path=output_dir / "scenario_frontier.png",
        dpi=args.dpi,
        top_n_labels=args.top_scenario_labels,
    )

    if not args.skip_timeseries:
        plot_timeseries_trends(
            timeseries_path=timeseries_path,
            runs_rows=runs_rows,
            output_path=output_dir / "timeseries_summary.png",
            dpi=args.dpi,
        )

    plot_communication_mode_comparison(
        runs_rows=runs_rows,
        output_path=output_dir / "communication_mode_comparison.png",
        dpi=args.dpi,
    )
    plot_zone_clear_steps_by_mode(
        runs_rows=runs_rows,
        output_path=output_dir / "zone_clear_steps_comparison.png",
        dpi=args.dpi,
    )
    plot_message_kind_breakdown(
        runs_rows=runs_rows,
        output_path=output_dir / "message_kind_breakdown.png",
        dpi=args.dpi,
    )

    generated_files = sorted(p.name for p in output_dir.glob("*.png"))
    print(f"Generated {len(generated_files)} plot(s) in: {output_dir.resolve()}")
    for name in generated_files:
        print(f"- {name}")


if __name__ == "__main__":
    main()
