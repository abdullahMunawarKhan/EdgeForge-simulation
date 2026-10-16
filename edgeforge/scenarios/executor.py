"""Safe execution adapter and dry-run validation for EdgeForge scenarios.

Connects ranked recommendations and candidate scenarios to the simulation runner,
strictly separating recommendation generation from execution, validating parameter
bounds, associating candidate and run IDs, and recording completed runs to the
historical store.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from edgeforge.config import settings
from edgeforge.data.history import RunHistoryStore
from edgeforge.data.models import DetectedObject, PerceptionFailureRecord
from edgeforge.perception.validation import (
    FailureSeverityRules,
    GroundTruthObject,
    RunValidationMetrics,
    ValidationMetrics,
    aggregate_run_metrics,
    evaluate_detections,
)
from edgeforge.scenarios.generator import (
    CARLA_WEATHER_PRESETS,
    KNOWN_UNSUPPORTED_PARAMETERS,
    SUPPORTED_MAPS,
    RankedScenario,
    ScenarioCandidate,
    WeatherParameters,
)
from edgeforge.simulation.scenario_runner import BACKEND_CARLA, BACKEND_MOCK, ScenarioRunner
from edgeforge.utils import get_logger

logger = get_logger(__name__)


class ExecutionStatus(str, Enum):
    """Lifecycle states distinguishing recommendations from attempted and completed runs."""

    RECOMMENDED = "recommended"
    VALIDATED = "validated"
    REJECTED = "rejected"
    ATTEMPTED = "attempted"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExecutionResult:
    """Outcome of a scenario execution or dry-run validation."""

    candidate_id: str
    scenario_id: str
    run_id: str
    status: ExecutionStatus
    backend: str
    scenario_config: dict[str, Any]
    metrics: Optional[RunValidationMetrics] = None
    error_message: Optional[str] = None
    persisted: bool = False
    sim_frames: int = 0
    sim_time_s: float = 0.0
    dry_run_summary: Optional[str] = None
    validation_errors: list[str] = field(default_factory=list)

    @property
    def is_successful(self) -> bool:
        """True only if the scenario completed execution and produced valid metrics."""
        return self.status == ExecutionStatus.COMPLETED and self.metrics is not None


def validate_scenario_config(
    candidate_or_config: ScenarioCandidate | RankedScenario | dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate that a scenario stays within supported parameter ranges and features.

    Returns:
        (is_valid, error_messages, normalized_runner_config)
    """
    errors: list[str] = []

    # 1. Normalize into a runner config dict
    if isinstance(candidate_or_config, RankedScenario):
        cfg = candidate_or_config.scenario_config or {}
        candidate_id = candidate_or_config.candidate_id
        scenario_id = candidate_or_config.scenario_id
        unsupported = list(candidate_or_config.unsupported_features)
    elif isinstance(candidate_or_config, ScenarioCandidate):
        cfg = candidate_or_config.to_runner_config()
        candidate_id = candidate_or_config.candidate_id
        scenario_id = candidate_or_config.scenario_id
        unsupported = list(candidate_or_config.unsupported_features)
    elif isinstance(candidate_or_config, dict):
        cfg = dict(candidate_or_config)
        candidate_id = str(cfg.get("candidate_id") or cfg.get("generated_metadata", {}).get("candidate_id", "untracked_candidate"))
        scenario_id = str(cfg.get("name", "unnamed_scenario"))
        unsupported = list(cfg.get("generated_metadata", {}).get("unsupported_features", []))
    else:
        return False, [f"Invalid candidate type: {type(candidate_or_config)}"], {}

    # 2. Check unsupported features
    if unsupported:
        errors.append(f"Scenario requests unsupported features: {unsupported}")

    # Check for known unsupported parameter keys in config
    for key in KNOWN_UNSUPPORTED_PARAMETERS:
        if key in cfg or ("generated_metadata" in cfg and key in cfg["generated_metadata"]):
            errors.append(f"Scenario config contains unsupported parameter: '{key}'")

    # 3. Validate Map
    map_name = cfg.get("map")
    if not map_name:
        errors.append("Scenario config missing required 'map' field.")
    elif map_name not in SUPPORTED_MAPS:
        errors.append(f"Map '{map_name}' is not in supported maps: {SUPPORTED_MAPS}")

    # 4. Validate Weather
    fine_weather = cfg.get("fine_weather") or cfg.get("generated_metadata", {}).get("fine_weather")
    if isinstance(cfg.get("weather"), dict):
        fine_weather = cfg["weather"]

    if fine_weather and isinstance(fine_weather, dict):
        ranges = {
            "cloudiness": (0.0, 100.0),
            "precipitation": (0.0, 100.0),
            "precipitation_deposits": (0.0, 100.0),
            "wind_intensity": (0.0, 100.0),
            "fog_density": (0.0, 100.0),
            "fog_distance": (0.0, 100.0),
            "wetness": (0.0, 100.0),
            "sun_azimuth_angle": (0.0, 360.0),
            "sun_altitude_angle": (-90.0, 90.0),
        }
        for param, (lo, hi) in ranges.items():
            if param in fine_weather:
                val = fine_weather[param]
                if not isinstance(val, (int, float)) or not math.isfinite(val) or not (lo <= val <= hi):
                    errors.append(
                        f"Weather parameter '{param}' = {val} is outside supported range [{lo}, {hi}]."
                    )

    # 5. Validate Traffic & Actors
    traffic = cfg.get("traffic", {})
    if isinstance(traffic, dict):
        for actor_kind in ("vehicles", "pedestrians", "bicycles"):
            cnt = traffic.get(actor_kind, 0)
            if not isinstance(cnt, int) or cnt < 0:
                errors.append(f"Traffic '{actor_kind}' count must be a non-negative integer, got {cnt}.")
    else:
        errors.append("Scenario config 'traffic' must be a dictionary.")

    ego = cfg.get("ego_vehicle", {})
    if isinstance(ego, dict):
        spawn_idx = ego.get("spawn_point_index", 0)
        if not isinstance(spawn_idx, int) or spawn_idx < 0:
            errors.append(f"Ego spawn_point_index must be a non-negative integer, got {spawn_idx}.")
    else:
        errors.append("Scenario config 'ego_vehicle' must be a dictionary.")

    # 6. Validate Sensors
    sensors = cfg.get("sensors", {})
    if not isinstance(sensors, dict) or not sensors.get("rgb_camera", {}).get("enabled", False):
        errors.append("Scenario must configure an enabled 'rgb_camera' sensor.")
    else:
        cam = sensors["rgb_camera"]
        if cam.get("width", 0) <= 0 or cam.get("height", 0) <= 0:
            errors.append("RGB camera width and height must be positive integers.")

    is_valid = len(errors) == 0
    return is_valid, errors, cfg


