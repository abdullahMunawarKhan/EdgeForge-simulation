from __future__ import annotations

import random
from typing import Any

import carla

from edgeforge.config.settings import settings

VEHICLE_COUNT = 12
PEDESTRIAN_COUNT = 5


def main() -> None:
    client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
    client.set_timeout(settings.CARLA_TIMEOUT)

    world = client.get_world()
    blueprints = world.get_blueprint_library()
    traffic_manager = client.get_trafficmanager(8000)

    spawn_points = world.get_map().get_spawn_points()
    random.shuffle(spawn_points)

    vehicle_blueprints = blueprints.filter("vehicle.*")
    vehicle_blueprints = [
        bp for bp in vehicle_blueprints
        if bp.has_attribute("number_of_wheels")
        and int(bp.get_attribute("number_of_wheels")) == 4
    ]

    vehicle_ids = []
    walker_ids = []
    controller_ids = []

    for transform in spawn_points:
        if len(vehicle_ids) >= VEHICLE_COUNT:
            break

        if not vehicle_blueprints:
            break

        bp = random.choice(vehicle_blueprints)

        if bp.has_attribute("color"):
            bp.set_attribute(
                "color",
                random.choice(bp.get_attribute("color").recommended_values),
            )

        actor: Any = world.try_spawn_actor(bp, transform)

        if actor:
            actor.set_autopilot(True, traffic_manager.get_port())
            vehicle_ids.append(actor.id)

    walker_blueprints = blueprints.filter("walker.pedestrian.*")
    for _ in range(PEDESTRIAN_COUNT):
        location = world.get_random_location_from_navigation()

        if location is None or not walker_blueprints:
            continue

        transform = carla.Transform(location)
        bp = random.choice(walker_blueprints)

        walker = world.try_spawn_actor(bp, transform)

        if walker:
            walker_ids.append(walker.id)

    controller_bp = blueprints.find("controller.ai.walker")

    for walker_id in walker_ids:
        walker = world.get_actor(walker_id)
        if walker is None:
            continue

        controller: Any = world.try_spawn_actor(
            controller_bp,
            carla.Transform(),
            attach_to=walker,
        )

        if controller:
            controller_ids.append(controller.id)
            controller.start()

            destination = world.get_random_location_from_navigation()
            if destination:
                controller.go_to_location(destination)

            controller.set_max_speed(random.uniform(1.0, 1.6))

    print(f"Spawned vehicles: {len(vehicle_ids)}")
    print(f"Spawned pedestrians: {len(walker_ids)}")
    print(f"Walker controllers: {len(controller_ids)}")
    print("Traffic is running. Spawned actors remain in CARLA until explicitly destroyed.")


if __name__ == "__main__":
    main()