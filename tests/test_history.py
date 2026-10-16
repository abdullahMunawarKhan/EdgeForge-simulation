"""Tests for EdgeForge historical run and failure storage (Milestone 3).

All tests are completely offline and self-contained; no CARLA simulator,
GPU, Torch, or YOLO model downloads are required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from edgeforge.data.history import (
    RunHistoryStore,
    get_history_store,
    import_report_to_history,
    list_historical_runs,
    load_failures_from_history,
    load_run_from_history,
    main as history_main,
    save_run_to_history,
)
from edgeforge.data.models import HistoricalRunRecord, PerceptionFailureRecord
from edgeforge.perception.validation import (
    RunValidationMetrics,
    export_failure_report,
    export_run_report,
)


def _make_dummy_failure(
    run_id: str = "run_test_01",
    scenario_id: str = "scenario_fog_01",
    failure_type: str = "missed_detection",
    severity: str = "high",
    frame_id: int = 10,
    confidence: float | None = None,
    iou: float | None = None,
) -> PerceptionFailureRecord:
    return PerceptionFailureRecord(
        run_id=run_id,
        scenario_id=scenario_id,
        failure_type=failure_type,
        severity=severity,
        object_class="car",
        confidence=confidence,
        iou=iou,
        frame_id=frame_id,
        message=f"Test failure: {failure_type}",
    )


def test_save_and_load_completed_run(tmp_path: Path) -> None:
    """A completed run can be saved and loaded with all metrics and parameters preserved."""
    store = RunHistoryStore(tmp_path)

    run_record = HistoricalRunRecord(
        run_id="run_20261016_001",
        scenario_id="scenario_urban_rain",
        timestamp="2026-10-16T10:00:00Z",
        iou_threshold=0.5,
        frames_processed=100,
        predictions=120,
        ground_truth_objects=110,
        true_positives=95,
        false_positives=25,
        missed_detections=15,
        precision=95 / (95 + 25),
        recall=95 / (95 + 15),
        f1=2 * (95 / 120) * (95 / 110) / ((95 / 120) + (95 / 110)),
        matched_iou=0.812,
        scenario_conditions={"weather": {"fog_density": 10.0, "precipitation": 40.0}},
        parameters={"fixed_delta_seconds": 0.05},
        failure_count=0,
        metadata={"map": "Town01", "detector": "yolov8n"},
    )

    saved = store.save_run(run_record)
    assert saved.run_id == "run_20261016_001"
    assert store.has_run("run_20261016_001")

    # Load back
    loaded = store.get_run("run_20261016_001")
    assert loaded.run_id == "run_20261016_001"
    assert loaded.scenario_id == "scenario_urban_rain"
    assert loaded.timestamp == "2026-10-16T10:00:00Z"
    assert loaded.frames_processed == 100
    assert loaded.predictions == 120
    assert loaded.ground_truth_objects == 110
    assert loaded.true_positives == 95
    assert loaded.false_positives == 25
    assert loaded.missed_detections == 15
    assert loaded.tp == 95
    assert loaded.fp == 25
    assert loaded.fn == 15
    assert loaded.false_negatives == 15
    assert loaded.precision == pytest.approx(95 / 120)
    assert loaded.recall == pytest.approx(95 / 110)
    assert loaded.matched_iou == pytest.approx(0.812)
    assert loaded.matched_box_iou == pytest.approx(0.812)
    assert loaded.scenario_conditions == {"weather": {"fog_density": 10.0, "precipitation": 40.0}}
    assert loaded.parameters == {"fixed_delta_seconds": 0.05}
    assert loaded.metadata == {"map": "Town01", "detector": "yolov8n"}


def test_save_and_load_associated_failure_records(tmp_path: Path) -> None:
    """Structured failure records associated with a run are persisted in JSONL and loaded accurately."""
    store = RunHistoryStore(tmp_path)

    f1 = _make_dummy_failure(failure_type="missed_detection", severity="high", frame_id=1)
    f2 = _make_dummy_failure(
        failure_type="poor_localization",
        severity="medium",
        frame_id=5,
        confidence=0.88,
        iou=0.42,
    )
    f3 = _make_dummy_failure(
        failure_type="low_confidence",
        severity="low",
        frame_id=12,
        confidence=0.35,
    )

    run_data = {
        "run_id": "run_with_failures_01",
        "scenario_id": "scenario_fog_01",
        "frames_processed": 50,
        "true_positives": 40,
        "false_positives": 10,
        "missed_detections": 5,
        "precision": 0.8,
        "recall": 0.888,
        "f1": 0.842,
        "matched_iou": 0.77,
        "scenario_conditions": {"weather": {"fog_density": 35.0}},
    }

    saved = store.save_run(run_data, failures=[f1, f2, f3])
    assert saved.failure_count == 3

    # Check failure file on disk
    failures_file = store.failures_path("run_with_failures_01")
    assert failures_file.is_file()
    lines = failures_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3

    # Load via store
    loaded_failures = store.get_run_failures("run_with_failures_01")
    assert len(loaded_failures) == 3
    assert loaded_failures[0].failure_type == "missed_detection"
    assert loaded_failures[0].severity == "high"
    assert loaded_failures[0].run_id == "run_with_failures_01"
    assert loaded_failures[1].failure_type == "poor_localization"
    assert loaded_failures[1].iou == pytest.approx(0.42)
    assert loaded_failures[2].failure_type == "low_confidence"
    assert loaded_failures[2].confidence == pytest.approx(0.35)


def test_multiple_runs_sharing_scenario_id(tmp_path: Path) -> None:
    """Multiple runs can share the same scenario_id with distinct run_ids."""
    store = RunHistoryStore(tmp_path)

    for i in range(1, 4):
        store.save_run(
            {
                "run_id": f"run_batch_{i:03d}",
                "scenario_id": "scenario_shared_highway",
                "timestamp": f"2026-10-16T1{i}:00:00Z",
                "precision": 0.75 + (i * 0.05),
                "recall": 0.80,
                "f1": 0.77,
                "matched_iou": 0.70,
            }
        )

    # Save a run with another scenario
    store.save_run(
        {
            "run_id": "run_other_999",
            "scenario_id": "scenario_different_city",
            "timestamp": "2026-10-16T20:00:00Z",
        }
    )

    all_runs = store.list_runs()
    assert len(all_runs) == 4

    highway_runs = store.list_runs(scenario_id="scenario_shared_highway")
    assert len(highway_runs) == 3
    run_ids = {r.run_id for r in highway_runs}
    assert run_ids == {"run_batch_001", "run_batch_002", "run_batch_003"}

    scenarios = store.get_tested_scenarios()
    assert scenarios == ["scenario_different_city", "scenario_shared_highway"]


def test_reject_duplicate_run_id_unless_explicit_overwrite(tmp_path: Path) -> None:
    """Overwriting an existing run_id raises FileExistsError unless overwrite=True."""
    store = RunHistoryStore(tmp_path)

    store.save_run(
        {
            "run_id": "run_protected_001",
            "scenario_id": "scenario_a",
            "precision": 0.80,
        }
    )

    # Attempting to save with the same run_id without overwrite must fail
    with pytest.raises(FileExistsError, match="already exists"):
        store.save_run(
            {
                "run_id": "run_protected_001",
                "scenario_id": "scenario_b",
                "precision": 0.99,
            },
            overwrite=False,
        )

    # Verify original run was not modified
    orig = store.get_run("run_protected_001")
    assert orig.scenario_id == "scenario_a"
    assert orig.precision == pytest.approx(0.80)

    # Now overwrite explicitly
    updated = store.save_run(
        {
            "run_id": "run_protected_001",
            "scenario_id": "scenario_b",
            "precision": 0.99,
        },
        overwrite=True,
    )
    assert updated.scenario_id == "scenario_b"
    assert updated.precision == pytest.approx(0.99)

    reloaded = store.get_run("run_protected_001")
    assert reloaded.scenario_id == "scenario_b"
    assert reloaded.precision == pytest.approx(0.99)


def test_missing_optional_metadata_handled_safely(tmp_path: Path) -> None:
    """Missing optional metadata does not crash the store and does not invent fake values."""
    store = RunHistoryStore(tmp_path)

    # Minimal run dict: only run_id and scenario_id provided
    record = store.save_run(
        {
            "run_id": "run_minimal_01",
            "scenario_id": "scenario_minimal",
        }
    )

    loaded = store.get_run("run_minimal_01")
    assert loaded.scenario_conditions == {}
    assert loaded.parameters == {}
    assert loaded.metadata == {}
    # No invented None values in metadata
    assert "server" not in loaded.metadata
    assert "detector" not in loaded.metadata
    assert loaded.failure_count == 0


def test_retain_weather_lighting_camera_and_actor_configuration(tmp_path: Path) -> None:
    """Full simulation report preserves weather, lighting, actor configuration and camera settings."""
    store = RunHistoryStore(tmp_path)

    report_payload = {
        "status": "completed",
        "map": "Town03",
        "server": {"host": "127.0.0.1", "port": 2000},
        "detector": {"model": "yolov8n.pt", "device": "cpu"},
        "scenario": {
            "scenario_id": "phase4-live-validation",
            "run_id": "run_carla_full_001",
            "ego_spawn_index": 2,
            "ego_actor_id": 401,
            "target_vehicles": [{"actor_id": 402, "model": "tesla.model3"}],
            "target_count": 1,
            "fixed_delta_seconds": 0.05,
            "weather": {
                "fog_density": 45.0,
                "precipitation": 20.0,
                "sun_altitude_angle": 15.0,
            },
            "lighting": {
                "sun_azimuth_angle": 120.0,
                "sun_altitude_angle": 15.0,
            },
            "camera": {
                "width": 1280,
                "height": 720,
                "horizontal_fov_degrees": 90.0,
            },
        },
        "metrics": {
            "frames_processed": 50,
            "predictions": 50,
            "ground_truth_objects": 50,
            "true_positives": 48,
            "false_positives": 2,
            "missed_detections": 2,
            "precision": 0.96,
            "recall": 0.96,
            "f1": 0.96,
            "matched_iou": 0.85,
        },
        "failures": [
            {
                "failure_type": "poor_localization",
                "severity": "medium",
                "object_class": "car",
                "iou": 0.48,
                "frame_id": 12,
            }
        ],
    }

    saved = store.save_run(report_payload)
    assert saved.run_id == "run_carla_full_001"
    assert saved.scenario_id == "phase4-live-validation"

    loaded = store.get_run("run_carla_full_001")
    cond = loaded.scenario_conditions

    assert "weather" in cond
    assert cond["weather"]["fog_density"] == 45.0
    assert cond["weather"]["precipitation"] == 20.0

    assert "lighting" in cond
    assert cond["lighting"]["sun_azimuth_angle"] == 120.0

    assert "camera" in cond
    assert cond["camera"]["width"] == 1280
    assert cond["camera"]["horizontal_fov_degrees"] == 90.0

    assert "actor_configuration" in cond
    assert cond["actor_configuration"]["ego_spawn_index"] == 2
    assert cond["actor_configuration"]["target_count"] == 1

    # Check that failure record inherited environmental conditions
    failures = store.get_run_failures("run_carla_full_001")
    assert len(failures) == 1
    assert failures[0].scenario_conditions["weather"]["fog_density"] == 45.0


def test_empty_runs_and_runs_without_failures(tmp_path: Path) -> None:
    """Empty runs with zero processed frames or zero failures are stored and retrieved without error."""
    store = RunHistoryStore(tmp_path)

    store.save_run(
        {
            "run_id": "run_zero_failures",
            "scenario_id": "scenario_clean",
            "frames_processed": 10,
            "true_positives": 10,
            "false_positives": 0,
            "missed_detections": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "matched_iou": 0.92,
        },
        failures=[],
    )

    failures = store.get_run_failures("run_zero_failures")
    assert failures == []

    # Run with 0 frames
    empty_run = store.save_run(
        {
            "run_id": "run_zero_frames",
            "scenario_id": "scenario_aborted",
            "frames_processed": 0,
            "predictions": 0,
            "ground_truth_objects": 0,
        }
    )
    assert empty_run.frames_processed == 0
    assert store.get_run_failures("run_zero_frames") == []


def test_malformed_historical_data_handling(tmp_path: Path) -> None:
    """Malformed run files and failure records are detected with clear errors, or skipped in non-strict listing."""
    store = RunHistoryStore(tmp_path)

    # 1. Non-existent run raises KeyError
    with pytest.raises(KeyError, match="not found"):
        store.get_run("non_existent_run_999")

    # 2. Corrupted run JSON
    bad_run_file = store.runs_dir / "corrupted_run.json"
    bad_run_file.write_text("NOT_VALID_JSON{", encoding="utf-8")

    with pytest.raises(ValueError, match="Corrupted run record JSON"):
        store.get_run("corrupted_run")

    # In strict mode, listing runs raises ValueError
    with pytest.raises(ValueError):
        store.list_runs(strict=True)

    # In non-strict mode, corrupted run is skipped gracefully
    runs = store.list_runs(strict=False)
    assert not any(r.run_id == "corrupted_run" for r in runs)

    # 3. Corrupted failure JSONL
    store.save_run({"run_id": "valid_run_bad_failures", "scenario_id": "scen_test"})
    failures_file = store.failures_path("valid_run_bad_failures")
    failures_file.write_text(
        '{"failure_type": "missed_detection", "severity": "high"}\nBAD_LINE_NOT_JSON\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Malformed failure record"):
        store.get_run_failures("valid_run_bad_failures", strict=True)

    lenient_failures = store.get_run_failures("valid_run_bad_failures", strict=False)
    assert len(lenient_failures) == 1
    assert lenient_failures[0].failure_type == "missed_detection"


def test_interrupted_write_preserves_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An interrupted or failed write cleans up partial files and does not corrupt existing history."""
    store = RunHistoryStore(tmp_path)

    # Save a valid initial run
    initial = store.save_run(
        {
            "run_id": "run_initial_safe",
            "scenario_id": "scen_safe",
            "precision": 0.85,
        }
    )
    assert store.has_run("run_initial_safe")

    # Simulate an I/O crash during the metadata write step of a new run
    orig_atomic_write = store._atomic_write_text

    def failing_atomic_write(target_path: Path, content: str) -> None:
        if target_path.name == "run_crashed.json":
            raise IOError("Simulated disk error during run write")
        orig_atomic_write(target_path, content)

    monkeypatch.setattr(store, "_atomic_write_text", failing_atomic_write)

    f1 = _make_dummy_failure(run_id="run_crashed")
    with pytest.raises(IOError, match="Simulated disk error"):
        store.save_run(
            {"run_id": "run_crashed", "scenario_id": "scen_crashed"},
            failures=[f1],
        )

    # Ensure partial files for run_crashed were cleaned up
    assert not store.has_run("run_crashed")
    assert not store.failures_path("run_crashed").exists()

    # Ensure existing history is completely untouched
    safe = store.get_run("run_initial_safe")
    assert safe.precision == pytest.approx(0.85)


