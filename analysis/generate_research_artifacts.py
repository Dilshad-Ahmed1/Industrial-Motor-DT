from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.experiment_metrics import compute_experiment_metrics


CONTROLLER_COLORS = {
    "baseline": "#3b82f6",
    "adaptive": "#f59e0b",
    "constrained": "#10b981",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _format(value: Any, digits: int = 3) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    if isinstance(value, (float, np.floating)):
        return f"{float(value):.{digits}f}"
    return str(value)


def _load_run_rows(campaign: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    import json

    manifest_path = campaign / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Campaign manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    fault_time = float(manifest["protocol"]["fault_injection_time_s"])
    config_path = PROJECT_ROOT / "config" / "twin_config.yaml"
    import yaml

    with config_path.open("r", encoding="utf-8") as source:
        config = yaml.safe_load(source)
    safety = config["induction_motor_digital_twin"]["safety"]
    for run in manifest.get("runs", []):
        row: dict[str, Any] = {
            "run_id": run["run_id"],
            "scenario": run["scenario"],
            "controller": run["controller"],
            "status": run["status"],
            "return_code": run["return_code"],
            "raw_csv": run["raw_csv"],
            "error": run.get("error"),
        }
        raw_path = Path(run["raw_csv"])
        if run["status"] == "completed":
            if not raw_path.is_file():
                raise FileNotFoundError(
                    f"Completed run has no raw CSV: {raw_path}"
                )
            frame = pd.read_csv(raw_path)
            row.update(
                compute_experiment_metrics(
                    frame,
                    fault_injection_time_s=fault_time,
                    safe_temp_threshold_c=float(
                        safety["winding_critical_C"]
                    ),
                    nominal_temp_c=float(safety["winding_warning_C"]),
                    intervention_temp_c=float(
                        safety["winding_intervention_C"]
                    ),
                    buffered_temp_c=float(safety["winding_buffered_C"]),
                )
            )
            row["run_id"] = run["run_id"]
            row["scenario"] = run["scenario"]
            row["controller"] = run["controller"]
            row["status"] = run["status"]
            row["return_code"] = run["return_code"]
            row["raw_csv"] = run["raw_csv"]
        rows.append(row)
    return manifest, rows


def _plot_temperature(
    campaign: Path,
    scenario: str,
    runs: list[dict[str, Any]],
    fault_time_s: float,
    warning_C: float,
    critical_C: float,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.8))
    for run in runs:
        if run["scenario"] != scenario or run["status"] != "completed":
            continue
        frame = pd.read_csv(run["raw_csv"])
        color = CONTROLLER_COLORS.get(run["controller"], None)
        ax.plot(
            frame["time_s"],
            frame["T_winding_C"],
            color=color,
            linewidth=1.8,
            label=f"{run['controller']} plant",
        )
        if "estimated_winding_C" in frame:
            ax.plot(
                frame["time_s"],
                frame["estimated_winding_C"],
                color=color,
                linestyle=":",
                linewidth=1.0,
                alpha=0.8,
                label=f"{run['controller']} estimate",
            )
    ax.axvline(
        fault_time_s,
        color="#111827",
        linestyle="--",
        linewidth=1.2,
        label="fault injection",
    )
    ax.axhline(
        warning_C,
        color="#eab308",
        linestyle="--",
        linewidth=1.0,
        label=f"warning {warning_C:g} °C",
    )
    ax.axhline(
        critical_C,
        color="#dc2626",
        linestyle="-.",
        linewidth=1.0,
        label=f"critical {critical_C:g} °C",
    )
    ax.set(
        title=f"{scenario}: winding temperature and Twin estimate",
        xlabel="Simulation time (s)",
        ylabel="Temperature (°C)",
    )
    ax.grid(True, alpha=0.25)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(campaign / "figures" / f"temperature_{scenario}.png", dpi=180)
    plt.close(fig)


def _plot_load_command(
    campaign: Path,
    scenario: str,
    runs: list[dict[str, Any]],
    fault_time_s: float,
) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.2))
    for run in runs:
        if run["scenario"] != scenario or run["status"] != "completed":
            continue
        frame = pd.read_csv(run["raw_csv"])
        ax.plot(
            frame["time_s"],
            frame["u_load_torque_pu"],
            color=CONTROLLER_COLORS.get(run["controller"]),
            linewidth=1.8,
            label=run["controller"],
        )
    ax.axvline(fault_time_s, color="#111827", linestyle="--", label="fault injection")
    ax.set(
        title=f"{scenario}: load command",
        xlabel="Simulation time (s)",
        ylabel="Load command (pu)",
        ylim=(0.0, 1.05),
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(campaign / "figures" / f"load_command_{scenario}.png", dpi=180)
    plt.close(fig)


def _plot_comparisons(
    campaign: Path,
    rows: list[dict[str, Any]],
    fault_time_s: float,
) -> None:
    completed = [row for row in rows if row["status"] == "completed"]
    frame = pd.DataFrame(completed)
    if frame.empty:
        return

    fig, ax = plt.subplots(figsize=(9, 6))
    for controller, group in frame.groupby("controller"):
        ax.scatter(
            group["useful_mechanical_work_kWh"],
            group["electrical_energy_kWh"],
            label=controller,
            color=CONTROLLER_COLORS.get(controller),
            alpha=0.85,
            s=48,
        )
    for _, row in frame.iterrows():
        ax.annotate(
            row["scenario"],
            (
                row["useful_mechanical_work_kWh"],
                row["electrical_energy_kWh"],
            ),
            fontsize=6,
            alpha=0.65,
        )
    ax.set(
        title="Electrical energy and useful shaft work",
        xlabel="Useful mechanical work (kWh)",
        ylabel="Electrical input energy (kWh)",
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(campaign / "figures" / "energy_vs_useful_work.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    scenarios = list(dict.fromkeys(frame["scenario"].tolist()))
    x = np.arange(len(scenarios))
    width = 0.38
    for offset, (metric, label, color) in enumerate(
        (
            ("prediction_mae_30s_C", "30 s MAE", "#2563eb"),
            ("prediction_mae_60s_C", "60 s MAE", "#f97316"),
        )
    ):
        values = []
        for scenario in scenarios:
            subset = frame[frame["scenario"] == scenario]
            values.append(float(subset[metric].mean()))
        ax.bar(
            x + (offset - 0.5) * width,
            values,
            width,
            label=label,
            color=color,
        )
    ax.set(
        title="Temperature forecast MAE by scenario",
        xlabel="Scenario",
        ylabel="Forecast MAE (°C)",
        xticks=x,
        xticklabels=scenarios,
    )
    ax.tick_params(axis="x", rotation=35)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(campaign / "figures" / "prediction_mae.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    runtime = frame.pivot(
        index="scenario",
        columns="controller",
        values="mean_solver_step_time_ms",
    )
    runtime.plot.bar(ax=ax, color=CONTROLLER_COLORS)
    ax.set(
        title="FMU solver-step execution time",
        xlabel="Scenario",
        ylabel="Mean time per FMU communication interval (ms)",
    )
    ax.tick_params(axis="x", rotation=35)
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(title="Controller")
    fig.tight_layout()
    fig.savefig(campaign / "figures" / "fmu_runtime.png", dpi=180)
    plt.close(fig)

    for scenario in scenarios:
        group = [
            run
            for run in rows
            if run["scenario"] == scenario and run["status"] == "completed"
        ]
        if not group or not any(
            "fault_severity_true" in pd.read_csv(run["raw_csv"]).columns
            for run in group
        ):
            continue
        fig, ax = plt.subplots(figsize=(9, 5.2))
        for run in group:
            trace = pd.read_csv(run["raw_csv"])
            ax.plot(
                trace["time_s"],
                trace["fault_severity_true"],
                color=CONTROLLER_COLORS.get(run["controller"]),
                linestyle="-",
                alpha=0.6,
                label=f"{run['controller']} injected index",
            )
            ax.plot(
                trace["time_s"],
                trace["fault_severity_estimated"],
                color=CONTROLLER_COLORS.get(run["controller"]),
                linestyle=":",
                linewidth=1.2,
                label=f"{run['controller']} anomaly score",
            )
        ax.set(
            title=f"{scenario}: injected severity index and estimated score",
            xlabel="Simulation time (s)",
            ylabel="Dimensionless index / score (different scales)",
        )
        ax.axvline(
            fault_time_s,
            color="#111827",
            linestyle="--",
            label="fault injection",
        )
        ax.grid(True, alpha=0.25)
        ax.legend(ncol=2, fontsize=7)
        fig.tight_layout()
        fig.savefig(
            campaign / "figures" / f"fault_severity_{scenario}.png",
            dpi=180,
        )
        plt.close(fig)


def _plot_aas_latency(campaign: Path, manifest: dict[str, Any]) -> bool:
    traces: list[pd.DataFrame] = []
    for run in manifest.get("runs", []):
        raw_path = Path(run.get("raw_csv", ""))
        detail = raw_path.with_name(f"{raw_path.stem}_basyx_detail.csv")
        if run.get("status") == "completed" and detail.is_file():
            frame = pd.read_csv(detail)
            frame["run_id"] = run["run_id"]
            traces.append(frame)
    if not traces:
        return False
    data = pd.concat(traces, ignore_index=True)
    columns = [
        column
        for column in (
            "write_latency_ms",
            "read_latency_ms",
            "end_to_end_loop_latency_ms",
        )
        if column in data.columns
    ]
    if not columns:
        return False
    fig, ax = plt.subplots(figsize=(10, 5.2))
    data[columns].plot(ax=ax, alpha=0.7, linewidth=1.1)
    ax.set(
        title="Measured BaSyx synchronization latency",
        xlabel="Synchronization attempt",
        ylabel="Latency (ms)",
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(campaign / "figures" / "aas_latency.png", dpi=180)
    plt.close(fig)
    data.to_csv(campaign / "aas_latency_samples.csv", index=False)
    return True


def _load_aas_evidence(summary_path: Path, campaign: Path) -> dict[str, Any]:
    summary_path = summary_path.resolve()
    if not summary_path.is_file():
        raise FileNotFoundError(f"AAS summary not found: {summary_path}")
    suffix = "_summary.json"
    if not summary_path.name.endswith(suffix):
        raise ValueError("AAS evidence must be an *_summary.json file")
    detail_path = summary_path.with_name(
        f"{summary_path.name[:-len(suffix)]}_detail.csv"
    )
    if not detail_path.is_file():
        raise FileNotFoundError(f"AAS detail CSV not found: {detail_path}")

    metrics = json.loads(summary_path.read_text(encoding="utf-8"))
    required_metrics = (
        "update_attempts",
        "update_successes",
        "read_attempts",
        "read_successes",
        "snapshot_alignment_attempts",
        "snapshot_alignment_successes",
        "aas_write_latency_mean_ms",
        "aas_read_latency_mean_ms",
        "aas_read_latency_p95_ms",
        "end_to_end_loop_latency_mean_ms",
    )
    missing = [key for key in required_metrics if key not in metrics]
    if missing:
        raise ValueError(f"AAS summary is missing metrics: {', '.join(missing)}")
    detail = pd.read_csv(detail_path)
    if detail.empty:
        raise ValueError(f"AAS detail CSV contains no measurements: {detail_path}")

    def relative_path(path: Path) -> str:
        return os.path.relpath(path, start=campaign.resolve()).replace("\\", "/")

    return {
        "summary_path": relative_path(summary_path),
        "summary_argument": os.path.relpath(
            summary_path, start=PROJECT_ROOT
        ).replace("\\", "/"),
        "detail_path": relative_path(detail_path),
        "detail_rows": len(detail),
        "metrics": metrics,
    }


def _write_report(
    campaign: Path,
    manifest: dict[str, Any],
    rows: list[dict[str, Any]],
    aas_plot_created: bool,
    aas_evidence: dict[str, Any] | None,
) -> None:
    completed = [row for row in rows if row["status"] == "completed"]
    failed = [row for row in rows if row["status"] != "completed"]
    lines = [
        "# Induction-motor Digital Twin research report",
        "",
        f"- Campaign: `{manifest['campaign_id']}`",
        f"- Plant: `{manifest['protocol']['plant_model']}`",
        f"- Scenario/controller cases: {len(rows)}",
        f"- Completed: {len(completed)}",
        f"- Failed: {len(failed)}",
        f"- Simulation: {manifest['protocol']['simulation_stop_time_s']:g} s; "
        f"fault at {manifest['protocol']['fault_injection_time_s']:g} s; "
        f"step {manifest['protocol']['communication_step_s']:g} s",
        "- Evidence type: deterministic simulation; not field or manufacturer validation.",
        "",
        "## Method",
        "",
        "All reported tables and plots are regenerated from the raw per-run CSVs "
        "using the metric definitions in `METRIC_DEFINITIONS.md`. Each case uses "
        "the same plant and protocol; controller information differences are "
        "documented in the project README. There is one deterministic case per "
        "scenario/controller, so no confidence intervals or statistical "
        "significance are reported.",
        "",
        "## Controller/scenario results",
        "",
        "The full machine-readable table is `summary_metrics.csv`. The table below "
        "reports measured maximum winding temperature, critical-limit exposure, "
        "post-fault output, estimated-state error, and runtime for every completed "
        "case.",
        "",
        "| Scenario | Controller | Max winding (°C) | Critical time (s) | Post-fault work (kWh) | Winding MAE (°C) | Solver RT factor |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in completed:
        lines.append(
            f"| {row['scenario']} | {row['controller']} | "
            f"{_format(row.get('max_winding_temperature_C'))} | "
            f"{_format(row.get('time_above_critical_s'))} | "
            f"{_format(row.get('post_fault_useful_work_kWh'))} | "
            f"{_format(row.get('winding_estimation_mae_C'))} | "
            f"{_format(row.get('real_time_factor'))} |"
        )
    lines.extend(
        (
            "",
            "## Fault severity interpretation",
            "",
            "The injected severity index and estimated anomaly score are reported "
            "separately. Their scales are not calibrated to the same physical "
            "meaning, so no severity MAE or physical severity accuracy is claimed. "
            "Their traces, when available, are saved under `figures/`.",
            "",
            "## BaSyx evidence",
            "",
        )
    )
    if aas_plot_created:
        lines.extend(
            (
                "An AAS latency plot and raw synchronization samples are present. "
                "Read/write/snapshot alignment success and latency percentiles are "
                "in the associated run's metrics JSON and detailed CSV.",
            )
        )
    elif aas_evidence:
        metrics = aas_evidence["metrics"]
        lines.extend(
            (
                "The 33-case controller campaign did not enable AAS. The following "
                "measurements are from a separate live BaSyx smoke experiment; they "
                "are reported separately and are not mixed into controller results.",
                "",
                f"Source: [`{aas_evidence['summary_path']}`]"
                f"(`{aas_evidence['summary_path']}`); detailed samples: "
                f"[`{aas_evidence['detail_path']}`]"
                f"(`{aas_evidence['detail_path']}`).",
                "",
                "| Measure | Observed result |",
                "|---|---:|",
                f"| Successful AAS writes | {metrics['update_successes']}/"
                f"{metrics['update_attempts']} "
                f"({_format(metrics.get('update_success_rate_percent'))}%) |",
                f"| Successful reads | {metrics['read_successes']}/"
                f"{metrics['read_attempts']} "
                f"({_format(metrics.get('read_success_rate_percent'))}%) |",
                f"| Snapshot alignment | "
                f"{metrics['snapshot_alignment_successes']}/"
                f"{metrics['snapshot_alignment_attempts']} "
                f"({_format(metrics.get('snapshot_alignment_success_rate_percent'))}%) |",
                f"| AAS write mean | "
                f"{_format(metrics['aas_write_latency_mean_ms'])} ms |",
                f"| Read mean / p95 | "
                f"{_format(metrics['aas_read_latency_mean_ms'])} / "
                f"{_format(metrics['aas_read_latency_p95_ms'])} ms |",
                f"| End-to-end loop mean | "
                f"{_format(metrics['end_to_end_loop_latency_mean_ms'])} ms |",
                f"| Controller-only mean | "
                f"{_format(metrics.get('controller_only_mean_latency_ms'))} ms |",
                "",
                "This smoke test recorded one synchronization snapshot (one write "
                "and one end-to-end loop sample). Therefore write and loop "
                "percentiles are single observations, not latency distributions. "
                "Read percentiles summarize the individual property reads within "
                "that snapshot, not repeated loop cycles. The measured end-to-end "
                "loop is compared with the 500 ms control interval only as a "
                "single-run feasibility warning, not a real-time guarantee.",
            )
        )
    else:
        lines.extend(
            (
                "No completed AAS detail trace was generated. Live AAS latency and "
                "success metrics are not asserted; see the manifest for any failed "
                "BaSyx-enabled run.",
            )
        )
    lines.extend(("", "## Failed or incomplete cases", ""))
    if failed:
        for row in failed:
            lines.append(
                f"- `{row['run_id']}`: return code {row['return_code']}; "
                f"{row.get('error') or 'no detailed error saved'}"
            )
    else:
        lines.append("- None.")
    reproduce_command = (
        "python -m analysis.generate_research_artifacts --campaign "
        f"results/research_evaluation/{manifest['campaign_id']}"
    )
    if aas_evidence:
        reproduce_command += (
            " --aas-evidence " + aas_evidence["summary_argument"]
        )
    lines.extend(
        (
            "",
            "## Limitations",
            "",
            "- The induction motor parameters are based on the MSL reference example, "
            "not an identified manufacturer product.",
            "- The winding/frame thermal RC network, fault strengths, and safety "
            "thresholds are explicit assumptions/configuration.",
            "- The plant is rotational-only and does not represent radial vibration "
            "or mechanical unbalance.",
            "- Deterministic simulation results do not establish physical or "
            "manufacturer validation.",
            "- Simulation throughput is not hardware real-time certification.",
            "",
            "## Reproduction",
            "",
            "From the repository root, run "
            "`python -m experiments.run_research_evaluation` to create a new campaign, "
            "then regenerate this report from saved raw evidence with "
            f"`{reproduce_command}`.",
            "",
            "The descriptive historical reduced-order comparison is in "
            "`MODEL_COMPARISON.md`; regenerate it from preserved legacy and "
            "induction raw traces with `python -m analysis.generate_model_comparison`.",
            "",
        )
    )
    (campaign / "RESEARCH_REPORT.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def generate(campaign: Path, aas_evidence_path: Path | None = None) -> None:
    campaign = campaign.resolve()
    campaign.mkdir(parents=True, exist_ok=True)
    (campaign / "figures").mkdir(exist_ok=True)
    manifest, rows = _load_run_rows(campaign)
    aas_evidence = (
        _load_aas_evidence(aas_evidence_path, campaign)
        if aas_evidence_path is not None
        else None
    )
    if aas_evidence:
        (campaign / "aas_evidence_summary.json").write_text(
            json.dumps(aas_evidence, indent=2) + "\n",
            encoding="utf-8",
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(campaign / "summary_metrics.csv", index=False)
    summary.to_csv(campaign / "controller_scenario_comparison.csv", index=False)

    config_path = PROJECT_ROOT / "config" / "twin_config.yaml"
    import yaml

    with config_path.open("r", encoding="utf-8") as source:
        config = yaml.safe_load(source)
    safety = config["induction_motor_digital_twin"]["safety"]
    fault_time = float(manifest["protocol"]["fault_injection_time_s"])
    for scenario in manifest["protocol"]["scenarios"]:
        _plot_temperature(
            campaign,
            scenario,
            rows,
            fault_time,
            float(safety["winding_warning_C"]),
            float(safety["winding_critical_C"]),
        )
        _plot_load_command(campaign, scenario, rows, fault_time)
    _plot_comparisons(
        campaign,
        rows,
        float(manifest["protocol"]["fault_injection_time_s"]),
    )
    aas_plot_created = _plot_aas_latency(campaign, manifest)
    _write_report(campaign, manifest, rows, aas_plot_created, aas_evidence)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Recompute research tables and plots from saved raw runs."
    )
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument(
        "--aas-evidence",
        type=Path,
        help="Optional separate BaSyx smoke-test *_summary.json evidence",
    )
    args = parser.parse_args()
    generate(args.campaign, args.aas_evidence)
    print(f"Research artifacts saved in {args.campaign.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
