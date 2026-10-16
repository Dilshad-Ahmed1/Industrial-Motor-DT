import pandas as pd
import pytest

from scripts.validate_induction_motor_nominal import (
    evaluate_nominal_results,
    reference_operating_point,
)


def _reference_frame() -> pd.DataFrame:
    reference = reference_operating_point()
    return pd.DataFrame(
        {
            "time": [7.0, 7.5, 8.0],
            "line_voltage_rms_V": [reference["line_voltage_rms_V"]] * 3,
            "line_current_rms_A": [reference["line_current_rms_A"]] * 3,
            "supply_frequency_Hz": [reference["supply_frequency_Hz"]] * 3,
            "speed_rpm": [reference["speed_rpm"]] * 3,
            "slip_fraction": [reference["slip_percent"] / 100.0] * 3,
            "torque_electromagnetic_Nm": [
                reference["electromagnetic_torque_Nm"]
            ]
            * 3,
            "torque_shaft_Nm": [reference["shaft_torque_Nm"]] * 3,
            "electrical_input_power_W": [
                reference["electrical_input_power_W"]
            ]
            * 3,
            "mechanical_output_power_W": [
                reference["mechanical_output_power_W"]
            ]
            * 3,
            "efficiency": [reference["efficiency_percent"] / 100.0] * 3,
            "power_factor": [reference["power_factor"]] * 3,
            "motor_losses_W": [reference["motor_losses_W"]] * 3,
            "stator_copper_losses_W": [
                reference["stator_copper_losses_W"]
            ]
            * 3,
            "stator_core_losses_W": [reference["stator_core_losses_W"]] * 3,
            "rotor_copper_losses_W": [reference["rotor_copper_losses_W"]] * 3,
            "rotor_core_losses_W": [reference["rotor_core_losses_W"]] * 3,
            "stray_load_losses_W": [reference["stray_load_losses_W"]] * 3,
            "friction_losses_W": [reference["friction_losses_W"]] * 3,
            "motor_lumped_temperature_K": [
                reference["motor_lumped_temperature_C"] + 273.15 + offset
                for offset in (0.0, 0.01, 0.02)
            ]
        }
    )


def test_reference_point_uses_documented_benchmark_values() -> None:
    reference = reference_operating_point()

    assert reference["line_voltage_rms_V"] == 400.0
    assert reference["supply_frequency_Hz"] == 50.0
    assert reference["speed_rpm"] == 1462.5
    assert reference["slip_percent"] == 2.5
    assert reference["mechanical_output_power_W"] == 18500.0
    assert reference["efficiency_percent"] == 90.49
    assert reference["electromagnetic_torque_Nm"] > reference["shaft_torque_Nm"]


def test_nominal_reference_dataset_passes_deviation_and_stability_checks() -> None:
    result = evaluate_nominal_results(_reference_frame())

    assert result["passed"]
    assert all(check["passed"] for check in result["deviation_checks"].values())
    assert all(check["passed"] for check in result["stability_checks"].values())
    assert result["steady_state_window_s"]["samples"] == 3


def test_nominal_validation_rejects_unstable_steady_speed() -> None:
    frame = _reference_frame()
    frame.loc[frame.index[-1], "speed_rpm"] += 0.2

    result = evaluate_nominal_results(frame)

    assert not result["passed"]
    assert not result["stability_checks"]["speed_rpm_peak_to_peak"]["passed"]


def test_nominal_validation_requires_a_thermal_state_response() -> None:
    frame = _reference_frame()
    frame["motor_lumped_temperature_K"] = 363.15

    result = evaluate_nominal_results(frame)

    assert not result["passed"]
    assert not result["thermal_response"]["changed_during_simulation"]


def test_nominal_validation_rejects_missing_measurement() -> None:
    frame = _reference_frame().drop(columns=["power_factor"])

    with pytest.raises(KeyError, match="power_factor"):
        evaluate_nominal_results(frame)