def test_import_existing_metrics_json_and_failure_jsonl(tmp_path: Path) -> None:
    """Existing validation reports (metrics JSON + failure JSONL) can be imported into the store."""
    export_dir = tmp_path / "exports"
    export_dir.mkdir()

    f1 = PerceptionFailureRecord(
        failure_type="poor_localization",
        object_class="truck",
        predicted_bbox=[0, 0, 10, 10],
        ground_truth_bbox=[0, 0, 15, 15],
        iou=0.44,
        severity="high",
        frame_id=15,
        scenario_id="scenario_import_test",
        run_id="run_exported_101",
    )

    metrics_obj = RunValidationMetrics(
        frames_processed=20,
        predictions=25,
        ground_truth_objects=20,
        true_positives=18,
        false_positives=7,
        missed_detections=2,
        precision=18 / 25,
        recall=18 / 20,
        f1=0.8,
        matched_iou=0.79,
        iou_threshold=0.5,
        failures=(f1,),
        scenario_id="scenario_import_test",
        run_id="run_exported_101",
        scenario_conditions={"weather": {"fog_density": 30.0}},
        parameters={"fixed_delta_seconds": 0.05},
    )

    metrics_file = export_dir / "metrics.json"
    failures_file = export_dir / "failures.jsonl"
    export_run_report(
        metrics_obj,
        metrics_file,
        failures_destination=failures_file,
        failure_format="jsonl",
    )

    store = RunHistoryStore(tmp_path / "history")
    imported = store.import_validation_report(
        metrics_path=metrics_file,
        failures_path=failures_file,
    )

    assert imported.run_id == "run_exported_101"
    assert imported.scenario_id == "scenario_import_test"
    assert imported.true_positives == 18
    assert imported.failure_count == 1

    stored_failures = store.get_run_failures("run_exported_101")
    assert len(stored_failures) == 1
    assert stored_failures[0].failure_type == "poor_localization"
    assert stored_failures[0].object_class == "truck"

    # Non-existent failures file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        store.import_validation_report(
            metrics_path=metrics_file,
            failures_path=export_dir / "non_existent_failures.jsonl",
        )


