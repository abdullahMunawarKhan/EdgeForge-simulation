"""
Object tracking stage for EdgeForge perception.

Implements a lightweight 2D bounding-box IoU tracker that associates detections
across frames, assigns consistent object IDs (e.g. track_001), handles occlusions /
missing detections through track aging, and removes stale tracks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from edgeforge.config.settings import settings
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


def compute_iou(box_a: List[float], box_b: List[float]) -> float:
    """Compute Intersection over Union (IoU) between two bounding boxes.

    Each box is expected to be [x1, y1, x2, y2].
    """
    if len(box_a) < 4 or len(box_b) < 4:
        return 0.0

    xa = max(box_a[0], box_b[0])
    ya = max(box_a[1], box_b[1])
    xb = min(box_a[2], box_b[2])
    yb = min(box_a[3], box_b[3])

    inter_width = max(0.0, xb - xa)
    inter_height = max(0.0, yb - ya)
    inter_area = inter_width * inter_height

    area_a = max(0.0, box_a[2] - box_a[0]) * max(0.0, box_a[3] - box_a[1])
    area_b = max(0.0, box_b[2] - box_b[0]) * max(0.0, box_b[3] - box_b[1])

    union_area = area_a + area_b - inter_area
    if union_area <= 0.0:
        return 0.0

    return float(inter_area / union_area)


@dataclass
class TrackedDetection:
    """Tracked object detection primitive with a persistent ID.

    Readily consumed by downstream monocular distance estimation and
    relative speed calculation.
    """

    object_id: str
    bbox: List[float]  # [x1, y1, x2, y2]
    object_type: str
    confidence: float
    class_id: Optional[int] = None
    time_since_update: int = 0
    hits: int = 1
    age: int = 1

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "object_id": self.object_id,
            "bbox": self.bbox,
            "object_type": self.object_type,
            "confidence": self.confidence,
            "class_id": self.class_id,
            "time_since_update": self.time_since_update,
            "hits": self.hits,
            "age": self.age,
        }


@dataclass
class Track:
    """Internal state representation for an individual active track."""

    object_id: str
    bbox: List[float]
    object_type: str
    confidence: float
    class_id: Optional[int] = None
    time_since_update: int = 0
    hits: int = 1
    age: int = 1

    def update(
        self,
        bbox: List[float],
        confidence: float,
        class_id: Optional[int] = None,
    ) -> None:
        """Update track with a newly matched detection."""
        self.bbox = bbox
        self.confidence = confidence
        if class_id is not None:
            self.class_id = class_id
        self.hits += 1
        self.time_since_update = 0
        self.age += 1

    def mark_missed(self) -> None:
        """Increment age and missed counter when not detected in current frame."""
        self.time_since_update += 1
        self.age += 1

    def to_tracked_detection(self) -> TrackedDetection:
        """Convert internal Track state to external TrackedDetection primitive."""
        return TrackedDetection(
            object_id=self.object_id,
            bbox=list(self.bbox),
            object_type=self.object_type,
            confidence=self.confidence,
            class_id=self.class_id,
            time_since_update=self.time_since_update,
            hits=self.hits,
            age=self.age,
        )


class ObjectTracker:
    """Lightweight 2D multi-object tracker using bounding-box IoU association.

    Features:
      * Persistent object ID assignment (e.g. track_001, track_002, ...)
      * Greedy IoU matching with strict class-matching enforcement
      * Track aging for handling temporary occlusion/dropouts
      * Deterministic prune after configurable max_age missing frames
    """

    def __init__(
        self,
        iou_threshold: Optional[float] = None,
        max_age: Optional[int] = None,
    ) -> None:
        self.iou_threshold = (
            iou_threshold
            if iou_threshold is not None
            else getattr(settings, "TRACKER_IOU_THRESHOLD", 0.3)
        )
        self.max_age = (
            max_age
            if max_age is not None
            else getattr(settings, "TRACKER_MAX_AGE", 5)
        )
        self._tracks: List[Track] = []
        self._next_id: int = 1

        logger.info(
            f"ObjectTracker initialized (iou_thresh={self.iou_threshold:.2f}, "
            f"max_age={self.max_age})"
        )

    @staticmethod
    def _extract_fields(det: Any) -> Tuple[List[float], str, float, Optional[int]]:
        """Extract bbox, object_type, confidence, class_id from various detection formats."""
        if isinstance(det, dict):
            bbox = [float(x) for x in det["bbox"]]
            object_type = str(det["object_type"])
            confidence = float(det["confidence"])
            class_id = det.get("class_id")
        else:
            bbox = [float(x) for x in getattr(det, "bbox")]
            object_type = str(getattr(det, "object_type"))
            confidence = float(getattr(det, "confidence"))
            class_id = getattr(det, "class_id", None)
        return bbox, object_type, confidence, class_id

    def update(
        self,
        detections: Optional[List[Any]] = None,
        return_all_active: bool = False,
    ) -> List[TrackedDetection]:
        """Update tracker state with detections from the current frame.

        Parameters
        ----------
        detections :
            List of RawDetection (or dicts with bbox, object_type, confidence).
        return_all_active :
            If True, returns all alive tracks including unobserved ones in this frame.
            By default False (returns only observed/updated detections in this frame).

        Returns
        -------
        List[TrackedDetection]
            Tracked detections with assigned stable object_ids.
        """
        if detections is None:
            detections = []

        matched_track_indices = set()
        matched_detection_indices = set()

        # 1. Match active tracks with incoming detections using IoU
        if self._tracks and detections:
            candidates: List[Tuple[int, int, float]] = []
            for t_idx, track in enumerate(self._tracks):
                for d_idx, det in enumerate(detections):
                    bbox, obj_type, conf, cls_id = self._extract_fields(det)
                    # Only match same class
                    if track.object_type != obj_type:
                        continue
                    iou = compute_iou(track.bbox, bbox)
                    if iou >= self.iou_threshold:
                        candidates.append((t_idx, d_idx, iou))

            # Sort greedy matches descending by IoU
            candidates.sort(key=lambda item: item[2], reverse=True)

            for t_idx, d_idx, iou in candidates:
                if t_idx in matched_track_indices or d_idx in matched_detection_indices:
                    continue
                matched_track_indices.add(t_idx)
                matched_detection_indices.add(d_idx)

                bbox, obj_type, conf, cls_id = self._extract_fields(detections[d_idx])
                self._tracks[t_idx].update(
                    bbox=bbox, confidence=conf, class_id=cls_id
                )

        # 2. Age unmatched active tracks
        for t_idx, track in enumerate(self._tracks):
            if t_idx not in matched_track_indices:
                track.mark_missed()

        # 3. Create new tracks for unmatched detections
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_detection_indices:
                bbox, obj_type, conf, cls_id = self._extract_fields(det)
                new_track = Track(
                    object_id=f"track_{self._next_id:03d}",
                    bbox=bbox,
                    object_type=obj_type,
                    confidence=conf,
                    class_id=cls_id,
                    time_since_update=0,
                    hits=1,
                    age=1,
                )
                self._next_id += 1
                self._tracks.append(new_track)

        # 4. Prune stale tracks that exceeded max_age
        active_before = len(self._tracks)
        self._tracks = [
            t for t in self._tracks if t.time_since_update <= self.max_age
        ]
        pruned = active_before - len(self._tracks)
        if pruned > 0:
            logger.debug(f"ObjectTracker pruned {pruned} stale track(s)")

        # 5. Return tracked detections
        if return_all_active:
            return [t.to_tracked_detection() for t in self._tracks]
        return [
            t.to_tracked_detection()
            for t in self._tracks
            if t.time_since_update == 0
        ]

    @property
    def active_tracks(self) -> List[TrackedDetection]:
        """Return all alive tracks currently held in memory."""
        return [t.to_tracked_detection() for t in self._tracks]

    @property
    def track_count(self) -> int:
        """Total number of currently alive tracks."""
        return len(self._tracks)

    @property
    def total_tracks_created(self) -> int:
        """Total count of unique tracks initialized since startup/reset."""
        return self._next_id - 1

    def get_track(self, object_id: str) -> Optional[TrackedDetection]:
        """Look up an active track by its object_id."""
        for t in self._tracks:
            if t.object_id == object_id:
                return t.to_tracked_detection()
        return None

    def reset(self) -> None:
        """Clear all tracks and reset the ID counter."""
        self._tracks.clear()
        self._next_id = 1
        logger.debug("ObjectTracker reset: tracks cleared, next_id=1")
