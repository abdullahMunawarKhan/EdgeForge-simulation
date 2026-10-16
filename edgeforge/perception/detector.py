"""
YOLO object detector for EdgeForge.

Detects all classes supported by the loaded Ultralytics YOLO model.
Known traffic participants are mapped to EdgeForge domain names, while
other detected classes are preserved for downstream perception.

Returns RawDetection primitives containing 2D bounding boxes,
class names, confidence scores, and class IDs.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

if __package__ in (None, ""):
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from edgeforge.config.settings import settings
from edgeforge.data.models import DetectedObject
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


# Map known COCO labels to EdgeForge domain labels.
# Unmapped classes are retained automatically.
COCO_CLASS_MAP: Dict[str, str] = {
    "person": "pedestrian",
    "car": "car",
    "motorcycle": "motorcycle",
    "bicycle": "bicycle",
    "bus": "bus",
    "truck": "truck",
    "traffic light": "traffic_light",
    "stop sign": "stop_sign",
    "fire hydrant": "fire_hydrant",
    "parking meter": "parking_meter",
    "sports ball": "sports_ball",
    "potted plant": "potted_plant",
    "dining table": "dining_table",
    "cell phone": "cell_phone",
    "tv": "tv",
    "wine glass": "wine_glass",
    "hot dog": "hot_dog",
    "teddy bear": "teddy_bear",
    "hair drier": "hair_drier",
}


@dataclass
class RawDetection:
    """Raw 2D detection produced by the object detector."""

    bbox: List[float]
    object_type: str
    confidence: float
    class_id: Optional[int] = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bbox": self.bbox,
            "object_type": self.object_type,
            "confidence": self.confidence,
            "class_id": self.class_id,
        }


def adapt_ground_truth_detections(
    detections: Sequence[DetectedObject],
    source_size: Tuple[int, int],
    target_size: Tuple[int, int],
) -> List[RawDetection]:
    """Adapt mock ground-truth boxes to the resized frame's detector format."""
    source_width, source_height = source_size
    target_width, target_height = target_size
    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("Source and target image dimensions must be positive.")

    scale_x = target_width / source_width
    scale_y = target_height / source_height
    raw_detections: List[RawDetection] = []
    for detection in detections:
        if detection.bbox is None or len(detection.bbox) != 4:
            raise ValueError(
                f"Mock ground-truth detection {detection.object_id!r} "
                "must have a four-coordinate bounding box."
            )
        x1, y1, x2, y2 = detection.bbox
        raw_detections.append(
            RawDetection(
                bbox=[
                    x1 * scale_x,
                    y1 * scale_y,
                    x2 * scale_x,
                    y2 * scale_y,
                ],
                object_type=detection.object_type,
                confidence=detection.confidence,
            )
        )
    return raw_detections