def test_query_failures_across_runs_by_type_and_severity(tmp_path: Path) -> None:
    """Historical failures can be queried and filtered by type, severity, and scenario."""
    store = RunHistoryStore(tmp_path)

    f1 = _make_dummy_failure(failure_type="missed_detection", severity="critical")
    f2 = _make_dummy_failure(failure_type="missed_detection", severity="low")
    f3 = _make_dummy_failure(failure_type="poor_localization", severity="high")

    store.save_run({"run_id": "run_q1", "scenario_id": "scen_q"}, failures=[f1, f2])
    store.save_run({"run_id": "run_q2", "scenario_id": "scen_q"}, failures=[f3])

    # All failures
    all_f = store.get_failures(scenario_id="scen_q")
    assert len(all_f) == 3

    # Filter by failure_type
    missed = store.get_failures(scenario_id="scen_q", failure_type="missed_detection")
    assert len(missed) == 2

    # Filter by min_severity
    high_or_crit = store.get_failures(scenario_id="scen_q", min_severity="high")
    assert len(high_or_crit) == 2  # critical and high, excludes low


def test_find_similar_failures(tmp_path: Path) -> None:
    """Failures occurring under similar conditions can be retrieved within a numeric tolerance."""
    store = RunHistoryStore(tmp_path)

    f_fog = _make_dummy_failure(failure_type="missed_detection", severity="high")
    store.save_run(
        {
            "run_id": "run_fog_20",
            "scenario_id": "scen_weather",
            "scenario_conditions": {"weather": {"fog_density": 20.0, "precipitation": 0.0}},
        },
        failures=[f_fog],
    )

    f_rain = _make_dummy_failure(failure_type="poor_localization", severity="medium")
    store.save_run(
        {
            "run_id": "run_rain_80",
            "scenario_id": "scen_weather",
            "scenario_conditions": {"weather": {"fog_density": 80.0, "precipitation": 90.0}},
        },
        failures=[f_rain],
    )

    # Query with short key 'fog_density' within tolerance of 5
    matches = store.find_similar_failures({"fog_density": 22.0}, tolerance=5.0)
    assert len(matches) == 1
    assert matches[0].failure_type == "missed_detection"

    # Query matching rain scenario
    rain_matches = store.find_similar_failures({"weather.fog_density": 82.0}, tolerance=5.0)
    assert len(rain_matches) == 1
    assert rain_matches[0].failure_type == "poor_localization"

    # Query out of range returns empty
    no_matches = store.find_similar_failures({"fog_density": 50.0}, tolerance=5.0)
    assert no_matches == []


