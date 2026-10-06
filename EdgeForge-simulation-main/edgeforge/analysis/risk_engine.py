"""
RiskEngine – turn perception output + ego state into a risk score.

The goal of this starter implementation is to produce an **explainable,
deterministic, rule-based** risk score between 0 and 1, along with a
discrete RiskLevel bucket (LOW / MEDIUM / HIGH / CRITICAL) and a plain-
text reason string.

This is intentionally *not* ML yet, but the class is structured so you
can swap in a learned model later without changing callers.
"""

from __future__ import annotations

from typing import List

from edgeforge.config.settings import settings
from edgeforge.data.models import DetectedObject, RiskAssessment, RiskLevel, VehicleState
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


class RiskEngine:
    """Rule-based risk calculator for EdgeForge.

    Risk-scoring logic (starter)
    ----------------------------
    For each detected object we compute a per-object hazard factor based
    on two simple, monotonic heuristics:
      * Smaller distance  -> higher risk.
      * Faster closing speed (negative relative_speed) -> higher risk.

    The overall risk score is the **maximum** per-object hazard (i.e. the
    single most dangerous object dominates), clamped to [0, 1].  This
    keeps the behaviour intuitive and the output easy to explain.

    Risk-level thresholds
    ---------------------
      0.00 – 0.30   -> LOW
      0.30 – 0.60   -> MEDIUM
      0.60 – 0.85   -> HIGH
      0.85 – 1.00   -> CRITICAL

    TODO:
      * Per-object-type weights (pedestrians > cyclists > cars).
      * Lane-/heading-awareness (objects in the same lane are more dangerous).
      * Time-to-collision (TTC) calculation from relative_speed.
      * ML-based risk predictor trained on historical scenario data.
      * Scenario-specific context (intersections, rain, night, …).
    """

    # Discrete risk-level thresholds.  Kept as class attributes so they
    # are easy to tweak without hunting through the logic.
    LEVEL_MEDIUM: float = 0.30
    LEVEL_HIGH: float = settings.RISK_THRESHOLD  # default 0.70 -> we bump to 0.60 below
    LEVEL_CRITICAL: float = 0.85

    def __init__(self) -> None:
        # The default threshold from settings is 0.70, which sits between
        # HIGH and CRITICAL.  Rebind HIGH so the banding is sensible.
        self.LEVEL_HIGH = 0.60
        self.LEVEL_CRITICAL = settings.RISK_THRESHOLD  # 0.70 by default
        logger.info(
            "RiskEngine initialized: thresholds "
            f"MEDIUM>={self.LEVEL_MEDIUM:.2f}, "
            f"HIGH>={self.LEVEL_HIGH:.2f}, "
            f"CRITICAL>={self.LEVEL_CRITICAL:.2f}"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _per_object_hazard(obj: DetectedObject) -> float:
        """Compute a single object's hazard in [0, 1]."""
        # --- Distance component -------------------------------------------
        #  0 m  -> 1.0 (collision / immediate hazard)
        # 50 m+ -> 0.0 (too far to care about right now)
        if obj.distance <= 0:
            dist_factor = 1.0
        else:
            dist_factor = max(0.0, 1.0 - obj.distance / 50.0)

        # --- Closing-speed component --------------------------------------
        # relative_speed: negative means the object is approaching.
        #  -30 m/s (~108 km/h closing) -> 1.0
        #    0 m/s                   -> 0.0
        #  +ve (moving away)        -> 0.0
        if obj.relative_speed >= 0:
            speed_factor = 0.0
        else:
            speed_factor = min(1.0, abs(obj.relative_speed) / 30.0)

        # Simple weighted combination; distance dominates a bit.
        hazard = 0.65 * dist_factor + 0.35 * speed_factor
        return max(0.0, min(1.0, hazard))

    def _risk_level(self, score: float) -> RiskLevel:
        if score >= self.LEVEL_CRITICAL:
            return RiskLevel.CRITICAL
        if score >= self.LEVEL_HIGH:
            return RiskLevel.HIGH
        if score >= self.LEVEL_MEDIUM:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def calculate_risk(
        self,
        detected_objects: List[DetectedObject],
        vehicle_state: VehicleState,
    ) -> RiskAssessment:
        """Assess overall driving risk given the current scene.

        Parameters
        ----------
        detected_objects :
            Objects currently observed by the perception stack.
        vehicle_state :
            Kinematic state of the ego vehicle.

        Returns
        -------
        RiskAssessment
            risk_score in [0,1], a discrete RiskLevel, a textual reason,
            and the ids of objects that contributed meaningfully.
        """
        if not detected_objects:
            logger.debug("No objects detected -> risk=0 (LOW, baseline)")
            return RiskAssessment(
                risk_score=0.0,
                risk_level=RiskLevel.LOW,
                reason="No objects detected around the ego vehicle. Safe baseline.",
            )

        # ---- Compute per-object hazards ---------------------------------
        hazards = [
            (obj, self._per_object_hazard(obj)) for obj in detected_objects
        ]

        # ---- Overall score = worst single object ------------------------
        overall_score = max(h for _, h in hazards)

        # ---- Build an explainable reason --------------------------------
        contributing: List[str] = []
        reasons: List[str] = []
        for obj, h in hazards:
            if h >= self.LEVEL_MEDIUM:
                contributing.append(obj.object_id)
                reasons.append(
                    f"{obj.object_type}@{obj.distance:.1f}m "
                    f"(closing={-obj.relative_speed:.1f}m/s -> hazard {h:.2f})"
                )

        reasons = reasons[:3]  # keep the reason string concise

        # Ego context contribution: high ego speed slightly amplifies risk.
        ego_speed_kmh = vehicle_state.speed * 3.6
        ego_amplifier = 1.0 + min(0.2, ego_speed_kmh / 500.0)
        overall_score = min(1.0, overall_score * ego_amplifier)

        level = self._risk_level(overall_score)

        if not reasons:
            reason_text = (
                f"{len(detected_objects)} object(s) observed but none are "
                f"immediately hazardous (ego speed {ego_speed_kmh:.1f} km/h)."
            )
        else:
            reason_text = (
                f"{level.name} risk: " + "; ".join(reasons) +
                f" (ego speed {ego_speed_kmh:.1f} km/h)."
            )

        logger.debug(
            f"RiskEngine: score={overall_score:.3f} level={level.name} "
            f"objects={len(detected_objects)}"
        )

        return RiskAssessment(
            risk_score=float(overall_score),
            risk_level=level,
            reason=reason_text,
            contributing_objects=contributing,
        )
