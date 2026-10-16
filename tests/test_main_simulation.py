from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import numpy as np
from fastapi.testclient import TestClient

from edgeforge import main as edgeforge_main
from edgeforge.api import app, runtime
from edgeforge.analysis import RiskEngine
from edgeforge.data.models import DetectedObject, RiskAssessment, VehicleState
from edgeforge.perception import RawDetection
from edgeforge.simulation import SensorFrame


def test_mock_simulation_routes_synthetic_detections_through_pipeline_and_api(
    monkeypatch,
) -> None:
    class NoInferenceDetector:
        def detect(self, frame: np.ndarray) -> list[RawDetection]:
            assert frame.ndim == 3
            raise AssertionError("mock mode must not run YOLO inference")

        def get_status(self) -> dict[str, Any]:
            return {"model": "disabled for mock"}

    class StubScenarioRunner:
        backend = "mock"

        def __init__(self) -> None:
            self.frame_index = 0
            self.ground_truth = [
                [
                    DetectedObject(
                        object_id="sim-car",
                        object_type="car",
                        confidence=0.88,
                        bbox=[4.0, 5.0, 12.0, 17.0],
                    ),
                    DetectedObject(
                        object_id="sim-pedestrian",
                        object_type="pedestrian",
                        confidence=0.81,
                        bbox=[20.0, 5.0, 26.0, 17.0],
                    ),
                ],
                [
                    DetectedObject(
                        object_id="sim-car",
                        object_type="car",
                        confidence=0.91,
                        bbox=[4.0, 5.0, 12.0, 21.0],
                    ),
                ],
            ]

        @property
        def latest_mock_ground_truth_detections(self) -> list[DetectedObject]:
            return self.ground_truth[self.frame_index]

        @classmethod
        def from_config(cls, scenario_path: str, backend: str | None = None):
            assert scenario_path == "unused.json"
            assert backend == "mock"
            return cls()

        @contextmanager
        def run(self):
            frames = [
                SensorFrame(
                    timestamp=1.0,
                    frame_number=1,
                    rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                    vehicle_state=VehicleState(speed=2.0),
                ),
                SensorFrame(
                    timestamp=2.0,
                    frame_number=2,
                    rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                    vehicle_state=VehicleState(speed=2.0),
                ),
            ]

            def stream():
                for index, frame in enumerate(frames):
                    self.frame_index = index
                    yield frame

            yield stream()

    monkeypatch.setattr(edgeforge_main, "ObjectDetector", NoInferenceDetector)
    monkeypatch.setattr(
        "edgeforge.simulation.ScenarioRunner",
        StubScenarioRunner,
    )
    monkeypatch.setattr(
        "edgeforge.api.start_api_server",
        lambda: type("StubServer", (), {"should_exit": False})(),
    )
    published: list[dict[str, Any]] = []
    api_client = TestClient(app)
    api_snapshots: list[dict[str, Any]] = []
    original_publish = runtime.publish_frame

    def record_publish(**frame: Any) -> None:
        original_publish(**frame)
        published.append(runtime.snapshot()[1])
        api_snapshots.append(
            api_client.get("/api/v1/simulation/snapshot").json()
        )

    monkeypatch.setattr(runtime, "publish_frame", record_publish)

    try:
        assert edgeforge_main.run_simulation(
            scenario_path="unused.json",
            headless=True,
            backend="mock",
        ) == 0
    finally:
        runtime.stop()

    assert len(published) == 2
    first = published[0]
    second = published[1]
    assert [item["object_type"] for item in first["detections"]] == [
        "car",
        "pedestrian",
    ]
    assert first["detections"][0]["object_id"] == "track_001"
    assert first["detections"][0]["confidence"] == 0.88
    assert first["detections"][0]["bbox"] == [160.0, 112.5, 480.0, 382.5]
    assert second["detections"][0]["object_id"] == "track_001"
    assert second["detections"][0]["distance"] < first["detections"][0]["distance"]
    assert second["detections"][0]["relative_speed"] < 0.0
    assert second["metrics"]["detection_count"] == 1
    assert second["risk_assessment"]["risk_score"] > 0.0
    assert second["risk_assessment"]["risk_level"] in {
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }
    assert api_snapshots[1]["frame_id"] == 2
    assert api_snapshots[1]["detections"][0]["object_id"] == "track_001"
    assert api_snapshots[1]["risk_assessment"]["risk_score"] > 0.0


