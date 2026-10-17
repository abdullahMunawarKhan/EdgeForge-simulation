from __future__ import annotations
import asyncio
import json
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

import cv2
import numpy as np
from fastapi.testclient import TestClient
from edgeforge.analysis import RiskEngine
import edgeforge.api as api_module
from edgeforge.api import app, get_camera_stream, get_camera_view_stream, runtime
from edgeforge.data.history import RunHistoryStore
from edgeforge.data.models import (
    DetectedObject,
    HistoricalRunRecord,
    PerceptionFailureRecord,
    RiskAssessment,
    VehicleState,
)
from edgeforge.perception import (
    CameraProcessor,
    DistanceEstimator,
    ObjectDetector,
    ObjectTracker,
    PerceptionPipeline,
)
from edgeforge.simulation import SensorFrame
from edgeforge.simulation.runner_service import SimulationService

client = TestClient(app)

def setup_function() -> None:
    runtime.stop()

def teardown_function() -> None:
    runtime.stop()

def test_status_and_snapshot_report_disconnected_without_pipeline() -> None:
    status = client.get("/api/v1/simulation/status")
    snapshot = client.get("/api/v1/simulation/snapshot")

    assert status.status_code == 200
    assert status.json()["status"] == "disconnected"
    assert status.json()["frame_id"] is None
    assert snapshot.status_code == 200
    assert snapshot.json()["simulation_status"] == "disconnected"
    assert snapshot.json()["detections"] is None
    assert snapshot.json()["metrics"] is None

def test_snapshot_exposes_published_pipeline_data() -> None:
    conditions = {
        "scenario_id": "night-test",
        "weather_preset": "ClearNoon",
        "backend": "carla",
    }
    runtime.start("carla", conditions)
    runtime.publish_frame(
        backend="carla",
        frame_id=27,
        timestamp=1.35,
        detections=[
            DetectedObject(
                object_id="vehicle-1",
                object_type="car",
                confidence=0.91,
                distance=12.0,
                relative_speed=-1.5,
                bbox=[10.0, 20.0, 80.0, 100.0],
            )
        ],
        scenario_conditions=conditions,
        metrics={"frames_processed": 27, "detection_count": 1},
        risk_assessment=RiskAssessment(risk_score=0.4),
        failures=[
            PerceptionFailureRecord(
                failure_type="missed_detection",
                severity="high",
                frame_id=27,
                object_class="pedestrian",
            )
        ],
    )

    status = client.get("/api/v1/simulation/status").json()
    snapshot = client.get("/api/v1/simulation/snapshot").json()

    assert status["status"] == "running"
    assert status["backend"] == "carla"
    assert status["frame_id"] == 27
    assert snapshot["simulation_status"] == "running"
    assert snapshot["detections"][0]["confidence"] == 0.91
    assert snapshot["detections"][0]["distance"] == 12.0
    assert snapshot["scenario_conditions"] == conditions
    assert snapshot["metrics"] == {"frames_processed": 27, "detection_count": 1}
    assert snapshot["risk_assessment"]["risk_score"] == 0.4
    assert snapshot["failures"][0]["failure_type"] == "missed_detection"


def test_websocket_sends_latest_snapshot() -> None:
    runtime.start("carla", {"scenario_id": "websocket-test", "backend": "carla"})

    with client.websocket_connect("/api/v1/simulation/ws") as websocket:
        message = websocket.receive_json()

    assert message["snapshot"]["simulation_status"] == "starting"
    assert message["snapshot"]["scenario_id"] == "websocket-test"


