import csv
import json

from analysis.generate_research_artifacts import _load_aas_evidence
from analysis.generate_model_comparison import generate as generate_model_comparison
from experiments.run_research_evaluation import _write_comparison


def test_comparison_csv_ignores_non_metric_run_metadata(tmp_path) -> None:
    runs = [
        {
            "run_id": "01_cooling_constrained",
            "scenario": "cooling",
            "controller": "constrained",
            "status": "completed",
            "return_code": 0,
            "raw_csv": "raw.csv",
            "run_log": "run.log",
            "controller_settings": {"max_load": 1.0},
            "basyx_aas_environment_url": "http://localhost:8081",
            "metrics": {"maximum_winding_temperature_C": 96.5},
        }
    ]
    _write_comparison(tmp_path, runs)

    with (tmp_path / "controller_scenario_comparison.csv").open(
        newline="", encoding="utf-8"
    ) as source:
        rows = list(csv.DictReader(source))

    assert len(rows) == 1
    assert rows[0]["scenario"] == "cooling"
    assert rows[0]["maximum_winding_temperature_C"] == "96.5"


def test_load_aas_evidence_requires_paired_summary_and_detail(tmp_path) -> None:
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    evidence_dir = tmp_path / "basyx_smoke"
    evidence_dir.mkdir()
    summary_path = evidence_dir / "smoke_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "update_attempts": 1,
                "update_successes": 1,
                "read_attempts": 12,
                "read_successes": 12,
                "snapshot_alignment_attempts": 1,
                "snapshot_alignment_successes": 1,
                "aas_write_latency_mean_ms": 10.0,
                "aas_read_latency_mean_ms": 2.0,
                "aas_read_latency_p95_ms": 3.0,
                "end_to_end_loop_latency_mean_ms": 20.0,
            }
        ),
        encoding="utf-8",
    )
    detail_path = evidence_dir / "smoke_detail.csv"
    with detail_path.open("w", newline="", encoding="utf-8") as target:
        writer = csv.DictWriter(target, fieldnames=["simulation_time_s"])
        writer.writeheader()
        writer.writerow({"simulation_time_s": 0.0})

    evidence = _load_aas_evidence(summary_path, campaign)

    assert evidence["detail_rows"] == 1
    assert evidence["summary_path"] == "../basyx_smoke/smoke_summary.json"
    assert evidence["metrics"]["update_successes"] == 1


def test_model_comparison_uses_only_shared_scenarios_and_raw_csvs(tmp_path) -> None:
    archive = tmp_path / "archive"
    output = tmp_path / "output"
    archive.mkdir()
    records = []
    for plant, rated_power, initial_temperature, solver_step in (
        ("legacy", 5500.0, 30.0, 0.001),
        ("induction", 18500.0, 90.0, 0.01),
    ):
        for controller in ("baseline", "adaptive", "constrained"):
            csv_path = archive / f"{plant}_{controller}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as target:
                writer = csv.DictWriter(
                    target,
                    fieldnames=[
                        "time_s",
                        "sample_interval_s",
                        "T_winding_C",
                        "speed_rpm",
                        "P_electrical_W",
                        "P_shaft_W",
                        "rated_output_W",
                        "solver_step_time_s",
                    ],
                )
                writer.writeheader()
                for time_s, temperature in (
                    (0.0, initial_temperature),
                    (0.5, initial_temperature + 2.0),
                ):
                    writer.writerow(
                        {
                            "time_s": time_s,
                            "sample_interval_s": 0.5,
                            "T_winding_C": temperature,
                            "speed_rpm": 1460.0,
                            "P_electrical_W": 6000.0,
                            "P_shaft_W": 5500.0,
                            "rated_output_W": rated_power,
                            "solver_step_time_s": solver_step,
                        }
                    )
            records.append(
                {
                    "plant": plant,
                    "scenario": "healthy",
                    "controller": controller,
                    "return_code": 0,
                    "csv": str(csv_path),
                }
            )
    (archive / "campaign.json").write_text(
        json.dumps(records),
        encoding="utf-8",
    )

    run_frame, summary = generate_model_comparison(archive, output)

    assert len(run_frame) == 6
    assert len(summary) == 2
    assert set(summary["plant"]) == {"legacy", "induction"}
    assert set(summary["run_count"]) == {3}
    assert (output / "MODEL_COMPARISON.md").is_file()
