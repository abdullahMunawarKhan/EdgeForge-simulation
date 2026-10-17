"""
End-to-end PerceptionPipeline for EdgeForge.

Wires together:
  BGR Camera Frame
  ↓
  CameraProcessor
  ↓
  ObjectDetector (YOLOv8)
  ↓
  RawDetection[]
  ↓
  ObjectTracker (IoU)
  ↓
  TrackedDetection[]
  ↓
  DistanceEstimator (Monocular Pinhole + EMA + Relative Velocity)
  ↓
  DetectedObject[]
  ↓
  (Consumed by RiskEngine)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import numpy as np

from edgeforge.data.models import DetectedObject
from edgeforge.perception.camera import CameraProcessor
from edgeforge.perception.detector import ObjectDetector, RawDetection
from edgeforge.perception.distance_estimator import DistanceEstimate, DistanceEstimator
from edgeforge.perception.tracker import ObjectTracker, TrackedDetection
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


class PerceptionPipeline:
    """Orchestrates EdgeForge perception modules into a unified stream.

    Processes incoming BGR camera frames through validation, 2D YOLOv8 detection,
    bounding-box IoU tracking, and monocular distance/relative-speed estimation,
    returning typed DetectedObject instances for the downstream RiskEngine.
    """

    def __init__(
        self,
        camera_processor: Optional[CameraProcessor] = None,
        detector: Optional[ObjectDetector] = None,
        tracker: Optional[ObjectTracker] = None,
        distance_estimator: Optional[DistanceEstimator] = None,
    ) -> None:
        """Initialize the perception pipeline with modular components.

        Any component omitted will be instantiated with project defaults.
        """
        self.camera_processor = (
            camera_processor if camera_processor is not None else CameraProcessor()
        )
        self.detector = (
            detector if detector is not None else ObjectDetector()
        )
        self.tracker = (
            tracker if tracker is not None else ObjectTracker()
        )
        self.distance_estimator = (
            distance_estimator
            if distance_estimator is not None
            else DistanceEstimator()
        )

        self._frame_count: int = 0
        logger.info("PerceptionPipeline initialized successfully.")

    def process_frame(
        self,
        frame: Any,
        timestamp: Optional[Union[float, int, datetime]] = None,
        raw_detections: Optional[List[RawDetection]] = None,
    ) -> List[DetectedObject]:
        """Process a single camera frame through the full perception stack.

        Parameters
        ----------
        frame :
            BGR NumPy array representing raw camera capture from CARLA (or offline image).
        timestamp :
            Optional frame capture timestamp (epoch seconds or datetime).
        raw_detections :
            Optional detector output. When provided, skips detector inference and
            sends these detections through tracking and distance estimation.

        Returns
        -------
        List[DetectedObject]
            Typed detection objects with assigned IDs, bounding boxes,
            estimated distances, and relative speeds.
        """
        # Step 1: Normalize timestamp
        if timestamp is None:
            dt_ts = datetime.utcnow()
            numeric_ts = dt_ts.timestamp()
        elif isinstance(timestamp, datetime):
            dt_ts = timestamp
            numeric_ts = timestamp.timestamp()
        elif isinstance(timestamp, (int, float)):
            numeric_ts = float(timestamp)
            dt_ts = datetime.utcfromtimestamp(numeric_ts)
        else:
            dt_ts = datetime.utcnow()
            numeric_ts = dt_ts.timestamp()

        # Step 2: Validate frame input
        if not self.camera_processor.is_valid_frame(frame):
            logger.debug(
                "process_frame() received an invalid or empty frame; returning []"
            )
            # Age active tracks when a frame is dropped/missing
            self.tracker.update([])
            return []

        self._frame_count += 1

        # Step 3: 2D Object Detection (YOLOv8)
        if raw_detections is None:
            raw_detections = self.detector.detect(frame)

        # Step 4: Multi-Object Tracking (IoU)
        tracked_detections: List[TrackedDetection] = self.tracker.update(
            raw_detections
        )

        # Prune dead track histories in the distance estimator
        active_ids = {t.object_id for t in self.tracker.active_tracks}
        self.distance_estimator.prune_stale(active_ids)

        if not tracked_detections:
            return []

        # Step 5: Distance & Relative Speed Estimation -> DetectedObject
        detected_objects: List[DetectedObject] = []
        for tracked in tracked_detections:
            est: DistanceEstimate = self.distance_estimator.estimate(
                tracked, timestamp=numeric_ts
            )

            obj = DetectedObject(
                object_id=tracked.object_id,
                object_type=tracked.object_type,
                confidence=tracked.confidence,
                distance=est.distance,
                relative_speed=est.relative_speed,
                bbox=list(tracked.bbox),
                timestamp=dt_ts,
            )
            detected_objects.append(obj)

        return detected_objects

    def reset(self) -> None:
        """Reset temporal state across tracker and distance estimator."""
        self.tracker.reset()
        self.distance_estimator.reset()
        self._frame_count = 0
        logger.debug("PerceptionPipeline temporal state reset.")

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of all connected perception modules."""
        return {
            "module": "perception_pipeline",
            "frames_processed": self._frame_count,
            "detector": self.detector.get_status(),
            "tracker": {
                "active_tracks": self.tracker.track_count,
                "total_tracks_created": self.tracker.total_tracks_created,
                "iou_threshold": self.tracker.iou_threshold,
                "max_age": self.tracker.max_age,
            },
            "distance_estimator": {
                "focal_length": self.distance_estimator.focal_length,
                "alpha": self.distance_estimator.alpha,
                "max_speed": self.distance_estimator.max_speed,
                "tracked_histories": len(self.distance_estimator._history),
            },
        }
