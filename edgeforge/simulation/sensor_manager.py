"""
Sensor factory + data adapters for the EdgeForge ↔ CARLA bridge.

Two kinds of helpers live here:

1. **Sensor factories** — build and attach the right CARLA sensor actors
   to a vehicle given a scenario-sensor spec dictionary (see
   ``default_scenario.json`` → ``sensors`` key).

2. **Data adapters** — turn raw CARLA objects (``carla.Image``,
   ``carla.Vehicle``, collision events, …) into the numpy / Pydantic
   types expected by the rest of the EdgeForge pipeline:
     * ``carla.Image``  → ``np.ndarray`` (BGR, uint8)
     * ``carla.Vehicle`` → ``VehicleState`` (pydantic model)
"""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    import carla
else:
    try:
        import carla
    except ImportError:
        carla = None
import numpy as np

from edgeforge.config import settings
from edgeforge.data.models import DetectedObject, Location, VehicleState
from edgeforge.utils import get_logger

logger = get_logger(__name__)

CAMERA_VIEW_MOUNTS = {
    "front": (1.5, 0.0, 2.4, 0.0, 0.0),
    "top_down": (0.0, 0.0, 20.0, -90.0, 0.0),
}


# ---------------------------------------------------------------------------
# Frame / event dataclasses (typed packets between modules)
# ---------------------------------------------------------------------------
@dataclass
class SensorFrame:
    """One complete sensor sample emitted by the scenario loop."""

    timestamp: float  # sim elapsed seconds
    frame_number: int
    rgb: Optional[np.ndarray] = None          # BGR uint8 shape (H,W,3)
    vehicle_state: Optional[VehicleState] = None
    collision_events: List[Any] = field(default_factory=list)
    lane_invasions: List[Any] = field(default_factory=list)
    camera_views: Dict[str, np.ndarray] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Data adapters (CARLA → pipeline types)
# ---------------------------------------------------------------------------
def image_to_bgr(image: carla.Image) -> np.ndarray:
    """Convert a ``carla.Image`` (BGRA) into an OpenCV-friendly BGR array.

    This is the canonical adapter: every module in the perception
    pipeline should receive its input through this function (or via the
    SensorManager callback plumbing below) so colour-space / shape
    assumptions stay in one place.
    """
    array = np.frombuffer(image.raw_data, dtype=np.uint8)
    array = np.reshape(array, (image.height, image.width, 4))
    return array[:, :, :3].copy()  # drop alpha, BGR order


def vehicle_to_state(
    vehicle: carla.Vehicle,
    vehicle_id: str = "ego_001",
    sim_elapsed: Optional[float] = None,
) -> VehicleState:
    """Build a ``VehicleState`` pydantic model from a CARLA vehicle.

    Note on coordinate conventions:
      * speed = magnitude of the velocity vector (always >= 0) [m/s]
      * acceleration = forward component of the acceleration vector [m/s^2]
    """
    velocity = vehicle.get_velocity()
    accel = vehicle.get_acceleration()
    transform = vehicle.get_transform()
    loc = transform.location

    speed = math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)

    forward = transform.get_forward_vector()
    acceleration_forward = (
        accel.x * forward.x + accel.y * forward.y + accel.z * forward.z
    )

    ts = datetime.fromtimestamp(sim_elapsed, tz=timezone.utc) if sim_elapsed is not None else datetime.utcnow()

    return VehicleState(
        vehicle_id=vehicle_id,
        speed=float(speed),
        acceleration=float(acceleration_forward),
        location=Location(x=float(loc.x), y=float(loc.y), z=float(loc.z)),
        timestamp=ts,
    )