class ScenarioExecutionManager:
    """Manages dry-run validation, offline/live simulation execution, and historical persistence."""

    def __init__(
        self,
        history_store: Optional[RunHistoryStore] = None,
        default_backend: str = BACKEND_MOCK,
    ) -> None:
        self.history_store = history_store
        self.default_backend = default_backend

    def dry_run(
        self,
        candidate_or_config: ScenarioCandidate | RankedScenario | dict[str, Any],
    ) -> ExecutionResult:
        """Validate candidate without launching CARLA or running simulation.

        Returns a structured ExecutionResult with validation status and human-readable plan.
        """
        is_valid, errors, cfg = validate_scenario_config(candidate_or_config)
        candidate_id = str(cfg.get("candidate_id") or cfg.get("generated_metadata", {}).get("candidate_id", "untracked_candidate"))
        scenario_id = str(cfg.get("name", "unnamed_scenario"))
        run_id = f"dryrun_{uuid.uuid4().hex[:10]}"

        if not is_valid:
            logger.warning(f"❌ Dry-run validation REJECTED '{scenario_id}': {errors}")
            return ExecutionResult(
                candidate_id=candidate_id,
                scenario_id=scenario_id,
                run_id=run_id,
                status=ExecutionStatus.REJECTED,
                backend="dry_run",
                scenario_config=cfg,
                validation_errors=errors,
                error_message="; ".join(errors),
                dry_run_summary="Dry-run rejected due to validation errors.",
            )

        # Build informative dry-run summary
        weather_info = cfg.get("weather", "ClearNoon")
        fine = cfg.get("fine_weather") or cfg.get("generated_metadata", {}).get("fine_weather")
        traffic = cfg.get("traffic", {})

        summary_lines = [
            f"=== DRY-RUN SCENARIO PLAN: {scenario_id} ===",
            f"Candidate ID:     {candidate_id}",
            f"Map:              {cfg.get('map')}",
            f"Weather Preset:   {weather_info}",
            f"Fine Weather:     {fine if fine else '<standard preset>'}",
            f"Traffic Actors:   vehicles={traffic.get('vehicles', 0)}, peds={traffic.get('pedestrians', 0)}, bikes={traffic.get('bicycles', 0)}",
            f"Ego Spawn Index:  {cfg.get('ego_vehicle', {}).get('spawn_point_index', 0)}",
            f"Duration Budget:  {cfg.get('duration_seconds', 30.0):.1f}s",
            f"Backend Target:   {self.default_backend} (offline validation)",
            "Status:           VALIDATED (safe for runner dispatch)",
            "============================================",
        ]
        summary_text = "\n".join(summary_lines)
        logger.info(f"✅ Dry-run validated:\n{summary_text}")

        return ExecutionResult(
            candidate_id=candidate_id,
            scenario_id=scenario_id,
            run_id=run_id,
            status=ExecutionStatus.VALIDATED,
            backend="dry_run",
            scenario_config=cfg,
            validation_errors=[],
            dry_run_summary=summary_text,
        )

    def execute(
        self,
        candidate_or_config: ScenarioCandidate | RankedScenario | dict[str, Any],
        backend: Optional[str] = None,
        dry_run: bool = False,
        detector: Any = None,
        max_frames: Optional[int] = None,
        iou_threshold: float = 0.5,
    ) -> ExecutionResult:
        """Safely execute a candidate scenario using the existing runner workflow.

        If dry_run=True, validates and returns without simulator connection.
        If backend='carla', connects to CARLA server; if unreachable, records failure.
        If backend='mock', executes synthetic simulation and computes perception metrics.
        Persists completed runs to history_store only when valid metrics are produced.
        """
        if dry_run:
            return self.dry_run(candidate_or_config)

        # 1. Validation check
        is_valid, errors, cfg = validate_scenario_config(candidate_or_config)
        candidate_id = str(cfg.get("candidate_id") or cfg.get("generated_metadata", {}).get("candidate_id", "untracked_candidate"))
        scenario_id = str(cfg.get("name", "unnamed_scenario"))
        run_id = f"run_{uuid.uuid4().hex[:12]}"

        if not is_valid:
            logger.error(f"❌ Execution REJECTED for '{scenario_id}': {errors}")
            return ExecutionResult(
                candidate_id=candidate_id,
                scenario_id=scenario_id,
                run_id=run_id,
                status=ExecutionStatus.REJECTED,
                backend=backend or self.default_backend,
                scenario_config=cfg,
                validation_errors=errors,
                error_message="; ".join(errors),
            )

        resolved_backend = backend or self.default_backend

        # 2. CARLA Backend safety check
        if resolved_backend == BACKEND_CARLA:
            try:
                from edgeforge.simulation.carla_client import CarlaClient
                test_client = CarlaClient()
                test_client.connect()
                test_client.disconnect()
            except Exception as exc:
                err = f"CARLA server unreachable at {settings.CARLA_HOST}:{settings.CARLA_PORT} ({exc}). Cannot execute live scenario."
                logger.error(f"🛑 {err}")
                return ExecutionResult(
                    candidate_id=candidate_id,
                    scenario_id=scenario_id,
                    run_id=run_id,
                    status=ExecutionStatus.FAILED,
                    backend=BACKEND_CARLA,
                    scenario_config=cfg,
                    error_message=err,
                )

        # 3. Execution via ScenarioRunner
        logger.info(f"🚀 Launching scenario '{scenario_id}' on backend='{resolved_backend}', run_id='{run_id}'")
        frame_metrics_list: list[ValidationMetrics] = []
        frames_processed = 0
        start_time = datetime.now(timezone.utc)
        sim_elapsed_s = 0.0

        fine = cfg.get("fine_weather") or cfg.get("generated_metadata", {}).get("fine_weather") or {}
        scenario_conditions = {
            "map": cfg.get("map", "Town01"),
            "weather": fine if fine else {"preset": cfg.get("weather", "ClearNoon")},
            "traffic": cfg.get("traffic", {}),
            "actor_configuration": cfg.get("actor_configuration", {}),
            "ego_vehicle": cfg.get("ego_vehicle", {}),
            "sensors": cfg.get("sensors", {}),
            "generated_metadata": cfg.get("generated_metadata", {}),
            "parameters": {
                "duration_seconds": cfg.get("duration_seconds"),
                "fixed_delta_seconds": cfg.get("fixed_delta_seconds", 0.05),
                "iou_threshold": iou_threshold,
            },
        }

        try:
            runner = ScenarioRunner(cfg, backend=resolved_backend)
            with runner.run() as frame_stream:
                for sf in frame_stream:
                    frames_processed += 1
                    sim_elapsed_s = sf.timestamp

                    # Gather ground truth objects
                    gt_objs: list[DetectedObject | GroundTruthObject] = (
                        runner.latest_ground_truth_objects
                    )

                    # Produce or evaluate predictions
                    predictions: list[DetectedObject] = []
                    if detector is not None and hasattr(detector, "detect"):
                        try:
                            predictions = detector.detect(sf.rgb)
                        except Exception as det_exc:
                            logger.warning(f"Detector error at frame {sf.frame_number}: {det_exc}")
                            predictions = []
                    else:
                        # Synthetic deterministic perception evaluator based on weather conditions
                        predictions = self._simulate_perception_detections(gt_objs, cfg, sf.frame_number)

                    # Evaluate detections using standard evaluation formulas
                    fm = evaluate_detections(
                        predictions=predictions,
                        ground_truth=gt_objs,
                        iou_threshold=iou_threshold,
                        frame_id=sf.frame_number,
                        scenario_id=scenario_id,
                        run_id=run_id,
                        scenario_conditions=scenario_conditions,
                    )
                    frame_metrics_list.append(fm)

                    if max_frames is not None and frames_processed >= max_frames:
                        logger.info(f"Target frame limit reached ({frames_processed} frames).")
                        break

            if frames_processed == 0 or not frame_metrics_list:
                raise RuntimeError("Simulation run finished without producing any valid sensor frames.")

            # Aggregate run metrics
            run_metrics: RunValidationMetrics = aggregate_run_metrics(
                frame_metrics=frame_metrics_list,
                scenario_id=scenario_id,
                run_id=run_id,
                scenario_conditions=scenario_conditions,
                # Preserve the normalized config so the run can be reproduced from history.
                parameters={
                    "candidate_id": candidate_id,
                    "backend": resolved_backend,
                    "duration_seconds": cfg.get("duration_seconds"),
                    "fixed_delta_seconds": cfg.get("fixed_delta_seconds", 0.05),
                    "iou_threshold": iou_threshold,
                    "scenario_config": cfg,
                },
                iou_threshold=iou_threshold,
            )

            # Persist to RunHistoryStore
            persisted = False
            if self.history_store is not None:
                self.history_store.save_run(run_metrics, run_id=run_id, scenario_id=scenario_id)
                persisted = True
                logger.info(f"💾 Persisted run '{run_id}' to historical store.")

            logger.success(
                f"🎉 Scenario '{scenario_id}' COMPLETED: frames={frames_processed}, "
                f"TP={run_metrics.true_positives}, FP={run_metrics.false_positives}, "
                f"FN={run_metrics.missed_detections}, F1={run_metrics.f1:.3f}"
            )

            return ExecutionResult(
                candidate_id=candidate_id,
                scenario_id=scenario_id,
                run_id=run_id,
                status=ExecutionStatus.COMPLETED,
                backend=resolved_backend,
                scenario_config=cfg,
                metrics=run_metrics,
                persisted=persisted,
                sim_frames=frames_processed,
                sim_time_s=sim_elapsed_s,
            )

        except Exception as exc:
            logger.exception(f"❌ Execution FAILED for scenario '{scenario_id}': {exc}")
            return ExecutionResult(
                candidate_id=candidate_id,
                scenario_id=scenario_id,
                run_id=run_id,
                status=ExecutionStatus.FAILED,
                backend=resolved_backend,
                scenario_config=cfg,
                error_message=str(exc),
                persisted=False,
                sim_frames=frames_processed,
                sim_time_s=sim_elapsed_s,
            )

    @staticmethod
    def _simulate_perception_detections(
        ground_truth: list[DetectedObject],
        config: dict[str, Any],
        frame_idx: int,
    ) -> list[DetectedObject]:
        """Produce deterministic synthetic predictions that degrade realistically under adverse conditions.

        Allows offline verification of perception evaluation without requiring live CARLA or GPU model weights.
        """
        fine = dict(config.get("fine_weather") or config.get("generated_metadata", {}).get("fine_weather") or {})
        preset_name = config.get("weather", "ClearNoon")
        if isinstance(preset_name, str) and preset_name in CARLA_WEATHER_PRESETS:
            preset_defaults = CARLA_WEATHER_PRESETS[preset_name]
            for k, v in preset_defaults.items():
                if k not in fine:
                    fine[k] = v

        fog = float(fine.get("fog_density", 0.0))
        rain = float(fine.get("precipitation", 0.0))
        sun_alt = float(fine.get("sun_altitude_angle", 60.0))

        # Seed per frame with stable deterministic scenario salt across separate Python processes
        name_bytes = str(config.get("name", "")).encode("utf-8")
        scenario_salt = int(hashlib.sha256(name_bytes).hexdigest()[:8], 16) % 10007
        rng = random.Random(frame_idx * 1009 + int(fog * 10) + int(rain * 10) + scenario_salt)

        predictions: list[DetectedObject] = []

        # Detection probability drops with fog and distance
        for gt in ground_truth:
            dist = max(1.0, gt.distance)
            # Base detection probability
            p_detect = 0.96

            # Fog degradation: drops sharply beyond 25m in heavy fog
            if fog > 10.0:
                p_detect -= (fog / 100.0) * min(0.65, (dist / 35.0) ** 1.5)

            # Rain spray degradation
            if rain > 20.0:
                p_detect -= (rain / 100.0) * 0.15

            # Night/low sun degradation
            if sun_alt < 0.0:
                p_detect -= 0.20
            elif sun_alt < 20.0:
                p_detect -= 0.08

            p_detect = max(0.10, min(0.99, p_detect))

            if rng.random() <= p_detect:
                # Add box with slight IoU perturbation
                jitter = (fog * 0.001) + (rain * 0.0008)
                x1, y1, x2, y2 = gt.bbox
                w = max(4.0, x2 - x1)
                h = max(4.0, y2 - y1)
                dx = (rng.random() - 0.5) * jitter * w
                dy = (rng.random() - 0.5) * jitter * h
                pred_bbox = [x1 + dx, y1 + dy, x2 + dx, y2 + dy]

                conf = gt.confidence * (1.0 - (fog / 250.0) - (rain / 300.0))
                if sun_alt < 0.0:
                    conf *= 0.85
                conf_jitter = (rng.random() - 0.5) * 0.04
                conf = max(0.40, min(0.99, conf + conf_jitter))

                predictions.append(
                    DetectedObject(
                        object_id=f"pred_{gt.object_id}",
                        object_type=gt.object_type,
                        confidence=conf,
                        distance=gt.distance,
                        relative_speed=gt.relative_speed,
                        bbox=pred_bbox,
                        timestamp=gt.timestamp,
                    )
                )

        # Adverse conditions occasionally introduce spurious false positives (e.g. reflections)
        fp_chance = (rain * 0.002) + (fog * 0.0015)
        if rng.random() < fp_chance and ground_truth:
            ref = ground_truth[0]
            predictions.append(
                DetectedObject(
                    object_id=f"fp_{frame_idx}",
                    object_type="car",
                    confidence=0.52,
                    distance=ref.distance + 12.0,
                    relative_speed=0.0,
                    bbox=[ref.bbox[0] + 50.0, ref.bbox[1], ref.bbox[2] + 50.0, ref.bbox[3]],
                    timestamp=ref.timestamp,
                )
            )

        return predictions
