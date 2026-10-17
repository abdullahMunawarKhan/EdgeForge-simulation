"""Regression tests for Live CARLA + YOLO perception evaluation repair.

Covers:
1. Real CARLA mode cannot use mock ground truth or MockCarlaClient.
2. Missing detector causes a clear failure in live benchmark and execution mode.
3. A YOLO inference exception is not treated as a valid empty detection result.
4. Missing or mismatched frames / invalid image dimensions invalidate the evaluation.
5. Valid live predictions and ground truth produce correct metrics matching SUPPORTED_EVALUATION_CLASSES.
6. Mock-mode isolation and backward compatibility.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from edgeforge.config import settings
from edgeforge.data.models import DetectedObject
from edgeforge.perception.validation import (
    SUPPORTED_EVALUATION_CLASSES,
    GroundTruthObject,
)
from edgeforge.scenarios.benchmark import TestingStrategyBenchmark
from edgeforge.scenarios.executor import (
    ExecutionResult,
    ExecutionStatus,
    ScenarioExecutionManager,
)
from edgeforge.simulation.mock_client import MockCarlaClient
from edgeforge.simulation.scenario_runner import (
    BACKEND_CARLA,
    BACKEND_MOCK,
    ScenarioRunner,
)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------
def _sample_scenario_config(width: int = 640, height: int = 480) -> dict[str, Any]:
    return {
        "name": "live_eval_test_scenario",
        "map": "Town01",
        "weather": "ClearNoon",
        "traffic": {"vehicles": 1, "pedestrians": 1, "bicycles": 0},
        "ego_vehicle": {"spawn_point_index": 0},
        "sensors": {
            "rgb_camera": {"enabled": True, "width": width, "height": height, "fov": 90}
        },
        "duration_seconds": 1.0,
        "fixed_delta_seconds": 0.05,
    }


class DummyMockDetector:
    def __init__(self, predictions: list[DetectedObject] | None = None) -> None:
        self.predictions = predictions if predictions is not None else []

    def detect(self, _frame: np.ndarray) -> list[DetectedObject]:
        return list(self.predictions)


class CrashingDetector:
    def detect(self, _frame: np.ndarray) -> list[DetectedObject]:
        raise RuntimeError("CUDA Out of Memory in YOLO model forward pass!")


# ---------------------------------------------------------------------------
# Case 1: Real CARLA mode cannot use mock ground truth or mock client
# ---------------------------------------------------------------------------
class TestCarlaBackendStrictIsolation:
    def test_scenario_runner_rejects_mock_carla_client_in_carla_mode(self) -> None:
        """CARLA mode explicitly rejects MockCarlaClient."""
        cfg = _sample_scenario_config()
        mock_client = MockCarlaClient()
        with pytest.raises(ValueError, match="Cannot use MockCarlaClient when backend is 'carla'"):
            ScenarioRunner(cfg, backend=BACKEND_CARLA, client=mock_client)

    def test_carla_mode_prohibits_latest_mock_ground_truth_detections(self) -> None:
        """latest_mock_ground_truth_detections raises RuntimeError in CARLA mode."""
        runner = ScenarioRunner.__new__(ScenarioRunner)
        runner._backend = BACKEND_CARLA
        with pytest.raises(
            RuntimeError, match="latest_mock_ground_truth_detections is strictly prohibited in real CARLA mode"
        ):
            _ = runner.latest_mock_ground_truth_detections

    def test_carla_execution_fails_if_mock_detected_objects_leak_into_ground_truth(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Scenario execution fails when mock DetectedObject appears in CARLA ground truth."""
        cfg = _sample_scenario_config()
        h, w = 480, 640
        fake_frame = np.zeros((h, w, 3), dtype=np.uint8)

        # Mock CARLA client reachability
        class MockCarlaClientPass:
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        monkeypatch.setattr("edgeforge.simulation.carla_client.CarlaClient", MockCarlaClientPass)

        class MockRunnerLeakingMockData:
            latest_ground_truth_objects = [
                DetectedObject(
                    object_id="mock_npc_1",
                    object_type="car",
                    confidence=1.0,
                    bbox=[10, 10, 50, 50],
                )
            ]

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            @contextmanager
            def run(self):
                yield [
                    SimpleNamespace(
                        frame_number=1,
                        timestamp=0.05,
                        rgb=fake_frame,
                        rgb_frame_number=1,
                    )
                ]

        monkeypatch.setattr("edgeforge.scenarios.executor.ScenarioRunner", MockRunnerLeakingMockData)

        manager = ScenarioExecutionManager()
        detector = DummyMockDetector()
        result = manager.execute(cfg, backend=BACKEND_CARLA, detector=detector)

        assert result.status == ExecutionStatus.FAILED
        assert result.is_successful is False
        assert "Synthetic ground truth leakage is strictly prohibited" in (result.error_message or "")


