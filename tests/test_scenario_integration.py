"""Tests for Scenario Integration, Runner Compatibility, and Safe Execution Manager.

Verifies:
- Generated scenario configurations are parsed by ScenarioRunner.
- Fine-grained weather parameters and presets are preserved.
- Dry-run validation works offline without CARLA connection.
- Rejection of invalid configurations and unsupported parameters.
- Run IDs and candidate IDs are correctly linked.
- Failed executions are not counted as completed tests or saved to history.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from edgeforge.data.history import RunHistoryStore
from edgeforge.scenarios.executor import (
    ExecutionResult,
    ExecutionStatus,
    ScenarioExecutionManager,
    validate_scenario_config,
)
from edgeforge.scenarios.generator import (
    ActorConfiguration,
    ScenarioCandidate,
    WeatherParameters,
)
from edgeforge.simulation.mock_client import MockCarlaClient
from edgeforge.simulation.scenario_runner import BACKEND_CARLA, BACKEND_MOCK, ScenarioInfo, ScenarioRunner


# ---------------------------------------------------------------------------
# Part A: Scenario Compatibility & Runner Configuration Parsing Tests
# ---------------------------------------------------------------------------
class TestScenarioCompatibility:
    """Verify generated scenario configurations parse cleanly in ScenarioRunner."""

    def test_generated_candidate_to_runner_config_parsed_by_scenario_runner(self) -> None:
        """ScenarioCandidate produces a config that ScenarioRunner initializes without error."""
        weather = WeatherParameters(
            cloudiness=75.0,
            precipitation=40.0,
            fog_density=55.0,
            wetness=60.0,
            sun_altitude_angle=18.0,
            sun_azimuth_angle=120.0,
        )
        actors = ActorConfiguration(
            target_count=3,
            ego_spawn_index=2,
            target_types=["car", "pedestrian"],
            traffic_vehicles=4,
            traffic_pedestrians=2,
            traffic_bicycles=1,
        )
        candidate = ScenarioCandidate(
            candidate_id="cand_test_001",
            scenario_id="scenario_test_001",
            map_name="Town02",
            weather=weather,
            actor_config=actors,
            weather_preset="MidRainSunset",
            fixed_delta_seconds=0.05,
        )

        cfg = candidate.to_runner_config(duration_seconds=20.0)

        # Initialize ScenarioRunner in mock backend
        runner = ScenarioRunner(cfg, backend=BACKEND_MOCK)

        assert runner.info.name == "scenario_test_001"
        assert runner.info.map_name == "Town02"
        assert runner.info.duration_seconds == 20.0
        assert runner.info.weather_preset == "MidRainSunset"
        assert runner.backend == BACKEND_MOCK

        # Fine-grained weather is preserved
        assert runner.info.fine_weather is not None
        assert runner.info.fine_weather["fog_density"] == pytest.approx(55.0)
        assert runner.info.fine_weather["precipitation"] == pytest.approx(40.0)
        assert runner.info.fine_weather["cloudiness"] == pytest.approx(75.0)
        assert runner.info.fine_weather["sun_altitude_angle"] == pytest.approx(18.0)
        assert runner.info.fine_weather["sun_azimuth_angle"] == pytest.approx(120.0)

    def test_fine_grained_weather_applied_to_client_on_start(self) -> None:
        """Starting a scenario actually applies fine-grained weather parameters to the client."""
        cfg = {
            "name": "weather_apply_test",
            "map": "Town01",
            "duration_seconds": 5.0,
            "weather": "ClearNoon",
            "fine_weather": {
                "fog_density": 85.0,
                "precipitation": 70.0,
                "cloudiness": 90.0,
                "sun_altitude_angle": -5.0,
            },
            "traffic": {"vehicles": 1},
            "ego_vehicle": {"model": "vehicle.tesla.model3", "spawn_point_index": 0},
            "sensors": {
                "rgb_camera": {"enabled": True, "width": 320, "height": 240, "tick": 0.05}
            },
        }

        mock_client = MockCarlaClient()
        runner = ScenarioRunner(cfg, backend=BACKEND_MOCK, client=mock_client)

        runner.start()
        try:
            applied = mock_client.get_weather()
            assert applied["fog_density"] == pytest.approx(85.0)
            assert applied["precipitation"] == pytest.approx(70.0)
            assert applied["cloudiness"] == pytest.approx(90.0)
            assert applied["sun_altitude_angle"] == pytest.approx(-5.0)
        finally:
            runner.stop()

    def test_weather_dict_in_root_parsed_without_crashing(self) -> None:
        """If a config supplies weather as a dict, it does not turn into an invalid preset string."""
        cfg = {
            "name": "dict_weather_test",
            "map": "Town03",
            "weather": {
                "preset": "CloudyNoon",
                "fog_density": 30.0,
                "precipitation": 10.0,
            },
            "traffic": {"vehicles": 0},
            "ego_vehicle": {"spawn_point_index": 0},
            "sensors": {"rgb_camera": {"enabled": True, "width": 320, "height": 240}},
        }
        runner = ScenarioRunner(cfg, backend=BACKEND_MOCK)
        assert runner.info.weather_preset == "CloudyNoon"
        assert runner.info.fine_weather["fog_density"] == pytest.approx(30.0)


# ---------------------------------------------------------------------------
# Part B: Safe Execution & Dry-Run Validation Tests
# ---------------------------------------------------------------------------
class TestSafeScenarioExecution:
    """Verify dry-run mode, validation bounds, error rejection, and history linkage."""

    def test_dry_run_validation_passes_without_simulator(self) -> None:
        """Dry-run validates candidate without launching CARLA or ticking mock client."""
        candidate = ScenarioCandidate(
            candidate_id="cand_dry_01",
            scenario_id="scenario_dry_01",
            map_name="Town01",
            weather=WeatherParameters(fog_density=40.0, precipitation=20.0),
            actor_config=ActorConfiguration(target_count=2, traffic_vehicles=3),
        )

        manager = ScenarioExecutionManager(default_backend=BACKEND_MOCK)
        result = manager.dry_run(candidate)

        assert result.status == ExecutionStatus.VALIDATED
        assert result.candidate_id == "cand_dry_01"
        assert result.scenario_id == "scenario_dry_01"
        assert result.backend == "dry_run"
        assert len(result.validation_errors) == 0
        assert result.dry_run_summary is not None
        assert "DRY-RUN SCENARIO PLAN" in result.dry_run_summary
        assert "Town01" in result.dry_run_summary
        assert result.metrics is None  # no metrics produced during dry-run

    def test_dry_run_rejects_unsupported_map(self) -> None:
        """Configs with unsupported maps are rejected with explicit message."""
        raw_cfg = {
            "name": "unsupported_map_scen",
            "map": "Town99_Invalid",
            "weather": "ClearNoon",
            "traffic": {"vehicles": 1},
            "ego_vehicle": {"spawn_point_index": 0},
            "sensors": {"rgb_camera": {"enabled": True, "width": 640, "height": 480}},
        }

        manager = ScenarioExecutionManager()
        result = manager.dry_run(raw_cfg)

        assert result.status == ExecutionStatus.REJECTED
        assert any("supported maps" in err.lower() for err in result.validation_errors)

    def test_dry_run_rejects_out_of_bounds_weather_parameters(self) -> None:
        """Weather values outside physically valid/supported ranges are rejected."""
        raw_cfg = {
            "name": "bad_fog_scen",
            "map": "Town01",
            "weather": "ClearNoon",
            "fine_weather": {
                "fog_density": 150.0,  # invalid: > 100
                "cloudiness": -10.0,   # invalid: < 0
            },
            "traffic": {"vehicles": 1},
            "ego_vehicle": {"spawn_point_index": 0},
            "sensors": {"rgb_camera": {"enabled": True, "width": 640, "height": 480}},
        }

        manager = ScenarioExecutionManager()
        result = manager.dry_run(raw_cfg)

        assert result.status == ExecutionStatus.REJECTED
        assert any("fog_density" in err for err in result.validation_errors)
        assert any("cloudiness" in err for err in result.validation_errors)

    def test_dry_run_rejects_unsupported_features(self) -> None:
        """Known unsupported features (e.g. adversarial cut-in) cannot silently appear active."""
        raw_cfg = {
            "name": "adversarial_scen",
            "map": "Town01",
            "weather": "ClearNoon",
            "traffic": {"vehicles": 2},
            "ego_vehicle": {"spawn_point_index": 0},
            "sensors": {"rgb_camera": {"enabled": True, "width": 640, "height": 480}},
            "adversarial_cut_in": True,  # unsupported feature
            "generated_metadata": {
                "unsupported_features": ["adversarial_cut_in"],
            },
        }

        manager = ScenarioExecutionManager()
        result = manager.dry_run(raw_cfg)

        assert result.status == ExecutionStatus.REJECTED
        assert any("unsupported" in err.lower() for err in result.validation_errors)

    def test_successful_mock_execution_links_ids_and_persists_to_history(self, tmp_path: Path) -> None:
        """Completed run produces valid metrics, links run_id/candidate_id, and saves to store."""
        store = RunHistoryStore(tmp_path / "test_store")
        manager = ScenarioExecutionManager(history_store=store, default_backend=BACKEND_MOCK)

        candidate = ScenarioCandidate(
            candidate_id="cand_exec_001",
            scenario_id="scenario_exec_001",
            map_name="Town01",
            weather=WeatherParameters(fog_density=30.0, precipitation=10.0),
            actor_config=ActorConfiguration(target_count=2, traffic_vehicles=2),
        )

        result = manager.execute(candidate, max_frames=10)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.is_successful is True
        assert result.candidate_id == "cand_exec_001"
        assert result.scenario_id == "scenario_exec_001"
        assert result.run_id.startswith("run_")
        assert result.sim_frames == 10
        assert result.metrics is not None
        assert result.persisted is True

        # Check history store persistence
        assert len(store) == 1
        record = store.get_run(result.run_id)
        assert record is not None
        assert record.scenario_id == "scenario_exec_001"
        assert record.parameters.get("candidate_id") == "cand_exec_001"
        assert record.frames_processed == 10

    def test_failed_execution_not_marked_successful_or_persisted(self, tmp_path: Path, monkeypatch: Any) -> None:
        """When an execution crashes, it is marked FAILED, not completed, and NOT saved to history."""
        store = RunHistoryStore(tmp_path / "test_store_fail")
        manager = ScenarioExecutionManager(history_store=store, default_backend=BACKEND_MOCK)

        candidate = ScenarioCandidate(
            candidate_id="cand_fail_001",
            scenario_id="scenario_fail_001",
            map_name="Town01",
        )

        # Force an unexpected simulation failure
        def mock_broken_run(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Simulated CARLA disconnect or crash")

        monkeypatch.setattr(ScenarioRunner, "start", mock_broken_run)

        result = manager.execute(candidate)

        assert result.status == ExecutionStatus.FAILED
        assert result.is_successful is False
        assert "Simulated CARLA disconnect" in (result.error_message or "")
        assert result.persisted is False

        # Must NOT add to history store
        assert len(store) == 0

    def test_carla_execution_safely_fails_when_server_unreachable(self) -> None:
        """Attempting CARLA execution when server is offline returns clear FAILED result without crashing."""
        manager = ScenarioExecutionManager()
        raw_cfg = {
            "name": "live_carla_attempt",
            "map": "Town01",
            "weather": "ClearNoon",
            "traffic": {"vehicles": 1},
            "ego_vehicle": {"spawn_point_index": 0},
            "sensors": {"rgb_camera": {"enabled": True, "width": 640, "height": 480}},
        }

        # Request live CARLA backend
        result = manager.execute(raw_cfg, backend=BACKEND_CARLA)

        assert result.status == ExecutionStatus.FAILED
        assert "CARLA server unreachable" in (result.error_message or "")
        assert result.is_successful is False
