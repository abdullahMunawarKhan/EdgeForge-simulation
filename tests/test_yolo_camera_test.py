"""Unit tests for YOLO camera test rendering without a CARLA server."""

import queue
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from edgeforge.api import runtime
from edgeforge.config.settings import settings
from edgeforge.data.models import DetectedObject
from edgeforge.perception.detector import ObjectDetector
from edgeforge.perception.yolo_camera_test import (
    _get_camera_frame_for_tick,
    publish_front_dashboard_frame,
    render_detections,
)


def test_mock_yolo_result_is_converted_and_rendered() -> None:
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    result = SimpleNamespace(
        names={2: "car"},
        boxes=[
            SimpleNamespace(
                cls=np.array([2]),
                conf=np.array([0.91]),
                xyxy=np.array([[4.0, 5.0, 20.0, 21.0]]),
            )
        ],
    )
    model = MagicMock()
    model.predict.return_value = [result]
    detector = ObjectDetector(model_name="mock.pt", model=model)

    detections = detector.detect_objects(frame)
    annotated = render_detections(frame, detections)

    assert len(detections) == 1
    assert detections[0].object_type == "car"
    assert detections[0].confidence == 0.91
    assert detections[0].bbox == [4.0, 5.0, 20.0, 21.0]
    assert detections[0].distance is None
    assert detections[0].relative_speed is None
    assert np.any(annotated[5, 4] == (0, 255, 0))
    model.predict.assert_called_once_with(
        source=frame,
        conf=settings.DETECTION_CONFIDENCE_THRESHOLD,
        iou=settings.YOLO_NMS_IOU,
        device=settings.YOLO_DEVICE,
        classes=None,
        verbose=False,
    )


def test_empty_detections_keep_live_frame_unchanged() -> None:
    frame = np.full((16, 16, 3), 37, dtype=np.uint8)

    annotated = render_detections(frame, [])

    assert np.array_equal(annotated, frame)
    assert annotated is not frame


def test_yolo_camera_frame_collection_discards_stale_frames() -> None:
    camera_queue: queue.Queue[tuple[np.ndarray, int, float]] = queue.Queue()
    camera_queue.put((np.zeros((2, 2, 3), dtype=np.uint8), 10, 1.0))
    matching_frame = (np.ones((2, 2, 3), dtype=np.uint8), 11, 1.1)
    camera_queue.put(matching_frame)

    result = _get_camera_frame_for_tick(
        "top_down",
        {"top_down": camera_queue},
        {},
        frame_id=11,
    )

    assert result is matching_frame
    assert camera_queue.empty()


def test_yolo_camera_frame_collection_keeps_a_future_frame_for_next_tick() -> None:
    camera_queue: queue.Queue[tuple[np.ndarray, int, float]] = queue.Queue()
    future_frame = (np.ones((2, 2, 3), dtype=np.uint8), 12, 1.2)
    camera_queue.put(future_frame)
    pending_frames = {}
    camera_queues = {"top_down": camera_queue}

    assert _get_camera_frame_for_tick(
        "top_down", camera_queues, pending_frames, frame_id=11
    ) is None
    assert _get_camera_frame_for_tick(
        "top_down", camera_queues, pending_frames, frame_id=12
    ) is future_frame


def test_front_camera_frame_and_yolo_results_are_published_to_dashboard() -> None:
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    top_down_frame = np.full((32, 32, 3), 64, dtype=np.uint8)
    detection = DetectedObject(
        object_type="car",
        confidence=0.91,
        bbox=[4.0, 5.0, 20.0, 21.0],
    )
    conditions = {
        "scenario_id": "yolo_camera_test",
        "map": "Town03",
        "backend": "carla",
    }
    detector_status = {"model_loaded": True, "model_name": "yolov8n.pt"}

    runtime.start("carla", conditions)
    try:
        publish_front_dashboard_frame(
            runtime,
            frame,
            [detection],
            frame_id=123,
            timestamp=6.15,
            scenario_conditions=conditions,
            detector_status=detector_status,
            camera_frames={
                "top_down": top_down_frame,
            },
        )

        deadline = time.monotonic() + 3.0
        camera_frames = {
            name: runtime.camera_frame(name)
            for name in ("front", "top_down")
        }
        while (
            not all(camera_frames.values())
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
            camera_frames = {
                name: runtime.camera_frame(name)
                for name in ("front", "top_down")
            }

        assert all(camera_frames.values())
        assert all(
            camera_frames[name][1].startswith(b"\xff\xd8")
            for name in ("front", "top_down")
        )
        assert runtime.camera_status()["cameras"]["front"]["frame_id"] == 123
        assert runtime.camera_status()["cameras"]["top_down"]["frame_id"] == 123

        snapshot = runtime.snapshot()[1]
        assert snapshot["simulation_status"] == "running"
        assert snapshot["detections"][0]["object_type"] == "car"
        assert snapshot["detections"][0]["confidence"] == 0.91
        assert snapshot["metrics"]["detection_count"] == 1
        assert snapshot["metrics"]["pipeline"]["detector"] == detector_status
    finally:
        runtime.stop()
