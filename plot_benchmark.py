"""Generate benchmark plots for Robot Mission experiments.

Supports:
- Global plots over all successful runs
- Optional grouped plots per `max_steps`
- Communication comparison plots (`with_comm` vs `no_comm`) when columns exist
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
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


def _has_cols(df: pd.DataFrame, cols: list[str]) -> bool:
    return all(col in df.columns for col in cols)


def _available_modes(df: pd.DataFrame) -> list[str]:
    if "communication_mode" not in df.columns:
        return []
    observed = set(df["communication_mode"].dropna().astype(str).tolist())
    return [mode for mode in MODE_LABELS if mode in observed]


def _paired_runs_by_mode(runs_df: pd.DataFrame) -> pd.DataFrame:
    required = ["communication_mode", "steps_executed", "final_efficiency", "completed"]
    if not _has_cols(runs_df, required):
        return pd.DataFrame()

    modes = _available_modes(runs_df)
    if "with_comm" not in modes or "no_comm" not in modes:
        return pd.DataFrame()

    key_candidates = [
        "scenario_id",
        "repetition",
        "seed",
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
    merge_keys = [
        key
        for key in key_candidates
        if key in runs_df.columns and runs_df[key].notna().any()
    ]
    if not merge_keys:
        return pd.DataFrame()

    value_fields = [
        "steps_executed",
        "final_efficiency",
        "completed",
        "messages_total",
        *MESSAGE_KIND_FIELDS,
    ]
    value_fields = [field for field in value_fields if field in runs_df.columns]

    with_df = runs_df[runs_df["communication_mode"] == "with_comm"][merge_keys + value_fields].copy()
    no_df = runs_df[runs_df["communication_mode"] == "no_comm"][merge_keys + value_fields].copy()
    if with_df.empty or no_df.empty:
        return pd.DataFrame()

    with_df = with_df.rename(columns={col: f"{col}_with_comm" for col in value_fields})
    no_df = no_df.rename(columns={col: f"{col}_no_comm" for col in value_fields})
    paired = with_df.merge(no_df, on=merge_keys, how="inner")
    if paired.empty:
        return pd.DataFrame()

    paired["steps_executed_with_comm"] = pd.to_numeric(paired["steps_executed_with_comm"], errors="coerce")
    paired["steps_executed_no_comm"] = pd.to_numeric(paired["steps_executed_no_comm"], errors="coerce")
    paired["final_efficiency_with_comm"] = pd.to_numeric(paired["final_efficiency_with_comm"], errors="coerce")
    paired["final_efficiency_no_comm"] = pd.to_numeric(paired["final_efficiency_no_comm"], errors="coerce")
    paired["completed_with_comm"] = pd.to_numeric(paired["completed_with_comm"], errors="coerce")
    paired["completed_no_comm"] = pd.to_numeric(paired["completed_no_comm"], errors="coerce")

    paired["steps_delta"] = paired["steps_executed_no_comm"] - paired["steps_executed_with_comm"]
    paired["efficiency_delta"] = paired["final_efficiency_with_comm"] - paired["final_efficiency_no_comm"]
    paired["completion_delta"] = paired["completed_with_comm"] - paired["completed_no_comm"]
    no_steps = paired["steps_executed_no_comm"].replace(0, np.nan)
    paired["steps_reduction_pct"] = 100.0 * paired["steps_delta"] / no_steps

    if _has_cols(paired, ["initial_green_waste", "initial_yellow_waste", "initial_red_waste"]):
        paired["total_initial_waste"] = (
            pd.to_numeric(paired["initial_green_waste"], errors="coerce")
            + pd.to_numeric(paired["initial_yellow_waste"], errors="coerce")
            + pd.to_numeric(paired["initial_red_waste"], errors="coerce")
        )
    if _has_cols(paired, ["n_green_robots", "n_yellow_robots", "n_red_robots"]):
        paired["total_robots"] = (
            pd.to_numeric(paired["n_green_robots"], errors="coerce")
            + pd.to_numeric(paired["n_yellow_robots"], errors="coerce")
            + pd.to_numeric(paired["n_red_robots"], errors="coerce")
        )

    return paired


def _style_axis(ax, title: str, xlabel: str, ylabel: str):
    ax.set_title(title, fontsize=11)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.25)


def _set_xticks_with_labels(ax, ticks, labels, rotation: int = 0):
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=rotation)


def _save(fig, output_path: Path, dpi: int):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _alias_plot(source_path: Path, alias_path: Path):
    if source_path.exists():
        alias_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, alias_path)


def plot_run_distributions(df: pd.DataFrame, output_dir: Path, dpi: int, suffix: str = ""):
    required = ["steps_executed", "final_efficiency", "final_total_distance", "completed"]
    if not _has_cols(df, required):
        return
    if df.empty:
        return

    steps = pd.to_numeric(df["steps_executed"], errors="coerce").dropna()
    efficiency = pd.to_numeric(df["final_efficiency"], errors="coerce").dropna()
    distance = pd.to_numeric(df["final_total_distance"], errors="coerce").dropna()
    completed = pd.to_numeric(df["completed"], errors="coerce")

    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    axes[0, 0].hist(steps, bins=30, color="#1f77b4", alpha=0.85)
    _style_axis(axes[0, 0], f"Distribution of Steps{suffix}", "steps_executed", "count")

    axes[0, 1].hist(efficiency, bins=30, color="#2ca02c", alpha=0.85)
    _style_axis(axes[0, 1], f"Distribution of Efficiency{suffix}", "final_efficiency", "count")

    axes[1, 0].hist(distance, bins=30, color="#ff7f0e", alpha=0.85)
    _style_axis(axes[1, 0], f"Distribution of Distance{suffix}", "final_total_distance", "count")

    completed_count = int((completed == 1).sum())
    not_completed_count = int((completed == 0).sum())
    axes[1, 1].pie(
        [completed_count, not_completed_count],
        labels=["completed", "not completed"],
        autopct="%1.1f%%",
        colors=["#2ca02c", "#d62728"],
        startangle=90,
    )
    axes[1, 1].set_title(f"Completion Ratio{suffix}")

    fig.suptitle("Benchmark Run-Level KPIs", fontsize=14)
    _save(fig, output_dir / "run_level_distributions.png", dpi=dpi)


def plot_runtime_distribution(df: pd.DataFrame, output_dir: Path, dpi: int, suffix: str = ""):
    if "elapsed_seconds" not in df.columns or df.empty:
        return
    elapsed = pd.to_numeric(df["elapsed_seconds"], errors="coerce").dropna()
    if elapsed.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(elapsed, bins=30, color="#9467bd", alpha=0.85)
    _style_axis(ax, f"Runtime per Run{suffix}", "elapsed_seconds", "count")
    _save(fig, output_dir / "runtime_distribution.png", dpi=dpi)


def plot_parameter_impact(
    df: pd.DataFrame,
    metric_key: str,
    title: str,
    ylabel: str,
    output_path: Path,
    dpi: int,
):
    if metric_key not in df.columns:
        return

    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    axes_flat = axes.ravel()

    for idx, param in enumerate(PARAM_IMPACT_KEYS):
        ax = axes_flat[idx]
        if param not in df.columns:
            ax.text(0.5, 0.5, "missing", ha="center", va="center")
            _style_axis(ax, param, param, ylabel)
            continue

        plot_df = pd.DataFrame(
            {
                param: pd.to_numeric(df[param], errors="coerce"),
                metric_key: pd.to_numeric(df[metric_key], errors="coerce"),
            }
        ).dropna()
        if plot_df.empty:
            ax.text(0.5, 0.5, "no data", ha="center", va="center")
            _style_axis(ax, param, param, ylabel)
            continue

        sns.lineplot(
            data=plot_df,
            x=param,
            y=metric_key,
            estimator="mean",
            errorbar="sd",
            marker="o",
            linewidth=1.5,
            color="#1f77b4",
            ax=ax,
        )
        _style_axis(ax, f"Impact of {param}", param, ylabel)
        ax.tick_params(labelsize=8)
        if metric_key == "completed":
            ax.set_ylim(0, 1)
        else:
            ax.set_ylim(bottom=0)

    fig.suptitle(title, fontsize=14)
    _save(fig, output_path, dpi=dpi)


def plot_proportion_successful_runs(df: pd.DataFrame, output_dir: Path, dpi: int, suffix: str = ""):
    if "completed" not in df.columns or df.empty:
        return
    completed = pd.to_numeric(df["completed"], errors="coerce")
    completed_count = int((completed == 1).sum())
    not_completed_count = int((completed == 0).sum())

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.pie(
        [completed_count, not_completed_count],
        labels=["all waste collected", "not all waste collected"],
        autopct="%1.1f%%",
        startangle=90,
    )
    ax.set_title(f"Proportion of Successful Runs{suffix}", fontsize=11)
    _save(fig, output_dir / "proportion_successful_collection.png", dpi=dpi)


def plot_scenario_frontier(
    scenario_df: pd.DataFrame,
    output_path: Path,
    dpi: int,
    top_n_labels: int = 15,
):
    required = ["steps_mean", "efficiency_mean", "completion_rate", "scenario_id"]
    if not _has_cols(scenario_df, required):
        return

    valid = scenario_df.dropna(subset=["steps_mean", "efficiency_mean", "completion_rate"])
    if valid.empty:
        return

    fig, ax = plt.subplots(figsize=(11, 7))
    scatter = ax.scatter(
        valid["steps_mean"],
        valid["efficiency_mean"],
        c=valid["completion_rate"],
        cmap="viridis",
        alpha=0.75,
        s=28,
        edgecolors="none",
    )
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("completion_rate")

    ranked = valid.sort_values(
        by=["completion_rate", "steps_mean", "efficiency_mean"],
        ascending=[False, True, False],
    ).head(top_n_labels)

    for _, row in ranked.iterrows():
        scenario_id = row.get("scenario_id", "?")
        mode = row.get("communication_mode", "with_comm")
        mode_prefix = "C" if mode == "with_comm" else "N"
        ax.annotate(
            f"{mode_prefix}S{scenario_id}",
            (row["steps_mean"], row["efficiency_mean"]),
            xytext=(5, 4),
            textcoords="offset points",
            fontsize=8,
        )

    _style_axis(ax, "Scenario Frontier", "steps_mean (lower is better)", "efficiency_mean (higher is better)")
    _save(fig, output_path, dpi=dpi)


def plot_timeseries_trends(
    timeseries_df: pd.DataFrame,
    runs_df: pd.DataFrame,
    output_path: Path,
    dpi: int,
):
    required_ts = ["run_id", "step", "remaining_waste", "disposed_waste"]
    if not _has_cols(timeseries_df, required_ts):
        return
    if "run_id" not in runs_df.columns:
        return

    valid_run_ids = set(pd.to_numeric(runs_df["run_id"], errors="coerce").dropna().astype(int).tolist())
    ts = timeseries_df.copy()
    ts["run_id"] = pd.to_numeric(ts["run_id"], errors="coerce")
    ts = ts[ts["run_id"].isin(valid_run_ids)].copy()
    ts["step"] = pd.to_numeric(ts["step"], errors="coerce")
    ts["remaining_waste"] = pd.to_numeric(ts["remaining_waste"], errors="coerce")
    ts["disposed_waste"] = pd.to_numeric(ts["disposed_waste"], errors="coerce")
    ts = ts.dropna(subset=["step", "remaining_waste", "disposed_waste"])
    if ts.empty:
        return

    grouped = ts.groupby("step")
    rem_mean = grouped["remaining_waste"].mean()
    rem_q10 = grouped["remaining_waste"].quantile(0.10)
    rem_q90 = grouped["remaining_waste"].quantile(0.90)
    disp_mean = grouped["disposed_waste"].mean()
    disp_q10 = grouped["disposed_waste"].quantile(0.10)
    disp_q90 = grouped["disposed_waste"].quantile(0.90)

    fig, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=True)
    steps = rem_mean.index.to_numpy(dtype=float)

    axes[0].plot(steps, rem_mean.to_numpy(), color="#d62728", linewidth=1.8, label="mean")
    axes[0].fill_between(steps, rem_q10.to_numpy(), rem_q90.to_numpy(), color="#d62728", alpha=0.2, label="p10-p90")
    _style_axis(axes[0], "Remaining Waste Over Time", "", "remaining_waste")
    axes[0].legend(loc="upper right")

    axes[1].plot(steps, disp_mean.to_numpy(), color="#2ca02c", linewidth=1.8, label="mean")
    axes[1].fill_between(steps, disp_q10.to_numpy(), disp_q90.to_numpy(), color="#2ca02c", alpha=0.2, label="p10-p90")
    _style_axis(axes[1], "Disposed Waste Over Time", "step", "disposed_waste")
    axes[1].legend(loc="upper left")

    fig.suptitle("Benchmark Time Series Summary", fontsize=14)
    _save(fig, output_path, dpi=dpi)


def plot_communication_mode_comparison(df: pd.DataFrame, output_path: Path, dpi: int):
    required = ["communication_mode", "steps_executed", "final_efficiency", "completed"]
    if not _has_cols(df, required):
        return
    if df.empty:
        return

    modes = [mode for mode in MODE_LABELS if mode in df["communication_mode"].unique()]
    if not modes:
        return

    steps_means, steps_stds = [], []
    eff_means, eff_stds = [], []
    msg_means, msg_stds = [], []
    completion_rates = []

    for mode in modes:
        mode_df = df[df["communication_mode"] == mode]
        steps = mode_df["steps_executed"].dropna().to_numpy(dtype=float)
        eff = mode_df["final_efficiency"].dropna().to_numpy(dtype=float)
        comp = mode_df["completed"].dropna().to_numpy(dtype=float)
        if "messages_total" in mode_df.columns:
            msgs = mode_df["messages_total"].dropna().to_numpy(dtype=float)
        else:
            msgs = np.zeros(len(mode_df), dtype=float)

        steps_means.append(float(np.mean(steps)) if len(steps) else float("nan"))
        steps_stds.append(float(np.std(steps)) if len(steps) else float("nan"))
        eff_means.append(float(np.mean(eff)) if len(eff) else float("nan"))
        eff_stds.append(float(np.std(eff)) if len(eff) else float("nan"))
        completion_rates.append(float(np.mean(comp)) if len(comp) else float("nan"))
        msg_means.append(float(np.mean(msgs)) if len(msgs) else float("nan"))
        msg_stds.append(float(np.std(msgs)) if len(msgs) else float("nan"))

    x = np.arange(len(modes))
    labels = [MODE_LABELS[m] for m in modes]

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes_flat = axes.ravel()

    axes_flat[0].bar(x, steps_means, yerr=steps_stds, color="#1f77b4", alpha=0.85, capsize=4)
    _set_xticks_with_labels(axes_flat[0], x, labels, rotation=10)
    _style_axis(axes_flat[0], "Steps Executed", "mode", "steps")

    axes_flat[1].bar(x, eff_means, yerr=eff_stds, color="#2ca02c", alpha=0.85, capsize=4)
    _set_xticks_with_labels(axes_flat[1], x, labels, rotation=10)
    _style_axis(axes_flat[1], "Final Efficiency", "mode", "efficiency")

    axes_flat[2].bar(x, completion_rates, color="#9467bd", alpha=0.85)
    _set_xticks_with_labels(axes_flat[2], x, labels, rotation=10)
    _style_axis(axes_flat[2], "Completion Rate", "mode", "rate")
    axes_flat[2].set_ylim(0, 1.0)

    axes_flat[3].bar(x, msg_means, yerr=msg_stds, color="#ff7f0e", alpha=0.85, capsize=4)
    _set_xticks_with_labels(axes_flat[3], x, labels, rotation=10)
    _style_axis(axes_flat[3], "Messages per Run", "mode", "messages_total")

    fig.suptitle("Communication Mode Comparison", fontsize=14)
    _save(fig, output_path, dpi=dpi)


def plot_zone_clear_steps_by_mode(df: pd.DataFrame, output_path: Path, dpi: int):
    required = ["communication_mode", "zone_clear_step_green", "zone_clear_step_yellow", "zone_clear_step_red"]
    if not _has_cols(df, required):
        return
    if df.empty:
        return

    modes = [mode for mode in MODE_LABELS if mode in df["communication_mode"].unique()]
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
        mode_df = df[df["communication_mode"] == mode]
        means = []
        for metric_key, _ in metrics:
            series = pd.to_numeric(mode_df[metric_key], errors="coerce")
            series = series[series >= 0]
            means.append(float(series.mean()) if not series.empty else float("nan"))
        offset = (idx - (len(modes) - 1) / 2.0) * width
        ax.bar(x + offset, means, width=width, label=MODE_LABELS.get(mode, mode), alpha=0.85)

    _set_xticks_with_labels(ax, x, [label for _, label in metrics], rotation=0)
    _style_axis(ax, "Steps Until Zone Clear", "zone", "step")
    ax.legend()
    _save(fig, output_path, dpi=dpi)


def plot_message_kind_breakdown(df: pd.DataFrame, output_path: Path, dpi: int):
    required = ["communication_mode"]
    if not _has_cols(df, required):
        return
    available_message_fields = [field for field in MESSAGE_KIND_FIELDS if field in df.columns]
    if not available_message_fields:
        return
    if df.empty:
        return

    modes = [mode for mode in MODE_LABELS if mode in df["communication_mode"].unique()]
    if not modes:
        return

    x = np.arange(len(available_message_fields))
    width = 0.35 if len(modes) == 2 else 0.6

    fig, ax = plt.subplots(figsize=(13, 6))
    for idx, mode in enumerate(modes):
        mode_df = df[df["communication_mode"] == mode]
        means = []
        for field in available_message_fields:
            series = pd.to_numeric(mode_df[field], errors="coerce").dropna()
            means.append(float(series.mean()) if not series.empty else 0.0)
        offset = (idx - (len(modes) - 1) / 2.0) * width
        ax.bar(x + offset, means, width=width, label=MODE_LABELS.get(mode, mode), alpha=0.85)

    labels = [field.replace("messages_", "") for field in available_message_fields]
    _set_xticks_with_labels(ax, x, labels, rotation=20)
    _style_axis(ax, "Mean Message Count by Kind", "message kind", "messages per run")
    ax.legend()
    _save(fig, output_path, dpi=dpi)


def plot_steps_ecdf_by_mode(df: pd.DataFrame, output_path: Path, dpi: int):
    required = ["communication_mode", "steps_executed"]
    if not _has_cols(df, required):
        return
    modes = _available_modes(df)
    if "with_comm" not in modes or "no_comm" not in modes:
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    for mode in ["with_comm", "no_comm"]:
        mode_df = df[df["communication_mode"] == mode].copy()
        mode_df["steps_executed"] = pd.to_numeric(mode_df["steps_executed"], errors="coerce")
        mode_df = mode_df.dropna(subset=["steps_executed"])
        if mode_df.empty:
            continue
        sns.ecdfplot(
            data=mode_df,
            x="steps_executed",
            label=MODE_LABELS.get(mode, mode),
            linewidth=2.0,
            ax=ax,
        )

    _style_axis(ax, "ECDF of Steps Executed", "steps_executed", "P(steps <= x)")
    ax.legend()
    _save(fig, output_path, dpi=dpi)


def plot_scenario_dumbbell_comparison(df: pd.DataFrame, output_path: Path, dpi: int, top_n: int = 20):
    paired = _paired_runs_by_mode(df)
    if paired.empty or "scenario_id" not in paired.columns:
        return

    scenario_summary = (
        paired.groupby("scenario_id", as_index=False)[
            [
                "steps_executed_no_comm",
                "steps_executed_with_comm",
                "final_efficiency_no_comm",
                "final_efficiency_with_comm",
                "completed_no_comm",
                "completed_with_comm",
                "steps_delta",
            ]
        ]
        .mean()
        .copy()
    )
    if scenario_summary.empty:
        return

    scenario_summary["abs_steps_delta"] = scenario_summary["steps_delta"].abs()
    focus = scenario_summary.sort_values("abs_steps_delta", ascending=False).head(top_n).copy()
    if focus.empty:
        return
    focus = focus.sort_values("steps_delta", ascending=True)
    focus["scenario_label"] = focus["scenario_id"].apply(lambda value: f"S{value}")

    y = np.arange(len(focus))
    fig, axes = plt.subplots(1, 3, figsize=(20, max(6, 0.35 * len(focus))))
    panels = [
        ("steps_executed_no_comm", "steps_executed_with_comm", "Steps", "steps"),
        ("final_efficiency_no_comm", "final_efficiency_with_comm", "Efficiency", "efficiency"),
        ("completed_no_comm", "completed_with_comm", "Completion", "rate"),
    ]

    for idx, (col_no, col_with, title, xlabel) in enumerate(panels):
        ax = axes[idx]
        ax.hlines(y, focus[col_no], focus[col_with], color="#777777", alpha=0.65, linewidth=1.2)
        ax.scatter(focus[col_no], y, color="#dd8452", s=35, label=MODE_LABELS["no_comm"])
        ax.scatter(focus[col_with], y, color="#4c72b0", s=35, label=MODE_LABELS["with_comm"])
        ax.set_yticks(y)
        if idx == 0:
            ax.set_yticklabels(focus["scenario_label"].tolist())
            ax.set_ylabel("scenario")
        else:
            ax.set_yticklabels([])
        _style_axis(ax, title, xlabel, "scenario")
        if title == "Completion":
            ax.set_xlim(-0.05, 1.05)

    handles, labels = axes[0].get_legend_handles_labels()
    unique = {}
    for handle, label in zip(handles, labels):
        unique[label] = handle
    fig.legend(unique.values(), unique.keys(), loc="upper center", ncol=2, frameon=False)
    fig.suptitle("Scenario-Level Dumbbell Comparison (No Comm vs With Comm)", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def plot_step_gain_heatmap(df: pd.DataFrame, output_path: Path, dpi: int):
    paired = _paired_runs_by_mode(df)
    if paired.empty:
        return
    if "steps_reduction_pct" not in paired.columns:
        return

    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    rendered = 0

    if _has_cols(paired, ["total_initial_waste", "max_steps"]):
        data = paired[["total_initial_waste", "max_steps", "steps_reduction_pct"]].copy()
        data["total_initial_waste"] = pd.to_numeric(data["total_initial_waste"], errors="coerce")
        data["max_steps"] = pd.to_numeric(data["max_steps"], errors="coerce")
        data = data.dropna()
        if not data.empty:
            pivot = pd.pivot_table(
                data,
                values="steps_reduction_pct",
                index="total_initial_waste",
                columns="max_steps",
                aggfunc="mean",
            )
            sns.heatmap(pivot.sort_index(), cmap="RdYlGn", center=0, ax=axes[0], cbar_kws={"label": "% step reduction"})
            _style_axis(axes[0], "Gain (%) by Initial Waste x Max Steps", "max_steps", "total_initial_waste")
            rendered += 1

    if _has_cols(paired, ["total_initial_waste", "total_robots"]):
        data = paired[["total_initial_waste", "total_robots", "steps_reduction_pct"]].copy()
        data["total_initial_waste"] = pd.to_numeric(data["total_initial_waste"], errors="coerce")
        data["total_robots"] = pd.to_numeric(data["total_robots"], errors="coerce")
        data = data.dropna()
        if not data.empty:
            pivot = pd.pivot_table(
                data,
                values="steps_reduction_pct",
                index="total_initial_waste",
                columns="total_robots",
                aggfunc="mean",
            )
            sns.heatmap(pivot.sort_index(), cmap="RdYlGn", center=0, ax=axes[1], cbar_kws={"label": "% step reduction"})
            _style_axis(axes[1], "Gain (%) by Initial Waste x Robots", "total_robots", "total_initial_waste")
            rendered += 1

    if rendered == 0:
        plt.close(fig)
        return

    fig.suptitle("Communication Gain Heatmaps", fontsize=14)
    _save(fig, output_path, dpi=dpi)


def plot_timeseries_mode_comparison(timeseries_df: pd.DataFrame, runs_df: pd.DataFrame, output_path: Path, dpi: int):
    required_ts = ["run_id", "communication_mode", "step", "remaining_waste", "disposed_waste"]
    if not _has_cols(timeseries_df, required_ts):
        return
    if not _has_cols(runs_df, ["run_id", "communication_mode"]):
        return
    modes = _available_modes(runs_df)
    if "with_comm" not in modes or "no_comm" not in modes:
        return

    valid_runs = runs_df[["run_id", "communication_mode"]].copy()
    valid_runs["run_id"] = pd.to_numeric(valid_runs["run_id"], errors="coerce")
    valid_runs = valid_runs.dropna(subset=["run_id"])
    valid_runs["run_id"] = valid_runs["run_id"].astype(int)

    ts = timeseries_df.copy()
    ts["run_id"] = pd.to_numeric(ts["run_id"], errors="coerce")
    ts["step"] = pd.to_numeric(ts["step"], errors="coerce")
    ts["remaining_waste"] = pd.to_numeric(ts["remaining_waste"], errors="coerce")
    ts["disposed_waste"] = pd.to_numeric(ts["disposed_waste"], errors="coerce")
    ts = ts.dropna(subset=["run_id", "step", "remaining_waste", "disposed_waste"])
    ts["run_id"] = ts["run_id"].astype(int)

    ts = ts.merge(valid_runs, on="run_id", how="inner", suffixes=("", "_run"))
    if ts.empty:
        return

    fig, axes = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    metrics = [("remaining_waste", "Remaining Waste"), ("disposed_waste", "Disposed Waste")]

    for ax, (metric, metric_label) in zip(axes, metrics):
        for mode in ["with_comm", "no_comm"]:
            mode_ts = ts[ts["communication_mode_run"] == mode]
            if mode_ts.empty:
                continue
            grouped = mode_ts.groupby("step")[metric]
            mean = grouped.mean()
            q10 = grouped.quantile(0.10)
            q90 = grouped.quantile(0.90)
            x = mean.index.to_numpy(dtype=float)
            y = mean.to_numpy(dtype=float)
            ax.plot(x, y, linewidth=2.0, label=f"{MODE_LABELS.get(mode, mode)} mean")
            ax.fill_between(
                x,
                q10.to_numpy(dtype=float),
                q90.to_numpy(dtype=float),
                alpha=0.18,
                label=f"{MODE_LABELS.get(mode, mode)} p10-p90",
            )

        _style_axis(ax, f"{metric_label} Over Time by Mode", "step", metric)
        ax.legend(loc="best", fontsize=8)

    fig.suptitle("Time Series Comparison by Communication Mode", fontsize=14)
    _save(fig, output_path, dpi=dpi)


def plot_completion_cdf_by_mode(df: pd.DataFrame, output_path: Path, dpi: int):
    required = ["communication_mode", "completed", "steps_executed"]
    if not _has_cols(df, required):
        return
    modes = _available_modes(df)
    if "with_comm" not in modes or "no_comm" not in modes:
        return

    fig, ax = plt.subplots(figsize=(10, 6))
    all_steps = pd.to_numeric(df["steps_executed"], errors="coerce").dropna()
    if all_steps.empty:
        plt.close(fig)
        return
    x_grid = np.sort(all_steps.unique())

    for mode in ["with_comm", "no_comm"]:
        mode_df = df[df["communication_mode"] == mode].copy()
        mode_df["steps_executed"] = pd.to_numeric(mode_df["steps_executed"], errors="coerce")
        mode_df["completed"] = pd.to_numeric(mode_df["completed"], errors="coerce")
        mode_df = mode_df.dropna(subset=["steps_executed", "completed"])
        if mode_df.empty:
            continue
        total_runs = float(len(mode_df))
        completed_steps = np.sort(mode_df.loc[mode_df["completed"] == 1, "steps_executed"].to_numpy(dtype=float))
        cumulative = np.searchsorted(completed_steps, x_grid, side="right") / total_runs
        ax.plot(x_grid, cumulative, linewidth=2.0, label=MODE_LABELS.get(mode, mode))

    _style_axis(ax, "P(Complete by step t)", "step t", "probability")
    ax.set_ylim(0, 1.02)
    ax.legend()
    _save(fig, output_path, dpi=dpi)


def plot_communication_cost_benefit(df: pd.DataFrame, output_path: Path, dpi: int):
    paired = _paired_runs_by_mode(df)
    if paired.empty or "messages_total_with_comm" not in paired.columns:
        return

    plot_df = paired[
        ["messages_total_with_comm", "steps_delta", "efficiency_delta", "steps_reduction_pct"]
    ].copy()
    plot_df["messages_total_with_comm"] = pd.to_numeric(plot_df["messages_total_with_comm"], errors="coerce")
    plot_df = plot_df.dropna(subset=["messages_total_with_comm", "steps_delta", "efficiency_delta"])
    if plot_df.empty:
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    sns.scatterplot(
        data=plot_df,
        x="messages_total_with_comm",
        y="steps_delta",
        hue="steps_reduction_pct",
        palette="RdYlGn",
        alpha=0.65,
        ax=axes[0],
        legend=False,
    )
    sns.regplot(
        data=plot_df,
        x="messages_total_with_comm",
        y="steps_delta",
        scatter=False,
        color="#333333",
        line_kws={"linewidth": 1.5},
        ax=axes[0],
    )
    axes[0].axhline(0, color="#777777", linewidth=1.0, linestyle="--")
    _style_axis(axes[0], "Messages vs Step Gain", "messages_total (with_comm)", "steps_delta (no - with)")

    sns.scatterplot(
        data=plot_df,
        x="messages_total_with_comm",
        y="efficiency_delta",
        alpha=0.65,
        color="#4c72b0",
        ax=axes[1],
    )
    sns.regplot(
        data=plot_df,
        x="messages_total_with_comm",
        y="efficiency_delta",
        scatter=False,
        color="#333333",
        line_kws={"linewidth": 1.5},
        ax=axes[1],
    )
    axes[1].axhline(0, color="#777777", linewidth=1.0, linestyle="--")
    _style_axis(axes[1], "Messages vs Efficiency Gain", "messages_total (with_comm)", "efficiency_delta (with - no)")

    fig.suptitle("Communication Cost-Benefit", fontsize=14)
    _save(fig, output_path, dpi=dpi)


def plot_message_composition_vs_gain(df: pd.DataFrame, output_path: Path, dpi: int, top_n: int = 12):
    paired = _paired_runs_by_mode(df)
    if paired.empty or "scenario_id" not in paired.columns:
        return

    message_cols = [f"{field}_with_comm" for field in MESSAGE_KIND_FIELDS if f"{field}_with_comm" in paired.columns]
    if not message_cols:
        return

    group_cols = ["scenario_id", "steps_reduction_pct", *message_cols]
    summary = paired[group_cols].groupby("scenario_id", as_index=False).mean()
    if summary.empty:
        return

    summary["abs_gain"] = summary["steps_reduction_pct"].abs()
    summary = summary.sort_values("abs_gain", ascending=False).head(top_n).copy()
    if summary.empty:
        return

    summary = summary.sort_values("steps_reduction_pct", ascending=False)
    x = np.arange(len(summary))
    scenario_labels = summary["scenario_id"].apply(lambda value: f"S{value}").tolist()

    fig, ax = plt.subplots(figsize=(16, 7))
    bottom = np.zeros(len(summary), dtype=float)
    colors = sns.color_palette("tab20", n_colors=len(message_cols))

    for idx, col in enumerate(message_cols):
        values = pd.to_numeric(summary[col], errors="coerce").fillna(0).to_numpy(dtype=float)
        ax.bar(x, values, bottom=bottom, color=colors[idx], alpha=0.9, label=col.replace("messages_", "").replace("_with_comm", ""))
        bottom += values

    _set_xticks_with_labels(ax, x, scenario_labels, rotation=30)
    _style_axis(ax, "Message Composition by Scenario", "scenario", "messages per run (with_comm)")

    ax2 = ax.twinx()
    gain = pd.to_numeric(summary["steps_reduction_pct"], errors="coerce").to_numpy(dtype=float)
    ax2.plot(x, gain, color="#111111", marker="o", linewidth=1.8, label="steps_reduction_pct")
    ax2.axhline(0, color="#777777", linewidth=1.0, linestyle="--")
    ax2.set_ylabel("step reduction (%)")

    handles1, labels1 = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles1 + handles2, labels1 + labels2, loc="upper right", fontsize=8, ncol=2)

    fig.suptitle("Message Composition vs Communication Gain", fontsize=14)
    _save(fig, output_path, dpi=dpi)


def run_all_plots(
    runs_ok: pd.DataFrame,
    scenarios: pd.DataFrame,
    timeseries: pd.DataFrame | None,
    output_dir: Path,
    dpi: int,
    top_scenario_labels: int,
    skip_timeseries: bool,
    suffix: str = "",
):
    output_dir.mkdir(parents=True, exist_ok=True)

    plot_run_distributions(runs_ok, output_dir, dpi=dpi, suffix=suffix)
    _alias_plot(output_dir / "run_level_distributions.png", output_dir / "run_distributions.png")
    plot_runtime_distribution(runs_ok, output_dir, dpi=dpi, suffix=suffix)
    plot_proportion_successful_runs(runs_ok, output_dir, dpi=dpi, suffix=suffix)

    plot_parameter_impact(
        runs_ok,
        metric_key="completed",
        title=f"Parameter Impact on Completion Rate{suffix}",
        ylabel="completion_rate",
        output_path=output_dir / "parameter_impact_completion.png",
        dpi=dpi,
    )
    _alias_plot(output_dir / "parameter_impact_completion.png", output_dir / "impact_completion_rate.png")
    plot_parameter_impact(
        runs_ok,
        metric_key="steps_executed",
        title=f"Parameter Impact on Steps{suffix}",
        ylabel="steps_executed",
        output_path=output_dir / "parameter_impact_steps.png",
        dpi=dpi,
    )
    plot_parameter_impact(
        runs_ok,
        metric_key="final_efficiency",
        title=f"Parameter Impact on Efficiency{suffix}",
        ylabel="final_efficiency",
        output_path=output_dir / "parameter_impact_efficiency.png",
        dpi=dpi,
    )
    _alias_plot(output_dir / "parameter_impact_efficiency.png", output_dir / "impact_efficiency.png")
    plot_parameter_impact(
        runs_ok,
        metric_key="final_remaining_waste",
        title=f"Parameter Impact on Remaining Waste{suffix}",
        ylabel="final_remaining_waste",
        output_path=output_dir / "parameter_impact_remaining_waste.png",
        dpi=dpi,
    )
    _alias_plot(output_dir / "parameter_impact_remaining_waste.png", output_dir / "impact_remaining_waste.png")

    plot_scenario_frontier(
        scenarios,
        output_path=output_dir / "scenario_frontier.png",
        dpi=dpi,
        top_n_labels=top_scenario_labels,
    )

    if not skip_timeseries and timeseries is not None:
        plot_timeseries_trends(
            timeseries_df=timeseries,
            runs_df=runs_ok,
            output_path=output_dir / "timeseries_summary.png",
            dpi=dpi,
        )

    plot_communication_mode_comparison(
        runs_ok,
        output_path=output_dir / "communication_mode_comparison.png",
        dpi=dpi,
    )
    plot_zone_clear_steps_by_mode(
        runs_ok,
        output_path=output_dir / "zone_clear_steps_comparison.png",
        dpi=dpi,
    )
    plot_message_kind_breakdown(
        runs_ok,
        output_path=output_dir / "message_kind_breakdown.png",
        dpi=dpi,
    )
    plot_steps_ecdf_by_mode(
        runs_ok,
        output_path=output_dir / "steps_ecdf_by_mode.png",
        dpi=dpi,
    )
    plot_scenario_dumbbell_comparison(
        runs_ok,
        output_path=output_dir / "scenario_dumbbell_comparison.png",
        dpi=dpi,
    )
    plot_step_gain_heatmap(
        runs_ok,
        output_path=output_dir / "step_gain_heatmap.png",
        dpi=dpi,
    )
    plot_completion_cdf_by_mode(
        runs_ok,
        output_path=output_dir / "completion_cdf_by_mode.png",
        dpi=dpi,
    )
    plot_communication_cost_benefit(
        runs_ok,
        output_path=output_dir / "communication_cost_benefit.png",
        dpi=dpi,
    )
    plot_message_composition_vs_gain(
        runs_ok,
        output_path=output_dir / "message_composition_vs_gain.png",
        dpi=dpi,
    )
    if not skip_timeseries and timeseries is not None:
        plot_timeseries_mode_comparison(
            timeseries_df=timeseries,
            runs_df=runs_ok,
            output_path=output_dir / "timeseries_mode_comparison.png",
            dpi=dpi,
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate benchmark figures from CSV outputs.")
    parser.add_argument("--input-dir", default="benchmark_results", help="Directory containing benchmark CSV files.")
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
    parser.add_argument(
        "--no-group-by-max-steps",
        action="store_true",
        help="Disable per-max_steps subdirectories and generate only global plots.",
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

    runs_df = pd.read_csv(runs_path)
    scenarios_df = pd.read_csv(scenarios_path)
    if "status" in runs_df.columns:
        runs_ok = runs_df[runs_df["status"] == "ok"].copy()
    else:
        runs_ok = runs_df.copy()
    timeseries_df = None
    if not args.skip_timeseries and timeseries_path.exists():
        timeseries_df = pd.read_csv(timeseries_path)

    run_all_plots(
        runs_ok=runs_ok,
        scenarios=scenarios_df,
        timeseries=timeseries_df,
        output_dir=output_dir,
        dpi=args.dpi,
        top_scenario_labels=args.top_scenario_labels,
        skip_timeseries=args.skip_timeseries,
        suffix="",
    )

    if (not args.no_group_by_max_steps) and ("max_steps" in runs_ok.columns):
        max_steps_series = pd.to_numeric(runs_ok["max_steps"], errors="coerce")
        unique_max_steps = sorted(max_steps_series.dropna().unique())
        for max_steps_value in unique_max_steps:
            subset_runs = runs_ok[max_steps_series == max_steps_value].copy()
            if subset_runs.empty:
                continue
            subset_scenarios = scenarios_df
            if "max_steps" in scenarios_df.columns:
                subset_scenarios = scenarios_df[scenarios_df["max_steps"] == max_steps_value].copy()
            subset_output = output_dir / f"max_steps_{int(max_steps_value)}"
            run_all_plots(
                runs_ok=subset_runs,
                scenarios=subset_scenarios,
                timeseries=timeseries_df,
                output_dir=subset_output,
                dpi=args.dpi,
                top_scenario_labels=args.top_scenario_labels,
                skip_timeseries=args.skip_timeseries,
                suffix=f" (max_steps={int(max_steps_value)})",
            )

    generated_files = sorted(p.relative_to(output_dir) for p in output_dir.glob("**/*.png"))
    print(f"Generated {len(generated_files)} plot(s) in: {output_dir.resolve()}")
    for relative_path in generated_files:
        print(f"- {relative_path}")


if __name__ == "__main__":
    sns.set_theme(style="whitegrid")
    main()
