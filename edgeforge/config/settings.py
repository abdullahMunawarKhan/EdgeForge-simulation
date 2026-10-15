"""Centralized configuration for EdgeForge.

This module intentionally loads the project-root .env file using python-dotenv
before resolving settings so the runtime can connect to the remote CARLA host
without hardcoded values scattered through the codebase.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings(BaseSettings):
    """Typed settings for the EdgeForge platform.

    Values are resolved in the following priority order (highest first):
      1. Environment variables
      2. .env file at the project root
      3. Defaults declared below
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Project metadata
    # ------------------------------------------------------------------
    PROJECT_NAME: str = "EdgeForge"
    VERSION: str = "0.1.0"
    DEBUG: bool = True

    # ------------------------------------------------------------------
    # CARLA simulator connection
    # ------------------------------------------------------------------
    CARLA_HOST: str = "127.0.0.1"
    CARLA_PORT: int = 2000
    CARLA_TIMEOUT: float = 10.0

    # ------------------------------------------------------------------
    # Camera / sensor defaults
    # ------------------------------------------------------------------
    CAMERA_WIDTH: int = 1280
    CAMERA_HEIGHT: int = 720
    CAMERA_FOV: int = 90
    CAMERA_TICK: float = 0.05  # seconds between camera captures (20 FPS)

    LIDAR_CHANNELS: int = Field(default=32, gt=0)
    LIDAR_POINTS_PER_SECOND: int = Field(default=56000, gt=0)
    LIDAR_RANGE_M: float = Field(default=10.0, gt=0)

    # ------------------------------------------------------------------
    # Risk analysis
    # ------------------------------------------------------------------
    RISK_THRESHOLD: float = 0.7
    RISK_OBJECT_WEIGHTS: Dict[str, float] = {
        "pedestrian": 1.5,
        "bicycle": 1.2,
        "car": 1.0,
    }

    # ------------------------------------------------------------------
    # Perception
    # ------------------------------------------------------------------
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.5
    YOLO_MODEL_PATH: str = "yolov8n.pt"
    YOLO_NMS_IOU: float = Field(default=0.7, gt=0, le=1)
    YOLO_DEVICE: Literal["cpu", "cuda"] = "cpu"
    TRACKER_IOU_THRESHOLD: float = 0.3
    TRACKER_MAX_AGE: int = 5

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------
    LOG_DIR: str = "logs"
    RUN_DIR: str = "runs"
    METRICS_FORMAT: Literal["csv", "parquet"] = "csv"

    @field_validator("RISK_OBJECT_WEIGHTS")
    @classmethod
    def check_weights_positive(cls, value: Dict[str, float]) -> Dict[str, float]:
        """Reject zero or negative weights."""
        for name, weight in value.items():
            if weight <= 0:
                raise ValueError(f"weight for {name!r} must be > 0")
        return value

settings = Settings()