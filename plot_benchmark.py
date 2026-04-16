"""Grouped benchmark plotting for the robot mission using Pandas and Seaborn.

This script generates visualizations (Distributions and Parameter Impacts) 
grouped by 'max_steps'.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

PARAM_IMPACT_KEYS = [
    "width",
    "height",
    "n_green_robots",
    "n_yellow_robots",
    "n_red_robots",
    "initial_green_waste",
    "initial_yellow_waste",
    "initial_red_waste",
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


def plot_run_distributions(df: pd.DataFrame, output_dir: Path, dpi: int):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    sns.histplot(data=df, x="steps_executed", bins=20, color="#1f77b4", alpha=0.8, ax=axes[0])
    axes[0].set_title("Distribution of Steps", fontsize=10)

    sns.histplot(data=df, x="final_efficiency", bins=20, color="#2ca02c", alpha=0.8, ax=axes[1])
    axes[1].set_title("Distribution of Efficiency", fontsize=10)

    for ax in axes:
        ax.grid(True, alpha=0.2)
        ax.tick_params(labelsize=8)

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
    fig.savefig(output_dir / "run_distributions.png", dpi=dpi)
    plt.close(fig)


def plot_parameter_impact(
    df: pd.DataFrame,
    metric_key: str,
    title: str,
    ylabel: str,
    output_path: Path,
    dpi: int,
):
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    axes_flat = axes.ravel()

    for idx, param in enumerate(PARAM_IMPACT_KEYS):
        ax = axes_flat[idx]
        
        sns.lineplot(
            data=df, 
            x=param, 
            y=metric_key, 
            errorbar='sd', 
            marker="o", 
            linewidth=1.5, 
            color="#1f77b4", 
            ax=ax
        )
        
        ax.set_title(f"Impact of {param}", fontsize=10)
        ax.set_xlabel(param, fontsize=9)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.tick_params(labelsize=8)
        ax.grid(True, alpha=0.2)

        if metric_key == 'completed':
            ax.set_ylim(0, 1)
        else:
            ax.set_ylim(bottom=0)

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

def plot_proportion_sucessfull_runs(df: pd.DataFrame, output_dir: Path, dpi: int):

    fig, ax = plt.subplots()
    labels = ['all waste collected', 'not all waste collected']
    values = [(df['completed'] == 1).sum(), (df['completed'] == 0).sum()]
    ax.pie(values, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.set_title("Proportion of successful collection of all waste", fontsize=10)
    fig.savefig(output_dir / "proportion_successful_collection.png", dpi=dpi)
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
    
    plot_run_distributions(df, output_dir, dpi)

    plot_parameter_impact(
        df,
        metric_key="completed",
        title=f"Parameter Impact on Completion Rate{suffix}",
        ylabel="completion_rate",
        output_path=output_dir / "impact_completion_rate.png",
        dpi=dpi,
    )

    plot_parameter_impact(
        df,
        metric_key="final_efficiency",
        title=f"Parameter Impact on Efficiency{suffix}",
        ylabel="final_efficiency",
        output_path=output_dir / "impact_efficiency.png",
        dpi=dpi,
    )

    plot_parameter_impact(
        df,
        metric_key="final_remaining_waste",
        title=f"Parameter Impact on Remaining Waste{suffix}",
        ylabel="final_remaining_waste",
        output_path=output_dir / "impact_remaining_waste.png",
        dpi=dpi,
    )

    plot_proportion_sucessfull_runs(df, output_dir, dpi)



def main():
    parser = argparse.ArgumentParser(description="Grouped benchmark plotting using Pandas/Seaborn.")
    parser.add_argument("--input-dir", default="benchmark_results", help="Input directory.")
    parser.add_argument("--output-dir", default=None, help="Root for plots.")
    parser.add_argument("--dpi", type=int, default=140, help="Resolution.")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    root_output = Path(args.output_dir) if args.output_dir else input_dir / "plots"
    
    runs_path = input_dir / "benchmark_runs.csv"
    df = pd.read_csv(runs_path)
    df = df[df['status'] == 'ok']
    
    unique_max_steps = sorted(df['max_steps'].dropna().unique())

    for ms in unique_max_steps:
        ms_dir = root_output / f"max_steps_{ms}"
        print(f"Generating plots for duration={ms} steps in: {ms_dir}")
        subset = df[df['max_steps'] == ms]
        run_all_plots(subset, ms_dir, args.dpi, suffix=f" (max_steps={ms})")

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
    sns.set_theme(style="whitegrid")
    main()
