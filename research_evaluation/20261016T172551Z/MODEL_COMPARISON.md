# Historical reduced-order versus induction-motor comparison

- Historical source archive: `C:\Users\dilsh\Documents\Industry 5.0\results\motor_model_comparison\20261003T111253Z`
- Comparison runs recomputed from raw CSVs: 12
- Plants: archived 5.5 kW reduced-order model (`legacy`) and 18.5 kW MSL induction model (`induction`).
- Shared scenarios: cooling, healthy; three controllers per plant/scenario.
- Evidence type: historical deterministic simulation; not physical validation.

## Matched-scenario summary

Values below are arithmetic means across the three archived controller runs for each shared scenario, recalculated from the archived raw time-series. Energy and useful work use trapezoidal integration over the recorded `time_s` timestamps. Useful work is normalized by each model's own rated shaft power (full-load-equivalent hours). Solver timing is the per-sample `solver_step_time_s` recorded in those historical runs.

| Scenario | Plant | Runs | Rated kW | Initial winding °C | Mean peak winding °C | Mean peak rise °C | Mean speed range rpm | Useful work / rated kW (h) | Mean solver step ms | Solver RT factor |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| cooling | induction | 3 | 18.50 | 90.00 | 96.43 | 6.43 | 37.364 | 0.2171 | 10.63715 | 47.7 |
| cooling | legacy | 3 | 5.50 | 30.00 | 76.57 | 46.57 | 0.000 | 0.2200 | 0.01055 | 49872.5 |
| healthy | induction | 3 | 18.50 | 90.00 | 90.03 | 0.03 | 37.042 | 0.2212 | 8.44918 | 62.9 |
| healthy | legacy | 3 | 5.50 | 30.00 | 72.50 | 42.50 | 0.000 | 0.2202 | 0.01287 | 40102.6 |

## Interpretation and limitations

Across the shared scenarios, the archived mean solver-step time is 0.01171 ms for the reduced-order model and 9.54316 ms for the MSL model (about 815x higher in the MSL runs). This is an indicative historical per-step timing comparison, not a controlled benchmark: the archive lacks a complete software/hardware environment manifest, and it does not measure BaSyx or the whole application loop.

The legacy model was rated at 5.5 kW and its traces start at 30 °C; the MSL traces are rated at 18.5 kW and start at 90 °C. Their absolute temperature, energy, and work values therefore are not direct equal-rating/equal-initial-condition comparisons. Normalizing shaft work by each model's own rating helps contextualize output but does not remove the thermal-parameter or initialization differences. The common 800 s healthy/cooling cases are the only shared scenario set in this archive. Saved traces span 799.5 s for the legacy model and 800.0 s for the MSL model, both sampled at 0.5 s. Other fault responses are not paired. Mechanical unbalance appears only in the historical legacy campaign and is unsupported by the rotational MSL model.

The archived results show the synthetic model holding speed near its fixed nominal value, while the MSL model exposes speed range and three-phase electrical/torque dynamics. The old model is no longer an active plant option; its archived raw runs are preserved only for this historical comparison.

## Reproduction

From the repository root, run `python -m analysis.generate_model_comparison` to recompute `model_comparison_runs.csv`, `model_comparison_summary.csv`, and this report from the preserved archive.