# ---------------------------------------------------------------------------
# Case 2: Missing detector causes clear failure in live benchmark and execution
# ---------------------------------------------------------------------------
class TestMissingDetectorFailsLiveEvaluation:
    def test_benchmark_raises_if_carla_backend_without_detector(self) -> None:
        """TestingStrategyBenchmark.run() raises if backend is carla and detector is missing."""
        benchmark = TestingStrategyBenchmark(
            scenario_budget=2,
            max_frames_per_scenario=5,
            backend=BACKEND_CARLA,
            detector=None,
        )
        with pytest.raises(
            RuntimeError, match="Live CARLA benchmark requires a valid detector"
        ):
            benchmark.run()

    def test_executor_fails_when_carla_backend_missing_detector(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ScenarioExecutionManager.execute() returns FAILED when detector is None in CARLA mode."""
        cfg = _sample_scenario_config()

        class MockCarlaClientPass:
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        monkeypatch.setattr("edgeforge.simulation.carla_client.CarlaClient", MockCarlaClientPass)

        manager = ScenarioExecutionManager()
        result = manager.execute(cfg, backend=BACKEND_CARLA, detector=None)

        assert result.status == ExecutionStatus.FAILED
        assert result.is_successful is False
        assert "Live CARLA perception evaluation requires a valid detector" in (result.error_message or "")


# ---------------------------------------------------------------------------
# Case 3: YOLO inference exception is not treated as a valid empty detection
# ---------------------------------------------------------------------------
class TestDetectorExceptionFailsEvaluation:
    def test_detector_inference_exception_causes_execution_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When YOLO raises during inference, executor does NOT treat it as empty detections."""
        cfg = _sample_scenario_config()
        h, w = 480, 640
        fake_frame = np.zeros((h, w, 3), dtype=np.uint8)

        class MockCarlaClientPass:
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        monkeypatch.setattr("edgeforge.simulation.carla_client.CarlaClient", MockCarlaClientPass)

        class MockRunnerWithFrame:
            latest_ground_truth_objects = [GroundTruthObject(101, "car", (10, 10, 50, 50))]

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            @contextmanager
            def run(self):
                yield [
                    SimpleNamespace(
                        frame_number=1,
                        timestamp=0.05,
                        rgb=fake_frame,
                        rgb_frame_number=1,
                    )
                ]

        monkeypatch.setattr("edgeforge.scenarios.executor.ScenarioRunner", MockRunnerWithFrame)

        manager = ScenarioExecutionManager()
        crashing_detector = CrashingDetector()
        result = manager.execute(cfg, backend=BACKEND_CARLA, detector=crashing_detector)

        assert result.status == ExecutionStatus.FAILED
        assert result.is_successful is False
        assert result.metrics is None
        assert "CUDA Out of Memory in YOLO model forward pass!" in (result.error_message or "")


# ---------------------------------------------------------------------------
# Case 4: Missing or mismatched frames invalidate the affected evaluation
# ---------------------------------------------------------------------------
class TestFrameSynchronizationAndDimensionIntegrity:
    def test_missing_rgb_frame_fails_carla_evaluation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When sf.rgb is None in CARLA mode, execution fails with clear error."""
        cfg = _sample_scenario_config()

        class MockCarlaClientPass:
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        monkeypatch.setattr("edgeforge.simulation.carla_client.CarlaClient", MockCarlaClientPass)

        class MockRunnerMissingRgb:
            latest_ground_truth_objects = [GroundTruthObject(101, "car", (10, 10, 50, 50))]

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            @contextmanager
            def run(self):
                yield [
                    SimpleNamespace(
                        frame_number=42,
                        timestamp=0.05,
                        rgb=None,
                        rgb_frame_number=None,
                    )
                ]

        monkeypatch.setattr("edgeforge.scenarios.executor.ScenarioRunner", MockRunnerMissingRgb)

        manager = ScenarioExecutionManager()
        result = manager.execute(cfg, backend=BACKEND_CARLA, detector=DummyMockDetector())

        assert result.status == ExecutionStatus.FAILED
        assert "Missing RGB frame at simulation frame 42" in (result.error_message or "")

    def test_mismatched_frame_number_fails_carla_evaluation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When camera rgb_frame_number != simulation frame_number, evaluation fails."""
        cfg = _sample_scenario_config()
        fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        class MockCarlaClientPass:
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        monkeypatch.setattr("edgeforge.simulation.carla_client.CarlaClient", MockCarlaClientPass)

        class MockRunnerMismatchedFrame:
            latest_ground_truth_objects = [GroundTruthObject(101, "car", (10, 10, 50, 50))]

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            @contextmanager
            def run(self):
                # Camera frame 41 arrived, but simulation ticked to 42
                yield [
                    SimpleNamespace(
                        frame_number=42,
                        timestamp=0.05,
                        rgb=fake_frame,
                        rgb_frame_number=41,
                    )
                ]

        monkeypatch.setattr("edgeforge.scenarios.executor.ScenarioRunner", MockRunnerMismatchedFrame)

        manager = ScenarioExecutionManager()
        result = manager.execute(cfg, backend=BACKEND_CARLA, detector=DummyMockDetector())

        assert result.status == ExecutionStatus.FAILED
        assert "Frame synchronization mismatch: camera frame 41 does not match simulation frame 42" in (
            result.error_message or ""
        )

    def test_invalid_image_dimensions_fails_carla_evaluation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When image dimensions do not match configured sensor spec, evaluation fails."""
        cfg = _sample_scenario_config(width=640, height=480)
        wrong_size_frame = np.zeros((200, 200, 3), dtype=np.uint8)

        class MockCarlaClientPass:
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        monkeypatch.setattr("edgeforge.simulation.carla_client.CarlaClient", MockCarlaClientPass)

        class MockRunnerWrongDimensions:
            latest_ground_truth_objects = [GroundTruthObject(101, "car", (10, 10, 50, 50))]

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            @contextmanager
            def run(self):
                yield [
                    SimpleNamespace(
                        frame_number=1,
                        timestamp=0.05,
                        rgb=wrong_size_frame,
                        rgb_frame_number=1,
                    )
                ]

        monkeypatch.setattr("edgeforge.scenarios.executor.ScenarioRunner", MockRunnerWrongDimensions)

        manager = ScenarioExecutionManager()
        result = manager.execute(cfg, backend=BACKEND_CARLA, detector=DummyMockDetector())

        assert result.status == ExecutionStatus.FAILED
        assert "Image dimension mismatch" in (result.error_message or "")


# ---------------------------------------------------------------------------
# Case 5: Valid live predictions and ground truth produce correct metrics
# ---------------------------------------------------------------------------
class TestValidLivePerceptionEvaluation:
    def test_live_evaluation_computes_correct_metrics_with_supported_classes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Valid detections and ground truth yield correct TP/FP/FN and filter supported classes."""
        cfg = _sample_scenario_config(width=640, height=480)
        valid_frame = np.zeros((480, 640, 3), dtype=np.uint8)

        class MockCarlaClientPass:
            def connect(self) -> None:
                pass

            def disconnect(self) -> None:
                pass

        monkeypatch.setattr("edgeforge.simulation.carla_client.CarlaClient", MockCarlaClientPass)

        # Ground truth: 1 car, 1 pedestrian, and 1 unsupported object (e.g. bench)
        gt = [
            GroundTruthObject(actor_id=1, object_type="car", bbox=(10.0, 10.0, 100.0, 100.0)),
            GroundTruthObject(actor_id=2, object_type="pedestrian", bbox=(150.0, 10.0, 190.0, 80.0)),
            GroundTruthObject(actor_id=3, object_type="bench", bbox=(300.0, 300.0, 350.0, 350.0)),
        ]

        # Predictions: 1 matching car (TP), 1 car in wrong place (FP), 1 unsupported dog (ignored)
        preds = [
            DetectedObject(
                object_id="det_1",
                object_type="car",
                confidence=0.92,
                bbox=[12.0, 10.0, 102.0, 100.0],  # High overlap with car
            ),
            DetectedObject(
                object_id="det_2",
                object_type="car",
                confidence=0.88,
                bbox=[400.0, 200.0, 480.0, 260.0],  # False positive car
            ),
            DetectedObject(
                object_id="det_3",
                object_type="dog",
                confidence=0.75,
                bbox=[50.0, 50.0, 80.0, 80.0],  # Outside supported classes
            ),
        ]

        class MockRunnerValidLive:
            latest_ground_truth_objects = gt

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            @contextmanager
            def run(self):
                yield [
                    SimpleNamespace(
                        frame_number=1,
                        timestamp=0.05,
                        rgb=valid_frame,
                        rgb_frame_number=1,
                    )
                ]

        monkeypatch.setattr("edgeforge.scenarios.executor.ScenarioRunner", MockRunnerValidLive)

        manager = ScenarioExecutionManager()
        detector = DummyMockDetector(predictions=preds)
        result = manager.execute(cfg, backend=BACKEND_CARLA, detector=detector)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.is_successful is True
        assert result.metrics is not None

        # Evaluated supported classes: "car" and "pedestrian"
        # TP = 1 (car match)
        # FP = 1 (unmatched car prediction; "dog" is excluded by SUPPORTED_EVALUATION_CLASSES)
        # FN = 1 (missed pedestrian; "bench" is excluded by SUPPORTED_EVALUATION_CLASSES)
        assert result.metrics.true_positives == 1
        assert result.metrics.false_positives == 1
        assert result.metrics.missed_detections == 1
        assert result.metrics.precision == 0.5
        assert result.metrics.recall == 0.5


# ---------------------------------------------------------------------------
# Case 6: Mock-mode regression tests
# ---------------------------------------------------------------------------
class TestMockModeRegression:
    def test_mock_mode_latest_mock_ground_truth_detections_accessible(self) -> None:
        """In mock mode, latest_mock_ground_truth_detections returns projected mock objects."""
        runner = ScenarioRunner.__new__(ScenarioRunner)
        runner._backend = BACKEND_MOCK
        expected_mock_obj = DetectedObject(
            object_id="mock_1", object_type="car", confidence=0.9, bbox=[0, 0, 10, 10]
        )
        runner._sensor_mgr = SimpleNamespace(latest_ground_truth_objects=[expected_mock_obj])

        assert runner.latest_mock_ground_truth_detections == [expected_mock_obj]
        assert runner.latest_ground_truth_objects == [expected_mock_obj]

    def test_mock_mode_execution_without_detector_uses_synthetic_perception(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """In mock mode, executor without detector uses synthetic degradation safely."""
        cfg = _sample_scenario_config()
        mock_gt = [
            DetectedObject(
                object_id="mock_car",
                object_type="car",
                confidence=1.0,
                distance=10.0,
                relative_speed=0.0,
                bbox=[10, 10, 50, 50],
            )
        ]

        class MockRunnerMockMode:
            latest_ground_truth_objects = mock_gt

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            @contextmanager
            def run(self):
                yield [
                    SimpleNamespace(
                        frame_number=1,
                        timestamp=0.05,
                        rgb=np.zeros((480, 640, 3), dtype=np.uint8),
                        rgb_frame_number=1,
                    )
                ]

        monkeypatch.setattr("edgeforge.scenarios.executor.ScenarioRunner", MockRunnerMockMode)

        manager = ScenarioExecutionManager()
        result = manager.execute(cfg, backend=BACKEND_MOCK, detector=None)

        assert result.status == ExecutionStatus.COMPLETED
        assert result.is_successful is True
        assert result.metrics is not None
        assert result.metrics.frames_processed == 1
        assert result.sim_frames == 1
