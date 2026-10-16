from __future__ import annotations

import sys
from pathlib import Path

import carla

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edgeforge.config.settings import settings


def main():
    client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
    client.set_timeout(15.0)

    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    vehicle_bp = blueprint_library.find("vehicle.tesla.model3")
    spawn_points = world.get_map().get_spawn_points()

    if not spawn_points:
        print("No spawn points available.")
        return

    # Find an unoccupied spawn point.
    for spawn_point in spawn_points:
        if world.get_actors().filter("vehicle.*"):
            # The simple test below is sufficient for a first run;
            # we will improve collision checking in the next iteration.
            pass

        try:
            vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)
            if vehicle is not None:
                print(f"Vehicle spawned successfully: {vehicle.type_id}")
                print(f"Actor ID: {vehicle.id}")
                print(f"Location: {vehicle.get_location()}")
                print("Press Ctrl+C to stop this script.")
                return
        except RuntimeError as exc:
            print("Spawn attempt failed:", exc)

    print("No available spawn point found.")


if __name__ == "__main__":
    main()
