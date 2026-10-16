"""Tests for Testing Strategy Benchmark, Failure Signatures, and Reporting.

Verifies:
- Reproducible random scenario generation with seed.
- Exact parameter bounds equivalence between guided and random strategies.
- Equal scenario and frame budgets in benchmark planning and execution.
- Temporal isolation: guided strategy uses only history accumulated up to that step.
- Unique failure-signature extraction, deduplication across repeated frames, and environmental binning.
- JSON and CSV benchmark export and reload integrity.
- Clear disclosure of simulation backend (mock vs CARLA).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from edgeforge.data.history import RunHistoryStore
from edgeforge.data.models import PerceptionFailureRecord
from edgeforge.scenarios.benchmark import (
    TestingStrategyBenchmark,
    compute_failure_signature,
)
from edgeforge.scenarios.generator import (
    DEFAULT_DOMAIN_BOUNDS,
    SUPPORTED_MAPS,
    RandomScenarioGenerator,
    ScenarioCandidate,
    ScenarioGenerator,
)
from edgeforge.simulation.scenario_runner import BACKEND_MOCK


# ---------------------------------------------------------------------------
# Part C: Fair Random Baseline & Budget Allocation Tests
# ---------------------------------------------------------------------------
class TestRandomBaselineAndBudgets:
    """Verify reproducible random baseline and budget fairness."""

    def test_reproducible_random_generation_with_seed(self) -> None:
        """Two RandomScenarioGenerator instances with same seed produce identical scenarios."""
        gen1 = RandomScenarioGenerator(seed=1234)
        cands1 = gen1.generate_candidates(count=5)

        gen2 = RandomScenarioGenerator(seed=1234)
        cands2 = gen2.generate_candidates(count=5)

        assert len(cands1) == 5
        assert len(cands2) == 5

        for c1, c2 in zip(cands1, cands2):
            assert c1.map_name == c2.map_name
            assert c1.weather_preset == c2.weather_preset
            assert c1.weather.fog_density == pytest.approx(c2.weather.fog_density)
            assert c1.weather.precipitation == pytest.approx(c2.weather.precipitation)
            assert c1.weather.sun_altitude_angle == pytest.approx(c2.weather.sun_altitude_angle)
            assert c1.actor_config.traffic_vehicles == c2.actor_config.traffic_vehicles
            assert c1.actor_config.target_count == c2.actor_config.target_count

    def test_different_seeds_produce_different_candidates(self) -> None:
        """Different seeds produce distinct scenario configurations."""
        gen1 = RandomScenarioGenerator(seed=101)
        gen2 = RandomScenarioGenerator(seed=202)

        cands1 = gen1.generate_candidates(count=3)
        cands2 = gen2.generate_candidates(count=3)

        assert any(
            c1.weather.fog_density != c2.weather.fog_density
            or c1.weather.sun_altitude_angle != c2.weather.sun_altitude_angle
            or c1.map_name != c2.map_name
            for c1, c2 in zip(cands1, cands2)
        )

    def test_random_candidates_stay_within_supported_bounds(self) -> None:
        """All sampled random candidates strictly conform to documented parameter bounds and maps."""
        gen = RandomScenarioGenerator(seed=42)
        candidates = gen.generate_candidates(count=20)

        for c in candidates:
            assert c.map_name in SUPPORTED_MAPS
            assert 0.0 <= c.weather.fog_density <= 100.0
            assert 0.0 <= c.weather.precipitation <= 100.0
            assert 0.0 <= c.weather.cloudiness <= 100.0
            assert -15.0 <= c.weather.sun_altitude_angle <= 85.0
            assert 0.0 <= c.weather.sun_azimuth_angle <= 360.0
            assert 1 <= c.actor_config.target_count <= 5
            assert c.actor_config.traffic_vehicles >= 0
            assert c.actor_config.ego_spawn_index >= 0
            assert len(c.unsupported_features) == 0

    def test_equal_budget_in_benchmark_planning(self) -> None:
        """Benchmark dry-run verifies equal scenario and frame allocations for both strategies."""
        benchmark = TestingStrategyBenchmark(
            scenario_budget=4,
            max_frames_per_scenario=25,
            duration_seconds=10.0,
            seed=777,
            backend=BACKEND_MOCK,
        )

        plan = benchmark.run_dry_run()

        assert plan["all_valid"] is True
        assert len(plan["guided_planned_scenarios"]) == 4
        assert len(plan["random_planned_scenarios"]) == 4
        assert plan["scenario_budget"] == 4
        assert plan["max_frames_per_scenario"] == 25


# ---------------------------------------------------------------------------
# Part C: Temporal Isolation Tests (No Future Data Leakage)
# ---------------------------------------------------------------------------
class TestTemporalHistoryIsolation:
    """Verify guided exploration uses history strictly step-by-step without data leakage."""

    def test_guided_strategy_uses_history_strictly_after_availability(self, tmp_path: Path) -> None:
        """At step t, generator only has access to runs 0..t-1."""
        store_dir = tmp_path / "guided_isolation_store"
        store = RunHistoryStore(store_dir)

        # Initially store has 0 runs
        assert len(store) == 0

        # Step 0: Guided generator sees empty store
        gen_step0 = ScenarioGenerator(history_store=store, seed=10)
        cands0 = gen_step0.generate_candidates(num_candidates=5)
        ranked0 = gen_step0.rank_candidates(cands0)
        assert all(r.cold_start for r in ranked0)  # Cold-start because no history exists yet

        # Execute step 0 and save to store
        from edgeforge.scenarios.executor import ScenarioExecutionManager
        manager = ScenarioExecutionManager(history_store=store, default_backend=BACKEND_MOCK)
        res0 = manager.execute(ranked0[0], max_frames=5)
        assert res0.status.value == "completed"
        assert len(store) == 1

        # Step 1: Generator now sees exactly 1 run in history
        gen_step1 = ScenarioGenerator(history_store=store, seed=11)
        cands1 = gen_step1.generate_candidates(num_candidates=5)
        ranked1 = gen_step1.rank_candidates(cands1)

        # Step 1 recommendations now have access to prior run evidence
        assert len(store) == 1
        assert not all(r.cold_start for r in ranked1)


# ---------------------------------------------------------------------------
# Part D: Unique Failure Signature Definition & Deduplication Tests
# ---------------------------------------------------------------------------
class TestUniqueFailureSignatures:
    """Verify failure signature extraction, repeated-frame deduplication, and environmental binning."""

    def test_repeated_frame_failures_in_same_condition_deduplicated_to_single_signature(self) -> None:
        """20 frame failures of missed pedestrian in dense fog night produce exactly 1 unique signature."""
        scenario_conditions = {
            "weather": {
                "fog_density": 80.0,
                "precipitation": 0.0,
                "sun_altitude_angle": -10.0,
            }
        }

        # Simulate 20 frame failures of the same type and object class
        failures = [
            PerceptionFailureRecord(
                failure_type="missed_detection",
                object_class="pedestrian",
                severity="high",
                frame_number=i,
                message=f"Missed pedestrian at frame {i}",
            )
            for i in range(1, 21)
        ]

        signatures = [compute_failure_signature(f, scenario_conditions) for f in failures]
        unique_sigs = set(signatures)

        # Crucial requirement: Do NOT treat every repeated failure frame as a new unique failure
        assert len(unique_sigs) == 1
        assert "missed_detection:pedestrian:high:fog_dense_dry_night" in unique_sigs

    def test_distinct_environmental_bins_produce_distinct_signatures(self) -> None:
        """Same failure type and class under different weather bins produce distinct signatures."""
        failure = PerceptionFailureRecord(
            failure_type="missed_detection",
            object_class="car",
            severity="high",
            frame_number=1,
        )

        cond_fog_night = {
            "weather": {"fog_density": 75.0, "precipitation": 0.0, "sun_altitude_angle": -5.0}
        }
        cond_rain_day = {
            "weather": {"fog_density": 5.0, "precipitation": 60.0, "sun_altitude_angle": 50.0}
        }
        cond_clear_day = {
            "weather": {"fog_density": 0.0, "precipitation": 0.0, "sun_altitude_angle": 60.0}
        }

        sig1 = compute_failure_signature(failure, cond_fog_night)
        sig2 = compute_failure_signature(failure, cond_rain_day)
        sig3 = compute_failure_signature(failure, cond_clear_day)

        assert sig1 != sig2
        assert sig2 != sig3
        assert sig1 != sig3
        assert "fog_dense_dry_night" in sig1
        assert "fog_clear_heavy_rain_day" in sig2
        assert "fog_clear_dry_day" in sig3


# ---------------------------------------------------------------------------
# Part E: Benchmark Execution & JSON/CSV Export & Reload Tests
# ---------------------------------------------------------------------------
class TestBenchmarkExecutionAndExports:
    """Verify benchmark run, structured JSON and CSV generation, and reloading integrity."""

    def test_benchmark_run_exports_valid_json_and_csv(self, tmp_path: Path) -> None:
        """Full benchmark executes under mock backend and exports complete JSON, CSV, and MD reports."""
        out_dir = tmp_path / "benchmark_run_test"
        benchmark = TestingStrategyBenchmark(
            scenario_budget=3,
            max_frames_per_scenario=10,
            duration_seconds=5.0,
            seed=42,
            backend=BACKEND_MOCK,
            output_dir=out_dir,
        )

        results = benchmark.run()

        # Check in-memory result structure
        assert "benchmark_id" in results
        assert results["backend"] == BACKEND_MOCK
        assert "mock" in results["backend_disclosure"].lower()
        assert "comparison" in results
        assert "strategies" in results

        guided = results["strategies"]["failure_guided"]
        random_base = results["strategies"]["random_baseline"]

        assert guided["completed_scenarios"] == 3
        assert random_base["completed_scenarios"] == 3
        assert guided["total_frames"] == 30
        assert random_base["total_frames"] == 30

        # Check JSON file existence and reload
        json_file = out_dir / "benchmark_results.json"
        assert json_file.exists()
        with json_file.open("r", encoding="utf-8") as fh:
            reloaded_json = json.load(fh)

        assert reloaded_json["benchmark_id"] == results["benchmark_id"]
        assert reloaded_json["comparison"]["guided_unique_signatures"] == guided["unique_failure_signatures_count"]
        assert reloaded_json["comparison"]["random_unique_signatures"] == random_base["unique_failure_signatures_count"]

        # Check CSV file existence and reload
        csv_file = out_dir / "benchmark_runs.csv"
        assert csv_file.exists()
        with csv_file.open("r", encoding="utf-8") as fh:
            reader = list(csv.DictReader(fh))

        assert len(reader) == 6  # 3 guided runs + 3 random runs
        strategies_in_csv = {row["strategy"] for row in reader}
        assert strategies_in_csv == {"failure_guided", "random_baseline"}

        for row in reader:
            assert row["status"] == "completed"
            assert int(row["frames"]) == 10
            assert row["run_id"].startswith("run_")

        # Check Markdown report existence
        md_file = out_dir / "benchmark_report.md"
        assert md_file.exists()
        md_text = md_file.read_text(encoding="utf-8")
        assert "EDGEFORGE — Testing Strategy Benchmark Report" in md_text
        assert "Unique Failure Signatures" in md_text
        assert "Mock synthetic simulation" in md_text
