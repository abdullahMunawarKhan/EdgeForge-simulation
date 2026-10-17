"""Smoke tests for the EdgeForge foundation layer.

None of these tests require CARLA or any ML models.
They validate:
  * Settings load with safe defaults
  * get_logger returns a usable logger
  * CameraProcessor validates frames correctly
  * ObjectDetector returns an empty list on valid input
  * RiskEngine produces expected RiskLevel enum values + boundary scores
"""

from __future__ import annotations

import numpy as np
import pytest

from edgeforge.analysis import RiskEngine
from edgeforge.config import settings
from edgeforge.data import DetectedObject, RiskLevel, VehicleState
from edgeforge.perception import CameraProcessor, ObjectDetector
from edgeforge.utils import get_logger


# ---- Settings ---------------------------------------------------------------
def test_settings_defaults_populated() -> None:
    assert settings.PROJECT_NAME == "EdgeForge"
    assert settings.CAMERA_WIDTH > 0
    assert settings.CAMERA_HEIGHT > 0
    assert 0.0 <= settings.RISK_THRESHOLD <= 1.0


# ---- Logger -----------------------------------------------------------------
def test_get_logger_returns_something_callable() -> None:
    log = get_logger("tests")
    assert log is not None
    log.info("hello from pytest")  # must not raise


# ---- CameraProcessor --------------------------------------------------------
def test_camera_processor_rejects_none_and_shapes() -> None:
    cp = CameraProcessor(640, 360)
    assert not cp.is_valid_frame(None)
    assert not cp.is_valid_frame(np.array([]))
    assert not cp.is_valid_frame(np.zeros((5, 5, 5, 5)))  # 4D nope

    info = cp.get_frame_info(None)
    assert info.empty is True
    assert info.width == 0


def test_camera_processor_accepts_uint8_bgr() -> None:
    cp = CameraProcessor()
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    assert cp.is_valid_frame(frame)
    info = cp.get_frame_info(frame)
    assert (info.width, info.height, info.channels) == (200, 100, 3)


def test_camera_processor_resize() -> None:
    cp = CameraProcessor()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    small = cp.resize_frame(frame, 640, 360)
    assert small.shape[:2] == (360, 640)


# ---- ObjectDetector ---------------------------------------------------------
def test_detector_returns_empty_list_on_valid_frame() -> None:
    det = ObjectDetector(model_name=None)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = det.detect(frame)
    assert isinstance(result, list)
    assert len(result) == 0


def test_detector_handles_none_gracefully() -> None:
    det = ObjectDetector(model_name=None)
    assert det.detect(None) == []


def test_detector_status_shows_no_model_loaded() -> None:
    det = ObjectDetector(model_name=None)
    status = det.get_status()
    assert status["module"] == "object_detector"
    assert status["model_loaded"] is False
    assert status["status"] == "initialized"


# ---- RiskEngine -------------------------------------------------------------
def test_risk_engine_empty_list_is_low() -> None:
    engine = RiskEngine()
    ego = VehicleState(speed=10.0)
    out = engine.calculate_risk([], ego)
    assert out.risk_level == RiskLevel.LOW
    assert out.risk_score == pytest.approx(0.0, abs=1e-9)


def test_risk_engine_close_and_climbing_is_high_or_critical() -> None:
    engine = RiskEngine()
    ego = VehicleState(speed=20.0)
    hazards = [
        DetectedObject(
            object_id="danger",
            object_type="pedestrian",
            confidence=0.9,
            distance=3.0,
            relative_speed=-20.0,  # hard closing speed
        )
    ]
    out = engine.calculate_risk(hazards, ego)
    # 3m + 20m/s closing → should be in HIGH or CRITICAL
    assert out.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    assert out.risk_score >= 0.55
    assert "danger" in out.contributing_objects
    assert len(out.reason) > 0


def test_risk_engine_handles_unknown_detection_distance_and_speed() -> None:
    out = RiskEngine().calculate_risk(
        [DetectedObject(object_type="car", distance=None, relative_speed=None)],
        VehicleState(),
    )
    assert out.risk_score == pytest.approx(0.0)
    assert "risk assessment is incomplete" in out.reason


def test_risk_level_enum_values() -> None:
    # Sanity check so the dashboard colour scheme has stable labels.
    assert {r.value for r in RiskLevel} == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


# ---- MockCarlaClient --------------------------------------------------------
def test_mock_client_connect_and_ticks() -> None:
    from edgeforge.simulation.mock_client import MockCarlaClient

    client = MockCarlaClient(fixed_delta_seconds=0.05)
    assert client.connect() is True
    assert client.is_connected() is True
    snap0 = client.get_snapshot()
    assert snap0.frame == 0
    f1 = client.tick()
    assert f1 == 1
    snap = client.get_snapshot()
    assert snap.frame == 1
    assert abs(snap.timestamp.elapsed_seconds - 0.05) < 1e-6