# ---------------------------------------------------------------------------
# Sensor manager (factory + callback registry)
# ---------------------------------------------------------------------------
class SensorManager:
    """Builds and manages the sensor suite for a single ego vehicle.

    Usage::

        sm = SensorManager(client)
        sm.build_suite(ego_vehicle, scenario_sensors_cfg)
        # ... run simulation ...
        latest = sm.latest_frame
        sm.cleanup()
    """

    def __init__(self, client: "CarlaClient") -> None:  # type: ignore[name-defined]
        self._client = client
        self._sensors: List[carla.Actor] = []
        self.rgb_cameras: Dict[str, Any] = {}

        self.latest_rgb: Optional[np.ndarray] = None
        self.latest_rgb_frame: int = -1
        self.latest_rgb_views: Dict[str, np.ndarray] = {}
        self.latest_rgb_view_frames: Dict[str, int] = {}
        self._rgb_views_lock = threading.Lock()

        self.collision_events: List[Dict[str, Any]] = []
        self.lane_invasions: List[Dict[str, Any]] = []

        self.external_rgb_callback: Optional[Callable[[np.ndarray], None]] = None
        self.external_collision_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.external_lane_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------
    def build_suite(
        self,
        vehicle: carla.Vehicle,
        sensor_spec: Dict[str, Any],
    ) -> None:
        """Spawn every sensor declared in ``sensor_spec`` and attach to vehicle."""
        if carla is None:
            raise RuntimeError(
                "The CARLA Python API is required to attach CARLA sensors. "
                "Install carla or run inside an environment with the CARLA client library."
            )

        rgb_cfg = sensor_spec.get("rgb_camera", {})
        if rgb_cfg.get("enabled", False):
            self._attach_rgb_cameras(
                vehicle=vehicle,
                width=int(rgb_cfg.get("width", settings.CAMERA_WIDTH)),
                height=int(rgb_cfg.get("height", settings.CAMERA_HEIGHT)),
                fov=int(rgb_cfg.get("fov", settings.CAMERA_FOV)),
                tick=float(rgb_cfg.get("tick", settings.CAMERA_TICK)),
            )

        if sensor_spec.get("collision", {}).get("enabled", False):
            self._attach_collision_sensor(vehicle)

        if sensor_spec.get("lane_invasion", {}).get("enabled", False):
            self._attach_lane_invasion_sensor(vehicle)

        # Stubs for future sensors.  Log so the simulation lead can verify
        # that the scenario config is being parsed correctly.
        for stub in ("lidar", "imu", "gnss"):
            cfg = sensor_spec.get(stub, {})
            if cfg.get("enabled", False):
                logger.info(
                    f"Sensor '{stub}' is enabled in scenario config but the "
                    f"adapter is a stub (no actor spawned).  Integration is "
                    f"the responsibility of the perception lead — the data "
                    f"contract shape is: np.ndarray point-cloud / pydantic "
                    f"IMUSample / GNSSSample."
                )

    # ---- RGB --------------------------------------------------------------
    def _attach_rgb_cameras(
        self,
        vehicle: carla.Vehicle,
        width: int,
        height: int,
        fov: int,
        tick: float,
    ) -> None:
        bp = self._client.blueprint_library.find("sensor.camera.rgb")
        bp.set_attribute("image_size_x", str(width))
        bp.set_attribute("image_size_y", str(height))
        bp.set_attribute("fov", str(fov))
        bp.set_attribute("sensor_tick", str(tick))

        for camera_name, (x, y, z, pitch, yaw) in CAMERA_VIEW_MOUNTS.items():
            transform = carla.Transform(
                carla.Location(x=x, y=y, z=z),
                carla.Rotation(pitch=pitch, yaw=yaw),
            )
            sensor = self._client.world.spawn_actor(bp, transform, attach_to=vehicle)
            self._client.register_actor(sensor)
            self._sensors.append(sensor)
            self.rgb_cameras[camera_name] = sensor

            def on_image(image: carla.Image, name: str = camera_name) -> None:
                frame = image_to_bgr(image)
                with self._rgb_views_lock:
                    self.latest_rgb_views[name] = frame
                    self.latest_rgb_view_frames[name] = image.frame
                    if name == "front":
                        self.latest_rgb = frame
                        self.latest_rgb_frame = image.frame
                if name == "front" and self.external_rgb_callback is not None:
                    self.external_rgb_callback(frame)

            sensor.listen(on_image)
            logger.success(
                f"📷 {camera_name} RGB camera attached: "
                f"{width}x{height} @ {fov}° tick={tick}s"
            )

    def get_synchronized_rgb_views(self, frame_number: int) -> Dict[str, np.ndarray]:
        """Return only camera frames captured on the requested simulator tick."""
        with self._rgb_views_lock:
            return {
                name: frame
                for name, frame in self.latest_rgb_views.items()
                if self.latest_rgb_view_frames.get(name) == frame_number
            }

    # ---- Collision --------------------------------------------------------
    def _attach_collision_sensor(self, vehicle: carla.Vehicle) -> None:
        bp = self._client.blueprint_library.find("sensor.other.collision")
        sensor = self._client.world.spawn_actor(bp, carla.Transform(), attach_to=vehicle)
        self._client.register_actor(sensor)
        self._sensors.append(sensor)

        def on_collision(event: carla.CollisionEvent) -> None:
            ts = getattr(event.timestamp, "elapsed_seconds", event.timestamp)
            entry = {
                "frame": event.frame,
                "timestamp": float(ts),
                "other_actor": event.other_actor.type_id if event.other_actor else "unknown",
                "impulse_norm": math.sqrt(
                    event.normal_impulse.x**2 +
                    event.normal_impulse.y**2 +
                    event.normal_impulse.z**2
                ),
            }
            self.collision_events.append(entry)
            if self.external_collision_callback is not None:
                self.external_collision_callback(entry)
            logger.warning(
                f"💥 Collision @ frame {entry['frame']}: {entry['other_actor']} "
                f"(impulse={entry['impulse_norm']:.1f})"
            )

        sensor.listen(on_collision)
        logger.info("💥 Collision sensor attached.")

    # ---- Lane invasion ----------------------------------------------------
    def _attach_lane_invasion_sensor(self, vehicle: carla.Vehicle) -> None:
        bp = self._client.blueprint_library.find("sensor.other.lane_invasion")
        sensor = self._client.world.spawn_actor(bp, carla.Transform(), attach_to=vehicle)
        self._client.register_actor(sensor)
        self._sensors.append(sensor)

        def on_lane(event: carla.LaneInvasionEvent) -> None:
            ts = getattr(event.timestamp, "elapsed_seconds", event.timestamp)
            entry = {
                "frame": event.frame,
                "timestamp": float(ts),
                "crossed_markings": [str(m.type) for m in event.crossed_lane_markings],
            }
            self.lane_invasions.append(entry)
            if self.external_lane_callback is not None:
                self.external_lane_callback(entry)
            logger.info(
                f"🛣  Lane invasion @ frame {entry['frame']}: "
                f"{entry['crossed_markings']}"
            )

        sensor.listen(on_lane)
        logger.info("🛣  Lane-invasion sensor attached.")

    # ------------------------------------------------------------------
    # Drain helpers (call once per tick to gather accumulated events)
    # ------------------------------------------------------------------
    def drain_collision_events(self) -> List[Dict[str, Any]]:
        events, self.collision_events = self.collision_events, []
        return events

    def drain_lane_invasions(self) -> List[Dict[str, Any]]:
        items, self.lane_invasions = self.lane_invasions, []
        return items

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        """Stop listening on every sensor (actors are destroyed via client)."""
        for s in self._sensors:
            if s.is_alive:
                try:
                    stop_fn = getattr(s, "stop", None)
                    if callable(stop_fn):
                        stop_fn()
                except Exception:
                    logger.exception("Could not stop a CARLA sensor during cleanup.")
        self._sensors.clear()
        self.rgb_cameras.clear()