def test_mock_yolo_pipeline_results_reach_rest_and_websocket() -> None:
    class FakeYoloModel:
        names = {0: "person", 2: "car"}

        def __init__(self) -> None:
            self.frames = [
                [
                    (2, 0.93, [100.0, 100.0, 200.0, 148.0]),
                    (0, 0.84, [300.0, 100.0, 340.0, 148.0]),
                ],
                [(2, 0.91, [102.0, 100.0, 202.0, 160.0])],
            ]

        def predict(self, source: np.ndarray, **kwargs: object) -> list[SimpleNamespace]:
            assert source.shape == (720, 1280, 3)
            assert kwargs["device"] == "cpu"
            boxes = [
                SimpleNamespace(
                    cls=np.array([class_id]),
                    conf=np.array([confidence]),
                    xyxy=np.array([bbox]),
                )
                for class_id, confidence, bbox in self.frames.pop(0)
            ]
            return [SimpleNamespace(boxes=boxes, names=self.names)]

    model = FakeYoloModel()
    detector = ObjectDetector(model_name="mock-yolo.pt", model=model, device="cpu")
    pipeline = PerceptionPipeline(
        camera_processor=CameraProcessor(default_width=1280, default_height=720),
        detector=detector,
        tracker=ObjectTracker(),
        distance_estimator=DistanceEstimator(focal_length=640.0, alpha=1.0),
    )
    risk_engine = RiskEngine()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    ego = VehicleState(speed=2.0)
    conditions = {"scenario_id": "mock-yolo-e2e", "backend": "mock"}
    runtime.start("mock", conditions)

    first_detections = pipeline.process_frame(frame, timestamp=1.0)
    first_risk = risk_engine.calculate_risk(first_detections, ego)
    second_detections = pipeline.process_frame(frame, timestamp=2.0)
    second_risk = risk_engine.calculate_risk(second_detections, ego)
    runtime.publish_frame(
        backend="mock",
        frame_id=2,
        timestamp=2.0,
        detections=second_detections,
        scenario_conditions=conditions,
        metrics={
            "frames_processed": pipeline.get_status()["frames_processed"],
            "detection_count": len(second_detections),
            "pipeline": pipeline.get_status(),
        },
        risk_assessment=second_risk,
    )

    assert [item.object_type for item in first_detections] == ["car", "pedestrian"]
    assert [item.object_id for item in first_detections] == ["track_001", "track_002"]
    assert first_detections[0].bbox == [100.0, 100.0, 200.0, 148.0]
    assert first_detections[0].confidence == 0.93
    assert first_detections[0].distance == 20.0
    assert first_detections[0].relative_speed == 0.0
    assert len(second_detections) == 1
    assert second_detections[0].object_id == first_detections[0].object_id
    assert second_detections[0].object_type == "car"
    assert second_detections[0].distance == 16.0
    assert second_detections[0].relative_speed == -4.0
    assert first_risk.risk_score > 0.0
    assert second_risk.risk_score > 0.0
    assert second_risk.risk_level.value == "MEDIUM"

    response = client.get("/api/v1/simulation/snapshot")
    assert response.status_code == 200
    rest_snapshot = response.json()
    assert rest_snapshot["frame_id"] == 2
    assert rest_snapshot["detections"][0]["object_id"] == "track_001"
    assert rest_snapshot["detections"][0]["object_type"] == "car"
    assert rest_snapshot["detections"][0]["bbox"] == [102.0, 100.0, 202.0, 160.0]
    assert rest_snapshot["detections"][0]["relative_speed"] == -4.0
    assert rest_snapshot["risk_assessment"]["risk_score"] == second_risk.risk_score
    assert rest_snapshot["risk_assessment"]["risk_level"] == "MEDIUM"

    with client.websocket_connect("/api/v1/simulation/ws") as websocket:
        websocket_snapshot = websocket.receive_json()["snapshot"]
    assert websocket_snapshot["frame_id"] == 2
    assert websocket_snapshot["detections"] == rest_snapshot["detections"]
    assert websocket_snapshot["risk_assessment"] == rest_snapshot["risk_assessment"]


def test_fastapi_mock_simulation_service_uses_pipeline_without_yolo(
    monkeypatch, tmp_path,
) -> None:
    class NoInferenceDetector:
        def detect(self, frame: np.ndarray) -> list:
            assert frame.ndim == 3
            raise AssertionError("mock mode must not run YOLO inference")

        def get_status(self) -> dict[str, str]:
            return {"model": "disabled for mock"}

    class StubScenarioRunner:
        backend = "mock"

        def __init__(self, _config: dict, backend: str) -> None:
            assert backend == "mock"
            self.info = SimpleNamespace(
                name="api-mock-pipeline",
                weather_preset="ClearNoon",
                map_name="Town03",
            )
            self.frame_index = 0
            self.ground_truth = [
                [
                    DetectedObject(
                        object_id="mock-car",
                        object_type="car",
                        confidence=0.9,
                        bbox=[4.0, 5.0, 12.0, 17.0],
                    )
                ],
                [
                    DetectedObject(
                        object_id="mock-car",
                        object_type="car",
                        confidence=0.92,
                        bbox=[4.0, 5.0, 12.0, 21.0],
                    )
                ],
            ]

        @property
        def latest_mock_ground_truth_detections(self) -> list[DetectedObject]:
            return self.ground_truth[self.frame_index]

        @contextmanager
        def run(self):
            frames = [
                SensorFrame(
                    timestamp=float(index + 1),
                    frame_number=index + 1,
                    rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                    vehicle_state=VehicleState(speed=2.0),
                )
                for index in range(2)
            ]

            def stream():
                for index, frame in enumerate(frames):
                    self.frame_index = index
                    yield frame

            yield stream()

    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ScenarioRunner",
        StubScenarioRunner,
    )
    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ObjectDetector",
        NoInferenceDetector,
    )
    service = SimulationService(runtime, RunHistoryStore(tmp_path / "pipeline-history"))
    snapshots: list[dict] = []
    original_publish = runtime.publish_frame

    def record_publish(**frame) -> None:
        original_publish(**frame)
        snapshots.append(client.get("/api/v1/simulation/snapshot").json())

    monkeypatch.setattr(runtime, "publish_frame", record_publish)

    service._run_loop("mock", {})

    assert len(snapshots) == 2
    assert snapshots[1]["frame_id"] == 2
    assert snapshots[1]["detections"][0]["object_id"] == "track_001"
    assert snapshots[1]["detections"][0]["confidence"] == 0.92
    assert snapshots[1]["detections"][0]["relative_speed"] < 0.0
    assert snapshots[1]["metrics"]["detection_count"] == 1
    assert snapshots[1]["metrics"]["validation"]["true_positives"] == 1
    assert snapshots[1]["risk_assessment"]["risk_score"] > 0.0
    saved_runs = service.history_store.list_runs()
    assert len(saved_runs) == 1
    assert saved_runs[0].scenario_id == "api-mock-pipeline"
    assert saved_runs[0].frames_processed == 2


