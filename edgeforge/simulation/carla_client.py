"""
CARLA synchronous-mode client wrapper.

Abstracts away raw ``carla.Client`` boilerplate so the rest of the
simulation layer can focus on scenario logic instead of low-level
bookkeeping.

Key responsibilities:
  * Connect with typed settings (no magic strings / hardcoded ports).
  * Enable deterministic synchronous mode with fixed timestep.
  * Centralised tick() + snapshot retrieval.
  * Safe cleanup (restores async mode on teardown).
"""

from __future__ import annotations

import atexit
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, List, Optional

if TYPE_CHECKING:
    import carla
else:
    try:
        import carla
    except ImportError:
        carla = None

from edgeforge.config import settings
from edgeforge.utils import get_logger

logger = get_logger(__name__)


@dataclass
class WorldSnapshot:
    """A thin wrapper around a ``carla.WorldSnapshot`` so upper layers
    don't need to import carla directly."""

    frame: int
    timestamp: float  # simulation seconds since epoch
    platform_timestamp: float  # wall-clock seconds


class CarlaClient:
    """Managed CARLA client with synchronous-mode lifecycle.

    Usage::

        client = CarlaClient()
        client.connect()
        try:
            client.set_synchronous_mode(True, fixed_delta_seconds=0.05)
            with client.tick_context():
                # ... per-frame work ...
                snap = client.snapshot
                ego_state = ego.get_velocity()  # etc.
        finally:
            client.disconnect()
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._host = host or settings.CARLA_HOST
        self._port = port or settings.CARLA_PORT
        self._timeout = timeout or settings.CARLA_TIMEOUT

        self._client: Optional[carla.Client] = None
        self._world: Optional[carla.World] = None
        self._map: Optional[carla.Map] = None
        self._blueprint_library: Optional[carla.BlueprintLibrary] = None
        self._traffic_manager: Optional[carla.TrafficManager] = None
        self._snapshot: Optional[carla.WorldSnapshot] = None

        self._sync_enabled: bool = False
        self._original_settings: Optional[carla.WorldSettings] = None
        self._actors: List[carla.Actor] = []

        atexit.register(self.disconnect)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Open the CARLA client connection and cache handles."""
        if carla is None:
            raise RuntimeError(
                "The CARLA Python API is not installed. Please install carla to connect to a CARLA server."
            )
        logger.info(f"Connecting to CARLA at {self._host}:{self._port} ...")
        self._client = carla.Client(self._host, self._port)
        self._client.set_timeout(self._timeout)

        self._world = self._client.get_world()
        self._map = self._world.get_map()
        self._blueprint_library = self._world.get_blueprint_library()
        self._traffic_manager = self._client.get_trafficmanager(8000)
        self._traffic_manager.set_global_distance_to_leading_vehicle(2.5)

        # Grab the *original* world settings so we can restore them on
        # disconnect (polite behaviour so subsequent scripts don't find
        # the simulator stuck in synchronous mode).
        self._original_settings = self._world.get_settings()
        self._sync_enabled = self._original_settings.synchronous_mode

        logger.success(
            f"✅ Connected. Map={self._map.name}, "
            f"sync_mode={self._sync_enabled}, "
            f"spawn_points={len(self._map.get_spawn_points())}"
        )

    def disconnect(self) -> None:
        """Restore original world settings and drop the connection."""
        if self._world is not None and self._original_settings is not None:
            try:
                self.set_synchronous_mode(False)
                self._world.apply_settings(self._original_settings)
                logger.debug("Restored original CARLA world settings.")
            except Exception as exc:  # pragma: no cover - best effort
                logger.warning(f"Could not restore world settings: {exc}")

        self.destroy_all_actors()
        self._client = None
        self._world = None
        self._map = None
        self._blueprint_library = None
        self._traffic_manager = None
        self._snapshot = None

    # ------------------------------------------------------------------
    # Core handles (fail loudly if not connected)
    # ------------------------------------------------------------------
    @property
    def raw_client(self) -> carla.Client:
        if self._client is None:
            raise RuntimeError("CarlaClient is not connected — call connect() first.")
        return self._client

    @property
    def world(self) -> carla.World:
        if self._world is None:
            raise RuntimeError("CarlaClient is not connected — call connect() first.")
        return self._world

    @property
    def map(self) -> carla.Map:
        if self._map is None:
            raise RuntimeError("CarlaClient is not connected — call connect() first.")
        return self._map

    @property
    def blueprint_library(self) -> carla.BlueprintLibrary:
        if self._blueprint_library is None:
            raise RuntimeError("CarlaClient is not connected — call connect() first.")
        return self._blueprint_library

    @property
    def traffic_manager(self) -> carla.TrafficManager:
        if self._traffic_manager is None:
            raise RuntimeError("CarlaClient is not connected — call connect() first.")
        return self._traffic_manager

    @property
    def snapshot(self) -> WorldSnapshot:
        """Last snapshot captured during tick()."""
        if self._snapshot is None:
            raise RuntimeError("No snapshot yet — call tick() first.")
        s = self._snapshot
        return WorldSnapshot(
            frame=s.frame,
            timestamp=s.timestamp.elapsed_seconds,
            platform_timestamp=s.timestamp.platform_timestamp,
        )

    # ------------------------------------------------------------------
    # Synchronous mode
    # ------------------------------------------------------------------
    def set_synchronous_mode(
        self,
        enabled: bool,
        fixed_delta_seconds: float = 0.05,
    ) -> None:
        """Toggle synchronous mode.

        When enabled the simulator *waits* for ``tick()`` before
        advancing the world, which guarantees determinism and makes
        sensor callbacks line up with the logic-frame timestamps.
        """
        ws = self.world.get_settings()
        ws.synchronous_mode = enabled
        if enabled:
            ws.fixed_delta_seconds = fixed_delta_seconds
            self.traffic_manager.set_synchronous_mode(True)
        else:
            self.traffic_manager.set_synchronous_mode(False)
        self.world.apply_settings(ws)
        self._sync_enabled = enabled
        logger.info(
            f"CARLA synchronous mode {'ENABLED' if enabled else 'DISABLED'} "
            f"(delta={fixed_delta_seconds if enabled else 'variable'}s)"
        )

    def tick(self) -> WorldSnapshot:
        """Advance the simulator by exactly one frame.

        Returns the ``WorldSnapshot`` for the new frame.  In async mode
        this returns the most recent snapshot without blocking.
        """
        if self._sync_enabled:
            frame = self.world.tick()
            self._snapshot = self.world.get_snapshot()
            assert self._snapshot.frame == frame, (
                "CARLA tick frame / snapshot frame mismatch – this should not happen."
            )
        else:
            self._snapshot = self.world.wait_for_tick()
        return self.snapshot

    def tick_context(self) -> "_TickContext":
        """Context-manager alias for ``tick()`` + teardown safety."""
        return _TickContext(self)

    # ------------------------------------------------------------------
    # Actor registry (so cleanup is one call)
    # ------------------------------------------------------------------
    def register_actor(self, actor: carla.Actor) -> carla.Actor:
        """Track an actor so it gets destroyed on disconnect()."""
        self._actors.append(actor)
        return actor

    def destroy_all_actors(self) -> None:
        """Destroy every actor tracked by this client."""
        if not self._actors:
            return
        logger.info(f"🧹 Destroying {len(self._actors)} simulation actors ...")
        for actor in reversed(self._actors):
            if actor is not None and actor.is_alive:
                try:
                    stop_fn = getattr(actor, "stop", None)
                    if callable(stop_fn):
                        stop_fn()
                    actor.destroy()
                except Exception as exc:  # pragma: no cover
                    logger.warning(f"Failed to destroy {actor.type_id}: {exc}")
        self._actors.clear()

    # ------------------------------------------------------------------
    # Weather
    # ------------------------------------------------------------------
    def set_weather_preset(self, name: str) -> None:
        """Apply a weather preset by name (case-insensitive).

        Valid names correspond to ``carla.WeatherParameters`` attributes,
        e.g. ``"ClearNoon"``, ``"HardRainSunset"``, ``"WetNight"`` etc.
        """
        if carla is None:
            raise RuntimeError("The CARLA Python API is required to set weather presets.")
        wp_attr = getattr(carla.WeatherParameters, name, None)
        if wp_attr is None:
            raise ValueError(
                f"Unknown weather preset '{name}'. Use any attribute of "
                "carla.WeatherParameters (e.g. ClearNoon, CloudySunset, ...)."
            )
        self.world.set_weather(wp_attr)
        logger.info(f"🌦  Weather preset applied: {name}")

    def set_weather(
        self,
        weather: Any,
        preset_base: str = "ClearNoon",
    ) -> None:
        """Apply either a weather preset name, WeatherParameters, or dictionary of fine-grained values.

        Supports applying fine-grained continuous values (e.g. fog_density,
        precipitation, cloudiness, sun_altitude_angle) on top of an optional
        base preset.
        """
        if carla is None:
            raise RuntimeError("The CARLA Python API is required to set weather.")
        if isinstance(weather, str):
            self.set_weather_preset(weather)
            return
        if hasattr(carla, "WeatherParameters") and isinstance(weather, carla.WeatherParameters):
            self.world.set_weather(weather)
            logger.info("🌦  CARLA WeatherParameters applied directly.")
            return
        if isinstance(weather, dict):
            base_name = weather.get("preset", preset_base)
            wp = getattr(carla.WeatherParameters, base_name, None)
            if wp is None:
                wp = carla.WeatherParameters()
            else:
                wp = carla.WeatherParameters(
                    cloudiness=getattr(wp, "cloudiness", 0.0),
                    precipitation=getattr(wp, "precipitation", 0.0),
                    precipitation_deposits=getattr(wp, "precipitation_deposits", 0.0),
                    wind_intensity=getattr(wp, "wind_intensity", 0.0),
                    sun_azimuth_angle=getattr(wp, "sun_azimuth_angle", 0.0),
                    sun_altitude_angle=getattr(wp, "sun_altitude_angle", 60.0),
                    fog_density=getattr(wp, "fog_density", 0.0),
                    fog_distance=getattr(wp, "fog_distance", 0.0),
                    wetness=getattr(wp, "wetness", 0.0),
                )
            for k, v in weather.items():
                if hasattr(wp, k) and isinstance(v, (int, float)):
                    setattr(wp, k, float(v))
            self.world.set_weather(wp)
            logger.info(f"🌦  Fine-grained weather applied (base: {base_name}): {weather}")
            return
        raise TypeError(f"Unsupported weather specification: {type(weather)}")

    # ------------------------------------------------------------------
    # Map switching
    # ------------------------------------------------------------------
    def load_map(self, map_name: str, layer: Optional[Any] = None) -> None:
        """Load a different CARLA map (blocking).

        ``map_name`` should be a simple name like ``"Town03"`` – this
        method will reload the world and refresh cached handles.
        """
        if carla is None:
            raise RuntimeError("The CARLA Python API is required to load maps.")
        if self._map is not None:
            current_clean = self._map.name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            target_clean = map_name.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            if current_clean == target_clean:
                logger.info(
                    f"🗺  CARLA is already on map '{self._map.name}'; skipping redundant load."
                )
                return
        logger.info(f"🗺  Requesting map load: {map_name}")
        if layer is not None:
            self.raw_client.load_world(map_name, layer)
        else:
            self.raw_client.load_world(map_name)
        # load_world returns immediately; wait for the server to come back.
        self._world = self.raw_client.get_world()
        self._map = self._world.get_map()
        self._blueprint_library = self._world.get_blueprint_library()
        # Reset original settings capture so disconnect() restores the
        # newly-loaded world's default settings.
        self._original_settings = self._world.get_settings()
        self._sync_enabled = self._original_settings.synchronous_mode
        logger.success(f"🗺  Map loaded: {self._map.name}")


class _TickContext:
    """Lightweight context manager wrapping a single tick."""

    def __init__(self, client: CarlaClient) -> None:
        self._client = client

    def __enter__(self) -> WorldSnapshot:
        return self._client.tick()

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None