def test_coverage_summary_and_unexplored_conditions(tmp_path: Path) -> None:
    """Coverage summary reports parameter ranges and identifies unexplored condition intervals."""
    store = RunHistoryStore(tmp_path)

    store.save_run(
        {
            "run_id": "run_cov_1",
            "scenario_id": "scen_cov_a",
            "scenario_conditions": {"weather": {"fog_density": 10.0}},
            "parameters": {"fixed_delta_seconds": 0.05},
        },
        failures=[_make_dummy_failure(failure_type="missed_detection", severity="high")],
    )
    store.save_run(
        {
            "run_id": "run_cov_2",
            "scenario_id": "scen_cov_a",
            "scenario_conditions": {"weather": {"fog_density": 30.0}},
            "parameters": {"fixed_delta_seconds": 0.05},
        },
        failures=[_make_dummy_failure(failure_type="low_confidence", severity="low")],
    )

    summary = store.get_coverage_summary()
    assert summary["total_runs"] == 2
    assert summary["total_failures"] == 2
    assert summary["failures_by_type"] == {"missed_detection": 1, "low_confidence": 1}
    assert summary["failures_by_severity"] == {"high": 1, "low": 1}

    fog_cov = summary["condition_coverage"]["weather.fog_density"]
    assert fog_cov["min"] == 10.0
    assert fog_cov["max"] == 30.0
    assert fog_cov["distinct_count"] == 2

    # Query unexplored condition intervals
    unexplored = store.get_unexplored_conditions({"fog_density": (0.0, 100.0)})
    assert "fog_density" in unexplored
    entry = unexplored["fog_density"]
    assert entry["tested_range"] == (10.0, 30.0)
    assert entry["untested_intervals"] == [(0.0, 10.0), (30.0, 100.0)]
    assert entry["coverage_ratio"] == pytest.approx(0.20, abs=0.01)


