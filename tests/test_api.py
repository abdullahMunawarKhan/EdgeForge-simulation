from __future__ import annotations
import asyncio
import json
import time

import cv2
import numpy as np
from fastapi.testclient import TestClient
from edgeforge.api import app, get_camera_stream, get_camera_view_stream, runtime
from edgeforge.data.models import DetectedObject, PerceptionFailureRecord, RiskAssessment

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
