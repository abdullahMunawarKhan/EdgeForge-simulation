from __future__ import annotations

import argparse
import sys
from pathlib import Path

import carla

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edgeforge.config.settings import settings


def clear_traffic(world: carla.World, keep_vehicle_id: int | None = None) -> None:
    actors = world.get_actors()
    vehicles = sorted(actors.filter("vehicle.*"), key=lambda actor: actor.id)

    if keep_vehicle_id is not None:
        if not any(vehicle.id == keep_vehicle_id for vehicle in vehicles):
            raise ValueError(f"Vehicle actor {keep_vehicle_id} was not found.")
        preserved_vehicle_id = keep_vehicle_id
    else:
        preserved_vehicle_id = vehicles[0].id if vehicles else None

    actors_to_destroy = [
        *actors.filter("controller.ai.walker"),
        *actors.filter("walker.pedestrian.*"),
        *(vehicle for vehicle in vehicles if vehicle.id != preserved_vehicle_id),
    ]

    failures: list[str] = []
    destroyed = 0
    for actor in actors_to_destroy:
        try:
            if actor.destroy():
                destroyed += 1
            else:
                failures.append(f"actor {actor.id} returned false")
        except RuntimeError as exc:
            failures.append(f"actor {actor.id}: {exc}")

    if preserved_vehicle_id is not None:
        print(f"Preserved vehicle actor {preserved_vehicle_id}.")
    print(f"Destroyed {destroyed} traffic actors.")

    if failures:
        details = "; ".join(failures)
        raise RuntimeError(f"Failed to destroy {len(failures)} actor(s): {details}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clear CARLA traffic while preserving the ego/test vehicle."
    )
    parser.add_argument(
        "--keep-vehicle-id",
        type=int,
        help="vehicle actor ID to preserve (defaults to the lowest-ID vehicle)",
    )
    args = parser.parse_args()

    client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
    client.set_timeout(15.0)
    clear_traffic(client.get_world(), keep_vehicle_id=args.keep_vehicle_id)


if __name__ == "__main__":
    main()
