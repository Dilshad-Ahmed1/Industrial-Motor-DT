from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from analysis.experiment_metrics import compute_experiment_metrics
from control.adaptive_controller import FaultAwareAdaptiveController
from integration.basyx_bridge import BaSyxBridge
from control.baseline_controller import (
    BaselineThresholdController,
    ControlCommand,
)
from simulation.fmu_runtime import FMURuntime
from twin.fault_detector import FaultDetector
from twin.fault_severity import estimate_fault_severity
from twin.predictor import ThermalPredictor
from twin.state_estimator import ThermalStateEstimator
from analysis.basyx_metrics import BaSyxEvaluationMetrics


# ---------------------------------------------------------------------------
# Scenario definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scenario:
    sensor_bias_C: float = 0.0
    sensor_freeze: bool = False
    cooling_efficiency: float = 1.0
    rth_degradation: float = 1.0
    unbalance_severity: float = 0.0
    truth_severity: float = 0.0


SCENARIOS: dict[str, Scenario] = {
    "healthy": Scenario(),

    "sensor_bias": Scenario(
        sensor_bias_C=10.0,
        truth_severity=1.0,
    ),

    "sensor_freeze": Scenario(
        sensor_freeze=True,
        truth_severity=1.0,
    ),

    "cooling": Scenario(
        cooling_efficiency=0.40,
        truth_severity=0.60,
    ),

    "rth_degradation": Scenario(
        rth_degradation=2.0,
        truth_severity=0.50,
    ),

    "unbalance": Scenario(
        unbalance_severity=0.75,
        truth_severity=0.75,
    ),

    "combined": Scenario(
        sensor_bias_C=10.0,
        cooling_efficiency=0.40,
        unbalance_severity=0.75,
        truth_severity=1.0,
    ),
}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_project_config() -> dict[str, Any]:
    """
    Load project configuration if available.

    The experiment remains runnable even if the YAML file does not exist.
    """
    path = Path("config/twin_config.yaml")

    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ---------------------------------------------------------------------------
# Fault injection
# ---------------------------------------------------------------------------

def _fault_inputs(
    scenario: Scenario,
    active: bool,
) -> dict[str, Any]:
    """
    Convert a scenario definition into FMU fault parameters.

    The controller/twin never receives these truth values directly.
    They are used only for plant fault injection.
    """
    if not active:
        return {
            "f_sensor_bias_C": 0.0,
            "f_sensor_freeze": False,
            "f_cooling_eff": 1.0,
            "f_rth_degradation": 1.0,
            "f_unbalance_severity": 0.0,
        }

    return {
        "f_sensor_bias_C": scenario.sensor_bias_C,
        "f_sensor_freeze": scenario.sensor_freeze,
        "f_cooling_eff": scenario.cooling_efficiency,
        "f_rth_degradation": scenario.rth_degradation,
        "f_unbalance_severity": scenario.unbalance_severity,
    }


# ---------------------------------------------------------------------------
# DataFrame validation
# ---------------------------------------------------------------------------

REQUIRED_LOG_COLUMNS = {
    # Time / experiment
    "time_s",
    "fault_active",
    "fault_type",
    "fault_severity_true",
    "controller",

    # Control
    "u_load_torque_pu",
    "u_speed_pu",
    "u_cooling_flow_pu",

    # IMPORTANT:
    # experiment_metrics.py explicitly requires this column.
    "speed_reference_pu",
    "speed_reference_rad_s",

    # Twin state estimation
    "estimated_winding_C",
    "estimated_frame_C",
    "estimated_winding_rate_C_s",
    "sensor_residual_C",
    "frame_model_residual_C",
    "frame_innovation_C",

    # Fault detection
    "fault_sensor_bias_detected",
    "fault_cooling_detected",
    "fault_unbalance_detected",
    "fault_alarm",
    "primary_fault",

    # Fault severity
    "fault_severity_sensor_bias",
    "fault_severity_cooling",
    "fault_severity_unbalance",
    "fault_severity_estimated",

    # Prediction
    "predicted_30s_C",
    "predicted_60s_C",

    # Runtime measurements
    "state_estimator_latency_ms",
    "fault_detection_latency_ms",
    "predictor_latency_ms",
    "controller_latency_ms",
    "loop_compute_latency_ms",
    "solver_step_time_s",

    # FMU outputs
    "T_winding_C",
    "T_frame_C",
    "T_sensor_C",
    "omega_rad_s",
    "speed_rpm",
    "torque_load_Nm",
    "torque_motor_Nm",
    "P_electrical_W",
    "P_shaft_W",
    "P_loss_total_W",
    "I_rms_A",
    "vibration_mm_s_out",
    "thermal_margin_to_critical_K",
    "thermal_state",
}


def validate_dataframe(df: pd.DataFrame) -> None:
    """
    Fail immediately with a useful message rather than allowing the
    metrics module to throw a KeyError later.
    """
    missing = sorted(REQUIRED_LOG_COLUMNS - set(df.columns))

    if missing:
        raise KeyError(
            "Experiment log is missing required columns:\n"
            + "\n".join(f"  - {name}" for name in missing)
        )



