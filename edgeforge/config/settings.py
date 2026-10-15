"""
EdgeForge global configuration.

Uses pydantic-settings to load values from environment variables and .env files.
CARLA-specific values live here so they can be overridden per deployment without
touching the perception / analysis pipeline code.

SIMULATION BACKENDS:
  EdgeForge can run the scenario loop in three ways — selected via
  --backend / --mock CLI flags or cfg["simulation"]["backend"] in the JSON:

    1. "carla"  — real CARLA server (needs a running CarlaUE4.exe).
       Server tips for Windows laptops with small VRAM:
         * Launch with:
             .\\CarlaUE4.exe -RenderOffscreen -quality-level=Low -nosound
                  -benchmark -fps=10 -carla-map=/Game/Carla/Maps/Town01
                  -NoTextureStreaming -FeatureLevelES31
         * NVIDIA Control Panel → Max Frame Rate = 30, Shader Cache = 100MB
         * Always use Town01 first (smallest map, ~50% less VRAM than Town03).

    2. "mock"   — pure-Python synthetic simulation.  No CARLA server, no
       CARLA wheel import needed for mock mode.  The ego/NPCs use a
       kinematic integrator and the camera renders a synthetic image
       (sky + perspective road + scrolling dashes + projected NPC car
       boxes).  The exact same SensorFrame / VehicleState / DetectedObject
       / RiskAssessment pydantic types flow through the pipeline, so
       Persons 2, 3, 4 can develop on any laptop without installing
       CARLA.  This is the default fallback when --backend=detect fails.

    3. "detect" — try "carla"; on connect failure fall back to "mock"
       with a warning.  Default.

REMOTE / WSL2 CARLA HOSTS:
  When running CARLA elsewhere (WSL2, cloud/Colab, a desktop):
    1. Set the ENV VARs below (or edit .env):
          CARLA_HOST=<ip or "wsl.localhost">
          CARLA_PORT=2000
    2. On the remote machine: run CarlaUE4.exe with extra flag
          -carla-rpc-port=2000
       and open TCP port 2000 + 2002 (for TM) in the firewall.
    3. For WSL2: "wsl.localhost" resolves the WSL2 VM automatically;
       if it doesn't, use `wsl hostname -I` and paste the IP into .env.
"""

from typing import Dict, Literal

from pydantic import Field, field_validator
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
    # ------------------------------------------------------------------
    CAMERA_WIDTH: int = 1280
    CAMERA_HEIGHT: int = 720
    CAMERA_FOV: int = 90
    CAMERA_TICK: float = 0.05  # seconds between camera captures (20 FPS)

    # NEW: LiDAR block (gt=0 means "must be greater than 0")
    LIDAR_CHANNELS: int = Field(default=32, gt=0)
    LIDAR_POINTS_PER_SECOND: int = Field(default=56000, gt=0)
    LIDAR_RANGE_M: float = Field(default=10.0, gt=0)

    # ------------------------------------------------------------------
    # Risk analysis
    # ------------------------------------------------------------------
    RISK_THRESHOLD: float = 0.7

    # NEW: per-object-type weights (keys must be these exact words)
    RISK_OBJECT_WEIGHTS: Dict[str, float] = {
        "pedestrian": 1.5,
        "bicycle": 1.2,
        "car": 1.0,
    }

    # ------------------------------------------------------------------
    # Perception
    # ------------------------------------------------------------------
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.5

    # NEW: YOLO block (Literal means only these exact values are allowed)
    YOLO_MODEL_PATH: str = "yolov8n.pt"
    YOLO_NMS_IOU: float = Field(default=0.7, gt=0, le=1)
    YOLO_DEVICE: Literal["cpu", "cuda"] = "cpu"

    # ------------------------------------------------------------------
    # NEW: Outputs
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