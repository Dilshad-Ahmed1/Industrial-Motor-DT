# 18.5 kW Induction-Motor Digital Twin

This repository supports one executable plant: the 18.5 kW Modelica Standard
Library (MSL) squirrel-cage induction motor. The Digital Twin composes
`Modelica.Electrical.Machines.BasicMachines.InductionMachines.IM_SquirrelCage`;
MSL sources are not modified. The model is a simulation benchmark based on the
MSL `IMC_withLosses` example, not a manufacturer-identified motor.

## Architecture

```text
Modelica 3-phase IM_SquirrelCage + lumped winding/frame thermal network
          | FMI 2.0 Co-Simulation (InductionMotorDigitalTwin18kW.fmu)
          v
simulation/fmu_runtime.py
  typed I/O; each control interval subdivided into <= 0.1 s FMI steps
          v
experiments/experiment_runner.py
  measured sample -> thermal observer -> fault diagnosis/severity
  -> 30/60 s forecast -> baseline/adaptive/constrained controller
          +--> raw time-series CSV + per-run metrics JSON
          +--> six BaSyx AAS submodels with shared snapshot ID/time
          v
experiments/run_research_evaluation.py
  deterministic scenario/controller campaign + immutable run manifest
          v
analysis/generate_research_artifacts.py
  tables and plots regenerated from the saved raw time series
```

The six AAS submodels remain `OperationalState`, `ElectricalState`,
`MechanicalState`, `ThermalState`, `FaultState`, and `ControlInterface`.
Snapshot values are assembled from one pre-step simulation sample; all
submodels receive the same simulation time, UTC capture timestamp, and
snapshot ID. The bridge writes the six submodels and reads back values to
measure synchronization and alignment.

True FMU winding temperature and component-loss values are retained only in
the evaluation log. The estimator, detector, predictor, and controllers use
current measured channels, observer state, and model-based estimates; they do
not receive future plant values or the injected fault severity. Thermal
temperatures in the Twin/AAS represent estimates, with the sensor reading
reported separately. The true severity log/AAS value is evaluation ground
truth, not a controller input.

`u_speed_pu` is a supply V/f operating command, not a closed-loop shaft-speed
setpoint. All three controllers currently hold it at nominal; speed error is
reported relative to nominal rated speed. Baseline control uses the
temperature sensor with its diagnosed reliability, while adaptive and
constrained control also use observer, diagnosis, and forecast outputs. The
information difference is intentional and should be considered when
interpreting controller comparisons.

## Plant parameters and provenance

The reference point is 18,500 W shaft power, 400 V line-to-line RMS, 32.85 A,
50 Hz, four poles, 1462.5 rpm, 120.79 N·m shaft torque, power factor 0.898,
and efficiency 90.49%. The MSL example provides the reference equivalent
circuit and loss data. Reactances are converted to inductances with
`L = X / (2*pi*f)`. The nominal shaft torque is calculated from
`T = P / omega`; the electromagnetic torque is calculated from shaft torque
plus friction and stray-load loss torque.

Stator/rotor resistances, leakage and magnetizing inductances, rotor inertia,
core loss, friction loss, and stray-load loss are MSL example/reference
values or inherited MSL parameter-record defaults. The separate winding/frame
thermal capacitances and resistances, fault magnitudes, diagnostic thresholds,
and 100/120 °C warning/critical policy are explicit model/controller
assumptions, not verified motor ratings. The full parameter-by-parameter
provenance and nominal validation method are in
[INDUCTION_MOTOR_REFERENCE.md](./INDUCTION_MOTOR_REFERENCE.md).

## Fault model

| Scenario | Implemented mechanism |
|---|---|
| `healthy` | No injected fault |
| `cooling` | Reduces frame-to-ambient conductance |
| `rth_degradation` | Increases winding-to-frame thermal resistance |
| `sensor_bias` | Adds a bias to the temperature-sensor channel only |
| `sensor_freeze` | Freezes the sensor sample; plant temperatures continue changing |
| `voltage_imbalance` | Increases phase-A amplitude; filtered phase RMS values measure imbalance |
| `supply_degradation` | Reduces all three supply-phase amplitudes |
| `frequency_deviation` | Changes the three-phase supply frequency |
| `overload` | Raises applied shaft-load torque, within the actuator/safety limits |
| `mechanical_friction` | Adds speed-opposing shaft friction torque |
| `combined_supported` | Sensor bias, cooling degradation, overload, and voltage reduction |

The rotational plant has no radial degrees of freedom, so mechanical unbalance
and vibration are unsupported and are not simulated or reported. Fault
amplitudes are controlled stress-test assumptions, not calibrated field
severity. Cooling, overload, electrical supply, friction, and sensor faults
affect their documented physical or measurement channels; see the reference
document for signal-level detail and limitations.

## Setup and verification

Use Python 3.12 and install the declared packages with
`.\.venv\Scripts\python.exe -m pip install -r requirements.txt`. FMU export
requires OpenModelica 1.27.1 with MSL 4.1.0:

```powershell
.\.venv\Scripts\python.exe scripts\export_induction_fmu.py --overwrite
.\.venv\Scripts\python.exe scripts\validate_induction_motor_nominal.py
.\.venv\Scripts\python.exe -m pytest -q
```

Nominal validation exports and simulates the standalone induction-motor
reference case, compares voltage/current/frequency/speed/slip/torque/input
power/output power/efficiency/power factor/losses against the documented MSL
nominal operating point, checks stability, and saves the raw CSV and JSON
validation report in a new `results/induction_motor_nominal/run_*` folder.
Passing this simulation check is not experimental or manufacturer validation.

One closed-loop experiment can be run with:

```powershell
.\.venv\Scripts\python.exe -m experiments.experiment_runner `
  --fmu models\InductionMotorDigitalTwin18kW.fmu `
  --scenario cooling --controller constrained `
  --stop 2700 --fault-time 350 --step 0.5 `
  --output results\manual\cooling_constrained.csv
```

The runner refuses to overwrite output and rejects any FMU other than the
named induction plant. The default protocol is 350 s pre-fault and 2350 s
post-fault, with 0.5 s control samples. The FMU is advanced in at-most-0.1 s
communication substeps because of the tested OpenModelica CVODE export
constraint.

## BaSyx / AAS

Start the existing Eclipse BaSyx services and seed the six-submodel AAS:

```powershell
docker compose -f docker\docker-compose.yml up -d
.\.venv\Scripts\python.exe scripts\seed_basyx.py
```

The default AAS services are the registry on port 8080, environment on 8081,
and submodel registry on 8082. To run a measured AAS sync case, add
`--basyx --basyx-host http://localhost:8081 --basyx-period 10` to the
experiment command. If the services are unavailable the experiment reports
the failure; it does not substitute synthetic latency or success values.

## Final research campaign

From the repository root, the default command runs all 11 supported scenarios
with all 3 controllers: 33 deterministic cases, each at 2700 s with fault
injection at 350 s and a 0.5 s sample interval:

```powershell
.\.venv\Scripts\python.exe -m experiments.run_research_evaluation
```

To measure live AAS synchronization for the combined-fault constrained case:

```powershell
.\.venv\Scripts\python.exe -m experiments.run_research_evaluation --with-basyx
```

Each invocation creates a new
`results/research_evaluation/<UTC timestamp>/` directory containing raw CSVs,
per-run metrics JSON, logs, `manifest.json`, `campaign.json`, and
`controller_scenario_comparison.csv`. The manifest records model/FMUs/config
hashes, software versions, protocol, controller/scenario parameters, run
times, command lines, and failed-run evidence. No random inputs are used, so
one run per case is deterministic evidence, not a statistical sample.

Generate paper figures and tables from a completed campaign's raw CSVs:

```powershell
.\.venv\Scripts\python.exe -m analysis.generate_research_artifacts `
  --campaign results\research_evaluation\<UTC timestamp>
```

The completed 33-run campaign is in
[results/research_evaluation/20261016T172551Z](./results/research_evaluation/20261016T172551Z/).
All 33 scenario/controller cases completed with no failures. Its
[manifest](./results/research_evaluation/20261016T172551Z/manifest.json),
[summary table](./results/research_evaluation/20261016T172551Z/summary_metrics.csv),
and [research report](./results/research_evaluation/20261016T172551Z/RESEARCH_REPORT.md)
are generated from the raw run CSVs.

Across scenarios, the mean maximum winding temperature was 96.171 °C for
baseline, 95.343 °C for adaptive, and 94.825 °C for constrained control. No
case crossed the configured 120 °C critical threshold; the hottest case was
baseline under cooling degradation at 112.741 °C. Mean useful shaft work was
12.377, 13.104, and 13.278 kWh respectively, and mean electrical energy was
13.639, 14.414, and 14.602 kWh. These are equally weighted deterministic
scenario averages, not statistical estimates or a universal controller
ranking. Controller signal access differs as described above.

The completed controller campaign did not enable AAS. Separate live BaSyx
smoke evidence is retained at
`results/research_evaluation/basyx_smoke_20261016_retry/20261016T171418Z/`:
one write, 12 reads, and one aligned snapshot succeeded; write latency was
443.361 ms and the single end-to-end loop was 1055.599 ms. This single snapshot
is a connectivity/snapshot smoke check, not a representative latency
distribution or real-time guarantee. Detailed methodology, limitations, and
all measured controller metrics are in
[REPRODUCIBILITY.md](./REPRODUCIBILITY.md).

The metric formulas, units, sampling convention, and threshold semantics are
defined in [METRIC_DEFINITIONS.md](./METRIC_DEFINITIONS.md).

A historical comparison with the former reduced-order model was recomputed
from preserved runs and is available as
[MODEL_COMPARISON.md](./results/research_evaluation/20261016T172551Z/MODEL_COMPARISON.md),
with [run-level metrics](./results/research_evaluation/20261016T172551Z/model_comparison_runs.csv)
and [scenario summaries](./results/research_evaluation/20261016T172551Z/model_comparison_summary.csv).
It pairs only healthy and cooling runs because those are the only shared
scenarios in the archive. The old 5.5 kW traces start at 30 °C, compared with
90 °C for the 18.5 kW MSL runs, so temperature and energy differences are not
an equal-initial-condition model validation. The historical per-step solver
timings averaged 0.01171 ms for the reduced-order traces and 9.54316 ms for the
MSL traces (about 815×), but the archive lacks a software/hardware manifest;
this is indicative simulation evidence, not a controlled runtime benchmark.
The old plant remains removed from supported code paths; historical raw results
are retained only for this explicitly limited comparison.

## Limitations

- The MSL benchmark is 18.5 kW, not a specific manufacturer motor.
- The integrated thermal network is lumped and uses assumed RC parameters.
- MSL thermal coupling omits or simplifies some core-loss thermal paths.
- Fault magnitudes and 100/120 °C thresholds have not been validated against
  physical equipment.
- Cooling residual thresholds are tuned to the noiseless simulated channel;
  physical sensor noise, sensor dynamics, and uncertainty are not modeled.
- Mechanical unbalance/radial vibration is not represented.
- Live AAS latency depends on the local container runtime and deployment.
- Simulation throughput is not a hardware real-time certification.

Historical outputs are retained for traceability but are not inputs to the
induction-only final campaign or evidence for its reported results.
