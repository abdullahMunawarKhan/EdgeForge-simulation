"""
End-to-end scenario runner for EdgeForge.

Loads a JSON scenario description (see ``scenarios/configs/default_scenario.json``)
and drives the CARLA simulator through it in deterministic synchronous mode.

The core public API is intentionally minimal:

    runner = ScenarioRunner.from_config("path/to/scenario.json")
    with runner.run() as stream:
        for sensor_frame in stream:
            # sensor_frame.rgb, sensor_frame.vehicle_state, ...
            # -> hand off to perception / risk pipeline

Alternatively, if you just want a one-shot scenario execution with a
callable per-frame hook and a self-contained lifecycle:

    ScenarioRunner.run_config("path/to/scenario.json", on_frame=my_hook)
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Union

import numpy as np

# ---------------------------------------------------------------------------
# Allow this script to be run directly as ``python scenario_runner.py``
# without installing the edgeforge package.
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_GRANDPARENT = _THIS_DIR.parent.parent
if str(_GRANDPARENT) not in sys.path:
    sys.path.insert(0, str(_GRANDPARENT))

from edgeforge.simulation.actor_manager import ActorManager, EgoBundle, TrafficBundle
from edgeforge.simulation.carla_client import CarlaClient, WorldSnapshot
from edgeforge.simulation.mock_client import MockCarlaClient
from edgeforge.simulation.mock_actor_manager import (
    MockActorManager,
    EgoBundle as MockEgoBundle,
    TrafficBundle as MockTrafficBundle,
)
from edgeforge.simulation.mock_sensor_manager import (
    MockSensorManager,
    SensorFrame as MockSensorFrame,
    vehicle_to_state as mock_vehicle_to_state,
)
from edgeforge.simulation.sensor_manager import SensorFrame, SensorManager, vehicle_to_state
from edgeforge.utils import get_logger

logger = get_logger(__name__)


StrPath = Union[str, Path]

# Sensors need a few extra ticks after actor spawn before callbacks start
# firing data.  Account for that in the warmup phase below.
_SPAWN_WARMUP_TICKS = 10

# Accepted backend tokens.
BACKEND_CARLA = "carla"
BACKEND_MOCK = "mock"
BACKEND_DETECT = "detect"
_BACKENDS = (BACKEND_CARLA, BACKEND_MOCK, BACKEND_DETECT)


@dataclass
class ScenarioInfo:
    """Bookkeeping info about the currently loaded scenario."""

    name: str
    description: str
    version: str
    duration_seconds: float
    weather_preset: str
    map_name: Optional[str]
    backend: str = BACKEND_CARLA
    fine_weather: Optional[Dict[str, float]] = None


def _parse_backend(cfg: Dict[str, Any], override: Optional[str]) -> str:
    """Resolve which simulation backend to use.

    Precedence:
      1. explicit ``override`` argument (used by CLI --backend / --mock)
      2. cfg["simulation"]["backend"] if present
      3. ``detect`` -> try CARLA then fall back to mock with a warning
    """
    if override is not None:
        if override not in _BACKENDS:
            raise ValueError(f"Unknown backend '{override}'. Must be one of {_BACKENDS}.")
        return override
    sim_cfg = cfg.get("simulation") or {}
    cfg_backend = sim_cfg.get("backend")
    if cfg_backend is not None:
        if cfg_backend not in _BACKENDS:
            raise ValueError(
                f"Unknown simulation.backend '{cfg_backend}'. Must be one of {_BACKENDS}."
            )
        return cfg_backend
    return BACKEND_DETECT


def _advance_mock_actors(client: MockCarlaClient, dt: float) -> None:
    """Update every living mock actor's kinematics each tick.

    Ego: cruise on a straight-ish path + sinusoidal lateral wiggle so the
    VehicleState has non-trivial speed / acceleration / lane drift.

    NPC vehicles: follow their own lane at desired_speed_kmh + minor yaw
    oscillation so their projected boxes move in the mock image.

    Pedestrians: small random walks.
    """
    # Access the living actor registry directly (friend module).
    actors = list(client._actors.values())  # noqa: SLF001
    for a in actors:
        if not a.alive:
            continue
        a_type = a.type_id or ""
        st = a.state
        # ---- Decide desired speed -----------------------------------------
        desired_kmh = float(a.attributes.get("desired_speed_kmh", 0.0))
        autopilot = bool(a.attributes.get("autopilot", False))
        if autopilot and (st.speed_kmh < 2.0):
            # Smoothly spin up from standstill on tick 0.
            desired_kmh = max(desired_kmh, 30.0)
        target_ms = desired_kmh / 3.6

        accel_target = (target_ms - st.speed_kmh / 3.6) / max(dt, 0.3)
        accel_target = max(-3.0, min(3.0, accel_target))
        st.ax = accel_target
        st.ay = 0.0
        st.az = 0.0
        # integrate velocity (saturate with target + small noise)
        yaw_rad = __import__("math").radians(float(getattr(a.transform, "yaw", 0.0)))
        cos_y = __import__("math").cos(yaw_rad)
        sin_y = __import__("math").sin(yaw_rad)
        # new forward speed
        forward_speed = st.vx * cos_y + st.vy * sin_y
        new_forward_speed = forward_speed + accel_target * dt
        if "walker" in a_type:
            # walkers: walk ~1.2 m/s
            new_forward_speed = max(0.0, min(1.4, target_ms or 1.2))
        elif "bicycle" in a_type or "bh" in a_type:
            new_forward_speed = max(0.0, min(8.0, target_ms or 5.0))
        else:
            new_forward_speed = max(0.0, new_forward_speed)
        st.vx = new_forward_speed * cos_y
        st.vy = new_forward_speed * sin_y
        st.vz = 0.0
        st.speed_kmh = new_forward_speed * 3.6
        st.throttle = max(0.0, min(1.0, accel_target / 2.5))
        st.brake = max(0.0, min(1.0, -accel_target / 2.5))
        st.gear = max(1, min(6, int(1 + st.speed_kmh // 25)))
        st.rpm = 900.0 + st.speed_kmh * 22.0
        # ---- Integrate position ------------------------------------------
        a.transform.x += st.vx * dt
        a.transform.y += st.vy * dt
        # ---- Yaw oscillation for non-ego vehicles ------------------------
        if "walker" not in a_type:
            t = (client._elapsed_s or 0.0)  # noqa: SLF001
            period = 9.0 if ("sensor" not in a_type and "walker" not in a_type) else 0.0
            if period > 0:
                amp = 2.5 if a.attributes.get("is_ego", False) else 3.5
                a.transform.yaw = amp * __import__("math").sin((2 * 3.14159 / period) * t)
                if a.attributes.get("is_ego", False):
                    # ego lateral wiggle via yaw is small – we'll nudge vy directly
                    a.transform.yaw *= 0.25
    # Ego is the first vehicle spawned (lowest id with vehicle.*).  Add a
    # tiny lateral drift so lane-invasion events are plausible even with
    # the mock lane sensor.
    ego_candidate = next(
        (a for a in actors if "vehicle" in (a.type_id or "") and a.attributes.get("is_ego")),
        None,
    )
    if ego_candidate is not None:
        ego_candidate.transform.y += 0.02 * __import__("math").sin(
            0.25 * (client._elapsed_s or 0.0)  # noqa: SLF001
        )
    # Publish ego state snapshot so MockSensorManager can compute
    # relative closing speeds for each NPC detection.
    ego_state = None
    if ego_candidate is not None:
        ego_state = ego_candidate.state
    # Use setattr so static analysers don't flag a missing attribute on MockCarlaClient
    # (the attribute is declared in MockCarlaClient.__init__ for safety).
    setattr(client, "_ego_state_snapshot", ego_state)  # noqa: SLF001


class ScenarioRunner:
    """Managed, deterministic CARLA (or mock) scenario session.

    Selects a backend via ``backend=<kwarg>`` / ``cfg["simulation"]["backend"]``:

    * ``"carla"``  — real CARLA server via CarlaClient + ActorManager + SensorManager
    * ``"mock"``   — pure-Python synthetic simulation (no server required)
    * ``"detect"`` — try CARLA; on connection failure, fall back to mock (default)
    """

    def __init__(
        self,
        config: Dict[str, Any],
        client: Optional[Any] = None,
        backend: Optional[str] = None,
    ) -> None:
        self._cfg = config
        backend_cfg = _parse_backend(config, backend)

        # ----- backend resolution (detect → try carla, fall back to mock) -----
        if backend_cfg == BACKEND_DETECT:
            if client is None:
                try_carla_client = CarlaClient()
                try:
                    try_carla_client.connect()
                    self._backend = BACKEND_CARLA
                    client = try_carla_client
                except Exception as exc:
                    logger.warning(
                        f"⚠️  Backend=detect: couldn't connect to CARLA server ({exc}); "
                        "falling back to mock synthetic simulation."
                    )
                    self._backend = BACKEND_MOCK
            else:
                self._backend = (
                    BACKEND_MOCK if isinstance(client, MockCarlaClient) else BACKEND_CARLA
                )
        else:
            self._backend = backend_cfg

        # Parse weather: preserve both preset and fine-grained continuous values
        weather_raw = config.get("weather", "ClearNoon")
        fine_weather: Optional[Dict[str, float]] = None
        if isinstance(weather_raw, dict):
            fine_weather = {k: float(v) for k, v in weather_raw.items() if isinstance(v, (int, float))}
            weather_preset = str(weather_raw.get("preset", "ClearNoon"))
        else:
            weather_preset = str(weather_raw)

        # Check for fine_weather in root or generated_metadata
        if "fine_weather" in config and isinstance(config["fine_weather"], dict):
            fine_weather = {k: float(v) for k, v in config["fine_weather"].items() if isinstance(v, (int, float))}
        elif "generated_metadata" in config and isinstance(config["generated_metadata"], dict):
            gen_fine = config["generated_metadata"].get("fine_weather")
            if isinstance(gen_fine, dict):
                fine_weather = {k: float(v) for k, v in gen_fine.items() if isinstance(v, (int, float))}

        self._info = ScenarioInfo(
            name=str(config.get("name", "unnamed_scenario")),
            description=str(config.get("description", "")),
            version=str(config.get("version", "1.0")),
            duration_seconds=float(config.get("duration_seconds", 60.0)),
            weather_preset=weather_preset,
            fine_weather=fine_weather,
            map_name=config.get("map"),
            backend=self._backend,
        )

        if self._backend == BACKEND_MOCK:
            self._client: Any = client or MockCarlaClient()
            self._actor_mgr = MockActorManager(self._client)
            self._sensor_mgr = MockSensorManager(self._client)
            self._vehicle_to_state_fn = mock_vehicle_to_state
        else:
            self._client = client or CarlaClient()
            self._actor_mgr = ActorManager(self._client)
            self._sensor_mgr = SensorManager(self._client)
            self._vehicle_to_state_fn = vehicle_to_state

        self._ego_bundle: Optional[Any] = None
        self._traffic_bundle: Optional[Any] = None
        self._started: bool = False

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, path: StrPath, backend: Optional[str] = None) -> "ScenarioRunner":
        """Build a runner from a JSON scenario file on disk.

        ``backend`` overrides ``cfg["simulation"]["backend"]`` if given.
        """
        cfg = cls._load_json(path)
        logger.info(f"📄 Scenario loaded: {Path(path).name} -> {cfg.get('name')}")
        return cls(cfg, backend=backend)

    @classmethod
    def run_config(
        cls,
        path: StrPath,
        on_frame: Optional[Callable[[SensorFrame], None]] = None,
        backend: Optional[str] = None,
    ) -> None:
        """Convenience entrypoint: load + run a scenario with a frame hook."""
        runner = cls.from_config(path, backend=backend)
        with runner.run() as stream:
            for frame in stream:
                if on_frame is not None:
                    on_frame(frame)

    @staticmethod
    def _load_json(path: StrPath) -> Dict[str, Any]:
        p = Path(path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"Scenario config not found: {p}")
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------
    @property
    def info(self) -> ScenarioInfo:
        return self._info

    @property
    def client(self) -> Any:
        return self._client

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def latest_mock_ground_truth_detections(self) -> List[Any]:
        """Synthetic ground-truth detections (only populated in mock mode).

        Returns the exact same projected NPC boxes that the mock RGB renderer
        draws into the frame, expressed as pydantic ``DetectedObject``.
        Used by the pipeline for mock demos so the RiskEngine produces real
        MEDIUM / HIGH risk levels before Person 2 wires YOLO.
        """
        if self._backend != BACKEND_MOCK:
            return []
        return list(getattr(self._sensor_mgr, "latest_ground_truth_objects", []) or [])

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Connect backend, build actors + sensors, warm up sensors."""
        if self._started:
            return
        self._print_header()

        if self._backend == BACKEND_MOCK:
            self._client.connect()
            if self._info.map_name:
                self._client.load_map(self._info.map_name)
            # Mock "synchronous mode" is always active via fixed dt.
            self._client.apply_settings(type("S", (), {
                "synchronous_mode": True,
                "fixed_delta_seconds": 0.05,
            })())
            if self._info.fine_weather:
                # Pass fine-grained values as-is; preset_base provides the
                # base palette without polluting the Dict[str, float] with a str.
                self._client.set_weather(
                    dict(self._info.fine_weather),
                    preset_base=self._info.weather_preset,
                )
            else:
                self._client.set_weather(self._info.weather_preset)
            # --- Ego + traffic ------------------------------------------------
            self._ego_bundle = self._actor_mgr.spawn_ego(self._cfg.get("ego_vehicle", {}))
            # Mark ego so kinematics can find it easily.
            self._ego_bundle.vehicle.attributes["is_ego"] = True
            self._traffic_bundle = self._actor_mgr.spawn_traffic(self._cfg.get("traffic", {}))
            # --- Sensors ------------------------------------------------------
            self._sensor_mgr.build_suite(
                self._ego_bundle.vehicle,
                self._cfg.get("sensors", {}),
            )
            logger.info(f"⏳ Spawn warmup ({_SPAWN_WARMUP_TICKS} ticks) ...")
            for _ in range(_SPAWN_WARMUP_TICKS):
                _advance_mock_actors(self._client, 0.05)
                self._client.tick()
                _warmup_snap = self._client.get_snapshot()
                npc_list = [
                    a for a in self._client._actors.values()  # noqa: SLF001
                    if a.alive and a.id != self._ego_bundle.vehicle.id and "vehicle" in a.type_id
                ]
                self._sensor_mgr.update_for_tick(
                    _warmup_snap.frame,
                    _warmup_snap.timestamp.elapsed_seconds,
                    npc_list,
                )
        else:
            self._client.connect()
            if self._info.map_name:
                current = self._client.map.name.rsplit("/", 1)[-1]
                if self._info.map_name != current:
                    self._client.load_map(self._info.map_name)

            self._client.set_synchronous_mode(True, fixed_delta_seconds=0.05)
            if hasattr(self._client, "set_weather"):
                if self._info.fine_weather:
                    self._client.set_weather(self._info.fine_weather, preset_base=self._info.weather_preset)
                else:
                    self._client.set_weather(self._info.weather_preset)
            else:
                self._client.set_weather_preset(self._info.weather_preset)

            # --- Ego + traffic ------------------------------------------------
            self._ego_bundle = self._actor_mgr.spawn_ego(self._cfg.get("ego_vehicle", {}))
            self._traffic_bundle = self._actor_mgr.spawn_traffic(self._cfg.get("traffic", {}))

            # --- Sensors ------------------------------------------------------
            self._sensor_mgr.build_suite(
                self._ego_bundle.vehicle,
                self._cfg.get("sensors", {}),
            )

            # --- Warmup: let sensors catch up --------------------------------
            logger.info(f"⏳ Spawn warmup ({_SPAWN_WARMUP_TICKS} ticks) ...")
            for _ in range(_SPAWN_WARMUP_TICKS):
                self._client.tick()
                time.sleep(0.005)

        self._started = True
        logger.success("🚀 Scenario ready.")

    def stop(self) -> None:
        """Tear down everything the runner set up (idempotent)."""
        try:
            if self._actor_mgr is not None and hasattr(self._actor_mgr, "stop_traffic"):
                self._actor_mgr.stop_traffic()
        finally:
            try:
                if self._sensor_mgr is not None and hasattr(self._sensor_mgr, "cleanup"):
                    self._sensor_mgr.cleanup()
            finally:
                try:
                    self._client.disconnect()
                except Exception:
                    pass
                self._started = False
        logger.info("🛑 Scenario torn down.")

    def _print_header(self) -> None:
        info = self._info
        border = "=" * 64
        print()
        print(border)
        print(f"  SCENARIO:  {info.name}  (v{info.version})")
        if info.description:
            print(f"  {info.description}")
        print(border)
        print(f"  Duration: {info.duration_seconds:.0f}s")
        weather_desc = info.weather_preset
        if info.fine_weather:
            weather_desc += f" (fine-grained: {info.fine_weather})"
        print(f"  Weather:  {weather_desc}")
        print(f"  Map:      {info.map_name or '<current>'}")
        print(border)
        print()

    # ------------------------------------------------------------------
    # Context-managed run (primary public API)
    # ------------------------------------------------------------------
    @contextmanager
    def run(self) -> Iterator[Iterator[SensorFrame]]:
        """``with runner.run() as frames: for sf in frames: ...``

        Yields an iterator of ``SensorFrame`` — one per simulated tick.
        The iterator stops after ``duration_seconds`` of simulation time
        has elapsed.  Cleanup (actors/sensors/world settings) happens
        automatically on context exit.
        """
        self.start()
        try:
            yield self._frame_stream()
        finally:
            self.stop()

    def _frame_stream(self) -> Iterator[SensorFrame]:
        """Generator: one ``SensorFrame`` per simulation tick."""
        assert self._ego_bundle is not None, "start() must be called first."
        ego = self._ego_bundle.vehicle
        duration = self._info.duration_seconds

        start_sim_time: Optional[float] = None
        last_wall = time.time()

        while True:
            if self._backend == BACKEND_MOCK:
                # 1) Advance mock kinematics 2) tick (advances frame counter)
                # 3) Push sensor frame generation
                _advance_mock_actors(self._client, 0.05)
                self._client.tick()  # frame++, elapsed_s += dt
                _snap = self._client.get_snapshot()
                frame_number = _snap.frame
                timestamp_s = float(_snap.timestamp.elapsed_seconds)
                npc_list = [
                    a for a in self._client._actors.values()  # noqa: SLF001
                    if a.alive and a.id != ego.id and "vehicle" in a.type_id
                ]
                self._sensor_mgr.update_for_tick(frame_number, timestamp_s, npc_list)
            else:
                snap: WorldSnapshot = self._client.tick()
                frame_number = snap.frame
                timestamp_s = snap.timestamp

            if start_sim_time is None:
                start_sim_time = timestamp_s

            elapsed_sim = timestamp_s - start_sim_time
            if duration > 0 and elapsed_sim >= duration:
                logger.info(f"⌛ Scenario duration reached ({duration:.0f}s sim time).")
                break

            vs = self._vehicle_to_state_fn(
                ego, vehicle_id=self._ego_bundle.model_id, sim_elapsed=timestamp_s
            )
            collisions = self._sensor_mgr.drain_collision_events()
            lane_inv = self._sensor_mgr.drain_lane_invasions()

            yield SensorFrame(
                timestamp=timestamp_s,
                frame_number=frame_number,
                rgb=self._sensor_mgr.latest_rgb,
                vehicle_state=vs,
                collision_events=collisions,
                lane_invasions=lane_inv,
                camera_views=self._sensor_mgr.get_synchronized_rgb_views(frame_number),
            )

            # Rough wall-clock throttling (UX only – determinism doesn't depend on this).
            now = time.time()
            dt_desired = 0.05 - 0.002
            sleep_for = max(0.0, dt_desired - (now - last_wall))
            if sleep_for > 0:
                time.sleep(sleep_for)
            last_wall = now


