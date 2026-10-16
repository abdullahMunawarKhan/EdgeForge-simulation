"""Unit tests for YOLO camera test rendering without a CARLA server."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from edgeforge.config.settings import settings
from edgeforge.perception.detector import ObjectDetector
from edgeforge.perception.yolo_camera_test import render_detections


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
