"""
Camera / frame processing utilities.

This module intentionally has NO dependency on CARLA.  It works on any
OpenCV-compatible numpy image so the rest of the perception pipeline
can be developed and tested without a running simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

import cv2
import numpy as np

from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FrameInfo:
    """Metadata extracted from an image frame."""

    width: int
    height: int
    channels: int
    dtype: str
    empty: bool


class CameraProcessor:
    """Lightweight frame preprocessing and validation helper.

    Responsibilities (starter):
      * Validate that an incoming frame is a well-formed numpy image.
      * Extract frame metadata (width, height, channels).
      * Resize frames to a target size using OpenCV.

    TODO:
      * Color-space conversion (BGR <-> RGB, BGR -> grayscale, ...).
      * Undistortion using calibration matrices.
      * Region-of-interest extraction.
      * Basic pre-processing (normalization, CLAHE, noise reduction).
    """

    def __init__(self, default_width: int = 1280, default_height: int = 720) -> None:
        self.default_width = default_width
        self.default_height = default_height
        logger.info(
            f"CameraProcessor initialized (defaults={default_width}x{default_height})"
        )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @staticmethod
    def is_valid_frame(frame: Any) -> bool:
        """Return True if ``frame`` looks like a valid OpenCV/numpy image."""
        if frame is None:
            return False
        if not isinstance(frame, np.ndarray):
            return False
        if frame.size == 0:
            return False
        if frame.ndim not in (2, 3):
            return False
        # OpenCV images are typically uint8; allow float32 for normalized frames.
        if frame.dtype not in (np.uint8, np.float32, np.float64):
            return False
        return True

    def validate_frame(self, frame: Any) -> None:
        """Raise a descriptive ValueError if the frame is invalid."""
        if frame is None:
            raise ValueError("Frame is None (no image provided).")
        if not isinstance(frame, np.ndarray):
            raise ValueError(
                f"Expected numpy.ndarray frame, got {type(frame).__name__}."
            )
        if frame.size == 0:
            raise ValueError("Frame is empty (0 elements).")
        if frame.ndim not in (2, 3):
            raise ValueError(
                f"Frame must be 2D (grayscale) or 3D (color), got {frame.ndim}D."
            )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------
    def get_frame_info(self, frame: Optional[np.ndarray]) -> FrameInfo:
        """Return a FrameInfo descriptor for the given frame."""
        if not self.is_valid_frame(frame):
            return FrameInfo(
                width=0, height=0, channels=0, dtype="unknown", empty=True
            )
        assert frame is not None  # for static analysis
        height, width = frame.shape[:2]
        channels = frame.shape[2] if frame.ndim == 3 else 1
        return FrameInfo(
            width=int(width),
            height=int(height),
            channels=int(channels),
            dtype=str(frame.dtype),
            empty=False,
        )

    # ------------------------------------------------------------------
    # Transformations
    # ------------------------------------------------------------------
    def resize_frame(
        self,
        frame: np.ndarray,
        width: Optional[int] = None,
        height: Optional[int] = None,
        interpolation: int = cv2.INTER_LINEAR,
    ) -> np.ndarray:
        """Resize a frame to the given (or default) dimensions.

        Parameters
        ----------
        frame :
            Valid input frame.
        width, height :
            Target size.  If omitted, the processor defaults are used.
        interpolation :
            OpenCV interpolation flag (default: INTER_LINEAR).
        """
        self.validate_frame(frame)
        w = width if width is not None else self.default_width
        h = height if height is not None else self.default_height
        resized = cv2.resize(frame, (w, h), interpolation=interpolation)
        logger.debug(f"Frame resized {frame.shape[:2]} -> {resized.shape[:2]}")
        return resized
