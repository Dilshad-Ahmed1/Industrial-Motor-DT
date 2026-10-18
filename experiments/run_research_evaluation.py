from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from fmpy import read_model_description

from experiments.experiment_runner import SCENARIOS


ROOT = Path(__file__).resolve().parents[1]
CONTROLLERS = ("baseline", "adaptive", "constrained")
DEFAULT_FMU = ROOT / "models" / "InductionMotorDigitalTwin18kW.fmu"
DEFAULT_CONFIG = ROOT / "config" / "twin_config.yaml"
DEFAULT_MODEL = ROOT / "models" / "InductionMotorDigitalTwin18kW.mo"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_state() -> dict[str, str | None]:
    commit_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    status_result = subprocess.run(
        ["git", "status", "--short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "commit": commit_result.stdout.strip() if commit_result.returncode == 0 else None,
        "working_tree_status": (
            status_result.stdout.strip() if status_result.returncode == 0 else None
        ),
    }


def _package_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=True),
        encoding="utf-8",
    )


def _write_comparison(output_dir: Path, runs: list[dict[str, Any]]) -> None:
    metric_names = sorted(
        {
            key
            for run in runs
            for key in run.get("metrics", {})
            if isinstance(run.get("metrics", {}).get(key), (int, float, bool))
        }
    )
    fields = [
        "run_id",
        "scenario",
        "controller",
        "status",
        "return_code",
        "raw_csv",
        "run_log",
        *metric_names,
    ]
    with (output_dir / "controller_scenario_comparison.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as destination:
        writer = csv.DictWriter(
            destination,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        for run in runs:
            row = {
                key: run.get(key)
                for key in fields
                if key in run
            }
            row.update(run.get("metrics", {}))
            writer.writerow(row)


def _run_case(
    *,
    run_id: str,
    scenario: str,
    controller: str,
    fmu_path: Path,
    output_dir: Path,
    stop_time: float,
    fault_time: float,
    step: float,
    basyx_enabled: bool,
    basyx_host: str,
    basyx_period_s: float,
) -> dict[str, Any]:
    csv_path = output_dir / f"{run_id}.csv"
    log_path = output_dir / f"{run_id}.log"
    command = [
        sys.executable,
        "-m",
        "experiments.experiment_runner",
        "--fmu",
        str(fmu_path),
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
    if basyx_enabled:
        command.extend(
            (
                "--basyx",
                "--basyx-host",
                basyx_host,
                "--basyx-period",
                str(basyx_period_s),
            )
        )

    started_at = _utc_now()
    started_clock = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.perf_counter() - started_clock
    log_path.write_text(
        result.stdout + result.stderr,
        encoding="utf-8",
    )
    metrics_path = csv_path.with_name(f"{csv_path.stem}_metrics.json")
    metrics = (
        json.loads(metrics_path.read_text(encoding="utf-8"))
        if metrics_path.is_file()
        else {}
    )
    status = (
        "completed"
        if result.returncode == 0 and csv_path.is_file() and metrics
        else "failed"
    )
    return {
        "run_id": run_id,
        "scenario": scenario,
        "scenario_parameters": asdict(SCENARIOS[scenario]),
        "controller": controller,
        "status": status,
        "return_code": result.returncode,
        "started_at_utc": started_at,
        "completed_at_utc": _utc_now(),
        "wall_time_s": elapsed,
        "command": command,
        "random_seed": None,
        "randomness": "None; deterministic plant and controller configuration.",
        "raw_csv": str(csv_path),
        "metrics_json": str(metrics_path),
        "run_log": str(log_path),
        "metrics": metrics,
        "error": None if status == "completed" else result.stderr[-8000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the deterministic induction-motor controller research "
            "campaign and preserve raw runs, logs, and a complete manifest."
        )
    )
    parser.add_argument("--fmu", type=Path, default=DEFAULT_FMU)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "results" / "research_evaluation",
    )
    parser.add_argument(
        "--stop",
        type=float,
        default=2700.0,
        help="Total simulated duration in seconds.",
    )
    parser.add_argument("--fault-time", type=float, default=350.0)
    parser.add_argument("--step", type=float, default=0.5)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=sorted(SCENARIOS),
        help="Optional scenario subset; repeat to select more than one.",
    )
    parser.add_argument(
        "--controller",
        action="append",
        choices=CONTROLLERS,
        help="Optional controller subset; repeat to select more than one.",
    )
    parser.add_argument(
        "--with-basyx",
        action="store_true",
        help="Synchronize one selected case with a live BaSyx instance.",
    )
    parser.add_argument(
        "--aas-scenario",
        choices=sorted(SCENARIOS),
        default="combined_supported",
    )
    parser.add_argument(
        "--aas-controller",
        choices=CONTROLLERS,
        default="constrained",
    )
    parser.add_argument("--basyx-host", default="http://localhost:8081")
    parser.add_argument("--basyx-period", type=float, default=10.0)
    args = parser.parse_args()

    if args.stop <= 0 or args.fault_time < 0 or args.fault_time >= args.stop:
        parser.error("Require stop > fault-time >= 0.")
    if args.step <= 0:
        parser.error("Require step > 0.")
    if args.basyx_period <= 0:
        parser.error("Require --basyx-period > 0.")

    fmu_path = args.fmu.resolve()
    if not fmu_path.is_file():
        parser.error(f"Induction FMU not found: {fmu_path}")
    if not DEFAULT_CONFIG.is_file() or not DEFAULT_MODEL.is_file():
        parser.error("Required induction configuration or Modelica source is missing.")
    with DEFAULT_CONFIG.open("r", encoding="utf-8") as config_file:
        configuration = yaml.safe_load(config_file)
    fmu_description = read_model_description(str(fmu_path))
    if (
        fmu_description.modelName
        != "MotorDigitalTwin.InductionMotorDigitalTwin18kW"
        or fmu_description.fmiVersion != "2.0"
        or fmu_description.coSimulation is None
    ):
        parser.error(
            "Campaign requires the FMI 2.0 Co-Simulation FMU for "
            "MotorDigitalTwin.InductionMotorDigitalTwin18kW."
        )

    scenarios = args.scenario or sorted(SCENARIOS)
    controllers = args.controller or list(CONTROLLERS)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (args.output_root / timestamp).resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    protocol = {
        "plant_model": "MotorDigitalTwin.InductionMotorDigitalTwin18kW",
        "modelica_standard_library": "4.1.0",
        "fmu_path": str(fmu_path),
        "simulation_stop_time_s": args.stop,
        "fault_injection_time_s": args.fault_time,
        "communication_step_s": args.step,
        "initial_conditions": "Modelica model initial conditions and config defaults",
        "scenarios": scenarios,
        "controllers": controllers,
        "controllers_receive_equal_plant_and_scenario_inputs": True,
        "random_seed": None,
        "randomness": "None; deterministic single-run cases.",
        "basyx_enabled_for": (
            f"{args.aas_scenario}/{args.aas_controller}"
            if args.with_basyx
            else None
        ),
    }
    manifest: dict[str, Any] = {
        "campaign_id": timestamp,
        "status": "running",
        "created_at_utc": _utc_now(),
        "completed_at_utc": None,
        "protocol": protocol,
        "artifacts": {
            "fmu_sha256": _sha256(fmu_path),
            "modelica_source_sha256": _sha256(DEFAULT_MODEL),
            "config_sha256": _sha256(DEFAULT_CONFIG),
            "fmu_model_name": fmu_description.modelName,
            "fmu_guid": fmu_description.guid,
            "fmi_version": fmu_description.fmiVersion,
            "fmu_generation_tool": fmu_description.generationTool,
            "fmu_model_identifier": fmu_description.coSimulation.modelIdentifier,
            "modelica_model_class": "MotorDigitalTwin.InductionMotorDigitalTwin18kW",
        },
        "configuration": configuration,
        "software_versions": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": _package_version("numpy"),
            "pandas": _package_version("pandas"),
            "fmpy": _package_version("fmpy"),
            "pyyaml": _package_version("PyYAML"),
            "matplotlib": _package_version("matplotlib"),
            "requests": _package_version("requests"),
            **_git_state(),
        },
        "runs": [],
    }
    manifest_path = output_dir / "manifest.json"
    _write_json(manifest_path, manifest)

    plan = [
        (scenario, controller)
        for scenario in scenarios
        for controller in controllers
    ]
    for index, (scenario, controller) in enumerate(plan, start=1):
        run_id = f"{index:02d}_{scenario}_{controller}"
        aas_enabled = (
            args.with_basyx
            and scenario == args.aas_scenario
            and controller == args.aas_controller
        )
        print(
            f"[{index}/{len(plan)}] {scenario}/{controller}"
            + (" + BaSyx" if aas_enabled else ""),
            flush=True,
        )
        run = _run_case(
            run_id=run_id,
            scenario=scenario,
            controller=controller,
            fmu_path=fmu_path,
            output_dir=output_dir,
            stop_time=args.stop,
            fault_time=args.fault_time,
            step=args.step,
            basyx_enabled=aas_enabled,
            basyx_host=args.basyx_host,
            basyx_period_s=args.basyx_period,
        )
        manifest["runs"].append(run)
        _write_json(manifest_path, manifest)
        _write_json(output_dir / "campaign.json", manifest)
        _write_comparison(output_dir, manifest["runs"])
        print(
            f"  {run['status']} exit={run['return_code']} "
            f"wall={run['wall_time_s']:.2f}s",
            flush=True,
        )

    failed_runs = [run for run in manifest["runs"] if run["status"] != "completed"]
    manifest["status"] = "completed" if not failed_runs else "completed_with_failures"
    manifest["completed_at_utc"] = _utc_now()
    manifest["failure_count"] = len(failed_runs)
    _write_json(manifest_path, manifest)
    _write_json(output_dir / "campaign.json", manifest)
    _write_comparison(output_dir, manifest["runs"])

    print(f"Campaign directory: {output_dir}")
    print(
        f"Completed: {len(manifest['runs'])-len(failed_runs)}/"
        f"{len(manifest['runs'])}; failed: {len(failed_runs)}"
    )
    return 1 if failed_runs else 0


if __name__ == "__main__":
    raise SystemExit(main())