# ---------------------------------------------------------------------------
# Standalone CLI (for direct testing of Simulation Lead deliverables)
# ---------------------------------------------------------------------------
def _cli_main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Run an EdgeForge CARLA scenario.")
    parser.add_argument(
        "config",
        nargs="?",
        default=str(
            Path(__file__).resolve().parent.parent
            / "scenarios"
            / "configs"
            / "default_scenario.json"
        ),
        help="Path to the scenario JSON file.",
    )
    parser.add_argument(
        "--backend",
        choices=list(_BACKENDS),
        default=BACKEND_DETECT,
        help=f"Simulation backend to use (default: {BACKEND_DETECT}).",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Shortcut: --backend=mock.  Forces synthetic simulation mode.",
    )
    parser.add_argument(
        "--no-display",
        action="store_true",
        help="Don't open an OpenCV window (headless runs / CI).",
    )
    args = parser.parse_args()

    backend = BACKEND_MOCK if args.mock else args.backend

    import cv2  # local – CV2 is optional for pure-simulation runs

    window_open = not args.no_display

    def on_frame(frame: SensorFrame) -> None:
        nonlocal window_open
        if not window_open:
            return
        if frame.rgb is None:
            return
        display = frame.rgb.copy()
        vs = frame.vehicle_state
        if vs is not None:
            kmh = vs.speed * 3.6
            label = f"{kmh:.0f} km/h  |  risk-TODO"
            cv2.putText(
                display,
                label,
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
        cv2.imshow("EdgeForge — Ego View", display)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            window_open = False

    try:
        ScenarioRunner.run_config(args.config, on_frame=on_frame, backend=backend)
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130
    finally:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(_cli_main())
