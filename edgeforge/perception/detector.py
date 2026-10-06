"""
Object detector skeleton for EdgeForge.

This is a **starter implementation**.  The detect() method is intentionally
a placeholder – it accepts a frame, validates it, and returns an empty list
of DetectedObjects.  The idea is to keep the *interface* stable so that
YOLO (or any other detector) can be slotted in later without touching
callers in the pipeline or main.py.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np

from edgeforge.data.models import DetectedObject
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


class ObjectDetector:
    """Perception module responsible for detecting objects in camera frames.

    Starter behaviour
    -----------------
    * Validates the input frame shape/type.
    * Returns an empty list of DetectedObjects (no fake detections!).
    * Exposes a get_status() report so callers can see the module is
      initialized but that no real model is loaded yet.

    Extending later
    ---------------
    Look for the clearly-marked "### YOLO / detection-model integration
    point ###" section below.  When you are ready:
      1. Install ultralytics (it is already in requirements.txt).
      2. Load a YOLOv8/YOLOv9 model in ``__init__``.
      3. Run inference in ``detect()`` and yield real DetectedObject entries.
    TODO:
      * LiDAR-based obstacle detection.
      * Multi-sensor fusion (camera + LiDAR + radar).
      * Object tracking (DeepSORT, ByteTrack, …).
      * Semantic segmentation (lane lines, drivable area).
    """

    def __init__(self) -> None:
        self._initialized = True
        self._model_loaded = False
        self._model_name: str = "none (placeholder)"
        self._detection_count: int = 0
        logger.info(
            f"ObjectDetector initialized (model={self._model_name}, "
            f"loaded={self._model_loaded})"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def detect(self, frame: Any) -> List[DetectedObject]:
        """Run object detection on ``frame``.

        Parameters
        ----------
        frame :
            OpenCV / numpy image.  Can be None or invalid – the method
            will simply return an empty list in that case.

        Returns
        -------
        List[DetectedObject]
            Currently returns an empty list (placeholder).
        """
        # ------------------------------------------------------------------
        # 1. Input validation
        # ------------------------------------------------------------------
        if frame is None:
            logger.debug("detect() called with None frame; returning []")
            return []
        if not isinstance(frame, np.ndarray):
            logger.warning(
                f"detect() received non-numpy frame: {type(frame).__name__}; "
                f"returning []"
            )
            return []
        if frame.size == 0 or frame.ndim not in (2, 3):
            logger.warning(
                f"detect() received invalid frame shape={getattr(frame, 'shape', None)}; "
                f"returning []"
            )
            return []

        # ------------------------------------------------------------------
        # ### YOLO / detection-model integration point ###
        #
        # When a real detection model is available, replace everything below
        # with real inference.  Pseudo-code outline:
        #
        #   results = self.model(frame, conf=0.5, verbose=False)
        #   detections: List[DetectedObject] = []
        #   for r in results:
        #       for box in r.boxes:
        #           obj = DetectedObject(
        #               object_type=r.names[int(box.cls)],
        #               confidence=float(box.conf),
        #               bbox=box.xyxy[0].tolist(),
        #               distance=self._estimate_distance(box),
        #               relative_speed=0.0,  # from tracking across frames
        #           )
        #           detections.append(obj)
        #   return detections
        # ------------------------------------------------------------------

        self._detection_count += 1
        if self._detection_count == 1:
            logger.info(
                "ObjectDetector.detect() first run: returning placeholder (empty list). "
                "Integrate YOLO in the marked section to enable real detection."
            )
        return []

    # ------------------------------------------------------------------
    def get_status(self) -> Dict[str, Any]:
        """Return a short human/JSON friendly status report."""
        return {
            "module": "object_detector",
            "status": "initialized" if self._initialized else "not_initialized",
            "model_loaded": self._model_loaded,
            "model_name": self._model_name,
            "total_detection_calls": self._detection_count,
        }
