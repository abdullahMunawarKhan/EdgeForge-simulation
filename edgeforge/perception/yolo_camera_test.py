import queue
import sys
import time
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edgeforge.config.settings import settings
from edgeforge.data.models import DetectedObject
from edgeforge.perception.detector import ObjectDetector
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)

DETECTION_LOG_INTERVAL_SECONDS = 2.0

def render_detections(
    frame: np.ndarray,
    detections: Sequence[DetectedObject],
) -> np.ndarray:
    """Draw converted YOLO detections over a copy of the camera frame."""
    annotated = frame.copy()
    for detection in detections:
        if detection.bbox is None or len(detection.bbox) != 4:
            continue

        x1, y1, x2, y2 = (int(value) for value in detection.bbox)
        label = f"{detection.object_type} {detection.confidence:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            annotated,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            2,
        )
    return annotated


def main():
    import carla

    detector = ObjectDetector()
    print(
        f"YOLO model: {detector.model_name}; "
        f"confidence: {detector.confidence_threshold}; device: {detector.device}"
    )

    client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
    client.set_timeout(settings.CARLA_TIMEOUT)
    world = client.get_world()
    library = world.get_blueprint_library()

    vehicle = None
    cameras = {}
    frames = {
        "front": queue.Queue(maxsize=1),
        "side": queue.Queue(maxsize=1),
    }

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
        camera_bp.set_attribute("image_size_x", str(settings.CAMERA_WIDTH))
        camera_bp.set_attribute("image_size_y", str(settings.CAMERA_HEIGHT))
        camera_bp.set_attribute("fov", str(settings.CAMERA_FOV))

        camera_transforms = {
            "front": carla.Transform(carla.Location(x=1.5, z=2.4)),
            "side": carla.Transform(
                carla.Location(y=2.0, z=2.0),
                carla.Rotation(pitch=-5.0, yaw=90.0),
            ),
        }

        def make_image_callback(camera_frames):
            def on_image(image):
                bgra = np.frombuffer(
                    image.raw_data, dtype=np.uint8
                ).reshape((image.height, image.width, 4))
                frame = bgra[:, :, :3].copy()

                if camera_frames.full():
                    try:
                        camera_frames.get_nowait()
                    except queue.Empty:
                        pass

                try:
                    camera_frames.put_nowait(frame)
                except queue.Full:
                    pass

            return on_image

        for camera_name, transform in camera_transforms.items():
            camera = world.spawn_actor(camera_bp, transform, attach_to=vehicle)
            cameras[camera_name] = camera
            camera.listen(make_image_callback(frames[camera_name]))

        active_camera = "front"
        print("YOLO running. Press 1 for front, 2 for right-side, or Q to quit.")
        last_detection_log = 0.0

        while True:
            try:
                frame = frames[active_camera].get(timeout=5)
            except queue.Empty:
                print(f"No frames received from the {active_camera} camera.")
                continue

            # detect_objects() explicitly converts detect()'s RawDetection
            # values into the DetectedObject interface used by this renderer.
            detections = detector.detect_objects(frame)
            annotated = render_detections(frame, detections)
            camera_label = (
                "Front camera (1)"
                if active_camera == "front"
                else "Right-side camera (2)"
            )
            cv2.putText(
                annotated,
                camera_label,
                (20, annotated.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2,
            )

            now = time.monotonic()
            if now - last_detection_log >= DETECTION_LOG_INTERVAL_SECONDS:
                summary = ", ".join(
                    f"{detection.object_type}={detection.confidence:.2f}"
                    for detection in detections
                )
                logger.info(
                    "YOLO inference: model_loaded={}, detections={}{}",
                    detector.get_status()["model_loaded"],
                    len(detections),
                    f" [{summary}]" if summary else "",
                )
                last_detection_log = now

            cv2.imshow("EdgeForge - Live YOLO Detection", annotated)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("1"):
                active_camera = "front"
            elif key == ord("2"):
                active_camera = "side"
            elif key == ord("q"):
                break

    finally:
        for camera in cameras.values():
            camera.stop()
            camera.destroy()

        if vehicle is not None:
            vehicle.destroy()

        cv2.destroyAllWindows()
        print("YOLO camera test stopped.")


if __name__ == "__main__":
    main()
