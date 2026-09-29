# Reproducibility Manifest

## Frozen project state

This manifest freezes the engineering implementation, scenario matrix, data products, and software environment associated with the final manuscript evidence set used in this repository.

- Project root: `C:\Users\dilsh\Documents\Industry 5.0`
- Date frozen: 2026-09-29
- Evidence set: `results/compare.csv`
- BaSyx timing summary: `results/compare_basyx_metrics.csv`
- Active controller set: `baseline`, `adaptive`, `constrained`
- Discarded exploratory controller: `energy_aware` (not part of the manuscript evidence)

## Core model and runtime artifacts

- Motor model: `models/MotorElectroThermalMechanicalFaultable.mo`
- Compiled FMU: `MotorElectroThermalMechanicalFaultable.fmu`
- Runtime: `simulation/fmu_runtime.py`
- Experiment loop: `experiments/experiment_runner.py`
- State estimator: `twin/state_estimator.py`
- Fault detector: `twin/fault_detector.py`
- Severity estimator: `twin/fault_severity.py`
- Predictor: `twin/predictor.py`
- Constrained controller: `control/constrained_adaptive_controller.py`
- AAS/BaSyx bridge: `integration/basyx_bridge.py`

## Frozen configuration and scenario matrix

### Simulation protocol

- Simulation duration: 1800 s
- Logged sample interval: 0.5 s
- Fault injection time: 600 s
- Safety threshold: 120 C model limit
- Thermal risk threshold: 100 C model threshold
- FMU interface: FMI 2.0 co-simulation
- Snapshot timing: Option A (AAS snapshot built before the FMU step using same-step measurement and estimate)

### Scenario matrix

| Scenario | Fault condition | Status |
|---|---|---|
| healthy | none | active |
| cooling | cooling effectiveness degradation | active |
| sensor_bias | +10 C sensor bias | active |
| sensor_freeze | sensor freeze input active | active |
| rth_degradation | thermal resistance degradation factor = 2.0 | active |
| unbalance | mechanical unbalance severity = 0.75 | active |
| combined | sensor bias + cooling degradation + unbalance | active |

### Controller definitions

| Controller | Purpose |
|---|---|
| baseline | nominal reference operation |
| adaptive | condition-aware adjustment |
| constrained | stateful thermal-risk-aware supervisory controller used as the final paper controller |

## Software environment

The values below are recorded from the project virtual environment at the time of freeze.

- Python: 3.12.4
- numpy: 2.5.3
- pandas: 3.0.6
- PyYAML: 6.0.3
- scipy: 1.18.1
- matplotlib: 3.11.2
- fmpy: 0.3.32
- requests: 2.34.2
- OMPython: available in the project environment but version metadata was not explicitly pinned in the source tree

The repository did not expose a Git commit hash in the currently checked-out workspace, so version pinning is recorded by the file set and the active Python environment rather than a Git SHA.

## Final frozen scientific results

The current evidence table is in `results/compare.csv`.

The leading values for the retained constrained controller are:

- combined scenario max winding temperature: 99.66 C
- combined scenario minimum safety margin: 18.24 C
- combined scenario mean derating fraction: 0.0593
- combined scenario time above 100 C: 0 s
- combined scenario time above 120 C: 0 s
- combined scenario energy-per-useful-work: 1.1132

## BaSyx evidence

The frozen BaSyx timing summary is in `results/compare_basyx_metrics.csv` and the detailed JSON is in `results/combined_constrained_1800s_basyx_basyx_summary.json`.

The current final values are:

- update success rate: 100.0%
- read success rate: 100.0%
- end-to-end loop latency mean: 750.03 ms
- controller-only latency mean: 0.20 ms
- write latency mean: 376.60 ms
- read latency mean: 61.32 ms
- synchronization MAE for thermal state: approximately 2.5e-10 C

## Result inventory

- `results/compare.csv`
- `results/compare_basyx_metrics.csv`
- `results/combined_constrained_1800s_basyx_basyx_summary.json`
- `results/healthy_baseline_1800s.csv`
- `results/healthy_adaptive_1800s.csv`
- `results/healthy_constrained_1800s.csv`
- `results/cooling_baseline_1800s.csv`
- `results/cooling_adaptive_1800s.csv`
- `results/cooling_constrained_1800s.csv`
- `results/sensor_bias_baseline_1800s.csv`
- `results/sensor_bias_adaptive_1800s.csv`
- `results/sensor_bias_constrained_1800s.csv`
- `results/sensor_freeze_baseline_1800s.csv`
- `results/sensor_freeze_adaptive_1800s.csv`
- `results/sensor_freeze_constrained_1800s.csv`
- `results/rth_degradation_baseline_1800s.csv`
- `results/rth_degradation_adaptive_1800s.csv`
- `results/rth_degradation_constrained_1800s.csv`
- `results/unbalance_baseline_1800s.csv`
- `results/unbalance_adaptive_1800s.csv`
- `results/unbalance_constrained_1800s.csv`
- `results/combined_baseline_1800s.csv`
- `results/combined_adaptive_1800s.csv`
- `results/combined_constrained_1800s.csv`
- `results/combined_constrained_1800s_basyx.csv`

## Regeneration workflow

The project should be regenerated with the active environment and the documented source files.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe analysis\compare_evaluation.py --input-dir .\results --output .\results\compare.csv
.\.venv\Scripts\python.exe analysis\generate_publication_figures.py
```

The self-contained figure-generation script is located at `analysis/generate_publication_figures.py` and emits publication-ready images into `results/figures`.

## Freeze statement

This manuscript evidence set represents the final version to be used for the paper. The energy-aware controller is intentionally excluded from the scientific evidence set, and the constrained controller remains the active, paper-credible final implementation.