def test_mock_live_loop_publishes_and_persists_validation_failures(
    monkeypatch, tmp_path,
) -> None:
    scenario_config = {
        "name": "live-validation-test",
        "weather": {"fog_density": 35.0},
        "traffic_density": "Light",
    }
    ground_truth = [
        DetectedObject(
            object_id="truth-car",
            object_type="car",
            confidence=1.0,
            bbox=[4.0, 5.0, 12.0, 17.0],
        )
    ]

    class NoInferenceDetector:
        def detect(self, _frame: np.ndarray) -> list:
            raise AssertionError("mock mode must not run YOLO inference")

        def get_status(self) -> dict[str, str]:
            return {"model": "disabled for mock"}

    class StubScenarioRunner:
        backend = "mock"
        latest_ground_truth_objects = ground_truth
        latest_mock_ground_truth_detections = ground_truth

        def __init__(self, _config: dict, backend: str) -> None:
            assert backend == "mock"
            self.info = SimpleNamespace(
                name="live-validation-test",
                weather_preset="ClearNoon",
                map_name="Town03",
            )

        @contextmanager
        def run(self):
            yield iter(
                [
                    SensorFrame(
                        timestamp=1.0,
                        frame_number=1,
                        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                        vehicle_state=VehicleState(speed=1.0),
                    )
                ]
            )

    isolated_runtime = api_module.SimulationRuntime()
    store = RunHistoryStore(tmp_path / "live-validation-history")
    service = SimulationService(isolated_runtime, store)
    published_snapshots: list[dict] = []
    websocket_snapshots: list[dict] = []
    original_publish = isolated_runtime.publish_frame

    def record_publish(**frame) -> None:
        original_publish(**frame)
        published_snapshots.append(isolated_runtime.snapshot()[1])
        with client.websocket_connect("/api/v1/simulation/ws") as websocket:
            websocket_snapshots.append(websocket.receive_json()["snapshot"])

    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ScenarioRunner",
        StubScenarioRunner,
    )
    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ObjectDetector",
        NoInferenceDetector,
    )
    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.adapt_ground_truth_detections",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(isolated_runtime, "publish_frame", record_publish)
    monkeypatch.setattr(api_module, "runtime", isolated_runtime)
    monkeypatch.setattr(api_module, "history_store", store)

    service.update_configuration(scenario_config)
    service._run_loop("mock", scenario_config)

    assert len(published_snapshots) == 1
    snapshot = published_snapshots[0]
    assert snapshot["metrics"]["validation"]["missed_detections"] == 1
    failure = snapshot["failures"][0]
    assert failure["failure_type"] == "missed_detection"
    assert failure["failure_id"]
    assert failure["fingerprint"]
    assert failure["run_id"] == snapshot["run_id"]
    assert websocket_snapshots[0]["failures"][0]["failure_id"] == failure["failure_id"]
    assert websocket_snapshots[0]["run_id"] == snapshot["run_id"]

    saved_run = store.get_run(snapshot["run_id"])
    assert saved_run.scenario_conditions["weather"]["fog_density"] == 35.0
    assert saved_run.parameters["scenario_config"] == scenario_config
    saved_failures = store.get_run_failures(snapshot["run_id"])
    assert [item.failure_id for item in saved_failures] == [failure["failure_id"]]
    assert saved_failures[0].fingerprint == failure["fingerprint"]

    history_response = client.get(
        "/api/v1/simulation/history",
        params={"run_id": snapshot["run_id"], "failure_type": "missed_detection"},
    )
    assert history_response.status_code == 200
    history = history_response.json()
    assert [item["run_id"] for item in history["runs"]] == [snapshot["run_id"]]
    assert [item["failure_id"] for item in history["failures"]] == [failure["failure_id"]]
    assert history["coverage"]["total_runs"] == 1


