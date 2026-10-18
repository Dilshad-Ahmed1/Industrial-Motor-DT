# Reproducibility and research evidence

## Supported plant and protocol

The supported plant is
`MotorDigitalTwin.InductionMotorDigitalTwin18kW`, a Modelica composition
around the unmodified MSL 4.1.0 `IM_SquirrelCage`. See
[INDUCTION_MOTOR_REFERENCE.md](./INDUCTION_MOTOR_REFERENCE.md) for all machine
parameters, their provenance, the nominal operating point, and thermal/fault
assumptions.

The final deterministic protocol uses 11 physically implemented scenarios,
three controllers, a common initial condition, 350 s fault injection, 2700 s
total duration, and 0.5 s control samples. It runs one case per
scenario/controller pair (33 runs) because no stochastic disturbances or
random seeds are used. It does not present repeated deterministic cases as
independent statistical evidence.

Faults are applied to the interval beginning at 350 s. The sample at 350 s is
the pre-step state and the first post-injection sampled state is at 350.5 s.
The CSV includes both current-sample `fault_active` and
`fault_input_active_for_next_interval` to preserve this distinction.

## Reproduction commands

Run from the repository root in the project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\export_induction_fmu.py --overwrite
.\.venv\Scripts\python.exe scripts\validate_induction_motor_nominal.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m experiments.run_research_evaluation
```

The campaign command creates a new timestamped
`results/research_evaluation/<UTC timestamp>/` directory; it refuses to reuse
an existing directory. Optional live AAS measurement is enabled with
`--with-basyx` after starting and seeding the local BaSyx deployment. The
campaign writes a complete `manifest.json` and `campaign.json`, per-case raw
CSV and metrics JSON, logs, and `controller_scenario_comparison.csv`.

Regenerate all final summaries and figures from the raw time-series files:

```powershell
.\.venv\Scripts\python.exe -m analysis.generate_research_artifacts `
  --campaign results\research_evaluation\<UTC timestamp>
```

The generated `RESEARCH_REPORT.md`, summary tables, and figures reside beside
the raw runs. Formulae, units, interval weighting, classification semantics,
and threshold definitions are specified in
[METRIC_DEFINITIONS.md](./METRIC_DEFINITIONS.md). The completed campaign is
`results/research_evaluation/20261016T172551Z/`, with 33/33 cases completed and
no failed runs.

Incomplete development attempts are preserved but excluded from this report:
`results/research_evaluation/20261016T171719Z/` has one completed case and an
unfinished campaign status, and `results/research_evaluation/20261016T172323Z/`
contains only an unfinalized manifest with no run entries. They are not pooled
with or substituted for the completed 33-case campaign.

For the completed campaign, regenerate tables and figures and incorporate the
separate AAS smoke evidence with:

```powershell
.\.venv\Scripts\python.exe -m analysis.generate_research_artifacts `
  --campaign results\research_evaluation\20261016T172551Z `
  --aas-evidence results\research_evaluation\basyx_smoke_20261016_retry\20261016T171418Z\01_cooling_constrained_basyx_summary.json
```

## Completed evidence

The final campaign used the 18.5 kW induction plant exclusively: 11 scenarios
times three controllers, 2700 s each, 350 s fault injection, and 0.5 s samples.
All 33 runs completed; no stochastic inputs were used, so these are deterministic
single-run comparisons, not independent repetitions or statistical estimates.
The run manifest is
[manifest.json](./results/research_evaluation/20261016T172551Z/manifest.json),
the raw per-run CSVs and generated outputs are in
[the campaign directory](./results/research_evaluation/20261016T172551Z/), and
the computed research report is
[RESEARCH_REPORT.md](./results/research_evaluation/20261016T172551Z/RESEARCH_REPORT.md).
Tables and figures were regenerated from those raw CSVs.

The nominal-validation command
`.\.venv\Scripts\python.exe scripts\validate_induction_motor_nominal.py`
also passed against OpenModelica 1.27.1/MSL 4.1.0. It evaluated 1002 samples
over 7–8 s. Measured values were 400.000 V line-to-line, 32.8565 A, 50.000 Hz,
1462.8938 rpm, 2.47375% slip, 122.6381 N·m electromagnetic torque,
120.7945 N·m shaft torque, 20.4443 kW electrical input, 18.5050 kW shaft
output, 90.5141% efficiency, 0.898112 power factor, and 1939.33 W total losses.
Every deviation, stability, and thermal-response check passed its explicit
tolerance in
[validation.json](./results/induction_motor_nominal/run_4vzqfv5z/validation.json);
the corresponding time series is
[motor_nominal.csv](./results/induction_motor_nominal/run_4vzqfv5z/motor_nominal.csv).
This is a simulation comparison to the MSL nominal reference, not independent
experimental validation.

Across the 11 equally weighted scenarios, mean maximum winding temperature
was 96.171 °C for baseline, 95.343 °C for adaptive, and 94.825 °C for
constrained control. No run exceeded the configured 120 °C critical threshold;
the smallest minimum margin to critical was 7.259 °C (baseline cooling
degradation). The maximum winding temperature was 112.741 °C in that same
baseline cooling case. These are model outputs under configured thresholds,
not verified limits for a manufacturer motor.

Mean total useful mechanical work over the full run was 12.377 kWh (baseline),
13.104 kWh (adaptive), and 13.278 kWh (constrained); mean electrical input
energy was 13.639, 14.414, and 14.602 kWh respectively. These simple means
weight each scenario equally and should not be interpreted as a universal
controller ranking; controller signal access differs as documented in the
README. Mean winding-estimation MAE was 1.131, 0.943, and 1.036 °C in the
same controller order. Mean 30/60 s forecast MAE was 0.934/1.022 °C for
baseline, 0.721/0.764 °C for adaptive, and 0.819/0.869 °C for constrained.
Mean solver real-time factor was 80.282, 79.505, and 81.755 respectively;
this is FMU solver throughput, not full application or hardware real-time
certification.

Live BaSyx evidence is from a separate short smoke run, not the 33-case
campaign. It recorded one successful write, 12 successful reads, and one
aligned snapshot (100% for these observed attempts). Write latency was
443.361 ms; mean read latency was 50.623 ms (p95 133.255 ms); the one
end-to-end synchronization loop took 1055.599 ms. Because there was one
snapshot, write/end-to-end percentiles are single observations; the read
percentiles are within-snapshot property-read values, not repeated loop
samples. See the raw evidence under
`results/research_evaluation/basyx_smoke_20261016_retry/20261016T171418Z/`.

## Historical reduced-order comparison

The old executable plant has been removed, but its archived runs were preserved
at `results/motor_model_comparison/20261003T111253Z/`. The descriptive
comparison in
[MODEL_COMPARISON.md](./results/research_evaluation/20261016T172551Z/MODEL_COMPARISON.md)
and the associated run-level and scenario-summary CSVs are recomputed directly
from those saved raw traces with:

```powershell
.\.venv\Scripts\python.exe -m analysis.generate_model_comparison
```

Only healthy and cooling are shared between the two archived plant campaigns,
with three controller runs per plant/scenario. The old and new ratings and
initial winding temperatures differ (5.5 kW/30 °C versus 18.5 kW/90 °C), so
absolute thermal and energy comparisons are descriptive rather than controlled
model validation. The old archive's timing lacks a software/hardware manifest;
the reported solver-step difference is indicative only.
