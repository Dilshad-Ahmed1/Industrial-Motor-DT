from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


FAULT_DETECTION_COLUMNS = {
    "cooling": ("fault_cooling_detected",),
    "rth_degradation": ("fault_cooling_detected",),
    "sensor_bias": ("fault_sensor_bias_detected",),
    "sensor_freeze": ("fault_sensor_freeze_detected",),
    "voltage_imbalance": ("fault_voltage_imbalance_detected",),
    "supply_degradation": ("fault_supply_degradation_detected",),
    "frequency_deviation": ("fault_frequency_deviation_detected",),
    "overload": ("fault_overload_detected",),
    "mechanical_friction": ("fault_mechanical_friction_detected",),
    "combined_supported": (
        "fault_sensor_bias_detected",
        "fault_cooling_detected",
        "fault_supply_degradation_detected",
        "fault_overload_detected",
    ),
}


def _rmse(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(values)))) if values.size else float("nan")


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator > 0.0 else float("nan")


def _forecast_errors(
    times: np.ndarray,
    predictions: np.ndarray,
    actual: np.ndarray,
    horizon_s: float,
) -> tuple[float, float]:
    errors: list[float] = []
    median_step = float(np.median(np.diff(times)))
    tolerance = max(1e-9, median_step * 0.51)
    for index, current_time in enumerate(times):
        target_time = current_time + horizon_s
        future_index = int(np.searchsorted(times, target_time))
        if future_index >= len(times):
            continue
        if abs(times[future_index] - target_time) > tolerance:
            continue
        errors.append(float(predictions[index] - actual[future_index]))
    values = np.asarray(errors, dtype=float)
    return (
        float(np.mean(np.abs(values))) if values.size else float("nan"),
        _rmse(values),
    )