def build_basyx_snapshot(
    measurement: dict[str, float],
    estimate,
    detection,
    severity: dict[str, float],
    command,
    elapsed_energy_kwh: float,
    useful_work_kwh: float,
) -> dict[str, dict[str, object]]:
    """
    Convert the current Digital Twin state into the project's
    AAS submodel representation.

    IMPORTANT:
    The hidden FMU fault parameters are NOT published here.
    Diagnostic values come from the estimator/detector.
    """

    speed_rad_s = float(
        measurement["omega_rad_s"]
    )

    speed_rpm = float(
        measurement["speed_rpm"]
    )

    thermal_margin_K = float(
        measurement[
            "thermal_margin_to_critical_K"
        ]
    )

    # --------------------------------------------------------------
    # Operational
    # --------------------------------------------------------------

    operational = {
        "SpeedPu": (
            speed_rad_s / 152.890842
        ),
        "LoadTorquePu": (
            float(
                measurement[
                    "torque_load_Nm"
                ]
            ) / 35.973378
        ),
        "PowerLossActualW": float(
            measurement[
                "P_loss_total_W"
            ]
        ),
    }

    # --------------------------------------------------------------
    # Electrical
    # --------------------------------------------------------------

    electrical = {
        "VoltageRmsV": 400.0,

        "CurrentRmsA": float(
            measurement["I_rms_A"]
        ),

        "PowerFactor": 0.81,

        "ActivePowerW": float(
            measurement[
                "P_electrical_W"
            ]
        ),

        "ReactivePowerVar": 0.0,

        "TotalEnergyConsumedkWh": (
            elapsed_energy_kwh
        ),
    }

    # --------------------------------------------------------------
    # Mechanical
    # --------------------------------------------------------------

    mechanical = {
        "SpeedRpm": speed_rpm,

        "SpeedRadS": speed_rad_s,

        "ElectromagneticTorqueNm": float(
            measurement[
                "torque_motor_Nm"
            ]
        ),

        "LoadTorqueNm": float(
            measurement[
                "torque_load_Nm"
            ]
        ),

        "UsefulOutputWorkkWh": (
            useful_work_kwh
        ),

        "VibrationAmplitudeMmS": float(
            measurement[
                "vibration_mm_s_out"
            ]
        ),

        # Estimated—not hidden truth.
        "UnbalanceSeverity": float(
            severity[
                "mechanical_unbalance"
            ]
        ),
    }

    # --------------------------------------------------------------
    # Thermal
    # --------------------------------------------------------------

    thermal = {
        "WindingTemperatureK": (
            float(
                measurement[
                    "T_winding_C"
                ]
            )
            + 273.15
        ),

        "FrameTemperatureK": (
            float(
                measurement[
                    "T_frame_C"
                ]
            )
            + 273.15
        ),

        "WindingSensorMeasuredK": (
            float(
                measurement[
                    "T_sensor_C"
                ]
            )
            + 273.15
        ),

        "ThermalMarginK": (
            thermal_margin_K
        ),
    }

    # --------------------------------------------------------------
    # Fault
    # --------------------------------------------------------------

    fault = {
        # Observable sensor/model residual.
        "SensorBiasActiveK": abs(
            float(
                estimate.sensor_residual_C
            )
        ),

        # The present runner does not estimate freeze state.
        "SensorFreezeActive": False,

        # Estimated cooling factor, NOT FMU truth.
        "CoolingEfficiencyFactor": max(
            0.0,
            min(
                1.0,
                1.0
                - float(
                    severity[
                        "cooling_degradation"
                    ]
                ),
            ),
        ),

        "MechanicalUnbalanceActive": bool(
            detection.mechanical_unbalance
        ),

        "EstimatedFaultSeverity": float(
            severity["overall"]
        ),
    }

    # --------------------------------------------------------------
    # Control
    # --------------------------------------------------------------

    load_pu = float(
        command.load_pu
    )

    cooling_pu = float(
        command.cooling_flow_pu
    )

    if load_pu >= 0.99:
        operating_mode = "NORMAL"

    elif load_pu > 0.60:
        operating_mode = "ADAPTIVE_DERATE"

    else:
        operating_mode = "PROTECTIVE"

    control = {
        "CoolingCommandPu": cooling_pu,

        "LoadDeratingCommandPu": load_pu,

        "OperatingMode": operating_mode,
    }

    return {
        "thermal": thermal,
        "electrical": electrical,
        "mechanical": mechanical,
        "operational": operational,
        "fault": fault,
        "control": control,
    }


# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------

