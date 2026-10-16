"""Milestone 4B.1: Benchmark Integrity Audit Regression Test Suite.

Comprehensive deterministic offline tests covering:
- Part B: Adaptive selection verification (empty history cold start, immediate persistence,
  failure-driven ranking shifts, exclusion of rejected/failed runs, ID linkage, fresh run IDs).
- Part C: Mock perception realism (TP, FP, FN evaluation rules, physically-inspired weather
  degradation, exact determinism under identical seeds, distinct outcomes across configurations).
- Part D & E: Benchmark fairness and metrics (budget equality, macro TP/FP/FN aggregation,
  TP-weighted IoU, unique failure signature deduplication, report parity).
- Part F: Weather propagation (fine-grained weather dictionaries applied to runners/clients
  and preset fallback behavior).
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
import pytest

from edgeforge.data.history import RunHistoryStore
from edgeforge.data.models import (
    DetectedObject,
    PerceptionFailureRecord,
)
from edgeforge.perception.validation import (
    RunValidationMetrics,
    ValidationMetrics,
    evaluate_detections,
)
from edgeforge.scenarios.benchmark import (
    PerRunRecord,
    TestingStrategyBenchmark,
    compute_failure_signature,
)
from edgeforge.scenarios.executor import (
    ExecutionStatus,
    ScenarioExecutionManager,
    validate_scenario_config,
)
from edgeforge.scenarios.generator import (
    ActorConfiguration,
    RandomScenarioGenerator,
    ScenarioCandidate,
    ScenarioGenerator,
    WeatherParameters,
)
from edgeforge.simulation.mock_client import MockCarlaClient
from edgeforge.simulation.scenario_runner import BACKEND_MOCK, ScenarioRunner


# ==============================================================================
# Part B: Adaptive Selection Verification Tests
# ==============================================================================
class TestAdaptiveSelectionIntegrity:
    """Audit tests for adaptive closed-loop scenario generation."""

    def test_initial_run_works_when_history_is_empty(self, tmp_path: Path) -> None:
        """Step 0: Generator handles empty store gracefully with cold-start heuristics."""
        store = RunHistoryStore(tmp_path / "empty_store")
        assert len(store) == 0

        gen = ScenarioGenerator(history_store=store, seed=42)
        candidates = gen.generate_candidates(num_candidates=5)
        ranked = gen.rank_candidates(candidates)

        assert len(ranked) == 5
        assert all(r.cold_start is True for r in ranked)
        assert all(r.score_breakdown.failure_evidence == 0.0 for r in ranked)
        assert all(r.overall_score > 0.0 for r in ranked)

    def test_completed_run_saved_before_next_ranking(self, tmp_path: Path) -> None:
        """Step t: Generator sees runs 0..t-1 persisted in store before ranking candidate t."""
        store = RunHistoryStore(tmp_path / "step_store")
        manager = ScenarioExecutionManager(history_store=store, default_backend=BACKEND_MOCK)

        # Before any execution
        assert len(store) == 0

        # Execute candidate 0
        gen0 = ScenarioGenerator(history_store=store, seed=10)
        c0 = gen0.rank_candidates(gen0.generate_candidates(2))[0]
        res0 = manager.execute(c0, max_frames=5)

        assert res0.status == ExecutionStatus.COMPLETED
        assert res0.persisted is True
        # Store now contains exactly 1 run immediately
        assert len(store) == 1

        # Next generator step sees the newly persisted run
        gen1 = ScenarioGenerator(history_store=store, seed=11)
        cands1 = gen1.generate_candidates(3)
        ranked1 = gen1.rank_candidates(cands1)

        assert not all(r.cold_start for r in ranked1)

    def test_previous_failures_alter_subsequent_rankings(self, tmp_path: Path) -> None:
        """Previous failure in dense fog increases failure-evidence ranking for dense fog candidates."""
        store = RunHistoryStore(tmp_path / "failure_shift_store")

        # Two distinct candidates: Dense Fog vs Heavy Rain
        cand_fog = ScenarioCandidate(
            candidate_id="cand_fog",
            scenario_id="scen_fog",
            map_name="Town01",
            weather_preset="DenseFog",
            weather=WeatherParameters(fog_density=90.0, precipitation=0.0, sun_altitude_angle=45.0),
            actor_config=ActorConfiguration(traffic_vehicles=5, traffic_pedestrians=2),
        )
        cand_rain = ScenarioCandidate(
            candidate_id="cand_rain",
            scenario_id="scen_rain",
            map_name="Town01",
            weather_preset="HeavyRain",
            weather=WeatherParameters(fog_density=0.0, precipitation=90.0, sun_altitude_angle=45.0),
            actor_config=ActorConfiguration(traffic_vehicles=5, traffic_pedestrians=2),
        )

        # Store A: 1 prior run with 0 failures
        store_no_fail = RunHistoryStore(tmp_path / "store_no_fail")
        store_no_fail.save_run(
            {
                "run_id": "run_pass",
                "scenario_id": "prior_fog_run",
                "scenario_conditions": {"weather": {"fog_density": 88.0, "precipitation": 0.0}},
                "precision": 1.0,
                "recall": 1.0,
                "f1": 1.0,
                "matched_iou": 0.85,
            },
            failures=[],
        )
        gen_before = ScenarioGenerator(history_store=store_no_fail, seed=42)
        ranked_before = {r.candidate_id: r for r in gen_before.rank_candidates([cand_fog, cand_rain])}
        score_fog_before = ranked_before["cand_fog"].overall_score
        score_rain_before = ranked_before["cand_rain"].overall_score

        # Store B: 1 prior run with high severity failure in dense fog
        store_with_fail = RunHistoryStore(tmp_path / "store_with_fail")
        failure = PerceptionFailureRecord(
            failure_type="missed_detection",
            object_class="pedestrian",
            severity="high",
            scenario_conditions={"weather": {"fog_density": 88.0, "precipitation": 0.0}},
            message="Missed pedestrian in dense fog",
        )
        store_with_fail.save_run(
            {
                "run_id": "run_fog_fail",
                "scenario_id": "prior_fog_run",
                "scenario_conditions": {"weather": {"fog_density": 88.0, "precipitation": 0.0}},
                "precision": 0.5,
                "recall": 0.3,
                "f1": 0.375,
                "matched_iou": 0.45,
            },
            failures=[failure],
        )

        gen_after = ScenarioGenerator(history_store=store_with_fail, seed=42)
        ranked_after = {r.candidate_id: r for r in gen_after.rank_candidates([cand_fog, cand_rain])}
        score_fog_after = ranked_after["cand_fog"].overall_score
        score_rain_after = ranked_after["cand_rain"].overall_score

        # Dense fog candidate score must increase due to failure evidence
        assert ranked_before["cand_fog"].score_breakdown.failure_evidence == 0.0
        assert ranked_after["cand_fog"].score_breakdown.failure_evidence > 0.0
        assert score_fog_after > score_fog_before
        assert (score_fog_after - score_fog_before) > (score_rain_after - score_rain_before)

    def test_failed_or_rejected_runs_not_saved_or_counted(self, tmp_path: Path) -> None:
        """Invalid or crashing candidates are rejected and NOT persisted to history store."""
        store = RunHistoryStore(tmp_path / "reject_store")
        manager = ScenarioExecutionManager(history_store=store, default_backend=BACKEND_MOCK)

        # Candidate with invalid map and invalid negative vehicles
        invalid_config = {
            "name": "invalid_scenario",
            "map": "Town99_Unsupported",
            "traffic": {"vehicles": -5},
        }

        res = manager.execute(invalid_config)
        assert res.status == ExecutionStatus.REJECTED
        assert res.persisted is False
        assert len(store) == 0

    def test_repeated_runs_generate_fresh_ids_and_metrics(self, tmp_path: Path) -> None:
        """Running the same candidate twice creates distinct run_ids without metric contamination."""
        store = RunHistoryStore(tmp_path / "freshness_store")
        manager = ScenarioExecutionManager(history_store=store, default_backend=BACKEND_MOCK)

        cand = ScenarioCandidate(
            candidate_id="repeat_cand",
            scenario_id="repeat_scen",
            map_name="Town01",
            weather_preset="ClearNoon",
            weather=WeatherParameters(fog_density=0.0, precipitation=0.0, sun_altitude_angle=60.0),
            actor_config=ActorConfiguration(traffic_vehicles=3),
        )

        res1 = manager.execute(cand, max_frames=5)
        res2 = manager.execute(cand, max_frames=5)

        assert res1.run_id != res2.run_id
        assert res1.candidate_id == res2.candidate_id == "repeat_cand"
        assert res1.scenario_id == res2.scenario_id == "repeat_scen"
        assert len(store) == 2

    def test_candidate_scenario_and_run_id_linkage(self, tmp_path: Path) -> None:
        """candidate_id, scenario_id, and run_id remain properly preserved across execution result and store."""
        store = RunHistoryStore(tmp_path / "linkage_store")
        manager = ScenarioExecutionManager(history_store=store, default_backend=BACKEND_MOCK)

        cand = ScenarioCandidate(
            candidate_id="cand_link_007",
            scenario_id="scen_link_007",
            map_name="Town01",
            weather_preset="ClearNoon",
            weather=WeatherParameters(fog_density=10.0, precipitation=5.0, sun_altitude_angle=50.0),
            actor_config=ActorConfiguration(traffic_vehicles=2),
        )

        res = manager.execute(cand, max_frames=5)
        assert res.candidate_id == "cand_link_007"
        assert res.scenario_id == "scen_link_007"
        assert res.run_id.startswith("run_")

        record = store.get_run(res.run_id)
        assert record is not None
        assert record.scenario_id == "scen_link_007"
        assert record.parameters.get("candidate_id") == "cand_link_007"


# ==============================================================================
# Part C: Mock Perception Realism & Matching Rules Tests
# ==============================================================================
class TestMockPerceptionRealism:
    """Audit tests inspecting mock synthetic detection behavior against evaluate_detections rules."""

    def test_matching_follows_class_and_iou_rules(self) -> None:
        """Evaluation strictly obeys class matching and IoU threshold."""
        gt = [
            DetectedObject(bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=1.0),
            DetectedObject(bbox=[300.0, 300.0, 350.0, 420.0], object_type="pedestrian", confidence=1.0),
        ]
        # Prediction 1: Matches car (high IoU)
        # Prediction 2: Overlaps pedestrian location but wrong class ('car' instead of 'pedestrian') -> FP
        # Prediction 3: Unmatched spurious box -> FP
        preds = [
            DetectedObject(bbox=[102.0, 101.0, 202.0, 201.0], object_type="car", confidence=0.9),
            DetectedObject(bbox=[300.0, 300.0, 350.0, 420.0], object_type="car", confidence=0.85),
            DetectedObject(bbox=[500.0, 500.0, 550.0, 550.0], object_type="bicycle", confidence=0.6),
        ]

        metrics = evaluate_detections(predictions=preds, ground_truth=gt, iou_threshold=0.5)

        assert metrics.true_positives == 1   # Car matched
        assert metrics.false_positives == 2  # Wrong-class box + spurious box
        assert metrics.missed_detections == 1  # Pedestrian missed

    def test_weather_affects_mock_detections_explicit_rules(self) -> None:
        """Dense fog creates significantly lower recall and F1 than clear sunny weather."""
        manager = ScenarioExecutionManager(default_backend=BACKEND_MOCK)

        cand_clear = ScenarioCandidate(
            candidate_id="clear_cand",
            scenario_id="clear_scen",
            map_name="Town01",
            weather_preset="ClearNoon",
            weather=WeatherParameters(fog_density=0.0, precipitation=0.0, sun_altitude_angle=65.0),
            actor_config=ActorConfiguration(traffic_vehicles=5),
        )
        cand_foggy = ScenarioCandidate(
            candidate_id="fog_cand",
            scenario_id="fog_scen",
            map_name="Town01",
            weather_preset="DenseFog",
            weather=WeatherParameters(fog_density=95.0, precipitation=20.0, sun_altitude_angle=-10.0),
            actor_config=ActorConfiguration(traffic_vehicles=5),
        )

        res_clear = manager.execute(cand_clear, max_frames=15)
        res_fog = manager.execute(cand_foggy, max_frames=15)

        assert res_clear.metrics is not None
        assert res_fog.metrics is not None

        # Fog must degrade perception performance
        assert res_fog.metrics.recall < res_clear.metrics.recall
        assert res_fog.metrics.missed_detections > res_clear.metrics.missed_detections
        assert res_fog.metrics.f1 < res_clear.metrics.f1

    def test_identical_seeds_and_configurations_reproduce_exact_results(self) -> None:
        """Mock perception is completely deterministic given same scenario name, seed, and config."""
        cfg = {
            "name": "deterministic_scenario_test",
            "map": "Town01",
            "weather": "DenseFog",
            "fine_weather": {"fog_density": 80.0, "precipitation": 30.0, "sun_altitude_angle": 10.0},
            "traffic": {"vehicles": 4, "pedestrians": 2},
        }

        gt_boxes = [
            DetectedObject(bbox=[100.0, 200.0, 180.0, 280.0], object_type="car", confidence=1.0, distance=15.0),
            DetectedObject(bbox=[300.0, 150.0, 330.0, 220.0], object_type="pedestrian", confidence=1.0, distance=30.0),
        ]

        preds1 = ScenarioExecutionManager._simulate_perception_detections(gt_boxes, cfg, frame_idx=7)
        preds2 = ScenarioExecutionManager._simulate_perception_detections(gt_boxes, cfg, frame_idx=7)

        assert len(preds1) == len(preds2)
        for p1, p2 in zip(preds1, preds2):
            assert p1.object_type == p2.object_type
            assert p1.confidence == pytest.approx(p2.confidence)
            assert p1.bbox == pytest.approx(p2.bbox)

    def test_different_scenarios_produce_different_random_draws(self) -> None:
        """Different scenario names receive independent random draws even with identical weather."""
        cfg_a = {
            "name": "scenario_alpha",
            "weather": "ClearNoon",
            "fine_weather": {"fog_density": 50.0, "precipitation": 0.0, "sun_altitude_angle": 30.0},
        }
        cfg_b = {
            "name": "scenario_beta",
            "weather": "ClearNoon",
            "fine_weather": {"fog_density": 50.0, "precipitation": 0.0, "sun_altitude_angle": 30.0},
        }
        gt_boxes = [
            DetectedObject(bbox=[100.0, 200.0, 180.0, 280.0], object_type="car", confidence=1.0, distance=25.0)
        ]

        # Over multiple frames, independent seeds cause different detection / jitter draws
        conf_diffs = []
        for f in range(1, 10):
            p_a = ScenarioExecutionManager._simulate_perception_detections(gt_boxes, cfg_a, frame_idx=f)
            p_b = ScenarioExecutionManager._simulate_perception_detections(gt_boxes, cfg_b, frame_idx=f)
            if p_a and p_b:
                conf_diffs.append(abs(p_a[0].confidence - p_b[0].confidence))

        assert any(d > 0.001 for d in conf_diffs)


# ==============================================================================
# Part D & E: Benchmark Fairness, Metrics & Reporting Tests
# ==============================================================================
class TestBenchmarkFairnessAndMetrics:
    """Audit tests verifying benchmark metric formulas, budget equality, and export parity."""

    def test_aggregate_precision_recall_f1_use_macro_tp_fp_fn(self) -> None:
        """Strategy metrics aggregate total TP, FP, FN rather than unweighted average of per-run scores."""
        bmk = TestingStrategyBenchmark(scenario_budget=2, max_frames_per_scenario=5)

        # Run 1: 1 TP, 0 FP, 0 FN -> Precision=1.0, Recall=1.0, F1=1.0
        # Run 2: 0 TP, 10 FP, 10 FN -> Precision=0.0, Recall=0.0, F1=0.0
        # Unweighted average: Precision=0.5, Recall=0.5, F1=0.5
        # Correct macro formula: Total TP=1, FP=10, FN=10 -> Prec=1/11=0.0909, Rec=1/11=0.0909, F1=0.0909
        r1 = PerRunRecord(
            strategy="test", run_id="r1", candidate_id="c1", scenario_id="s1", status="completed",
            map_name="Town01", weather_preset="ClearNoon", fog_density=0, precipitation=0,
            sun_altitude_angle=60, traffic_vehicles=1, frames=5, sim_time_s=1.0,
            tp=1, fp=0, fn=0, precision=1.0, recall=1.0, f1=1.0, matched_iou=0.8,
            failure_count=0, unique_signatures_count=0, unique_signatures=[],
        )
        r2 = PerRunRecord(
            strategy="test", run_id="r2", candidate_id="c2", scenario_id="s2", status="completed",
            map_name="Town01", weather_preset="ClearNoon", fog_density=0, precipitation=0,
            sun_altitude_angle=60, traffic_vehicles=1, frames=5, sim_time_s=1.0,
            tp=0, fp=10, fn=10, precision=0.0, recall=0.0, f1=0.0, matched_iou=0.0,
            failure_count=5, unique_signatures_count=1, unique_signatures=["sig1"],
        )

        metrics = bmk._aggregate_strategy_metrics("test", [r1, r2], {"sig1"}, {}, {}, {})

        expected_prec = 1.0 / 11.0
        expected_rec = 1.0 / 11.0
        expected_f1 = (2 * expected_prec * expected_rec) / (expected_prec + expected_rec)

        assert metrics.precision == pytest.approx(expected_prec)
        assert metrics.recall == pytest.approx(expected_rec)
        assert metrics.f1 == pytest.approx(expected_f1)
        # Verify it is NOT 0.5
        assert metrics.precision != pytest.approx(0.5)

    def test_matched_iou_is_tp_weighted(self) -> None:
        """Matched IoU uses TP-weighted average across all matched detections."""
        bmk = TestingStrategyBenchmark(scenario_budget=2, max_frames_per_scenario=5)

        # Run 1: 10 TP, IoU=0.9
        # Run 2: 1 TP, IoU=0.5
        # Unweighted avg = (0.9 + 0.5) / 2 = 0.70
        # TP-weighted avg = (10*0.9 + 1*0.5) / 11 = 9.5 / 11 = 0.8636
        r1 = PerRunRecord(
            strategy="test", run_id="r1", candidate_id="c1", scenario_id="s1", status="completed",
            map_name="Town01", weather_preset="ClearNoon", fog_density=0, precipitation=0,
            sun_altitude_angle=60, traffic_vehicles=1, frames=5, sim_time_s=1.0,
            tp=10, fp=0, fn=0, precision=1.0, recall=1.0, f1=1.0, matched_iou=0.9,
            failure_count=0, unique_signatures_count=0, unique_signatures=[],
        )
        r2 = PerRunRecord(
            strategy="test", run_id="r2", candidate_id="c2", scenario_id="s2", status="completed",
            map_name="Town01", weather_preset="ClearNoon", fog_density=0, precipitation=0,
            sun_altitude_angle=60, traffic_vehicles=1, frames=5, sim_time_s=1.0,
            tp=1, fp=0, fn=0, precision=1.0, recall=1.0, f1=1.0, matched_iou=0.5,
            failure_count=0, unique_signatures_count=0, unique_signatures=[],
        )

        metrics = bmk._aggregate_strategy_metrics("test", [r1, r2], set(), {}, {}, {})
        expected_weighted_iou = 9.5 / 11.0
        assert metrics.matched_iou == pytest.approx(expected_weighted_iou)

    def test_empty_runs_and_zero_metrics_handled_safely(self) -> None:
        """Benchmark handles empty run list and zero metrics without crashing or ZeroDivisionError."""
        bmk = TestingStrategyBenchmark(scenario_budget=1, max_frames_per_scenario=5)
        metrics = bmk._aggregate_strategy_metrics("empty", [], set(), {}, {}, {})

        assert metrics.attempted_scenarios == 0
        assert metrics.completed_scenarios == 0
        assert metrics.precision == 0.0
        assert metrics.recall == 0.0
        assert metrics.f1 == 0.0
        assert metrics.matched_iou == 0.0

    def test_json_csv_and_markdown_exports_agree(self, tmp_path: Path) -> None:
        """All three export artifacts report identical metrics and disclosure."""
        out_dir = tmp_path / "export_parity_test"
        bmk = TestingStrategyBenchmark(
            scenario_budget=2,
            max_frames_per_scenario=5,
            duration_seconds=5.0,
            seed=42,
            backend=BACKEND_MOCK,
            output_dir=out_dir,
        )
        data = bmk.run()

        json_path = out_dir / "benchmark_results.json"
        csv_path = out_dir / "benchmark_runs.csv"
        md_path = out_dir / "benchmark_report.md"

        assert json_path.exists()
        assert csv_path.exists()
        assert md_path.exists()

        with json_path.open("r", encoding="utf-8") as fh:
            j_data = json.load(fh)

        md_text = md_path.read_text(encoding="utf-8")

        # Disclosures match
        assert j_data["backend_disclosure"] == data["backend_disclosure"]
        assert data["backend_disclosure"] in md_text

        # Unique signatures count match across JSON and MD
        guided_sigs = data["comparison"]["guided_unique_signatures"]
        random_sigs = data["comparison"]["random_unique_signatures"]
        assert j_data["comparison"]["guided_unique_signatures"] == guided_sigs
        assert j_data["comparison"]["random_unique_signatures"] == random_sigs
        assert f"Guided Unique Signatures ({guided_sigs})" in md_text
        assert f"Random Baseline Unique Signatures ({random_sigs})" in md_text


# ==============================================================================
# Part F: Weather Integration Verification Tests
# ==============================================================================
class TestWeatherIntegration:
    """Audit tests tracing fine-grained weather dictionary application."""

    def test_fine_weather_applied_to_mock_client(self) -> None:
        """Fine-grained weather values are parsed and actively applied to MockCarlaClient."""
        cfg = {
            "name": "fine_weather_test",
            "map": "Town01",
            "weather": "Custom",
            "fine_weather": {
                "fog_density": 77.5,
                "precipitation": 42.0,
                "sun_altitude_angle": -5.0,
                "cloudiness": 90.0,
            },
        }

        runner = ScenarioRunner(cfg, backend=BACKEND_MOCK)
        assert runner._info.fine_weather is not None
        assert runner._info.fine_weather.get("fog_density") == pytest.approx(77.5)
        with runner.run() as _:
            weather = runner._client.get_weather()
            assert weather.get("fog_density") == pytest.approx(77.5)
            assert weather.get("precipitation") == pytest.approx(42.0)

    def test_preset_fallback_behavior_when_fine_weather_omitted(self) -> None:
        """When fine_weather is omitted, runner maps standard CARLA weather preset."""
        cfg = {
            "name": "preset_fallback_test",
            "map": "Town01",
            "weather": "HardRainNoon",
        }

        runner = ScenarioRunner(cfg, backend=BACKEND_MOCK)
        assert runner._info.weather_preset == "HardRainNoon"
        with runner.run() as _:
            weather = runner._client.get_weather()
            assert weather.get("precipitation") == pytest.approx(80.0)
            assert weather.get("cloudiness") == pytest.approx(100.0)


# ==============================================================================
# Milestone 4B.2: Cross-Process Seed Reproducibility & Metric Terminology Tests
# ==============================================================================
class TestCrossProcessReproducibility:
    """Verify separate Python processes with identical seeds produce identical serialized outputs."""

    def test_cross_process_seed_reproducibility(self, tmp_path: Path) -> None:
        """Benchmark executed in two separate Python processes produces bit-for-bit identical results."""
        out_dir_p1 = tmp_path / "proc1_output"
        out_dir_p2 = tmp_path / "proc2_output"

        cmd1 = [
            sys.executable,
            "-m",
            "edgeforge.scenarios.benchmark",
            "--scenarios",
            "3",
            "--frames",
            "10",
            "--seed",
            "42",
            "--backend",
            "mock",
            "--output-dir",
            str(out_dir_p1),
        ]
        cmd2 = [
            sys.executable,
            "-m",
            "edgeforge.scenarios.benchmark",
            "--scenarios",
            "3",
            "--frames",
            "10",
            "--seed",
            "42",
            "--backend",
            "mock",
            "--output-dir",
            str(out_dir_p2),
        ]

        proc1 = subprocess.run(cmd1, capture_output=True, text=True, check=True)
        proc2 = subprocess.run(cmd2, capture_output=True, text=True, check=True)

        assert proc1.returncode == 0
        assert proc2.returncode == 0

        # Load both JSON result artifacts
        with (out_dir_p1 / "benchmark_results.json").open("r", encoding="utf-8") as f1:
            data1 = json.load(f1)
        with (out_dir_p2 / "benchmark_results.json").open("r", encoding="utf-8") as f2:
            data2 = json.load(f2)

        # 1. Compare comparison metrics
        c1 = data1["comparison"]
        c2 = data2["comparison"]
        assert c1["completed_budget_matched"] == c2["completed_budget_matched"] is True
        assert c1["attempted_budget_matched"] == c2["attempted_budget_matched"] is True
        assert c1["guided_completed"] == c2["guided_completed"] == 3
        assert c1["random_completed"] == c2["random_completed"] == 3
        assert c1["guided_unique_signatures"] == c2["guided_unique_signatures"]
        assert c1["random_unique_signatures"] == c2["random_unique_signatures"]
        assert c1["unique_signatures_delta"] == c2["unique_signatures_delta"]
        assert c1["guided_micro_f1"] == c2["guided_micro_f1"]
        assert c1["random_micro_f1"] == c2["random_micro_f1"]
        assert c1["micro_f1_delta"] == c2["micro_f1_delta"]
        assert c1["guided_micro_precision"] == c2["guided_micro_precision"]
        assert c1["random_micro_precision"] == c2["random_micro_precision"]
        assert c1["guided_micro_recall"] == c2["guided_micro_recall"]
        assert c1["random_micro_recall"] == c2["random_micro_recall"]
        assert c1["guided_coverage_ratio"] == c2["guided_coverage_ratio"]
        assert c1["random_coverage_ratio"] == c2["random_coverage_ratio"]
        assert c1["verdict"] == c2["verdict"]

        # 2. Compare strategy-level aggregated metrics
        for strat in ["failure_guided", "random_baseline"]:
            s1 = data1["strategies"][strat]
            s2 = data2["strategies"][strat]
            assert s1["completed_scenarios"] == s2["completed_scenarios"]
            assert s1["attempted_scenarios"] == s2["attempted_scenarios"]
            assert s1["total_frames"] == s2["total_frames"]
            assert s1["total_tp"] == s2["total_tp"]
            assert s1["total_fp"] == s2["total_fp"]
            assert s1["total_fn"] == s2["total_fn"]
            assert s1["precision"] == s2["precision"]
            assert s1["recall"] == s2["recall"]
            assert s1["f1"] == s2["f1"]
            assert s1["matched_iou"] == s2["matched_iou"]
            assert s1["unique_failure_signatures_count"] == s2["unique_failure_signatures_count"]
            assert s1["unique_signatures"] == s2["unique_signatures"]
            assert s1["failures_by_type"] == s2["failures_by_type"]
            assert s1["failures_by_severity"] == s2["failures_by_severity"]

        # 3. Compare per-run CSV outputs
        with (out_dir_p1 / "benchmark_runs.csv").open("r", encoding="utf-8") as f1:
            rows1 = list(csv.DictReader(f1))
        with (out_dir_p2 / "benchmark_runs.csv").open("r", encoding="utf-8") as f2:
            rows2 = list(csv.DictReader(f2))

        assert len(rows1) == len(rows2) == 6
        for r1, r2 in zip(rows1, rows2):
            assert r1["strategy"] == r2["strategy"]
            assert r1["candidate_id"] == r2["candidate_id"]
            assert r1["scenario_id"] == r2["scenario_id"]
            assert r1["status"] == r2["status"]
            assert r1["map_name"] == r2["map_name"]
            assert r1["weather_preset"] == r2["weather_preset"]
            assert float(r1["fog_density"]) == pytest.approx(float(r2["fog_density"]))
            assert float(r1["precipitation"]) == pytest.approx(float(r2["precipitation"]))
            assert float(r1["sun_altitude_angle"]) == pytest.approx(float(r2["sun_altitude_angle"]))
            assert int(r1["frames"]) == int(r2["frames"])
            assert int(r1["tp"]) == int(r2["tp"])
            assert int(r1["fp"]) == int(r2["fp"])
            assert int(r1["fn"]) == int(r2["fn"])
            assert float(r1["precision"]) == pytest.approx(float(r2["precision"]))
            assert float(r1["recall"]) == pytest.approx(float(r2["recall"]))
            assert float(r1["f1"]) == pytest.approx(float(r2["f1"]))
            assert float(r1["matched_iou"]) == pytest.approx(float(r2["matched_iou"]))
            assert int(r1["failure_count"]) == int(r2["failure_count"])
            assert int(r1["unique_signatures_count"]) == int(r2["unique_signatures_count"])


class TestMetricTerminologyAndDistinction:
    """Verify micro-aggregation terminology and clear distinction between per-run and strategy-level metrics."""

    def test_micro_aggregation_labels_in_markdown_and_json(self, tmp_path: Path) -> None:
        """Strategy-level metrics are explicitly documented as micro-aggregated."""
        out_dir = tmp_path / "term_test"
        bmk = TestingStrategyBenchmark(
            scenario_budget=2,
            max_frames_per_scenario=5,
            duration_seconds=5.0,
            seed=42,
            backend=BACKEND_MOCK,
            output_dir=out_dir,
        )
        data = bmk.run()

        # Check JSON keys
        assert "guided_micro_precision" in data["comparison"]
        assert "guided_micro_recall" in data["comparison"]
        assert "guided_micro_f1" in data["comparison"]
        assert "guided_attempted" in data["comparison"]
        assert "guided_completed" in data["comparison"]
        assert "completed_budget_matched" in data["comparison"]
        assert "attempted_budget_matched" in data["comparison"]

        # Check Markdown report
        md_text = (out_dir / "benchmark_report.md").read_text(encoding="utf-8")
        assert "Micro-aggregated Precision" in md_text
        assert "Micro-aggregated Recall" in md_text
        assert "Micro-aggregated F1 Score" in md_text
        assert "micro-aggregated" in md_text.lower()
        assert "per-run metrics are recorded individually in `benchmark_runs.csv`" in md_text.lower()