def test_completed_mock_run_evaluates_and_persists_scenario_metrics(
    monkeypatch, tmp_path,
) -> None:
    scenario_config = {
        "name": "scenario-evaluation-test",
        "risk_analysis": {"threshold": 0.75},
    }

    class NoInferenceDetector:
        def detect(self, _frame: np.ndarray) -> list:
            raise AssertionError("Frames without images must not invoke the detector")

        def get_status(self) -> dict[str, str]:
            return {"model": "disabled for test"}

    class ControlledRiskEngine:
        def __init__(self) -> None:
            self.scores = iter([0.8, 0.9, 0.2])

        def calculate_risk(self, _detections, _vehicle_state) -> RiskAssessment:
            return RiskAssessment(risk_score=next(self.scores))

    class StubScenarioRunner:
        backend = "mock"
        latest_ground_truth_objects = []
        latest_mock_ground_truth_detections = []

        def __init__(self, _config: dict, backend: str) -> None:
            assert backend == "mock"
            self.info = SimpleNamespace(
                name=scenario_config["name"],
                weather_preset="ClearNoon",
                map_name="Town03",
            )

        @contextmanager
        def run(self):
            yield iter(
                [
                    SensorFrame(
                        timestamp=1.0,
                        frame_number=1,
                        vehicle_state=VehicleState(speed=1.0),
                    ),
                    SensorFrame(
                        timestamp=2.0,
                        frame_number=2,
                        vehicle_state=VehicleState(speed=1.0),
                        collision_events=[
                            {
                                "timestamp": 2.0,
                                "other_actor": "vehicle.audi.a2",
                                "impulse_norm": 400.0,
                            }
                        ],
                    ),
                    SensorFrame(
                        timestamp=4.0,
                        frame_number=3,
                        vehicle_state=VehicleState(speed=1.0),
                        lane_invasions=[
                            {
                                "timestamp": 4.0,
                                "crossed_markings": ["Solid", "Broken"],
                            },
                            {
                                "timestamp": 4.0,
                                "crossed_markings": ["Solid"],
                            },
                        ],
                    ),
                ]
            )

    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ScenarioRunner",
        StubScenarioRunner,
    )
    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ObjectDetector",
        NoInferenceDetector,
    )
    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.RiskEngine",
        ControlledRiskEngine,
    )
    store = RunHistoryStore(tmp_path / "scenario-evaluation-history")
    service = SimulationService(api_module.SimulationRuntime(), store)

    service._run_loop("mock", scenario_config)

    [saved_run] = store.list_runs(scenario_id=scenario_config["name"])
    assert saved_run.frames_processed == 3
    assert saved_run.scenario_metrics == {
        "max_risk_score": 0.9,
        "time_above_threshold": 3.0,
        "near_collisions_ttc_below_1s": 0.0,
        "collision_count": 1.0,
        "lane_invasion_count": 2.0,
    }
    persisted_json = json.loads(store.run_path(saved_run.run_id).read_text(encoding="utf-8"))
    assert persisted_json["scenario_metrics"] == saved_run.scenario_metrics


def test_completed_mock_run_with_missing_risk_data_still_persists(
    monkeypatch, tmp_path,
) -> None:
    scenario_config = {"name": "scenario-no-risk-samples"}

    class NoInferenceDetector:
        def detect(self, _frame: np.ndarray) -> list:
            raise AssertionError("No image was provided")

        def get_status(self) -> dict[str, str]:
            return {"model": "disabled for test"}

    class StubScenarioRunner:
        backend = "mock"
        latest_ground_truth_objects = []
        latest_mock_ground_truth_detections = []

        def __init__(self, _config: dict, backend: str) -> None:
            assert backend == "mock"
            self.info = SimpleNamespace(
                name=scenario_config["name"],
                weather_preset="ClearNoon",
                map_name="Town03",
            )

        @contextmanager
        def run(self):
            yield iter(
                [
                    SensorFrame(timestamp=3.0, frame_number=1),
                    SensorFrame(timestamp=5.0, frame_number=2),
                ]
            )

    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ScenarioRunner",
        StubScenarioRunner,
    )
    monkeypatch.setattr(
        "edgeforge.simulation.runner_service.ObjectDetector",
        NoInferenceDetector,
    )
    store = RunHistoryStore(tmp_path / "scenario-missing-data-history")
    service = SimulationService(api_module.SimulationRuntime(), store)

    service._run_loop("mock", scenario_config)

    [saved_run] = store.list_runs(scenario_id=scenario_config["name"])
    assert saved_run.frames_processed == 2
    assert saved_run.scenario_metrics == {
        "max_risk_score": 0.0,
        "time_above_threshold": 0.0,
        "near_collisions_ttc_below_1s": 0.0,
        "collision_count": 0.0,
        "lane_invasion_count": 0.0,
    }


def test_history_reads_legacy_run_without_scenario_metrics(tmp_path) -> None:
    store = RunHistoryStore(tmp_path / "legacy-history")
    store.run_path("legacy-run").write_text(
        json.dumps(
            {
                "run_id": "legacy-run",
                "scenario_id": "legacy-scenario",
                "frames_processed": 1,
                "failure_count": 0,
            }
        ),
        encoding="utf-8",
    )

    legacy_run = store.get_run("legacy-run")

    assert legacy_run.scenario_metrics == {}