def run_experiment(
    fmu_path: Path,
    scenario_name: str,
    controller_name: str,
    stop_time: float,
    step: float,
    fault_time: float,
    output: Path,
    basyx_enabled: bool = False,
    basyx_host: str = "http://localhost:8081",
    basyx_period_s: float = 2.0,
    realtime: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any]]:

    # -------------------------
    # Validate CLI arguments
    # -------------------------

    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario_name}")

    if controller_name not in {
        "baseline",
        "adaptive",
        "constrained",
    }:
        raise ValueError(f"Unknown controller: {controller_name}")

    if stop_time <= 0:
        raise ValueError("stop_time must be > 0")

    if step <= 0:
        raise ValueError("step must be > 0")

    if fault_time < 0:
        raise ValueError("fault_time must be >= 0")

    # -------------------------
    # Configuration
    # -------------------------

    cfg = load_project_config()

    safety_cfg = cfg.get("safety", {})
    thermal_cfg = cfg.get("thermal_model", {})
    motor_cfg = cfg.get("motor", {})

    min_load = float(
        safety_cfg.get("minimum_load_pu", 0.50)
    )

    ref_load = float(
        safety_cfg.get("reference_load_pu", 1.00)
    )

    warning_C = float(
        safety_cfg.get("winding_warning_C", 100.0)
    )

    critical_C = float(
        safety_cfg.get("winding_critical_C", 120.0)
    )

    vib_warning = float(
        safety_cfg.get("vibration_warning_mm_s", 2.8)
    )

    ambient_C = float(
        thermal_cfg.get("ambient_temperature_C", 25.0)
    )

    rwf = float(
        thermal_cfg.get("winding_frame_Rth_K_per_W", 0.0400)
    )

    rfa = float(
        thermal_cfg.get("frame_ambient_Rth_K_per_W", 0.086672)
    )

    cw = float(
        thermal_cfg.get("winding_thermal_capacitance_J_per_K", 1500.0)
    )

    cf = float(
        thermal_cfg.get("frame_thermal_capacitance_J_per_K", 9000.0)
    )

    # WEG W22 reference motor.
    # 1460 rpm = 152.890842 rad/s.
    rated_speed_rpm = float(
        motor_cfg.get("rated_speed_rpm", 1460.0)
    )

    rated_omega_rad_s = (
        2.0
        * math.pi
        * rated_speed_rpm
        / 60.0
    )

    scenario = SCENARIOS[scenario_name]

    # -------------------------
    # Instantiate twin modules
    # -------------------------

    estimator = ThermalStateEstimator(
        ambient_C=ambient_C,
        r_winding_frame_K_W=rwf,
        r_frame_ambient_K_W=rfa,
        c_winding_J_K=cw,
        c_frame_J_K=cf,
    )

    predictor = ThermalPredictor(estimator)

    detector = FaultDetector(
        sensor_bias_threshold_C=6.0,
        cooling_residual_threshold_C=5.0,
        vibration_warning_mm_s=vib_warning,
        estimated_temp_warning_C=warning_C,
    )

    baseline = BaselineThresholdController(
        min_load,
        ref_load,
        warning_C,
        critical_C,
    )

    adaptive = FaultAwareAdaptiveController(
        min_load,
        ref_load,
        warning_C,
        critical_C,
    )

    # New safety-constrained predictive controller.
    from control.constrained_adaptive_controller import (
        ConstrainedAdaptiveController,
    )

    constrained = ConstrainedAdaptiveController(
        critical_temperature_C=critical_C,
        warning_temperature_C=warning_C,
        minimum_load_pu=0.70,
        maximum_load_pu=ref_load,
        minimum_cooling_pu=0.50,
        maximum_cooling_pu=1.00,
        safety_buffer_C=5.0,
    )

    if controller_name == "baseline":
        controller = baseline
    elif controller_name == "adaptive":
        controller = adaptive
    else:
        controller = constrained

    # -------------------------
    # Experiment storage
    # -------------------------

    rows: list[dict[str, Any]] = []

    basyx = None

    if basyx_enabled:
        print()
        print("[BaSyx] Initializing AAS synchronization...")

        basyx = BaSyxBridge(
            host=basyx_host
        )

        health = basyx.health_check()

        print(
            f"[BaSyx] Connected "
            f"({health['latency_ms']:.3f} ms)"
        )

    last_basyx_sync_t = -1e9

    basyx_sync_count = 0
    basyx_sync_failures = 0
    basyx_latency_ms = []

    basyx_metrics = (
    BaSyxEvaluationMetrics(
            environment_url=basyx_host,
            timeout_s=5.0,
        )
        if basyx_enabled
        else None
    )

    realtime_wall_start = None
    realtime_wall_elapsed_s = None
    realtime_deadline_misses = 0
    realtime_cycle_latencies_ms: list[float] = []

    # -------------------------
    # FMU runtime
    # -------------------------

    with FMURuntime(
        fmu_path,
        stop_time=stop_time,
    ) as runtime:

        # Initial healthy measurement at t = 0.
        measurement = runtime.initialize()

        # Initialize the digital-twin observer.
        estimator.initialize_from_measurement(
            measurement
        )

        # Initial command.
        current_command = ControlCommand(
            load_pu=ref_load,
            speed_pu=1.0,
            cooling_flow_pu=1.0,
        )

        elapsed_energy_kwh = 0.0
        useful_work_kwh = 0.0

        # Reset the constrained controller ONCE before the experiment.
        # Do NOT reset it inside the control loop because that would
        # destroy its rate-limiting / stateful behavior every timestep.
        if controller_name == "constrained":
            constrained.reset()

        # ---------------------------------------------------------------
        # Closed-loop simulation
        # ---------------------------------------------------------------

        if realtime:
            realtime_wall_start = time.perf_counter()

        while runtime.current_time < stop_time - 1e-12:

            # Current simulation instant.
            t = runtime.current_time

            if realtime and realtime_wall_start is not None:
                scheduled_start = realtime_wall_start + t
                wait_s = scheduled_start - time.perf_counter()
                if wait_s > 0.0:
                    time.sleep(wait_s)
                cycle_wall_start = time.perf_counter()
            else:
                cycle_wall_start = time.perf_counter()

            # Fault state is determined from simulation time.
            fault_active = t >= fault_time

            # -----------------------------------------------------------
            # 1. STATE ESTIMATION
            # -----------------------------------------------------------

            t0 = time.perf_counter()

            estimate = estimator.update(
                measurement=measurement,
                cooling_flow_pu=current_command.cooling_flow_pu,
                dt_s=step,
            )

            estimator_latency_ms = (
                time.perf_counter() - t0
            ) * 1000.0

            # -----------------------------------------------------------
            # 2. FAULT DETECTION + SEVERITY
            # -----------------------------------------------------------

            t0 = time.perf_counter()

            detection = detector.detect(
                estimate,
                measurement,
            )

            severity = estimate_fault_severity(
                estimate,
                detection,
                measurement,
            )

            detection_latency_ms = (
                time.perf_counter() - t0
            ) * 1000.0

            # -----------------------------------------------------------
            # 3. THERMAL PREDICTION
            # -----------------------------------------------------------

            t0 = time.perf_counter()

            forecast = predictor.predict(
                measurement,
                current_command.cooling_flow_pu,
            )

            predictor_latency_ms = (
                time.perf_counter() - t0
            ) * 1000.0

            # -----------------------------------------------------------
            # 4. CONTROLLER
            # -----------------------------------------------------------

            t0 = time.perf_counter()

            if controller_name == "baseline":

                next_command = controller.compute(
                    measurement
                )

                controller_load_command_pu = float(
                    next_command.load_pu
                )

                controller_cooling_command_pu = float(
                    next_command.cooling_flow_pu
                )

                controller_operating_mode = (
                    "NORMAL"
                    if next_command.load_pu >= 0.99
                    else "PROTECTIVE"
                )

                controller_derating_fraction = max(
                    0.0,
                    min(
                        1.0,
                        1.0 - (
                            next_command.load_pu
                            / max(ref_load, 1e-9)
                        ),
                    ),
                )

                controller_predicted_temperature_C = float(
                    max(
                        forecast.predicted_30s_C,
                        forecast.predicted_60s_C,
                    )
                )

                controller_safety_margin_C = (
                    critical_C
                    - controller_predicted_temperature_C
                )

            elif controller_name == "adaptive":

                next_command = controller.compute(
                    estimate,
                    detection,
                    severity,
                    forecast,
                )

                controller_load_command_pu = float(
                    next_command.load_pu
                )

                controller_cooling_command_pu = float(
                    next_command.cooling_flow_pu
                )

                controller_operating_mode = (
                    "NORMAL"
                    if next_command.load_pu >= 0.99
                    else "ADAPTIVE_DERATE"
                )

                controller_derating_fraction = max(
                    0.0,
                    min(
                        1.0,
                        1.0 - (
                            next_command.load_pu
                            / max(ref_load, 1e-9)
                        ),
                    ),
                )

                controller_predicted_temperature_C = float(
                    max(
                        forecast.predicted_30s_C,
                        forecast.predicted_60s_C,
                    )
                )

                controller_safety_margin_C = (
                    critical_C
                    - controller_predicted_temperature_C
                )

            else:

                # Sensor reliability is reduced when the diagnostic
                # system identifies a sensor-bias condition.
                sensor_reliability = (
                    0.5
                    if detection.sensor_bias
                    else 1.0
                )

                # Convert estimated cooling degradation severity
                # into an estimated remaining cooling efficiency.
                estimated_cooling_efficiency = max(
                    0.05,
                    min(
                        1.0,
                        1.0
                        - float(
                            severity[
                                "cooling_degradation"
                            ]
                        ),
                    ),
                )

                constrained_result = constrained.update(
                    commanded_load_pu=ref_load,
                    estimated_temperature_C=float(
                        estimate.estimated_winding_C
                    ),
                    predicted_temperature_30s_C=float(
                        forecast.predicted_30s_C
                    ),
                    predicted_temperature_60s_C=float(
                        forecast.predicted_60s_C
                    ),
                    fault_severity=float(
                        severity["overall"]
                    ),
                    cooling_efficiency=(
                        estimated_cooling_efficiency
                    ),
                    sensor_reliability=sensor_reliability,
                )

                next_command = ControlCommand(
                    load_pu=constrained_result.load_command_pu,
                    speed_pu=1.0,
                    cooling_flow_pu=(
                        constrained_result.cooling_command_pu
                    ),
                )

                controller_load_command_pu = float(
                    constrained_result.load_command_pu
                )

                controller_cooling_command_pu = float(
                    constrained_result.cooling_command_pu
                )

                controller_operating_mode = (
                    constrained_result.operating_mode
                )

                controller_derating_fraction = float(
                    constrained_result.derating_fraction
                )

                controller_predicted_temperature_C = float(
                    constrained_result.predicted_temperature_C
                )

                controller_safety_margin_C = float(
                    constrained_result.safety_margin_C
                )

            controller_latency_ms = (
                time.perf_counter() - t0
            ) * 1000.0

            # -----------------------------------------------------------
            # 5. APPLY FAULT + CONTROL INPUTS
            # -----------------------------------------------------------

            fault_inputs = _fault_inputs(
                scenario,
                fault_active,
            )

            inputs = {
                "u_load_torque_pu": next_command.load_pu,
                "u_speed_pu": next_command.speed_pu,
                "u_cooling_flow_pu": next_command.cooling_flow_pu,
                **fault_inputs,
            }

            # ------------------------------------------------------------
            # 6. SYNCHRONIZE AAS SNAPSHOT AT THE CURRENT TIME
            # ------------------------------------------------------------

            # The measurement, estimate, diagnosis, severity and command
            # all describe the same pre-step simulation instant t.
            if (
                basyx_enabled
                and basyx is not None
                and basyx_metrics is not None
                and (
                    t - last_basyx_sync_t
                    >= basyx_period_s - 1e-12
                )
            ):
                snapshot = build_basyx_snapshot(
                    measurement=measurement,
                    estimate=estimate,
                    detection=detection,
                    severity=severity,
                    command=next_command,
                    elapsed_energy_kwh=elapsed_energy_kwh,
                    useful_work_kwh=useful_work_kwh,
                )

                controller_only_latency_ms = float(
                    estimator_latency_ms
                    + detection_latency_ms
                    + predictor_latency_ms
                    + controller_latency_ms
                )

                sync_measurement = basyx_metrics.record_sync(
                    simulation_time_s=float(t),
                    controller_only_latency_ms=controller_only_latency_ms,
                    update_snapshot=lambda: basyx.update_snapshot(
                        **snapshot
                    ),
                    snapshot=snapshot,
                )

                if sync_measurement["update_success"]:
                    basyx_sync_count += 1
                    basyx_latency_ms.append(
                        sync_measurement["write_latency_ms"]
                    )

                    print(
                        f"[BaSyx] "
                        f"t={t:7.1f}s | "
                        f"write={sync_measurement['write_latency_ms']:.2f} ms | "
                        f"read={sync_measurement['read_latency_ms']:.2f} ms | "
                        f"e2e={sync_measurement['end_to_end_loop_latency_ms']:.2f} ms"
                    )
                else:
                    basyx_sync_failures += 1

                    print(
                        "[BaSyx] Synchronization failed: "
                        f"{sync_measurement['error']}"
                    )

                last_basyx_sync_t = t

            # -----------------------------------------------------------
            # 7. ADVANCE FMU
            # -----------------------------------------------------------

            actual_step = min(
                step,
                stop_time - t,
            )

            elapsed_energy_kwh += (
                max(
                    0.0,
                    float(
                        measurement["P_electrical_W"]
                    ),
                )
                * actual_step
                / 3_600_000.0
            )

            useful_work_kwh += (
                max(
                    0.0,
                    float(
                        measurement["P_shaft_W"]
                    ),
                )
                * actual_step
                / 3_600_000.0
            )

            post_measurement, solver_time_s = runtime.step(
                actual_step,
                inputs,
            )

            cycle_wall_end = time.perf_counter()
            realtime_cycle_latency_ms = (
                cycle_wall_end - cycle_wall_start
            ) * 1000.0
            realtime_deadline_ms = actual_step * 1000.0
            realtime_deadline_missed = int(
                realtime
                and realtime_cycle_latency_ms
                > realtime_deadline_ms + 1e-6
            )

            if realtime:
                realtime_cycle_latencies_ms.append(
                    realtime_cycle_latency_ms
                )
                realtime_deadline_misses += (
                    realtime_deadline_missed
                )

                if realtime_wall_start is not None:
                    scheduled_end = (
                        realtime_wall_start
                        + t
                        + actual_step
                    )
                    remaining_s = (
                        scheduled_end - time.perf_counter()
                    )
                    if remaining_s > 0.0:
                        time.sleep(remaining_s)

            # -----------------------------------------------------------
            # 7. LOG STATE AT THE CORRESPONDING SIMULATION TIME
            # -----------------------------------------------------------

            #
            # We log the measurement used by the estimator at time t,
            # not the post-step measurement at t + dt.
            #

            speed_reference_pu = float(
                next_command.speed_pu
            )

            speed_reference_rad_s = (
                speed_reference_pu
                * rated_omega_rad_s
            )

            row = {
                # -------------------------------------------------------
                # Time / scenario
                # -------------------------------------------------------

                "time_s": t,

                "fault_active": fault_active,

                "fault_type": scenario_name,

                # Ground truth is logged only for evaluation.
                "fault_severity_true_sensor_bias": (
                    min(
                        abs(scenario.sensor_bias_C) / 10.0,
                        1.0,
                    )
                    if fault_active
                    else 0.0
                ),

                "fault_severity_true_cooling": (
                    max(
                        0.0,
                        1.0 - scenario.cooling_efficiency,
                    )
                    if fault_active
                    else 0.0
                ),

                "fault_severity_true_unbalance": (
                    scenario.unbalance_severity
                    if fault_active
                    else 0.0
                ),

                "fault_severity_true": (
                    max(
                        min(
                            abs(
                                scenario.sensor_bias_C
                            ) / 10.0,
                            1.0,
                        ),
                        max(
                            0.0,
                            1.0
                            - scenario.cooling_efficiency,
                        ),
                        scenario.unbalance_severity,
                    )
                    if fault_active
                    else 0.0
                ),

                "frame_innovation_C": float(
                    estimate.frame_innovation_C
                ),

                "controller": controller_name,

                # -------------------------------------------------------
                # Control
                # -------------------------------------------------------

                "u_load_torque_pu": float(
                    next_command.load_pu
                ),

                "u_speed_pu": float(
                    next_command.speed_pu
                ),

                "u_cooling_flow_pu": float(
                    next_command.cooling_flow_pu
                ),

                "speed_reference_pu": (
                    speed_reference_pu
                ),

                "speed_reference_rad_s": (
                    speed_reference_rad_s
                ),

                # -------------------------------------------------------
                # Constrained controller diagnostics
                # -------------------------------------------------------

                "controller_load_command_pu": (
                    controller_load_command_pu
                ),

                "controller_cooling_command_pu": (
                    controller_cooling_command_pu
                ),

                "controller_operating_mode": (
                    controller_operating_mode
                ),

                "controller_derating_fraction": (
                    controller_derating_fraction
                ),

                "controller_predicted_temperature_C": (
                    controller_predicted_temperature_C
                ),

                "controller_safety_margin_C": (
                    controller_safety_margin_C
                ),

                # -------------------------------------------------------
                # Twin state estimate
                # -------------------------------------------------------

                "estimated_winding_C": float(
                    estimate.estimated_winding_C
                ),

                "estimated_frame_C": float(
                    estimate.estimated_frame_C
                ),

                "estimated_winding_rate_C_s": float(
                    estimate.estimated_winding_rate_C_s
                ),

                "sensor_residual_C": float(
                    estimate.sensor_residual_C
                ),

                "frame_model_residual_C": float(
                    estimate.frame_model_residual_C
                ),

                # -------------------------------------------------------
                # Fault detector
                # -------------------------------------------------------

                "fault_sensor_bias_detected": bool(
                    detection.sensor_bias
                ),

                "fault_cooling_detected": bool(
                    detection.cooling_degradation
                ),

                "fault_unbalance_detected": bool(
                    detection.mechanical_unbalance
                ),

                "fault_alarm": bool(
                    detection.alarm
                ),

                "primary_fault": str(
                    detection.primary_fault
                ),

                # -------------------------------------------------------
                # Fault severity
                # -------------------------------------------------------

                "fault_severity_sensor_bias": float(
                    severity["sensor_bias"]
                ),

                "fault_severity_cooling": float(
                    severity["cooling_degradation"]
                ),

                "fault_severity_unbalance": float(
                    severity["mechanical_unbalance"]
                ),

                "fault_severity_estimated": float(
                    severity["overall"]
                ),

                # -------------------------------------------------------
                # Prediction
                # -------------------------------------------------------

                "predicted_30s_C": float(
                    forecast.predicted_30s_C
                ),

                "predicted_60s_C": float(
                    forecast.predicted_60s_C
                ),

                # -------------------------------------------------------
                # Runtime timing
                # -------------------------------------------------------

                "state_estimator_latency_ms": float(
                    estimator_latency_ms
                ),

                "fault_detection_latency_ms": float(
                    detection_latency_ms
                ),

                "predictor_latency_ms": float(
                    predictor_latency_ms
                ),

                "controller_latency_ms": float(
                    controller_latency_ms
                ),

                "loop_compute_latency_ms": float(
                    estimator_latency_ms
                    + detection_latency_ms
                    + predictor_latency_ms
                    + controller_latency_ms
                ),

                "solver_step_time_s": float(
                    solver_time_s
                ),

                "realtime_cycle_latency_ms": float(
                    realtime_cycle_latency_ms
                ),

                "realtime_deadline_ms": float(
                    realtime_deadline_ms
                ),

                "realtime_deadline_missed": int(
                    realtime_deadline_missed
                ),
            }

            # -----------------------------------------------------------
            # Add CURRENT FMU measurements
            # -----------------------------------------------------------

            row.update(measurement)

            rows.append(row)

            # -----------------------------------------------------------
            # 8. MOVE TO NEXT CONTROL CYCLE
            # -----------------------------------------------------------

            current_command = next_command
            measurement = post_measurement

        if realtime and realtime_wall_start is not None:
            realtime_wall_elapsed_s = (
                time.perf_counter() - realtime_wall_start
            )

    # -------------------------------------------------------------------
    # Build DataFrame
    # -------------------------------------------------------------------

    if not rows:
        raise RuntimeError(
            "Experiment completed without generating any data rows."
        )

    df = pd.DataFrame(rows)

    # -------------------------------------------------------------------
    # Verify all metric-required columns before writing anything
    # -------------------------------------------------------------------

    validate_dataframe(df)

    # -------------------------------------------------------------------
    # Save time-series data
    # -------------------------------------------------------------------

    output = Path(output).resolve()

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        output,
        index=False,
    )

    # -------------------------------------------------------------------
    # Calculate metrics
    # -------------------------------------------------------------------

    metrics = compute_experiment_metrics(
        df,
        fault_injection_time_s=fault_time,
        safe_temp_threshold_c=critical_C,
        nominal_temp_c=warning_C,
    )

    if realtime and realtime_wall_start is not None:
        realtime_wall_time_s = float(
            realtime_wall_elapsed_s or 0.0
        )
        latency_series = pd.Series(
            realtime_cycle_latencies_ms,
            dtype=float,
        )
        metrics.update(
            {
                "realtime_enabled": True,
                "realtime_wall_time_s": float(
                    realtime_wall_time_s
                ),
                "realtime_factor": float(
                    stop_time / max(realtime_wall_time_s, 1e-9)
                ),
                "realtime_deadline_ms": float(
                    step * 1000.0
                ),
                "realtime_deadline_misses": int(
                    realtime_deadline_misses
                ),
                "realtime_deadline_miss_rate_percent": (
                    float(realtime_deadline_misses)
                    / max(len(realtime_cycle_latencies_ms), 1)
                    * 100.0
                ),
                "realtime_cycle_latency_mean_ms": float(
                    latency_series.mean()
                ),
                "realtime_cycle_latency_p95_ms": float(
                    latency_series.quantile(0.95)
                ),
                "realtime_cycle_latency_max_ms": float(
                    latency_series.max()
                ),
            }
        )
    else:
        metrics["realtime_enabled"] = False


    if basyx_metrics is not None:
        basyx_detail_csv = output.with_name(
            f"{output.stem}_basyx_detail.csv"
        )

        basyx_summary_json = output.with_name(
            f"{output.stem}_basyx_summary.json"
        )

        basyx_summary = basyx_metrics.save(
            detail_csv=basyx_detail_csv,
            summary_json=basyx_summary_json,
        )

        metrics.update(
            {
                f"basyx_{key}": value
                for key, value in basyx_summary.items()
            }
        )

        print()
        print("BaSyx / AAS evaluation")
        print(
            "AAS write mean / P95        : "
            f"{basyx_summary['aas_write_latency_mean_ms']:.3f} / "
            f"{basyx_summary['aas_write_latency_p95_ms']:.3f} ms"
        )
        print(
            "AAS read mean / P95         : "
            f"{basyx_summary['aas_read_latency_mean_ms']:.3f} / "
            f"{basyx_summary['aas_read_latency_p95_ms']:.3f} ms"
        )
        print(
            "End-to-end DT loop mean     : "
            f"{basyx_summary['end_to_end_loop_mean_latency_ms']:.3f} ms"
        )
        print(
            "BaSyx overhead              : "
            f"{basyx_summary['basyx_overhead_mean_ms']:.3f} ms "
            f"({basyx_summary['basyx_overhead_percent']:.2f}%)"
        )
        print(
            "AAS update success rate     : "
            f"{basyx_summary['update_success_rate_percent']:.2f}%"
        )
        print(
            "Winding synchronization MAE : "
            f"{basyx_summary['sync_winding_temperature_C_mae']:.6f} °C"
        )
        print(
            "Load-command synchronization MAE: "
            f"{basyx_summary['sync_load_command_pu_mae']:.6f} pu"
        )
        print(f"BaSyx detailed log           : {basyx_detail_csv}")
        print(f"BaSyx summary                : {basyx_summary_json}")

    # Add constrained-controller metrics to the returned metric dictionary.
    metrics["controller"] = controller_name

    if "controller_safety_margin_C" in df.columns:
        metrics["minimum_controller_safety_margin_C"] = float(
            df["controller_safety_margin_C"].min()
        )

        metrics["mean_controller_safety_margin_C"] = float(
            df["controller_safety_margin_C"].mean()
        )

    if "controller_derating_fraction" in df.columns:
        metrics["mean_controller_derating_fraction"] = float(
            df["controller_derating_fraction"].mean()
        )

        metrics["max_controller_derating_fraction"] = float(
            df["controller_derating_fraction"].max()
        )

    if "controller_operating_mode" in df.columns:
        metrics["emergency_fraction"] = float(
            df["controller_operating_mode"]
            .isin(
                [
                    "EMERGENCY",
                    "EMERGENCY_DERATING",
                ]
            )
            .mean()
        )

    # -------------------------------------------------------------------
    # Console summary
    # -------------------------------------------------------------------

    print()
    print("=" * 72)
    print("EXPERIMENT COMPLETED")
    print("=" * 72)

    print(f"Scenario                     : {scenario_name}")
    print(f"Controller                   : {controller_name}")
    print(f"Simulation time              : {stop_time:.3f} s")
    print(f"Communication step           : {step:.3f} s")
    print(f"Fault injection time         : {fault_time:.3f} s")
    print(f"Rows                         : {len(df)}")
    print(f"Saved                        : {output}")

    print()

    print(
        "Max true winding temperature : "
        f"{df['T_winding_C'].max():.3f} °C"
    )

    print(
        "Max sensor temperature       : "
        f"{df['T_sensor_C'].max():.3f} °C"
    )

    print(
        "Max estimated temperature    : "
        f"{df['estimated_winding_C'].max():.3f} °C"
    )

    print(
        "Max predicted 30 s temp      : "
        f"{df['predicted_30s_C'].max():.3f} °C"
    )

    print(
        "Max predicted 60 s temp      : "
        f"{df['predicted_60s_C'].max():.3f} °C"
    )

    print(
        "Detection latency            : "
        f"{metrics['detection_latency_s']:.3f} s"
    )

    print(
        "State estimation MAE         : "
        f"{metrics['state_estimation_mae_C']:.3f} °C"
    )

    print(
        "Prediction MAE (30 s)        : "
        f"{metrics['prediction_mae_30s_C']:.3f} °C"
    )

    print(
        "Prediction MAE (60 s)        : "
        f"{metrics['prediction_mae_60s_C']:.3f} °C"
    )

    print(
        "Speed RMSE                   : "
        f"{metrics['speed_rmse_rad_s']:.6f} rad/s"
    )

    print(
        "Energy / useful work ratio    : "
        f"{metrics['energy_to_useful_work_ratio']:.6f}"
    )

    print(
        "Solver real-time factor      : "
        f"{metrics['real_time_factor']:.3f}"
    )

    if realtime:
        print(
            "Wall-clock real-time factor : "
            f"{metrics['realtime_factor']:.3f}"
        )
        print(
            "Wall-clock elapsed          : "
            f"{metrics['realtime_wall_time_s']:.3f} s"
        )
        print(
            "Wall-clock deadline misses  : "
            f"{metrics['realtime_deadline_misses']}"
        )
        print(
            "Wall-clock cycle mean / P95 : "
            f"{metrics['realtime_cycle_latency_mean_ms']:.3f} / "
            f"{metrics['realtime_cycle_latency_p95_ms']:.3f} ms"
        )

    if controller_name == "constrained":

        print(
            "Minimum safety margin        : "
            f"{metrics['minimum_controller_safety_margin_C']:.3f} °C"
        )

        print(
            "Mean derating fraction       : "
            f"{metrics['mean_controller_derating_fraction']:.4f}"
        )

        print(
            "Max derating fraction        : "
            f"{metrics['max_controller_derating_fraction']:.4f}"
        )

        print(
            "Emergency fraction           : "
            f"{metrics['emergency_fraction']:.4f}"
        )

    print("=" * 72)
    print()

    return df, metrics

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Closed-loop Digital Twin experiment runner "
            "using the shared FMU runtime."
        )
    )

    parser.add_argument(
        "--fmu",
        required=True,
        type=Path,
        help="Path to the FMI 2.0 Co-Simulation FMU.",
    )

    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        default="combined",
    )

    parser.add_argument(
        "--controller",
        choices=["baseline", "adaptive", "constrained"],
        default="constrained",
    )

    parser.add_argument(
        "--stop",
        type=float,
        default=1800.0,
    )

    parser.add_argument(
        "--step",
        type=float,
        default=0.5,
    )

    parser.add_argument(
        "--fault-time",
        type=float,
        default=600.0,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "results/experiment.csv"
        ),
    )


    parser.add_argument(
        "--basyx",
        action="store_true",
        help="Enable live BaSyx AAS synchronization.",
    )

    parser.add_argument(
        "--basyx-host",
        type=str,
        default="http://localhost:8081",
        help="BaSyx AAS Environment URL.",
    )

    parser.add_argument(
        "--basyx-period",
        type=float,
        default=2.0,
        help=(
            "Simulation-time interval between "
            "BaSyx synchronizations."
        ),
    )

    parser.add_argument(
        "--realtime",
        action="store_true",
        help=(
            "Pace the simulation against wall clock and record "
            "control-cycle deadline misses."
        ),
    )

    args = parser.parse_args()

    print(
        f"Scenario   : {args.scenario}"
    )

    print(
        f"Controller : {args.controller}"
    )

    print(
        f"Stop time  : {args.stop} s"
    )

    print(
        f"Step       : {args.step} s"
    )

    print(
        f"Fault time : {args.fault_time} s"
    )

    run_experiment(
        fmu_path=args.fmu.resolve(),
        scenario_name=args.scenario,
        controller_name=args.controller,
        stop_time=args.stop,
        step=args.step,
        fault_time=args.fault_time,
        output=args.output.resolve(),
        basyx_enabled=args.basyx,
        basyx_host=args.basyx_host,
        basyx_period_s=args.basyx_period,
        realtime=args.realtime,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())