# Research metric definitions

## Sampling and time alignment

The CSV contains one row per controller sample at simulation time `t_i`.
Measurements, estimates, forecasts, diagnoses, and commands in that row refer
to the pre-step state at `t_i`. `sample_interval_s` is the interval actually
advanced after that row; it is normally 0.5 s and may be shorter for the final
partial interval. Power, temperature, and command values at a sample are
treated as left-endpoint values over `[t_i, t_i + sample_interval_s)`.
Consequently, a run's accounted duration is `sum(sample_interval_s)`, including
the final interval to the requested stop time.

`fault_active` means the sampled plant state at `t_i` already includes the
fault. `fault_input_active_for_next_interval` means the injection is applied
while advancing the interval starting at `t_i`. For a 350 s injection with a
0.5 s sample, the sample at 350 s remains pre-fault; the first sampled faulted
state is at 350.5 s. This separation keeps sensor/estimator values aligned to
the plant state while assigning interval energy and work to the input applied
over that interval.

The reported `T_winding_C` and `T_frame_C` columns are FMU truth for
evaluation. `estimated_winding_C` and `estimated_frame_C` are Digital Twin
estimates. The predictor receives only current measurements and observer
state. Forecast accuracy is evaluated after simulation by comparing a
prediction made at `t_i` to true winding temperature at `t_i + 30 s` or
`t_i + 60 s`; this future truth is not available to the predictor/controller.

## Thermal safety

For each threshold `L`, time above threshold is

`sum(1[T_winding_C(t_i) >= L] * sample_interval_s_i)`.

Its percentage is that duration divided by the full accounted run duration.
Thresholds are configured as intervention (90 °C), warning (100 °C),
buffered safety (115 °C), and critical (120 °C). They are Twin/controller
policy values, not verified limits for an identified motor. A critical
violation is any positive sampled duration at or above the critical threshold.
Minimum thermal margin is `critical_threshold_C - max(T_winding_C)`.

Time to thermal-risk detection is measured from the first sampled true winding
temperature at or above the intervention threshold to the first sample at or
after that crossing where the estimated winding temperature is at or above
the warning threshold. It is NaN if no sampled risk crossing or no subsequent
estimated warning is observed.

Time to return below buffered safety is zero if the post-fault trace never
reaches the buffered threshold. Otherwise, it is the time from the configured
fault injection to the first sample below the threshold after the last sampled
exceedance. It is NaN when the run ends without a sampled return.

## Energy and operational performance

Electrical input energy (kWh) uses left-endpoint integration:

`sum(P_electrical_W(t_i) * sample_interval_s_i) / 3,600,000`.

Useful mechanical work uses the positive part of shaft power:

`sum(max(P_shaft_W(t_i), 0) * sample_interval_s_i) / 3,600,000`.

Post-fault energy/work apply the same formulas only to rows whose
`fault_input_active_for_next_interval` is true. Electrical-energy/useful-work
ratio is undefined (NaN) when useful work is zero or negative; it is not
replaced by a large finite number. This ratio is not itself a comparison of
motor efficiencies unless scenarios, useful output, and operating points are
comparable.

Speed RMSE is the root mean squared difference between measured shaft speed
and `speed_reference_rad_s` (nominal rated speed multiplied by the V/f
command). Torque command error is measured `torque_load_Nm` minus
`torque_command_Nm`; it includes the effect of the modeled load actuator.
Derating is the interval-weighted mean of the controller's normalized
derating output. Reduced-load and emergency durations are the sum of the
intervals in the corresponding command/mode.

## Estimation, prediction, and fault handling

Winding/frame estimation MAE and RMSE compare the corresponding estimate to
the FMU truth at each same-time sample. The 30 s/60 s forecast MAE and RMSE
compare only horizons with a future sample within 0.51 of the median sample
interval; the final horizon tail without a target sample is excluded.

Fault detection latency is the first time at which the scenario-specific
detector channel is active on a sample where `fault_active` is true, minus the
configured injection time. The combined scenario uses the OR of its
sensor-bias, cooling, supply-degradation, and overload detector channels.
Healthy operation uses the generic alarm channel. An undetected fault has
NaN latency, not zero.

Sample-level TP/FP/TN/FN and precision/recall/F1 use `fault_active` as ground
truth and the same scenario-specific detection channels. The resulting
classification is conditional on this deterministic synthetic scenario
labeling and should not be interpreted as field diagnostic performance.

`fault_severity_true` is a scenario-input severity index normalized by
configured fault-amplitude scales. `fault_severity_estimated` is an observer/
detector anomaly score. Although both are dimensionless and bounded, their
component scales and semantics are not calibrated to be equivalent. The
campaign therefore reports their post-fault means separately and does not
claim a severity MAE or physical severity calibration.

## Runtime and AAS

`solver_step_time_s` measures FMU advance time in the process, excluding
forecast/controller and AAS work. Solver real-time factor is accounted
simulation duration divided by the sum of FMU advance times; values above 1
mean the simulation ran faster than simulation time in that measurement.
`loop_compute_latency_ms` sums the separately timed estimator, detector,
predictor, and controller calls. Wall-clock real-time pacing metrics, when
enabled, use complete control-cycle elapsed time and the requested
communication interval as the deadline.

BaSyx write/read/end-to-end percentiles are calculated only from actual
requests made by the enabled experiment. Failed updates and read-backs remain
in the detailed log and success-rate denominator. Snapshot alignment compares
the read-back `SnapshotId` and simulation timestamp across the six submodels.
No AAS latency, success, or alignment value is imputed when BaSyx is
unavailable.

## Reproducibility and statistical interpretation

The supported campaign is deterministic: there is no random disturbance,
random seed, stochastic sensor noise, or independent repetition. Each
scenario/controller pair is run once from the model's specified initial
conditions with the same duration and fault time. The campaign therefore
reports per-case measurements only; it does not report confidence intervals,
between-run variability, or statistical significance.
