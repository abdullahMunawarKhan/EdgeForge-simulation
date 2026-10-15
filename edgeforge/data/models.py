"""
Typed data models shared across EdgeForge modules.

These Pydantic models define the "contracts" between the simulation,
perception, and analysis layers. Keeping them in one place makes it
easy to add fields later (e.g. LiDAR point-cloud metadata, heading,
lane information, …) without touching the pipeline code.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Shared small types
# ---------------------------------------------------------------------------

class Location(BaseModel):
    """A 3D position, typically in the simulator/world coordinate system."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class RiskLevel(str, Enum):
    """Discrete risk buckets returned by the RiskEngine."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Vehicle / simulation state
# ---------------------------------------------------------------------------

class VehicleState(BaseModel):
    """Current kinematic state of the ego (autonomous) vehicle."""

    vehicle_id: str = "ego_001"
    speed: float = 0.0  # m/s
    acceleration: float = 0.0  # m/s^2
    location: Location = Field(default_factory=Location)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # TODO: Add heading/yaw, lane_id, steering_angle, brake_pressure, ...


# ---------------------------------------------------------------------------
# Perception output
# ---------------------------------------------------------------------------

class DetectedObject(BaseModel):
    """A single object returned by the perception module."""

    object_id: str = Field(default_factory=lambda: f"obj_{id(object).__str__()}")
    object_type: str = "unknown"  # e.g. "car", "pedestrian", "bicycle", ...
    confidence: float = 0.0  # 0..1
    distance: Optional[float] = None  # meters from ego vehicle, when estimated
    relative_speed: Optional[float] = None  # m/s, when estimated
    bbox: Optional[List[float]] = None  # [x1, y1, x2, y2] in pixel coords
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("confidence")
    @classmethod
    def _clamp_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    # TODO: Add 3D bbox, tracking_id, orientation, class_ids, sensor_source


# ---------------------------------------------------------------------------
# Risk analysis output
# ---------------------------------------------------------------------------

class RiskAssessment(BaseModel):
    """Output of the RiskEngine for one timestamp."""

    risk_score: float = 0.0  # 0..1 overall risk score
    risk_level: RiskLevel = RiskLevel.LOW
    reason: str = "No hazards detected."
    contributing_objects: List[str] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("risk_score")
    @classmethod
    def _clamp_score(cls, v: float) -> float:
        return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# Scenario events
# ---------------------------------------------------------------------------

EVENT_COLLISION = "collision"
EVENT_LANE_INVASION = "lane_invasion"
EVENT_NEAR_COLLISION = "near_collision"
EVENT_INFO = "info"

VALID_EVENT_TYPES = (
    EVENT_COLLISION,
    EVENT_LANE_INVASION,
    EVENT_NEAR_COLLISION,
    EVENT_INFO,
)

VALID_SEVERITIES = ("info", "warning", "critical")


class ScenarioEvent(BaseModel):
    """A structured event that occurs during a scenario run."""

    type: str
    severity: str
    timestamp: float
    message: str = ""

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: str) -> str:
        if v not in VALID_EVENT_TYPES:
            raise ValueError(f"Unknown event type: {v}")
        return v

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        if v not in VALID_SEVERITIES:
            raise ValueError(f"Unknown severity: {v}")
        return v

    @field_validator("timestamp")
    @classmethod
    def _validate_timestamp(cls, v: float) -> float:
        if v < 0:
            raise ValueError("timestamp must be non-negative")
        return v


# ---------------------------------------------------------------------------
# Lane information
# ---------------------------------------------------------------------------

class LaneInfo(BaseModel):
    """Information about the ego vehicle's current lane."""

    lane_id: int = 0
    lane_width_m: float = 3.5
    lateral_offset_m: float = 0.0
    is_invading: bool = False


# ---------------------------------------------------------------------------
# Agent action
# ---------------------------------------------------------------------------

class AgentAction(BaseModel):
    """Control action produced by an agent."""

    throttle: float = 0.0
    steer: float = 0.0
    brake: float = 0.0

    @field_validator("throttle")
    @classmethod
    def _validate_throttle(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("throttle must be between 0 and 1")
        return v

    @field_validator("steer")
    @classmethod
    def _validate_steer(cls, v: float) -> float:
        if not -1.0 <= v <= 1.0:
            raise ValueError("steer must be between -1 and 1")
        return v

    @field_validator("brake")
    @classmethod
    def _validate_brake(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("brake must be between 0 and 1")
        return v


# ---------------------------------------------------------------------------
# LiDAR point cloud
# ---------------------------------------------------------------------------

class LidarPointCloud(BaseModel):
    """Metadata and points representing a LiDAR point cloud."""

    timestamp: float = 0.0
    channels: int = 0
    points: object = Field(default_factory=list)

    @property
    def num_points(self) -> int:
        try:
            return len(self.points)
        except TypeError:
            return 0


# ---------------------------------------------------------------------------
# Scenario result
# ---------------------------------------------------------------------------

class ScenarioResult(BaseModel):
    """Final result of a scenario execution."""

    scenario_name: str
    run_id: str = ""
    success: bool = False
    exit_status: str = "unknown"
    duration_s: float = 0.0
    events: List[ScenarioEvent] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)