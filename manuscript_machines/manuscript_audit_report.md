# Manuscript audit report

## Current status

The revised LaTeX package is being prepared for author confirmation and possible submission. The corresponding author reports that both authors reviewed the prior manuscript and agreed to submit after the requested changes. They should confirm this revised version before submission.

The manuscript now includes a colored, structured workflow diagram; two additional campaign figures; a link to the project's GitHub repository; and prose that describes the scientific methods without relying on internal source-file names. Exact commands remain in the reproducibility subsection because they are operationally necessary to reproduce the software workflow.

The work is still a deterministic simulation study, not physical motor validation. The public GitHub commit now captures the changed source/configuration state recorded as dirty in the original campaign manifest. The raw per-run campaign traces are not in the public repository; the manuscript states that they are available from the corresponding author upon reasonable request. Reproducibility is therefore source-versioned but not fully self-contained from the public repository.

## Evidence inspected

- Official MDPI Machines template/class and supplied author instructions.
- Current README, parameter provenance, metric definitions, and reproducibility documentation.
- Final campaign `results/research_evaluation/20261016T172551Z`, including manifest, raw traces, summary metrics, report, and generated figures.
- Nominal validation evidence `results/induction_motor_nominal/run_4vzqfv5z/validation.json`.
- MSL model, FMI/Python runtime, observer, fault/severity estimation, forecasting, controllers, evaluation scripts, tests, and BaSyx integration.
- Historical reduced-order-model artifacts were considered separately and are not combined with the final campaign.

## Verified campaign and validation results

- 11 deterministic scenarios × 3 controllers = 33 completed runs, no failed runs; 2700 s per run, fault input at 350 s, samples every 0.5 s.
- The 350 s sample is pre-injection; the first sampled fault state is 350.5 s.
- Scenario-average maximum winding temperature (baseline/adaptive/constrained): 96.171/95.343/94.825 °C.
- Scenario-average useful shaft work: 12.377/13.104/13.278 kWh.
- Scenario-average electrical energy: 13.639/14.414/14.602 kWh.
- Winding-estimation MAE: 1.131/0.943/1.036 °C; 30 s forecast MAE: 0.934/0.721/0.819 °C; 60 s forecast MAE: 1.022/0.764/0.869 °C.
- No simulated run reached the configured 120 °C threshold. Minimum margin was 7.259 °C in baseline cooling degradation, whose maximum winding temperature was 112.741 °C.
- Nominal operating-point values and deviations trace to the validation JSON. This is consistency with an MSL reference example, not physical-motor validation.
- Separate BaSyx smoke test: one write, 12 reads, one aligned snapshot; end-to-end 1055.599 ms, write 443.361 ms, mean read 50.623 ms, observed-read p95 133.255 ms. These few observations are not a statistical latency distribution or real-time guarantee.

All campaign averages are deterministic scenario averages, not statistical estimates. Controller information access differs; the results are not a matched-information algorithm comparison.

## Scientific limits disclosed in the article

- The 18.5 kW plant is MSL-example-based, not a manufacturer-identified or physically calibrated motor.
- Thermal-network parameters are assumptions or derived under assumed structure; core/other losses are aggregated and spatial heat paths are omitted.
- Externally imposed friction work contributes to total loss reporting but is not separately coupled as heat into the thermal network.
- Fault magnitudes, residual thresholds, and 100/120 °C policy thresholds are not validated against physical equipment. Residual tuning uses simulated channels without measured sensor noise/dynamics.
- Mechanical unbalance and radial vibration are not modeled.
- The supervisory `speed_pu` input changes supply frequency; it is not a closed-loop shaft-speed setpoint.
- Simulation runtime does not establish hardware real-time performance or certification.
- AAS evidence is limited to the described local write/read/snapshot smoke test.

## Literature and declarations

- Metadata and abstracts were checked for Adamou and Alaoui (2024) and Chen et al. (2025). MDPI publisher pages returned HTTP 403; their full methods/results were not independently reviewed. No detailed quantitative comparison is made.
- Metadata for other cited scholarly sources was checked; human review of the full texts remains necessary.
- MSL, FMI, and AAS references cite official project/specification sources.
- Author order, affiliations, emails, ORCIDs, funding, conflicts, and CRediT roles came from the corresponding author.
- GenAI disclosure identifies GitHub Copilot in Visual Studio Code; exact version information was unavailable. The authors are responsible for final verification and approval.

## Build, figures, and package

- LaTeX build after the requested content/figure/data-statement changes succeeded: 12-page A4 PDF. Citation/reference resolution passed; no overfull boxes were reported in the final build log.
- Four campaign figures are included: cooling temperature, voltage-imbalance temperature, cooling load commands, and scenario forecast MAE. The architecture diagram is drawn in the LaTeX source.
- Existing test suite: 22 passed in the preceding validation run; manuscript-only revisions do not change application source code.
- MDPI's class generates a default template DOI (`10.3390/machines1010000`) in the submission PDF. It is not an assigned DOI and must not be treated as one.
- The current ZIP was rebuilt from the revised LaTeX source, MDPI support files, four figures, figure-generation note, and cover letter. The ZIP was extracted into a clean temporary folder and compiled successfully. Rebuild after further source edits.

## Remaining conditions before submission

1. Both authors should confirm the revised manuscript and the updated authorship/GenAI statements.
2. Review full texts and confirm citations and literature framing.
3. Confirm that the linked GitHub commit is the intended source snapshot. It captures the working-tree changes recorded in the campaign manifest and the Modelica/configuration hashes match.
4. Raw campaign traces remain outside the public repository. The corresponding author should confirm the stated request-access route or publish a stable data archive.
5. After the authors confirm this revised version and data-access statement, inspect/rebuild the final PDF and source ZIP if any changes are needed.
6. Resolve the MDPI template DOI through the journal workflow without inventing an identifier.

No journal submission has been made. This audit does not assert that a data archive, DOI, or final co-author approval of this revised version exists.
