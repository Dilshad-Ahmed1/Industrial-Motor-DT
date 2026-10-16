from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
INDUCTION_SCENARIOS = (
    "healthy",
    "cooling",
    "sensor_bias",
    "sensor_freeze",
    "voltage_imbalance",
    "frequency_deviation",
    "overload",
    "mechanical_friction",
    "combined_supported",
)
CONTROLLERS = ("baseline", "adaptive", "constrained")


def _slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-").lower()


def _run_case(
    *,
    plant: str,
    scenario: str,
    controller: str,
    fmu_path: Path,
    output_dir: Path,
    stop_time: float,
    fault_time: float,
    step: float,
    aas_enabled: bool,
    basyx_host: str,
    basyx_period_s: float,
) -> dict[str, Any]:
    case_name = _slug(f"{plant}-{scenario}-{controller}")
    csv_path = output_dir / f"{case_name}.csv"
    command = [
        sys.executable,
        "-m",
        "experiments.experiment_runner",
        "--fmu",
        str(fmu_path),
        "--plant-profile",
        plant,
        "--scenario",
        scenario,
        "--controller",
        controller,
        "--stop",
        str(stop_time),
        "--step",
        str(step),
        "--fault-time",
        str(fault_time),
        "--output",
        str(csv_path),
    ]
    if aas_enabled:
        command.extend(
            (
                "--basyx",
                "--basyx-host",
                basyx_host,
                "--basyx-period",
                str(basyx_period_s),
            )
        )
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    (output_dir / f"{case_name}.log").write_text(
        result.stdout + result.stderr,
        encoding="utf-8",
    )
    metrics_path = csv_path.with_name(f"{csv_path.stem}_metrics.json")
    row: dict[str, Any] = {
        "plant": plant,
        "scenario": scenario,
        "controller": controller,
        "return_code": result.returncode,
        "csv": str(csv_path),
        "log": str(output_dir / f"{case_name}.log"),
        "metrics": str(metrics_path),
    }
    if metrics_path.is_file():
        row["results"] = json.loads(metrics_path.read_text(encoding="utf-8"))
    else:
        row["error"] = result.stderr[-4000:]
    return row


def _write_campaign_outputs(output_dir: Path, runs: list[dict[str, Any]]) -> None:
    (output_dir / "campaign.json").write_text(
        json.dumps(runs, indent=2, allow_nan=True),
        encoding="utf-8",
    )
    metric_keys = (
        "maximum_winding_temperature_C",
        "time_above_critical_s",
        "minimum_thermal_margin_C",
        "state_estimation_mae_C",
        "fault_detection_latency_s",
        "fault_severity_mae",
        "fault_severity_mae_post_fault",
        "prediction_mae_30s_C",
        "prediction_mae_60s_C",
        "energy_total_kWh",
        "useful_work_total_kWh",
        "energy_to_useful_work_ratio",
        "mean_load_command_pu",
        "post_fault_mean_load_command_pu",
        "mean_controller_derating_fraction",
        "max_controller_derating_fraction",
        "speed_rmse_rad_s",
        "torque_command_rmse_Nm",
        "mean_solver_step_time_ms",
        "real_time_factor",
        "realtime_factor",
        "basyx_aas_write_latency_mean_ms",
        "basyx_aas_read_latency_mean_ms",
        "basyx_update_success_rate_percent",
        "basyx_read_success_rate_percent",
        "basyx_snapshot_alignment_success_rate_percent",
        "basyx_end_to_end_loop_mean_latency_ms",
    )
    fields = ["plant", "scenario", "controller", "return_code", *metric_keys]
    with (output_dir / "comparison.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            results = run.get("results", {})
            row = {
                "plant": run["plant"],
                "scenario": run["scenario"],
                "controller": run["controller"],
                "return_code": run["return_code"],
            }
            for key in metric_keys:
                row[key] = results.get(key, "")
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run timestamped, non-overwriting motor-model/controller "
            "comparison experiments."
        )
    )
    parser.add_argument(
        "--induction-fmu",
        type=Path,
        default=ROOT / "models" / "InductionMotorDigitalTwin18kW.fmu",
    )
    parser.add_argument(
        "--legacy-fmu",
        type=Path,
        default=ROOT / "MotorElectroThermalMechanicalFaultable.fmu",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "results" / "motor_model_comparison",
    )
    parser.add_argument("--stop", type=float, default=800.0)
    parser.add_argument("--fault-time", type=float, default=350.0)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument("--skip-legacy", action="store_true")
    parser.add_argument("--with-basyx", action="store_true")
    parser.add_argument("--basyx-host", default="http://localhost:8081")
    parser.add_argument("--basyx-period", type=float, default=10.0)
    args = parser.parse_args()

    if args.fault_time < 0 or args.stop <= args.fault_time or args.step <= 0:
        parser.error("Require stop > fault-time >= 0 and step > 0.")
    induction_fmu = args.induction_fmu.resolve()
    legacy_fmu = args.legacy_fmu.resolve()
    if not induction_fmu.is_file():
        parser.error(f"Induction FMU not found: {induction_fmu}")
    if not args.skip_legacy and not legacy_fmu.is_file():
        parser.error(f"Legacy FMU not found: {legacy_fmu}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (args.output_root / stamp).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    plans = [
        ("induction", scenario, controller, induction_fmu)
        for scenario in INDUCTION_SCENARIOS
        for controller in CONTROLLERS
    ]
    if not args.skip_legacy:
        plans.extend(
            ("legacy", scenario, controller, legacy_fmu)
            for scenario in ("healthy", "cooling", "unbalance")
            for controller in CONTROLLERS
        )

    runs: list[dict[str, Any]] = []
    for index, (plant, scenario, controller, fmu) in enumerate(plans, 1):
        aas_enabled = (
            args.with_basyx
            and plant == "induction"
            and scenario == "combined_supported"
            and controller == "constrained"
        )
        print(
            f"[{index}/{len(plans)}] {plant}/{scenario}/{controller}"
            + (" + BaSyx" if aas_enabled else ""),
            flush=True,
        )
        run = _run_case(
            plant=plant,
            scenario=scenario,
            controller=controller,
            fmu_path=fmu,
            output_dir=output_dir,
            stop_time=args.stop,
            fault_time=args.fault_time,
            step=args.step,
            aas_enabled=aas_enabled,
            basyx_host=args.basyx_host,
            basyx_period_s=args.basyx_period,
        )
        runs.append(run)
        _write_campaign_outputs(output_dir, runs)
        print(
            f"  exit={run['return_code']} "
            f"csv={Path(run['csv']).name}",
            flush=True,
        )

    failures = [run for run in runs if run["return_code"] != 0]
    print(f"Campaign folder: {output_dir}")
    print(f"Completed: {len(runs)-len(failures)}/{len(runs)}; failed: {len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
