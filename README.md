# Industrial Motor Digital Twin

This repository keeps two motor models side by side:

1. **Legacy reference/fallback:** the WEG W22 5.5 kW reduced-order
   electro-thermal-mechanical model.
2. **Standard induction plant:** an MSL 4.1.0 squirrel-cage induction motor,
   using the documented 18.5 kW reference dataset.

The MSL plant is a separate Modelica composition around the unmodified
`Modelica.Electrical.Machines.BasicMachines.InductionMachines.IM_SquirrelCage`.
It does not replace or rewrite the WEG model, legacy FMU, or historical results.

## Architecture

```text
Modelica MSL motor FMU
  electrical / torque / shaft dynamics / losses
  winding and frame thermal network + physical fault inputs
             |
             v
simulation/fmu_runtime.py
  typed FMI I/O; at most 0.1 s FMI substeps for induction plant
             |
             v
experiments/experiment_runner.py
  measurement normalization -> thermal observer -> fault diagnosis/severity
  -> 30/60 s forecast -> baseline/adaptive/constrained controller
             |
             +--> timestamped experiment CSV + JSON metrics
             |
             +--> existing Eclipse BaSyx v2 AAS Environment
                   OperationalState, ElectricalState, MechanicalState,
                   ThermalState, FaultState, ControlInterface
```

All six submodels carry an identical `SnapshotId`, UTC capture timestamp, and
simulation-time value for each synchronization. Each experiment builds the
snapshot once from pre-step values, then updates all six submodels and reads
back values, including each snapshot ID, to verify synchronization.
`TrueFaultSeverity` is simulation ground truth and is published only for
evaluation; estimated fault severity is computed from observer/detector
signals. In the experiment CSV, MSL component losses and winding temperature
are explicitly named as truth channels; the estimator/predictor/controller
receive current input/shaft-power observations and model-based estimates, not
future plant state.

BaSyx service URLs default to:

- AAS Registry: `http://localhost:8080`
- AAS Environment: `http://localhost:8081`
- Submodel Registry: `http://localhost:8082`

The stable AAS shell/global asset identifiers remain those of the original
reference asset. `OperationalState.PlantProfile` and the rated-value fields
make the active simulation profile explicit; do not interpret the induction
profile as physical measurements from the legacy WEG asset.

## Motor parameters and provenance

The new plant uses the Modelica Standard Library example `IMC_withLosses`,
described as a standard 18.5 kW, 400 V, 50 Hz motor with published equivalent
circuit parameters, loss breakdown and measurements. MSL does not name a
manufacturer/model. The complete parameter list and its manufacturer,
reference, calculated and assumed provenance are documented in
[INDUCTION_MOTOR_REFERENCE.md](./INDUCTION_MOTOR_REFERENCE.md).

No complete, verifiable equivalent-circuit set was found for the preferred
5–7.5 kW range. The MSL benchmark is used rather than silently fabricating
parameters for the original WEG 5.5 kW motor.

## Fault mechanisms

Supported by the induction plant:

- Cooling degradation changes frame-to-ambient conductance; a separate
  winding-frame resistance multiplier is available.
- Sensor bias and freeze affect the sensor channel, not true winding state.
- Overload changes shaft-load torque; a smooth actuator slew limits torque
  rate.
- Increased mechanical friction applies additional speed-opposing torque.
- Supply degradation scales all phase amplitudes; voltage imbalance modifies
  phase A and is diagnosed from filtered phase RMS values.
- Frequency deviation changes the three-phase source frequency.
- `combined_supported` combines sensor bias, cooling degradation, overload,
  and supply voltage reduction.

Mechanical unbalance is not supported by the new model because it has no radial
degrees of freedom. The runner rejects that scenario for the induction model
instead of simulating a fabricated vibration signal. It remains available for
the legacy plant.

Fault amplitudes and thermal RC values are test/model assumptions, not
manufacturer failure limits. The source, affected channels, diagnostics and
limitations are recorded in the motor reference document.

## Build, validate, and test

