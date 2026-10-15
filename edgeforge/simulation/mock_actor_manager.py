"""
Mock actor factory + synthetic physics for EdgeForge CARLA-less runs.

This module mirrors ``actor_manager.ActorManager``'s public surface 1:1:
  - spawn_ego(cfg) -> EgoBundle
  - spawn_traffic(cfg) -> TrafficBundle
  - stop_traffic() / cleanup helpers

Instead of CARLA actors, actors are ``MockActor`` instances owned by a
``MockCarlaClient``.  The critical guarantee is: after each tick the ego
vehicle has *non-trivial* kinematics (speed, position, acceleration) so
the perception / risk pipelines receive the same typed data they'd get
from a real CARLA run.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from edgeforge.simulation.mock_client import MockActor, MockCarlaClient, MockTransform
from edgeforge.utils import get_logger

logger = get_logger(__name__)


@dataclass
class EgoBundle:
    vehicle: MockActor
    model_id: str
    spawn_index: int


@dataclass
class TrafficBundle:
    vehicles: List[MockActor]
    pedestrians: List[MockActor]
    walkers_controllers: List[MockActor]
    bicycles: List[MockActor]

    @property
    def total(self) -> int:
        return len(self.vehicles) + len(self.pedestrians) + len(self.bicycles)


class MockActorManager:
    """Mock version of ActorManager – no CARLA server required."""

    def __init__(self, client: MockCarlaClient) -> None:
        self._client = client
        self._ego: Optional[MockActor] = None
        self._traffic: Optional[TrafficBundle] = None
        self._rng = random.Random(42)

    # ------------------------------------------------------------------ ego
    def spawn_ego(self, cfg: Dict[str, Any]) -> EgoBundle:
        world = self._client
        bp_lib = world.get_blueprint_library()
        spawn_points = world.get_spawn_points()

        if not spawn_points:
            raise RuntimeError("Mock world has no spawn points.")

        model_id = cfg.get("model", "vehicle.tesla.model3")
        bps = bp_lib.filter(model_id)
        if not bps:
            logger.warning(f"Mock blueprint '{model_id}' not found – using prius.")
            bps = bp_lib.filter("vehicle.toyota.prius")
        bp = self._rng.choice(list(bps))

        idx = int(cfg.get("spawn_point_index", 0))
        if idx < 0 or idx >= len(spawn_points):
            logger.warning(f"spawn_point_index={idx} out of range – using 0.")
            idx = 0

        transform = spawn_points[idx]
        vehicle = world.try_spawn_actor(bp, transform)
        assert vehicle is not None

        self._ego = vehicle

        speed_limit_kmh = float(cfg.get("speed_limit", 50))
        if cfg.get("autopilot", False):
            # Stored as a custom attribute – our per-tick kinematics loop
            # (in the runner) will read this.
            vehicle.attributes["autopilot"] = True
            vehicle.attributes["desired_speed_kmh"] = speed_limit_kmh
            logger.info(f"🚗 Mock ego autopilot ON, desired speed {speed_limit_kmh:.0f} km/h")

        logger.success(
            f"🚗 Mock ego spawned: {vehicle.type_id} @ spawn #{idx}"
        )
        return EgoBundle(vehicle=vehicle, model_id=vehicle.type_id, spawn_index=idx)

    # ------------------------------------------------------------------ traffic
    def spawn_traffic(self, cfg: Dict[str, Any]) -> TrafficBundle:
        n_vehicles = int(cfg.get("vehicles", 0))
        n_pedestrians = int(cfg.get("pedestrians", 0))
        n_bicycles = int(cfg.get("bicycles", 0))

        vehicles = self._spawn_n_vehicles(n_vehicles, "vehicle.*", "vehicle")
        bicycles = self._spawn_n_vehicles(n_bicycles, "vehicle.bh.*", "bicycle")
        peds, controllers = self._spawn_n_pedestrians(n_pedestrians)

        bundle = TrafficBundle(
            vehicles=vehicles,
            pedestrians=peds,
            walkers_controllers=controllers,
            bicycles=bicycles,
        )
        self._traffic = bundle
        logger.success(
            f"🚦 Mock traffic: {bundle.total} total "
            f"(vehicles={len(vehicles)}, bikes={len(bicycles)}, peds={len(peds)})"
        )
        return bundle

    # ---- helpers ----------------------------------------------------------
    def _spawn_n_vehicles(self, count: int, pattern: str, kind: str) -> List[MockActor]:
        if count <= 0:
            return []
        world = self._client
        bps = list(world.get_blueprint_library().filter(pattern))
        if not bps:
            return []
        spawn_points = list(world.get_spawn_points())
        self._rng.shuffle(spawn_points)
        spawned: List[MockActor] = []
        tf_iter = iter(spawn_points)
        attempts = 0
        max_attempts = count * 5
        while len(spawned) < count and attempts < max_attempts:
            attempts += 1
            try:
                tf = next(tf_iter)
            except StopIteration:
                break
            # Offset each NPC from ego to avoid the exact same spot.
            offset_xy = 8 * (len(spawned) + 1)
            tf.x += offset_xy
            tf.y += ((-1) ** len(spawned)) * 2.5
            bp = self._rng.choice(bps)
            a = world.try_spawn_actor(bp, tf)
            if a is None:
                continue
            a.attributes["autopilot"] = True
            a.attributes["desired_speed_kmh"] = float(self._rng.randint(25, 60))
            spawned.append(a)
        if len(spawned) < count:
            logger.info(f"Spawned {len(spawned)}/{count} mock {kind}s.")
        return spawned

    def _spawn_n_pedestrians(self, count: int) -> Tuple[List[MockActor], List[MockActor]]:
        if count <= 0:
            return [], []
        world = self._client
        walker_bps = list(world.get_blueprint_library().filter("walker.pedestrian.*"))
        if not walker_bps:
            return [], []
        spawned_walkers: List[MockActor] = []
        spawned_controllers: List[MockActor] = []
        # Deterministic pseudo-navmesh: small ring of points near ego.
        ring_radius = 12.0
        for i in range(count):
            angle = (i / max(count, 1)) * 2.0 * math.pi
            x = ring_radius * math.cos(angle) + 2.0
            y = ring_radius * math.sin(angle)
            tf = MockTransform(x=x, y=y, z=0.5)
            bp = self._rng.choice(walker_bps)
            walker = world.try_spawn_actor(bp, tf)
            if walker is None:
                continue
            # controller pseudo-actor (no blueprint – we just want a handle)
            controller = MockActor(
                world._next_id, "controller.ai.walker", MockTransform(x, y, 0.0),  # noqa: SLF001
                attributes={"walker_id": walker.id, "alive": True},
            )
            world._next_id += 1  # noqa: SLF001
            world._actors[controller.id] = controller  # noqa: SLF001
            walker.attributes["controller_id"] = controller.id
            walker.attributes["desired_speed_kmh"] = float(self._rng.uniform(0.8, 2.2)) * 3.6
            spawned_walkers.append(walker)
            spawned_controllers.append(controller)
        return spawned_walkers, spawned_controllers

    # ------------------------------------------------------------------ cleanup
    def stop_traffic(self) -> None:
        if self._traffic is None:
            return
        for ctrl in self._traffic.walkers_controllers:
            ctrl.attributes["alive"] = False
