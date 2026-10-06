"""
EdgeForge global configuration.

Uses pydantic-settings to load values from environment variables and .env files.
CARLA-specific values live here so they can be overridden per deployment without
touching the perception / analysis pipeline code.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the EdgeForge platform.

    Values are resolved in the following priority order (highest first):
      1. Environment variables
      2. .env file at the project root
      3. Defaults declared below
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
    # TODO: Integrate CARLA synchronous mode + TrafficManager config here.
    # ------------------------------------------------------------------
    CARLA_HOST: str = "127.0.0.1"
    CARLA_PORT: int = 2000
    CARLA_TIMEOUT: float = 10.0

    # ------------------------------------------------------------------
    # Camera / sensor defaults
    # TODO: Add LiDAR, IMU, GNSS sensor configs here as they are integrated.
    # ------------------------------------------------------------------
    CAMERA_WIDTH: int = 1280
    CAMERA_HEIGHT: int = 720
    CAMERA_FOV: int = 90
    CAMERA_TICK: float = 0.05  # seconds between camera captures (20 FPS)

    # ------------------------------------------------------------------
    # Risk analysis
    # TODO: Add per-object-type risk weight configuration here later.
    # ------------------------------------------------------------------
    RISK_THRESHOLD: float = 0.7

    # ------------------------------------------------------------------
    # Perception
    # ------------------------------------------------------------------
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.5
    TRACKER_IOU_THRESHOLD: float = 0.3
    TRACKER_MAX_AGE: int = 5


settings = Settings()
