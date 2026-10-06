import carla


def main():
    print("Connecting to CARLA...")

    client = carla.Client("127.0.0.1", 2000)
    client.set_timeout(10.0)

    world = client.get_world()

    print("✅ Connected to CARLA!")
    print(f"Map: {world.get_map().name}")

    weather = world.get_weather()

    print(f"Cloudiness: {weather.cloudiness}")
    print(f"Rain: {weather.precipitation}")
    print(f"Fog: {weather.fog_density}")


if __name__ == "__main__":
    main()