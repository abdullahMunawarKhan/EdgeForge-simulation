import carla
import random
import time


def main():
    client = carla.Client("127.0.0.1", 2000)
    client.set_timeout(10.0)

    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    # Find a vehicle
    vehicle_blueprints = blueprint_library.filter("vehicle.*")
    vehicle_bp = random.choice(vehicle_blueprints)

    # Find a spawn point
    spawn_points = world.get_map().get_spawn_points()

    if not spawn_points:
        print("No spawn points available.")
        return

    spawn_point = random.choice(spawn_points)

    # Spawn vehicle
    vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)

    if vehicle is None:
        print("Vehicle could not be spawned.")
        return

    print(f"Vehicle spawned: {vehicle.type_id}")

    # Let it exist for a few seconds
    time.sleep(10)

    # Clean up
    vehicle.destroy()
    print("Vehicle removed.")


if __name__ == "__main__":
    main()