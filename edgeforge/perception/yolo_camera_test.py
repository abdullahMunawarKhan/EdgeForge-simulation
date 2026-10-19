from __future__ import annotations

import queue
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence

import cv2
import numpy as np

if TYPE_CHECKING:
    from edgeforge.api import SimulationRuntime

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


def publish_front_dashboard_frame(
    runtime: SimulationRuntime,
    frame: np.ndarray,
    detections: Sequence[DetectedObject],
    *,
    frame_id: int,
    timestamp: float,
    scenario_conditions: Mapping[str, Any],
    detector_status: Mapping[str, Any],
    camera_frames: Mapping[str, np.ndarray] | None = None,
) -> None:
    """Publish live CARLA camera frames and front-camera detections."""
    frames_to_publish = dict(camera_frames or {})
    frames_to_publish["front"] = frame
    runtime.publish_frame(
        backend="carla",
        frame_id=frame_id,
        timestamp=timestamp,
        detections=detections,
        scenario_conditions=scenario_conditions,
        metrics={
            "detection_count": len(detections),
            "pipeline": {
                "module": "yolo_camera_test",
                "detector": dict(detector_status),
            },
        },
        risk_assessment=None,
        camera_frames=frames_to_publish,
    )


def _get_camera_frame_for_tick(
    camera_name: str,
    camera_frames: Mapping[str, queue.Queue],
    pending_frames: dict[str, tuple[np.ndarray, int, float]],
    frame_id: int,
    timeout: float = 0.1,
) -> tuple[np.ndarray, int, float] | None:
    """Return a camera frame from the requested CARLA tick, dropping stale frames."""
    deadline = time.monotonic() + timeout
    pending = pending_frames.get(camera_name)
    while pending is None or pending[1] < frame_id:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            pending = camera_frames[camera_name].get(timeout=remaining)
        except queue.Empty:
            return None
        if pending[1] < frame_id:
            continue
        pending_frames[camera_name] = pending

    if pending[1] != frame_id:
        return None
    pending_frames.pop(camera_name, None)
    return pending


def main():
    import carla
    from edgeforge.api import runtime, start_api_server

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
        "top_down": queue.Queue(maxsize=1),
    }
    pending_camera_frames: dict[str, tuple[np.ndarray, int, float]] = {}
    api_server = None
    runtime_started = False

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
            "top_down": carla.Transform(
                carla.Location(z=20.0),
                carla.Rotation(pitch=-90.0, yaw=0.0),
            ),
        }

        def make_image_callback(camera_frames):
            def on_image(image):
                bgra = np.frombuffer(
                    image.raw_data, dtype=np.uint8
                ).reshape((image.height, image.width, 4))
                frame = bgra[:, :, :3].copy()
                frame_data = (frame, int(image.frame), float(image.timestamp))

                if camera_frames.full():
                    try:
                        camera_frames.get_nowait()
                    except queue.Empty:
                        pass

                try:
                    camera_frames.put_nowait(frame_data)
                except queue.Full:
                    pass

            return on_image

        for camera_name, transform in camera_transforms.items():
            camera = world.spawn_actor(camera_bp, transform, attach_to=vehicle)
            cameras[camera_name] = camera
            camera.listen(make_image_callback(frames[camera_name]))

        scenario_conditions = {
            "scenario_id": "yolo_camera_test",
            "scenario_name": "YOLO camera test",
            "map": world.get_map().name,
            "backend": "carla",
        }
        runtime.start("carla", scenario_conditions)
        runtime_started = True
        api_server = start_api_server()

        active_camera = "front"
        print(
            f"YOLO running. Dashboard API: http://{settings.API_HOST}:"
            f"{settings.API_PORT}. Press 1 for front, 2 for top-down, or Q to quit."
        )
        last_detection_log = 0.0

        while True:
            try:
                front_frame, frame_id, timestamp = frames["front"].get(timeout=5)
            except queue.Empty:
                print("No frames received from the front camera.")
                continue

            detections = detector.detect_objects(front_frame)
            dashboard_frames = {"front": front_frame}
            camera_frame = _get_camera_frame_for_tick(
                "top_down",
                frames,
                pending_camera_frames,
                frame_id,
            )
            if camera_frame is not None:
                dashboard_frames["top_down"] = camera_frame[0]
            publish_front_dashboard_frame(
                runtime,
                front_frame,
                detections,
                frame_id=frame_id,
                timestamp=timestamp,
                scenario_conditions=scenario_conditions,
                detector_status=detector.get_status(),
                camera_frames=dashboard_frames,
            )

            display_frame = dashboard_frames.get(active_camera)
            if display_frame is None:
                logger.warning(
                    "No synchronized {} camera frame for CARLA frame {}.",
                    active_camera,
                    frame_id,
                )
                key = cv2.waitKey(1) & 0xFF
                if key == ord("1"):
                    active_camera = "front"
                elif key == ord("2"):
                    active_camera = "top_down"
                elif key == ord("q"):
                    break
                continue

            display_detections = detections if active_camera == "front" else []
            annotated = render_detections(display_frame, display_detections)
            camera_label = (
                "Front camera (1)"
                if active_camera == "front"
                else "Top-down camera (2)"
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
                active_camera = "top_down"
            elif key == ord("q"):
                break

    finally:
        try:
            for camera in cameras.values():
                camera.stop()
                camera.destroy()

            if vehicle is not None:
                vehicle.destroy()
        finally:
            if runtime_started:
                runtime.stop("YOLO camera test stopped.")
            if api_server is not None:
                api_server.should_exit = True
            cv2.destroyAllWindows()
            print("YOLO camera test stopped.")


if __name__ == "__main__":
    main()
