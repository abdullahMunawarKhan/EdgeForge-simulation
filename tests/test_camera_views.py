from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from edgeforge.simulation import sensor_manager as sensor_module
from edgeforge.simulation.sensor_manager import CAMERA_VIEW_MOUNTS, SensorManager


class _Blueprint:
    def set_attribute(self, name: str, value: str) -> None:
        pass


class _Sensor:
    def __init__(self) -> None:
        self.callback = None
        self.is_alive = True
        self.stop_calls = 0

    def listen(self, callback) -> None:
        self.callback = callback

    def stop(self) -> None:
        self.stop_calls += 1


class _World:
    def __init__(self) -> None:
        self.spawned: list[tuple[_Blueprint, object, object]] = []
        self.sensors: list[_Sensor] = []

    def spawn_actor(self, blueprint, transform, attach_to):
        sensor = _Sensor()
        self.spawned.append((blueprint, transform, attach_to))
        self.sensors.append(sensor)
        return sensor


class _Client:
    def __init__(self) -> None:
        self.blueprint_library = SimpleNamespace(find=lambda _name: _Blueprint())
        self.world = _World()
        self.registered = []

    def register_actor(self, actor) -> None:
        self.registered.append(actor)


def _image(frame_number: int) -> SimpleNamespace:
    pixels = np.zeros((4, 6, 4), dtype=np.uint8)
    pixels[:, :, 2] = 100
    return SimpleNamespace(
        raw_data=pixels.tobytes(),
        height=4,
        width=6,
        frame=frame_number,
    )


def test_managed_camera_suite_attaches_three_views_to_same_ego_and_cleans_up(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        sensor_module,
        "carla",
        SimpleNamespace(
            Location=lambda **values: values,
            Rotation=lambda **values: values,
            Transform=lambda location, rotation: (location, rotation),
        ),
    )
    client = _Client()
    ego = object()
    sensors = SensorManager(client)

    sensors.build_suite(
        ego,
        {
            "rgb_camera": {
                "enabled": True,
                "width": 6,
                "height": 4,
                "tick": 0.05,
            }
        },
    )

    assert len(client.world.spawned) == 3
    assert len(client.registered) == 3
    assert all(attachment is ego for _, _, attachment in client.world.spawned)
    assert list(CAMERA_VIEW_MOUNTS) == [
        "front",
        "right_side",
        "top_down",
    ]
    top_location, top_rotation = client.world.spawned[2][1]
    assert top_location == {"x": 0.0, "y": 0.0, "z": 20.0}
    assert top_rotation == {"pitch": -90.0, "yaw": 0.0}

    for sensor in client.world.sensors:
        sensor.callback(_image(12))
    synchronized = sensors.get_synchronized_rgb_views(12)
    assert set(synchronized) == {"front", "right_side", "top_down"}
    assert all(frame.shape == (4, 6, 3) for frame in synchronized.values())
    assert sensors.latest_rgb is synchronized["front"]

    client.world.sensors[2].callback(_image(13))
    assert set(sensors.get_synchronized_rgb_views(12)) == {"front", "right_side"}

    sensors.cleanup()
    assert all(sensor.stop_calls == 1 for sensor in client.world.sensors)


def test_camera_cleanup_continues_after_a_sensor_stop_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        sensor_module,
        "carla",
        SimpleNamespace(
            Location=lambda **values: values,
            Rotation=lambda **values: values,
            Transform=lambda location, rotation: (location, rotation),
        ),
    )
    client = _Client()
    sensors = SensorManager(client)
    sensors.build_suite(
        object(),
        {"rgb_camera": {"enabled": True, "width": 6, "height": 4}},
    )

    def fail_stop() -> None:
        raise RuntimeError("stop failed")

    client.world.sensors[1].stop = fail_stop
    logged_errors = []
    monkeypatch.setattr(
        sensor_module.logger,
        "exception",
        lambda message: logged_errors.append(message),
    )

    sensors.cleanup()

    assert client.world.sensors[0].stop_calls == 1
    assert client.world.sensors[2].stop_calls == 1
    assert sensors._sensors == []
    assert logged_errors == ["Could not stop a CARLA sensor during cleanup."]
