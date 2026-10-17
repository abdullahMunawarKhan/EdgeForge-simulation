"""Read-only API for the live EdgeForge simulation dashboard."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Literal, Mapping, Optional, Sequence

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from pydantic import BaseModel, Field

from edgeforge.config.settings import PROJECT_ROOT, settings
from edgeforge.data.history import RunHistoryStore
from edgeforge.data.models import DetectedObject, PerceptionFailureRecord, RiskAssessment
from edgeforge.perception.yolo_camera_test import render_detections
from edgeforge.scenarios.executor import ScenarioExecutionManager, ExecutionStatus
from edgeforge.scenarios.generator import ScenarioGenerator
from edgeforge.simulation.runner_service import SimulationService
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)
_CAMERA_FRAME_MAX_AGE_SECONDS = 3.0
_CAMERA_JPEG_QUALITY = 82
CAMERA_NAMES = ("front", "right_side", "top_down")

_DEFAULT_SNAPSHOT: dict[str, Any] = {
    "simulation_status": "disconnected",
    "backend": None,
    "scenario_id": None,
    "run_id": None,
    "frame_id": None,
    "timestamp": None,
    "detections": None,
    "scenario_conditions": None,
    "metrics": None,
    "risk_assessment": None,
    "failures": None,
}


class SimulationRuntime:
    """Thread-safe latest-state store shared by the API and simulation loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._status = "disconnected"
        self._message = "No simulation pipeline is currently publishing live data."
        self._snapshot = deepcopy(_DEFAULT_SNAPSHOT)
        self._updated_at: str | None = None
        self._camera_lock = threading.Lock()
        self._camera_queue: queue.Queue[
            tuple[int, str, np.ndarray, list[DetectedObject], int, float]
        ] = queue.Queue(maxsize=len(CAMERA_NAMES))
        self._camera_worker: threading.Thread | None = None
        self._camera_generation = 0
        self._active_cameras: set[str] = set()
        self._camera_messages = {
            name: "No CARLA camera stream is available." for name in CAMERA_NAMES
        }
        self._camera_jpegs: dict[str, bytes] = {}
        self._camera_frame_ids: dict[str, int] = {}
        self._camera_timestamps: dict[str, float] = {}
        self._camera_published_at: dict[str, float] = {}
        self._camera_updated_at: dict[str, str] = {}
        self._camera_sequences = {name: 0 for name in CAMERA_NAMES}
        self._camera_fps = {name: 0.0 for name in CAMERA_NAMES}
        self._camera_interval_started = {name: monotonic() for name in CAMERA_NAMES}
        self._camera_interval_frames = {name: 0 for name in CAMERA_NAMES}

    def _replace(self, status: str, message: str, snapshot: Mapping[str, Any]) -> None:
        with self._lock:
            self._status = status
            self._message = message
            self._snapshot = deepcopy(dict(snapshot))
            self._updated_at = datetime.now(timezone.utc).isoformat()
            self._version += 1

    def start(self, backend: str, scenario_conditions: Mapping[str, Any]) -> None:
        with self._camera_lock:
            self._camera_generation += 1
            self._active_cameras = set(CAMERA_NAMES) if backend == "carla" else set()
            self._camera_messages = {
                name: (
                    f"Waiting for the existing CARLA {name.replace('_', '-')} camera."
                    if name in self._active_cameras
                    else "A CARLA camera feed is unavailable when using the mock backend."
                )
                for name in CAMERA_NAMES
            }
            self._camera_jpegs.clear()
            self._camera_frame_ids.clear()
            self._camera_timestamps.clear()
            self._camera_published_at.clear()
            self._camera_updated_at.clear()
            for name in CAMERA_NAMES:
                self._camera_fps[name] = 0.0
                self._camera_interval_started[name] = monotonic()
                self._camera_interval_frames[name] = 0
            self._ensure_camera_worker()
        snapshot = deepcopy(_DEFAULT_SNAPSHOT)
        snapshot.update(
            simulation_status="starting",
            backend=backend,
            scenario_id=scenario_conditions.get("scenario_id"),
            run_id=scenario_conditions.get("run_id"),
            scenario_conditions=dict(scenario_conditions),
            failures=None,
        )
        self._replace("starting", "Simulation pipeline is starting.", snapshot)

    def publish_frame(
        self,
        *,
        backend: str,
        frame_id: int,
        timestamp: float,
        detections: Sequence[DetectedObject] | None,
        scenario_conditions: Mapping[str, Any],
        metrics: Mapping[str, Any],
        risk_assessment: RiskAssessment | None,
        failures: Sequence[PerceptionFailureRecord] | None = None,
        camera_frame: np.ndarray | None = None,
        camera_frames: Mapping[str, np.ndarray] | None = None,
    ) -> None:
        snapshot = {
            "simulation_status": "running",
            "backend": backend,
            "scenario_id": scenario_conditions.get("scenario_id"),
            "run_id": scenario_conditions.get("run_id"),
            "frame_id": frame_id,
            "timestamp": timestamp,
            "detections": (
                [item.model_dump(mode="json") for item in detections]
                if detections is not None
                else None
            ),
            "scenario_conditions": dict(scenario_conditions),
            "metrics": dict(metrics),
            "risk_assessment": (
                risk_assessment.model_dump(mode="json")
                if risk_assessment is not None
                else None
            ),
            "failures": (
                [item.model_dump(mode="json") for item in failures]
                if failures is not None
                else None
            ),
        }
        self._replace("running", "Simulation pipeline is publishing live data.", snapshot)
        frames_to_encode = dict(camera_frames or {})
        if camera_frame is not None:
            frames_to_encode.setdefault("front", camera_frame)
        if backend == "carla" and frames_to_encode:
            with self._camera_lock:
                if self._active_cameras:
                    for camera_name, frame in frames_to_encode.items():
                        if camera_name not in self._active_cameras:
                            continue
                        camera_detections = (
                            list(detections or []) if camera_name == "front" else []
                        )
                        work_item = (
                            self._camera_generation,
                            camera_name,
                            frame,
                            camera_detections,
                            frame_id,
                            timestamp,
                        )
                        try:
                            self._camera_queue.put_nowait(work_item)
                            continue
                        except queue.Full:
                            pass
                        try:
                            self._camera_queue.get_nowait()
                        except queue.Empty:
                            pass
                        try:
                            self._camera_queue.put_nowait(work_item)
                        except queue.Full:
                            logger.warning(
                                "Dropping {} camera frame because encoder queue is full.",
                                camera_name,
                            )

    def stop(self, message: str = "Simulation pipeline is not running.") -> None:
        with self._camera_lock:
            self._camera_generation += 1
            self._active_cameras.clear()
            self._camera_messages = {name: message for name in CAMERA_NAMES}
            self._camera_jpegs.clear()
            self._camera_frame_ids.clear()
            self._camera_timestamps.clear()
            self._camera_published_at.clear()
            self._camera_updated_at.clear()
            for name in CAMERA_NAMES:
                self._camera_fps[name] = 0.0
            try:
                while True:
                    self._camera_queue.get_nowait()
            except queue.Empty:
                pass
        with self._lock:
            self._status = "disconnected"
            self._message = message
            self._snapshot = deepcopy(_DEFAULT_SNAPSHOT)
            self._updated_at = datetime.now(timezone.utc).isoformat()
            self._version += 1

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "status": self._status,
                "message": self._message,
                "backend": self._snapshot.get("backend"),
                "scenario_id": self._snapshot.get("scenario_id"),
                "frame_id": self._snapshot.get("frame_id"),
                "updated_at": self._updated_at,
            }

    def snapshot(self) -> tuple[int, dict[str, Any]]:
        with self._lock:
            return self._version, deepcopy(self._snapshot)

    def _camera_status_locked(self, camera_name: str) -> dict[str, Any]:
        published_at = self._camera_published_at.get(camera_name)
        is_fresh = (
            published_at is not None
            and monotonic() - published_at <= _CAMERA_FRAME_MAX_AGE_SECONDS
        )
        available = (
            camera_name in self._active_cameras
            and camera_name in self._camera_jpegs
            and is_fresh
        )
        if available:
            state = "connected"
            message = f"Streaming the managed CARLA {camera_name.replace('_', '-')} camera."
            if camera_name == "front":
                message += " YOLO pipeline detections are overlaid."
        elif camera_name in self._active_cameras:
            state = "connecting"
            message = self._camera_messages[camera_name]
            if camera_name in self._camera_jpegs and not is_fresh:
                state = "disconnected"
                message = "The camera feed stopped sending fresh frames."
        else:
            state = "disconnected"
            message = self._camera_messages[camera_name]
        return {
            "status": state,
            "available": available,
            "message": message,
            "camera": camera_name if camera_name in self._active_cameras else None,
            "frame_id": self._camera_frame_ids.get(camera_name) if available else None,
            "timestamp": self._camera_timestamps.get(camera_name) if available else None,
            "fps": (
                round(self._camera_fps[camera_name], 1)
                if available and self._camera_fps[camera_name] > 0
                else None
            ),
            "updated_at": self._camera_updated_at.get(camera_name) if available else None,
        }

    def camera_status(self) -> dict[str, Any]:
        with self._camera_lock:
            camera_statuses = {
                name: self._camera_status_locked(name) for name in CAMERA_NAMES
            }
            return {**camera_statuses["front"], "cameras": camera_statuses}

    def camera_frame(self, camera_name: str = "front") -> tuple[int, bytes] | None:
        with self._camera_lock:
            if (
                camera_name not in self._active_cameras
                or camera_name not in self._camera_jpegs
                or camera_name not in self._camera_published_at
                or monotonic() - self._camera_published_at[camera_name]
                > _CAMERA_FRAME_MAX_AGE_SECONDS
            ):
                return None
            return (
                self._camera_sequences[camera_name],
                self._camera_jpegs[camera_name],
            )

    def _ensure_camera_worker(self) -> None:
        if self._camera_worker is not None and self._camera_worker.is_alive():
            return
        self._camera_worker = threading.Thread(
            target=self._encode_camera_frames,
            name="edgeforge-camera-encoder",
            daemon=True,
        )
        self._camera_worker.start()

    def _encode_camera_frames(self) -> None:
        while True:
            try:
                generation, camera_name, frame, detections, frame_id, timestamp = (
                    self._camera_queue.get(timeout=0.5)
                )
            except queue.Empty:
                continue
            try:
                annotated = render_detections(frame, detections)
                encoded, jpeg = cv2.imencode(
                    ".jpg",
                    annotated,
                    [cv2.IMWRITE_JPEG_QUALITY, _CAMERA_JPEG_QUALITY],
                )
                if not encoded:
                    raise RuntimeError("OpenCV could not encode the annotated camera frame.")
                now = monotonic()
                with self._camera_lock:
                    if (
                        generation != self._camera_generation
                        or camera_name not in self._active_cameras
                    ):
                        continue
                    self._camera_jpegs[camera_name] = jpeg.tobytes()
                    self._camera_frame_ids[camera_name] = frame_id
                    self._camera_timestamps[camera_name] = timestamp
                    self._camera_published_at[camera_name] = now
                    self._camera_updated_at[camera_name] = datetime.now(timezone.utc).isoformat()
                    self._camera_sequences[camera_name] += 1
                    self._camera_interval_frames[camera_name] += 1
                    elapsed = now - self._camera_interval_started[camera_name]
                    if elapsed >= 1.0:
                        self._camera_fps[camera_name] = (
                            self._camera_interval_frames[camera_name] / elapsed
                        )
                        self._camera_interval_started[camera_name] = now
                        self._camera_interval_frames[camera_name] = 0
                    self._camera_messages[camera_name] = (
                        "Annotated CARLA front-camera frame is available."
                        if camera_name == "front"
                        else f"CARLA {camera_name.replace('_', '-')} camera frame is available."
                    )
            except Exception:
                logger.exception("Could not prepare an annotated CARLA camera frame.")
                with self._camera_lock:
                    if generation == self._camera_generation:
                        self._camera_messages[camera_name] = (
                            f"Could not encode the CARLA {camera_name.replace('_', '-')} camera frame."
                        )