Windows PowerShell, from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts\export_induction_fmu.py --overwrite
.\.venv\Scripts\python.exe -m pytest -q
```

The exporter requires OpenModelica 1.27.1 and MSL 4.1.0. It checks the model,
exports FMI 2.0 Co-Simulation, and validates the FMU interface.

## Experiments

Single experiment. The fault-free interval is `[0, fault-time)` and the
selected scenario activates at `fault-time`; use the required 350–800 s window
as follows:

```powershell
.\.venv\Scripts\python.exe -m experiments.experiment_runner `
  --fmu models\InductionMotorDigitalTwin18kW.fmu `
  --plant-profile induction `
  --scenario cooling `
  --controller constrained `
  --stop 800 --fault-time 350 --step 0.5 `
  --output results\induction_manual\cooling_constrained.csv
```

Supported induction scenario names are `healthy`, `cooling`, `sensor_bias`,
`sensor_freeze`, `voltage_imbalance`, `frequency_deviation`, `overload`,
`mechanical_friction`, and `combined_supported`. Controllers are `baseline`,
`adaptive`, and `constrained`. The unsupported `unbalance` scenario is
available only with a plant that implements radial mechanics.

For live AAS writes/read-back measurements, add `--basyx` and optionally
`--basyx-host` and `--basyx-period`:

```powershell
.\.venv\Scripts\python.exe -m experiments.experiment_runner `
  --fmu models\InductionMotorDigitalTwin18kW.fmu `
  --plant-profile induction `
  --scenario combined_supported `
  --controller constrained `
  --stop 800 --fault-time 350 --step 0.5 `
  --output results\induction_manual\combined_constrained_basyx.csv `
  --basyx --basyx-host http://localhost:8081 --basyx-period 10
```

The comparison campaign runs all three controllers for each supported
induction scenario, plus healthy/cooling/unbalance runs for all three
controllers on the preserved legacy FMU. It runs one AAS-enabled induction
combined-fault constrained case when `--with-basyx` is given. It creates a new
UTC timestamped results folder and writes each run's CSV, JSON metrics, log,
an aggregate `comparison.csv`, and `campaign.json`; it never reuses an
existing campaign folder.

```powershell
.\.venv\Scripts\python.exe -m experiments.run_motor_comparison `
  --induction-fmu models\InductionMotorDigitalTwin18kW.fmu `
  --legacy-fmu MotorElectroThermalMechanicalFaultable.fmu `
  --stop 800 --fault-time 350 --step 0.5 --with-basyx
