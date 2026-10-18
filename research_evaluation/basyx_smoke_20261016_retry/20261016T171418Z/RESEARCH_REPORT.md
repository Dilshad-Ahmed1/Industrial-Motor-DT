# Induction-motor Digital Twin research report

- Campaign: `20261016T171418Z`
- Plant: `MotorDigitalTwin.InductionMotorDigitalTwin18kW`
- Scenario/controller cases: 1
- Completed: 1
- Failed: 0
- Simulation: 2 s; fault at 1 s; step 0.5 s
- Evidence type: deterministic simulation; not field or manufacturer validation.

## Method

All reported tables and plots are regenerated from the raw per-run CSVs using the metric definitions in `METRIC_DEFINITIONS.md`. Each case uses the same plant and protocol; controller information differences are documented in the project README. There is one deterministic case per scenario/controller, so no confidence intervals or statistical significance are reported.

## Controller/scenario results

The full machine-readable table is `summary_metrics.csv`. The table below reports measured maximum winding temperature, critical-limit exposure, post-fault output, estimated-state error, and runtime for every completed case.

| Scenario | Controller | Max winding (°C) | Critical time (s) | Post-fault work (kWh) | Winding MAE (°C) | Solver RT factor |
|---|---|---:|---:|---:|---:|---:|
| cooling | constrained | 90.000 | 0.000 | 0.001 | 0.019 | 43.736 |

## Fault severity interpretation

The injected severity index and estimated anomaly score are reported separately. Their scales are not calibrated to the same physical meaning, so no severity MAE or physical severity accuracy is claimed. Their traces, when available, are saved under `figures/`.

## BaSyx evidence

An AAS latency plot and raw synchronization samples are present. Read/write/snapshot alignment success and latency percentiles are in the associated run's metrics JSON and detailed CSV.

## Failed or incomplete cases

- None.

## Limitations

- The induction motor parameters are based on the MSL reference example, not an identified manufacturer product.
- The winding/frame thermal RC network, fault strengths, and safety thresholds are explicit assumptions/configuration.
- The plant is rotational-only and does not represent radial vibration or mechanical unbalance.
- Deterministic simulation results do not establish physical or manufacturer validation.
- Simulation throughput is not hardware real-time certification.

## Reproduction

From the repository root, run `python -m experiments.run_research_evaluation` to create a new campaign, then run `python -m analysis.generate_research_artifacts --campaign results/research_evaluation/20261016T171418Z`.