def compute_experiment_metrics(
    df: pd.DataFrame,
    fault_injection_time_s: float,
    safe_temp_threshold_c: float = 120.0,
    nominal_temp_c: float = 100.0,
    intervention_temp_c: float = 90.0,
    buffered_temp_c: float = 115.0,
) -> dict[str, Any]:
    if df.empty:
        raise ValueError("Experiment dataframe is empty.")
    required = {
        "time_s",
        "sample_interval_s",
        "fault_active",
        "fault_input_active_for_next_interval",
        "fault_type",
        "fault_severity_true",
        "fault_severity_estimated",
        "T_winding_C",
        "T_frame_C",
        "estimated_winding_C",
        "estimated_frame_C",
        "predicted_30s_C",
        "predicted_60s_C",
        "P_electrical_W",
        "P_shaft_W",
        "fault_alarm",
        "loop_compute_latency_ms",
        "speed_reference_rad_s",
        "omega_rad_s",
        "u_load_torque_pu",
        "controller_derating_fraction",
        "controller_operating_mode",
        "solver_step_time_s",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise KeyError(f"Experiment results are missing metric inputs: {missing}")

    d = df.sort_values("time_s").reset_index(drop=True)
    numeric_columns = required - {
        "fault_type",
        "controller_operating_mode",
    }
    numeric_values = d[list(numeric_columns)].apply(
        pd.to_numeric,
        errors="coerce",
    ).to_numpy(dtype=float)
    if not np.isfinite(numeric_values).all():
        raise ValueError("Experiment metrics require finite numeric inputs.")
    times = d["time_s"].to_numpy(dtype=float)
    if len(times) > 1 and np.any(np.diff(times) <= 0.0):
        raise ValueError("Experiment sample times must be strictly increasing.")
    intervals = d["sample_interval_s"].to_numpy(dtype=float)
    if np.any(~np.isfinite(intervals)) or np.any(intervals <= 0.0):
        raise ValueError("Sample intervals must be finite and positive.")
    if len(times) > 1 and not np.allclose(
        intervals[:-1],
        np.diff(times),
        rtol=1e-7,
        atol=1e-9,
    ):
        raise ValueError(
            "Sample intervals do not match consecutive sample timestamps."
        )
    thresholds = (
        intervention_temp_c,
        nominal_temp_c,
        buffered_temp_c,
        safe_temp_threshold_c,
    )
    if not np.isfinite(thresholds).all() or not (
        intervention_temp_c
        <= nominal_temp_c
        <= buffered_temp_c
        <= safe_temp_threshold_c
    ):
        raise ValueError(
            "Thermal thresholds must be finite and ordered intervention "
            "<= warning <= buffered safety <= critical."
        )
    duration_s = float(np.sum(intervals))
    if duration_s <= 0.0:
        raise ValueError("Experiment duration must be positive.")

    winding = d["T_winding_C"].to_numpy(dtype=float)
    frame = d["T_frame_C"].to_numpy(dtype=float)
    fault_truth = d["fault_active"].astype(bool).to_numpy()
    fault_interval = d[
        "fault_input_active_for_next_interval"
    ].astype(bool).to_numpy()
    scenario = str(d["fault_type"].iloc[0])

    def time_above(signal: np.ndarray, threshold: float) -> float:
        return float(np.sum(intervals[signal >= threshold]))

    thresholds = {
        "intervention": intervention_temp_c,
        "warning": nominal_temp_c,
        "buffered_safety": buffered_temp_c,
        "critical": safe_temp_threshold_c,
    }
    thermal_times = {
        name: time_above(winding, threshold)
        for name, threshold in thresholds.items()
    }
    post_indices = np.flatnonzero(fault_truth)
    if post_indices.size:
        first_fault_index = int(post_indices[0])
        post_winding = winding[first_fault_index:]
        post_intervals = intervals[first_fault_index:]
        post_critical_time = float(
            np.sum(post_intervals[post_winding >= safe_temp_threshold_c])
        )
    else:
        first_fault_index = len(d)
        post_critical_time = 0.0

    buffered_exceedances = np.flatnonzero(
        fault_truth & (winding >= buffered_temp_c)
    )
    if not buffered_exceedances.size:
        time_to_safe_s = 0.0
    else:
        last_unsafe_index = int(buffered_exceedances[-1])
        returned_indices = np.flatnonzero(
            (np.arange(len(d)) > last_unsafe_index)
            & (winding < buffered_temp_c)
        )
        time_to_safe_s = (
            float(times[returned_indices[0]] - fault_injection_time_s)
            if returned_indices.size
            else float("nan")
        )

    alarm = d["fault_alarm"].astype(bool).to_numpy()
    pre_fault_alarm_events = int(
        np.count_nonzero(
            alarm[~fault_truth][1:] & ~alarm[~fault_truth][:-1]
        )
    ) if np.count_nonzero(~fault_truth) > 1 else int(
        bool(alarm[~fault_truth][0]) if np.any(~fault_truth) else False
    )
    post_alarm_events = int(
        np.count_nonzero(
            alarm[fault_truth][1:] & ~alarm[fault_truth][:-1]
        )
    ) if np.count_nonzero(fault_truth) > 1 else int(
        bool(alarm[fault_truth][0]) if np.any(fault_truth) else False
    )

    detection_columns = FAULT_DETECTION_COLUMNS.get(scenario)
    if detection_columns:
        missing_detections = sorted(set(detection_columns) - set(d.columns))
        if missing_detections:
            raise KeyError(
                f"Scenario {scenario!r} lacks detection channels: "
                f"{missing_detections}"
            )
        detected = d[list(detection_columns)].fillna(False).astype(bool).any(
            axis=1
        ).to_numpy()
    else:
        detected = alarm
    true_positive = int(np.count_nonzero(fault_truth & detected))
    false_positive = int(np.count_nonzero(~fault_truth & detected))
    false_negative = int(np.count_nonzero(fault_truth & ~detected))
    true_negative = int(np.count_nonzero(~fault_truth & ~detected))
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if np.isfinite(precision) and np.isfinite(recall)
        and precision + recall > 0.0
        else float("nan")
    )
    detected_fault_indices = np.flatnonzero(fault_truth & detected)
    detection_latency_s = (
        float(times[detected_fault_indices[0]] - fault_injection_time_s)
        if detected_fault_indices.size
        else float("nan")
    )

    thermal_warning_detected = (
        d["thermal_warning_detected"].astype(bool).to_numpy()
        if "thermal_warning_detected" in d
        else np.zeros(len(d), dtype=bool)
    )
    risk_crossings = np.flatnonzero(winding >= intervention_temp_c)
    risk_detection_indices = np.flatnonzero(thermal_warning_detected)
    time_to_risk_detection_s = float("nan")
    if risk_crossings.size:
        after_crossing = risk_detection_indices[
            risk_detection_indices >= risk_crossings[0]
        ]
        if after_crossing.size:
            time_to_risk_detection_s = float(
                times[after_crossing[0]] - times[risk_crossings[0]]
            )

    electrical_energy_kwh = float(
        np.sum(d["P_electrical_W"].to_numpy(dtype=float) * intervals)
        / 3_600_000.0
    )
    useful_work_kwh = float(
        np.sum(np.maximum(0.0, d["P_shaft_W"].to_numpy(dtype=float)) * intervals)
        / 3_600_000.0
    )
    post_mask = fault_interval
    electrical_post_fault_kwh = float(
        np.sum(
            d.loc[post_mask, "P_electrical_W"].to_numpy(dtype=float)
            * intervals[post_mask]
        )
        / 3_600_000.0
    )
    useful_work_post_fault_kwh = float(
        np.sum(
            np.maximum(
                0.0,
                d.loc[post_mask, "P_shaft_W"].to_numpy(dtype=float),
            )
            * intervals[post_mask]
        )
        / 3_600_000.0
    )

    actual_winding = winding
    winding_error = (
        d["estimated_winding_C"].to_numpy(dtype=float) - actual_winding
    )
    frame_error = d["estimated_frame_C"].to_numpy(dtype=float) - frame
    times30_mae, times30_rmse = _forecast_errors(
        times,
        d["predicted_30s_C"].to_numpy(dtype=float),
        actual_winding,
        30.0,
    )
    times60_mae, times60_rmse = _forecast_errors(
        times,
        d["predicted_60s_C"].to_numpy(dtype=float),
        actual_winding,
        60.0,
    )

    speed_error = (
        d["omega_rad_s"].to_numpy(dtype=float)
        - d["speed_reference_rad_s"].to_numpy(dtype=float)
    )
    torque_error = (
        d["torque_load_Nm"].to_numpy(dtype=float)
        - d["torque_command_Nm"].to_numpy(dtype=float)
        if "torque_command_Nm" in d
        else np.asarray([], dtype=float)
    )
    solver_seconds = float(d["solver_step_time_s"].sum())
    reduced_load = d["u_load_torque_pu"].to_numpy(dtype=float) < 0.999
    emergency_modes = d["controller_operating_mode"].isin(
        ("EMERGENCY", "EMERGENCY_DERATING")
    ).to_numpy()
    return {
        "simulation_duration_s": duration_s,
        "sample_count": int(len(d)),
        "faulted_interval_duration_s": float(np.sum(intervals[fault_interval])),
        "max_winding_temperature_C": float(np.max(winding)),
        "max_frame_temperature_C": float(np.max(frame)),
        "time_above_intervention_s": thermal_times["intervention"],
        "time_above_intervention_percent": 100.0
        * thermal_times["intervention"] / duration_s,
        "time_above_warning_s": thermal_times["warning"],
        "time_above_warning_percent": 100.0
        * thermal_times["warning"] / duration_s,
        "time_above_buffered_safety_s": thermal_times["buffered_safety"],
        "time_above_buffered_safety_percent": 100.0
        * thermal_times["buffered_safety"] / duration_s,
        "time_above_critical_s": thermal_times["critical"],
        "time_above_critical_percent": 100.0
        * thermal_times["critical"] / duration_s,
        "critical_limit_violation": bool(thermal_times["critical"] > 0.0),
        "post_fault_time_above_critical_s": post_critical_time,
        "minimum_thermal_margin_C": float(
            safe_temp_threshold_c - np.max(winding)
        ),
        "time_to_thermal_risk_detection_s": time_to_risk_detection_s,
        "time_to_return_below_buffered_safety_s": time_to_safe_s,
        "fault_detection_latency_s": detection_latency_s,
        "true_positive_samples": true_positive,
        "false_positive_samples": false_positive,
        "true_negative_samples": true_negative,
        "false_negative_samples": false_negative,
        "fault_detection_precision": precision,
        "fault_detection_recall": recall,
        "fault_detection_f1": f1,
        "pre_fault_alarm_events": pre_fault_alarm_events,
        "post_fault_alarm_events": post_alarm_events,
        "missed_fault": bool(np.any(fault_truth) and false_negative > 0),
        "electrical_energy_kWh": electrical_energy_kwh,
        "useful_mechanical_work_kWh": useful_work_kwh,
        "electrical_energy_to_useful_work_ratio": _ratio(
            electrical_energy_kwh, useful_work_kwh
        ),
        "post_fault_electrical_energy_kWh": electrical_post_fault_kwh,
        "post_fault_useful_work_kWh": useful_work_post_fault_kwh,
        "speed_rmse_rad_s": _rmse(speed_error),
        "torque_command_rmse_Nm": _rmse(torque_error),
        "torque_command_mae_Nm": float(np.mean(np.abs(torque_error)))
        if torque_error.size
        else float("nan"),
        "winding_estimation_mae_C": float(np.mean(np.abs(winding_error))),
        "winding_estimation_rmse_C": _rmse(winding_error),
        "frame_estimation_mae_C": float(np.mean(np.abs(frame_error))),
        "frame_estimation_rmse_C": _rmse(frame_error),
        "prediction_mae_30s_C": times30_mae,
        "prediction_rmse_30s_C": times30_rmse,
        "prediction_mae_60s_C": times60_mae,
        "prediction_rmse_60s_C": times60_rmse,
        "mean_load_command_pu": float(d["u_load_torque_pu"].mean()),
        "mean_load_command_pu_post_fault_interval": float(
            np.average(
                d["u_load_torque_pu"].to_numpy(dtype=float)[fault_interval],
                weights=intervals[fault_interval],
            )
        )
        if np.any(fault_interval)
        else float("nan"),
        "mean_controller_derating_fraction": float(
            np.average(
                d["controller_derating_fraction"].to_numpy(dtype=float),
                weights=intervals,
            )
        ),
        "mean_controller_derating_fraction_post_fault": float(
            np.average(
                d["controller_derating_fraction"].to_numpy(dtype=float)[
                    fault_interval
                ],
                weights=intervals[fault_interval],
            )
        )
        if np.any(fault_interval)
        else float("nan"),
        "time_at_reduced_load_s": float(np.sum(intervals[reduced_load])),
        "reduced_load_time_percent": 100.0
        * float(np.sum(intervals[reduced_load]))
        / duration_s,
        "emergency_intervention_time_s": float(
            np.sum(intervals[emergency_modes])
        ),
        "emergency_fraction": float(
            np.sum(intervals[emergency_modes]) / duration_s
        ),
        "mean_injected_severity_index_post_fault": float(
            d.loc[fault_truth, "fault_severity_true"].mean()
        )
        if np.any(fault_truth)
        else float("nan"),
        "mean_estimated_anomaly_severity_score_post_fault": float(
            d.loc[fault_truth, "fault_severity_estimated"].mean()
        )
        if np.any(fault_truth)
        else float("nan"),
        "mean_loop_compute_latency_ms": float(
            d["loop_compute_latency_ms"].mean()
        ),
        "mean_solver_step_time_ms": 1000.0 * solver_seconds / len(d),
        "real_time_factor": duration_s / max(solver_seconds, 1e-12),
        "warning_threshold_C": nominal_temp_c,
        "intervention_threshold_C": intervention_temp_c,
        "buffered_safety_threshold_C": buffered_temp_c,
        "critical_threshold_C": safe_temp_threshold_c,
    }
