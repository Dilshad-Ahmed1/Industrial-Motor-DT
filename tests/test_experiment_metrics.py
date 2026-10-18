import math

import pandas as pd
import pytest

from analysis.experiment_metrics import compute_experiment_metrics


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time_s": [0.0, 1.0, 2.0],
            "sample_interval_s": [1.0, 1.0, 1.0],
            "fault_active": [False, True, True],
            "fault_input_active_for_next_interval": [False, True, True],
            "fault_type": ["cooling"] * 3,
            "T_winding_C": [80.0, 90.0, 100.0],
            "T_frame_C": [70.0, 75.0, 80.0],
            "estimated_winding_C": [80.0, 89.0, 98.0],
            "estimated_frame_C": [70.0, 74.0, 79.0],
            "predicted_30s_C": [80.0, 90.0, 100.0],
            "predicted_60s_C": [80.0, 90.0, 100.0],
            "P_electrical_W": [100.0] * 3,
            "P_shaft_W": [50.0] * 3,
            "fault_alarm": [False, False, True],
            "fault_cooling_detected": [False, False, True],
            "speed_reference_rad_s": [10.0] * 3,
            "omega_rad_s": [10.0, 9.0, 8.0],
            "u_load_torque_pu": [1.0, 0.9, 0.8],
            "controller_derating_fraction": [0.0, 0.1, 0.2],
            "controller_operating_mode": ["NORMAL", "NORMAL", "EMERGENCY"],
            "solver_step_time_s": [0.01] * 3,
            "thermal_warning_detected": [False, False, True],
            "torque_load_Nm": [10.0] * 3,
            "torque_command_Nm": [10.0] * 3,
            "fault_severity_estimated": [0.0, 0.1, 0.3],
            "fault_severity_true": [0.0, 0.5, 0.5],
            "loop_compute_latency_ms": [1.0, 2.0, 3.0],
        }
    )


def test_metrics_integrate_sample_intervals_and_measure_detection() -> None:
    metrics = compute_experiment_metrics(
        _sample_frame(),
        fault_injection_time_s=1.0,
        safe_temp_threshold_c=105.0,
        nominal_temp_c=95.0,
        intervention_temp_c=85.0,
        buffered_temp_c=98.0,
    )

    assert metrics["simulation_duration_s"] == pytest.approx(3.0)
    assert metrics["faulted_interval_duration_s"] == pytest.approx(2.0)
    assert metrics["time_above_intervention_s"] == pytest.approx(2.0)
    assert metrics["electrical_energy_kWh"] == pytest.approx(100 / 1_200_000)
    assert metrics["useful_mechanical_work_kWh"] == pytest.approx(
        50 / 1_200_000
    )
    assert metrics["electrical_energy_to_useful_work_ratio"] == pytest.approx(2.0)
    assert metrics["fault_detection_latency_s"] == pytest.approx(1.0)
    assert metrics["fault_detection_precision"] == pytest.approx(1.0)
    assert metrics["fault_detection_recall"] == pytest.approx(0.5)
    assert metrics["winding_estimation_mae_C"] == pytest.approx(1.0)
    assert metrics["emergency_intervention_time_s"] == pytest.approx(1.0)
    assert math.isnan(metrics["prediction_mae_30s_C"])


def test_metrics_reject_invalid_sampling_and_non_finite_measurements() -> None:
    frame = _sample_frame()
    frame.loc[1, "sample_interval_s"] = 0.0
    with pytest.raises(ValueError, match="finite and positive"):
        compute_experiment_metrics(frame, fault_injection_time_s=1.0)

    frame = _sample_frame()
    frame.loc[1, "T_winding_C"] = float("inf")
    with pytest.raises(ValueError, match="finite numeric inputs"):
        compute_experiment_metrics(frame, fault_injection_time_s=1.0)
