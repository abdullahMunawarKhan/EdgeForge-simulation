"""
CARLA-specific simulation layer for EdgeForge.

All code that imports and talks directly to the CARLA Python API lives
in this package.  The rest of EdgeForge (perception / analysis / config /
data) must NOT depend on carla – that way they remain testable without a
running simulator.

Public surface (Person 1 / Simulation Lead deliverables):
  - CarlaClient       — managed synchronous-mode connection + lifecycle
  - WorldSnapshot     — typed frame/timestamp descriptor
  - ActorManager      — ego + NPC (vehicles/peds/bicycles) spawning
  - EgoBundle / TrafficBundle — typed actor-spawn result objects
  - SensorManager     — sensor factory (RGB, collision, lane invasion, ...)
  - SensorFrame       — typed per-frame data packet (image + state + events)
  - ScenarioRunner    — end-to-end scenario orchestrator (JSON config)
  - ScenarioInfo      — scenario metadata descriptor
  - image_to_bgr      — adapter: carla.Image  → np.ndarray (BGR)
  - vehicle_to_state  — adapter: carla.Vehicle → VehicleState (Pydantic)
"""

from edgeforge.simulation.actor_manager import (
    ActorManager,
    EgoBundle,
    TrafficBundle,
)
from edgeforge.simulation.carla_client import (
    CarlaClient,
    WorldSnapshot,
)
from edgeforge.simulation.scenario_runner import (
    ScenarioInfo,
    ScenarioRunner,
)
from edgeforge.simulation.sensor_manager import (
    SensorFrame,
    SensorManager,
    image_to_bgr,
    vehicle_to_state,
)

__all__ = [
    "ActorManager",
    "CarlaClient",
    "EgoBundle",
    "ScenarioInfo",
    "ScenarioRunner",
    "SensorFrame",
    "SensorManager",
    "TrafficBundle",
    "WorldSnapshot",
    "image_to_bgr",
    "vehicle_to_state",
]
