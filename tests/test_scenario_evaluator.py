
import csv

import pytest

from edgeforge.analysis.scenario_evaluator import ScenarioEvaluator
from edgeforge.data.models import ScenarioEvent, ScenarioResult


def test_evaluator_counts_events_and_risk_samples(tmp_path):
    evaluator = ScenarioEvaluator(
        risk_threshold=0.7,
        output_dir=tmp_path,
        output_format="csv",
    )

    scenario = ScenarioResult(
        scenario_name="test_scenario",
        events=[
            ScenarioEvent(
                type="collision",
                severity="critical",
                timestamp=2.0,
                message="Collision detected",
            ),
            ScenarioEvent(
                type="lane_invasion",
                severity="warning",
                timestamp=3.0,
                message="Lane boundary crossed",
            ),
            ScenarioEvent(
                type="near_collision",
                severity="warning",
                timestamp=4.0,
                message="TTC=0.5s",
            ),
            ScenarioEvent(
                type="near_collision",
                severity="warning",
                timestamp=5.0,
                message="TTC=1.5s",
            ),
        ],
    )

    risk_history = [
        {"timestamp": 0.0, "risk_score": 0.8},
        {"timestamp": 2.0, "risk_score": 0.9},
        {"timestamp": 5.0, "risk_score": 0.4},
    ]

    metrics = evaluator.evaluate(scenario, risk_history)

    assert metrics["max_risk_score"] == 0.9
    assert metrics["time_above_threshold"] == 5.0
    assert metrics["collision_count"] == 1.0
    assert metrics["lane_invasion_count"] == 1.0
    assert metrics["near_collisions_ttc_below_1s"] == 1.0


def test_csv_export_creates_file(tmp_path):
    evaluator = ScenarioEvaluator(
        output_dir=tmp_path,
        output_format="csv",
    )
    scenario = ScenarioResult(
        scenario_name="empty_test",
        metrics={"max_risk_score": 0.2},
    )

    output_path = evaluator.export([scenario])

    assert output_path.exists()
    assert output_path.suffix == ".csv"
    assert "empty_test" in output_path.read_text(encoding="utf-8")


def test_evaluator_handles_empty_risk_samples_and_missing_timestamps():
    evaluator = ScenarioEvaluator(risk_threshold=0.7)
    scenario = ScenarioResult(scenario_name="missing-risk-data")

    empty_metrics = evaluator.evaluate(scenario)
    assert empty_metrics["max_risk_score"] == 0.0
    assert empty_metrics["time_above_threshold"] == 0.0

    missing_timestamp_metrics = evaluator.evaluate(
        scenario,
        [{"risk_score": 0.9}, {"timestamp": 1.0}],
    )
    assert missing_timestamp_metrics["max_risk_score"] == 0.9
    assert missing_timestamp_metrics["time_above_threshold"] == 0.0


def test_csv_export_includes_evaluated_run_metrics(tmp_path):
    evaluator = ScenarioEvaluator(output_dir=tmp_path, output_format="csv")
    scenario = ScenarioResult(
        scenario_name="evaluated-run",
        run_id="run-123",
        success=True,
        exit_status="completed",
        duration_s=2.0,
        events=[
            ScenarioEvent(
                type="collision",
                severity="critical",
                timestamp=1.0,
                message="Collision",
            )
        ],
    )
    evaluator.evaluate(
        scenario,
        [
            {"timestamp": 0.0, "risk_score": 0.8},
            {"timestamp": 2.0, "risk_score": 0.2},
        ],
    )

    output_path = evaluator.export([scenario])
    with output_path.open(newline="", encoding="utf-8") as file:
        row = next(csv.DictReader(file))

    assert row["run_id"] == "run-123"
    assert row["collision_count"] == "1.0"
    assert row["max_risk_score"] == "0.8"
    assert row["time_above_threshold"] == "2.0"


def test_parquet_export_reports_missing_engine_clearly(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    import pandas as pd

    def unavailable_engine(*_args, **_kwargs):
        raise ImportError("no parquet engine")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", unavailable_engine)
    evaluator = ScenarioEvaluator(output_dir=tmp_path, output_format="parquet")

    with pytest.raises(ImportError, match="Parquet export requires a Parquet engine"):
        evaluator.export([ScenarioResult(scenario_name="no-parquet-engine")])