def test_rebuild_index_from_disk(tmp_path: Path) -> None:
    """Index can be rebuilt from disk files if deleted or corrupted."""
    store = RunHistoryStore(tmp_path)

    store.save_run({"run_id": "run_idx_1", "scenario_id": "scen_1", "precision": 0.9})
    store.save_run({"run_id": "run_idx_2", "scenario_id": "scen_2", "precision": 0.8})

    assert store.index_path.is_file()

    # Corrupt index file
    store.index_path.write_text("CORRUPTED_INDEX", encoding="utf-8")

    rebuilt = store.rebuild_index()
    assert len(rebuilt["runs"]) == 2
    assert "run_idx_1" in rebuilt["runs"]
    assert "run_idx_2" in rebuilt["runs"]


def test_top_level_convenience_functions(tmp_path: Path) -> None:
    """Module-level convenience functions work seamlessly."""
    record = save_run_to_history(
        {"run_id": "run_conv_01", "scenario_id": "scen_conv", "precision": 0.95},
        history_dir=tmp_path,
    )
    assert record.run_id == "run_conv_01"

    loaded = load_run_from_history("run_conv_01", history_dir=tmp_path)
    assert loaded.precision == pytest.approx(0.95)

    runs = list_historical_runs(history_dir=tmp_path)
    assert len(runs) == 1

    failures = load_failures_from_history("run_conv_01", history_dir=tmp_path)
    assert failures == []


