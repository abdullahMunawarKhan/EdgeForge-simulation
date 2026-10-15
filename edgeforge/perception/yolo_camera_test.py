
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
        camera_bp.set_attribute("image_size_x", str(settings.CAMERA_WIDTH))
        camera_bp.set_attribute("image_size_y", str(settings.CAMERA_HEIGHT))
        camera_bp.set_attribute("fov", str(settings.CAMERA_FOV))

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
        last_detection_log = 0.0

        while True:
            try:
                frame = frames.get(timeout=5)
            except queue.Empty:
                print("No camera frames received.")
                break

            # detect_objects() explicitly converts detect()'s RawDetection
            # values into the DetectedObject interface used by this renderer.
            detections = detector.detect_objects(frame)
            annotated = render_detections(frame, detections)

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
