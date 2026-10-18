# Figure provenance and regeneration

The manuscript uses four figures copied from the final campaign artifacts:

- `figures/temperature_cooling.png`
- `figures/temperature_voltage_imbalance.png`
- `figures/load_command_cooling.png`
- `figures/prediction_mae.png`

The generator is maintained in the repository at [`analysis/generate_research_artifacts.py`](../analysis/generate_research_artifacts.py). From the repository root, regenerate the campaign artifacts with:

```powershell
.\.venv\Scripts\python.exe -m analysis.generate_research_artifacts --campaign results\research_evaluation\<UTC timestamp>
```

Replace `<UTC timestamp>` with the exact campaign directory name. The generator requires the campaign raw data and the repository analysis modules; this manuscript package alone is not a standalone reproduction archive.
