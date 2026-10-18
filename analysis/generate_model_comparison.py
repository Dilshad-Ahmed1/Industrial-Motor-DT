from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = (
    PROJECT_ROOT
    / "results"
    / "motor_model_comparison"
    / "20261003T111253Z"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "results"
    / "research_evaluation"
    / "20261016T172551Z"
)
PLANTS = ("legacy", "induction")
CONTROLLERS = ("baseline", "adaptive", "constrained")


def _raw_path(record: dict[str, Any], archive: Path) -> Path:
    path = Path(record["csv"])
    if not path.is_file():
        path = archive / path.name
    if not path.is_file():
        raise FileNotFoundError(f"Archived raw run CSV not found: {path}")
    return path


def _run_metrics(record: dict[str, Any], archive: Path) -> dict[str, Any]:
    raw_path = _raw_path(record, archive)
    frame = pd.read_csv(raw_path).sort_values("time_s").reset_index(drop=True)
    required = (
        "time_s",
        "T_winding_C",
        "speed_rpm",
        "P_electrical_W",
        "P_shaft_W",
        "rated_output_W",
        "solver_step_time_s",
    )
    missing = [column for column in required if column not in frame]
    if missing:
        raise KeyError(f"{raw_path} is missing raw comparison columns: {missing}")
    values = frame[list(required)].to_numpy(dtype=float)
    if frame.empty or not np.isfinite(values).all():
        raise ValueError(f"{raw_path} contains empty or non-finite measurements")

    times = frame["time_s"].to_numpy(dtype=float)
    time_steps = np.diff(times)
    if len(time_steps) == 0 or np.any(time_steps <= 0.0):
        raise ValueError(f"{raw_path} has invalid simulation timestamps")
    communication_step_s = float(np.median(time_steps))
    solver_seconds = frame["solver_step_time_s"].to_numpy(dtype=float)
    total_solver_seconds = float(np.sum(solver_seconds))
    if total_solver_seconds <= 0.0:
        raise ValueError(f"{raw_path} has no positive solver execution time")

    winding = frame["T_winding_C"].to_numpy(dtype=float)
    rated_output_kw = float(frame["rated_output_W"].iloc[0]) / 1000.0
    electrical_energy_kwh = float(
        np.trapezoid(
            frame["P_electrical_W"].to_numpy(dtype=float),
            times,
        )
        / 3_600_000.0
    )
    useful_work_kwh = float(
        np.trapezoid(
            np.maximum(0.0, frame["P_shaft_W"].to_numpy(dtype=float)),
            times,
        )
        / 3_600_000.0
    )
    return {
        "plant": record["plant"],
        "scenario": record["scenario"],
        "controller": record["controller"],
        "return_code": int(record["return_code"]),
        "raw_csv": str(raw_path),
        "sample_count": len(frame),
        "duration_s": float(times[-1] - times[0]),
        "communication_step_s": communication_step_s,
        "rated_output_kW": rated_output_kw,
        "initial_winding_temperature_C": float(winding[0]),
        "maximum_winding_temperature_C": float(np.max(winding)),
        "peak_winding_rise_C": float(np.max(winding) - winding[0]),
        "mean_speed_rpm": float(frame["speed_rpm"].mean()),
        "speed_range_rpm": float(
            frame["speed_rpm"].max() - frame["speed_rpm"].min()
        ),
        "electrical_energy_kWh": electrical_energy_kwh,
        "useful_shaft_work_kWh": useful_work_kwh,
        "electrical_energy_full_load_equivalent_h": (
            electrical_energy_kwh / rated_output_kw
        ),
        "useful_work_full_load_equivalent_h": (
            useful_work_kwh / rated_output_kw
        ),
        "mean_solver_step_time_ms": (
            float(np.mean(solver_seconds)) * 1000.0
        ),
        "solver_real_time_factor": (
            communication_step_s / float(np.mean(solver_seconds))
        ),
    }