runtime = SimulationRuntime()
history_store = RunHistoryStore()
simulation_service = SimulationService(runtime, history_store)
app = FastAPI(title="EdgeForge Simulation API", version=settings.VERSION)

_configured_origins = [
    origin.strip()
    for origin in os.getenv("EDGEFORGE_CORS_ORIGINS", "").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_configured_origins or [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_run_dir = Path(settings.RUN_DIR)
if not _run_dir.is_absolute():
    _run_dir = PROJECT_ROOT / _run_dir
LATEST_REPORT_PATH = _run_dir / "phase4-live-validation.json"


class SimulationStartPayload(BaseModel):
    backend: str = "mock"
    scenario: Optional[dict[str, Any]] = None
    scenario_path: Optional[str] = None


class RecommendedScenarioExecutionPayload(BaseModel):
    candidate_id: str
    scenario_config: dict[str, Any]
    backend: Literal["mock"] = "mock"
    max_frames: int = Field(default=20, ge=1, le=300)


@app.get("/api/v1/simulation/status")
def get_simulation_status() -> dict[str, Any]:
    """Return the latest simulation/pipeline connection status."""
    st = runtime.status()
    st["is_running"] = simulation_service.is_running or st.get("status") == "running"
    return st


@app.post("/api/v1/simulation/start")
def start_simulation(payload: Optional[SimulationStartPayload] = None) -> dict[str, Any]:
    """Start a background simulation (defaulting to mock backend)."""
    backend = payload.backend if payload else "mock"
    scenario_cfg = payload.scenario if payload else None
    scenario_path = payload.scenario_path if payload else None
    return simulation_service.start(
        backend=backend,
        scenario_config=scenario_cfg,
        scenario_path=scenario_path,
    )


@app.post("/api/v1/simulation/stop")
def stop_simulation() -> dict[str, Any]:
    """Stop the active simulation."""
    return simulation_service.stop()


@app.get("/api/v1/simulation/configuration")
def get_simulation_configuration() -> dict[str, Any]:
    """Return active or pending scenario configuration."""
    return {
        "status": "success",
        "configuration": simulation_service.get_configuration(),
    }


@app.put("/api/v1/simulation/configuration")
@app.post("/api/v1/simulation/configuration")
def update_simulation_configuration(
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Update active or pending scenario configuration."""
    return simulation_service.update_configuration(payload)


@app.get("/api/v1/simulation/snapshot")
def get_simulation_snapshot() -> dict[str, Any]:
    """Return the latest real pipeline snapshot, or explicit unavailable values."""
    return runtime.snapshot()[1]


@app.get("/api/v1/simulation/history")
def get_simulation_history(
    scenario_id: str | None = None,
    run_id: str | None = None,
    failure_type: str | None = None,
    min_severity: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return persisted runs, failures, and coverage with optional filters."""
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000.")
    if min_severity is not None and min_severity.lower() not in {
        "low",
        "medium",
        "high",
        "critical",
    }:
        raise HTTPException(
            status_code=422,
            detail="min_severity must be low, medium, high, or critical.",
        )

    runs = history_store.list_runs(scenario_id=scenario_id)
    if run_id is not None:
        runs = [run for run in runs if run.run_id == run_id]
    runs = runs[:limit]
    failures = history_store.get_failures(
        scenario_id=scenario_id,
        run_id=run_id,
        failure_type=failure_type,
        min_severity=min_severity,
    )
    return {
        "runs": [run.model_dump(mode="json") for run in runs],
        "failures": [failure.model_dump(mode="json") for failure in failures],
        "coverage": history_store.get_coverage_summary(),
    }


@app.get("/api/v1/scenarios/recommendations")
def get_scenario_recommendations(
    count: int = Query(default=5, ge=1, le=20),
    seed: int = 42,
) -> dict[str, Any]:
    """Rank reproducible next scenarios from persisted failures and coverage."""
    generator = ScenarioGenerator(history_store=history_store, seed=seed)
    recommendations = generator.generate_and_rank(
        num_candidates=count,
        seed=seed,
        allow_duplicates=False,
    )
    return {
        "cold_start": recommendations[0].cold_start if recommendations else not bool(history_store.list_runs()),
        "recommendations": [
            recommendation.model_dump(mode="json")
            for recommendation in recommendations
        ],
    }


@app.post("/api/v1/scenarios/execute")
def execute_recommended_scenario(
    payload: RecommendedScenarioExecutionPayload,
) -> dict[str, Any]:
    """Execute a selected recommendation using the mock scenario runner."""
    scenario_config = dict(payload.scenario_config)
    if scenario_config.get("candidate_id") != payload.candidate_id:
        raise HTTPException(
            status_code=422,
            detail="candidate_id must match the recommended scenario configuration.",
        )
    manager = ScenarioExecutionManager(
        history_store=history_store,
        default_backend="mock",
    )
    result = manager.execute(
        scenario_config,
        backend="mock",
        max_frames=payload.max_frames,
    )
    response: dict[str, Any] = {
        "candidate_id": result.candidate_id,
        "scenario_id": result.scenario_id,
        "run_id": result.run_id,
        "status": result.status.value,
        "backend": result.backend,
        "persisted": result.persisted,
        "scenario_config": result.scenario_config,
        "sim_frames": result.sim_frames,
        "sim_time_s": result.sim_time_s,
        "error_message": result.error_message,
    }
    if result.metrics is not None:
        response["metrics"] = result.metrics.to_dict()
        response["failures"] = [
            failure.model_dump(mode="json")
            for failure in result.metrics.failures
        ]
        if result.persisted:
            response["run"] = history_store.get_run(result.run_id).model_dump(
                mode="json"
            )
    if result.status == ExecutionStatus.FAILED:
        raise HTTPException(
            status_code=500,
            detail=response,
        )
    if result.status == ExecutionStatus.REJECTED:
        raise HTTPException(
            status_code=422,
            detail=response,
        )
    return response


@app.get("/api/v1/simulation/camera/status")
def get_camera_status() -> dict[str, Any]:
    """Report availability and metadata for all managed CARLA camera views."""
    return runtime.camera_status()


async def _camera_stream(camera_name: str) -> StreamingResponse:
    if camera_name not in CAMERA_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown camera view: {camera_name}")
    camera_status = runtime.camera_status()["cameras"][camera_name]
    if not camera_status["available"]:
        raise HTTPException(
            status_code=503,
            detail=camera_status["message"],
        )

    async def frames():
        last_sequence = 0
        while True:
            current = runtime.camera_frame(camera_name)
            if current is None:
                return
            sequence, jpeg = current
            if sequence != last_sequence:
                last_sequence = sequence
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                    + jpeg
                    + b"\r\n"
                )
            await asyncio.sleep(0.03)

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


@app.get("/api/v1/simulation/camera/stream")
async def get_camera_stream() -> StreamingResponse:
    """Backward-compatible route for the front-camera MJPEG stream."""
    return await _camera_stream("front")


@app.get("/api/v1/simulation/camera/{camera_name}/stream")
async def get_camera_view_stream(camera_name: str) -> StreamingResponse:
    """Stream one managed CARLA camera view as MJPEG."""
    return await _camera_stream(camera_name)


def _read_latest_report() -> dict[str, Any]:
    if not LATEST_REPORT_PATH.is_file():
        return {
            "status": "unavailable",
            "message": "No validation report has been generated yet.",
            "report": None,
        }
    try:
        report = json.loads(LATEST_REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read the latest validation report: {exc}",
        ) from exc
    if not isinstance(report, dict):
        raise HTTPException(
            status_code=500,
            detail="The latest validation report must contain a JSON object.",
        )
    return {"status": "available", "report": report}


@app.get("/api/v1/simulation/reports/latest")
def get_latest_report() -> dict[str, Any]:
    """Return the latest real validation report if one has been written."""
    return _read_latest_report()


@app.websocket("/api/v1/simulation/ws")
async def simulation_updates(websocket: WebSocket) -> None:
    """Send an initial snapshot and then each new published frame."""
    await websocket.accept()
    version, snapshot = runtime.snapshot()
    await websocket.send_json({"snapshot": snapshot})
    try:
        while True:
            await asyncio.sleep(0.1)
            next_version, next_snapshot = runtime.snapshot()
            if next_version != version:
                version = next_version
                await websocket.send_json({"snapshot": next_snapshot})
    except WebSocketDisconnect:
        return


def start_api_server() -> uvicorn.Server:
    """Start the API in a background thread for an in-process simulation run."""
    config = uvicorn.Config(
        app,
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    startup_error: list[Exception] = []

    def serve() -> None:
        try:
            server.run()
        except Exception as exc:
            startup_error.append(exc)

    thread = threading.Thread(
        target=serve,
        name="edgeforge-api",
        daemon=True,
    )
    thread.start()
    deadline = monotonic() + 5.0
    while not server.started and thread.is_alive() and monotonic() < deadline:
        sleep(0.05)
    if startup_error:
        raise RuntimeError("Could not start the EdgeForge API server.") from startup_error[0]
    if not server.started:
        server.should_exit = True
        raise RuntimeError(
            f"EdgeForge API did not start at {settings.API_HOST}:{settings.API_PORT}."
        )
    return server