```

The campaign reports actual maximum winding temperature, time above the
configured critical temperature, minimum thermal margin, state-estimation MAE,
fault-specific detection latency, true/estimated severity MAE, 30/60 s
prediction MAE, electrical energy, useful work, their ratio, load derating,
speed/torque command errors, solver runtime and simulation real-time factor.
When BaSyx is enabled, it also reports measured write/read/end-to-end latency,
write/read success rates, and cross-submodel snapshot-ID alignment. Missing
measurements remain missing; no experiment result is synthesized or imputed.

## Validation methodology and model comparison

The new Modelica model is checked and simulated before FMU export. FMI runtime
tests cover nominal channels, supported fault mechanisms, finite/physical
outputs, observer/predictor/controller operation, and AAS snapshot structure.
The end-to-end experiment records pre-step observer/controller/AAS values at
simulation instant `t`; the post-step FMU sample is used at the next loop.
Forecasts are evaluated against the future winding-temperature sample at their
30 s/60 s horizon. Fault detection latency is based on the relevant detected
fault channel (or a supported component for a combined scenario), not merely
on a generic thermal alarm.

For a fair quantitative comparison, use the matched cooling-fault experiments
in `comparison.csv` with the same controller, stop/fault time and communication
step. Compare measured trajectories and runtime metrics, not raw signals with
different units or hidden truths:

- **Physical behavior:** the legacy model is calibrated to the WEG 5.5 kW
  rating and uses reduced-order torque/current/loss relations. The MSL plant
  resolves three-phase electrical state, electromagnetic torque, rotor/load
  mechanics, and MSL losses; its benchmark is 18.5 kW and its thermal network
  remains lumped and assumed.
- **Fault response:** compare supported cooling/common faults at matching
  severity only where each FMU exposes a corresponding input. Mechanical
  unbalance is comparable only on the legacy plant; the MSL rotational model
  explicitly does not claim it.
- **Computational cost:** use campaign mean solver-step cost and simulation
  real-time factor. The induction FMU requires internal FMI communication
  substeps no larger than 0.1 s with the tested OpenModelica CVODE build; this
  solver limit does not imply a physical 10 Hz motor model.
- **Real-time feasibility:** `--realtime` measures wall-clock pacing and
  deadline misses for an actual experiment. Simulation-throughput real-time
  factor alone is not an assertion about production deployment or network
  latency. BaSyx timing is reported only when the AAS integration ran.

## Executed comparison campaign

The full requested campaign was run with the above command at
`stop=800 s`, `fault-time=350 s`, `step=0.5 s`. The preserved outputs are in
[`results/motor_model_comparison/20261003T111253Z`](./results/motor_model_comparison/20261003T111253Z):
36/36 runs completed successfully (27 induction scenarios/controller cases
and 9 legacy cases). Every stored run had finite winding-temperature,
speed, electrical-power, and shaft-power samples. The aggregate
[`comparison.csv`](./results/motor_model_comparison/20261003T111253Z/comparison.csv)
contains thermal, detection, severity, prediction, energy/work, derating,
speed/torque, solver-throughput, and AAS metrics.

Measured matched cooling results (full-window winding maximum and total
electrical-energy/useful-work ratio):

| Controller | Induction max winding °C | Legacy max winding °C | Induction energy/work | Legacy energy/work | Cooling detection latency |
|---|---:|---:|---:|---:|---|
| Baseline | 97.73 | 77.27 | 1.1052 | 1.1148 | Induction 2.0 s; legacy not detected |
| Adaptive | 96.36 | 75.15 | 1.1043 | 1.1137 | Induction 2.0 s; legacy not detected |
| Constrained | 95.19 | 77.27 | 1.1038 | 1.1148 | Induction 2.0 s; legacy not detected |

These absolute temperatures and energy/work values are not a like-for-like
motor efficiency or thermal-rating comparison: the legacy model is rated
5.5 kW and the new MSL benchmark is rated 18.5 kW, with different thermal
parameterizations. The cooling-fault legacy cases had no post-fault alarm, so
fault-specific detection latency is missing (NaN); this is a measured
limitation of the legacy detection path, not a zero latency. On the induction
cooling runs, maximum winding temperature was 95.19–97.73 °C and the
fault-specific detector responded in 2.0 s. No run exceeded the configured
120 °C critical threshold.

Across all completed runs, mean per-step solver time was 9.24 ms for the
induction FMU (mean measured simulation-throughput factor 56.1×) and
0.0104 ms for the legacy FMU (53,133×). Both therefore simulated faster than
the requested 0.5 s control interval when measured without external pacing or
AAS calls. The AAS-enabled combined/constrained induction run synchronized
81 snapshots and read 972 submodels successfully: write, read, and
cross-submodel snapshot-alignment rates were each 100%. Mean AAS write/read
latencies were 308.08/22.96 ms; mean end-to-end loop latency was 586.87 ms
(P95 776.86 ms). Since this AAS loop mean exceeds the 500 ms controller
interval, synchronous AAS use on every control cycle is not demonstrated as
real-time feasible. The campaign used a 10 s AAS synchronization interval and
did not enable wall-clock `--realtime` pacing; deadline-miss rates were not
measured.

## Limitations

- The standard MSL case is 18.5 kW rather than the preferred 5–7.5 kW, because
  a complete, traceable smaller-motor parameter set was not available.
- Winding/frame thermal capacitances and resistances, load slew, fault
  amplitudes, diagnostic thresholds and the inherited 100/120 °C safety
  envelope are assumptions or Twin settings, not verified ratings for the
  unidentified MSL benchmark.
- Cooling-residual thresholds were calibrated on a noiseless simulated
  channel; physical sensor error/noise and cooling response require validation.
- Mechanical unbalance/radial vibration is not represented by the MSL variant.
- Live AAS performance depends on the local BaSyx deployment and is reported
  only when the corresponding run actually completed.
- `README_STEP1.md` is a preserved historical foundation note for the legacy
  stage; these current instructions supersede its “do not tune controllers”
  instruction.