def test_start_accepts_frontend_scenario_payload_and_can_stop_and_restart(
    monkeypatch, tmp_path,
) -> None:
    isolated_runtime = api_module.SimulationRuntime()
    service = SimulationService(
        isolated_runtime,
        RunHistoryStore(tmp_path / "start-payload-history"),
    )

    def wait_for_stop(backend: str, config: dict) -> None:
        isolated_runtime.start(
            backend,
            {"scenario_id": config["name"], "backend": backend, **config},
        )
        while not service._stop_event.wait(0.01):
            pass
        isolated_runtime.stop()
        with service._lock:
            service._thread = None

    monkeypatch.setattr(service, "_run_loop", wait_for_stop)
    monkeypatch.setattr(api_module, "simulation_service", service)
    payload = {
        "backend": "mock",
        "scenario": {
            "weather": {
                "precipitation": 70,
                "fog_density": 40,
                "wetness": 80,
            },
            "traffic_density": "Moderate",
            "lighting": "Day",
        },
    }

    def request_start(result: dict, finished: threading.Event) -> None:
        result["response"] = client.post("/api/v1/simulation/start", json=payload)
        finished.set()

    for _ in range(2):
        result: dict = {}
        finished = threading.Event()
        request_thread = threading.Thread(
            target=request_start,
            args=(result, finished),
            daemon=True,
        )
        request_thread.start()
        assert finished.wait(timeout=2.0), "Start request deadlocked on scenario configuration."
        response = result["response"]
        assert response.status_code == 200
        assert response.json()["configuration"]["weather"]["precipitation"] == 70.0
        configuration_response = client.put(
            "/api/v1/simulation/configuration",
            json={"weather": {"precipitation": 42.0}},
        )
        assert (
            configuration_response.json()["configuration"]["weather"]["precipitation"]
            == 42.0
        )
        assert client.post("/api/v1/simulation/stop").json()["status"] == "stopped"


def test_stop_timeout_preserves_running_thread_and_runtime(monkeypatch, tmp_path) -> None:
    isolated_runtime = api_module.SimulationRuntime()
    service = SimulationService(
        isolated_runtime,
        RunHistoryStore(tmp_path / "stop-timeout-history"),
    )
    release = threading.Event()
    finished = threading.Event()
    isolated_runtime.start("mock", {"scenario_id": "slow-stop"})
    worker = threading.Thread(
        target=lambda: (release.wait(), finished.set()),
        daemon=True,
    )
    service._thread = worker
    worker.start()
    monkeypatch.setattr(worker, "join", lambda timeout=None: None)

    result = service.stop()

    assert result["status"] == "stopping"
    assert service._thread is worker
    assert isolated_runtime.status()["status"] == "starting"
    release.set()
    assert finished.wait(timeout=2.0)


