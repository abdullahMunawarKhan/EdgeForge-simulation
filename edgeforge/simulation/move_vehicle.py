from __future__ import annotations

import sys
import time
from pathlib import Path

import carla

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edgeforge.config.settings import settings

DISTANCE_METERS = 30.0
TARGET_SPEED = 2.0  # m/s, approximately 7.2 km/h


def main():
    client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
    client.set_timeout(15.0)

    world = client.get_world()
    vehicles = world.get_actors().filter("vehicle.*")

    if not vehicles:
        print("No vehicle found. Spawn a vehicle first.")
        return

    vehicle = vehicles[0]
    start = vehicle.get_location()

    print(f"Moving vehicle {vehicle.id} forwards for {DISTANCE_METERS:.0f} metres...")

    vehicle.set_autopilot(False)
    vehicle.apply_control(
        carla.VehicleControl(throttle=0.25, steer=0.0, reverse=False)
    )

    try:
        while True:
            current = vehicle.get_location()
            distance = start.distance(current)

            print(f"Distance travelled: {distance:.2f} m")

            if distance >= DISTANCE_METERS:
                break

            time.sleep(0.1)

    finally:
        vehicle.apply_control(carla.VehicleControl())
        vehicle.set_target_velocity(carla.Vector3D(0, 0, 0))
        print("Vehicle stopped.")


if __name__ == "__main__":
    main()
