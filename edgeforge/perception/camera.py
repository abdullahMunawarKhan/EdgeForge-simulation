"""
Camera / frame processing utilities.

This module intentionally has NO dependency on CARLA.  It works on any
OpenCV-compatible numpy image so the rest of the perception pipeline
can be developed and tested without a running simulator.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
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
    """Lightweight frame preprocessing, validation, and camera calibration helper.

    Responsibilities:
      * Validate that an incoming frame is a well-formed numpy image.
      * Extract frame metadata (width, height, channels, dtype).
      * Resize frames to a target size using OpenCV.
      * Color-space conversions (BGR <-> RGB, BGR -> grayscale).
      * CLAHE contrast enhancement for challenging lighting conditions.
      * Deterministic frame preprocessing pipeline.
      * Pinhole camera intrinsic and focal-length calculations.
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
        # OpenCV images are typically uint8; allow float32/float64 for normalized frames.
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
        if frame.dtype not in (np.uint8, np.float32, np.float64):
            raise ValueError(
                f"Unsupported frame dtype: {frame.dtype}. Expected uint8, float32, or float64."
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
    # Transformations & Color Conversions
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
            Target size. If omitted, the processor defaults are used.
        interpolation :
            OpenCV interpolation flag (default: INTER_LINEAR).
        """
        self.validate_frame(frame)
        w = width if width is not None else self.default_width
        h = height if height is not None else self.default_height
        resized = cv2.resize(frame, (w, h), interpolation=interpolation)
        logger.debug(f"Frame resized {frame.shape[:2]} -> {resized.shape[:2]}")
        return resized

    def to_rgb(self, frame: np.ndarray) -> np.ndarray:
        """Convert a BGR (or grayscale / BGRA) frame to RGB."""
        self.validate_frame(frame)
        if frame.ndim == 2:
            return cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
        if frame.shape[2] == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if frame.shape[2] == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2RGB)
        raise ValueError(f"Cannot convert {frame.shape[2]}-channel frame to RGB.")

    def to_bgr(self, frame: np.ndarray) -> np.ndarray:
        """Convert an RGB (or grayscale / RGBA) frame to BGR."""
        self.validate_frame(frame)
        if frame.ndim == 2:
            return cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        if frame.shape[2] == 3:
            return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if frame.shape[2] == 4:
            return cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
        raise ValueError(f"Cannot convert {frame.shape[2]}-channel frame to BGR.")

    def to_grayscale(self, frame: np.ndarray) -> np.ndarray:
        """Convert a BGR or BGRA frame to single-channel grayscale."""
        self.validate_frame(frame)
        if frame.ndim == 2:
            return frame.copy()
        if frame.shape[2] == 1:
            return frame[:, :, 0].copy()
        if frame.shape[2] == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if frame.shape[2] == 4:
            return cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        raise ValueError(f"Cannot convert {frame.shape[2]}-channel frame to grayscale.")

    def apply_clahe(
        self,
        frame: np.ndarray,
        clip_limit: float = 2.0,
        tile_grid_size: Tuple[int, int] = (8, 8),
    ) -> np.ndarray:
        """Apply Contrast Limited Adaptive Histogram Equalization (CLAHE).

        Useful for enhancing object visibility under bad weather or uneven shadows.
        """
        self.validate_frame(frame)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size)
        if frame.ndim == 2:
            return clahe.apply(frame)
        if frame.shape[2] == 1:
            enhanced = clahe.apply(frame[:, :, 0])
            return enhanced[:, :, np.newaxis]
        # For 3-channel BGR: convert to LAB, equalize lightness, convert back
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        enhanced_l = clahe.apply(l_channel)
        enhanced_lab = cv2.merge((enhanced_l, a_channel, b_channel))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    def preprocess_frame(
        self,
        frame: Any,
        target_width: Optional[int] = None,
        target_height: Optional[int] = None,
        to_rgb: bool = False,
        enhance_contrast: bool = False,
    ) -> np.ndarray:
        """Deterministic preprocessing pipeline.

        Applies optional contrast enhancement, resizing, and color conversion.
        """
        self.validate_frame(frame)
        processed = frame.copy()
        if enhance_contrast:
            processed = self.apply_clahe(processed)
        if target_width is not None or target_height is not None:
            processed = self.resize_frame(
                processed, width=target_width, height=target_height
            )
        if to_rgb:
            processed = self.to_rgb(processed)
        return processed

    # ------------------------------------------------------------------
    # Camera Intrinsics
    # ------------------------------------------------------------------
    @staticmethod
    def compute_focal_length(image_width: int, fov_degrees: float) -> float:
        """Calculate pinhole focal length (in pixels) given image width and horizontal FOV.

        Formula: f = (W / 2) / tan(FOV_rad / 2)
        """
        if image_width <= 0:
            raise ValueError(f"Image width must be positive, got {image_width}")
        if not (0 < fov_degrees < 180):
            raise ValueError(f"FOV must be between 0 and 180 degrees, got {fov_degrees}")
        fov_rad = math.radians(fov_degrees)
        focal_length = (image_width / 2.0) / math.tan(fov_rad / 2.0)
        return float(focal_length)

    def get_camera_intrinsics(
        self,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fov_degrees: float = 90.0,
    ) -> Tuple[float, np.ndarray]:
        """Compute focal length and 3x3 camera intrinsic matrix K.

        Matrix layout:
            [[fx,  0, cx],
             [ 0, fy, cy],
             [ 0,  0,  1]]
        """
        w = width if width is not None else self.default_width
        h = height if height is not None else self.default_height
        focal_length = self.compute_focal_length(w, fov_degrees)
        cx = w / 2.0
        cy = h / 2.0
        intrinsic_matrix = np.array(
            [
                [focal_length, 0.0, cx],
                [0.0, focal_length, cy],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        return focal_length, intrinsic_matrix
