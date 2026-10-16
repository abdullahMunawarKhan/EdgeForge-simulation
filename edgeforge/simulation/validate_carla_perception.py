"""Run reproducible live CARLA YOLO-versus-actor-box validation.

Run from the repository root:
    python -m edgeforge.simulation.validate_carla_perception --frames 50
"""

from __future__ import annotations

import argparse
import json
import queue
import sys
import time
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from edgeforge.config import settings
from edgeforge.data.models import PerceptionFailureRecord
from edgeforge.perception import (
    FailureSeverityRules,
    ObjectDetector,
    evaluate_detections,
    export_failure_report,
    extract_carla_ground_truth,
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _select_target_spawn_points(
    ego_transform: Any,
    spawn_points: list[Any],
    ego_spawn_index: int,
) -> list[tuple[int, Any]]:
    ego_location = ego_transform.location
    forward = ego_transform.get_forward_vector()
    candidates: list[tuple[float, float, int, Any]] = []

    for index, spawn_point in enumerate(spawn_points):
        if index == ego_spawn_index:
            continue
        location = spawn_point.location
        dx = location.x - ego_location.x
        dy = location.y - ego_location.y
        forward_distance = dx * forward.x + dy * forward.y
        lateral_distance = abs(dx * forward.y - dy * forward.x)
        vertical_distance = abs(location.z - ego_location.z)
        if (
            8.0 <= forward_distance <= 35.0
            and lateral_distance <= 6.0
            and vertical_distance <= 3.0
        ):
            candidates.append((forward_distance, lateral_distance, index, spawn_point))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    return [(index, transform) for _, _, index, transform in candidates]


def run_live_validation(
    frame_count: int = 50,
    iou_threshold: float = 0.5,
    ego_spawn_index: int = 0,
    target_count: int = 2,
    fixed_delta_seconds: float = 0.05,
    scenario_id: str = "phase4-live-validation",
    baseline_confidence: Mapping[str, float] | None = None,
    severity_rules: FailureSeverityRules | None = None,
) -> dict[str, Any]:
    """Connect to CARLA, spawn a controlled scene, and aggregate frame metrics."""
    import carla

    if frame_count <= 0 or target_count <= 0 or fixed_delta_seconds <= 0:
        raise ValueError("Frame count, target count, and fixed delta must be positive.")
    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("IoU threshold must be between 0.0 and 1.0.")
    if ego_spawn_index < 0:
        raise ValueError("Ego spawn-point index must be non-negative.")
    active_severity_rules = severity_rules or FailureSeverityRules()

    client = carla.Client(settings.CARLA_HOST, settings.CARLA_PORT)
    client.set_timeout(settings.CARLA_TIMEOUT)
    world = client.get_world()
    original_world_settings = world.get_settings()
    spawned_actors: list[Any] = []
    camera = None
    frames: queue.Queue[tuple[int, np.ndarray]] = queue.Queue(maxsize=2)
    detector = ObjectDetector()
    frame_metrics: list[dict[str, Any]] = []
    failure_records = []

    try:
        world_settings = world.get_settings()
        world_settings.synchronous_mode = True
        world_settings.fixed_delta_seconds = fixed_delta_seconds
        world.apply_settings(world_settings)

        spawn_points = list(world.get_map().get_spawn_points())
        if not spawn_points:
            raise RuntimeError("The active CARLA map has no vehicle spawn points.")

        ego_blueprint = world.get_blueprint_library().find("vehicle.tesla.model3")
        ego = None
        selected_ego_index = None
        for offset in range(len(spawn_points)):
            index = (ego_spawn_index + offset) % len(spawn_points)
            ego = world.try_spawn_actor(ego_blueprint, spawn_points[index])
            if ego is not None:
                selected_ego_index = index
                break
        if ego is None or selected_ego_index is None:
            raise RuntimeError("Could not spawn the validation ego vehicle.")
        spawned_actors.append(ego)
        ego.set_autopilot(False)

        target_points = _select_target_spawn_points(
            ego.get_transform(),
            spawn_points,
            selected_ego_index,
        )
        if not target_points:
            raise RuntimeError(
                "No CARLA spawn points are in the ego camera's forward test region."
            )

        target_blueprint = world.get_blueprint_library().find("vehicle.tesla.model3")
        targets = []
        for spawn_index, transform in target_points:
            actor = world.try_spawn_actor(target_blueprint, transform)
            if actor is not None:
                actor.set_autopilot(False)
                spawned_actors.append(actor)
                targets.append({"actor_id": int(actor.id), "spawn_index": spawn_index})
            if len(targets) >= target_count:
                break
        if len(targets) != target_count:
            raise RuntimeError(
                f"Spawned {len(targets)} of {target_count} controlled target "
                "vehicles; check the selected map, nearby spawn-point occupancy, "
                "and CARLA server state."
            )

        camera_blueprint = world.get_blueprint_library().find("sensor.camera.rgb")
        camera_blueprint.set_attribute("image_size_x", str(settings.CAMERA_WIDTH))
        camera_blueprint.set_attribute("image_size_y", str(settings.CAMERA_HEIGHT))
        camera_blueprint.set_attribute("fov", str(settings.CAMERA_FOV))
        camera_blueprint.set_attribute("sensor_tick", str(fixed_delta_seconds))

        camera = world.spawn_actor(
            camera_blueprint,
            carla.Transform(carla.Location(x=1.5, z=2.4)),
            attach_to=ego,
        )
        spawned_actors.append(camera)

        def on_image(image: Any) -> None:
            bgra = np.frombuffer(image.raw_data, dtype=np.uint8).reshape(
                (image.height, image.width, 4)
            )
            frame = bgra[:, :, :3].copy()
            if frames.full():
                try:
                    frames.get_nowait()
                except queue.Empty:
                    pass
            try:
                frames.put_nowait((int(image.frame), frame))
            except queue.Full:
                pass

        camera.listen(on_image)
        map_name = world.get_map().name
        weather = world.get_weather()
        weather_conditions = {
            name: float(getattr(weather, name))
            for name in (
                "cloudiness",
                "precipitation",
                "precipitation_deposits",
                "wind_intensity",
                "fog_density",
                "fog_distance",
                "wetness",
                "sun_azimuth_angle",
                "sun_altitude_angle",
            )
            if hasattr(weather, name)
        }
        scenario_conditions = {
            "map": map_name,
            "weather": weather_conditions,
            "fixed_delta_seconds": fixed_delta_seconds,
            "camera": {
                "width": settings.CAMERA_WIDTH,
                "height": settings.CAMERA_HEIGHT,
                "horizontal_fov_degrees": settings.CAMERA_FOV,
            },
        }
        print(
            "Live validation uses synchronous CARLA ticks; the script restores "
            "the original world settings on exit."
        )

        controlled_actor_ids = {target["actor_id"] for target in targets}
        stale_frames = 0
        processed_frames = 0
        total_true_positives = 0
        total_false_positives = 0
        total_missed_detections = 0

        while processed_frames < frame_count:
            expected_frame = int(world.tick())
            deadline = time.monotonic() + settings.CARLA_TIMEOUT
            image_frame = -1
            bgr_frame = None
            while time.monotonic() < deadline:
                try:
                    image_frame, bgr_frame = frames.get(
                        timeout=max(0.01, deadline - time.monotonic())
                    )
                except queue.Empty:
                    break
                if image_frame == expected_frame:
                    break
                if image_frame < expected_frame:
                    stale_frames += 1
                    continue
                raise RuntimeError(
                    f"Camera frame {image_frame} arrived ahead of CARLA tick "
                    f"{expected_frame}; refusing to compare mismatched frames."
                )

            if bgr_frame is None or image_frame != expected_frame:
                raise TimeoutError(
                    f"No RGB image for CARLA frame {expected_frame} within "
                    f"{settings.CARLA_TIMEOUT:.1f} seconds."
                )

            predictions = detector.detect(bgr_frame)
            ground_truth = extract_carla_ground_truth(
                actors=list(world.get_actors()),
                ego_actor=ego,
                camera_transform=camera.get_transform(),
                image_width=settings.CAMERA_WIDTH,
                image_height=settings.CAMERA_HEIGHT,
                horizontal_fov_degrees=settings.CAMERA_FOV,
                actor_ids=controlled_actor_ids,
            )
            metrics = evaluate_detections(
                predictions,
                ground_truth,
                iou_threshold=iou_threshold,
                scenario_conditions=scenario_conditions,
                frame_id=expected_frame,
                scenario_id=scenario_id,
                baseline_confidence=baseline_confidence,
                severity_rules=active_severity_rules,
            )
            failure_records.extend(metrics.failure_records)
            total_true_positives += metrics.true_positives
            total_false_positives += metrics.false_positives
            total_missed_detections += metrics.missed_detections
            frame_metrics.append(
                {
                    "frame": expected_frame,
                    "predictions": metrics.prediction_count,
                    "ground_truth": metrics.ground_truth_count,
                    "prediction_details": [
                        {
                            "class": prediction.object_type,
                            "confidence": prediction.confidence,
                            "bbox": prediction.bbox,
                        }
                        for prediction in predictions
                    ],
                    "ground_truth_details": [
                        {
                            "actor_id": item.actor_id,
                            "class": item.object_type,
                            "bbox": item.bbox,
                        }
                        for item in ground_truth
                    ],
                    "true_positives": metrics.true_positives,
                    "false_positives": metrics.false_positives,
                    "missed_detections": metrics.missed_detections,
                    "failures": [
                        failure.model_dump(mode="json")
                        for failure in metrics.failure_records
                    ],
                    "matches": [
                        {
                            "prediction_index": match.prediction_index,
                            "ground_truth_actor_id": ground_truth[
                                match.ground_truth_index
                            ].actor_id,
                            "iou": match.iou,
                        }
                        for match in metrics.matches
                    ],
                }
            )
            processed_frames += 1

    finally:
        try:
            if camera is not None:
                camera.stop()
        finally:
            try:
                for actor in reversed(spawned_actors):
                    actor.destroy()
            finally:
                world.apply_settings(original_world_settings)

    total_predictions = total_true_positives + total_false_positives
    total_ground_truth = total_true_positives + total_missed_detections
    precision = (
        total_true_positives / total_predictions if total_predictions else 0.0
    )
    recall = (
        total_true_positives / total_ground_truth if total_ground_truth else 0.0
    )
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )

    return {
        "status": "completed",
        "server": {"host": settings.CARLA_HOST, "port": settings.CARLA_PORT},
        "map": map_name,
        "scenario": {
            "scenario_id": scenario_id,
            "ego_spawn_index": selected_ego_index,
            "ego_actor_id": int(ego.id),
            "target_vehicles": targets,
            "fixed_delta_seconds": fixed_delta_seconds,
            "weather": weather_conditions,
            "camera": {
                "width": settings.CAMERA_WIDTH,
                "height": settings.CAMERA_HEIGHT,
                "horizontal_fov_degrees": settings.CAMERA_FOV,
            },
        },
        "detector": {
            "model": detector.model_name,
            "device": detector.device,
            "confidence_threshold": detector.confidence_threshold,
        },
        "failure_rules": {
            "low_confidence_threshold": active_severity_rules.low_confidence_threshold,
            "confidence_degradation_margin": (
                active_severity_rules.confidence_degradation_margin
            ),
            "severity_by_type": dict(active_severity_rules.severity_by_type or {}),
            "baseline_confidence": dict(baseline_confidence or {}),
        },
        "metrics": {
            "iou_threshold": iou_threshold,
            "frames_requested": frame_count,
            "frames_processed": processed_frames,
            "stale_camera_frames_discarded": stale_frames,
            "predictions": total_predictions,
            "ground_truth_objects": total_ground_truth,
            "true_positives": total_true_positives,
            "false_positives": total_false_positives,
            "missed_detections": total_missed_detections,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "aggregation": "micro-averaged counts across processed frames",
            "zero_denominator_convention": "metric is 0.0",
        },
        "failures": [
            failure.model_dump(mode="json") for failure in failure_records
        ],
        "frames": frame_metrics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare YOLO camera detections with CARLA actor bounding boxes "
            "for a controlled, repeatable scene."
        )
    )
    parser.add_argument("--frames", type=_positive_int, default=50)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--ego-spawn-index", type=int, default=0)
    parser.add_argument("--targets", type=_positive_int, default=2)
    parser.add_argument("--fixed-delta", type=_positive_float, default=0.05)
    parser.add_argument("--scenario-id", default="phase4-live-validation")
    parser.add_argument(
        "--low-confidence-threshold",
        type=float,
        default=FailureSeverityRules().low_confidence_threshold,
    )
    parser.add_argument(
        "--confidence-degradation-margin",
        type=float,
        default=FailureSeverityRules().confidence_degradation_margin,
    )
    parser.add_argument(
        "--baseline-confidence",
        type=Path,
        help="Optional JSON object mapping normalized class names to baseline confidence.",
    )
    parser.add_argument(
        "--failure-severity",
        action="append",
        default=[],
        metavar="TYPE=SEVERITY",
        help="Override a failure severity, e.g. missed_detection=critical.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / settings.RUN_DIR / "phase4-live-validation.json",
        help="JSON report path (default: runs/phase4-live-validation.json).",
    )
    parser.add_argument(
        "--failures-output",
        type=Path,
        default=PROJECT_ROOT / settings.RUN_DIR / "phase4-failures.jsonl",
        help="Failure-record output path (default: runs/phase4-failures.jsonl).",
    )
    parser.add_argument(
        "--failure-format",
        choices=("json", "jsonl"),
        help="Failure export format; defaults from the output file extension.",
    )
    args = parser.parse_args()

    if not 0.0 <= args.iou_threshold <= 1.0:
        parser.error("--iou-threshold must be between 0 and 1")
    if not 0.0 <= args.low_confidence_threshold <= 1.0:
        parser.error("--low-confidence-threshold must be between 0 and 1")
    if not 0.0 <= args.confidence_degradation_margin <= 1.0:
        parser.error("--confidence-degradation-margin must be between 0 and 1")

    baseline_confidence = None
    if args.baseline_confidence is not None:
        loaded_baseline = json.loads(args.baseline_confidence.read_text(encoding="utf-8"))
        if not isinstance(loaded_baseline, dict):
            parser.error("--baseline-confidence must contain a JSON object.")
        baseline_confidence = {}
        for class_name, raw_confidence in loaded_baseline.items():
            if isinstance(raw_confidence, bool):
                parser.error(f"Baseline confidence for {class_name!r} must be a number.")
            try:
                confidence = float(raw_confidence)
            except (TypeError, ValueError, OverflowError):
                parser.error(
                    f"Baseline confidence for {class_name!r} must be a number."
                )
            if (
                not isinstance(class_name, str)
                or not class_name.strip()
                or not isfinite(confidence)
                or not 0.0 <= confidence <= 1.0
            ):
                parser.error(
                    "Baseline confidence entries must use non-empty class names "
                    "and values between 0 and 1."
                )
            baseline_confidence[class_name] = confidence

    severity_by_type = {}
    for override in args.failure_severity:
        failure_type, separator, severity = override.partition("=")
        if not separator:
            parser.error("--failure-severity must use TYPE=SEVERITY.")
        severity_by_type[failure_type] = severity
    try:
        severity_rules = FailureSeverityRules(
            low_confidence_threshold=args.low_confidence_threshold,
            confidence_degradation_margin=args.confidence_degradation_margin,
            severity_by_type=severity_by_type or None,
        )
    except ValueError as exc:
        parser.error(str(exc))

    report = run_live_validation(
        frame_count=args.frames,
        iou_threshold=args.iou_threshold,
        ego_spawn_index=args.ego_spawn_index,
        target_count=args.targets,
        fixed_delta_seconds=args.fixed_delta,
        scenario_id=args.scenario_id,
        baseline_confidence=baseline_confidence,
        severity_rules=severity_rules,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    export_failure_report(
        [
            PerceptionFailureRecord.model_validate(failure)
            for failure in report["failures"]
        ],
        args.failures_output,
        format=args.failure_format,
    )
    print(json.dumps(report["metrics"], indent=2, sort_keys=True))
    print(f"Saved validation report to {args.output}")
    print(f"Saved failure records to {args.failures_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
