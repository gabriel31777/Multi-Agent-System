"""Headless runner and benchmark CLI for the robot mission.

Group number: 22
Creation date: 2026-03-18
Members:
    - Gabriel Anjos Moura
    - Vinicius da Mata e Mota
    - Nicholas Oliveira Rodrigues Braganca
"""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import time
from pathlib import Path
from statistics import mean, pstdev

try:
    from .config import DEFAULT_PARAMS
    from .model import RobotMissionModel
except ImportError:
    from config import DEFAULT_PARAMS
    from model import RobotMissionModel

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

MODEL_METRIC_COLUMNS = [
    "Green waste",
    "Yellow waste",
    "Red waste",
    "Disposed waste",
    "Remaining waste",
    "Total distance",
    "Efficiency",
    "Active robots",
    "Average cargo",
]

METRIC_COLUMN_TO_KEY = {
    "Green waste": "green_waste",
    "Yellow waste": "yellow_waste",
    "Red waste": "red_waste",
    "Disposed waste": "disposed_waste",
    "Remaining waste": "remaining_waste",
    "Total distance": "total_distance",
    "Efficiency": "efficiency",
    "Active robots": "active_robots",
    "Average cargo": "average_cargo",
}

COMMUNICATION_MODES = [
    ("with_comm", True),
    ("no_comm", False),
]

MESSAGE_PERFORMATIVE_KEYS = {
    "PROPOSE": "messages_propose",
    "COMMIT": "messages_commit",
    "INFORM_REF": "messages_inform_ref",
}

MESSAGE_KIND_KEYS = {
    "handoff_ready": "messages_handoff_ready",
    "handoff_claim": "messages_handoff_claim",
    "target_claim": "messages_target_claim",
    "target_found": "messages_target_found",
    "congestion_alert": "messages_congestion_alert",
    "zone_clear": "messages_zone_clear",
}


def _parse_csv_int_list(raw: str, label: str, min_value: int = 0) -> list[int]:
    values: list[int] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        try:
            number = int(token)
        except ValueError as exc:
            raise ValueError(f"Invalid integer in {label}: '{token}'") from exc
        if number < min_value:
            raise ValueError(f"{label} must be >= {min_value}. Invalid value: {number}")
        values.append(number)

    if not values:
        raise ValueError(f"{label} cannot be empty.")
    return values


def _build_single_params(args: argparse.Namespace) -> dict:
    return {
        "width": args.width,
        "height": args.height,
        "n_green_robots": args.n_green_robots,
        "n_yellow_robots": args.n_yellow_robots,
        "n_red_robots": args.n_red_robots,
        "initial_green_waste": args.initial_green_waste,
        "initial_yellow_waste": args.initial_yellow_waste,
        "initial_red_waste": args.initial_red_waste,
        "max_steps": args.max_steps,
        "enable_communication": not args.disable_communication,
    }


def _build_param_grid(args: argparse.Namespace) -> dict[str, list[int]]:
    return {
        "width": _parse_csv_int_list(args.widths, "widths", min_value=1),
        "height": _parse_csv_int_list(args.heights, "heights", min_value=1),
        "n_green_robots": _parse_csv_int_list(args.green_robots, "green_robots", min_value=0),
        "n_yellow_robots": _parse_csv_int_list(args.yellow_robots, "yellow_robots", min_value=0),
        "n_red_robots": _parse_csv_int_list(args.red_robots, "red_robots", min_value=0),
        "initial_green_waste": _parse_csv_int_list(args.green_waste, "green_waste", min_value=0),
        "initial_yellow_waste": _parse_csv_int_list(args.yellow_waste, "yellow_waste", min_value=0),
        "initial_red_waste": _parse_csv_int_list(args.red_waste, "red_waste", min_value=0),
        "max_steps": _parse_csv_int_list(args.max_steps_grid, "max_steps_grid", min_value=1),
    }


