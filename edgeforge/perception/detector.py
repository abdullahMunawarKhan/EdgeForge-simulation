"""
YOLOv8 object detector for EdgeForge.

This module provides 2D object detection on camera frames using Ultralytics YOLOv8.
It filters detections for autonomous driving relevant traffic participants (pedestrian,
car, truck, bus, motorcycle, bicycle) and yields clean detection primitives (RawDetection)
ready for downstream tracking and distance estimation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

from edgeforge.config.settings import settings
from edgeforge.data.models import DetectedObject
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)

# COCO class name to EdgeForge domain class name mapping
COCO_CLASS_MAP: Dict[str, str] = {
    "person": "pedestrian",
    "car": "car",
    "motorcycle": "motorcycle",
    "bicycle": "bicycle",
    "bus": "bus",
    "truck": "truck",
}


@dataclass
class RawDetection:
    """Raw perception primitive from the 2D detector.

    Contains 2D image coordinates and classification before downstream
    temporal tracking, monocular depth estimation, or risk scoring.
    """

    bbox: List[float]  # [x1, y1, x2, y2] in pixel coords
    object_type: str  # mapped class name (e.g. "pedestrian", "car")
    confidence: float  # [0.0, 1.0]
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


class ObjectDetector:
    """YOLOv8-based 2D object detector for EdgeForge perception.

    Accepts BGR frames, runs YOLO inference, filters for relevant traffic
    participants, and returns RawDetection primitives.

    Model path, confidence threshold, NMS IoU, and device default to centralized
    settings. Pass ``model_name=None`` explicitly to disable inference.
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
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else settings.DETECTION_CONFIDENCE_THRESHOLD
        )
        self.device = device if device is not None else settings.YOLO_DEVICE
        self._model = model
        self._model_loaded = model is not None
        self._initialized = True
        self._detection_count = 0

        if self._model is not None:
            self._model_name_display = model_name or "custom_model"
        elif self.model_name is not None:
            self._model_name_display = self.model_name
            if not lazy_load:
                self._load_model()
        else:
            self._model_name_display = "none (placeholder)"

        logger.info(
            f"ObjectDetector initialized (model={self._model_name_display}, "
            f"loaded={self._model_loaded}, conf_thresh={self.confidence_threshold:.2f}, "
            f"device={self.device})"
        )

    def _load_model(self) -> None:
        """Load the YOLOv8 model safely."""
        if self._model_loaded:
            return
        if not self.model_name:
            return

        try:
            from ultralytics import YOLO

            logger.info(
                f"Loading YOLO model '{self.model_name}' on device '{self.device}'..."
            )
            self._model = YOLO(self.model_name)
            self._model_loaded = True
            logger.info(f"YOLO model '{self.model_name}' loaded successfully.")
        except Exception as exc:
            self._model_loaded = False
            self._model = None
            logger.error(f"Failed to load YOLO model '{self.model_name}': {exc}")
            raise RuntimeError(
                f"Failed to load YOLO model '{self.model_name}': {exc}"
            ) from exc

    def detect(self, frame: Any) -> List[RawDetection]:
        """Run object detection on ``frame``.

        Parameters
        ----------
        frame :
            OpenCV / NumPy image in BGR format. If None or invalid, returns [].

        Returns
        -------
        List[RawDetection]
            List of detected objects with bbox, object_type, and confidence.
        """
        # 1. Input validation
        if frame is None:
            logger.debug("detect() called with None frame; returning []")
            return []
        if not isinstance(frame, np.ndarray):
            logger.warning(
                f"detect() received non-numpy frame: {type(frame).__name__}; returning []"
            )
            return []
        if (
            frame.size == 0
            or frame.ndim not in (2, 3)
            or (frame.ndim == 3 and frame.shape[2] not in (1, 3))
        ):
            logger.warning(
                f"detect() received invalid frame shape={getattr(frame, 'shape', None)}; returning []"
            )
            return []
        if frame.dtype not in (np.uint8, np.float32, np.float64):
            logger.warning(
                f"detect() received invalid frame dtype={frame.dtype}; returning []"
            )
            return []

        # 2. Check placeholder / unconfigured mode
        if self.model_name is None and self._model is None:
            self._detection_count += 1
            if self._detection_count == 1:
                logger.info(
                    "ObjectDetector.detect() running in placeholder mode (model_name=None); returning []."
                )
            return []

        # 3. Ensure model is loaded
        if not self._model_loaded:
            self._load_model()

        if self._model is None:
            raise RuntimeError(
                f"Model '{self.model_name}' was not loaded properly."
            )

        # 4. Inference
        try:
            results = self._model(
                frame,
                conf=self.confidence_threshold,
                iou=settings.YOLO_NMS_IOU,
                device=self.device,
                verbose=False,
            )
        except Exception as exc:
            logger.error(f"Inference error in ObjectDetector: {exc}")
            raise RuntimeError(f"Inference failed: {exc}") from exc

        # 5. Extract and filter detections
        detections: List[RawDetection] = []
        for r in results:
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue

            for box in boxes:
                # Extract class id
                cls_attr = box.cls
                if hasattr(cls_attr, "__getitem__") and hasattr(cls_attr, "__len__") and len(cls_attr) > 0:
                    cls_val = cls_attr[0]
                else:
                    cls_val = cls_attr
                cls_id = int(cls_val.item() if hasattr(cls_val, "item") else cls_val)

                # Extract confidence
                conf_attr = box.conf
                if hasattr(conf_attr, "__getitem__") and hasattr(conf_attr, "__len__") and len(conf_attr) > 0:
                    conf_val = conf_attr[0]
                else:
                    conf_val = conf_attr
                conf = float(conf_val.item() if hasattr(conf_val, "item") else conf_val)

                # Resolve class name from results or model dictionary
                raw_name: Optional[str] = None
                if hasattr(r, "names") and isinstance(r.names, dict) and cls_id in r.names:
                    raw_name = r.names[cls_id]
                elif hasattr(self._model, "names") and isinstance(self._model.names, dict) and cls_id in self._model.names:
                    raw_name = self._model.names[cls_id]

                if raw_name is None:
                    continue

                normalized_name = str(raw_name).lower().strip()

                # Filter: ignore unrelated COCO classes
                if normalized_name not in COCO_CLASS_MAP:
                    continue

                object_type = COCO_CLASS_MAP[normalized_name]

                # Extract bounding box [x1, y1, x2, y2]
                xyxy_attr = box.xyxy
                if hasattr(xyxy_attr, "__getitem__") and hasattr(xyxy_attr, "__len__") and len(xyxy_attr) > 0:
                    xyxy_val = xyxy_attr[0]
                else:
                    xyxy_val = xyxy_attr

                if hasattr(xyxy_val, "tolist"):
                    xyxy_list = xyxy_val.tolist()
                elif hasattr(xyxy_val, "__iter__"):
                    xyxy_list = list(xyxy_val)
                else:
                    xyxy_list = [0.0, 0.0, 0.0, 0.0]

                bbox = [float(c) for c in xyxy_list]

                detections.append(
                    RawDetection(
                        bbox=bbox,
                        object_type=object_type,
                        confidence=conf,
                        class_id=cls_id,
                    )
                )

        self._detection_count += 1
        return detections

    def detect_objects(self, frame: Any) -> List[DetectedObject]:
        """Return detections as shared data models without inferred motion data."""
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
        """Return a short human/JSON friendly status report."""
        return {
            "module": "object_detector",
            "status": "initialized" if self._initialized else "not_initialized",
            "model_loaded": self._model_loaded,
            "model_name": self._model_name_display,
            "total_detection_calls": self._detection_count,
        }
