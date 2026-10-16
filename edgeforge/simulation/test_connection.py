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

    print("Client version:", client.get_client_version())
    print("Server version:", client.get_server_version())

    world = client.get_world()
    print("Current map:", world.get_map().name)
    print("EdgeForge connected to remote CARLA!")


if __name__ == "__main__":
    main()
    