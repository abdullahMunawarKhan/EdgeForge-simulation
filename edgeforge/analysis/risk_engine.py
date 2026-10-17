
"""
RiskEngine – convert perception output and ego state into an explainable
driving-risk assessment.

The rule-based score is bounded between 0 and 1. It considers object
distance, closing speed, object-type weights, time to collision (TTC),
multiple hazards, and ego-vehicle speed.
"""

from __future__ import annotations

import math
from typing import List, Optional

from edgeforge.config.settings import settings
from edgeforge.data.models import (
    DetectedObject,
    RiskAssessment,
    RiskLevel,
    VehicleState,
)
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


class RiskEngine:
    """Calculate explainable driving risk using deterministic rules."""

    LEVEL_MEDIUM: float = 0.30
    LEVEL_HIGH: float = 0.60
    LEVEL_CRITICAL: float = settings.RISK_THRESHOLD

    TTC_THRESHOLD_SECONDS: float = 3.0
    TTC_EXPONENTIAL_SCALE: float = 3.0
    MAX_RELEVANT_DISTANCE: float = 50.0
    MAX_CLOSING_SPEED: float = 30.0
    MAX_EGO_SPEED_KMH: float = 100.0
    MAX_EGO_AMPLIFIER: float = 1.3

    def __init__(self, use_ml: bool = False) -> None:
        self.use_ml = use_ml

        logger.info(
            "RiskEngine initialized: thresholds "
            f"MEDIUM>={self.LEVEL_MEDIUM:.2f}, "
            f"HIGH>={self.LEVEL_HIGH:.2f}, "
            f"CRITICAL>={self.LEVEL_CRITICAL:.2f}"
        )

    @staticmethod
    def _calculate_ttc(obj: DetectedObject) -> Optional[float]:
        """
        Calculate time to collision in seconds.

        Negative relative_speed means the object is approaching.
        TTC is unavailable when distance or closing speed is unknown,
        or when the object is not approaching.
        """
        if obj.distance is None or obj.relative_speed is None:
            return None

        if obj.distance <= 0:
            return 0.0

        if obj.relative_speed >= 0:
            return None

        return obj.distance / max(0.001, -obj.relative_speed)

    def _per_object_hazard(self, obj: DetectedObject) -> float:
        """Return one object's hazard score, bounded between 0 and 1."""

        # Nearer objects receive a higher distance factor.
        if obj.distance is None:
            distance_factor = 0.0
        elif obj.distance <= 0:
            distance_factor = 1.0
        else:
            distance_factor = max(
                0.0,
                1.0 - obj.distance / self.MAX_RELEVANT_DISTANCE,
            )

        # Negative relative speed indicates an approaching object.
        if obj.relative_speed is None or obj.relative_speed >= 0:
            speed_factor = 0.0
        else:
            speed_factor = min(
                1.0,
                -obj.relative_speed / self.MAX_CLOSING_SPEED,
            )

        # Preserve the baseline distance/closing-speed calculation.
        base_hazard = (
            0.65 * distance_factor
            + 0.35 * speed_factor
        )

        # Apply the configured importance of each object type.
        object_type = obj.object_type.strip().lower()
        object_weight = settings.RISK_OBJECT_WEIGHTS.get(
            object_type, 1.0
        )
        hazard = base_hazard * object_weight

        # Exponentially increase hazard when TTC is below 3 seconds.
        ttc = self._calculate_ttc(obj)

        if ttc is not None and ttc < self.TTC_THRESHOLD_SECONDS:
            ttc_multiplier = math.exp(
                (self.TTC_THRESHOLD_SECONDS - ttc)
                / self.TTC_EXPONENTIAL_SCALE
            )
            hazard *= ttc_multiplier

        # A negative or zero distance indicates an immediate hazard.
        if obj.distance is not None and obj.distance <= 0:
            hazard = 1.0

        return max(0.0, min(1.0, hazard))

    def _risk_level(self, score: float) -> RiskLevel:
        """Map a numeric risk score to its existing risk category."""
        if score >= self.LEVEL_CRITICAL:
            return RiskLevel.CRITICAL
        if score >= self.LEVEL_HIGH:
            return RiskLevel.HIGH
        if score >= self.LEVEL_MEDIUM:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _calculate_risk_ml(
        self,
        detected_objects: List[DetectedObject],
        vehicle_state: VehicleState,
    ) -> Optional[float]:
        """
        Placeholder for a future trained risk-prediction model.

        No ML model is connected yet. Returning None allows the
        deterministic rule-based calculation to remain the fallback.
        """
        return None

    def calculate_risk(
        self,
        detected_objects: List[DetectedObject],
        vehicle_state: VehicleState,
    ) -> RiskAssessment:
        """Assess risk and return the project's existing output model."""

        if not detected_objects:
            return RiskAssessment(
                risk_score=0.0,
                risk_level=RiskLevel.LOW,
                reason="No objects detected around the ego vehicle.",
                contributing_objects=[],
            )

        # Calculate each object's hazard independently.
        hazards = [
            (obj, self._per_object_hazard(obj))
            for obj in detected_objects
        ]

        # Combine hazards from all objects rather than using only the
        # single largest hazard. Keep the aggregate bounded.
        combined_hazard = min(
            1.0,
            sum(hazard for _, hazard in hazards),
        )

        # Ego speed is measured in metres per second in VehicleState.
        ego_speed_kmh = max(0.0, vehicle_state.speed * 3.6)
        speed_fraction = min(
            ego_speed_kmh / self.MAX_EGO_SPEED_KMH,
            1.0,
        )
        ego_amplifier = (
            1.0
            + (self.MAX_EGO_AMPLIFIER - 1.0) * speed_fraction
        )

        overall_score = min(1.0, combined_hazard * ego_amplifier)
        level = self._risk_level(overall_score)
        measurements_incomplete = any(
            obj.distance is None or obj.relative_speed is None
            for obj in detected_objects
        )

        contributing: List[str] = []
        reasons: List[str] = []

        for obj, hazard in hazards:
            if hazard < self.LEVEL_MEDIUM:
                continue

            contributing.append(obj.object_id)

            distance_text = (
                f"{obj.distance:.1f} m"
                if obj.distance is not None
                else "unknown distance"
            )

            if obj.relative_speed is None:
                speed_text = "unknown relative speed"
            elif obj.relative_speed < 0:
                speed_text = f"closing at {-obj.relative_speed:.1f} m/s"
            elif obj.relative_speed > 0:
                speed_text = f"moving away at {obj.relative_speed:.1f} m/s"
            else:
                speed_text = "no relative movement"

            ttc = self._calculate_ttc(obj)
            ttc_text = (
                f", TTC={ttc:.2f} s"
                if ttc is not None
                else ", TTC unavailable"
            )

            reasons.append(
                f"{obj.object_type}@{distance_text} "
                f"({speed_text}{ttc_text}, hazard={hazard:.2f})"
            )

        # Keep the explanation concise while retaining all contributors.
        displayed_reasons = reasons[:3]

        if displayed_reasons:
            reason_text = (
                f"{level.name} risk: "
                + "; ".join(displayed_reasons)
                + f". Ego speed={ego_speed_kmh:.1f} km/h; "
                f"speed multiplier={ego_amplifier:.2f}."
            )
            if len(reasons) > 3:
                reason_text += (
                    f" {len(reasons) - 3} additional contributing "
                    "object(s) omitted from the explanation."
                )
            if measurements_incomplete:
                reason_text += (
                    " risk assessment is incomplete because distance or "
                    "relative-speed measurements are unavailable."
                )
        elif measurements_incomplete:
            reason_text = (
                f"{len(detected_objects)} object(s) observed, but distance or "
                "relative-speed measurements are unavailable; risk assessment "
                "is incomplete."
            )
        else:
            reason_text = (
                f"{level.name} risk: no individual object reached "
                f"the {self.LEVEL_MEDIUM:.2f} contribution threshold. "
                f"Ego speed={ego_speed_kmh:.1f} km/h."
            )

        logger.debug(
            f"RiskEngine: score={overall_score:.3f}, "
            f"level={level.name}, objects={len(detected_objects)}"
        )

        return RiskAssessment(
            risk_score=float(overall_score),
            risk_level=level,
            reason=reason_text,
            contributing_objects=contributing,
        )
