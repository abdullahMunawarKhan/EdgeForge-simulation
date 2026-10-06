"""
Typed data models shared across EdgeForge modules.

These Pydantic models define the "contracts" between the simulation,
perception, and analysis layers.  Keeping them in one place makes it
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
    distance: float = 0.0  # meters from ego vehicle
    relative_speed: float = 0.0  # m/s, positive = object moving away
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
