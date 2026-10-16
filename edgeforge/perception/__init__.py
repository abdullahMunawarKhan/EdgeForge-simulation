from edgeforge.data.models import PerceptionFailureRecord
from edgeforge.perception.camera import CameraProcessor, FrameInfo
from edgeforge.perception.detector import COCO_CLASS_MAP, ObjectDetector, RawDetection
from edgeforge.perception.distance_estimator import DistanceEstimate, DistanceEstimator
from edgeforge.perception.pipeline import PerceptionPipeline
from edgeforge.perception.tracker import ObjectTracker, TrackedDetection, compute_iou
from edgeforge.perception.validation import (
    SUPPORTED_EVALUATION_CLASSES,
    DetectionMatch,
    FailureSeverityRules,
    GroundTruthObject,
    RunValidationMetrics,
    ValidationMetrics,
    aggregate_run_metrics,
    carla_actor_class,
    evaluate_detections,
    export_failure_report,
    export_run_report,
    extract_carla_ground_truth,
    project_carla_actor_bbox,
)

__all__ = [
    "CameraProcessor",
    "FrameInfo",
    "ObjectDetector",
    "RawDetection",
    "COCO_CLASS_MAP",
    "ObjectTracker",
    "TrackedDetection",
    "compute_iou",
    "DistanceEstimator",
    "DistanceEstimate",
    "PerceptionPipeline",
    "PerceptionFailureRecord",
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
