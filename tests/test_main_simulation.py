from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import numpy as np

from edgeforge import main as edgeforge_main
from edgeforge.analysis import RiskEngine
from edgeforge.data.models import DetectedObject, RiskAssessment, VehicleState
from edgeforge.perception import RawDetection
from edgeforge.simulation import SensorFrame


def test_live_simulation_passes_estimated_objects_to_risk_engine(monkeypatch) -> None:
    class StubDetector:
        calls = 0

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
