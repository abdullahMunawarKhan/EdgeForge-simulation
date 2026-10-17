"""
Unit tests for EdgeForge perception stage 1 & 2:
  1. Camera preprocessing (CameraProcessor)
  2. YOLOv8 object detection (ObjectDetector, RawDetection)

These tests DO NOT require a running CARLA server and DO NOT download YOLO model weights.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import numpy as np
import pytest

from edgeforge.config import settings
from edgeforge.analysis import RiskEngine
from edgeforge.data.models import DetectedObject, VehicleState
from edgeforge.perception import (
    COCO_CLASS_MAP,
    CameraProcessor,
    DistanceEstimate,
    DistanceEstimator,
    FrameInfo,
    ObjectDetector,
    ObjectTracker,
    PerceptionPipeline,
    RawDetection,
    TrackedDetection,
    adapt_ground_truth_detections,
    compute_iou,
)


# ==============================================================================
# 1. CameraProcessor Tests
# ==============================================================================

class TestCameraProcessor:
    """Tests for CameraProcessor validation, conversions, and camera calibration."""

    @pytest.fixture
    def processor(self) -> CameraProcessor:
        return CameraProcessor(default_width=1280, default_height=720)

    @pytest.fixture
    def sample_bgr_frame(self) -> np.ndarray:
        # Create a deterministic 3-channel BGR test image
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        frame[:, :, 0] = 50   # Blue
        frame[:, :, 1] = 100  # Green
        frame[:, :, 2] = 200  # Red
        return frame

    def test_validation_rejects_none_and_empty(self, processor: CameraProcessor) -> None:
        assert not processor.is_valid_frame(None)
        assert not processor.is_valid_frame(np.array([]))
        assert not processor.is_valid_frame("not an array")

        with pytest.raises(ValueError, match="no image provided"):
            processor.validate_frame(None)

        with pytest.raises(ValueError, match="Frame is empty"):
            processor.validate_frame(np.array([]))

        with pytest.raises(ValueError, match="Expected numpy.ndarray"):
            processor.validate_frame([1, 2, 3])

    def test_validation_rejects_invalid_dimensions(self, processor: CameraProcessor) -> None:
        flat_1d = np.zeros(100, dtype=np.uint8)
        hyper_4d = np.zeros((2, 2, 2, 2), dtype=np.uint8)

        assert not processor.is_valid_frame(flat_1d)
        assert not processor.is_valid_frame(hyper_4d)

        with pytest.raises(ValueError, match="Frame must be 2D .* or 3D"):
            processor.validate_frame(flat_1d)

        with pytest.raises(ValueError, match="Frame must be 2D .* or 3D"):
            processor.validate_frame(hyper_4d)

    def test_validation_rejects_invalid_dtype(self, processor: CameraProcessor) -> None:
        int64_frame = np.zeros((10, 10, 3), dtype=np.int64)
        assert not processor.is_valid_frame(int64_frame)

        with pytest.raises(ValueError, match="Unsupported frame dtype"):
            processor.validate_frame(int64_frame)

    def test_validation_accepts_valid_frames(
        self, processor: CameraProcessor, sample_bgr_frame: np.ndarray
    ) -> None:
        assert processor.is_valid_frame(sample_bgr_frame)
        processor.validate_frame(sample_bgr_frame)

        float_frame = sample_bgr_frame.astype(np.float32) / 255.0
        assert processor.is_valid_frame(float_frame)
        processor.validate_frame(float_frame)

    def test_get_frame_info(
        self, processor: CameraProcessor, sample_bgr_frame: np.ndarray
    ) -> None:
        info = processor.get_frame_info(sample_bgr_frame)
        assert isinstance(info, FrameInfo)
        assert info.width == 200
        assert info.height == 100
        assert info.channels == 3
        assert info.dtype == "uint8"
        assert not info.empty

        empty_info = processor.get_frame_info(None)
        assert empty_info.empty is True
        assert empty_info.width == 0

    def test_bgr_to_rgb_conversion(
        self, processor: CameraProcessor, sample_bgr_frame: np.ndarray
    ) -> None:
        rgb = processor.to_rgb(sample_bgr_frame)
        assert rgb.shape == sample_bgr_frame.shape
        # Input was B=50, G=100, R=200; in RGB it should be R=200, G=100, B=50
        assert rgb[0, 0, 0] == 200
        assert rgb[0, 0, 1] == 100
        assert rgb[0, 0, 2] == 50

    def test_rgb_to_bgr_conversion(self, processor: CameraProcessor) -> None:
        rgb_frame = np.zeros((10, 10, 3), dtype=np.uint8)
        rgb_frame[:, :, 0] = 255  # Red
        bgr = processor.to_bgr(rgb_frame)
        assert bgr.shape == rgb_frame.shape
        assert bgr[0, 0, 0] == 0    # Blue
        assert bgr[0, 0, 2] == 255  # Red

    def test_to_grayscale_conversion(
        self, processor: CameraProcessor, sample_bgr_frame: np.ndarray
    ) -> None:
        gray = processor.to_grayscale(sample_bgr_frame)
        assert gray.ndim == 2
        assert gray.shape == (100, 200)

        # Grayscale input returned cleanly
        gray_again = processor.to_grayscale(gray)
        assert gray_again.shape == gray.shape

    def test_clahe_contrast_enhancement(
        self, processor: CameraProcessor, sample_bgr_frame: np.ndarray
    ) -> None:
        enhanced_bgr = processor.apply_clahe(sample_bgr_frame)
        assert enhanced_bgr.shape == sample_bgr_frame.shape
        assert enhanced_bgr.dtype == np.uint8

        gray = processor.to_grayscale(sample_bgr_frame)
        enhanced_gray = processor.apply_clahe(gray)
        assert enhanced_gray.shape == gray.shape

    def test_deterministic_preprocessing_pipeline(
        self, processor: CameraProcessor, sample_bgr_frame: np.ndarray
    ) -> None:
        processed = processor.preprocess_frame(
            sample_bgr_frame,
            target_width=640,
            target_height=360,
            to_rgb=True,
            enhance_contrast=True,
        )
        assert processed.shape == (360, 640, 3)
        assert processed.dtype == np.uint8

    def test_compute_focal_length_geometry(self, processor: CameraProcessor) -> None:
        # At FOV = 90 degrees, tan(FOV/2) = tan(45 deg) = 1.0.
        # f = (width / 2) / 1.0 = width / 2.
        focal_90 = processor.compute_focal_length(image_width=1280, fov_degrees=90.0)
        assert focal_90 == pytest.approx(640.0, abs=1e-5)

        focal_60 = processor.compute_focal_length(image_width=1280, fov_degrees=60.0)
        # tan(30 deg) = 1 / sqrt(3) ≈ 0.57735
        expected_focal_60 = 640.0 / np.tan(np.radians(30.0))
        assert focal_60 == pytest.approx(expected_focal_60, abs=1e-5)

    def test_compute_focal_length_invalid_inputs(self, processor: CameraProcessor) -> None:
        with pytest.raises(ValueError, match="width must be positive"):
            processor.compute_focal_length(image_width=0, fov_degrees=90.0)

        with pytest.raises(ValueError, match="FOV must be between 0 and 180"):
            processor.compute_focal_length(image_width=1280, fov_degrees=0.0)

        with pytest.raises(ValueError, match="FOV must be between 0 and 180"):
            processor.compute_focal_length(image_width=1280, fov_degrees=180.0)

    def test_get_camera_intrinsics_matrix(self, processor: CameraProcessor) -> None:
        focal, k_matrix = processor.get_camera_intrinsics(
            width=1280, height=720, fov_degrees=90.0
        )
        assert focal == pytest.approx(640.0, abs=1e-5)
        assert k_matrix.shape == (3, 3)
        assert k_matrix[0, 0] == pytest.approx(640.0, abs=1e-5)  # fx
        assert k_matrix[1, 1] == pytest.approx(640.0, abs=1e-5)  # fy
        assert k_matrix[0, 2] == pytest.approx(640.0, abs=1e-5)  # cx
        assert k_matrix[1, 2] == pytest.approx(360.0, abs=1e-5)  # cy
        assert k_matrix[2, 2] == 1.0


# ==============================================================================
# 2. ObjectDetector & RawDetection Tests
# ==============================================================================

class TestRawDetection:
    """Tests for the RawDetection perception primitive."""

    def test_raw_detection_properties_and_access(self) -> None:
        det = RawDetection(
            bbox=[10.0, 20.0, 100.0, 200.0],
            object_type="car",
            confidence=0.88,
            class_id=2,
        )
        assert det.bbox == [10.0, 20.0, 100.0, 200.0]
        assert det.object_type == "car"
        assert det.confidence == 0.88
        assert det.class_id == 2

        # Subscript access
        assert det["bbox"] == [10.0, 20.0, 100.0, 200.0]
        assert det["object_type"] == "car"

        # Dict representation
        d_dict = det.to_dict()
        assert d_dict["object_type"] == "car"
        assert d_dict["confidence"] == 0.88


class TestObjectDetector:
    """Tests for ObjectDetector loading, inference, filtering, and error handling."""

    @pytest.fixture
    def valid_frame(self) -> np.ndarray:
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def test_model_and_device_default_to_settings(self) -> None:
        detector = ObjectDetector()
        assert detector.model_name == settings.YOLO_MODEL_PATH
        assert detector.device == settings.YOLO_DEVICE
        assert detector.confidence_threshold == settings.DETECTION_CONFIDENCE_THRESHOLD

    def test_model_none_placeholder_behavior(self, valid_frame: np.ndarray) -> None:
        det = ObjectDetector(model_name=None)
        status = det.get_status()

        assert status["module"] == "object_detector"
        assert status["model_loaded"] is False
        assert status["model_name"] == "none (placeholder)"
        assert status["status"] == "initialized"

        # detect() on valid frame returns empty list without error
        res = det.detect(valid_frame)
        assert isinstance(res, list)
        assert len(res) == 0
        assert det.get_status()["total_detection_calls"] == 1

    def test_detect_handles_none_and_invalid_inputs(self) -> None:
        # With placeholder detector
        det = ObjectDetector(model_name=None)
        assert det.detect(None) == []
        assert det.detect(np.array([])) == []
        assert det.detect("string_not_an_image") == []
        assert det.detect(np.zeros((10, 10, 5), dtype=np.uint8)) == []  # 5-dim
        assert det.detect(np.zeros((10, 10, 3), dtype=np.int64)) == []  # wrong dtype

    def test_detect_handles_invalid_inputs_without_loading_model(self) -> None:
        # Lazy loading should NOT trigger model download/loading for invalid inputs
        det = ObjectDetector(model_name="yolov8n.pt", lazy_load=True)
        assert det.detect(None) == []
        assert det.detect(np.array([])) == []
        assert det.get_status()["model_loaded"] is False

    def test_load_failure_raises_clear_runtime_error(self) -> None:
        with patch("ultralytics.YOLO", side_effect=Exception("Weights corrupt or missing")):
            with pytest.raises(RuntimeError, match="Failed to load YOLO model"):
                ObjectDetector(model_name="corrupt.pt", lazy_load=False)

    def test_uses_settings_confidence_threshold_by_default(self) -> None:
        det = ObjectDetector(model_name=None)
        assert det.confidence_threshold == settings.DETECTION_CONFIDENCE_THRESHOLD

        custom_det = ObjectDetector(model_name=None, confidence_threshold=0.85)
        assert custom_det.confidence_threshold == 0.85

    def _create_mock_yolo_result(self, raw_detections_info: List[Dict[str, Any]]) -> MagicMock:
        """Helper to create a mock Ultralytics Results object."""
        mock_result = MagicMock()
        mock_result.names = {
            0: "person",
            1: "bicycle",
            2: "car",
            3: "motorcycle",
            5: "bus",
            7: "truck",
            9: "traffic light",
            11: "stop sign",
            16: "dog",
            56: "chair",
        }

        mock_boxes = []
        for info in raw_detections_info:
            box = MagicMock()
            box.cls = np.array([info["cls_id"]])
            box.conf = np.array([info["conf"]])
            box.xyxy = np.array([info["xyxy"]])
            mock_boxes.append(box)

        mock_result.boxes = mock_boxes
        return mock_result

    def _create_mock_yolo_model(self, result: Any) -> MagicMock:
        """Configure a model mock with the Ultralytics predict() interface."""
        mock_model = MagicMock()
        mock_model.predict.return_value = [result]
        mock_model.names = result.names
        return mock_model

    def test_mock_yolo_inference_and_class_mapping(self, valid_frame: np.ndarray) -> None:
        """Verify COCO class mapping for all required autonomous driving classes."""
        mock_boxes_info = [
            {"cls_id": 0, "conf": 0.91, "xyxy": [10.0, 20.0, 50.0, 100.0]},   # person -> pedestrian
            {"cls_id": 2, "conf": 0.85, "xyxy": [60.0, 70.0, 200.0, 180.0]},  # car -> car
            {"cls_id": 7, "conf": 0.78, "xyxy": [210.0, 50.0, 400.0, 300.0]}, # truck -> truck
            {"cls_id": 5, "conf": 0.82, "xyxy": [15.0, 10.0, 180.0, 250.0]},  # bus -> bus
            {"cls_id": 3, "conf": 0.75, "xyxy": [30.0, 40.0, 70.0, 110.0]},   # motorcycle -> motorcycle
            {"cls_id": 1, "conf": 0.65, "xyxy": [80.0, 90.0, 110.0, 150.0]},  # bicycle -> bicycle
        ]
        mock_res = self._create_mock_yolo_result(mock_boxes_info)
        mock_model = self._create_mock_yolo_model(mock_res)

        det = ObjectDetector(model_name="mock_yolo.pt", model=mock_model)
        assert det.get_status()["model_loaded"] is True

        detections = det.detect(valid_frame)
        assert len(detections) == 6

        type_map = {d.class_id: d.object_type for d in detections}
        assert type_map[0] == "pedestrian"
        assert type_map[2] == "car"
        assert type_map[7] == "truck"
        assert type_map[5] == "bus"
        assert type_map[3] == "motorcycle"
        assert type_map[1] == "bicycle"

        # Verify bbox and confidence extraction
        first = detections[0]
        assert first.bbox == [10.0, 20.0, 50.0, 100.0]
        assert first.confidence == pytest.approx(0.91, abs=1e-4)

    def test_retains_all_model_classes_and_maps_known_classes(
        self, valid_frame: np.ndarray
    ) -> None:
        """Keep supported model classes while normalizing known traffic labels."""
        mock_boxes_info = [
            {"cls_id": 2, "conf": 0.88, "xyxy": [10.0, 20.0, 50.0, 60.0]},    # car (KEEP)
            {"cls_id": 9, "conf": 0.95, "xyxy": [100.0, 10.0, 120.0, 40.0]},  # traffic light (IGNORE)
            {"cls_id": 11, "conf": 0.89, "xyxy": [200.0, 30.0, 240.0, 70.0]}, # stop sign (IGNORE)
            {"cls_id": 16, "conf": 0.77, "xyxy": [50.0, 80.0, 70.0, 100.0]},  # dog (IGNORE)
            {"cls_id": 56, "conf": 0.62, "xyxy": [80.0, 90.0, 110.0, 130.0]}, # chair (IGNORE)
            {"cls_id": 0, "conf": 0.92, "xyxy": [15.0, 25.0, 45.0, 85.0]},    # person (KEEP)
        ]
        mock_res = self._create_mock_yolo_result(mock_boxes_info)
        mock_model = self._create_mock_yolo_model(mock_res)

        det = ObjectDetector(model_name="mock_yolo.pt", model=mock_model)
        detections = det.detect(valid_frame)

        assert len(detections) == len(mock_boxes_info)
        detected_types = {d.object_type for d in detections}
        assert detected_types == {
            "car",
            "traffic_light",
            "stop_sign",
            "dog",
            "chair",
            "pedestrian",
        }

    def test_confidence_threshold_passed_to_model(self, valid_frame: np.ndarray) -> None:
        """Verify the confidence threshold is properly passed to the YOLO inference call."""
        mock_res = self._create_mock_yolo_result([])
        mock_model = self._create_mock_yolo_model(mock_res)

        det = ObjectDetector(
            model_name="mock_yolo.pt",
            confidence_threshold=0.72,
            device="cpu",
            model=mock_model,
        )
        det.detect(valid_frame)

        mock_model.predict.assert_called_once_with(
            source=valid_frame,
            conf=0.72,
            iou=settings.YOLO_NMS_IOU,
            device="cpu",
            classes=None,
            verbose=False,
        )

    def test_detect_objects_returns_shared_models_without_fake_motion(
        self, valid_frame: np.ndarray
    ) -> None:
        mock_result = self._create_mock_yolo_result([
            {"cls_id": 2, "conf": 0.88, "xyxy": [10.0, 20.0, 50.0, 60.0]},
        ])
        mock_model = self._create_mock_yolo_model(mock_result)
        detector = ObjectDetector(model_name="mock_yolo.pt", model=mock_model)

        detections = detector.detect_objects(valid_frame)

        assert len(detections) == 1
        detection = detections[0]
        assert isinstance(detection, DetectedObject)
        assert detection.object_type == "car"
        assert detection.confidence == pytest.approx(0.88)
        assert detection.bbox == [10.0, 20.0, 50.0, 60.0]
        assert detection.distance is None
        assert detection.relative_speed is None

    def test_detect_objects_returns_empty_for_no_yolo_boxes(
        self, valid_frame: np.ndarray
    ) -> None:
        mock_model = self._create_mock_yolo_model(self._create_mock_yolo_result([]))
        detector = ObjectDetector(model_name="mock_yolo.pt", model=mock_model)

        assert detector.detect_objects(valid_frame) == []

    def test_supports_list_names_and_preserves_unknown_classes(
        self, valid_frame: np.ndarray
    ) -> None:
        result = MagicMock()
        result.names = ["person", "traffic light", "traffic cone"]
        result.boxes = [
            SimpleNamespace(cls=np.array([0]), conf=np.array([0.8]), xyxy=np.array([[1, 1, 8, 8]])),
            SimpleNamespace(cls=np.array([1]), conf=np.array([0.9]), xyxy=np.array([[9, 1, 16, 8]])),
            SimpleNamespace(cls=np.array([2]), conf=np.array([0.7]), xyxy=np.array([[17, 1, 24, 8]])),
        ]
        model = self._create_mock_yolo_model(result)
        # The model's names are the authoritative class metadata.
        model.names = result.names

        detections = ObjectDetector(model_name="mock.pt", model=model).detect(valid_frame)

        assert [d.object_type for d in detections] == [
            "pedestrian",
            "traffic_light",
            "traffic_cone",
        ]

    def test_confidence_threshold_filters_returned_boxes(
        self, valid_frame: np.ndarray
    ) -> None:
        result = MagicMock()
        result.names = {2: "car"}
        result.boxes = [
            SimpleNamespace(cls=np.array([2]), conf=np.array([0.71]), xyxy=np.array([[1, 1, 8, 8]])),
            SimpleNamespace(cls=np.array([2]), conf=np.array([0.50]), xyxy=np.array([[9, 1, 16, 8]])),
        ]
        model = self._create_mock_yolo_model(result)
        detector = ObjectDetector(
            model_name="mock.pt",
            confidence_threshold=0.7,
            model=model,
        )

        detections = detector.detect(valid_frame)

        assert len(detections) == 1
        assert detections[0].confidence == pytest.approx(0.71)

    def test_missing_boxes_and_malformed_bboxes_are_skipped(
        self, valid_frame: np.ndarray
    ) -> None:
        missing_boxes = MagicMock()
        missing_boxes.boxes = None
        missing_boxes.names = {2: "car"}

        malformed_boxes = MagicMock()
        malformed_boxes.names = {2: "car"}
        malformed_boxes.boxes = [
            SimpleNamespace(cls=np.array([2]), conf=np.array([0.8]), xyxy=np.array([[1, 2, 3]])),
            SimpleNamespace(cls=np.array([2]), conf=np.array([0.8]), xyxy=np.array([[10, 10, 5, 5]])),
            SimpleNamespace(cls=np.array([2]), conf=np.array([0.8]), xyxy=np.array([[1, 1, 8, 8]])),
        ]
        model = MagicMock()
        model.predict.return_value = [missing_boxes, malformed_boxes]
        model.names = {2: "car"}

        detections = ObjectDetector(model_name="mock.pt", model=model).detect(valid_frame)

        assert len(detections) == 1
        assert detections[0].bbox == [1.0, 1.0, 8.0, 8.0]

    def test_mock_ground_truth_adapter_scales_boxes_to_resized_frame(self) -> None:
        detections = [
            DetectedObject(
                object_id="mock-car",
                object_type="car",
                confidence=0.87,
                bbox=[10.0, 20.0, 30.0, 50.0],
            )
        ]

        raw = adapt_ground_truth_detections(
            detections,
            source_size=(100, 100),
            target_size=(200, 150),
        )

        assert len(raw) == 1
        assert raw[0].bbox == [20.0, 30.0, 60.0, 75.0]
        assert raw[0].object_type == "car"
        assert raw[0].confidence == pytest.approx(0.87)

    def test_mock_ground_truth_adapter_rejects_invalid_dimensions_and_boxes(self) -> None:
        detection = DetectedObject(
            object_id="mock-car",
            object_type="car",
            confidence=0.87,
        )
        with pytest.raises(ValueError, match="dimensions must be positive"):
            adapt_ground_truth_detections([detection], (0, 10), (20, 20))
        with pytest.raises(ValueError, match="four-coordinate bounding box"):
            adapt_ground_truth_detections([detection], (10, 10), (20, 20))

    def test_predict_detections_work_with_pipeline_and_risk_engine(
        self, valid_frame: np.ndarray
    ) -> None:
        result = self._create_mock_yolo_result([
            {"cls_id": 2, "conf": 0.9, "xyxy": [100.0, 100.0, 200.0, 260.0]},
        ])
        detector = ObjectDetector(
            model_name="mock.pt",
            model=self._create_mock_yolo_model(result),
        )

        detections = PerceptionPipeline(detector=detector).process_frame(
            valid_frame,
            timestamp=1.0,
        )
        assessment = RiskEngine().calculate_risk(detections, VehicleState())

        assert len(detections) == 1
        assert detections[0].distance is not None and detections[0].distance > 0
        assert detections[0].relative_speed == 0.0
        assert 0.0 <= assessment.risk_score <= 1.0


# ==============================================================================
# 3. ObjectTracker & TrackedDetection Tests
# ==============================================================================

class TestComputeIoU:
    """Tests for the bounding-box Intersection-over-Union utility."""

    def test_identical_boxes_return_one(self) -> None:
        box = [10.0, 10.0, 50.0, 50.0]
        assert compute_iou(box, box) == pytest.approx(1.0)

    def test_disjoint_boxes_return_zero(self) -> None:
        box_a = [0.0, 0.0, 10.0, 10.0]
        box_b = [20.0, 20.0, 30.0, 30.0]
        assert compute_iou(box_a, box_b) == pytest.approx(0.0)

    def test_partial_overlap_calculation(self) -> None:
        # Box A: [0, 0, 10, 10], Area = 100
        # Box B: [5, 0, 15, 10], Area = 100
        # Intersection: [5, 0, 10, 10], Area = 5 * 10 = 50
        # Union: 100 + 100 - 50 = 150
        # IoU: 50 / 150 = 1/3
        box_a = [0.0, 0.0, 10.0, 10.0]
        box_b = [5.0, 0.0, 15.0, 10.0]
        assert compute_iou(box_a, box_b) == pytest.approx(50.0 / 150.0, abs=1e-5)

    def test_invalid_box_lengths_return_zero(self) -> None:
        assert compute_iou([], [1, 2, 3, 4]) == 0.0
        assert compute_iou([1, 2], [1, 2, 3, 4]) == 0.0


class TestTrackedDetection:
    """Tests for the TrackedDetection perception primitive."""

    def test_tracked_detection_attributes_and_dict(self) -> None:
        td = TrackedDetection(
            object_id="track_001",
            bbox=[10.0, 20.0, 100.0, 200.0],
            object_type="car",
            confidence=0.89,
            class_id=2,
            time_since_update=0,
            hits=3,
            age=3,
        )
        assert td.object_id == "track_001"
        assert td["object_id"] == "track_001"
        assert td["bbox"] == [10.0, 20.0, 100.0, 200.0]
        assert td.hits == 3

        d_dict = td.to_dict()
        assert d_dict["object_id"] == "track_001"
        assert d_dict["hits"] == 3
        assert d_dict["confidence"] == 0.89


class TestObjectTracker:
    """Comprehensive tests for ObjectTracker behavior and lifecycle."""

    @pytest.fixture
    def tracker(self) -> ObjectTracker:
        return ObjectTracker(iou_threshold=0.3, max_age=3)

    def test_1_first_detection_receives_an_id(self, tracker: ObjectTracker) -> None:
        """First detection in a scene receives a clean sequential ID."""
        detections = [
            RawDetection(bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9)
        ]
        tracked = tracker.update(detections)

        assert len(tracked) == 1
        assert tracked[0].object_id == "track_001"
        assert tracked[0].object_type == "car"
        assert tracked[0].hits == 1
        assert tracked[0].age == 1
        assert tracker.total_tracks_created == 1

    def test_2_same_object_consecutive_frames_keeps_same_id(self, tracker: ObjectTracker) -> None:
        """Same object moving slightly across consecutive frames preserves its ID."""
        frame1 = [
            RawDetection(bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9)
        ]
        tracked1 = tracker.update(frame1)
        assert tracked1[0].object_id == "track_001"

        # Frame 2: small shift (high IoU)
        frame2 = [
            RawDetection(bbox=[102.0, 101.0, 202.0, 201.0], object_type="car", confidence=0.88)
        ]
        tracked2 = tracker.update(frame2)
        assert len(tracked2) == 1
        assert tracked2[0].object_id == "track_001"
        assert tracked2[0].hits == 2
        assert tracked2[0].age == 2
        assert tracked2[0].bbox == [102.0, 101.0, 202.0, 201.0]

    def test_3_two_different_objects_receive_different_ids(self, tracker: ObjectTracker) -> None:
        """Distinct objects in the same frame receive unique non-colliding IDs."""
        frame = [
            RawDetection(bbox=[50.0, 50.0, 120.0, 120.0], object_type="car", confidence=0.92),
            RawDetection(bbox=[300.0, 300.0, 350.0, 420.0], object_type="pedestrian", confidence=0.85),
        ]
        tracked = tracker.update(frame)

        assert len(tracked) == 2
        ids = {t.object_id for t in tracked}
        assert ids == {"track_001", "track_002"}

    def test_4_objects_can_enter_the_frame(self, tracker: ObjectTracker) -> None:
        """New object entering in a subsequent frame is assigned a new unique ID."""
        # Frame 1: only car
        frame1 = [
            RawDetection(bbox=[50.0, 50.0, 120.0, 120.0], object_type="car", confidence=0.9)
        ]
        tracked1 = tracker.update(frame1)
        assert len(tracked1) == 1
        assert tracked1[0].object_id == "track_001"

        # Frame 2: car continues, and a pedestrian enters
        frame2 = [
            RawDetection(bbox=[52.0, 51.0, 122.0, 121.0], object_type="car", confidence=0.9),
            RawDetection(bbox=[200.0, 200.0, 240.0, 300.0], object_type="pedestrian", confidence=0.8),
        ]
        tracked2 = tracker.update(frame2)
        assert len(tracked2) == 2

        track_map = {t.object_type: t.object_id for t in tracked2}
        assert track_map["car"] == "track_001"
        assert track_map["pedestrian"] == "track_002"

    def test_5_missing_detections_age_correctly(self, tracker: ObjectTracker) -> None:
        """Track increments time_since_update when an object is momentarily missed."""
        frame1 = [
            RawDetection(bbox=[50.0, 50.0, 120.0, 120.0], object_type="car", confidence=0.9)
        ]
        tracker.update(frame1)

        t1 = tracker.get_track("track_001")
        assert t1 is not None
        assert t1.time_since_update == 0
        assert t1.age == 1

        # Frame 2: object undetected
        tracked2 = tracker.update([])
        assert len(tracked2) == 0  # not observed in current frame

        t2 = tracker.get_track("track_001")
        assert t2 is not None
        assert t2.time_since_update == 1
        assert t2.age == 2

        # Frame 3: object still undetected
        tracker.update([])
        t3 = tracker.get_track("track_001")
        assert t3 is not None
        assert t3.time_since_update == 2
        assert t3.age == 3

    def test_6_stale_tracks_are_eventually_removed(self) -> None:
        """Track exceeding max_age missing frames is permanently pruned."""
        tracker = ObjectTracker(iou_threshold=0.3, max_age=2)

        # Frame 1: Spawn track_001
        tracker.update([
            RawDetection(bbox=[50.0, 50.0, 120.0, 120.0], object_type="car", confidence=0.9)
        ])
        assert tracker.track_count == 1

        # Frame 2: Miss 1 (time_since_update=1 <= max_age 2)
        tracker.update([])
        assert tracker.track_count == 1

        # Frame 3: Miss 2 (time_since_update=2 <= max_age 2)
        tracker.update([])
        assert tracker.track_count == 1

        # Frame 4: Miss 3 (time_since_update=3 > max_age 2) -> PRUNED
        tracker.update([])
        assert tracker.track_count == 0
        assert tracker.get_track("track_001") is None

    def test_7_different_object_classes_are_not_incorrectly_matched(
        self, tracker: ObjectTracker
    ) -> None:
        """Detections with overlapping bboxes but different classes must not match."""
        # Frame 1: Car at [100, 100, 200, 200]
        tracker.update([
            RawDetection(bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9)
        ])
        assert tracker.get_track("track_001").object_type == "car"

        # Frame 2: Pedestrian at the exact same coordinates (100% IoU with car track)
        tracked2 = tracker.update([
            RawDetection(bbox=[100.0, 100.0, 200.0, 200.0], object_type="pedestrian", confidence=0.85)
        ])

        assert len(tracked2) == 1
        # Must spawn a new track because class differs
        assert tracked2[0].object_id == "track_002"
        assert tracked2[0].object_type == "pedestrian"

        # Old car track should be missed
        car_track = tracker.get_track("track_001")
        assert car_track is not None
        assert car_track.time_since_update == 1

    def test_8_iou_threshold_is_respected(self) -> None:
        """Detections below the IoU threshold do not match existing tracks."""
        tracker = ObjectTracker(iou_threshold=0.5, max_age=3)

        # Frame 1: Object at [100, 100, 200, 200] (area = 10000)
        tracker.update([
            RawDetection(bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9)
        ])

        # Frame 2: Large jump to [180, 100, 280, 200]
        # Overlap: [180, 100, 200, 200] -> width 20, height 100 -> area 2000
        # Union: 10000 + 10000 - 2000 = 18000
        # IoU = 2000 / 18000 ≈ 0.111 (< 0.5 threshold)
        tracked2 = tracker.update([
            RawDetection(bbox=[180.0, 100.0, 280.0, 200.0], object_type="car", confidence=0.9)
        ])

        assert len(tracked2) == 1
        # Low IoU -> considered a new object
        assert tracked2[0].object_id == "track_002"
        # Old track aged
        t1 = tracker.get_track("track_001")
        assert t1 is not None
        assert t1.time_since_update == 1

    def test_9_multiple_objects_maintain_stable_ids(self, tracker: ObjectTracker) -> None:
        """Multiple vehicles moving across several frames maintain stable IDs."""
        # 3 vehicles moving +2 px right per frame
        v1_base = [50.0, 100.0, 120.0, 180.0]
        v2_base = [200.0, 100.0, 280.0, 180.0]
        v3_base = [400.0, 100.0, 500.0, 200.0]

        for step in range(5):
            detections = [
                RawDetection(
                    bbox=[v1_base[0] + step * 2, v1_base[1], v1_base[2] + step * 2, v1_base[3]],
                    object_type="car",
                    confidence=0.9,
                ),
                RawDetection(
                    bbox=[v2_base[0] + step * 2, v2_base[1], v2_base[2] + step * 2, v2_base[3]],
                    object_type="car",
                    confidence=0.88,
                ),
                RawDetection(
                    bbox=[v3_base[0] + step * 2, v3_base[1], v3_base[2] + step * 2, v3_base[3]],
                    object_type="truck",
                    confidence=0.85,
                ),
            ]
            tracked = tracker.update(detections)
            assert len(tracked) == 3

            id_map = {t.bbox[0]: t.object_id for t in tracked}
            v1_x1 = v1_base[0] + step * 2
            v2_x1 = v2_base[0] + step * 2
            v3_x1 = v3_base[0] + step * 2

            assert id_map[v1_x1] == "track_001"
            assert id_map[v2_x1] == "track_002"
            assert id_map[v3_x1] == "track_003"

    def test_tracker_reset_clears_state(self, tracker: ObjectTracker) -> None:
        """Reset clears active tracks and resets ID counter."""
        tracker.update([
            RawDetection(bbox=[10.0, 10.0, 50.0, 50.0], object_type="car", confidence=0.9)
        ])
        assert tracker.track_count == 1
        assert tracker.total_tracks_created == 1

        tracker.reset()
        assert tracker.track_count == 0
        assert tracker.total_tracks_created == 0

        # After reset, next object starts from track_001
        res = tracker.update([
            RawDetection(bbox=[10.0, 10.0, 50.0, 50.0], object_type="car", confidence=0.9)
        ])
        assert res[0].object_id == "track_001"


# ==============================================================================
# 4. DistanceEstimator & Relative Speed Tests
# ==============================================================================

class TestDistanceEstimate:
    """Tests for the DistanceEstimate dataclass primitive."""

    def test_distance_estimate_attributes_and_dict(self) -> None:
        est = DistanceEstimate(
            object_id="track_001",
            distance=18.5,
            relative_speed=-2.5,
            raw_distance=19.0,
            timestamp=100.0,
        )
        assert est.object_id == "track_001"
        assert est.distance == 18.5
        assert est.relative_speed == -2.5
        assert est.raw_distance == 19.0
        assert est.timestamp == 100.0

        # Subscript indexing
        assert est["distance"] == 18.5
        assert est["relative_speed"] == -2.5

        # Dict representation
        d_dict = est.to_dict()
        assert d_dict["object_id"] == "track_001"
        assert d_dict["distance"] == 18.5
        assert d_dict["relative_speed"] == -2.5


class TestDistanceEstimator:
    """Comprehensive tests for monocular distance and relative velocity estimation."""

    @pytest.fixture
    def estimator(self) -> DistanceEstimator:
        # Fixed focal length 640.0 px (matches 1280px width @ 90 FOV)
        return DistanceEstimator(focal_length=640.0, alpha=0.6, max_speed=60.0)

    def test_1_distance_decreases_when_bbox_height_increases(
        self, estimator: DistanceEstimator
    ) -> None:
        """Larger pixel height indicates an object is closer (distance decreases)."""
        det_far = TrackedDetection(
            object_id="t1", bbox=[100.0, 100.0, 200.0, 150.0], object_type="car", confidence=0.9
        )  # height = 50px
        det_near = TrackedDetection(
            object_id="t2", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9
        )  # height = 100px

        dist_far = estimator.calculate_raw_distance(det_far.bbox, det_far.object_type)
        dist_near = estimator.calculate_raw_distance(det_near.bbox, det_near.object_type)

        assert dist_far > dist_near
        # Height doubled -> distance halved
        assert dist_far == pytest.approx(2.0 * dist_near, abs=1e-4)

    def test_2_distance_increases_when_bbox_height_decreases(
        self, estimator: DistanceEstimator
    ) -> None:
        """Smaller pixel height indicates an object is further away (distance increases)."""
        det_near = TrackedDetection(
            object_id="t1", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9
        )  # height = 100px
        det_far = TrackedDetection(
            object_id="t2", bbox=[100.0, 100.0, 200.0, 125.0], object_type="car", confidence=0.9
        )  # height = 25px

        dist_near = estimator.calculate_raw_distance(det_near.bbox, det_near.object_type)
        dist_far = estimator.calculate_raw_distance(det_far.bbox, det_far.object_type)

        assert dist_far > dist_near
        assert dist_far == pytest.approx(4.0 * dist_near, abs=1e-4)

    def test_3_car_distance_uses_car_reference_height(
        self, estimator: DistanceEstimator
    ) -> None:
        """Car uses 1.5m reference height: distance = (640 * 1.5) / 100 = 9.6m."""
        det = TrackedDetection(
            object_id="t1", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9
        )  # height = 100px
        dist = estimator.calculate_raw_distance(det.bbox, det.object_type)

        expected = (640.0 * 1.5) / 100.0
        assert dist == pytest.approx(expected, abs=1e-4)
        assert dist == pytest.approx(9.6, abs=1e-4)

    def test_4_pedestrian_distance_uses_pedestrian_reference_height(
        self, estimator: DistanceEstimator
    ) -> None:
        """Pedestrian uses 1.7m reference height: distance = (640 * 1.7) / 100 = 10.88m."""
        det = TrackedDetection(
            object_id="t1", bbox=[100.0, 100.0, 200.0, 200.0], object_type="pedestrian", confidence=0.9
        )  # height = 100px
        dist = estimator.calculate_raw_distance(det.bbox, det.object_type)

        expected = (640.0 * 1.7) / 100.0
        assert dist == pytest.approx(expected, abs=1e-4)
        assert dist == pytest.approx(10.88, abs=1e-4)

    def test_5_invalid_bounding_box_handled_safely(
        self, estimator: DistanceEstimator
    ) -> None:
        """Inverted or short coordinates return safe max_distance without raising exception."""
        # y2 < y1 (negative height)
        dist_inverted = estimator.calculate_raw_distance([10.0, 100.0, 50.0, 50.0], "car")
        assert dist_inverted == estimator.max_distance

        # Short list
        dist_short = estimator.calculate_raw_distance([10.0, 20.0], "car")
        assert dist_short == estimator.max_distance

    def test_6_zero_pixel_height_does_not_cause_division_by_zero(
        self, estimator: DistanceEstimator
    ) -> None:
        """Zero height does not cause ZeroDivisionError and safely returns max_distance."""
        dist_zero = estimator.calculate_raw_distance([100.0, 50.0, 200.0, 50.0], "car")
        assert dist_zero == estimator.max_distance

    def test_7_first_observation_returns_relative_speed_zero(
        self, estimator: DistanceEstimator
    ) -> None:
        """On first observation, no previous distance exists so relative_speed is 0.0."""
        det = TrackedDetection(
            object_id="car_001", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9
        )
        res = estimator.estimate(det, timestamp=10.0)

        assert res.object_id == "car_001"
        assert res.relative_speed == 0.0
        assert res.distance == pytest.approx(9.6, abs=1e-4)

    def test_8_distance_decreases_relative_speed_is_negative(
        self, estimator: DistanceEstimator
    ) -> None:
        """When an object approaches (distance drops), relative_speed is negative."""
        # Initial position: 20m away (height = 48px -> dist = 640 * 1.5 / 48 = 20.0m)
        det_t1 = TrackedDetection(
            object_id="car_001", bbox=[100.0, 100.0, 200.0, 148.0], object_type="car", confidence=0.9
        )
        # alpha=1.0 for exact unweighted arithmetic in this test
        fast_est = DistanceEstimator(focal_length=640.0, alpha=1.0)
        fast_est.estimate(det_t1, timestamp=0.0)

        # 1 second later: object moved closer to 16m (height = 60px -> dist = 640 * 1.5 / 60 = 16.0m)
        det_t2 = TrackedDetection(
            object_id="car_001", bbox=[100.0, 100.0, 200.0, 160.0], object_type="car", confidence=0.9
        )
        res_t2 = fast_est.estimate(det_t2, timestamp=1.0)

        assert res_t2.distance < 20.0
        # (16.0 - 20.0) / 1.0 = -4.0 m/s
        assert res_t2.relative_speed == pytest.approx(-4.0, abs=1e-3)
        assert res_t2.relative_speed < 0.0

    def test_9_distance_increases_relative_speed_is_positive(
        self, estimator: DistanceEstimator
    ) -> None:
        """When an object moves away (distance grows), relative_speed is positive."""
        fast_est = DistanceEstimator(focal_length=640.0, alpha=1.0)

        # t=0: height = 60px (dist = 16.0m)
        det_t1 = TrackedDetection(
            object_id="car_001", bbox=[100.0, 100.0, 200.0, 160.0], object_type="car", confidence=0.9
        )
        fast_est.estimate(det_t1, timestamp=0.0)

        # t=1: height = 48px (dist = 20.0m) -> moved away
        det_t2 = TrackedDetection(
            object_id="car_001", bbox=[100.0, 100.0, 200.0, 148.0], object_type="car", confidence=0.9
        )
        res_t2 = fast_est.estimate(det_t2, timestamp=1.0)

        assert res_t2.distance > 16.0
        # (20.0 - 16.0) / 1.0 = +4.0 m/s
        assert res_t2.relative_speed == pytest.approx(4.0, abs=1e-3)
        assert res_t2.relative_speed > 0.0

    def test_10_same_distance_relative_speed_is_zero(
        self, estimator: DistanceEstimator
    ) -> None:
        """When distance remains constant across frames, relative_speed is 0.0."""
        det = TrackedDetection(
            object_id="car_001", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9
        )
        estimator.estimate(det, timestamp=0.0)
        res_t2 = estimator.estimate(det, timestamp=0.5)

        assert res_t2.relative_speed == pytest.approx(0.0, abs=1e-6)

    def test_11_invalid_or_repeated_timestamp_handled_safely(
        self, estimator: DistanceEstimator
    ) -> None:
        """Repeated or backward timestamps do not cause division by zero."""
        det = TrackedDetection(
            object_id="car_001", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9
        )
        estimator.estimate(det, timestamp=1.0)

        # Repeated timestamp: dt = 0
        res_repeated = estimator.estimate(det, timestamp=1.0)
        assert res_repeated.relative_speed == 0.0

        # Backward timestamp: dt < 0
        res_backward = estimator.estimate(det, timestamp=0.5)
        assert res_backward.relative_speed == 0.0

        # None timestamp
        res_none = estimator.estimate(det, timestamp=None)
        assert res_none.relative_speed == 0.0

    def test_12_ema_smoothing_behaves_correctly(self) -> None:
        """EMA properly weights new raw distance against previous smoothed distance."""
        # alpha = 0.5 for simple arithmetic
        est = DistanceEstimator(focal_length=640.0, alpha=0.5)

        # Frame 1: dist_raw = 10.0m
        det1 = TrackedDetection(
            object_id="obj_1", bbox=[100.0, 100.0, 200.0, 196.0], object_type="car", confidence=0.9
        )  # h=96px -> 640 * 1.5 / 96 = 10.0m
        r1 = est.estimate(det1, timestamp=0.0)
        assert r1.distance == pytest.approx(10.0, abs=1e-4)

        # Frame 2: dist_raw = 20.0m (h=48px -> 640 * 1.5 / 48 = 20.0m)
        det2 = TrackedDetection(
            object_id="obj_1", bbox=[100.0, 100.0, 200.0, 148.0], object_type="car", confidence=0.9
        )
        r2 = est.estimate(det2, timestamp=1.0)
        # Expected smoothed: 0.5 * 20.0 + 0.5 * 10.0 = 15.0m
        assert r2.raw_distance == pytest.approx(20.0, abs=1e-4)
        assert r2.distance == pytest.approx(15.0, abs=1e-4)

    def test_13_no_extreme_numerical_values_produced(self) -> None:
        """Relative speed spikes are securely clamped to max_speed."""
        # max_speed set to 30.0 m/s
        est = DistanceEstimator(focal_length=640.0, alpha=1.0, max_speed=30.0)

        # Frame 1: 50m
        det1 = TrackedDetection(
            object_id="spiker", bbox=[100.0, 100.0, 200.0, 119.2], object_type="car", confidence=0.9
        )
        est.estimate(det1, timestamp=0.0)

        # Frame 2: Huge distance change over tiny dt (e.g. dt = 0.001s)
        det2 = TrackedDetection(
            object_id="spiker", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9
        )
        r2 = est.estimate(det2, timestamp=0.001)

        # Must not produce an uncontrolled thousands m/s velocity
        assert abs(r2.relative_speed) <= 30.0
        assert r2.relative_speed == -30.0

    def test_batch_estimation_and_pruning(self, estimator: DistanceEstimator) -> None:
        """Batch processing works for multiple tracks and prune_stale cleans history."""
        tracks = [
            TrackedDetection(object_id="car_1", bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9),
            TrackedDetection(object_id="ped_1", bbox=[300.0, 100.0, 350.0, 270.0], object_type="pedestrian", confidence=0.9),
        ]
        results = estimator.estimate_tracks(tracks, timestamp=1.0)

        assert len(results) == 2
        assert results[0].object_id == "car_1"
        assert results[1].object_id == "ped_1"
        assert len(estimator._history) == 2

        # Prune: keep only car_1
        estimator.prune_stale({"car_1"})
        assert len(estimator._history) == 1
        assert "car_1" in estimator._history
        assert "ped_1" not in estimator._history

        # Reset
        estimator.reset()
        assert len(estimator._history) == 0


# ==============================================================================
# 5. PerceptionPipeline Integration Tests
# ==============================================================================

class TestPerceptionPipeline:
    """Integration tests verifying end-to-end flow from BGR frame to DetectedObject[]."""

    @pytest.fixture
    def valid_bgr_frame(self) -> np.ndarray:
        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def test_1_valid_frame_complete_pipeline_executes(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        """Complete pipeline executes on a valid frame and returns DetectedObject list."""
        mock_detector = MagicMock(spec=ObjectDetector)
        mock_detector.detect.return_value = [
            RawDetection(bbox=[600.0, 300.0, 800.0, 500.0], object_type="car", confidence=0.92)
        ]

        pipeline = PerceptionPipeline(detector=mock_detector)
        results = pipeline.process_frame(valid_bgr_frame)

        assert isinstance(results, list)
        assert len(results) == 1
        obj = results[0]
        assert isinstance(obj, DetectedObject)
        assert obj.object_type == "car"
        assert obj.confidence == 0.92

    def test_2_detector_multiple_objects_returns_multiple_detected_objects(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        """Multiple detections in a frame are all processed into DetectedObject instances."""
        mock_detector = MagicMock(spec=ObjectDetector)
        mock_detector.detect.return_value = [
            RawDetection(bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.88),
            RawDetection(bbox=[400.0, 200.0, 460.0, 380.0], object_type="pedestrian", confidence=0.79),
            RawDetection(bbox=[700.0, 150.0, 850.0, 350.0], object_type="truck", confidence=0.85),
        ]

        pipeline = PerceptionPipeline(detector=mock_detector)
        results = pipeline.process_frame(valid_bgr_frame)

        assert len(results) == 3
        types = [o.object_type for o in results]
        assert types == ["car", "pedestrian", "truck"]

    def test_3_object_ids_from_tracker_are_preserved(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        """Tracker IDs remain stable across consecutive frames for the same tracked object."""
        mock_detector = MagicMock(spec=ObjectDetector)
        # Frame 1 and Frame 2 observe the same car slightly moving
        mock_detector.detect.side_effect = [
            [RawDetection(bbox=[500.0, 250.0, 700.0, 450.0], object_type="car", confidence=0.9)],
            [RawDetection(bbox=[502.0, 251.0, 702.0, 451.0], object_type="car", confidence=0.9)],
        ]

        pipeline = PerceptionPipeline(detector=mock_detector)
        out1 = pipeline.process_frame(valid_bgr_frame, timestamp=0.0)
        out2 = pipeline.process_frame(valid_bgr_frame, timestamp=0.05)

        assert len(out1) == 1
        assert len(out2) == 1
        assert out1[0].object_id == "track_001"
        assert out2[0].object_id == "track_001"

    def test_mock_detections_use_tracker_and_distance_stages(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        detector = MagicMock(spec=ObjectDetector)
        pipeline = PerceptionPipeline(
            detector=detector,
            distance_estimator=DistanceEstimator(focal_length=640.0, alpha=1.0),
        )
        first = [
            RawDetection([100.0, 100.0, 160.0, 148.0], "car", 0.91),
            RawDetection([300.0, 100.0, 340.0, 148.0], "pedestrian", 0.82),
        ]
        second = [
            RawDetection([102.0, 100.0, 162.0, 160.0], "car", 0.93),
        ]

        first_frame = pipeline.process_frame(
            valid_bgr_frame,
            timestamp=1.0,
            raw_detections=first,
        )
        second_frame = pipeline.process_frame(
            valid_bgr_frame,
            timestamp=2.0,
            raw_detections=second,
        )

        assert detector.detect.call_count == 0
        assert [item.object_type for item in first_frame] == ["car", "pedestrian"]
        assert [item.object_id for item in first_frame] == ["track_001", "track_002"]
        assert first_frame[0].bbox == first[0].bbox
        assert first_frame[0].confidence == pytest.approx(0.91)
        assert first_frame[1].confidence == pytest.approx(0.82)
        assert first_frame[0].distance == pytest.approx(20.0)
        assert first_frame[0].relative_speed == 0.0
        assert len(second_frame) == 1
        assert second_frame[0].object_id == first_frame[0].object_id
        assert second_frame[0].distance == pytest.approx(16.0)
        assert second_frame[0].relative_speed == pytest.approx(-4.0)

    def test_empty_frame_detections_age_tracks_and_later_reassociate(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        detector = MagicMock(spec=ObjectDetector)
        pipeline = PerceptionPipeline(detector=detector)
        detection = RawDetection(
            [500.0, 250.0, 600.0, 350.0],
            "car",
            0.9,
        )
        first = pipeline.process_frame(valid_bgr_frame, raw_detections=[detection])
        missing = pipeline.process_frame(valid_bgr_frame, raw_detections=[])
        returned = pipeline.process_frame(valid_bgr_frame, raw_detections=[detection])

        assert len(first) == 1
        assert missing == []
        assert len(returned) == 1
        assert returned[0].object_id == first[0].object_id
        assert detector.detect.call_count == 0

    def test_detector_errors_are_not_silently_converted_to_empty_results(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        detector = MagicMock(spec=ObjectDetector)
        detector.detect.side_effect = RuntimeError("inference failed")
        pipeline = PerceptionPipeline(detector=detector)

        with pytest.raises(RuntimeError, match="inference failed"):
            pipeline.process_frame(valid_bgr_frame)

    def test_4_distance_is_populated(self, valid_bgr_frame: np.ndarray) -> None:
        """DetectedObject has a physically meaningful positive distance populated."""
        mock_detector = MagicMock(spec=ObjectDetector)
        mock_detector.detect.return_value = [
            RawDetection(bbox=[500.0, 300.0, 700.0, 460.0], object_type="car", confidence=0.91)
        ]

        pipeline = PerceptionPipeline(detector=mock_detector)
        results = pipeline.process_frame(valid_bgr_frame)

        assert len(results) == 1
        assert results[0].distance > 0.0
        # height = 160px; focal_length = 640px; real_height = 1.5m -> 640 * 1.5 / 160 = 6.0m
        assert results[0].distance == pytest.approx(6.0, abs=0.1)

    def test_5_relative_speed_is_populated(self, valid_bgr_frame: np.ndarray) -> None:
        """DetectedObject has relative_speed populated (0.0 on first frame, numeric on second)."""
        mock_detector = MagicMock(spec=ObjectDetector)
        mock_detector.detect.side_effect = [
            [RawDetection(bbox=[500.0, 300.0, 700.0, 460.0], object_type="car", confidence=0.91)],
            [RawDetection(bbox=[500.0, 300.0, 700.0, 460.0], object_type="car", confidence=0.91)],
        ]

        pipeline = PerceptionPipeline(detector=mock_detector)
        out1 = pipeline.process_frame(valid_bgr_frame, timestamp=1.0)
        assert out1[0].relative_speed == 0.0

        out2 = pipeline.process_frame(valid_bgr_frame, timestamp=2.0)
        assert isinstance(out2[0].relative_speed, float)
        assert out2[0].relative_speed == pytest.approx(0.0, abs=1e-5)

    def test_6_correct_negative_relative_speed_when_object_approaches(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        """Approaching object (growing bbox height) produces negative relative speed."""
        mock_detector = MagicMock(spec=ObjectDetector)
        # alpha=1.0 for exact unweighted arithmetic
        dist_est = DistanceEstimator(focal_length=640.0, alpha=1.0)
        pipeline = PerceptionPipeline(detector=mock_detector, distance_estimator=dist_est)

        # Frame 1: h=48px -> dist = 640 * 1.5 / 48 = 20.0m
        mock_detector.detect.return_value = [
            RawDetection(bbox=[500.0, 100.0, 700.0, 148.0], object_type="car", confidence=0.9)
        ]
        pipeline.process_frame(valid_bgr_frame, timestamp=0.0)

        # Frame 2: h=60px -> dist = 640 * 1.5 / 60 = 16.0m (approached by 4m over 1s)
        mock_detector.detect.return_value = [
            RawDetection(bbox=[500.0, 100.0, 700.0, 160.0], object_type="car", confidence=0.9)
        ]
        out2 = pipeline.process_frame(valid_bgr_frame, timestamp=1.0)

        assert out2[0].relative_speed == pytest.approx(-4.0, abs=1e-3)
        assert out2[0].relative_speed < 0.0  # negative = closing speed

    def test_7_correct_positive_relative_speed_when_object_moves_away(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        """Receding object (shrinking bbox height) produces positive relative speed."""
        mock_detector = MagicMock(spec=ObjectDetector)
        dist_est = DistanceEstimator(focal_length=640.0, alpha=1.0)
        pipeline = PerceptionPipeline(detector=mock_detector, distance_estimator=dist_est)

        # Frame 1: h=60px (16.0m)
        mock_detector.detect.return_value = [
            RawDetection(bbox=[500.0, 100.0, 700.0, 160.0], object_type="car", confidence=0.9)
        ]
        pipeline.process_frame(valid_bgr_frame, timestamp=0.0)

        # Frame 2: h=48px (20.0m) -> moved away by 4m over 1s
        mock_detector.detect.return_value = [
            RawDetection(bbox=[500.0, 100.0, 700.0, 148.0], object_type="car", confidence=0.9)
        ]
        out2 = pipeline.process_frame(valid_bgr_frame, timestamp=1.0)

        assert out2[0].relative_speed == pytest.approx(4.0, abs=1e-3)
        assert out2[0].relative_speed > 0.0

    def test_8_no_detections_returns_empty_list(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        """Frame with zero detections cleanly returns an empty list without fake objects."""
        mock_detector = MagicMock(spec=ObjectDetector)
        mock_detector.detect.return_value = []

        pipeline = PerceptionPipeline(detector=mock_detector)
        results = pipeline.process_frame(valid_bgr_frame)

        assert isinstance(results, list)
        assert len(results) == 0

    def test_9_invalid_or_none_frame_handled_safely(self) -> None:
        """Invalid frames (None, empty, wrong shape) return [] without crashing."""
        pipeline = PerceptionPipeline()

        assert pipeline.process_frame(None) == []
        assert pipeline.process_frame(np.array([])) == []
        assert pipeline.process_frame("not_a_frame") == []
        assert pipeline.process_frame(np.zeros((10, 10, 5), dtype=np.uint8)) == []

    def test_10_timestamp_is_correctly_propagated(
        self, valid_bgr_frame: np.ndarray
    ) -> None:
        """Provided timestamp is accurately attached to the resulting DetectedObject."""
        mock_detector = MagicMock(spec=ObjectDetector)
        mock_detector.detect.return_value = [
            RawDetection(bbox=[100.0, 100.0, 200.0, 200.0], object_type="car", confidence=0.9)
        ]

        pipeline = PerceptionPipeline(detector=mock_detector)
        target_dt = datetime(2026, 10, 6, 15, 30, 45)
        results = pipeline.process_frame(valid_bgr_frame, timestamp=target_dt)

        assert len(results) == 1
        assert results[0].timestamp == target_dt

    def test_pipeline_reset_and_status(self, valid_bgr_frame: np.ndarray) -> None:
        """Pipeline get_status reports diagnostics and reset clears temporal state."""
        pipeline = PerceptionPipeline()
        status = pipeline.get_status()

        assert status["module"] == "perception_pipeline"
        assert status["frames_processed"] == 0
        assert "detector" in status
        assert "tracker" in status
        assert "distance_estimator" in status

        pipeline.process_frame(valid_bgr_frame)
        assert pipeline.get_status()["frames_processed"] == 1

        pipeline.reset()
        assert pipeline.get_status()["frames_processed"] == 0
