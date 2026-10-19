"""Simulation service for starting, stopping, and updating EdgeForge simulations.

Provides thread-safe lifecycle control over background ScenarioRunner sessions
for the live FastAPI interface and dashboard.
"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from time import monotonic, sleep
from typing import TYPE_CHECKING, Any, Dict, Mapping, Optional
from uuid import uuid4

from edgeforge.analysis.risk_engine import RiskEngine
from edgeforge.analysis.scenario_evaluator import ScenarioEvaluator
from edgeforge.config.settings import PROJECT_ROOT, settings
from edgeforge.data.history import RunHistoryStore
from edgeforge.data.models import DetectedObject, ScenarioEvent, ScenarioResult
from edgeforge.perception.camera import CameraProcessor
from edgeforge.perception.detector import (
    ObjectDetector,
    adapt_ground_truth_detections,
)
from edgeforge.perception.pipeline import PerceptionPipeline
from edgeforge.perception.validation import (
    GroundTruthObject,
    ValidationMetrics,
    aggregate_run_metrics,
    evaluate_detections,
)
from edgeforge.simulation.scenario_runner import BACKEND_MOCK, ScenarioRunner
from edgeforge.utils.logger import get_logger

if TYPE_CHECKING:
    from edgeforge.api import SimulationRuntime

logger = get_logger(__name__)

DEFAULT_SCENARIO_PATH = (
    PROJECT_ROOT / "edgeforge" / "scenarios" / "configs" / "default_scenario.json"
)

TRAFFIC_PRESETS = {
    "Low": {"vehicles": 2, "pedestrians": 3, "bicycles": 1},
    "Moderate": {"vehicles": 5, "pedestrians": 10, "bicycles": 2},
    "High": {"vehicles": 12, "pedestrians": 18, "bicycles": 4},
}

LIGHTING_PRESETS = {
    "Day": 60.0,
    "Dawn/Dusk": 15.0,
    "Night": -15.0,
}


def _load_base_scenario(scenario_path: Optional[str] = None) -> Dict[str, Any]:
    path = Path(scenario_path) if scenario_path else DEFAULT_SCENARIO_PATH
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not load scenario JSON from {path}: {exc}")
    # Sensible fallback starter scenario
    return {
        "name": "mock_urban_scenario",
        "description": "API-driven EdgeForge mock scenario",
        "weather": "ClearNoon",
        "map": "Town03",
        "duration_seconds": 0,
        "traffic": {"vehicles": 5, "pedestrians": 10, "bicycles": 2},
        "ego_vehicle": {
            "model": "vehicle.tesla.model3",
            "spawn_point_index": 0,
            "speed_limit": 50,
            "autopilot": False,
        },
        "sensors": {
            "rgb_camera": {
                "enabled": True,
                "width": settings.CAMERA_WIDTH,
                "height": settings.CAMERA_HEIGHT,
                "fov": settings.CAMERA_FOV,
                "tick": settings.CAMERA_TICK,
            },
            "collision": {"enabled": True},
            "lane_invasion": {"enabled": True},
        },
    }


class SimulationService:
    """Manages active background simulation runs for the FastAPI server."""

    def __init__(
        self,
        runtime: SimulationRuntime,
        history_store: RunHistoryStore | None = None,
    ) -> None:
        self.runtime = runtime
        self.history_store = (
            history_store if history_store is not None else RunHistoryStore()
        )
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active_runner: Optional[ScenarioRunner] = None
        self._lock = threading.RLock()
        self._current_config: Dict[str, Any] = {
            "weather": {
                "precipitation": 0.0,
                "fog_density": 0.0,
                "wetness": 0.0,
                "sun_altitude_angle": 60.0,
            },
            "traffic_density": "Moderate",
            "lighting": "Day",
            "backend": "mock",
        }

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_configuration(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._current_config)

    def update_configuration(self, updates: Mapping[str, Any]) -> Dict[str, Any]:
        """Dynamically apply scenario parameters to the running or pending simulation."""
        with self._lock:
            # Normalize weather
            raw_weather = updates.get("weather")
            weather_dict: Dict[str, Any] = {}
            if isinstance(raw_weather, dict):
                for k, v in raw_weather.items():
                    if isinstance(v, (int, float)):
                        weather_dict[k] = float(v)
            elif isinstance(raw_weather, str):
                weather_dict["preset"] = raw_weather

            lighting = updates.get("lighting")
            if lighting in LIGHTING_PRESETS:
                weather_dict["sun_altitude_angle"] = LIGHTING_PRESETS[lighting]

            traffic_density = updates.get("traffic_density")
            if traffic_density in TRAFFIC_PRESETS:
                self._current_config["traffic"] = dict(TRAFFIC_PRESETS[traffic_density])
                self._current_config["traffic_density"] = traffic_density

            if lighting:
                self._current_config["lighting"] = lighting
            if weather_dict:
                self._current_config.setdefault("weather", {}).update(weather_dict)

            for key, val in updates.items():
                if key not in ("weather", "traffic"):
                    self._current_config[key] = deepcopy(val)

            # Apply to active client if running
            if self._active_runner is not None and hasattr(self._active_runner, "_client"):
                client = self._active_runner._client
                if hasattr(client, "set_weather") and weather_dict:
                    try:
                        client.set_weather(weather_dict)
                    except Exception as exc:
                        logger.warning(f"Could not update weather on active client: {exc}")

            # Reflect conditions in runtime snapshot
            with self.runtime._lock:  # noqa: SLF001
                if isinstance(self.runtime._snapshot.get("scenario_conditions"), dict):  # noqa: SLF001
                    self.runtime._snapshot["scenario_conditions"].update(  # noqa: SLF001
                        dict(self._current_config)
                    )
                    self.runtime._version += 1  # noqa: SLF001

            return {
                "status": "success",
                "message": "Scenario configuration updated successfully.",
                "configuration": deepcopy(self._current_config),
            }

    def start(
        self,
        backend: str = "mock",
        scenario_config: Optional[Dict[str, Any]] = None,
        scenario_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a simulation session in a background thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {
                    "status": "running",
                    "backend": backend,
                    "message": "Simulation is already running.",
                    "configuration": deepcopy(self._current_config),
                }

            self._stop_event.clear()
            base_cfg = _load_base_scenario(scenario_path)

            if scenario_config:
                self.update_configuration(scenario_config)

            # Inject active configuration into runner config
            merged_cfg = deepcopy(base_cfg)
            if backend == "carla" and "map" not in (scenario_config or {}):
                merged_cfg["map"] = "current"
            if "weather" in self._current_config:
                merged_cfg["weather"] = deepcopy(self._current_config["weather"])
            if "traffic" in self._current_config:
                merged_cfg["traffic"] = deepcopy(self._current_config["traffic"])
            response_config = deepcopy(self._current_config)

            self._thread = threading.Thread(
                target=self._run_loop,
                args=(backend, merged_cfg),
                name="edgeforge-simulation-runner",
                daemon=True,
            )
            self._thread.start()

        # Await startup confirmation
        deadline = monotonic() + 3.0
        while monotonic() < deadline:
            st = self.runtime.status()
            if st.get("status") in ("running", "starting"):
                break
            sleep(0.05)

        return {
            "status": "started",
            "backend": backend,
            "message": f"Simulation started successfully [{backend} backend].",
            "configuration": response_config,
        }

    def stop(self) -> Dict[str, Any]:
        """Stop the active simulation gracefully."""
        thread: Optional[threading.Thread] = None
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self.runtime.stop()
                return {"status": "stopped", "message": "Simulation is not running."}

            self._stop_event.set()
            thread = self._thread

        if thread is not None:
            thread.join(timeout=3.0)

        with self._lock:
            if thread is not None and thread.is_alive():
                return {
                    "status": "stopping",
                    "message": "Simulation is still shutting down.",
                }

        return {"status": "stopped", "message": "Simulation stopped successfully."}

    def _run_loop(self, backend: str, config: Dict[str, Any]) -> None:
        """Internal background loop running the pipeline and publishing to runtime."""
        camera_proc = CameraProcessor(
            default_width=settings.CAMERA_WIDTH,
            default_height=settings.CAMERA_HEIGHT,
        )
        detector = ObjectDetector()
        perception_pipeline = PerceptionPipeline(
            camera_processor=camera_proc,
            detector=detector,
        )
        risk_engine = RiskEngine()

        runner: Optional[ScenarioRunner] = None
        frame_metrics: list[ValidationMetrics] = []
        risk_samples: list[dict[str, float]] = []
        scenario_events: list[ScenarioEvent] = []
        frame_timestamps: list[float] = []
        run_id = uuid4().hex
        completed = False
        scenario_conditions: Dict[str, Any] = {}
        try:
            runner = ScenarioRunner(config, backend=backend)
            with self._lock:
                self._active_runner = runner

            scenario_info = getattr(runner, "info", None)
            scenario_conditions = {
                "scenario_id": getattr(scenario_info, "name", "live_scenario"),
                "scenario_name": getattr(scenario_info, "name", "live_scenario"),
                "weather_preset": getattr(scenario_info, "weather_preset", "ClearNoon"),
                "map": getattr(scenario_info, "map_name", "Town03"),
                "backend": runner.backend,
                "run_id": run_id,
            }
            with self._lock:
                active_config = deepcopy(self._current_config)
            scenario_conditions.update(active_config)
            self.runtime.start(runner.backend, scenario_conditions)

            logger.info(f"🚀 SimulationService loop started [backend={runner.backend}].")

            with runner.run() as stream:
                for frame in stream:
                    if self._stop_event.is_set():
                        break
                    if runner.backend == BACKEND_MOCK:
                        frame_timestamps.append(float(frame.timestamp))
                        scenario_events.extend(
                            self._scenario_events_for_frame(frame)
                        )

                    pipeline_detections: list[DetectedObject] | None = None
                    last_detections: list[DetectedObject] = []
                    camera_frame = None
                    source_size: tuple[int, int] | None = None
                    target_size: tuple[int, int] | None = None
                    ground_truth = getattr(
                        runner,
                        "latest_ground_truth_objects",
                        None,
                    )
                    if ground_truth is None:
                        ground_truth = getattr(
                            runner,
                            "latest_mock_ground_truth_detections",
                            [],
                        )

                    if frame.rgb is not None and camera_proc.is_valid_frame(frame.rgb):
                        rgb = frame.rgb
                        info = camera_proc.get_frame_info(rgb)
                        source_size = (info.width, info.height)
                        if (
                            info.width != settings.CAMERA_WIDTH
                            or info.height != settings.CAMERA_HEIGHT
                        ):
                            rgb = camera_proc.resize_frame(
                                rgb,
                                width=settings.CAMERA_WIDTH,
                                height=settings.CAMERA_HEIGHT,
                            )
                        camera_frame = rgb
                        target_size = (rgb.shape[1], rgb.shape[0])

                        if runner.backend == "mock":
                            mock_detections = adapt_ground_truth_detections(
                                runner.latest_mock_ground_truth_detections,
                                source_size=source_size,
                                target_size=target_size,
                            )
                            last_detections = perception_pipeline.process_frame(
                                rgb,
                                timestamp=frame.timestamp,
                                raw_detections=mock_detections,
                            )
                        else:
                            last_detections = perception_pipeline.process_frame(
                                rgb,
                                timestamp=frame.timestamp,
                            )
                        pipeline_detections = last_detections
                    else:
                        last_detections = []

                    if source_size is not None and target_size is not None:
                        scale_x = target_size[0] / source_size[0]
                        scale_y = target_size[1] / source_size[1]
                    else:
                        scale_x = scale_y = 1.0
                    scaled_ground_truth = [
                        GroundTruthObject(
                            actor_id=getattr(item, "actor_id", index),
                            object_type=item.object_type,
                            bbox=(
                                item.bbox[0] * scale_x,
                                item.bbox[1] * scale_y,
                                item.bbox[2] * scale_x,
                                item.bbox[3] * scale_y,
                            ),
                        )
                        for index, item in enumerate(ground_truth)
                        if item.bbox is not None and len(item.bbox) == 4
                    ]
                    with self._lock:
                        current_config = deepcopy(self._current_config)
                    cur_conditions = dict(scenario_conditions)
                    cur_conditions.update(current_config)
                    validation = evaluate_detections(
                        last_detections,
                        scaled_ground_truth,
                        frame_id=frame.frame_number,
                        scenario_id=scenario_conditions["scenario_id"],
                        run_id=run_id,
                        scenario_conditions=cur_conditions,
                    )
                    frame_metrics.append(validation)

                    last_risk = None
                    if frame.vehicle_state is not None:
                        last_risk = risk_engine.calculate_risk(
                            last_detections,
                            frame.vehicle_state,
                        )
                        if runner.backend == BACKEND_MOCK:
                            risk_samples.append(
                                {
                                    "timestamp": float(frame.timestamp),
                                    "risk_score": float(last_risk.risk_score),
                                }
                            )

                    pipeline_status = perception_pipeline.get_status()

                    self.runtime.publish_frame(
                        backend=runner.backend,
                        frame_id=frame.frame_number,
                        timestamp=frame.timestamp,
                        detections=(
                            last_detections
                            if runner.backend == "mock"
                            else pipeline_detections
                        ),
                        scenario_conditions=cur_conditions,
                        metrics={
                            "frames_processed": pipeline_status["frames_processed"],
                            "detection_count": len(last_detections),
                            "pipeline": pipeline_status,
                            "validation": {
                                "prediction_count": validation.prediction_count,
                                "ground_truth_count": validation.ground_truth_count,
                                "true_positives": validation.true_positives,
                                "false_positives": validation.false_positives,
                                "missed_detections": validation.missed_detections,
                                "precision": validation.precision,
                                "recall": validation.recall,
                                "f1": validation.f1,
                                "matched_iou": validation.matched_iou,
                            },
                        },
                        risk_assessment=last_risk,
                        failures=validation.failure_records,
                        camera_frame=camera_frame if runner.backend == "carla" else None,
                        camera_frames=frame.camera_views if runner.backend == "carla" else None,
                    )
            completed = True
        except Exception as exc:
            logger.error(f"Error in SimulationService loop: {exc}", exc_info=True)
        finally:
            if completed and runner is not None and (
                frame_metrics or runner.backend == BACKEND_MOCK
            ):
                try:
                    run_metrics = aggregate_run_metrics(
                        frame_metrics,
                        scenario_id=str(scenario_conditions["scenario_id"]),
                        run_id=run_id,
                        scenario_conditions=scenario_conditions,
                        parameters={
                            "backend": backend,
                            "scenario_config": config,
                        },
                    )
                    if runner.backend == BACKEND_MOCK:
                        risk_config = config.get("risk_analysis", {})
                        threshold = (
                            risk_config.get("threshold", settings.RISK_THRESHOLD)
                            if isinstance(risk_config, Mapping)
                            else settings.RISK_THRESHOLD
                        )
                        scenario_result = ScenarioResult(
                            scenario_name=str(
                                scenario_conditions.get("scenario_name")
                                or scenario_conditions["scenario_id"]
                            ),
                            run_id=run_id,
                            success=True,
                            exit_status="completed",
                            duration_s=(
                                max(frame_timestamps) - min(frame_timestamps)
                                if frame_timestamps
                                else 0.0
                            ),
                            events=scenario_events,
                        )
                        scenario_metrics = ScenarioEvaluator(
                            risk_threshold=float(threshold),
                        ).evaluate(scenario_result, risk_samples)
                        self.history_store.save_run(
                            run_metrics,
                            scenario_metrics=scenario_metrics,
                        )
                    else:
                        self.history_store.save_run(run_metrics)
                except Exception:
                    logger.exception("Could not persist completed simulation history.")
            self.runtime.stop()
            with self._lock:
                self._active_runner = None
                if self._thread is threading.current_thread():
                    self._thread = None
            logger.info("🛑 SimulationService loop stopped.")

    @staticmethod
    def _scenario_events_for_frame(frame: Any) -> list[ScenarioEvent]:
        events: list[ScenarioEvent] = []
        for event in frame.collision_events:
            events.append(
                ScenarioEvent(
                    type="collision",
                    severity="critical",
                    timestamp=float(event.get("timestamp", frame.timestamp)),
                    message=(
                        f"Collision with {event.get('other_actor', 'unknown actor')}; "
                        f"impulse={event.get('impulse_norm', 'unknown')}."
                    ),
                )
            )
        for event in frame.lane_invasions:
            markings = event.get("crossed_markings", [])
            events.append(
                ScenarioEvent(
                    type="lane_invasion",
                    severity="warning",
                    timestamp=float(event.get("timestamp", frame.timestamp)),
                    message=f"Crossed lane markings: {', '.join(map(str, markings))}.",
                )
            )
        return events
