from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch
import pytest

from edgeforge.simulation.carla_client import CarlaClient
from edgeforge.simulation.runner_service import SimulationService
from edgeforge.simulation.scenario_runner import ScenarioRunner
from edgeforge.api import SimulationRuntime


def test_spawn_traffic_import_does_not_connect_to_carla():
    with patch("carla.Client") as client_factory:
        module = importlib.import_module("edgeforge.simulation.spawn_traffic")
        importlib.reload(module)

    client_factory.assert_not_called()


class DummyMap:
    def __init__(self, name: str = "/Game/Carla/Maps/Town10HD_Opt"):
        self.name = name

    def get_spawn_points(self):
        return [MagicMock()]


class DummyWorld:
    def __init__(self, map_name: str = "/Game/Carla/Maps/Town10HD_Opt"):
        self._map = DummyMap(map_name)

    def get_map(self):
        return self._map

    def get_settings(self):
        m = MagicMock()
        m.synchronous_mode = False
        return m

    def apply_settings(self, settings):
        pass


def test_scenario_runner_reuses_active_map_when_map_is_current():
    """ScenarioRunner must not call load_map when map is 'current'."""
    mock_client = MagicMock()
    mock_client.map.name = "/Game/Carla/Maps/Town10HD_Opt"
    mock_client.set_weather = MagicMock()
    mock_client.set_synchronous_mode = MagicMock()
    mock_client.tick = MagicMock()

    cfg = {
        "name": "test_current_map_scenario",
        "map": "current",
        "weather": "ClearNoon",
        "duration_seconds": 1.0,
        "ego_vehicle": {"model": "vehicle.tesla.model3"},
        "traffic": {"vehicles": 0, "pedestrians": 0, "bicycles": 0},
        "sensors": {"rgb_camera": {"enabled": False}},
    }

    runner = ScenarioRunner(cfg, client=mock_client, backend="carla")
    with patch.object(runner._actor_mgr, "spawn_ego", return_value=MagicMock()), \
         patch.object(runner._actor_mgr, "spawn_traffic", return_value=MagicMock()), \
         patch.object(runner._sensor_mgr, "build_suite"):
        runner.start()

    # load_map must NEVER have been called because map was 'current'
    mock_client.load_map.assert_not_called()
    assert runner.info.map_name == "Town10HD_Opt"
    runner.stop()


def test_scenario_runner_reuses_active_map_when_target_matches_server_map():
    """ScenarioRunner skips load_map if target map name matches server map."""
    mock_client = MagicMock()
    mock_client.map.name = "Carla/Maps/Town03"
    mock_client.set_weather = MagicMock()
    mock_client.set_synchronous_mode = MagicMock()
    mock_client.tick = MagicMock()

    cfg = {
        "name": "test_matching_map_scenario",
        "map": "Town03",
        "weather": "ClearNoon",
        "duration_seconds": 1.0,
        "ego_vehicle": {"model": "vehicle.tesla.model3"},
        "traffic": {"vehicles": 0, "pedestrians": 0, "bicycles": 0},
        "sensors": {"rgb_camera": {"enabled": False}},
    }

    runner = ScenarioRunner(cfg, client=mock_client, backend="carla")
    with patch.object(runner._actor_mgr, "spawn_ego", return_value=MagicMock()), \
         patch.object(runner._actor_mgr, "spawn_traffic", return_value=MagicMock()), \
         patch.object(runner._sensor_mgr, "build_suite"):
        runner.start()

    # load_map must not be called because server is already on Town03
    mock_client.load_map.assert_not_called()
    runner.stop()


def test_scenario_runner_cleans_up_when_startup_fails():
    mock_client = MagicMock()
    mock_client.map.name = "Carla/Maps/Town10HD_Opt"
    mock_client.set_weather = MagicMock()
    mock_client.set_synchronous_mode = MagicMock()

    cfg = {
        "name": "test_startup_cleanup",
        "map": "current",
        "weather": "ClearNoon",
        "ego_vehicle": {"model": "vehicle.tesla.model3"},
        "traffic": {"vehicles": 0, "pedestrians": 0, "bicycles": 0},
        "sensors": {"rgb_camera": {"enabled": True}},
    }
    runner = ScenarioRunner(cfg, client=mock_client, backend="carla")

    with patch.object(runner._actor_mgr, "spawn_ego", return_value=MagicMock()), \
         patch.object(runner._actor_mgr, "spawn_traffic", return_value=MagicMock()), \
         patch.object(
             runner._sensor_mgr,
             "build_suite",
             side_effect=RuntimeError("camera spawn failed"),
         ), \
         patch.object(runner._sensor_mgr, "cleanup") as cleanup_sensors, \
         patch.object(runner._actor_mgr, "stop_traffic") as stop_traffic:
        with pytest.raises(RuntimeError, match="camera spawn failed"):
            runner.start()

    cleanup_sensors.assert_called_once()
    stop_traffic.assert_called_once()
    mock_client.disconnect.assert_called_once()
    assert runner._started is False


def test_carla_client_load_map_skips_redundant_load_world():
    """CarlaClient.load_map skips raw load_world if map name is already active."""
    client = CarlaClient(host="127.0.0.1", port=2000)
    client._client = MagicMock()
    client._map = DummyMap("/Game/Carla/Maps/Town03")

    with patch("edgeforge.simulation.carla_client.carla", MagicMock()):
        client.load_map("Town03")

    # raw_client.load_world must not be invoked
    client.raw_client.load_world.assert_not_called()


def test_simulation_service_start_defaults_carla_backend_to_current_map():
    """When starting CARLA simulation from UI/API without explicit map, default to 'current'."""
    runtime = SimulationRuntime()
    service = SimulationService(runtime)

    captured_configs = []

    def fake_run_loop(backend, cfg):
        captured_configs.append((backend, cfg))

    service._run_loop = fake_run_loop

    service.start(backend="carla", scenario_config={"weather": {"precipitation": 50}})

    assert len(captured_configs) == 1
    backend, cfg = captured_configs[0]
    assert backend == "carla"
    assert cfg["map"] == "current"
    service.stop()