def test_cli_execution(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI utility executes --list, --summary, --scenarios, and --run commands without error."""
    store = get_history_store(tmp_path)
    store.save_run(
        {
            "run_id": "run_cli_01",
            "scenario_id": "scen_cli",
            "precision": 0.85,
            "recall": 0.80,
            "f1": 0.82,
            "matched_iou": 0.75,
        },
        failures=[_make_dummy_failure(run_id="run_cli_01")],
    )

    with patch("sys.argv", ["history", "--history-dir", str(tmp_path), "--list"]):
        exit_code = history_main()
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "run_cli_01" in captured

    with patch("sys.argv", ["history", "--history-dir", str(tmp_path), "--summary"]):
        exit_code = history_main()
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "total_runs" in captured

    with patch("sys.argv", ["history", "--history-dir", str(tmp_path), "--scenarios"]):
        exit_code = history_main()
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "scen_cli" in captured

    with patch("sys.argv", ["history", "--history-dir", str(tmp_path), "--run", "run_cli_01"]):
        exit_code = history_main()
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert '"run_id": "run_cli_01"' in captured

    with patch("sys.argv", ["history", "--history-dir", str(tmp_path), "--failures", "run_cli_01"]):
        exit_code = history_main()
        assert exit_code == 0
        captured = capsys.readouterr().out
        assert "missed_detection" in captured


def test_validate_carla_perception_integration(tmp_path: Path) -> None:
    """validate_carla_perception CLI automatically saves runs to history unless --no-history is given."""
    from edgeforge.simulation.validate_carla_perception import main as sim_main

    mock_report = {
        "status": "completed",
        "map": "Town01",
        "run_id": "run_sim_cli_100",
        "scenario": {
            "scenario_id": "phase4-live-validation",
            "run_id": "run_sim_cli_100",
            "weather": {"fog_density": 15.0},
        },
        "metrics": {
            "frames_processed": 10,
            "predictions": 10,
            "ground_truth_objects": 10,
            "true_positives": 9,
            "false_positives": 1,
            "missed_detections": 1,
            "precision": 0.9,
            "recall": 0.9,
            "f1": 0.9,
            "matched_iou": 0.8,
        },
        "failures": [
            {
                "failure_type": "missed_detection",
                "severity": "high",
                "object_class": "car",
            }
        ],
    }

    metrics_out = tmp_path / "metrics.json"
    failures_out = tmp_path / "failures.jsonl"
    hist_dir = tmp_path / "history_store"

    # Test 1: By default, run is persisted to history_dir
    with patch(
        "edgeforge.simulation.validate_carla_perception.run_live_validation",
        return_value=mock_report,
    ), patch(
        "sys.argv",
        [
            "validate_carla_perception",
            "--output",
            str(metrics_out),
            "--failures-output",
            str(failures_out),
            "--history-dir",
            str(hist_dir),
        ],
    ):
        ret = sim_main()
        assert ret == 0

    assert metrics_out.is_file()
    assert failures_out.is_file()
    hist_store = RunHistoryStore(hist_dir)
    assert hist_store.has_run("run_sim_cli_100")
    loaded = hist_store.get_run("run_sim_cli_100")
    assert loaded.true_positives == 9
    assert loaded.scenario_conditions["weather"]["fog_density"] == 15.0

    # Test 2: With --no-history, history store is NOT updated
    hist_dir_2 = tmp_path / "history_store_2"
    with patch(
        "edgeforge.simulation.validate_carla_perception.run_live_validation",
        return_value=mock_report,
    ), patch(
        "sys.argv",
        [
            "validate_carla_perception",
            "--output",
            str(tmp_path / "m2.json"),
            "--failures-output",
            str(tmp_path / "f2.jsonl"),
            "--history-dir",
            str(hist_dir_2),
            "--no-history",
        ],
    ):
        ret = sim_main()
        assert ret == 0

    hist_store_2 = RunHistoryStore(hist_dir_2)
    assert not hist_store_2.has_run("run_sim_cli_100")
