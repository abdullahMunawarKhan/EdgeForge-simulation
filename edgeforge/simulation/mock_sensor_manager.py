"""
Sensor factory + adapters for MOCK simulation mode (no CARLA wheel needed).

Mirrors the public shape of ``sensor_manager.SensorManager`` exactly:

  - build_suite(vehicle, sensor_spec)       — wires a synthetic "sensor suite"
  - latest_rgb: np.ndarray | None           — latest 3-channel BGR frame
  - latest_rgb_frame: int                   — frame # of last RGB callback
  - drain_collision_events() -> List[dict]
  - drain_lane_invasions()  -> List[dict]
  - external_rgb_callback / external_collision_callback / external_lane_callback

The RGB frame is a synthetic scene pattern (sky gradient + scrolling dashed
lane markings + a few "cars" as moving coloured rectangles) so the
perception + display stacks see content that *visually changes* frame to
frame, which is essential when testing Detector + HUD + CV2 windows.

Synthetic ground-truth detections (``latest_ground_truth_objects`` list)
are produced each RGB push — same world-space NPCs that are drawn into
the frame.  This lets the pipeline produce non-trivial DetectedObject →
RiskAssessment values *before* Person 2 wires real YOLO.  Callers in
main.py can optionally treat ``sm.latest_ground_truth_objects`` as the
"oracle detector" for mock demos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from edgeforge.data.models import DetectedObject, Location, VehicleState
from edgeforge.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Frame dataclass (shared with the real SensorManager — we redefine the
# exact same shape so isinstance checks are forgiving).
# ---------------------------------------------------------------------------
@dataclass
class SensorFrame:
    timestamp: float
    frame_number: int
    rgb: Optional[np.ndarray] = None
    vehicle_state: Optional[VehicleState] = None
    collision_events: List[Any] = field(default_factory=list)
    lane_invasions: List[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Duck-typed image adapter (matches what image_to_bgr() expects)
# ---------------------------------------------------------------------------
@dataclass
class _MockRawImage:
    width: int
    height: int
    frame: int
    raw_data: bytes


def image_to_bgr(image: _MockRawImage) -> np.ndarray:
    array = np.frombuffer(image.raw_data, dtype=np.uint8)
    array = np.reshape(array, (image.height, image.width, 4))
    return array[:, :, :3].copy()


def vehicle_to_state(
    actor: Any,
    vehicle_id: str = "ego_001",
    sim_elapsed: Optional[float] = None,
) -> VehicleState:
    """Reconstruct a pydantic VehicleState from a MockActor's attributes.

    The MockActor kinematic state is stored directly on its ``.state``
    attribute (vx, vy, vz, speed_kmh, ax, ay, az) plus ``.transform``.
    """
    vx = float(getattr(actor.state, "vx", 0.0))
    vy = float(getattr(actor.state, "vy", 0.0))
    vz = float(getattr(actor.state, "vz", 0.0))
    ax = float(getattr(actor.state, "ax", 0.0))
    ay = float(getattr(actor.state, "ay", 0.0))
    az = float(getattr(actor.state, "az", 0.0))
    speed = math.sqrt(vx * vx + vy * vy + vz * vz)

    t = actor.transform
    yaw_rad = math.radians(float(getattr(t, "yaw", 0.0)))
    fx = math.cos(yaw_rad)
    fy = math.sin(yaw_rad)
    fz = 0.0
    acceleration_forward = ax * fx + ay * fy + az * fz

    ts = datetime.fromtimestamp(sim_elapsed, tz=timezone.utc) if sim_elapsed is not None else datetime.utcnow()

    return VehicleState(
        vehicle_id=vehicle_id,
        speed=float(speed),
        acceleration=float(acceleration_forward),
        location=Location(x=float(t.x), y=float(t.y), z=float(t.z)),
        timestamp=ts,
    )


# ---------------------------------------------------------------------------
# Sensor manager
# ---------------------------------------------------------------------------
class MockSensorManager:
    """Build + update a synthetic sensor suite for a MockActor."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self._sensors: List[Any] = []
        self._rgb_cfg: Optional[Dict[str, Any]] = None
        self._rgb_next_tick_at = 0.0
        self._collision_enabled = False
        self._lane_enabled = False
        self._collision_cooldown_until = 0.0
        self._lane_cooldown_until = 0.0

        self.latest_rgb: Optional[np.ndarray] = None
        self.latest_rgb_frame: int = -1
        self.latest_ground_truth_objects: List[DetectedObject] = []

        self.collision_events: List[Dict[str, Any]] = []
        self.lane_invasions: List[Dict[str, Any]] = []

        self.external_rgb_callback: Optional[Callable[[np.ndarray], None]] = None
        self.external_collision_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.external_lane_callback: Optional[Callable[[Dict[str, Any]], None]] = None

    # ------------------------------------------------------------ build suite
    def build_suite(self, vehicle: Any, sensor_spec: Dict[str, Any]) -> None:
        rgb_cfg = sensor_spec.get("rgb_camera", {})
        if rgb_cfg.get("enabled", False):
            self._rgb_cfg = {
                "width": int(rgb_cfg.get("width", 320)),
                "height": int(rgb_cfg.get("height", 240)),
                "fov": int(rgb_cfg.get("fov", 90)),
                "tick": float(rgb_cfg.get("tick", 0.1)),
            }
            # We don't spawn a real sensor; we just push frames from the
            # tick() helper below.  Keep a list for parity with real SM.
            self._sensors.append(("rgb_camera", self._rgb_cfg))
            logger.success(
                f"📷 Mock RGB camera attached: {self._rgb_cfg['width']}x{self._rgb_cfg['height']} "
                f"@ {self._rgb_cfg['fov']}° tick={self._rgb_cfg['tick']}s"
            )

        if sensor_spec.get("collision", {}).get("enabled", False):
            self._collision_enabled = True
            logger.info("💥 Mock Collision sensor attached.")

        if sensor_spec.get("lane_invasion", {}).get("enabled", False):
            self._lane_enabled = True
            logger.info("🛣  Mock Lane-invasion sensor attached.")

        for stub in ("lidar", "imu", "gnss"):
            cfg = sensor_spec.get(stub, {})
            if cfg.get("enabled", False):
                logger.info(
                    f"Sensor '{stub}' is enabled but the mock adapter only "
                    f"returns an empty placeholder – integrate when Person 3 wires it."
                )

    # ------------------------------------------------------------ tick-time push
    def update_for_tick(self, frame_number: int, sim_time_s: float, actors: List[Any]) -> None:
        """Called by the runner once per simulation tick.

        Produces RGB frames according to ``tick`` cadence and injects rare
        synthetic collision/lane events so the risk engine is exercised.
        """
        # --- RGB ----------------------------------------------------------
        if self._rgb_cfg is not None and sim_time_s >= self._rgb_next_tick_at:
            W = self._rgb_cfg["width"]
            H = self._rgb_cfg["height"]
            frame_px, dets = self._render_scene(W, H, sim_time_s, actors)
            self.latest_rgb = frame_px
            self.latest_rgb_frame = frame_number
            self.latest_ground_truth_objects = dets
            if self.external_rgb_callback is not None:
                self.external_rgb_callback(frame_px)
            self._rgb_next_tick_at = sim_time_s + self._rgb_cfg["tick"]

        # --- Synthetic rare events --------------------------------------
        if self._collision_enabled and sim_time_s > self._collision_cooldown_until:
            if np.random.random() < 0.0015:  # ~0.15% / tick
                impulse_norm = 350.0 + np.random.random() * 200.0
                entry = {
                    "frame": frame_number,
                    "timestamp": sim_time_s,
                    "other_actor": "vehicle.audi.a2",
                    "impulse_norm": impulse_norm,
                }
                self.collision_events.append(entry)
                if self.external_collision_callback:
                    self.external_collision_callback(entry)
                self._collision_cooldown_until = sim_time_s + 15.0
                logger.warning(
                    f"💥 Mock collision @ frame {frame_number} (impulse={impulse_norm:.1f})"
                )

        if self._lane_enabled and sim_time_s > self._lane_cooldown_until:
            if np.random.random() < 0.006:  # ~0.6% / tick
                entry = {
                    "frame": frame_number,
                    "timestamp": sim_time_s,
                    "crossed_markings": ["Solid", "Broken"],
                }
                self.lane_invasions.append(entry)
                if self.external_lane_callback:
                    self.external_lane_callback(entry)
                self._lane_cooldown_until = sim_time_s + 4.0
                logger.info("🛣  Mock lane-invasion recorded.")

    # ------------------------------------------------------------ scene render
    def _render_scene(
        self, W: int, H: int, sim_time_s: float, actors: List[Any]
    ) -> tuple[np.ndarray, List[DetectedObject]]:
        """Produce a BGR uint8 frame ``(H, W, 3)`` + pydantic detections.

        The returned DetectedObject list uses the *same* projected NPC boxes
        that are drawn into the frame so the RiskEngine receives real,
        non-zero distance/closing-speed hazards even before Person 2
        integrates YOLOv8.

        Design:
          - top half: sky gradient (changes with weather preset if known)
          - bottom half: asphalt with dashed lane markings scrolling over time
          - draw up to 5 actors as coloured boxes in the "road plane"
        """
        frame = np.zeros((H, W, 3), dtype=np.uint8)

        # sky gradient: goes from BGR(sky_top) → BGR(sky_horizon) in top 55%
        sky_top = np.array([180, 140, 90], dtype=np.float32)
        sky_bot = np.array([220, 200, 170], dtype=np.float32)
        horizon_row = int(H * 0.45)
        for r in range(horizon_row):
            t = r / max(1, horizon_row - 1)
            colour = (sky_top * (1 - t) + sky_bot * t).astype(np.uint8)
            frame[r, :] = colour

        # asphalt below horizon + fading towards camera
        asphalt_top = np.array([60, 60, 60], dtype=np.uint8)
        asphalt_bot = np.array([20, 20, 20], dtype=np.uint8)
        for r in range(horizon_row, H):
            t = (r - horizon_row) / max(1, (H - horizon_row - 1))
            colour = (asphalt_top * (1 - t) + asphalt_bot * t).astype(np.uint8)
            frame[r, :] = colour

        # lane dashes – 3 perspective lanes, scrolling
        lane_col = np.array([255, 255, 255], dtype=np.uint8)
        scroll = (sim_time_s * 60.0) % 80.0  # scrolls dashes over time
        for lane_x_frac in (-0.33, 0.0, 0.33):
            base_x = int(W * (0.5 + lane_x_frac * 0.45))
            for r in range(horizon_row, H):
                depth = (r - horizon_row) / max(1, H - horizon_row)
                # Perspective: dashes get larger closer to camera
                dash_len = int(10 + 60 * depth)
                gap_len = int(8 + 40 * depth)
                period = dash_len + gap_len
                pos_in_period = (r + int(scroll * depth)) % period
                if pos_in_period < dash_len:
                    half_w = max(1, int(1 + 4 * depth))
                    x1 = max(0, base_x - half_w)
                    x2 = min(W - 1, base_x + half_w)
                    frame[r, x1:x2 + 1] = lane_col

        # Draw up to 5 coloured "car" rectangles representing NPCs in the
        # world, projected into the image via simple perspective mapping.
        # Ground truth boxes are computed simultaneously so the risk engine
        # gets real hazard inputs during mock-mode demos.
        palette = [
            (80, 80, 200),   # red
            (80, 200, 80),   # green
            (200, 140, 40),  # blue-ish
            (50, 200, 200),  # cyan
            (120, 80, 220),  # purple
        ]
        objects: List[DetectedObject] = []
        for idx, actor in enumerate(actors[:5]):
            # actor.transform (x,y) is world position relative to ego at ~origin
            wx = float(actor.transform.x) - 2.0  # small ego offset
            wy = float(actor.transform.y)
            # Distance down the road (pseudo-depth).  Used for depth-scale
            # and for the DetectedObject.distance field.
            z_depth = max(1.0, wx)
            if wx < 0:
                continue
            # Image x based on lateral position + z
            lateral_ratio = np.clip(wy / (2.5 * z_depth + 1e-6), -0.9, 0.9)
            px = int(W * (0.5 + lateral_ratio * 0.4))
            # Image y: near horizon when far, near bottom when close
            py = int(
                horizon_row
                + 0.05 * (H - horizon_row)
                + (1 - 1.0 / (1.0 + z_depth / 15.0)) * (0.9 * (H - horizon_row))
            )
            # box size grows as z shrinks
            scale = 1.0 / (1.0 + z_depth / 10.0)
            bw = max(6, int(70 * scale))
            bh = max(4, int(40 * scale))
            colour = palette[idx % len(palette)]
            x1 = max(0, px - bw // 2)
            y1 = max(horizon_row, py - bh)
            x2 = min(W - 1, x1 + bw)
            y2 = min(H - 1, y1 + bh)
            frame[y1:y2, x1:x2] = colour

            # --- Build the pydantic ground-truth detection ---------------
            npc_st = actor.state
            # relative speed: closing speed (negative = approaching)
            ego_st = getattr(self._client, "_ego_state_snapshot", None)
            ego_forward = ego_st.speed_kmh / 3.6 if ego_st is not None else 0.0
            npc_forward = npc_st.speed_kmh / 3.6
            rel_speed = npc_forward - ego_forward  # negative = approaching

            obj_type = "car"
            if "bicycle" in actor.type_id or "bh" in actor.type_id:
                obj_type = "bicycle"
            elif "walker" in actor.type_id:
                obj_type = "pedestrian"

            conf = 0.90 + 0.08 * float(1.0 / (1.0 + z_depth / 50.0))
            objects.append(
                DetectedObject(
                    object_id=f"npc_{actor.id:03d}",
                    object_type=obj_type,
                    confidence=float(min(0.99, conf)),
                    distance=float(z_depth),
                    relative_speed=float(rel_speed),
                    bbox=[float(x1), float(y1), float(x2), float(y2)],
                    timestamp=datetime.fromtimestamp(sim_time_s, tz=timezone.utc),
                )
            )

        # Ego hood at bottom (fixed strip) for a little visual context.
        hood_col = np.array([30, 30, 30], dtype=np.uint8)
        hood = int(H * 0.08)
        frame[-hood:, :] = frame[-hood:, :] // 3 + hood_col // 3 * 2

        return np.ascontiguousarray(frame), objects

    # ------------------------------------------------------------ drain helpers
    def drain_collision_events(self) -> List[Dict[str, Any]]:
        events, self.collision_events = self.collision_events, []
        return events

    def drain_lane_invasions(self) -> List[Dict[str, Any]]:
        items, self.lane_invasions = self.lane_invasions, []
        return items

    # ------------------------------------------------------------ cleanup
    def cleanup(self) -> None:
        self._sensors.clear()
