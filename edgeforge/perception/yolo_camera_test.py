
import queue

import carla
import cv2
import numpy as np
import torch
from ultralytics import YOLO

HOST = "192.168.97.250"
PORT = 2000

WIDTH = 640
HEIGHT = 480
MODEL_NAME = "yolo26n.pt"


def main():
    device = 0 if torch.cuda.is_available() else "cpu"
    print("Inference device:", torch.cuda.get_device_name(0)
          if device == 0 else "CPU")

    print(f"Loading {MODEL_NAME}...")
    model = YOLO(MODEL_NAME)

    client = carla.Client(HOST, PORT)
    client.set_timeout(15.0)
    world = client.get_world()
    library = world.get_blueprint_library()

    vehicle = None
    camera = None
    frames = queue.Queue(maxsize=1)

    try:
        vehicle_bp = library.find("vehicle.tesla.model3")

        for spawn_point in world.get_map().get_spawn_points():
            vehicle = world.try_spawn_actor(vehicle_bp, spawn_point)
            if vehicle is not None:
                break

        if vehicle is None:
            print("No free spawn point. Remove vehicles and retry.")
            return

        camera_bp = library.find("sensor.camera.rgb")
        camera_bp.set_attribute("image_size_x", str(WIDTH))
        camera_bp.set_attribute("image_size_y", str(HEIGHT))
        camera_bp.set_attribute("fov", "90")

        transform = carla.Transform(
            carla.Location(x=1.5, z=2.4)
        )

        camera = world.spawn_actor(
            camera_bp, transform, attach_to=vehicle
        )

        def on_image(image):
            bgra = np.frombuffer(
                image.raw_data, dtype=np.uint8
            ).reshape((image.height, image.width, 4))

            frame = bgra[:, :, :3].copy()

            if frames.full():
                try:
                    frames.get_nowait()
                except queue.Empty:
                    pass

            try:
                frames.put_nowait(frame)
            except queue.Full:
                pass

        camera.listen(on_image)
        print("YOLO running. Press Q to quit.")

        while True:
            try:
                frame = frames.get(timeout=5)
            except queue.Empty:
                print("No camera frames received.")
                break

            results = model.predict(
                source=frame,
                device=device,
                imgsz=640,
                conf=0.35,
                verbose=False,
            )

            annotated = results[0].plot()
            cv2.imshow("EdgeForge - Live YOLO Detection", annotated)

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:
        if camera is not None:
            camera.stop()
            camera.destroy()

        if vehicle is not None:
            vehicle.destroy()

        cv2.destroyAllWindows()
        print("YOLO camera test stopped.")


if __name__ == "__main__":
    main()
