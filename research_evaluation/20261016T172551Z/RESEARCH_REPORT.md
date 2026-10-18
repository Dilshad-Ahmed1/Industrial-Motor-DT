# Induction-motor Digital Twin research report

- Campaign: `20261016T172551Z`
- Plant: `MotorDigitalTwin.InductionMotorDigitalTwin18kW`
- Scenario/controller cases: 33
- Completed: 33
- Failed: 0
- Simulation: 2700 s; fault at 350 s; step 0.5 s
- Evidence type: deterministic simulation; not field or manufacturer validation.

## Method

All reported tables and plots are regenerated from the raw per-run CSVs using the metric definitions in `METRIC_DEFINITIONS.md`. Each case uses the same plant and protocol; controller information differences are documented in the project README. There is one deterministic case per scenario/controller, so no confidence intervals or statistical significance are reported.

## Controller/scenario results

The full machine-readable table is `summary_metrics.csv`. The table below reports measured maximum winding temperature, critical-limit exposure, post-fault output, estimated-state error, and runtime for every completed case.

| Scenario | Controller | Max winding (°C) | Critical time (s) | Post-fault work (kWh) | Winding MAE (°C) | Solver RT factor |
|---|---|---:|---:|---:|---:|---:|
| combined_supported | baseline | 90.000 | 0.000 | 6.722 | 1.891 | 79.455 |
| combined_supported | adaptive | 104.274 | 0.000 | 10.731 | 0.526 | 65.598 |
| combined_supported | constrained | 102.036 | 0.000 | 10.415 | 0.462 | 83.634 |
| cooling | baseline | 112.741 | 0.000 | 10.167 | 0.737 | 89.032 |
| cooling | adaptive | 106.713 | 0.000 | 9.374 | 1.073 | 85.365 |
| cooling | constrained | 107.609 | 0.000 | 9.379 | 1.147 | 85.814 |
| frequency_deviation | baseline | 92.251 | 0.000 | 12.309 | 0.059 | 83.479 |
| frequency_deviation | adaptive | 90.000 | 0.000 | 11.115 | 0.646 | 86.570 |
| frequency_deviation | constrained | 90.695 | 0.000 | 12.121 | 0.069 | 83.199 |
| healthy | baseline | 90.000 | 0.000 | 12.077 | 0.025 | 68.029 |
| healthy | adaptive | 90.000 | 0.000 | 12.037 | 0.054 | 83.919 |
| healthy | constrained | 90.077 | 0.000 | 12.068 | 0.031 | 85.387 |
| mechanical_friction | baseline | 90.870 | 0.000 | 12.191 | 0.058 | 83.378 |
| mechanical_friction | adaptive | 90.519 | 0.000 | 12.148 | 0.035 | 77.606 |
| mechanical_friction | constrained | 90.346 | 0.000 | 12.120 | 0.019 | 85.906 |
| overload | baseline | 103.261 | 0.000 | 13.759 | 1.199 | 83.995 |
| overload | adaptive | 102.684 | 0.000 | 13.651 | 1.099 | 80.626 |
| overload | constrained | 96.545 | 0.000 | 12.971 | 0.595 | 84.534 |
| rth_degradation | baseline | 109.155 | 0.000 | 10.768 | 0.507 | 85.022 |
| rth_degradation | adaptive | 104.582 | 0.000 | 10.213 | 0.760 | 85.376 |
| rth_degradation | constrained | 102.086 | 0.000 | 9.798 | 0.990 | 83.777 |
| sensor_bias | baseline | 90.000 | 0.000 | 6.130 | 2.402 | 86.388 |
| sensor_bias | adaptive | 90.000 | 0.000 | 12.037 | 0.054 | 84.074 |
| sensor_bias | constrained | 90.077 | 0.000 | 12.068 | 0.031 | 86.534 |
| sensor_freeze | baseline | 90.000 | 0.000 | 12.077 | 0.025 | 84.175 |
| sensor_freeze | adaptive | 90.000 | 0.000 | 12.037 | 0.054 | 85.625 |
| sensor_freeze | constrained | 90.077 | 0.000 | 12.068 | 0.031 | 85.524 |
| supply_degradation | baseline | 99.606 | 0.000 | 11.983 | 1.319 | 85.390 |
| supply_degradation | adaptive | 90.000 | 0.000 | 10.835 | 0.427 | 86.326 |
| supply_degradation | constrained | 93.451 | 0.000 | 11.441 | 0.887 | 81.488 |
| voltage_imbalance | baseline | 90.000 | 0.000 | 8.298 | 4.217 | 54.753 |
| voltage_imbalance | adaptive | 90.000 | 0.000 | 10.373 | 5.648 | 53.475 |
| voltage_imbalance | constrained | 90.077 | 0.000 | 11.983 | 7.129 | 53.506 |

## Fault severity interpretation

The injected severity index and estimated anomaly score are reported separately. Their scales are not calibrated to the same physical meaning, so no severity MAE or physical severity accuracy is claimed. Their traces, when available, are saved under `figures/`.

## BaSyx evidence

The 33-case controller campaign did not enable AAS. The following measurements are from a separate live BaSyx smoke experiment; they are reported separately and are not mixed into controller results.

Source: [`../basyx_smoke_20261016_retry/20261016T171418Z/01_cooling_constrained_basyx_summary.json`](`../basyx_smoke_20261016_retry/20261016T171418Z/01_cooling_constrained_basyx_summary.json`); detailed samples: [`../basyx_smoke_20261016_retry/20261016T171418Z/01_cooling_constrained_basyx_detail.csv`](`../basyx_smoke_20261016_retry/20261016T171418Z/01_cooling_constrained_basyx_detail.csv`).

| Measure | Observed result |
|---|---:|
| Successful AAS writes | 1/1 (100.000%) |
| Successful reads | 12/12 (100.000%) |
| Snapshot alignment | 1/1 (100.000%) |
| AAS write mean | 443.361 ms |
| Read mean / p95 | 50.623 / 133.255 ms |
| End-to-end loop mean | 1055.599 ms |
| Controller-only mean | 0.245 ms |

This smoke test recorded one synchronization snapshot (one write and one end-to-end loop sample). Therefore write and loop percentiles are single observations, not latency distributions. Read percentiles summarize the individual property reads within that snapshot, not repeated loop cycles. The measured end-to-end loop is compared with the 500 ms control interval only as a single-run feasibility warning, not a real-time guarantee.

## Failed or incomplete cases

- None.

## Limitations

- The induction motor parameters are based on the MSL reference example, not an identified manufacturer product.
- The winding/frame thermal RC network, fault strengths, and safety thresholds are explicit assumptions/configuration.
- The plant is rotational-only and does not represent radial vibration or mechanical unbalance.
- Deterministic simulation results do not establish physical or manufacturer validation.
- Simulation throughput is not hardware real-time certification.

## Reproduction

From the repository root, run `python -m experiments.run_research_evaluation` to create a new campaign, then regenerate this report from saved raw evidence with `python -m analysis.generate_research_artifacts --campaign results/research_evaluation/20261016T172551Z --aas-evidence results/research_evaluation/basyx_smoke_20261016_retry/20261016T171418Z/01_cooling_constrained_basyx_summary.json`.

The descriptive historical reduced-order comparison is in `MODEL_COMPARISON.md`; regenerate it from preserved legacy and induction raw traces with `python -m analysis.generate_model_comparison`.