def _build_scenarios(param_grid: dict[str, list[int]]) -> list[dict]:
    keys = list(param_grid.keys())
    combinations = itertools.product(*(param_grid[k] for k in keys))
    return [dict(zip(keys, values)) for values in combinations]


def _get_last_metrics(model) -> dict:
    df = model.datacollector.get_model_vars_dataframe()
    if df.empty:
        return {
            "green_waste": model.count_waste("green"),
            "yellow_waste": model.count_waste("yellow"),
            "red_waste": model.count_waste("red"),
            "disposed_waste": model.disposed_waste,
            "remaining_waste": model.count_remaining_waste(),
            "total_distance": model.total_distance,
            "efficiency": model.efficiency(),
            "active_robots": model.count_robots(),
            "average_cargo": model.average_cargo(),
        }

    row = df.iloc[-1]
    return {METRIC_COLUMN_TO_KEY[column]: row[column] for column in MODEL_METRIC_COLUMNS}


def _run_once(params: dict, seed: int | None = None, collect_agent_data: bool = True):
    start_time = time.perf_counter()
    model = RobotMissionModel(seed=seed, collect_agent_data=collect_agent_data, **params)
    while model.running:
        model.step()
    elapsed_seconds = time.perf_counter() - start_time
    metrics = _get_last_metrics(model)
    completed = metrics["remaining_waste"] == 0
    terminated_by_max_steps = model.steps >= params["max_steps"] and not completed
    termination_reason = "max_steps" if terminated_by_max_steps else "all_waste_collected"
    return model, metrics, completed, termination_reason, elapsed_seconds


def _message_metrics(model) -> dict:
    result = {"messages_total": 0}
    for key in MESSAGE_PERFORMATIVE_KEYS.values():
        result[key] = 0
    for key in MESSAGE_KIND_KEYS.values():
        result[key] = 0

    service = getattr(model, "message_service", None)
    if service is None or not hasattr(service, "get_message_stats"):
        return result

    stats = service.get_message_stats() or {}
    result["messages_total"] = int(stats.get("total", 0))
    by_performative = stats.get("by_performative", {}) or {}
    by_kind = stats.get("by_kind", {}) or {}
    for perf_name, field in MESSAGE_PERFORMATIVE_KEYS.items():
        result[field] = int(by_performative.get(perf_name, 0))
    for kind_name, field in MESSAGE_KIND_KEYS.items():
        result[field] = int(by_kind.get(kind_name, 0))
    return result


def _zone_clear_metrics(model) -> dict:
    milestones = getattr(model, "zone_clear_steps", {}) or {}
    messages = getattr(model, "zone_clear_message_steps", {}) or {}

    def _fmt_step(raw):
        if raw is None:
            return -1
        try:
            return int(raw)
        except (TypeError, ValueError):
            return -1

    return {
        "zone_clear_step_green": _fmt_step(milestones.get("green")),
        "zone_clear_step_yellow": _fmt_step(milestones.get("yellow")),
        "zone_clear_step_red": _fmt_step(milestones.get("red")),
        "zone_clear_message_step_green": _fmt_step(messages.get("green")),
        "zone_clear_message_step_yellow": _fmt_step(messages.get("yellow")),
        "zone_clear_message_step_red": _fmt_step(messages.get("red")),
    }


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run_single(args: argparse.Namespace):
    params = _build_single_params(args)
    model, metrics, completed, termination_reason, elapsed_seconds = _run_once(
        params,
        seed=args.seed,
        collect_agent_data=True,
    )
    summary = {
        "status": "ok",
        "params": params,
        "seed": args.seed,
        "communication_mode": "no_comm" if args.disable_communication else "with_comm",
        "steps": model.steps,
        "termination_reason": termination_reason,
        "completed": completed,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "metrics": metrics,
        "message_metrics": _message_metrics(model),
        "zone_clear_metrics": _zone_clear_metrics(model),
    }
    print(json.dumps(summary, indent=2))


