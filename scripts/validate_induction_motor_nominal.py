from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_FILE = PROJECT_ROOT / "models" / "InductionMotorSquirrelCage18kW.mo"
MODEL_CLASS = "MotorDigitalTwin.InductionMotorSquirrelCage18kW"
MSL_VERSION = "4.1.0"
STOP_TIME_S = 8.0
SETTLING_WINDOW_S = 1.0

REFERENCE: dict[str, float] = {
    "line_voltage_rms_V": 400.0,
    "line_current_rms_A": 32.85,
    "supply_frequency_Hz": 50.0,
    "speed_rpm": 1462.5,
    "slip_percent": 2.5,
    "shaft_torque_Nm": 18500.0 / (2.0 * math.pi * 1462.5 / 60.0),
    "electrical_input_power_W": 20443.95,
    "mechanical_output_power_W": 18500.0,
    "efficiency_percent": 90.49,
    "power_factor": 0.898,
    "motor_losses_W": 1943.95,
    "stator_copper_losses_W": 770.13,
    "stator_core_losses_W": 410.0,
    "rotor_copper_losses_W": 481.60,
    "rotor_core_losses_W": 0.0,
    "stray_load_losses_W": 102.22,
    "friction_losses_W": 180.0,
    "motor_lumped_temperature_C": 90.0,
}

_NOMINAL_OMEGA_RAD_S = 2.0 * math.pi * REFERENCE["speed_rpm"] / 60.0
_REFERENCE_STRAY_LOSS_W = REFERENCE["stray_load_losses_W"]
REFERENCE["electromagnetic_torque_Nm"] = (
    REFERENCE["shaft_torque_Nm"]
    + (REFERENCE["friction_losses_W"] + _REFERENCE_STRAY_LOSS_W)
    / _NOMINAL_OMEGA_RAD_S
)

_CHECKS: dict[str, tuple[str, float, str]] = {
    "line_voltage_rms_V": ("line_voltage_rms_V", 0.4, "absolute"),
    "line_current_rms_A": ("line_current_rms_A", 2.0, "relative_percent"),
    "supply_frequency_Hz": ("supply_frequency_Hz", 0.001, "absolute"),
    "speed_rpm": ("speed_rpm", 0.5, "relative_percent"),
    "slip_percent": ("slip_percent", 0.1, "absolute"),
    "electromagnetic_torque_Nm": (
        "electromagnetic_torque_Nm",
        2.0,
        "relative_percent",
    ),
    "shaft_torque_Nm": ("shaft_torque_Nm", 2.0, "relative_percent"),
    "electrical_input_power_W": (
        "electrical_input_power_W",
        2.0,
        "relative_percent",
    ),
    "mechanical_output_power_W": (
        "mechanical_output_power_W",
        2.0,
        "relative_percent",
    ),
    "efficiency_percent": ("efficiency_percent", 0.5, "absolute"),
    "power_factor": ("power_factor", 0.02, "absolute"),
    "motor_losses_W": ("motor_losses_W", 5.0, "relative_percent"),
    "stator_copper_losses_W": (
        "stator_copper_losses_W",
        3.0,
        "relative_percent",
    ),
    "stator_core_losses_W": (
        "stator_core_losses_W",
        3.0,
        "relative_percent",
    ),
    "rotor_copper_losses_W": (
        "rotor_copper_losses_W",
        3.0,
        "relative_percent",
    ),
    "rotor_core_losses_W": ("rotor_core_losses_W", 0.1, "absolute"),
    "stray_load_losses_W": (
        "stray_load_losses_W",
        3.0,
        "relative_percent",
    ),
    "friction_losses_W": ("friction_losses_W", 3.0, "relative_percent"),
    "motor_lumped_temperature_C": (
        "motor_lumped_temperature_C",
        5.0,
        "absolute",
    ),
}

_REQUIRED_COLUMNS = {
    "time",
    "line_voltage_rms_V",
    "line_current_rms_A",
    "supply_frequency_Hz",
    "speed_rpm",
    "slip_fraction",
    "torque_electromagnetic_Nm",
    "torque_shaft_Nm",
    "electrical_input_power_W",
    "mechanical_output_power_W",
    "efficiency",
    "power_factor",
    "motor_losses_W",
    "stator_copper_losses_W",
    "stator_core_losses_W",
    "rotor_copper_losses_W",
    "rotor_core_losses_W",
    "stray_load_losses_W",
    "friction_losses_W",
    "motor_lumped_temperature_K",
}
_CSV_VARIABLE_FILTER = "^(" + "|".join(
    re.escape(column) for column in sorted(_REQUIRED_COLUMNS)
) + ")$"