def test_history_endpoint_filters_persisted_failures(monkeypatch, tmp_path) -> None:
    store = RunHistoryStore(tmp_path / "api-history")
    store.save_run(
        HistoricalRunRecord(
            run_id="filter-run",
            scenario_id="filter-scenario",
            scenario_conditions={"weather": {"fog_density": 30.0}},
        ),
        [
            PerceptionFailureRecord(
                failure_id="filter-failure",
                failure_type="missed_detection",
                severity="high",
                object_class="pedestrian",
                run_id="filter-run",
                scenario_id="filter-scenario",
            )
        ],
    )
    monkeypatch.setattr(api_module, "history_store", store)

    response = client.get(
        "/api/v1/simulation/history",
        params={
            "scenario_id": "filter-scenario",
            "failure_type": "missed_detection",
            "min_severity": "high",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert [run["run_id"] for run in data["runs"]] == ["filter-run"]
    assert [failure["failure_id"] for failure in data["failures"]] == ["filter-failure"]
    assert data["failures"][0]["fingerprint"]
    assert data["coverage"]["condition_coverage"]["weather.fog_density"] == {
        "min": 30.0,
        "max": 30.0,
        "distinct_count": 1,
    }
    assert client.get(
        "/api/v1/simulation/history",
        params={"min_severity": "urgent"},
    ).status_code == 422


def test_failure_guided_recommendation_executes_and_feeds_history(
    monkeypatch, tmp_path,
) -> None:
    store = RunHistoryStore(tmp_path / "scenario-loop-history")
    monkeypatch.setattr(api_module, "history_store", store)
    cold_start = client.get(
        "/api/v1/scenarios/recommendations",
        params={"count": 4, "seed": 123},
    ).json()
    repeated_cold_start = client.get(
        "/api/v1/scenarios/recommendations",
        params={"count": 4, "seed": 123},
    ).json()

    assert cold_start["cold_start"] is True
    assert [item["candidate_id"] for item in cold_start["recommendations"]] == [
        item["candidate_id"] for item in repeated_cold_start["recommendations"]
    ]
    recommendation = cold_start["recommendations"][0]
    assert recommendation["cold_start"] is True
    assert "cold-start" in recommendation["selection_reason"].lower()

    class ControlledMockRunner:
        def __init__(self, _config: dict, backend: str) -> None:
            assert backend == "mock"
            self.latest_ground_truth_objects = [
                DetectedObject(
                    object_id="controlled-gt-car",
                    object_type="car",
                    confidence=1.0,
                    distance=12.0,
                    bbox=[2.0, 3.0, 20.0, 24.0],
                )
            ]

        @contextmanager
        def run(self):
            yield iter(
                [
                    SensorFrame(
                        timestamp=0.05,
                        frame_number=1,
                        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                    ),
                    SensorFrame(
                        timestamp=0.1,
                        frame_number=2,
                        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                    ),
                ]
            )

    monkeypatch.setattr(
        "edgeforge.scenarios.executor.ScenarioRunner",
        ControlledMockRunner,
    )
    monkeypatch.setattr(
        "edgeforge.scenarios.executor.ScenarioExecutionManager._simulate_perception_detections",
        staticmethod(lambda *_args: []),
    )
    execution_response = client.post(
        "/api/v1/scenarios/execute",
        json={
            "candidate_id": recommendation["candidate_id"],
            "scenario_config": recommendation["scenario_config"],
            "backend": "mock",
            "max_frames": 2,
        },
    )

    assert execution_response.status_code == 200
    executed = execution_response.json()
    assert executed["candidate_id"] == recommendation["candidate_id"]
    assert executed["scenario_id"] == recommendation["scenario_id"]
    assert executed["status"] == "completed"
    assert executed["backend"] == "mock"
    assert executed["persisted"] is True
    assert executed["sim_frames"] == 2
    assert executed["scenario_config"] == recommendation["scenario_config"]
    saved_run = store.get_run(executed["run_id"])
    assert saved_run.parameters["candidate_id"] == recommendation["candidate_id"]
    assert saved_run.parameters["scenario_config"] == recommendation["scenario_config"]
    assert saved_run.timestamp
    assert saved_run.failure_count == 2

    persisted_failures = store.get_run_failures(executed["run_id"])
    assert len(persisted_failures) == 2
    for failure in persisted_failures:
        assert failure.failure_type == "missed_detection"
        assert failure.severity == "high"
        assert failure.run_id == executed["run_id"]
        assert failure.scenario_id == executed["scenario_id"]
        assert failure.timestamp
        assert failure.fingerprint
        assert failure.scenario_conditions["weather"] == recommendation["scenario_conditions"]["weather"]

    next_ranked = client.get(
        "/api/v1/scenarios/recommendations",
        params={"count": 20, "seed": 123},
    ).json()
    assert next_ranked["cold_start"] is False
    assert recommendation["scenario_id"] not in {
        item["scenario_id"] for item in next_ranked["recommendations"]
    }
    assert any(
        evidence["run_id"] == executed["run_id"]
        for item in next_ranked["recommendations"]
        for evidence in item["historical_evidence"]
    )


def test_recommendations_use_nonempty_clean_history_without_failure_evidence(
    monkeypatch, tmp_path,
) -> None:
    store = RunHistoryStore(tmp_path / "clean-scenario-history")
    store.save_run(
        HistoricalRunRecord(
            run_id="clean-run",
            scenario_id="clean-scenario",
            frames_processed=1,
            true_positives=1,
            precision=1.0,
            recall=1.0,
            f1=1.0,
            scenario_conditions={
                "weather": {"fog_density": 0.0, "precipitation": 0.0}
            },
        ),
        [],
    )
    monkeypatch.setattr(api_module, "history_store", store)

    response = client.get(
        "/api/v1/scenarios/recommendations",
        params={"count": 3, "seed": 17},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["cold_start"] is False
    assert len(result["recommendations"]) == 3
    assert all(not item["cold_start"] for item in result["recommendations"])
    assert all(item["historical_evidence"] == [] for item in result["recommendations"])
    assert all("exploratory novelty" in item["selection_reason"] for item in result["recommendations"])


def test_recommended_mock_run_with_no_failures_updates_history(
    monkeypatch, tmp_path,
) -> None:
    store = RunHistoryStore(tmp_path / "clean-execution-history")
    monkeypatch.setattr(api_module, "history_store", store)
    recommendation = client.get(
        "/api/v1/scenarios/recommendations",
        params={"count": 1, "seed": 57},
    ).json()["recommendations"][0]
    ground_truth = DetectedObject(
        object_id="clean-gt",
        object_type="car",
        confidence=0.9,
        distance=10.0,
        bbox=[1.0, 2.0, 18.0, 22.0],
    )

    class CleanMockRunner:
        latest_ground_truth_objects = [ground_truth]

        def __init__(self, _config: dict, backend: str) -> None:
            assert backend == "mock"

        @contextmanager
        def run(self):
            yield iter(
                [
                    SensorFrame(
                        timestamp=0.05,
                        frame_number=1,
                        rgb=np.zeros((32, 32, 3), dtype=np.uint8),
                    )
                ]
            )

    monkeypatch.setattr(
        "edgeforge.scenarios.executor.ScenarioRunner",
        CleanMockRunner,
    )
    monkeypatch.setattr(
        "edgeforge.scenarios.executor.ScenarioExecutionManager._simulate_perception_detections",
        staticmethod(lambda truths, *_args: list(truths)),
    )

    response = client.post(
        "/api/v1/scenarios/execute",
        json={
            "candidate_id": recommendation["candidate_id"],
            "scenario_config": recommendation["scenario_config"],
            "max_frames": 1,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["persisted"] is True
    assert result["metrics"]["failure_count"] == 0
    assert store.get_run(result["run_id"]).failure_count == 0
    assert store.get_run_failures(result["run_id"]) == []

    updated = client.get(
        "/api/v1/scenarios/recommendations",
        params={"count": 2, "seed": 57},
    ).json()
    assert updated["cold_start"] is False
    assert all(item["historical_evidence"] == [] for item in updated["recommendations"])


def test_latest_report_returns_unavailable_when_no_report_exists(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "edgeforge.api.LATEST_REPORT_PATH",
        tmp_path / "missing-report.json",
    )

    response = client.get("/api/v1/simulation/reports/latest")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unavailable",
        "message": "No validation report has been generated yet.",
        "report": None,
    }


def test_latest_report_returns_existing_validation_data(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "validation.json"
    report_data = {"status": "completed", "metrics": {"precision": 0.75}, "failures": []}
    report_path.write_text(json.dumps(report_data), encoding="utf-8")
    monkeypatch.setattr("edgeforge.api.LATEST_REPORT_PATH", report_path)

    response = client.get("/api/v1/simulation/reports/latest")

    assert response.status_code == 200
    assert response.json() == {"status": "available", "report": report_data}


def test_latest_report_rejects_malformed_report(monkeypatch, tmp_path) -> None:
    report_path = tmp_path / "validation.json"
    report_path.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr("edgeforge.api.LATEST_REPORT_PATH", report_path)

    response = client.get("/api/v1/simulation/reports/latest")

    assert response.status_code == 500
    assert "Could not read the latest validation report" in response.json()["detail"]


def test_camera_status_is_disconnected_without_a_live_carla_feed() -> None:
    response = client.get("/api/v1/simulation/camera/status")

    assert response.status_code == 200
    assert response.json()["status"] == "disconnected"
    assert response.json()["available"] is False
    assert response.json()["frame_id"] is None
    assert response.json()["fps"] is None
    assert set(response.json()["cameras"]) == {"front", "right_side", "top_down"}
    assert all(
        not camera["available"] for camera in response.json()["cameras"].values()
    )


def test_camera_stream_returns_unavailable_without_live_frames() -> None:
    response = client.get("/api/v1/simulation/camera/stream")

    assert response.status_code == 503
    assert "not running" in response.json()["detail"]


def test_camera_worker_renders_and_exposes_pipeline_frame() -> None:
    runtime.start("carla", {"scenario_id": "camera-test"})
    runtime.publish_frame(
        backend="carla",
        frame_id=42,
        timestamp=2.1,
        detections=[
            DetectedObject(
                object_id="car-1",
                object_type="car",
                confidence=0.9,
                bbox=[8.0, 8.0, 40.0, 40.0],
            )
        ],
        scenario_conditions={"scenario_id": "camera-test"},
        metrics={"frames_processed": 42, "detection_count": 1},
        risk_assessment=None,
        camera_frame=np.zeros((64, 64, 3), dtype=np.uint8),
    )

    deadline = time.monotonic() + 3.0
    frame = runtime.camera_frame()
    while frame is None and time.monotonic() < deadline:
        time.sleep(0.01)
        frame = runtime.camera_frame()

    assert frame is not None
    assert frame[1].startswith(b"\xff\xd8")
    decoded_frame = cv2.imdecode(
        np.frombuffer(frame[1], dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    assert decoded_frame is not None
    assert int(decoded_frame[8, 20, 1]) > 120
    assert runtime.camera_status()["available"] is True
    assert runtime.camera_status()["frame_id"] == 42

    response = asyncio.run(get_camera_stream())

    async def read_and_close_stream() -> bytes:
        chunk = await response.body_iterator.__anext__()
        await response.body_iterator.aclose()
        return chunk

    chunk = asyncio.run(read_and_close_stream())
    assert chunk.startswith(b"--frame\r\nContent-Type: image/jpeg\r\n")
    assert b"Content-Length:" in chunk
    runtime.stop()
    assert runtime.camera_frame() is None
    assert runtime.camera_status()["available"] is False


def test_camera_worker_publishes_three_same_tick_views() -> None:
    runtime.start("carla", {"scenario_id": "three-camera-test"})
    front = np.zeros((64, 64, 3), dtype=np.uint8)
    right_side = np.full((64, 64, 3), 32, dtype=np.uint8)
    top_down = np.full((64, 64, 3), 64, dtype=np.uint8)
    runtime.publish_frame(
        backend="carla",
        frame_id=84,
        timestamp=4.2,
        detections=[
            DetectedObject(
                object_id="front-car",
                object_type="car",
                confidence=0.95,
                bbox=[8.0, 8.0, 40.0, 40.0],
            )
        ],
        scenario_conditions={"scenario_id": "three-camera-test"},
        metrics={"frames_processed": 84, "detection_count": 1},
        risk_assessment=None,
        camera_frames={
            "front": front,
            "right_side": right_side,
            "top_down": top_down,
        },
    )

    deadline = time.monotonic() + 3.0
    statuses = runtime.camera_status()["cameras"]
    while (
        not all(status["available"] for status in statuses.values())
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
        statuses = runtime.camera_status()["cameras"]

    assert set(statuses) == {"front", "right_side", "top_down"}
    assert all(status["available"] for status in statuses.values())
    assert {status["frame_id"] for status in statuses.values()} == {84}
    assert all(runtime.camera_frame(name) is not None for name in statuses)
    api_status = client.get("/api/v1/simulation/camera/status").json()
    assert api_status["cameras"]["right_side"]["frame_id"] == 84
    assert api_status["cameras"]["top_down"]["frame_id"] == 84

    front_jpeg = runtime.camera_frame("front")[1]
    side_jpeg = runtime.camera_frame("right_side")[1]
    top_jpeg = runtime.camera_frame("top_down")[1]
    front_image = cv2.imdecode(
        np.frombuffer(front_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    side_image = cv2.imdecode(
        np.frombuffer(side_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    top_image = cv2.imdecode(
        np.frombuffer(top_jpeg, dtype=np.uint8), cv2.IMREAD_COLOR
    )
    assert front_image is not None and side_image is not None and top_image is not None
    assert int(front_image[8, 20, 1]) > 120
    assert int(side_image[8, 20, 1]) < 120
    assert int(top_image[8, 20, 1]) < 120

    response = asyncio.run(get_camera_view_stream("top_down"))

    async def read_top_down_stream() -> bytes:
        chunk = await response.body_iterator.__anext__()
        await response.body_iterator.aclose()
        return chunk

    assert asyncio.run(read_top_down_stream()).startswith(
        b"--frame\r\nContent-Type: image/jpeg\r\n"
    )
    runtime.stop()
    assert all(not status["available"] for status in runtime.camera_status()["cameras"].values())


def test_mock_backend_does_not_publish_camera_frames() -> None:
    runtime.start("mock", {"scenario_id": "mock-camera-test"})
    runtime.publish_frame(
        backend="mock",
        frame_id=7,
        timestamp=0.35,
        detections=[],
        scenario_conditions={"scenario_id": "mock-camera-test"},
        metrics={"frames_processed": 7},
        risk_assessment=None,
        camera_frame=np.zeros((32, 32, 3), dtype=np.uint8),
    )

    status = client.get("/api/v1/simulation/camera/status").json()

    assert status["status"] == "disconnected"
    assert status["available"] is False


def test_simulation_start_stop_endpoints(monkeypatch, tmp_path) -> None:
    api_module.simulation_service.history_store = RunHistoryStore(
        tmp_path / "start-stop-history"
    )

    # 1. Start simulation
    response = client.post("/api/v1/simulation/start", json={"backend": "mock"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("started", "running")

    # Status should reflect running
    deadline = time.monotonic() + 3.0
    st = client.get("/api/v1/simulation/status").json()
    while not st.get("is_running") and time.monotonic() < deadline:
        time.sleep(0.05)
        st = client.get("/api/v1/simulation/status").json()
    assert st.get("is_running") is True

    # Check snapshot data
    snap = client.get("/api/v1/simulation/snapshot").json()
    assert snap["simulation_status"] in ("running", "starting")

    # 2. Stop simulation
    stop_resp = client.post("/api/v1/simulation/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["status"] == "stopped"

    # Status should reflect stopped
    st_stopped = client.get("/api/v1/simulation/status").json()
    assert st_stopped["status"] == "disconnected"
    assert st_stopped.get("is_running") is False


def test_simulation_configuration_endpoints() -> None:
    # Update configuration
    resp = client.put(
        "/api/v1/simulation/configuration",
        json={
            "weather": {"precipitation": 45.0, "fog_density": 20.0},
            "lighting": "Night",
            "traffic_density": "High",
        },
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "success"

    # Get configuration
    get_resp = client.get("/api/v1/simulation/configuration")
    assert get_resp.status_code == 200
    config_data = get_resp.json()["configuration"]
    assert config_data["weather"]["precipitation"] == 45.0
    assert config_data["lighting"] == "Night"
    assert config_data["traffic_density"] == "High"