def test_mock_client_blueprints_and_spawn() -> None:
    from edgeforge.simulation.mock_client import MockCarlaClient

    c = MockCarlaClient()
    c.connect()
    lib = c.get_blueprint_library()
    tesla_bps = lib.filter("vehicle.tesla")
    assert len(tesla_bps) >= 1
    spawn_points = c.get_spawn_points()
    assert len(spawn_points) >= 20
    a = c.try_spawn_actor(tesla_bps[0], spawn_points[0])
    assert a is not None
    assert a.type_id.startswith("vehicle.")


def test_mock_client_unknown_weather_preset_keeps_current_weather() -> None:
    from edgeforge.simulation.mock_client import MockCarlaClient

    client = MockCarlaClient()
    client.set_weather_preset("UnknownPreset")

    assert client.get_weather() == client.PRESET_WEATHER["ClearNoon"]


# ---- MockActorManager (kinematics + path) -----------------------------------
def test_mock_actor_manager_ego_moves_with_autopilot() -> None:
    from edgeforge.simulation.mock_actor_manager import MockActorManager
    from edgeforge.simulation.mock_client import MockCarlaClient
    from edgeforge.simulation.scenario_runner import _advance_mock_actors

    client = MockCarlaClient(fixed_delta_seconds=0.05)
    client.connect()
    mgr = MockActorManager(client)
    bundle = mgr.spawn_ego({"model": "vehicle.toyota.prius", "autopilot": True, "speed_limit": 60})
    bundle.vehicle.attributes["is_ego"] = True
    start_x = bundle.vehicle.transform.x
    start_speed = bundle.vehicle.state.speed_kmh
    for _ in range(200):
        _advance_mock_actors(client, 0.05)
        client.tick()
    moved_m = bundle.vehicle.transform.x - start_x
    gained = bundle.vehicle.state.speed_kmh - start_speed
    assert moved_m > 20.0, f"Ego should move forward (moved {moved_m:.1f}m)"
    assert gained > 15.0, f"Ego should speed up on autopilot (gained {gained:.1f} km/h)"


# ---- MockSensorManager (RGB frames produced) --------------------------------
def test_mock_sensor_manager_produces_rgb() -> None:
    from edgeforge.simulation.mock_client import MockCarlaClient
    from edgeforge.simulation.mock_sensor_manager import MockSensorManager
    import numpy as np

    c = MockCarlaClient()
    c.connect()
    bp = c.get_blueprint_library().filter("vehicle.tesla")[0]
    sp = c.get_spawn_points()[0]
    ego = c.try_spawn_actor(bp, sp)
    sm = MockSensorManager(c)
    W, H = 320, 240
    sm.build_suite(ego, {"rgb_camera": {"enabled": True, "width": W, "height": H, "tick": 0.05}})
    # Frame 0 — push tick and validate a frame was emitted
    sm.update_for_tick(frame_number=1, sim_time_s=0.05, actors=[])
    assert sm.latest_rgb is not None
    assert sm.latest_rgb.shape == (H, W, 3)
    assert sm.latest_rgb.dtype == np.uint8
    # Ensure the synthetic image isn't just a blank canvas (pixel variation)
    assert sm.latest_rgb.std() > 5.0, "Mock RGB frame should have visible variation"


# ---- ScenarioRunner backend dispatch + full loop (end-to-end mock) ----------
def test_scenario_runner_backend_mock_end_to_end() -> None:
    import json
    import tempfile
    from pathlib import Path
    from edgeforge.simulation import ScenarioRunner, SensorFrame

    cfg = {
        "name": "mock_test",
        "version": "1.0",
        "description": "ci-test",
        "duration_seconds": 0.5,
        "weather": "ClearNoon",
        "map": "Town01",
        "simulation": {"backend": "mock"},
        "traffic": {"vehicles": 2, "pedestrians": 1, "bicycles": 0},
        "ego_vehicle": {"model": "vehicle.tesla.model3", "spawn_point_index": 0, "autopilot": True, "speed_limit": 50},
        "sensors": {
            "rgb_camera": {"enabled": True, "width": 160, "height": 120, "tick": 0.1},
            "collision": {"enabled": True},
            "lane_invasion": {"enabled": True},
        },
    }
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "scen.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")

        runner = ScenarioRunner.from_config(str(p), backend="mock")
        assert runner.backend == "mock"
        assert runner.info.backend == "mock"

        frames_seen = 0
        seen_vehicle_state = False
        seen_rgb = False
        with runner.run() as stream:
            for frame in stream:
                assert isinstance(frame, SensorFrame)
                frames_seen += 1
                if frame.vehicle_state is not None:
                    seen_vehicle_state = True
                    assert frame.vehicle_state.speed is not None
                    assert frame.vehicle_state.location is not None
                if frame.rgb is not None:
                    seen_rgb = True

        # 0.5s / 0.05 = 10 ticks; warmup happens first so we should see >= 5
        assert frames_seen >= 3, f"Expected frames, got {frames_seen}"
        assert seen_vehicle_state, "Every mock scenario should emit VehicleState"
        assert seen_rgb, "RGB camera enabled → frames should flow"
