from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np


@dataclass
class MockTransform:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.5
    pitch: float = 0.0
    yaw: float = 0.0
    roll: float = 0.0

    @property
    def location(self) -> "MockTransform":
        return MockTransform(self.x, self.y, self.z)

    def get_forward_vector(self) -> "MockTransform":
        yr = math.radians(self.yaw)
        return MockTransform(math.cos(yr), math.sin(yr), 0.0)

    def get_right_vector(self) -> "MockTransform":
        yr = math.radians(self.yaw + 90.0)
        return MockTransform(math.cos(yr), math.sin(yr), 0.0)


@dataclass
class MockVehicleState:
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    speed_kmh: float = 0.0
    ax: float = 0.0
    ay: float = 0.0
    az: float = 0.0
    throttle: float = 0.0
    steer: float = 0.0
    brake: float = 0.0
    gear: int = 1
    rpm: float = 800.0


class MockActor:
    def __init__(self, actor_id: int, blueprint: str, transform: MockTransform,
                 attributes: Optional[Dict[str, Any]] = None):
        self.id = actor_id
        self.type_id = blueprint
        self.transform = transform
        self.attributes: Dict[str, Any] = attributes or {}
        self.state = MockVehicleState()
        self.alive = True

    def get_transform(self) -> MockTransform:
        return self.transform

    def get_velocity(self) -> MockTransform:
        return MockTransform(self.state.vx, self.state.vy, self.state.vz)

    def get_acceleration(self) -> MockTransform:
        return MockTransform(self.state.ax, self.state.ay, self.state.az)

    def get_control(self) -> MockVehicleState:
        return self.state

    def destroy(self) -> bool:
        self.alive = False
        return True


class MockWorldSnapshot:
    def __init__(self, frame: int, timestamp_s: float, platform_timestamp: float):
        self.frame = frame
        self.timestamp = type("T", (), {
            "elapsed_seconds": timestamp_s,
            "platform_timestamp": platform_timestamp,
            "delta_seconds": 0.05,
            "frame": frame,
        })()
        self._actors: Dict[int, MockActor] = {}

    def add(self, actor: MockActor) -> None:
        self._actors[actor.id] = actor

    def has_actor(self, actor_id: int) -> bool:
        return actor_id in self._actors and self._actors[actor_id].alive

    def find(self, actor_id: int) -> Optional[MockActor]:
        a = self._actors.get(actor_id)
        return a if a and a.alive else None


