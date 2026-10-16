"""Class-aware YOLO detection validation against CARLA camera ground truth."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import isfinite, tan
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

import numpy as np

from edgeforge.data.models import PerceptionFailureRecord
from edgeforge.perception.tracker import compute_iou

_BOX_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 0),
    (4, 5), (5, 6), (6, 7), (7, 4),
    (0, 4), (1, 5), (2, 6), (3, 7),
)
_NEAR_PLANE_M = 1e-3

# Canonical supported object classes evaluated between CARLA GT and YOLO
SUPPORTED_EVALUATION_CLASSES: frozenset[str] = frozenset({
    "car",
    "pedestrian",
    "truck",
    "bus",
    "motorcycle",
    "bicycle",
    "traffic_light",
    "stop_sign",
})


@dataclass(frozen=True)
class GroundTruthObject:
    """A visible CARLA actor projected into camera-image coordinates."""

    actor_id: int
    object_type: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class DetectionMatch:
    """A one-to-one class-aware prediction/ground-truth association."""

    prediction_index: int
    ground_truth_index: int
    iou: float


@dataclass(frozen=True)
class ValidationMetrics:
    """Micro-averaged object-detection metrics for one image/frame."""

    iou_threshold: float
    prediction_count: int
    ground_truth_count: int
    true_positives: int
    false_positives: int
    missed_detections: int
    precision: float
    recall: float
    f1: float
    matches: tuple[DetectionMatch, ...]
    false_positive_indices: tuple[int, ...]
    missed_ground_truth_indices: tuple[int, ...]
    failure_records: tuple[PerceptionFailureRecord, ...] = ()
    matched_iou: float = 0.0
    excluded_prediction_count: int = 0
    excluded_ground_truth_count: int = 0

    @property
    def matched_box_iou(self) -> float:
        """Alias for matched_iou."""
        return self.matched_iou

    @property
    def mean_iou(self) -> float:
        """Alias for matched_iou."""
        return self.matched_iou

    @property
    def false_negatives(self) -> int:
        """Alias for missed_detections."""
        return self.missed_detections


@dataclass(frozen=True)
class FailureSeverityRules:
    """Configurable thresholds and default severities for validation failures."""

    low_confidence_threshold: float = 0.6
    confidence_degradation_margin: float = 0.15
    severity_by_type: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        for name, value in (
            ("low_confidence_threshold", self.low_confidence_threshold),
            ("confidence_degradation_margin", self.confidence_degradation_margin),
        ):
            if not isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0.")

        valid_types = {
            "missed_detection",
            "false_positive",
            "poor_localization",
            "low_confidence",
            "confidence_degradation",
            "invalid_box",
        }
        valid_severities = {"low", "medium", "high", "critical"}
        if self.severity_by_type is not None:
            unknown_types = set(self.severity_by_type) - valid_types
            invalid_severities = set(self.severity_by_type.values()) - valid_severities
            if unknown_types:
                raise ValueError(f"Unknown failure types: {sorted(unknown_types)}")
            if invalid_severities:
                raise ValueError(
                    f"Unknown failure severities: {sorted(invalid_severities)}"
                )

    def severity_for(self, failure_type: str) -> str:
        defaults = {
            "missed_detection": "high",
            "false_positive": "medium",
            "poor_localization": "high",
            "low_confidence": "medium",
            "confidence_degradation": "medium",
            "invalid_box": "high",
        }
        configured = self.severity_by_type or {}
        return configured.get(failure_type, defaults[failure_type])


def carla_actor_class(actor: Any) -> str | None:
    """Map supported CARLA actor blueprints to detector class names.

    CARLA's standard pedestrian and vehicle blueprints do not expose COCO
    labels. Vehicle subtypes are therefore mapped using their blueprint ID;
    unrecognized vehicles are treated as cars. Other actor families are
    included only when their blueprint identifies a supported traffic object.
    """
    if isinstance(actor, dict):
        raw_type = actor.get("type_id", actor.get("object_type", ""))
    else:
        raw_type = getattr(actor, "type_id", "")
    type_id = str(raw_type).lower()

    if type_id.startswith("walker.pedestrian."):
        return "pedestrian"
    if type_id.startswith("traffic.traffic_light"):
        return "traffic_light"
    if type_id.startswith(("traffic.stop", "traffic.stop_sign")):
        return "stop_sign"
    if not type_id.startswith("vehicle."):
        return None

    remainder = type_id.split(".", maxsplit=1)[1] if "." in type_id else type_id
    if any(token in remainder for token in ("crossbike", "bicycle", "diamondback", "omafiets")):
        return "bicycle"
    if any(token in remainder for token in ("motorcycle", "motorbike", "ninja", "harley", "yamaha", "vespa")):
        return "motorcycle"
    if "bus" in remainder:
        return "bus"
    if any(token in remainder for token in ("truck", "carlacola")):
        return "truck"
    return "car"


def project_carla_actor_bbox(
    actor: Any,
    camera_transform: Any,
    image_width: int,
    image_height: int,
    horizontal_fov_degrees: float,
) -> tuple[float, float, float, float] | None:
    """Project an actor's oriented CARLA bounding box into an RGB image.

    CARLA camera-local coordinates use X forward, Y right, and Z up. Vertices
    behind the near plane are discarded; box edges crossing the near plane
    are clipped before pinhole projection.
    """
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image dimensions must be positive.")
    if not 0.0 < horizontal_fov_degrees < 180.0:
        raise ValueError("Horizontal FOV must be between 0 and 180 degrees.")

    actor_transform = actor.get_transform()
    world_vertices = actor.bounding_box.get_world_vertices(actor_transform)
    if len(world_vertices) != 8:
        raise ValueError("CARLA actor bounding boxes must have exactly 8 vertices.")

    world_to_camera = np.asarray(camera_transform.get_inverse_matrix(), dtype=np.float64)
    if world_to_camera.shape != (4, 4) or not np.all(np.isfinite(world_to_camera)):
        raise ValueError("Camera inverse transform must be a finite 4x4 matrix.")

    homogeneous_vertices = np.asarray(
        [[vertex.x, vertex.y, vertex.z, 1.0] for vertex in world_vertices],
        dtype=np.float64,
    )
    camera_vertices = (world_to_camera @ homogeneous_vertices.T).T[:, :3]

    points = [point for point in camera_vertices if point[0] >= _NEAR_PLANE_M]
    for first_index, second_index in _BOX_EDGES:
        first = camera_vertices[first_index]
        second = camera_vertices[second_index]
        first_in_front = first[0] >= _NEAR_PLANE_M
        second_in_front = second[0] >= _NEAR_PLANE_M
        if first_in_front == second_in_front:
            continue

        front = first if first_in_front else second
        behind = second if first_in_front else first
        fraction = (_NEAR_PLANE_M - front[0]) / (behind[0] - front[0])
        points.append(front + fraction * (behind - front))

    if not points:
        return None

    projected = np.asarray(points, dtype=np.float64)
    focal_length = image_width / (
        2.0 * tan(np.deg2rad(horizontal_fov_degrees) / 2.0)
    )
    center_x = image_width / 2.0
    center_y = image_height / 2.0

    image_x = focal_length * projected[:, 1] / projected[:, 0] + center_x
    image_y = center_y - focal_length * projected[:, 2] / projected[:, 0]
    x1 = max(0.0, min(float(image_width), float(np.min(image_x))))
    y1 = max(0.0, min(float(image_height), float(np.min(image_y))))
    x2 = max(0.0, min(float(image_width), float(np.max(image_x))))
    y2 = max(0.0, min(float(image_height), float(np.max(image_y))))

    if not all(isfinite(value) for value in (x1, y1, x2, y2)):
        return None
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def extract_carla_ground_truth(
    actors: Sequence[Any],
    ego_actor: Any,
    camera_transform: Any,
    image_width: int,
    image_height: int,
    horizontal_fov_degrees: float,
    actor_ids: set[int] | None = None,
) -> list[GroundTruthObject]:
    """Project supported, visible actors to image-space ground-truth boxes.

    Supplying ``actor_ids`` restricts the result to a controlled set of actors,
    which is useful for reproducible tests that should not count unrelated
    traffic already present in the CARLA world.
    """
    ego_id = int(ego_actor.id)
    output: list[GroundTruthObject] = []
    for actor in actors:
        actor_id = int(actor.id)
        if actor_id == ego_id or (actor_ids is not None and actor_id not in actor_ids):
            continue

        object_type = carla_actor_class(actor)
        if object_type is None:
            continue

        bbox = project_carla_actor_bbox(
            actor,
            camera_transform,
            image_width,
            image_height,
            horizontal_fov_degrees,
        )
        if bbox is not None:
            output.append(
                GroundTruthObject(
                    actor_id=actor_id,
                    object_type=object_type,
                    bbox=bbox,
                )
            )
    return output


def _field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _validated_bbox(bbox: Any) -> tuple[float, float, float, float] | None:
    try:
        if bbox is None or len(bbox) != 4:
            return None
    except TypeError:
        return None
    if any(isinstance(value, bool) for value in bbox):
        return None
    try:
        coordinates = tuple(float(value) for value in bbox)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(isfinite(value) for value in coordinates):
        return None
    if coordinates[2] <= coordinates[0] or coordinates[3] <= coordinates[1]:
        return None
    return coordinates


def _normalized_class(object_type: Any) -> str | None:
    if object_type is None:
        return None
    normalized_type = str(object_type).strip().lower().replace(" ", "_")
    return normalized_type or None


def _box_and_class(item: Any) -> tuple[Sequence[float], str]:
    coordinates = _validated_bbox(_field(item, "bbox"))
    normalized_type = _normalized_class(_field(item, "object_type"))
    if coordinates is None:
        raise ValueError("Bounding boxes must have four finite, ordered coordinates.")
    if normalized_type is None:
        raise ValueError("Object class names must not be empty.")
    return coordinates, normalized_type


def _valid_confidence(item: Any) -> float | None:
    raw_confidence = _field(item, "confidence")
    if isinstance(raw_confidence, bool):
        return None
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return None
    return confidence


def _record(
    failure_type: str,
    rules: FailureSeverityRules,
    scenario_conditions: Mapping[str, Any] | None,
    frame_id: int | None,
    scenario_id: str | None,
    *,
    run_id: str | None = None,
    item: Any = None,
    ground_truth: Any = None,
    object_class: str | None = None,
    confidence: float | None = None,
    baseline_confidence: float | None = None,
    iou: float | None = None,
    message: str = "",
) -> PerceptionFailureRecord:
    actor_id = _field(ground_truth, "actor_id")
    try:
        actor_id = int(actor_id) if actor_id is not None else None
    except (TypeError, ValueError, OverflowError):
        actor_id = None
    return PerceptionFailureRecord(
        failure_type=failure_type,
        scenario_conditions=dict(scenario_conditions or {}),
        object_class=(
            object_class
            or _normalized_class(_field(item, "object_type"))
            or _normalized_class(_field(ground_truth, "object_type"))
        ),
        confidence=confidence if confidence is not None else _valid_confidence(item),
        baseline_confidence=baseline_confidence,
        predicted_bbox=(
            list(box)
            if (box := _validated_bbox(_field(item, "bbox"))) is not None
            else None
        ),
        ground_truth_bbox=(
            list(box)
            if (box := _validated_bbox(_field(ground_truth, "bbox"))) is not None
            else None
        ),
        iou=iou,
        severity=rules.severity_for(failure_type),
        frame_id=frame_id,
        scenario_id=scenario_id,
        run_id=run_id,
        actor_id=actor_id,
        message=message,
    )


def export_failure_report(
    failures: Sequence[PerceptionFailureRecord],
    destination: str | Path,
    format: Literal["json", "jsonl"] | None = None,
) -> Path:
    """Write structured failure records as a JSON array or JSON Lines."""
    path = Path(destination)
    report_format = format or (
        "jsonl" if path.suffix.lower() in {".jsonl", ".ndjson"} else "json"
    )
    if report_format not in {"json", "jsonl"}:
        raise ValueError("Failure report format must be 'json' or 'jsonl'.")

    payload = [failure.model_dump(mode="json") for failure in failures]
    path.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "jsonl":
        serialized = "".join(
            json.dumps(record, sort_keys=True, allow_nan=False) + "\n"
            for record in payload
        )
    else:
        serialized = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    path.write_text(serialized, encoding="utf-8")
    return path


def evaluate_detections(
    predictions: Sequence[Any],
    ground_truth: Sequence[GroundTruthObject],
    iou_threshold: float = 0.5,
    *,
    evaluation_classes: Sequence[str] | set[str] | None = None,
    excluded_classes: Sequence[str] | set[str] | None = None,
    scenario_conditions: Mapping[str, Any] | None = None,
    frame_id: int | None = None,
    scenario_id: str | None = None,
    run_id: str | None = None,
    baseline_confidence: Mapping[str, float] | None = None,
    severity_rules: FailureSeverityRules | None = None,
) -> ValidationMetrics:
    """Calculate class-aware, one-to-one matching and frame-level metrics.

    Precision and recall are reported as 0.0 when their denominator is zero.
    Candidate matches are considered in descending IoU order, and a prediction
    and ground-truth object can each participate in at most one match.
    Predictions or ground-truth items whose class is outside ``evaluation_classes``
    (or inside ``excluded_classes``) are excluded from matching and are not
    counted as false positives or missed detections.
    """
    if not isfinite(iou_threshold) or not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("IoU threshold must be between 0.0 and 1.0.")

    rules = severity_rules or FailureSeverityRules()
    prediction_boxes: list[tuple[Sequence[float], str] | None] = []
    ground_truth_boxes: list[tuple[Sequence[float], str] | None] = []
    failure_records: list[PerceptionFailureRecord] = []

    allowed_classes: set[str] | None = None
    if evaluation_classes is not None:
        allowed_classes = {
            norm for c in evaluation_classes if (norm := _normalized_class(c)) is not None
        }

    disallowed_classes: set[str] | None = None
    if excluded_classes is not None:
        disallowed_classes = {
            norm for c in excluded_classes if (norm := _normalized_class(c)) is not None
        }

    def _is_class_evaluated(cls_name: str) -> bool:
        if allowed_classes is not None and cls_name not in allowed_classes:
            return False
        if disallowed_classes is not None and cls_name in disallowed_classes:
            return False
        return True

    excluded_prediction_indices: set[int] = set()
    excluded_ground_truth_indices: set[int] = set()

    for idx, prediction in enumerate(predictions):
        raw_class = _normalized_class(_field(prediction, "object_type"))
        if raw_class is not None and not _is_class_evaluated(raw_class):
            excluded_prediction_indices.add(idx)
            prediction_boxes.append(None)
            continue
        try:
            box_and_cls = _box_and_class(prediction)
            prediction_boxes.append(box_and_cls)
        except (AttributeError, KeyError, TypeError, ValueError):
            prediction_boxes.append(None)
            failure_records.append(
                _record(
                    "invalid_box",
                    rules,
                    scenario_conditions,
                    frame_id,
                    scenario_id,
                    run_id=run_id,
                    item=prediction,
                    message="Prediction is missing a valid class or bounding box.",
                )
            )

    for idx, truth in enumerate(ground_truth):
        raw_class = _normalized_class(_field(truth, "object_type"))
        if raw_class is not None and not _is_class_evaluated(raw_class):
            excluded_ground_truth_indices.add(idx)
            ground_truth_boxes.append(None)
            continue
        try:
            box_and_cls = _box_and_class(truth)
            ground_truth_boxes.append(box_and_cls)
        except (AttributeError, KeyError, TypeError, ValueError):
            ground_truth_boxes.append(None)
            failure_records.append(
                _record(
                    "invalid_box",
                    rules,
                    scenario_conditions,
                    frame_id,
                    scenario_id,
                    run_id=run_id,
                    ground_truth=truth,
                    message="Ground-truth object is missing a valid class or bounding box.",
                )
            )

    candidates: list[DetectionMatch] = []
    overlaps: list[DetectionMatch] = []

    for prediction_index, prediction_entry in enumerate(prediction_boxes):
        if prediction_entry is None:
            continue
        prediction_box, prediction_type = prediction_entry
        for ground_truth_index, ground_truth_entry in enumerate(ground_truth_boxes):
            if ground_truth_entry is None:
                continue
            ground_truth_box, ground_truth_type = ground_truth_entry
            if prediction_type != ground_truth_type:
                continue
            overlap = compute_iou(list(prediction_box), list(ground_truth_box))
            if overlap > 0.0:
                overlaps.append(
                    DetectionMatch(
                        prediction_index=prediction_index,
                        ground_truth_index=ground_truth_index,
                        iou=overlap,
                    )
                )
            if overlap > 0.0 and overlap >= iou_threshold:
                candidates.append(
                    DetectionMatch(
                        prediction_index=prediction_index,
                        ground_truth_index=ground_truth_index,
                        iou=overlap,
                    )
                )

    candidates.sort(key=lambda match: match.iou, reverse=True)
    matched_predictions: set[int] = set()
    matched_ground_truth: set[int] = set()
    matches: list[DetectionMatch] = []
    for candidate in candidates:
        if (
            candidate.prediction_index in matched_predictions
            or candidate.ground_truth_index in matched_ground_truth
        ):
            continue
        matches.append(candidate)
        matched_predictions.add(candidate.prediction_index)
        matched_ground_truth.add(candidate.ground_truth_index)

    true_positives = len(matches)
    false_positive_set = {
        index
        for index in range(len(predictions))
        if index not in matched_predictions
        and index not in excluded_prediction_indices
    }
    missed_ground_truth_set = {
        index
        for index in range(len(ground_truth))
        if index not in matched_ground_truth
        and index not in excluded_ground_truth_indices
    }
    poor_localization_pairs: list[DetectionMatch] = []
    used_false_positives: set[int] = set()
    used_missed_ground_truth: set[int] = set()
    for overlap in sorted(overlaps, key=lambda match: match.iou, reverse=True):
        if overlap.iou >= iou_threshold:
            continue
        if (
            overlap.prediction_index in false_positive_set
            and overlap.ground_truth_index in missed_ground_truth_set
            and overlap.prediction_index not in used_false_positives
            and overlap.ground_truth_index not in used_missed_ground_truth
        ):
            poor_localization_pairs.append(overlap)
            used_false_positives.add(overlap.prediction_index)
            used_missed_ground_truth.add(overlap.ground_truth_index)
    false_positive_indices = tuple(sorted(false_positive_set))
    missed_ground_truth_indices = tuple(sorted(missed_ground_truth_set))
    false_positives = len(false_positive_indices)
    missed_detections = len(missed_ground_truth_indices)

    for pair in poor_localization_pairs:
        failure_records.append(
            _record(
                "poor_localization",
                rules,
                scenario_conditions,
                frame_id,
                scenario_id,
                run_id=run_id,
                item=predictions[pair.prediction_index],
                ground_truth=ground_truth[pair.ground_truth_index],
                confidence=_valid_confidence(predictions[pair.prediction_index]),
                iou=pair.iou,
                message="Same-class detection overlaps the actor, but falls below the IoU threshold.",
            )
        )
    for index in false_positive_indices:
        if index in used_false_positives or prediction_boxes[index] is None:
            continue
        failure_records.append(
            _record(
                "false_positive",
                rules,
                scenario_conditions,
                frame_id,
                scenario_id,
                run_id=run_id,
                item=predictions[index],
                message="Prediction did not match a visible ground-truth object.",
            )
        )
    for index in missed_ground_truth_indices:
        if (
            index in used_missed_ground_truth
            or ground_truth_boxes[index] is None
        ):
            continue
        failure_records.append(
            _record(
                "missed_detection",
                rules,
                scenario_conditions,
                frame_id,
                scenario_id,
                run_id=run_id,
                ground_truth=ground_truth[index],
                message="Visible ground-truth object has no matching prediction.",
            )
        )

    normalized_baseline = {
        _normalized_class(name): value
        for name, value in (baseline_confidence or {}).items()
        if _normalized_class(name) is not None
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
        and 0.0 <= float(value) <= 1.0
    }
    for index, item in enumerate(predictions):
        if index in excluded_prediction_indices:
            continue
        prediction = prediction_boxes[index]
        confidence = _valid_confidence(item)
        if prediction is None or confidence is None:
            continue
        _, object_class = prediction
        if confidence < rules.low_confidence_threshold:
            failure_records.append(
                _record(
                    "low_confidence",
                    rules,
                    scenario_conditions,
                    frame_id,
                    scenario_id,
                    run_id=run_id,
                    item=item,
                    object_class=object_class,
                    confidence=confidence,
                    message=(
                        f"Confidence {confidence:.3f} is below configured threshold "
                        f"{rules.low_confidence_threshold:.3f}."
                    ),
                )
            )
        baseline = normalized_baseline.get(object_class)
        if (
            baseline is not None
            and confidence < baseline - rules.confidence_degradation_margin
        ):
            failure_records.append(
                _record(
                    "confidence_degradation",
                    rules,
                    scenario_conditions,
                    frame_id,
                    scenario_id,
                    run_id=run_id,
                    item=item,
                    object_class=object_class,
                    confidence=confidence,
                    baseline_confidence=float(baseline),
                    message=(
                        f"Confidence decreased from baseline {float(baseline):.3f} "
                        f"by more than {rules.confidence_degradation_margin:.3f}."
                    ),
                )
            )
    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    recall = (
        true_positives / (true_positives + missed_detections)
        if true_positives + missed_detections
        else 0.0
    )
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0

    matched_iou = (
        sum(match.iou for match in matches) / len(matches) if matches else 0.0
    )

    return ValidationMetrics(
        iou_threshold=iou_threshold,
        prediction_count=len(predictions) - len(excluded_prediction_indices),
        ground_truth_count=len(ground_truth) - len(excluded_ground_truth_indices),
        true_positives=true_positives,
        false_positives=false_positives,
        missed_detections=missed_detections,
        precision=precision,
        recall=recall,
        f1=f1,
        matches=tuple(matches),
        false_positive_indices=false_positive_indices,
        missed_ground_truth_indices=missed_ground_truth_indices,
        failure_records=tuple(failure_records),
        matched_iou=matched_iou,
        excluded_prediction_count=len(excluded_prediction_indices),
        excluded_ground_truth_count=len(excluded_ground_truth_indices),
    )


@dataclass(frozen=True)
class RunValidationMetrics:
    """Aggregated validation metrics across a full simulation run or image set."""

    frames_processed: int
    predictions: int
    ground_truth_objects: int
    true_positives: int
    false_positives: int
    missed_detections: int
    precision: float
    recall: float
    f1: float
    matched_iou: float
    iou_threshold: float
    failures: tuple[PerceptionFailureRecord, ...] = ()
    scenario_id: str | None = None
    run_id: str | None = None
    scenario_conditions: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    excluded_predictions: int = 0
    excluded_ground_truth: int = 0

    @property
    def matched_box_iou(self) -> float:
        """Alias for matched_iou."""
        return self.matched_iou

    @property
    def mean_iou(self) -> float:
        """Alias for matched_iou."""
        return self.matched_iou

    @property
    def false_negatives(self) -> int:
        """Alias for missed_detections."""
        return self.missed_detections

    @property
    def tp(self) -> int:
        """Alias for true_positives."""
        return self.true_positives

    @property
    def fp(self) -> int:
        """Alias for false_positives."""
        return self.false_positives

    @property
    def fn(self) -> int:
        """Alias for missed_detections."""
        return self.missed_detections

    def to_dict(self) -> dict[str, Any]:
        """Convert aggregated metrics to a JSON-serializable dictionary."""
        return {
            "iou_threshold": self.iou_threshold,
            "frames_processed": self.frames_processed,
            "predictions": self.predictions,
            "ground_truth_objects": self.ground_truth_objects,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "missed_detections": self.missed_detections,
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "matched_iou": self.matched_iou,
            "matched_box_iou": self.matched_iou,
            "aggregation": "micro-averaged counts across processed frames",
            "zero_denominator_convention": "metric is 0.0",
            "scenario_id": self.scenario_id,
            "run_id": self.run_id,
            "scenario_conditions": self.scenario_conditions,
            "parameters": self.parameters,
            "excluded_predictions": self.excluded_predictions,
            "excluded_ground_truth": self.excluded_ground_truth,
            "failure_count": len(self.failures),
        }


def aggregate_run_metrics(
    frame_metrics: Sequence[ValidationMetrics],
    *,
    scenario_id: str | None = None,
    run_id: str | None = None,
    scenario_conditions: Mapping[str, Any] | None = None,
    parameters: Mapping[str, Any] | None = None,
    iou_threshold: float | None = None,
) -> RunValidationMetrics:
    """Aggregate per-frame validation metrics using micro-averaged total counts.

    Run-level precision and recall are calculated from total true positives,
    false positives, and missed detections across all frames, rather than
    averaging frame-level ratios.
    """
    frames_processed = len(frame_metrics)
    total_tp = sum(m.true_positives for m in frame_metrics)
    total_fp = sum(m.false_positives for m in frame_metrics)
    total_fn = sum(m.missed_detections for m in frame_metrics)
    total_pred = sum(m.prediction_count for m in frame_metrics)
    total_gt = sum(m.ground_truth_count for m in frame_metrics)
    total_excluded_pred = sum(m.excluded_prediction_count for m in frame_metrics)
    total_excluded_gt = sum(m.excluded_ground_truth_count for m in frame_metrics)

    precision = (
        total_tp / (total_tp + total_fp)
        if (total_tp + total_fp)
        else 0.0
    )
    recall = (
        total_tp / (total_tp + total_fn)
        if (total_tp + total_fn)
        else 0.0
    )
    f1 = (
        2.0 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    all_matches = [match for m in frame_metrics for match in m.matches]
    matched_iou = (
        sum(match.iou for match in all_matches) / len(all_matches)
        if all_matches
        else 0.0
    )

    all_failures: list[PerceptionFailureRecord] = []
    for m in frame_metrics:
        all_failures.extend(m.failure_records)

    effective_iou_threshold = (
        iou_threshold
        if iou_threshold is not None
        else (frame_metrics[0].iou_threshold if frame_metrics else 0.5)
    )

    return RunValidationMetrics(
        frames_processed=frames_processed,
        predictions=total_pred,
        ground_truth_objects=total_gt,
        true_positives=total_tp,
        false_positives=total_fp,
        missed_detections=total_fn,
        precision=precision,
        recall=recall,
        f1=f1,
        matched_iou=matched_iou,
        iou_threshold=effective_iou_threshold,
        failures=tuple(all_failures),
        scenario_id=scenario_id,
        run_id=run_id,
        scenario_conditions=dict(scenario_conditions or {}),
        parameters=dict(parameters or {}),
        excluded_predictions=total_excluded_pred,
        excluded_ground_truth=total_excluded_gt,
    )


def export_run_report(
    run_metrics: RunValidationMetrics | Mapping[str, Any],
    destination: str | Path,
    *,
    failures_destination: str | Path | None = None,
    failure_format: Literal["json", "jsonl"] | None = None,
) -> tuple[Path, Path | None]:
    """Persist structured per-run metrics and failure records to disk.

    Parameters
    ----------
    run_metrics:
        A ``RunValidationMetrics`` instance or dictionary containing run metrics.
    destination:
        File path to save the run metrics JSON.
    failures_destination:
        Optional file path to save structured failure records (JSON or JSONL).
    failure_format:
        Optional format override ('json' or 'jsonl').

    Returns
    -------
    tuple[Path, Path | None]
        Paths to the saved metrics file and failures file (if saved).
    """
    dest_path = Path(destination)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(run_metrics, "to_dict"):
        metrics_dict = run_metrics.to_dict()
        failures = getattr(run_metrics, "failures", ())
    else:
        metrics_dict = dict(run_metrics)
        failures = metrics_dict.get("failures", ())

    dest_path.write_text(
        json.dumps(metrics_dict, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    failures_path: Path | None = None
    if failures_destination is not None:
        failures_path = Path(failures_destination)
        failure_objs = [
            f if isinstance(f, PerceptionFailureRecord) else PerceptionFailureRecord.model_validate(f)
            for f in failures
        ]
        export_failure_report(failure_objs, failures_path, format=failure_format)

    return dest_path, failures_path


__all__ = [
    "SUPPORTED_EVALUATION_CLASSES",
    "DetectionMatch",
    "FailureSeverityRules",
    "GroundTruthObject",
    "RunValidationMetrics",
    "ValidationMetrics",
    "aggregate_run_metrics",
    "carla_actor_class",
    "evaluate_detections",
    "export_failure_report",
    "export_run_report",
    "extract_carla_ground_truth",
    "project_carla_actor_bbox",
]