def test_live_simulation_passes_estimated_objects_to_risk_engine(monkeypatch) -> None:
    class StubDetector:
        calls = 0

        def get_status(self) -> dict[str, Any]:
            return {"model": "test"}

        def detect(self, frame: np.ndarray) -> list[RawDetection]:
            assert frame.shape == (
                edgeforge_main.settings.CAMERA_HEIGHT,
                edgeforge_main.settings.CAMERA_WIDTH,
                3,
            )
            self.calls += 1
            bottom = 260.0 if self.calls == 1 else 300.0
            return [
                RawDetection(
                    bbox=[100.0, 100.0, 200.0, bottom],
                    object_type="car",
                    confidence=0.9,
                )
            ]

    class StubScenarioRunner:
        backend = "carla"

        @classmethod
        def from_config(cls, scenario_path: str, backend: str | None = None):
            assert scenario_path == "unused.json"
            assert backend == "carla"
            return cls()

        @contextmanager
        def run(self):
            yield iter(
                [
                    SensorFrame(
                        timestamp=1.0,
                        frame_number=1,
                        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                        vehicle_state=VehicleState(speed=2.0),
                    ),
                    SensorFrame(
                        timestamp=2.0,
                        frame_number=2,
                        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                        vehicle_state=VehicleState(speed=2.0),
                    ),
                ]
            )

    observed: dict[str, Any] = {"objects": [], "assessments": []}

    class RecordingRiskEngine(RiskEngine):
        def calculate_risk(
            self,
            detected_objects: list[DetectedObject],
            vehicle_state: VehicleState,
        ) -> RiskAssessment:
            observed["objects"].append(detected_objects)
            observed["vehicle_state"] = vehicle_state
            assessment = super().calculate_risk(detected_objects, vehicle_state)
            observed["assessments"].append(assessment)
            return assessment

    monkeypatch.setattr(edgeforge_main, "ObjectDetector", StubDetector)
    monkeypatch.setattr(edgeforge_main, "RiskEngine", RecordingRiskEngine)
    monkeypatch.setattr(
        "edgeforge.simulation.ScenarioRunner",
        StubScenarioRunner,
    )
    monkeypatch.setattr(
        "edgeforge.api.start_api_server",
        lambda: type("StubServer", (), {"should_exit": False})(),
    )
    published_frames: list[dict[str, Any]] = []
    original_publish_frame = runtime.publish_frame

    def record_published_frame(**frame: Any) -> None:
        published_frames.append(frame)
        original_publish_frame(**frame)

    monkeypatch.setattr(runtime, "publish_frame", record_published_frame)

    assert edgeforge_main.run_simulation(
        scenario_path="unused.json",
        headless=True,
        backend="carla",
    ) == 0

    objects_by_frame = observed["objects"]
    assert len(objects_by_frame) == 2
    first_detection = objects_by_frame[0][0]
    second_detection = objects_by_frame[1][0]
    assert first_detection.object_type == "car"
    assert first_detection.distance is not None and first_detection.distance > 0
    assert first_detection.relative_speed == 0.0
    assert second_detection.distance is not None and second_detection.distance > 0
    assert second_detection.relative_speed is not None
    assert second_detection.relative_speed < 0.0

    # The risk engine accepted the estimated output and returned a normal result.
    assert isinstance(observed["vehicle_state"], VehicleState)
    assert len(observed["assessments"]) == 2
    assert all(
        isinstance(assessment, RiskAssessment)
        and 0.0 <= assessment.risk_score <= 1.0
        for assessment in observed["assessments"]
    )
    assert len(published_frames) == 2
    assert published_frames[-1]["frame_id"] == 2
    assert published_frames[-1]["detections"][0].object_type == "car"
    assert published_frames[-1]["metrics"]["detection_count"] == 1