def _load_comparable_runs(archive: Path) -> list[dict[str, Any]]:
    campaign_path = archive / "campaign.json"
    if not campaign_path.is_file():
        raise FileNotFoundError(f"Archived campaign not found: {campaign_path}")
    records = json.loads(campaign_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Archived campaign.json must contain a run list")
    plant_scenarios = {
        plant: {
            record["scenario"]
            for record in records
            if record.get("plant") == plant and int(record["return_code"]) == 0
        }
        for plant in PLANTS
    }
    common_scenarios = set.intersection(
        *(plant_scenarios[plant] for plant in PLANTS)
    )
    if not common_scenarios:
        raise ValueError("The archive has no scenarios shared by both plants")

    selected = [
        record
        for record in records
        if record.get("plant") in PLANTS
        and record.get("scenario") in common_scenarios
        and record.get("controller") in CONTROLLERS
        and int(record["return_code"]) == 0
    ]
    expected = {
        (plant, scenario, controller)
        for plant in PLANTS
        for scenario in common_scenarios
        for controller in CONTROLLERS
    }
    found = {
        (record["plant"], record["scenario"], record["controller"])
        for record in selected
    }
    if found != expected:
        raise ValueError(
            f"Archived comparison has incomplete matched cases: "
            f"missing={sorted(expected - found)}, extra={sorted(found - expected)}"
        )
    return [_run_metrics(record, archive) for record in selected]


def _summary(runs: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(runs)
    summary = (
        frame.groupby(["scenario", "plant"], as_index=False)
        .agg(
            run_count=("controller", "count"),
            mean_duration_s=("duration_s", "mean"),
            mean_communication_step_s=("communication_step_s", "mean"),
            rated_output_kW=("rated_output_kW", "mean"),
            mean_initial_winding_temperature_C=(
                "initial_winding_temperature_C",
                "mean",
            ),
            mean_maximum_winding_temperature_C=(
                "maximum_winding_temperature_C",
                "mean",
            ),
            mean_peak_winding_rise_C=("peak_winding_rise_C", "mean"),
            mean_speed_rpm=("mean_speed_rpm", "mean"),
            mean_speed_range_rpm=("speed_range_rpm", "mean"),
            mean_electrical_energy_kWh=("electrical_energy_kWh", "mean"),
            mean_useful_shaft_work_kWh=("useful_shaft_work_kWh", "mean"),
            mean_electrical_energy_full_load_equivalent_h=(
                "electrical_energy_full_load_equivalent_h",
                "mean",
            ),
            mean_useful_work_full_load_equivalent_h=(
                "useful_work_full_load_equivalent_h",
                "mean",
            ),
            mean_solver_step_time_ms=("mean_solver_step_time_ms", "mean"),
            mean_solver_real_time_factor=("solver_real_time_factor", "mean"),
        )
        .sort_values(["scenario", "plant"])
        .reset_index(drop=True)
    )
    return summary


def _write_report(
    output: Path,
    archive: Path,
    runs: list[dict[str, Any]],
    summary: pd.DataFrame,
) -> None:
    legacy = summary[summary["plant"] == "legacy"]
    induction = summary[summary["plant"] == "induction"]
    legacy_step_ms = float(legacy["mean_solver_step_time_ms"].mean())
    induction_step_ms = float(induction["mean_solver_step_time_ms"].mean())
    ratio = induction_step_ms / legacy_step_ms if legacy_step_ms > 0 else float("nan")
    table_rows: list[str] = []
    for row in summary.itertuples(index=False):
        table_rows.append(
            f"| {row.scenario} | {row.plant} | {row.run_count} | "
            f"{row.rated_output_kW:.2f} | "
            f"{row.mean_initial_winding_temperature_C:.2f} | "
            f"{row.mean_maximum_winding_temperature_C:.2f} | "
            f"{row.mean_peak_winding_rise_C:.2f} | "
            f"{row.mean_speed_range_rpm:.3f} | "
            f"{row.mean_useful_work_full_load_equivalent_h:.4f} | "
            f"{row.mean_solver_step_time_ms:.5f} | "
            f"{row.mean_solver_real_time_factor:.1f} |"
        )

    lines = [
        "# Historical reduced-order versus induction-motor comparison",
        "",
        f"- Historical source archive: `{archive}`",
        f"- Comparison runs recomputed from raw CSVs: {len(runs)}",
        "- Plants: archived 5.5 kW reduced-order model (`legacy`) and "
        "18.5 kW MSL induction model (`induction`).",
        "- Shared scenarios: "
        + ", ".join(sorted(summary["scenario"].unique()))
        + "; three controllers per plant/scenario.",
        "- Evidence type: historical deterministic simulation; not physical "
        "validation.",
        "",
        "## Matched-scenario summary",
        "",
        "Values below are arithmetic means across the three archived controller "
        "runs for each shared scenario, recalculated from the archived raw "
        "time-series. Energy and useful work use trapezoidal integration over "
        "the recorded `time_s` timestamps. Useful work is normalized by each "
        "model's own rated shaft power (full-load-equivalent hours). Solver "
        "timing is the per-sample `solver_step_time_s` recorded in those "
        "historical runs.",
        "",
        "| Scenario | Plant | Runs | Rated kW | Initial winding °C | Mean peak winding °C | Mean peak rise °C | Mean speed range rpm | Useful work / rated kW (h) | Mean solver step ms | Solver RT factor |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        *table_rows,
        "",
        "## Interpretation and limitations",
        "",
        f"Across the shared scenarios, the archived mean solver-step time is "
        f"{legacy_step_ms:.5f} ms for the reduced-order model and "
        f"{induction_step_ms:.5f} ms for the MSL model "
        f"(about {ratio:.0f}x higher in the MSL runs). This is an indicative "
        "historical per-step timing comparison, not a controlled benchmark: the "
        "archive lacks a complete software/hardware environment manifest, and "
        "it does not measure BaSyx or the whole application loop.",
        "",
        "The legacy model was rated at 5.5 kW and its traces start at 30 °C; the "
        "MSL traces are rated at 18.5 kW and start at 90 °C. Their absolute "
        "temperature, energy, and work values therefore are not direct equal-"
        "rating/equal-initial-condition comparisons. Normalizing shaft work by "
        "each model's own rating helps contextualize output but does not remove "
        "the thermal-parameter or initialization differences. The common 800 s "
        "healthy/cooling cases are the only shared scenario set in this archive. "
        "Saved traces span 799.5 s for the legacy model and 800.0 s for the MSL "
        "model, both sampled at 0.5 s. Other fault responses are not paired. "
        "Mechanical unbalance appears only "
        "in the historical legacy campaign and is unsupported by the rotational "
        "MSL model.",
        "",
        "The archived results show the synthetic model holding speed near its "
        "fixed nominal value, while the MSL model exposes speed range and "
        "three-phase electrical/torque dynamics. The old model is no longer an "
        "active plant option; its archived raw runs are preserved only for this "
        "historical comparison.",
        "",
        "## Reproduction",
        "",
        "From the repository root, run "
        "`python -m analysis.generate_model_comparison` to recompute "
        "`model_comparison_runs.csv`, `model_comparison_summary.csv`, and this "
        "report from the preserved archive.",
        "",
    ]
    (output / "MODEL_COMPARISON.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def generate(archive: Path, output: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    archive = archive.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runs = _load_comparable_runs(archive)
    run_frame = pd.DataFrame(runs)
    summary = _summary(runs)
    run_frame.to_csv(output / "model_comparison_runs.csv", index=False)
    summary.to_csv(output / "model_comparison_summary.csv", index=False)
    _write_report(output, archive, runs, summary)
    return run_frame, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute a historical plant comparison from archived raw runs."
    )
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    _, summary = generate(args.archive, args.output)
    print(
        f"Wrote model-comparison evidence for {len(summary)} "
        f"shared scenario/plant groups in {args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
