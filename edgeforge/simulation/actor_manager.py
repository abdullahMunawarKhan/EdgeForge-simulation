"""
Actor spawning and TrafficManager orchestration.

Responsibilities:
  * Spawn the ego vehicle from a scenario config (explicit model +
    spawn-point index, with a fallback to first available point).
  * Populate the world with NPC vehicles, pedestrians, and bicycles
    via CARLA's built-in TrafficManager so scenario traffic scales
    declaratively (``default_scenario.json`` → ``traffic`` key).
  * Track all actor handles for clean teardown.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import carla

from edgeforge.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Typed result bundles (so callers don't need to juggle raw lists)
# ---------------------------------------------------------------------------
@dataclass
class EgoBundle:
    """Everything the scenario runner needs to operate the ego vehicle."""

    vehicle: carla.Vehicle
    model_id: str
    spawn_index: int


@dataclass
class TrafficBundle:
    """All background traffic registered with the TrafficManager."""

    vehicles: List[carla.Vehicle]
    pedestrians: List[carla.Actor]
    walkers_controllers: List[carla.Actor]
    bicycles: List[carla.Vehicle]

    @property
    def total(self) -> int:
        return len(self.vehicles) + len(self.pedestrians) + len(self.bicycles)


class ActorManager:
    """Centralised actor factory – all spawning goes through here."""

    def __init__(self, client: "CarlaClient") -> None:  # type: ignore[name-defined]
        self._client = client
        self._ego: Optional[carla.Vehicle] = None
        self._traffic: Optional[TrafficBundle] = None
        # Pedestrian spawn helpers require a persistent batch of transform
        # samples so walker AI can pick destinations deterministically.
        self._rng = random.Random(42)

    # ------------------------------------------------------------------
    # Ego vehicle
    # ------------------------------------------------------------------
    def spawn_ego(self, cfg: Dict[str, Any]) -> EgoBundle:
        """Spawn the principal (ego) vehicle according to ``cfg``.

        ``cfg`` keys (all optional, with sensible defaults):
          * ``model``          -- CARLA blueprint id, e.g. "vehicle.tesla.model3"
          * ``spawn_point_index`` -- integer index into map spawn points
          * ``speed_limit``    -- km/h; only advisory, used for autopilot hint
          * ``autopilot``      -- bool; enable TrafficManager autopilot
        """
        world = self._client.world
        bp_lib = self._client.blueprint_library
        spawn_points = self._client.map.get_spawn_points()

        if not spawn_points:
            raise RuntimeError("Current CARLA map has no spawn points.")

        # --- Resolve blueprint ------------------------------------------------
        model_id = cfg.get("model", "vehicle.tesla.model3")
        bps = bp_lib.filter(model_id)
        if not bps:
            logger.warning(
                f"Vehicle '{model_id}' not found in blueprint library; "
                f"falling back to a random passenger car."
            )
            bps = bp_lib.filter("vehicle.*")
        bp = self._rng.choice(list(bps))

        # --- Resolve spawn point ---------------------------------------------
        idx = int(cfg.get("spawn_point_index", 0))
        if idx < 0 or idx >= len(spawn_points):
            logger.warning(
                f"spawn_point_index={idx} out of range (0..{len(spawn_points)-1}); "
                f"using index 0."
            )
            idx = 0

        transform = spawn_points[idx]
        vehicle: Optional[carla.Vehicle] = world.try_spawn_actor(bp, transform)

        if vehicle is None:
            # Location occupied – scan for first free spawn point.
            for fallback_idx, fallback_tf in enumerate(spawn_points):
                vehicle = world.try_spawn_actor(bp, fallback_tf)
                if vehicle is not None:
                    idx = fallback_idx
                    logger.info(
                        f"Requested spawn {idx} blocked; used spawn #{fallback_idx}."
                    )
                    break
        if vehicle is None:
            raise RuntimeError(
                "Could not find a free spawn point for the ego vehicle."
            )

        self._client.register_actor(vehicle)
        self._ego = vehicle

        # --- Optional autopilot ----------------------------------------------
        if cfg.get("autopilot", False):
            tm = self._client.traffic_manager
            vehicle.set_autopilot(True, tm.get_port())
            speed_limit_kmh = float(cfg.get("speed_limit", 50))
            tm.set_desired_speed(vehicle, speed_limit_kmh)
            tm.ignore_lights_percentage(vehicle, 0.0)
            logger.info(f"🚗 Ego autopilot ON, desired speed {speed_limit_kmh:.0f} km/h")

        logger.success(
            f"🚗 Ego vehicle spawned: {vehicle.type_id} @ spawn #{idx}"
        )
        return EgoBundle(vehicle=vehicle, model_id=vehicle.type_id, spawn_index=idx)

    # ------------------------------------------------------------------
    # NPC traffic (vehicles / bicycles / pedestrians)
    # ------------------------------------------------------------------
    def spawn_traffic(self, cfg: Dict[str, Any]) -> TrafficBundle:
        """Spawn background traffic according to the ``traffic`` cfg block."""

        n_vehicles = int(cfg.get("vehicles", 0))
        n_pedestrians = int(cfg.get("pedestrians", 0))
        n_bicycles = int(cfg.get("bicycles", 0))

        vehicles = self._spawn_n_vehicles(n_vehicles, filter_pattern="vehicle.*")
        bicycles = self._spawn_n_vehicles(
            n_bicycles, filter_pattern="vehicle.bh.* bicycle.*", kind="bicycle"
        )
        peds, controllers = self._spawn_n_pedestrians(n_pedestrians)

        bundle = TrafficBundle(
            vehicles=vehicles,
            pedestrians=peds,
            walkers_controllers=controllers,
            bicycles=bicycles,
        )
        self._traffic = bundle

        logger.success(
            f"🚦 Traffic spawned: {bundle.total} total "
            f"(vehicles={len(vehicles)}, bikes={len(bicycles)}, peds={len(peds)})"
        )
        return bundle

    # ---- Vehicles (motorised + bicycles) ----------------------------------
    def _spawn_n_vehicles(
        self,
        count: int,
        filter_pattern: str = "vehicle.*",
        kind: str = "vehicle",
    ) -> List[carla.Vehicle]:
        if count <= 0:
            return []

        world = self._client.world
        bp_lib = self._client.blueprint_library
        tm = self._client.traffic_manager
        spawn_points = list(self._client.map.get_spawn_points())
        self._rng.shuffle(spawn_points)

        bps = list(bp_lib.filter(filter_pattern))
        # For bicycles we want *only* the two-wheeled ones; the pattern
        # may also match motorcycles – that's fine, treat them as peers.
        if not bps:
            logger.warning(f"No blueprints matched '{filter_pattern}' – skipping {kind}s.")
            return []

        spawned: List[carla.Vehicle] = []
        tf_iter = iter(spawn_points)
        attempts = 0
        max_attempts = count * 10

        while len(spawned) < count and attempts < max_attempts:
            attempts += 1
            try:
                tf = next(tf_iter)
            except StopIteration:
                break
            bp = self._rng.choice(bps)
            actor = world.try_spawn_actor(bp, tf)
            if actor is None:
                continue
            self._client.register_actor(actor)
            actor.set_autopilot(True, tm.get_port())
            tm.set_global_distance_to_leading_vehicle(2.0)
            spawned.append(actor)

        if len(spawned) < count:
            logger.info(
                f"Spawned {len(spawned)}/{count} {kind}s (some spots were blocked)."
            )
        return spawned

    # ---- Pedestrians + walker controllers ---------------------------------
    def _spawn_n_pedestrians(
        self, count: int
    ) -> Tuple[List[carla.Actor], List[carla.Actor]]:
        if count <= 0:
            return [], []

        world = self._client.world
        bp_lib = self._client.blueprint_library
        walker_bps = list(bp_lib.filter("walker.pedestrian.*"))
        controller_bp = bp_lib.find("controller.ai.walker")
        if not walker_bps or controller_bp is None:
            logger.warning("Pedestrian blueprints missing – skipping pedestrians.")
            return [], []

        spawned_walkers: List[carla.Actor] = []
        spawned_controllers: List[carla.Actor] = []
        batch = world.get_random_location_from_navigation
        attempts = 0
        max_attempts = count * 10

        while len(spawned_walkers) < count and attempts < max_attempts:
            attempts += 1
            loc: Optional[carla.Location] = batch()
            if loc is None:
                continue
            # Navigation-mesh locations come back with no ground offset –
            # lift them a little so they spawn on the pavement instead of
            # inside it.
            loc.z += 0.5
            transform = carla.Transform(loc)
            bp = self._rng.choice(walker_bps)
            walker = world.try_spawn_actor(bp, transform)
            if walker is None:
                continue

            controller = world.spawn_actor(
                controller_bp, carla.Transform(), attach_to=walker
            )
            self._client.register_actor(walker)
            self._client.register_actor(controller)

            spawned_walkers.append(walker)
            spawned_controllers.append(controller)

            # Start the walker wandering to a random destination.
            controller.start()
            dest = world.get_random_location_from_navigation()
            if dest is not None:
                controller.go_to_location(dest)
                controller.set_max_speed(1.0 + self._rng.random() * 1.2)

        if len(spawned_walkers) < count:
            logger.info(
                f"Spawned {len(spawned_walkers)}/{count} pedestrians (navmesh spots exhausted)."
            )
        return spawned_walkers, spawned_controllers

    # ------------------------------------------------------------------
    # Cleanup (in addition to client-level destroy_all_actors)
    # ------------------------------------------------------------------
    def stop_traffic(self) -> None:
        """Gracefully stop walker AI before teardown (suppresses warnings)."""
        if self._traffic is None:
            return
        for ctrl in self._traffic.walkers_controllers:
            if ctrl.is_alive:
                try:
                    ctrl.stop()
                except Exception:
                    pass