class ObjectDetector:
    """YOLO-based object detector for EdgeForge.

    Parameters
    ----------
    model_name:
        Model path or Ultralytics model name. None disables inference
        unless a model instance is supplied.
    confidence_threshold:
        Minimum confidence for a detection. Defaults to 0.15 to improve
        recall during initial testing.
    device:
        Inference device, such as "cpu", "0", or "cuda:0", depending
        on the installed Ultralytics/PyTorch configuration.
    model:
        Optional preloaded model instance.
    lazy_load:
        If False, load the model during initialization.
    """

    DEFAULT_MODEL: str = settings.YOLO_MODEL_PATH

    def __init__(
        self,
        model_name: Optional[str] = settings.YOLO_MODEL_PATH,
        confidence_threshold: Optional[float] = None,
        device: Optional[str] = None,
        model: Optional[Any] = None,
        lazy_load: bool = True,
    ) -> None:
        self.model_name = model_name

        configured_confidence = (
            confidence_threshold
            if confidence_threshold is not None
            else getattr(settings, "DETECTION_CONFIDENCE_THRESHOLD", 0.15)
        )

        self.confidence_threshold = float(configured_confidence)

        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ValueError(
                "confidence_threshold must be between 0.0 and 1.0"
            )

        self.device = (
            device
            if device is not None
            else settings.YOLO_DEVICE
        )

        self._model = model
        self._model_loaded = model is not None
        self._initialized = True
        self._detection_count = 0
        self._last_detection_count = 0

        if self._model is not None:
            self._model_name_display = model_name or "custom_model"
        elif self.model_name is not None:
            self._model_name_display = self.model_name

            if not lazy_load:
                self._load_model()
        else:
            self._model_name_display = "none (placeholder)"

        logger.info(
            "ObjectDetector initialized "
            f"(model={self._model_name_display}, "
            f"loaded={self._model_loaded}, "
            f"conf_thresh={self.confidence_threshold:.2f}, "
            f"device={self.device})"
        )

    def _load_model(self) -> None:
        """Load the configured Ultralytics YOLO model."""
        if self._model_loaded:
            return

        if not self.model_name:
            return

        try:
            from ultralytics import YOLO

            logger.info(
                f"Loading YOLO model '{self.model_name}' "
                f"on device '{self.device}'..."
            )

            self._model = YOLO(self.model_name)
            self._model_loaded = True

            names = getattr(self._model, "names", None)

            logger.info(
                f"YOLO model loaded successfully; "
                f"supported_classes={len(names) if names else 'unknown'}"
            )

            if isinstance(names, dict):
                logger.debug(f"YOLO class names: {names}")

        except Exception as exc:
            self._model_loaded = False
            self._model = None

            logger.exception(
                f"Failed to load YOLO model '{self.model_name}': {exc}"
            )

            raise RuntimeError(
                f"Failed to load YOLO model '{self.model_name}': {exc}"
            ) from exc

    @staticmethod
    def _scalar(value: Any) -> Any:
        """Convert a tensor or NumPy scalar into a Python scalar."""
        if hasattr(value, "item"):
            return value.item()
        return value

    @staticmethod
    def _get_class_name(
        result: Any,
        model: Any,
        class_id: int,
    ) -> Optional[str]:
        """Resolve a class label from result or model metadata."""
        for owner in (result, model):
            names = getattr(owner, "names", None)

            if isinstance(names, dict) and class_id in names:
                return str(names[class_id])

            if isinstance(names, (list, tuple)):
                if 0 <= class_id < len(names):
                    return str(names[class_id])

        return None

    def detect(self, frame: Any) -> List[RawDetection]:
        """Detect all supported classes in a BGR image frame."""
        if frame is None:
            logger.debug("Received None frame; returning no detections.")
            return []

        if not isinstance(frame, np.ndarray):
            logger.warning(
                f"Expected NumPy frame, received {type(frame).__name__}."
            )
            return []

        if (
            frame.size == 0
            or frame.ndim not in (2, 3)
            or (
                frame.ndim == 3
                and frame.shape[2] not in (1, 3)
            )
        ):
            logger.warning(
                f"Invalid frame shape: {getattr(frame, 'shape', None)}"
            )
            return []

        if frame.dtype not in (
            np.uint8,
            np.float32,
            np.float64,
        ):
            logger.warning(f"Unsupported frame dtype: {frame.dtype}")
            return []

        if self.model_name is None and self._model is None:
            self._last_detection_count = 0

            if self._detection_count == 0:
                logger.info(
                    "Detector is in placeholder mode; inference disabled."
                )

            self._detection_count += 1
            return []

        if not self._model_loaded:
            self._load_model()

        if self._model is None:
            raise RuntimeError(
                f"Model '{self.model_name}' was not loaded properly."
            )

        height, width = frame.shape[:2]

        # No class restriction: allow every class supported by the model.
        try:
            results = self._model.predict(
                source=frame,
                conf=self.confidence_threshold,
                iou=settings.YOLO_NMS_IOU,
                device=self.device,
                classes=None,
                verbose=False,
            )

        except Exception as exc:
            logger.exception(f"YOLO inference failed: {exc}")
            raise RuntimeError(
                f"Inference failed: {exc}"
            ) from exc

        detections: List[RawDetection] = []

        for result in results:
            boxes = getattr(result, "boxes", None)

            if boxes is None:
                continue

            for box in boxes:
                try:
                    cls_value = self._scalar(box.cls[0])
                    conf_value = self._scalar(box.conf[0])

                    class_id = int(cls_value)
                    confidence = float(conf_value)

                    if not np.isfinite(confidence):
                        continue

                    if not 0.0 <= confidence <= 1.0:
                        continue
                    if confidence < self.confidence_threshold:
                        continue

                    raw_name = self._get_class_name(
                        result,
                        self._model,
                        class_id,
                    )

                    if raw_name is None:
                        logger.debug(
                            f"No class label available for ID {class_id}; "
                            "skipping detection."
                        )
                        continue

                    normalized_name = raw_name.lower().strip()

                    if not normalized_name:
                        continue

                    # Map known classes and preserve all other classes.
                    object_type = COCO_CLASS_MAP.get(
                        normalized_name,
                        normalized_name.replace(" ", "_"),
                    )

                    xyxy = box.xyxy[0]

                    if hasattr(xyxy, "tolist"):
                        coordinates = xyxy.tolist()
                    else:
                        coordinates = list(xyxy)

                    if len(coordinates) != 4:
                        continue

                    x1, y1, x2, y2 = (
                        float(coordinate)
                        for coordinate in coordinates
                    )

                    if not np.all(
                        np.isfinite([x1, y1, x2, y2])
                    ):
                        continue

                    # Clamp coordinates to the frame boundaries.
                    x1 = max(0.0, min(x1, float(width)))
                    y1 = max(0.0, min(y1, float(height)))
                    x2 = max(0.0, min(x2, float(width)))
                    y2 = max(0.0, min(y2, float(height)))

                    # Reject empty or inverted bounding boxes.
                    if x2 <= x1 or y2 <= y1:
                        continue

                    detections.append(
                        RawDetection(
                            bbox=[x1, y1, x2, y2],
                            object_type=object_type,
                            confidence=confidence,
                            class_id=class_id,
                        )
                    )

                except (TypeError, ValueError, IndexError, AttributeError) as exc:
                    logger.debug(
                        f"Skipping malformed YOLO detection: {exc}"
                    )
                    continue

        self._detection_count += 1
        self._last_detection_count = len(detections)

        logger.info(
            "YOLO inference: "
            f"model_loaded={self._model_loaded}, "
            f"detections={len(detections)}, "
            f"classes={[d.object_type for d in detections]}"
        )

        return detections

    def detect_objects(self, frame: Any) -> List[DetectedObject]:
        """Convert raw detections into EdgeForge shared data models."""
        return [
            DetectedObject(
                object_type=detection.object_type,
                confidence=detection.confidence,
                bbox=list(detection.bbox),
                distance=None,
                relative_speed=None,
            )
            for detection in self.detect(frame)
        ]

    def get_status(self) -> Dict[str, Any]:
        """Return a JSON-friendly detector status report."""
        return {
            "module": "object_detector",
            "status": (
                "initialized"
                if self._initialized
                else "not_initialized"
            ),
            "model_loaded": self._model_loaded,
            "model_name": self._model_name_display,
            "confidence_threshold": self.confidence_threshold,
            "total_detection_calls": self._detection_count,
            "last_detection_count": self._last_detection_count,
        }