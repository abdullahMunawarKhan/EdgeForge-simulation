from __future__ import annotations

import queue
import sys
import time
from pathlib import Path

import carla
import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edgeforge.config.settings import settings

WIDTH = settings.CAMERA_WIDTH
HEIGHT = settings.CAMERA_HEIGHT
FOV = settings.CAMERA_FOV


def main():
    client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
    client.set_timeout(15.0)

    world = client.get_world()
    blueprint_library = world.get_blueprint_library()

    vehicle = None
    camera = None
    frame_queue = queue.Queue(maxsize=2)

    try:
        # Spawn a vehicle at an available location.
        vehicle_bp = blueprint_library.find("vehicle.tesla.model3")

        for spawn_point in world.get_map().get_spawn_points():
            vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)
            if vehicle is not None:
                break

        if vehicle is None:
            print("No free spawn point. Remove existing vehicles and retry.")
            return

        print(f"Vehicle spawned: {vehicle.id}")

        # Configure an RGB camera.
        camera_bp = blueprint_library.find("sensor.camera.rgb")
        camera_bp.set_attribute("image_size_x", str(WIDTH))
        camera_bp.set_attribute("image_size_y", str(HEIGHT))
        camera_bp.set_attribute("fov", str(FOV))

        # Position the camera above and in front of the vehicle.
        camera_transform = carla.Transform(
            carla.Location(x=1.5, z=2.4)
        )

        camera: carla.Sensor = world.spawn_actor(  # type: ignore[assignment]
            camera_bp,
            camera_transform,
            attach_to=vehicle,
        )

        def process_image(image):
            # Convert CARLA BGRA data to an OpenCV BGR image.
            array = np.frombuffer(image.raw_data, dtype=np.uint8)
            array = array.reshape((image.height, image.width, 4))
            frame = array[:, :, :3].copy()

            # Keep the newest frame rather than accumulating latency.
            try:
                frame_queue.put_nowait((image.frame, frame))
            except queue.Full:
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    pass

                try:
                    frame_queue.put_nowait((image.frame, frame))
                except queue.Full:
                    pass

        camera.listen(process_image)

        print("RGB camera streaming. Press Q to exit.")

        while True:
            try:
                frame_id, frame = frame_queue.get(timeout=2.0)
                cv2.putText(
                    frame,
                    f"EdgeForge | Frame {frame_id}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.9,
                    (0, 255, 0),
                    2,
                )
                cv2.imshow("EdgeForge - CARLA RGB Camera", frame)

            except queue.Empty:
                print("Waiting for camera frames...")
                continue

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    except Exception as exc:
        print(f"Camera test failed: {exc}")

    finally:
        if camera is not None:
            camera.stop()
            camera.destroy()

        if vehicle is not None:
            vehicle.destroy()

        cv2.destroyAllWindows()
        print("Camera test stopped; spawned actors cleaned up.")


if __name__ == "__main__":
    main()