def reference_operating_point() -> dict[str, float]:
    """Return the nominal point and explicitly derived reference quantities."""
    return dict(REFERENCE)


def evaluate_nominal_results(
    frame: pd.DataFrame,
    stop_time_s: float = STOP_TIME_S,
    settling_window_s: float = SETTLING_WINDOW_S,
) -> dict[str, Any]:
    missing = sorted(_REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise KeyError(f"Simulation result is missing columns: {missing}")
    if frame.empty:
        raise ValueError("Simulation result contains no samples.")
    if stop_time_s <= 0.0 or settling_window_s <= 0.0:
        raise ValueError("Simulation and settling-window durations must be positive.")

    numeric = frame.loc[:, sorted(_REQUIRED_COLUMNS)].apply(
        pd.to_numeric,
        errors="coerce",
    )
    if not numeric.notna().all().all():
        raise ValueError("Simulation result contains non-numeric or missing values.")
    if not math.isclose(float(numeric["time"].iloc[-1]), stop_time_s, abs_tol=1e-8):
        raise ValueError(
            f"Simulation ended at {numeric['time'].iloc[-1]} s, "
            f"expected {stop_time_s} s."
        )

    tail = numeric[numeric["time"] >= stop_time_s - settling_window_s]
    if len(tail) < 2:
        raise ValueError("Steady-state window contains fewer than two samples.")

    actual: dict[str, float] = {
        "line_voltage_rms_V": float(tail["line_voltage_rms_V"].mean()),
        "line_current_rms_A": float(tail["line_current_rms_A"].mean()),
        "supply_frequency_Hz": float(tail["supply_frequency_Hz"].mean()),
        "speed_rpm": float(tail["speed_rpm"].mean()),
        "slip_percent": float(tail["slip_fraction"].mean() * 100.0),
        "electromagnetic_torque_Nm": float(
            tail["torque_electromagnetic_Nm"].mean()
        ),
        "shaft_torque_Nm": float(tail["torque_shaft_Nm"].mean()),
        "electrical_input_power_W": float(
            tail["electrical_input_power_W"].mean()
        ),
        "mechanical_output_power_W": float(
            tail["mechanical_output_power_W"].mean()
        ),
        "efficiency_percent": float(tail["efficiency"].mean() * 100.0),
        "power_factor": float(tail["power_factor"].mean()),
        "motor_losses_W": float(tail["motor_losses_W"].mean()),
        "stator_copper_losses_W": float(tail["stator_copper_losses_W"].mean()),
        "stator_core_losses_W": float(tail["stator_core_losses_W"].mean()),
        "rotor_copper_losses_W": float(tail["rotor_copper_losses_W"].mean()),
        "rotor_core_losses_W": float(tail["rotor_core_losses_W"].mean()),
        "stray_load_losses_W": float(tail["stray_load_losses_W"].mean()),
        "friction_losses_W": float(tail["friction_losses_W"].mean()),
        "motor_lumped_temperature_C": float(
            tail["motor_lumped_temperature_K"].mean() - 273.15
        ),
    }

    checks: dict[str, dict[str, float | bool | str]] = {}
    for name, (actual_name, tolerance, mode) in _CHECKS.items():
        measured = actual[actual_name]
        reference = REFERENCE[name]
        absolute_error = abs(measured - reference)
        relative_error = (
            absolute_error / abs(reference) * 100.0
            if reference != 0.0
            else None
        )
        passed = (
            absolute_error <= tolerance
            if mode == "absolute"
            else relative_error is not None and relative_error <= tolerance
        )
        checks[name] = {
            "actual": measured,
            "reference": reference,
            "absolute_deviation": measured - reference,
            "relative_deviation_percent": relative_error,
            "tolerance": tolerance,
            "tolerance_type": mode,
            "passed": passed,
        }

    steady_ranges = {
        "speed_rpm_peak_to_peak": float(
            tail["speed_rpm"].max() - tail["speed_rpm"].min()
        ),
        "line_current_rms_A_peak_to_peak": float(
            tail["line_current_rms_A"].max() - tail["line_current_rms_A"].min()
        ),
        "electrical_input_power_W_peak_to_peak": float(
            tail["electrical_input_power_W"].max()
            - tail["electrical_input_power_W"].min()
        ),
        "mechanical_output_power_W_peak_to_peak": float(
            tail["mechanical_output_power_W"].max()
            - tail["mechanical_output_power_W"].min()
        ),
    }
    temperatures_c = numeric["motor_lumped_temperature_K"] - 273.15
    thermal_response = {
        "initial_temperature_C": float(temperatures_c.iloc[0]),
        "final_temperature_C": float(temperatures_c.iloc[-1]),
        "minimum_temperature_C": float(temperatures_c.min()),
        "maximum_temperature_C": float(temperatures_c.max()),
        "temperature_range_C": float(temperatures_c.max() - temperatures_c.min()),
        "changed_during_simulation": bool(
            temperatures_c.max() - temperatures_c.min() > 1e-9
        ),
    }
    stability_checks = {
        "speed_rpm_peak_to_peak": {
            "actual": steady_ranges["speed_rpm_peak_to_peak"],
            "maximum": 0.1,
            "passed": steady_ranges["speed_rpm_peak_to_peak"] <= 0.1,
        },
        "line_current_rms_A_peak_to_peak": {
            "actual": steady_ranges["line_current_rms_A_peak_to_peak"],
            "maximum": 0.02,
            "passed": steady_ranges["line_current_rms_A_peak_to_peak"] <= 0.02,
        },
        "electrical_input_power_W_peak_to_peak": {
            "actual": steady_ranges["electrical_input_power_W_peak_to_peak"],
            "maximum": 20.0,
            "passed": steady_ranges[
                "electrical_input_power_W_peak_to_peak"
            ] <= 20.0,
        },
        "mechanical_output_power_W_peak_to_peak": {
            "actual": steady_ranges["mechanical_output_power_W_peak_to_peak"],
            "maximum": 20.0,
            "passed": steady_ranges[
                "mechanical_output_power_W_peak_to_peak"
            ] <= 20.0,
        },
    }
    return {
        "passed": all(check["passed"] for check in checks.values())
        and all(check["passed"] for check in stability_checks.values())
        and thermal_response["changed_during_simulation"],
        "steady_state_window_s": {
            "start": stop_time_s - settling_window_s,
            "stop": stop_time_s,
            "samples": len(tail),
        },
        "operating_point": actual,
        "reference_point": reference_operating_point(),
        "deviation_checks": checks,
        "stability_checks": stability_checks,
        "thermal_response": thermal_response,
    }


def _modelica_string(value: str | Path) -> str:
    return '"' + str(value).replace("\\", "/").replace('"', '\\"') + '"'


def _find_omc(omc_argument: Path | None, omhome: Path | None) -> Path:
    candidates: list[Path] = []
    if omc_argument is not None:
        candidates.append(omc_argument)
    if omhome is not None:
        candidates.append(omhome / "bin" / "omc.exe")
        candidates.append(omhome / "bin" / "omc")
    configured_home = os.environ.get("OPENMODELICAHOME")
    if configured_home:
        candidates.append(Path(configured_home) / "bin" / "omc.exe")
        candidates.append(Path(configured_home) / "bin" / "omc")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    candidates.append(
        Path(program_files) / "OpenModelica1.27.1-64bit" / "bin" / "omc.exe"
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    found = shutil.which("omc")
    if found:
        return Path(found).resolve()
    raise FileNotFoundError(
        "OpenModelica 1.27.1 was not found. Pass --omhome or --omc."
    )


def run_modelica_simulation(
    omc_executable: Path,
    output_dir: Path,
) -> tuple[Path, str, str]:
    version_result = subprocess.run(
        [str(omc_executable), "--version"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    version_text = (version_result.stdout + version_result.stderr).strip()
    if version_result.returncode != 0 or "v1.27.1" not in version_text:
        raise RuntimeError(
            "This validation requires OpenModelica 1.27.1; "
            f"found {version_text or 'an unreported version'}."
        )

    with tempfile.TemporaryDirectory(prefix="induction_motor_omc_") as temp_name:
        temp_dir = Path(temp_name)
        result_prefix = "induction_motor_nominal"
        result_in_temp = temp_dir / f"{result_prefix}_res.csv"
        mos_file = temp_dir / "run_nominal.mos"
        mos_file.write_text(
            "\n".join(
                [
                    "loadModel(Modelica);",
                    f'print("MSL_VERSION=" + getVersion(Modelica) + "\\n");',
                    f"loadFile({_modelica_string(MODEL_FILE)});",
                    f"checkModel({MODEL_CLASS});",
                    (
                        f"simulate({MODEL_CLASS}, "
                        f"stopTime={STOP_TIME_S:g}, "
                        f"numberOfIntervals={int(STOP_TIME_S * 1000)}, "
                        'tolerance=1e-6, method="dassl", '
                        f'outputFormat="csv", variableFilter="{_CSV_VARIABLE_FILTER}", '
                        f'fileNamePrefix="{result_prefix}");'
                    ),
                    "",
                ]
            ),
            encoding="utf-8",
        )
        run = subprocess.run(
            [str(omc_executable), str(mos_file)],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        omc_output = (run.stdout + run.stderr).strip()
        if run.returncode != 0:
            raise RuntimeError(
                f"OpenModelica failed (exit {run.returncode}):\n{omc_output}"
            )
        if not result_in_temp.is_file():
            raise RuntimeError(
                "OpenModelica did not produce the nominal CSV result.\n"
                f"Output:\n{omc_output}"
            )
        if "simulation finished successfully." not in omc_output.lower():
            raise RuntimeError(
                "OpenModelica did not report a successful simulation.\n"
                f"Output:\n{omc_output}"
            )
        msl_match = re.search(r"MSL_VERSION=([^\s]+)", omc_output)
        msl_version = msl_match.group(1) if msl_match else "unknown"
        if msl_version != MSL_VERSION:
            raise RuntimeError(
                f"This benchmark is documented against MSL {MSL_VERSION}; "
                f"found MSL {msl_version}."
            )

        result_path = output_dir / "motor_nominal.csv"
        shutil.copy2(result_in_temp, result_path)
        return result_path, version_text, msl_version


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Simulate and nominally validate the separate MSL "
            "18.5 kW squirrel-cage induction-motor model."
        )
    )
    parser.add_argument(
        "--omhome",
        type=Path,
        default=None,
        help="OpenModelica installation directory.",
    )
    parser.add_argument(
        "--omc",
        type=Path,
        default=None,
        help="Path to omc.exe (overrides --omhome).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "results" / "induction_motor_nominal",
        help="Parent directory for a new, uniquely named run directory.",
    )
    args = parser.parse_args()

    if not MODEL_FILE.is_file():
        raise FileNotFoundError(f"Modelica model not found: {MODEL_FILE}")
    omc_executable = _find_omc(args.omc, args.omhome)
    output_root = args.output_dir.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(
        tempfile.mkdtemp(prefix="run_", dir=output_root)
    )

    csv_path, omc_version, msl_version = run_modelica_simulation(
        omc_executable,
        run_dir,
    )
    frame = pd.read_csv(csv_path)
    validation = evaluate_nominal_results(frame)
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_file": str(MODEL_FILE),
        "model_class": MODEL_CLASS,
        "openmodelica_version": omc_version,
        "modelica_standard_library_version": msl_version,
        "stop_time_s": STOP_TIME_S,
        "settling_window_s": SETTLING_WINDOW_S,
        "reference_source": (
            "Modelica Standard Library 4.1.0, "
            "Modelica.Electrical.Machines.Examples.InductionMachines.IMC_withLosses"
        ),
        "result_csv": str(csv_path.resolve()),
        **validation,
    }
    report_path = run_dir / "validation.json"
    report_path.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print(f"OpenModelica : {omc_version}")
    print(f"Modelica     : {msl_version}")
    print(f"Model class  : {MODEL_CLASS}")
    print(
        f"Steady window: "
        f"{validation['steady_state_window_s']['start']:.3f}-"
        f"{validation['steady_state_window_s']['stop']:.3f} s "
        f"({validation['steady_state_window_s']['samples']} samples)"
    )
    print()
    print(
        f"{'Quantity':38s} {'Actual':>14s} {'Reference':>14s} "
        f"{'Deviation':>14s} {'Status':>8s}"
    )
    print("-" * 94)
    for name, check in validation["deviation_checks"].items():
        actual = float(check["actual"])
        reference = float(check["reference"])
        deviation = float(check["absolute_deviation"])
        print(
            f"{name:38s} {actual:14.6f} {reference:14.6f} "
            f"{deviation:14.6f} "
            f"{'PASS' if check['passed'] else 'FAIL':>8s}"
        )
    for name, check in validation["stability_checks"].items():
        print(
            f"{name + ' (steady range)':38s} "
            f"{float(check['actual']):14.6f} "
            f"{float(check['maximum']):14.6f} "
            f"{'PASS' if check['passed'] else 'FAIL':>8s}"
        )
    print(
        "thermal_response (full-run temperature range): "
        f"{validation['thermal_response']['temperature_range_C']:.6f} degC "
        f"{'PASS' if validation['thermal_response']['changed_during_simulation'] else 'FAIL'}"
    )
    print()
    print(f"Result CSV   : {csv_path}")
    print(f"Validation   : {report_path}")
    print(f"Overall      : {'PASS' if validation['passed'] else 'FAIL'}")

    if not validation["passed"]:
        raise RuntimeError("Nominal induction-motor validation failed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