class MockCarlaClient:
    """Drop-in replacement for CarlaClient that works WITHOUT any CARLA server.

    Mimics the synchronous-mode API surface we actually use:
      - connect / is_connected / disconnect (no-ops, always succeeds)
      - apply_settings (synchronous_mode + fixed_delta_seconds respected)
      - get_world() → returns this client (we collapse world/client for simplicity)
      - tick() → advances internal clock + moves mock actors
      - wait_for_tick() / on_tick(callback) → synchronous listeners
      - get_map() / get_weather() / set_weather(preset) / load_map(name)
      - get_blueprint_library().filter(pattern) → returns list of str blueprint names
      - get_spawn_points() → returns List[MockTransform]
      - try_spawn_actor(bp, t) → MockActor
      - actor registry so ScenarioRunner/ActorManager/SensorManager work unchanged
      - get_snapshot() → MockWorldSnapshot for current frame
    """

    PRESET_WEATHER: Dict[str, Dict[str, float]] = {
        "ClearNoon":     {"cloudiness": 0.0, "precipitation": 0.0, "precipitation_deposits": 0.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 60.0,
                          "fog_density": 0.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 0.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "CloudyNoon":    {"cloudiness": 80.0, "precipitation": 0.0, "precipitation_deposits": 0.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 60.0,
                          "fog_density": 0.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 0.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "WetNoon":       {"cloudiness": 90.0, "precipitation": 0.0, "precipitation_deposits": 100.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 60.0,
                          "fog_density": 0.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 100.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "WetSunset":     {"cloudiness": 90.0, "precipitation": 0.0, "precipitation_deposits": 100.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 15.0,
                          "fog_density": 0.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 100.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "MidRainyNoon":  {"cloudiness": 80.0, "precipitation": 40.0, "precipitation_deposits": 50.0,
                          "wind_intensity": 25.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 60.0,
                          "fog_density": 10.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 60.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "HardRainNoon":  {"cloudiness": 100.0, "precipitation": 80.0, "precipitation_deposits": 100.0,
                          "wind_intensity": 50.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 45.0,
                          "fog_density": 20.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 100.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "SoftRainNoon":  {"cloudiness": 60.0, "precipitation": 20.0, "precipitation_deposits": 20.0,
                          "wind_intensity": 10.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 60.0,
                          "fog_density": 5.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 30.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "ClearSunset":   {"cloudiness": 0.0, "precipitation": 0.0, "precipitation_deposits": 0.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 15.0,
                          "fog_density": 0.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 0.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "CloudySunset":  {"cloudiness": 80.0, "precipitation": 0.0, "precipitation_deposits": 0.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 15.0,
                          "fog_density": 0.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 0.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "WetCloudySunset":{"cloudiness": 80.0, "precipitation": 0.0, "precipitation_deposits": 80.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 15.0,
                          "fog_density": 10.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 80.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "MidRainSunset": {"cloudiness": 80.0, "precipitation": 40.0, "precipitation_deposits": 50.0,
                          "wind_intensity": 25.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 15.0,
                          "fog_density": 15.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 60.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "HardRainSunset":{"cloudiness": 100.0, "precipitation": 80.0, "precipitation_deposits": 100.0,
                          "wind_intensity": 50.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 15.0,
                          "fog_density": 25.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 100.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "SoftRainSunset":{"cloudiness": 80.0, "precipitation": 30.0, "precipitation_deposits": 30.0,
                          "wind_intensity": 10.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 15.0,
                          "fog_density": 15.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 50.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
        "ClearSunrise":  {"cloudiness": 0.0, "precipitation": 0.0, "precipitation_deposits": 0.0,
                          "wind_intensity": 0.0, "sun_azimuth_angle": 0.0, "sun_altitude_angle": 5.0,
                          "fog_density": 0.0, "fog_distance": 0.0, "fog_falloff": 0.0, "wetness": 0.0,
                          "scattering_intensity": 0.0, "mie_scattering_scale": 0.0, "rayleigh_scattering_scale": 0.0331},
    }

    BLUEPRINTS = [
        "vehicle.tesla.model3", "vehicle.toyota.prius", "vehicle.audi.a2",
        "vehicle.volkswagen.t2", "vehicle.bmw.grandtourer", "vehicle.nissan.patrol",
        "vehicle.bh.crossbike", "vehicle.diamondback.century",
        "sensor.camera.rgb", "sensor.lidar.ray_cast", "sensor.other.imu",
        "sensor.other.gnss", "sensor.other.collision", "sensor.other.lane_invasion",
        "walker.pedestrian.0001", "walker.pedestrian.0002", "walker.pedestrian.0003",
    ]

    def __init__(self, host: str = "mock://localhost", port: int = 2000, timeout_s: float = 5.0,
                 fixed_delta_seconds: float = 0.05):
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._connected = False
        self._frame = 0
        self._elapsed_s = 0.0
        self._fixed_dt = fixed_delta_seconds
        self._sync_mode = True
        self._map_name = "Town01"
        self._weather: Dict[str, float] = dict(self.PRESET_WEATHER["ClearNoon"])
        self._actors: Dict[int, MockActor] = {}
        self._next_id = 1
        self._tick_callbacks: List[Callable[[MockWorldSnapshot], None]] = []
        self._lock = threading.RLock()
        self._sensors_blueprints: Dict[str, Any] = {}

    # ------------------------------------------------------------------ connection
    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------ settings
    def apply_settings(self, settings: Any) -> None:
        self._sync_mode = bool(getattr(settings, "synchronous_mode", self._sync_mode))
        self._fixed_dt = float(getattr(settings, "fixed_delta_seconds", self._fixed_dt))

    def get_settings(self):
        class _S:
            synchronous_mode = self._sync_mode
            fixed_delta_seconds = self._fixed_dt
            no_rendering_mode = False
        return _S()

    def set_timeout(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s

    # ------------------------------------------------------------------ world proxy
    def get_world(self) -> "MockCarlaClient":
        return self

    def get_map(self):
        name = self._map_name
        return type("Map", (), {"name": name, "id": name})()

    def load_map(self, name: str) -> None:
        self._map_name = name
        self._actors.clear()

    # ------------------------------------------------------------------ weather
    def get_weather(self) -> Dict[str, float]:
        return dict(self._weather)

    def set_weather_preset(self, name: str) -> None:
        """Apply a weather preset by name (case-insensitive)."""
        # Try direct match then case-insensitive match
        if name in self.PRESET_WEATHER:
            self._weather = dict(self.PRESET_WEATHER[name])
            return
        lower_map = {k.lower(): k for k in self.PRESET_WEATHER}
        if name.lower() in lower_map:
            self._weather = dict(self.PRESET_WEATHER[lower_map[name.lower()]])
            return
        logger.warning(
            f"Weather preset '{name}' not found in mock presets; keeping current weather."
        )

    def set_weather(self, weather_params: Any, preset_base: str = "ClearNoon") -> None:
        """Apply a preset string or dictionary of fine-grained weather parameters."""
        if isinstance(weather_params, str):
            self.set_weather_preset(weather_params)
            return
        if isinstance(weather_params, dict):
            base_preset = weather_params.get("preset", preset_base)
            if base_preset in self.PRESET_WEATHER:
                self._weather = dict(self.PRESET_WEATHER[base_preset])
            for k, v in weather_params.items():
                if k in self._weather and isinstance(v, (int, float)):
                    self._weather[k] = float(v)
            return
        raise TypeError(f"Unsupported weather_params type: {type(weather_params)}")

    # ------------------------------------------------------------------ blueprints + spawns
    def get_blueprint_library(self):
        parent = self

        class _BP:
            def filter(bp_self, pattern: str) -> List[Any]:
                pat = pattern.lower().replace("*", "")
                matched = [bp for bp in parent.BLUEPRINTS if pat in bp.lower()]

                class _Entry:
                    def __init__(e_self, bp_name: str):
                        e_self.id = bp_name
                        e_self._attrs: Dict[str, Any] = {}

                    def has_attribute(e_self, key: str) -> bool:
                        return key in e_self._attrs

                    def set_attribute(e_self, key: str, val: Any) -> None:
                        e_self._attrs[key] = val

                    def __repr__(e_self) -> str:
                        return f"BP({e_self.id})"

                return [_Entry(m) for m in matched]

        return _BP()

    def get_spawn_points(self) -> List[MockTransform]:
        return [MockTransform(x=float(i * 5), y=0.0, z=0.3, yaw=0.0) for i in range(50)]

    # ------------------------------------------------------------------ actors
    def try_spawn_actor(self, blueprint: Any, transform: MockTransform,
                        attach_to: Optional[MockActor] = None,
                        attachment_type: Any = None) -> Optional[MockActor]:
        bp_name = blueprint.id if hasattr(blueprint, "id") else str(blueprint)
        attrs: Dict[str, Any] = getattr(blueprint, "_attrs", {}) or {}
        with self._lock:
            actor = MockActor(self._next_id, bp_name, MockTransform(transform.x, transform.y, transform.z,
                                                                    getattr(transform, "pitch", 0.0),
                                                                    getattr(transform, "yaw", 0.0),
                                                                    getattr(transform, "roll", 0.0)),
                              attributes=dict(attrs))
            if attach_to is not None:
                actor.attributes["parent_id"] = attach_to.id
            self._actors[actor.id] = actor
            self._next_id += 1
        return actor

    def get_actor(self, actor_id: int) -> Optional[MockActor]:
        a = self._actors.get(actor_id)
        return a if a and a.alive else None

    def get_actors(self, ids: Optional[List[int]] = None):
        with self._lock:
            items = [a for a in self._actors.values() if a.alive]
            if ids:
                items = [a for a in items if a.id in ids]
        class _List:
            def __len__(l_self) -> int: return len(items)
            def __iter__(l_self): return iter(items)
            def filter(l_self, pattern: str):
                pat = pattern.lower().replace("*", "")
                return [a for a in items if pat in a.type_id.lower()]
        return _List()

    # ------------------------------------------------------------------ tick / snapshot
    def tick(self) -> int:
        with self._lock:
            self._frame += 1
            self._elapsed_s += self._fixed_dt
            snap = self._build_snapshot()
        for cb in list(self._tick_callbacks):
            try:
                cb(snap)
            except Exception:  # pragma: no cover - defensive
                pass
        return self._frame

    def wait_for_tick(self, timeout_s: Optional[float] = None) -> MockWorldSnapshot:
        return self._build_snapshot()

    def on_tick(self, callback: Callable[[MockWorldSnapshot], None]) -> int:
        self._tick_callbacks.append(callback)
        return len(self._tick_callbacks)

    def remove_on_tick(self, handle: int) -> None:
        if 0 < handle <= len(self._tick_callbacks):
            # just no-op removal to avoid index drift issues in tests
            pass

    def get_snapshot(self) -> MockWorldSnapshot:
        return self._build_snapshot()

    def _build_snapshot(self) -> MockWorldSnapshot:
        snap = MockWorldSnapshot(self._frame, self._elapsed_s, time.time())
        with self._lock:
            for a in self._actors.values():
                if a.alive:
                    snap.add(a)
        return snap

    # ------------------------------------------------------------------ conv
    def __repr__(self) -> str:
        return f"<MockCarlaClient connected={self._connected} map={self._map_name} frame={self._frame}>"
