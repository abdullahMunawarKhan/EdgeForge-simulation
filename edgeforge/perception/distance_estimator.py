"""
Monocular distance and relative speed estimation for EdgeForge perception.

Estimates distance in meters using pinhole camera geometry and known real-world
object heights, and derives relative speed (m/s) from consecutive observations.

Sign convention:
  * Negative relative_speed = object is approaching the ego vehicle (closing speed).
  * Positive relative_speed = object is moving away from the ego vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from edgeforge.config.settings import settings
from edgeforge.perception.camera import CameraProcessor
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DistanceEstimate:
    """Estimated distance and relative velocity for a tracked object."""

    object_id: str
    distance: float  # Smoothed distance in meters from ego camera
    relative_speed: float  # m/s: negative = approaching, positive = moving away
    raw_distance: float  # Unfiltered monocular distance estimate in meters
    timestamp: Optional[float] = None  # Measurement timestamp in epoch seconds

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "distance": self.distance,
            "relative_speed": self.relative_speed,
            "raw_distance": self.raw_distance,
            "timestamp": self.timestamp,
        }


@dataclass
class _TrackHistory:
    """Internal per-track distance and velocity state."""

    smoothed_distance: float
    last_timestamp: Optional[float]
    last_relative_speed: float


class DistanceEstimator:
    """Monocular distance and relative velocity estimator.

    Uses pinhole camera geometry:
        distance = (focal_length * real_object_height) / pixel_object_height

    Computes relative velocity:
        relative_speed = (current_distance - previous_distance) / delta_time

    Smooths distance noise with Exponential Moving Average (EMA) and prevents
    velocity spikes due to small delta_time or measurement jitter.
    """

    # Reference real-world physical heights in meters
    REFERENCE_HEIGHTS: Dict[str, float] = {
        "pedestrian": 1.7,
        "car": 1.5,
        "motorcycle": 1.4,
        "bicycle": 1.4,
        "bus": 3.2,
        "truck": 3.2,
    }
    DEFAULT_HEIGHT: float = 1.5

    def __init__(
        self,
        focal_length: Optional[float] = None,
        image_width: Optional[int] = None,
        fov_degrees: Optional[float] = None,
        alpha: float = 0.6,
        max_speed: float = 60.0,
        max_distance: float = 250.0,
        min_distance: float = 0.5,
    ) -> None:
        """Initialize the DistanceEstimator.

        Parameters
        ----------
        focal_length :
            Pinhole focal length in pixels. If omitted, computed from width and FOV.
        image_width :
            Image width in pixels (defaults to settings.CAMERA_WIDTH).
        fov_degrees :
            Horizontal field of view (defaults to settings.CAMERA_FOV).
        alpha :
            EMA smoothing weight in [0, 1]. Higher alpha gives more weight to the
            newest observation; lower alpha provides heavier smoothing.
        max_speed :
            Clamping limit for relative velocity magnitude in m/s (default 60 m/s).
        max_distance :
            Upper distance bound for clipping outliers (default 250 m).
        min_distance :
            Lower distance bound for clipping (default 0.5 m).
        """
        w = image_width if image_width is not None else settings.CAMERA_WIDTH
        fov = fov_degrees if fov_degrees is not None else float(settings.CAMERA_FOV)

        if focal_length is not None:
            self.focal_length = float(focal_length)
        else:
            self.focal_length = CameraProcessor.compute_focal_length(
                image_width=w, fov_degrees=fov
            )

        self.alpha = float(max(0.0, min(1.0, alpha)))
        self.max_speed = float(max_speed)
        self.max_distance = float(max_distance)
        self.min_distance = float(min_distance)

        self._history: Dict[str, _TrackHistory] = {}

        logger.info(
            f"DistanceEstimator initialized (focal_length={self.focal_length:.2f}px, "
            f"alpha={self.alpha:.2f}, max_speed={self.max_speed}m/s)"
        )

    def get_reference_height(self, object_type: str) -> float:
        """Lookup reference physical height in meters for an object class."""
        normalized = str(object_type).lower().strip()
        return self.REFERENCE_HEIGHTS.get(normalized, self.DEFAULT_HEIGHT)

    def calculate_raw_distance(
        self, bbox: List[float], object_type: str
    ) -> float:
        """Calculate single-frame monocular distance in meters without temporal smoothing.

        Formula: distance = (focal_length * real_height) / pixel_height
        """
        if len(bbox) < 4:
            return self.max_distance

        y1, y2 = bbox[1], bbox[3]
        pixel_height = float(y2 - y1)

        # Handle zero, negative, or degenerate height safely
        if pixel_height <= 0.0 or math.isnan(pixel_height) or math.isinf(pixel_height):
            logger.debug(
                f"Degenerate bbox height {pixel_height:.2f}; returning max_distance."
            )
            return self.max_distance

        real_height = self.get_reference_height(object_type)
        raw_dist = (self.focal_length * real_height) / pixel_height

        # Clamp distance to physically plausible bounds
        return float(max(self.min_distance, min(self.max_distance, raw_dist)))

    @staticmethod
    def _parse_timestamp(timestamp: Optional[Union[float, int, datetime]]) -> Optional[float]:
        """Convert timestamp input to numeric epoch seconds."""
        if timestamp is None:
            return None
        if isinstance(timestamp, datetime):
            return timestamp.timestamp()
        if isinstance(timestamp, (int, float)):
            return float(timestamp)
        return None

    def estimate(
        self,
        tracked_detection: Any,
        timestamp: Optional[Union[float, int, datetime]] = None,
    ) -> DistanceEstimate:
        """Estimate distance and relative velocity for a single tracked detection.

        Parameters
        ----------
        tracked_detection :
            TrackedDetection instance or dict containing object_id, bbox, object_type.
        timestamp :
            Optional timestamp (epoch seconds or datetime).

        Returns
        -------
        DistanceEstimate
            Contains object_id, smoothed distance, relative_speed, raw_distance.
        """
        # 1. Extract detection fields
        if isinstance(tracked_detection, dict):
            object_id = str(tracked_detection["object_id"])
            bbox = [float(x) for x in tracked_detection["bbox"]]
            object_type = str(tracked_detection["object_type"])
        else:
            object_id = str(getattr(tracked_detection, "object_id"))
            bbox = [float(x) for x in getattr(tracked_detection, "bbox")]
            object_type = str(getattr(tracked_detection, "object_type"))

        # 2. Compute raw distance
        raw_dist = self.calculate_raw_distance(bbox, object_type)
        ts_sec = self._parse_timestamp(timestamp)

        # 3. Handle tracking state
        if object_id not in self._history:
            # First observation: no prior distance, relative velocity defaults to 0.0
            smoothed_dist = raw_dist
            relative_speed = 0.0
            self._history[object_id] = _TrackHistory(
                smoothed_distance=smoothed_dist,
                last_timestamp=ts_sec,
                last_relative_speed=0.0,
            )
        else:
            prev = self._history[object_id]

            # Exponential Moving Average (EMA) distance smoothing
            smoothed_dist = (
                self.alpha * raw_dist + (1.0 - self.alpha) * prev.smoothed_distance
            )

            # Compute relative velocity: (current - previous) / delta_time
            if ts_sec is None or prev.last_timestamp is None:
                relative_speed = 0.0
            else:
                dt = ts_sec - prev.last_timestamp
                if dt <= 0.0 or math.isnan(dt):
                    # Zero or negative delta_time: maintain previous speed without division
                    relative_speed = prev.last_relative_speed
                else:
                    speed = (smoothed_dist - prev.smoothed_distance) / dt
                    # Clamp to realistic physical range
                    relative_speed = float(
                        max(-self.max_speed, min(self.max_speed, speed))
                    )

            self._history[object_id] = _TrackHistory(
                smoothed_distance=smoothed_dist,
                last_timestamp=ts_sec,
                last_relative_speed=relative_speed,
            )

        return DistanceEstimate(
            object_id=object_id,
            distance=float(smoothed_dist),
            relative_speed=float(relative_speed),
            raw_distance=float(raw_dist),
            timestamp=ts_sec,
        )

    def estimate_tracks(
        self,
        tracked_detections: List[Any],
        timestamp: Optional[Union[float, int, datetime]] = None,
    ) -> List[DistanceEstimate]:
        """Estimate distance and relative velocity for a batch of tracked detections."""
        return [self.estimate(det, timestamp=timestamp) for det in tracked_detections]

    def prune_stale(self, active_track_ids: Set[str]) -> None:
        """Remove history records for objects that are no longer active in tracker."""
        stale_ids = [oid for oid in self._history if oid not in active_track_ids]
        for oid in stale_ids:
            del self._history[oid]

    def reset(self) -> None:
        """Clear all observation histories."""
        self._history.clear()
        logger.debug("DistanceEstimator history reset.")
