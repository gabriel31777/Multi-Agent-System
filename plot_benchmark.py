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


def plot_run_distributions(df: pd.DataFrame, output_dir: Path, dpi: int):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    sns.histplot(data=df, x="steps_executed", bins=20, color="#1f77b4", alpha=0.8, ax=axes[0])
    axes[0].set_title("Distribution of Steps", fontsize=10)

    sns.histplot(data=df, x="final_efficiency", bins=20, color="#2ca02c", alpha=0.8, ax=axes[1])
    axes[1].set_title("Distribution of Efficiency", fontsize=10)

    for ax in axes:
        ax.grid(True, alpha=0.2)
        ax.tick_params(labelsize=8)

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

    fig.suptitle(title, fontsize=14)
    fig.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def run_all_plots(df: pd.DataFrame, output_dir: Path, dpi: int, suffix: str):
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

    print("\nDone")


if __name__ == "__main__":
    sns.set_theme(style="whitegrid")
    main()