def _scenario_stats(
    rows: list[dict],
    metric_key: str,
    ignore_negative: bool = False,
) -> dict[str, float | int | None]:
    values = []
    for row in rows:
        try:
            value = float(row[metric_key])
        except (TypeError, ValueError):
            continue
        if ignore_negative and value < 0:
            continue
        values.append(value)
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None}
    std = pstdev(values) if len(values) > 1 else 0.0
    return {
        "mean": mean(values),
        "std": std,
        "min": min(values),
        "max": max(values),
    }


def run_benchmark(args: argparse.Namespace):
    if args.repetitions < 1:
        raise ValueError("repetitions must be >= 1")

    param_grid = _build_param_grid(args)
    scenarios = _build_scenarios(param_grid)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "benchmark_date_unix": int(time.time()),
        "repetitions": args.repetitions,
        "seed_base": args.seed_base,
        "total_scenarios": len(scenarios),
        "communication_modes": [mode for mode, _ in COMMUNICATION_MODES],
        "total_runs_planned": len(scenarios) * args.repetitions * len(COMMUNICATION_MODES),
        "param_grid": param_grid,
    }
    metadata_path = output_dir / "benchmark_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    run_rows: list[dict] = []
    scenario_rows: list[dict] = []

    total_runs = len(scenarios) * args.repetitions * len(COMMUNICATION_MODES)
    run_id = 0
    timeseries_writer = None
    timeseries_file = None
    if not args.skip_timeseries:
        timeseries_fieldnames = [
            "run_id",
            "scenario_id",
            "communication_mode",
            "enable_communication",
            "repetition",
            "seed",
            *PARAM_KEYS,
            "step",
            *(METRIC_COLUMN_TO_KEY[c] for c in MODEL_METRIC_COLUMNS),
        ]
        timeseries_file = (output_dir / "benchmark_timeseries.csv").open("w", newline="", encoding="utf-8")
        timeseries_writer = csv.DictWriter(timeseries_file, fieldnames=timeseries_fieldnames)
        timeseries_writer.writeheader()

    try:
        for scenario_id, params in enumerate(scenarios, start=1):
            scenario_run_rows: dict[str, list[dict]] = {mode: [] for mode, _ in COMMUNICATION_MODES}
            for repetition in range(1, args.repetitions + 1):
                base_seed = None
                if args.seed_base is not None:
                    seed_offset = (scenario_id - 1) * args.repetitions + (repetition - 1)
                    base_seed = args.seed_base + seed_offset

                for communication_mode, communication_enabled in COMMUNICATION_MODES:
                    run_id += 1
                    seed = base_seed
                    mode_params = dict(params)
                    mode_params["enable_communication"] = communication_enabled
                    if not args.quiet:
                        print(
                            f"[{run_id}/{total_runs}] scenario={scenario_id}/{len(scenarios)} "
                            f"mode={communication_mode} repetition={repetition} seed={seed} params={params}"
                        )

                    try:
                        model, metrics, completed, termination_reason, elapsed_seconds = _run_once(
                            mode_params,
                            seed=seed,
                            collect_agent_data=False,
                        )
                        run_row = {
                            "run_id": run_id,
                            "scenario_id": scenario_id,
                            "communication_mode": communication_mode,
                            "enable_communication": int(communication_enabled),
                            "repetition": repetition,
                            "seed": seed,
                            "status": "ok",
                            "error": "",
                            **params,
                            "steps_executed": model.steps,
                            "termination_reason": termination_reason,
                            "completed": int(completed),
                            "elapsed_seconds": elapsed_seconds,
                            "final_green_waste": metrics["green_waste"],
                            "final_yellow_waste": metrics["yellow_waste"],
                            "final_red_waste": metrics["red_waste"],
                            "final_disposed_waste": metrics["disposed_waste"],
                            "final_remaining_waste": metrics["remaining_waste"],
                            "final_total_distance": metrics["total_distance"],
                            "final_efficiency": metrics["efficiency"],
                            "final_active_robots": metrics["active_robots"],
                            "final_average_cargo": metrics["average_cargo"],
                            **_message_metrics(model),
                            **_zone_clear_metrics(model),
                        }
                        run_rows.append(run_row)
                        scenario_run_rows[communication_mode].append(run_row)

                        if timeseries_writer is not None:
                            df = model.datacollector.get_model_vars_dataframe()
                            for step, (_, metric_row) in enumerate(df.iterrows()):
                                timeseries_writer.writerow(
                                    {
                                        "run_id": run_id,
                                        "scenario_id": scenario_id,
                                        "communication_mode": communication_mode,
                                        "enable_communication": int(communication_enabled),
                                        "repetition": repetition,
                                        "seed": seed,
                                        **params,
                                        "step": step,
                                        **{
                                            METRIC_COLUMN_TO_KEY[column]: metric_row[column]
                                            for column in MODEL_METRIC_COLUMNS
                                        },
                                    }
                                )
                    except Exception as exc:
                        error_row = {
                            "run_id": run_id,
                            "scenario_id": scenario_id,
                            "communication_mode": communication_mode,
                            "enable_communication": int(communication_enabled),
                            "repetition": repetition,
                            "seed": seed,
                            "status": "error",
                            "error": str(exc),
                            **params,
                            "steps_executed": 0,
                            "termination_reason": "error",
                            "completed": 0,
                            "elapsed_seconds": 0.0,
                            "final_green_waste": "",
                            "final_yellow_waste": "",
                            "final_red_waste": "",
                            "final_disposed_waste": "",
                            "final_remaining_waste": "",
                            "final_total_distance": "",
                            "final_efficiency": "",
                            "final_active_robots": "",
                            "final_average_cargo": "",
                        }
                        error_row.update({field: "" for field in MESSAGE_PERFORMATIVE_KEYS.values()})
                        error_row.update({field: "" for field in MESSAGE_KIND_KEYS.values()})
                        error_row.update(
                            {
                                "messages_total": "",
                                "zone_clear_step_green": "",
                                "zone_clear_step_yellow": "",
                                "zone_clear_step_red": "",
                                "zone_clear_message_step_green": "",
                                "zone_clear_message_step_yellow": "",
                                "zone_clear_message_step_red": "",
                            }
                        )
                        run_rows.append(error_row)
                        scenario_run_rows[communication_mode].append(error_row)
                        if not args.quiet:
                            print(f"  -> ERROR in run {run_id}: {exc}")

            for communication_mode, communication_enabled in COMMUNICATION_MODES:
                successful = [row for row in scenario_run_rows[communication_mode] if row["status"] == "ok"]
                scenario_row = {
                    "scenario_id": scenario_id,
                    "communication_mode": communication_mode,
                    "enable_communication": int(communication_enabled),
                    **params,
                    "runs": args.repetitions,
                    "successful_runs": len(successful),
                    "completion_rate": (
                        sum(row["completed"] for row in successful) / len(successful) if successful else 0.0
                    ),
                }
                steps_stats = _scenario_stats(successful, "steps_executed")
                efficiency_stats = _scenario_stats(successful, "final_efficiency")
                distance_stats = _scenario_stats(successful, "final_total_distance")
                elapsed_stats = _scenario_stats(successful, "elapsed_seconds")
                message_stats = _scenario_stats(successful, "messages_total")
                green_clear_stats = _scenario_stats(successful, "zone_clear_step_green", ignore_negative=True)
                yellow_clear_stats = _scenario_stats(successful, "zone_clear_step_yellow", ignore_negative=True)
                red_clear_stats = _scenario_stats(successful, "zone_clear_step_red", ignore_negative=True)
                scenario_row.update(
                    {
                        "steps_mean": steps_stats["mean"],
                        "steps_std": steps_stats["std"],
                        "steps_min": steps_stats["min"],
                        "steps_max": steps_stats["max"],
                        "efficiency_mean": efficiency_stats["mean"],
                        "efficiency_std": efficiency_stats["std"],
                        "efficiency_min": efficiency_stats["min"],
                        "efficiency_max": efficiency_stats["max"],
                        "distance_mean": distance_stats["mean"],
                        "distance_std": distance_stats["std"],
                        "distance_min": distance_stats["min"],
                        "distance_max": distance_stats["max"],
                        "elapsed_mean_seconds": elapsed_stats["mean"],
                        "elapsed_std_seconds": elapsed_stats["std"],
                        "elapsed_min_seconds": elapsed_stats["min"],
                        "elapsed_max_seconds": elapsed_stats["max"],
                        "messages_total_mean": message_stats["mean"],
                        "messages_total_std": message_stats["std"],
                        "zone_clear_green_mean_step": green_clear_stats["mean"],
                        "zone_clear_green_std_step": green_clear_stats["std"],
                        "zone_clear_yellow_mean_step": yellow_clear_stats["mean"],
                        "zone_clear_yellow_std_step": yellow_clear_stats["std"],
                        "zone_clear_red_mean_step": red_clear_stats["mean"],
                        "zone_clear_red_std_step": red_clear_stats["std"],
                    }
                )
                scenario_rows.append(scenario_row)
    finally:
        if timeseries_file is not None:
            timeseries_file.close()

    run_fieldnames = [
        "run_id",
        "scenario_id",
        "communication_mode",
        "enable_communication",
        "repetition",
        "seed",
        "status",
        "error",
        *PARAM_KEYS,
        "steps_executed",
        "termination_reason",
        "completed",
        "elapsed_seconds",
        "final_green_waste",
        "final_yellow_waste",
        "final_red_waste",
        "final_disposed_waste",
        "final_remaining_waste",
        "final_total_distance",
        "final_efficiency",
        "final_active_robots",
        "final_average_cargo",
        "messages_total",
        *MESSAGE_PERFORMATIVE_KEYS.values(),
        *MESSAGE_KIND_KEYS.values(),
        "zone_clear_step_green",
        "zone_clear_step_yellow",
        "zone_clear_step_red",
        "zone_clear_message_step_green",
        "zone_clear_message_step_yellow",
        "zone_clear_message_step_red",
    ]
    _write_csv(output_dir / "benchmark_runs.csv", run_rows, run_fieldnames)

    scenario_fieldnames = [
        "scenario_id",
        "communication_mode",
        "enable_communication",
        *PARAM_KEYS,
        "runs",
        "successful_runs",
        "completion_rate",
        "steps_mean",
        "steps_std",
        "steps_min",
        "steps_max",
        "efficiency_mean",
        "efficiency_std",
        "efficiency_min",
        "efficiency_max",
        "distance_mean",
        "distance_std",
        "distance_min",
        "distance_max",
        "elapsed_mean_seconds",
        "elapsed_std_seconds",
        "elapsed_min_seconds",
        "elapsed_max_seconds",
        "messages_total_mean",
        "messages_total_std",
        "zone_clear_green_mean_step",
        "zone_clear_green_std_step",
        "zone_clear_yellow_mean_step",
        "zone_clear_yellow_std_step",
        "zone_clear_red_mean_step",
        "zone_clear_red_std_step",
    ]
    _write_csv(output_dir / "benchmark_scenarios.csv", scenario_rows, scenario_fieldnames)

    summary = {
        "status": "ok",
        "output_dir": str(output_dir.resolve()),
        "total_runs_planned": total_runs,
        "total_runs_executed": len(run_rows),
        "total_successful_runs": sum(1 for row in run_rows if row["status"] == "ok"),
        "timeseries_saved": not args.skip_timeseries,
    }
    print(json.dumps(summary, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a single headless simulation or a combinatorial benchmark sweep."
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Enable benchmark mode (multiple scenario combinations).",
    )
    parser.add_argument("--quiet", action="store_true", help="Suppress per-run logs in benchmark mode.")

    parser.add_argument("--width", type=int, default=DEFAULT_PARAMS["width"])
    parser.add_argument("--height", type=int, default=DEFAULT_PARAMS["height"])
    parser.add_argument("--n-green-robots", dest="n_green_robots", type=int, default=DEFAULT_PARAMS["n_green_robots"])
    parser.add_argument(
        "--n-yellow-robots",
        dest="n_yellow_robots",
        type=int,
        default=DEFAULT_PARAMS["n_yellow_robots"],
    )
    parser.add_argument("--n-red-robots", dest="n_red_robots", type=int, default=DEFAULT_PARAMS["n_red_robots"])
    parser.add_argument(
        "--initial-green-waste",
        dest="initial_green_waste",
        type=int,
        default=DEFAULT_PARAMS["initial_green_waste"],
    )
    parser.add_argument(
        "--initial-yellow-waste",
        dest="initial_yellow_waste",
        type=int,
        default=DEFAULT_PARAMS["initial_yellow_waste"],
    )
    parser.add_argument(
        "--initial-red-waste",
        dest="initial_red_waste",
        type=int,
        default=DEFAULT_PARAMS["initial_red_waste"],
    )
    parser.add_argument("--max-steps", dest="max_steps", type=int, default=DEFAULT_PARAMS["max_steps"])
    parser.add_argument("--seed", type=int, default=None, help="Seed for single-run mode.")
    parser.add_argument(
        "--disable-communication",
        action="store_true",
        help="Disable all agent messages (single-run mode).",
    )

    parser.add_argument(
        "--widths",
        default=str(DEFAULT_PARAMS["width"]),
        help="CSV list for benchmark sweep. Example: 15,30,45",
    )
    parser.add_argument(
        "--heights",
        default=str(DEFAULT_PARAMS["height"]),
        help="CSV list for benchmark sweep. Example: 10,20",
    )
    parser.add_argument(
        "--green-robots",
        default=str(DEFAULT_PARAMS["n_green_robots"]),
        help="CSV list for benchmark sweep.",
    )
    parser.add_argument(
        "--yellow-robots",
        default=str(DEFAULT_PARAMS["n_yellow_robots"]),
        help="CSV list for benchmark sweep.",
    )
    parser.add_argument(
        "--red-robots",
        default=str(DEFAULT_PARAMS["n_red_robots"]),
        help="CSV list for benchmark sweep.",
    )
    parser.add_argument(
        "--green-waste",
        default=str(DEFAULT_PARAMS["initial_green_waste"]),
        help="CSV list for benchmark sweep.",
    )
    parser.add_argument(
        "--yellow-waste",
        default=str(DEFAULT_PARAMS["initial_yellow_waste"]),
        help="CSV list for benchmark sweep.",
    )
    parser.add_argument(
        "--red-waste",
        default=str(DEFAULT_PARAMS["initial_red_waste"]),
        help="CSV list for benchmark sweep.",
    )
    parser.add_argument(
        "--max-steps-grid",
        default=str(DEFAULT_PARAMS["max_steps"]),
        help="CSV list for benchmark sweep.",
    )
    parser.add_argument("--repetitions", type=int, default=5, help="Runs per scenario in benchmark mode.")
    parser.add_argument(
        "--seed-base",
        type=int,
        default=None,
        help="Optional deterministic seed base (seed = seed_base + run_id - 1).",
    )
    parser.add_argument("--output-dir", default="benchmark_results", help="Directory for benchmark CSV outputs.")
    parser.add_argument(
        "--skip-timeseries",
        action="store_true",
        help="Do not export per-step timeseries CSV.",
    )
    return parser


if __name__ == "__main__":
    cli_args = build_parser().parse_args()
    if cli_args.benchmark:
        run_benchmark(cli_args)
    else:
        run_single(cli_args)
