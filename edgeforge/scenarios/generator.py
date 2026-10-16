"""EDGEFORGE — Next-Best Scenario Generator (Milestone 4A).

Proposes and ranks CARLA perception-testing scenarios by combining:
1. Historical Failure Evidence: Prioritizing conditions where YOLO detections
   have previously failed (missed detections, poor localization, low confidence).
2. Coverage Novelty: Identifying gaps and under-tested intervals in parameter space.
3. Condition Similarity: Quantifying the depth of prior test evidence.
4. Test Feasibility & Duplicate Avoidance: Rejecting invalid parameters and identical tests.

This module is strictly a recommendation tool and does NOT launch CARLA,
download models, or execute live validation runs.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from edgeforge.config.settings import PROJECT_ROOT, settings
from edgeforge.data.history import RunHistoryStore, get_history_store
from edgeforge.perception.validation import SUPPORTED_EVALUATION_CLASSES
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)

# Canonical bounds for supported scenario parameters
DEFAULT_DOMAIN_BOUNDS: dict[str, tuple[float, float]] = {
    "weather.fog_density": (0.0, 100.0),
    "weather.precipitation": (0.0, 100.0),
    "weather.cloudiness": (0.0, 100.0),
    "weather.sun_altitude_angle": (-15.0, 85.0),
    "weather.sun_azimuth_angle": (0.0, 360.0),
    "weather.wetness": (0.0, 100.0),
    "weather.wind_intensity": (0.0, 100.0),
    "actor_configuration.target_count": (1.0, 5.0),
}

# Supported CARLA maps in the current test environment
SUPPORTED_MAPS: tuple[str, ...] = ("Town01", "Town02", "Town03")

# Standard CARLA weather presets and representative parameter profiles
CARLA_WEATHER_PRESETS: dict[str, dict[str, float]] = {
    "ClearNoon": {"cloudiness": 0.0, "precipitation": 0.0, "fog_density": 0.0, "sun_altitude_angle": 60.0, "wetness": 0.0},
    "CloudyNoon": {"cloudiness": 80.0, "precipitation": 0.0, "fog_density": 0.0, "sun_altitude_angle": 60.0, "wetness": 0.0},
    "WetNoon": {"cloudiness": 90.0, "precipitation": 0.0, "fog_density": 0.0, "sun_altitude_angle": 60.0, "wetness": 100.0},
    "WetSunset": {"cloudiness": 90.0, "precipitation": 0.0, "fog_density": 0.0, "sun_altitude_angle": 15.0, "wetness": 100.0},
    "MidRainyNoon": {"cloudiness": 80.0, "precipitation": 40.0, "fog_density": 10.0, "sun_altitude_angle": 60.0, "wetness": 60.0},
    "HardRainNoon": {"cloudiness": 100.0, "precipitation": 80.0, "fog_density": 20.0, "sun_altitude_angle": 45.0, "wetness": 100.0},
    "ClearSunset": {"cloudiness": 0.0, "precipitation": 0.0, "fog_density": 0.0, "sun_altitude_angle": 15.0, "wetness": 0.0},
    "SoftRainSunset": {"cloudiness": 80.0, "precipitation": 30.0, "fog_density": 15.0, "sun_altitude_angle": 15.0, "wetness": 50.0},
    "ClearSunrise": {"cloudiness": 0.0, "precipitation": 0.0, "fog_density": 0.0, "sun_altitude_angle": 5.0, "wetness": 0.0},
    "CloudySunset": {"cloudiness": 80.0, "precipitation": 0.0, "fog_density": 0.0, "sun_altitude_angle": 15.0, "wetness": 0.0},
    "WetCloudySunset": {"cloudiness": 80.0, "precipitation": 0.0, "fog_density": 10.0, "sun_altitude_angle": 15.0, "wetness": 80.0},
    "MidRainSunset": {"cloudiness": 80.0, "precipitation": 40.0, "fog_density": 15.0, "sun_altitude_angle": 15.0, "wetness": 60.0},
    "HardRainSunset": {"cloudiness": 100.0, "precipitation": 80.0, "fog_density": 25.0, "sun_altitude_angle": 15.0, "wetness": 100.0},
}

# Known parameters NOT supported by the current simulation runner
KNOWN_UNSUPPORTED_PARAMETERS: frozenset[str] = frozenset({
    "adversarial_cut_in",
    "dynamic_occlusion_mesh",
    "emergency_braking_trigger",
    "sensor_dirt_overlay",
    "pedestrian_jaywalking_trajectory",
    "variable_focal_length",
})


def match_closest_weather_preset(
    cloudiness: float,
    precipitation: float,
    fog_density: float,
    sun_altitude_angle: float,
    wetness: float,
) -> str:
    """Find the nearest CARLA weather preset by Euclidean distance."""
    best_name = "ClearNoon"
    best_dist = float("inf")

    target = (cloudiness, precipitation, fog_density, sun_altitude_angle, wetness)
    for name, p in CARLA_WEATHER_PRESETS.items():
        candidate = (
            p["cloudiness"],
            p["precipitation"],
            p["fog_density"],
            p["sun_altitude_angle"],
            p["wetness"],
        )
        dist = sum((a - b) ** 2 for a, b in zip(target, candidate))
        if dist < best_dist:
            best_dist = dist
            best_name = name

    return best_name


class WeatherParameters(BaseModel):
    """Granular weather conditions compatible with CARLA WeatherParameters."""

    cloudiness: float = Field(default=0.0, ge=0.0, le=100.0)
    precipitation: float = Field(default=0.0, ge=0.0, le=100.0)
    precipitation_deposits: float = Field(default=0.0, ge=0.0, le=100.0)
    wind_intensity: float = Field(default=0.0, ge=0.0, le=100.0)
    fog_density: float = Field(default=0.0, ge=0.0, le=100.0)
    fog_distance: float = Field(default=0.0, ge=0.0, le=100.0)
    wetness: float = Field(default=0.0, ge=0.0, le=100.0)
    sun_azimuth_angle: float = Field(default=0.0, ge=0.0, le=360.0)
    sun_altitude_angle: float = Field(default=60.0, ge=-90.0, le=90.0)


class ActorConfiguration(BaseModel):
    """Actor deployment configuration supported by the test harness."""

    target_count: int = Field(default=2, ge=1, le=5)
    ego_spawn_index: int = Field(default=0, ge=0)
    target_types: list[str] = Field(default_factory=lambda: ["car"])
    traffic_vehicles: int = Field(default=2, ge=0)
    traffic_pedestrians: int = Field(default=0, ge=0)
    traffic_bicycles: int = Field(default=0, ge=0)


class ScoreBreakdown(BaseModel):
    """Decomposed, normalized score components."""

    failure_evidence: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage_novelty: float = Field(default=0.0, ge=0.0, le=1.0)
    condition_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    feasibility: float = Field(default=1.0, ge=0.0, le=1.0)


class ScenarioCandidate(BaseModel):
    """A proposed candidate scenario before or during ranking."""

    candidate_id: str
    scenario_id: str
    map_name: str = "Town01"
    weather: WeatherParameters = Field(default_factory=WeatherParameters)
    actor_config: ActorConfiguration = Field(default_factory=ActorConfiguration)
    weather_preset: str = "ClearNoon"
    fixed_delta_seconds: float = 0.05
    unsupported_features: list[str] = Field(default_factory=list)

    @field_validator("map_name")
    @classmethod
    def _validate_map(cls, v: str) -> str:
        if v not in SUPPORTED_MAPS:
            raise ValueError(f"Unsupported map '{v}'. Must be one of {SUPPORTED_MAPS}.")
        return v

    def to_scenario_conditions(self) -> dict[str, Any]:
        """Convert candidate to validation scenario conditions dictionary."""
        return {
            "map": self.map_name,
            "weather": self.weather.model_dump(),
            "lighting": {
                "sun_azimuth_angle": self.weather.sun_azimuth_angle,
                "sun_altitude_angle": self.weather.sun_altitude_angle,
            },
            "actor_configuration": {
                "ego_spawn_index": self.actor_config.ego_spawn_index,
                "target_count": self.actor_config.target_count,
                "target_types": self.actor_config.target_types,
            },
            "fixed_delta_seconds": self.fixed_delta_seconds,
        }

    def to_runner_config(self, duration_seconds: float = 30.0) -> dict[str, Any]:
        """Convert candidate to scenario_runner JSON schema."""
        return {
            "name": self.scenario_id,
            "description": f"Generated scenario ({self.weather_preset}, fog={self.weather.fog_density:.1f})",
            "version": "1.0",
            "weather": self.weather_preset,
            "fine_weather": self.weather.model_dump(),
            "candidate_id": self.candidate_id,
            "map": self.map_name,
            "duration_seconds": duration_seconds,
            "simulation": {"backend": "carla"},
            "traffic": {
                "vehicles": self.actor_config.traffic_vehicles,
                "pedestrians": self.actor_config.traffic_pedestrians,
                "bicycles": self.actor_config.traffic_bicycles,
            },
            "ego_vehicle": {
                "model": "vehicle.tesla.model3",
                "spawn_point_index": self.actor_config.ego_spawn_index,
                "speed_limit": 50,
                "autopilot": False,
            },
            "sensors": {
                "rgb_camera": {
                    "enabled": true if hasattr(bool, "true") else True,
                    "width": settings.CAMERA_WIDTH,
                    "height": settings.CAMERA_HEIGHT,
                    "fov": settings.CAMERA_FOV,
                    "tick": self.fixed_delta_seconds,
                },
                "collision": {"enabled": True},
                "lane_invasion": {"enabled": True},
            },
            "generated_metadata": {
                "candidate_id": self.candidate_id,
                "fine_weather": self.weather.model_dump(),
                "unsupported_features": self.unsupported_features,
            },
        }


class RankedScenario(BaseModel):
    """A scored scenario recommendation with full human-readable audit trail."""

    candidate_id: str
    scenario_id: str
    overall_score: float = Field(ge=0.0, le=1.0)
    score_breakdown: ScoreBreakdown
    weights: dict[str, float]
    cold_start: bool = False
    selection_reason: str
    historical_evidence: list[dict[str, Any]] = Field(default_factory=list)
    novelty_explanation: str = ""
    unsupported_features: list[str] = Field(default_factory=list)
    scenario_conditions: dict[str, Any] = Field(default_factory=dict)
    scenario_config: dict[str, Any] = Field(default_factory=dict)


class ScenarioGenerator:
    """Proposes, scores, and explains next-best scenario candidates."""

    def __init__(
        self,
        history_store: RunHistoryStore | None = None,
        *,
        history_dir: str | Path | None = None,
        weights: Mapping[str, float] | None = None,
        domain_bounds: Mapping[str, tuple[float, float]] | None = None,
        seed: int | None = None,
    ) -> None:
        self.store = history_store or get_history_store(history_dir)
        self.domain_bounds = dict(domain_bounds or DEFAULT_DOMAIN_BOUNDS)
        self.rng = random.Random(seed)

        # Configurable ranking weights
        raw_weights = dict(
            weights
            or {
                "failure_evidence": 0.45,
                "coverage_novelty": 0.40,
                "condition_similarity": 0.15,
            }
        )
        total_w = sum(raw_weights.values())
        if total_w <= 0:
            raise ValueError("Total weights must be strictly positive.")
        self.weights = {k: v / total_w for k, v in raw_weights.items()}

    def generate_candidates(
        self,
        num_candidates: int = 20,
        *,
        seed: int | None = None,
        unsupported_parameters: Sequence[str] | None = None,
    ) -> list[ScenarioCandidate]:
        """Generate valid candidate scenarios through bounded parametric sampling.

        Parameters
        ----------
        num_candidates:
            Number of candidate scenarios to generate.
        seed:
            Optional random seed for reproducible sampling.
        unsupported_parameters:
            Optional parameter names that the caller requested but are unsupported.

        Returns
        -------
        list[ScenarioCandidate]
            List of valid, schema-checked scenario candidates.
        """
        if num_candidates <= 0:
            raise ValueError("num_candidates must be a positive integer.")

        rng = random.Random(seed) if seed is not None else self.rng
        candidates: list[ScenarioCandidate] = []

        unsupported_list: list[str] = []
        if unsupported_parameters:
            for p in unsupported_parameters:
                if p in KNOWN_UNSUPPORTED_PARAMETERS or p not in DEFAULT_DOMAIN_BOUNDS:
                    unsupported_list.append(p)

        target_classes_pool = [c for c in sorted(SUPPORTED_EVALUATION_CLASSES) if c in {"car", "pedestrian", "truck", "bicycle"}]

        for i in range(1, num_candidates + 1):
            cand_uuid = f"{rng.getrandbits(24):06x}"
            cand_id = f"cand_{i:03d}_{cand_uuid}"
            scenario_id = f"nextbest_scen_{i:03d}_{cand_uuid}"

            # Bounded continuous sampling
            fog = rng.uniform(0.0, 100.0)
            precip = rng.uniform(0.0, 100.0)
            cloud = rng.uniform(0.0, 100.0)
            sun_alt = rng.uniform(-15.0, 85.0)
            sun_az = rng.uniform(0.0, 360.0)
            wet = min(100.0, max(0.0, precip * rng.uniform(0.8, 1.2)))
            wind = rng.uniform(0.0, 80.0)

            # Discrete actor choices
            target_count = rng.randint(1, 4)
            ego_spawn = rng.randint(0, 5)
            selected_map = rng.choice(SUPPORTED_MAPS)

            # Sample 1-2 evaluation target classes
            n_classes = min(len(target_classes_pool), rng.randint(1, 2))
            chosen_classes = rng.sample(target_classes_pool, n_classes)

            # Nearest CARLA preset mapping
            preset = match_closest_weather_preset(
                cloudiness=cloud,
                precipitation=precip,
                fog_density=fog,
                sun_altitude_angle=sun_alt,
                wetness=wet,
            )

            weather_obj = WeatherParameters(
                cloudiness=round(cloud, 2),
                precipitation=round(precip, 2),
                precipitation_deposits=round(precip * 0.9, 2),
                wind_intensity=round(wind, 2),
                fog_density=round(fog, 2),
                fog_distance=round(rng.uniform(0.0, 50.0), 2),
                wetness=round(wet, 2),
                sun_azimuth_angle=round(sun_az, 2),
                sun_altitude_angle=round(sun_alt, 2),
            )

            actor_obj = ActorConfiguration(
                target_count=target_count,
                ego_spawn_index=ego_spawn,
                target_types=chosen_classes,
                traffic_vehicles=rng.randint(1, 6),
                traffic_pedestrians=rng.randint(0, 3),
                traffic_bicycles=1 if "bicycle" in chosen_classes else 0,
            )

            candidate = ScenarioCandidate(
                candidate_id=cand_id,
                scenario_id=scenario_id,
                map_name=selected_map,
                weather=weather_obj,
                actor_config=actor_obj,
                weather_preset=preset,
                fixed_delta_seconds=0.05,
                unsupported_features=list(unsupported_list),
            )
            candidates.append(candidate)

        return candidates

    def score_candidate(
        self,
        candidate: ScenarioCandidate,
        *,
        history_runs: Sequence[Any],
        tolerance: float = 15.0,
    ) -> tuple[float, ScoreBreakdown, list[dict[str, Any]], str]:
        """Score a single candidate against historical evidence and parameter coverage.

        Returns
        -------
        tuple[float, ScoreBreakdown, list[dict], str]
            (overall_score, breakdown, historical_evidence, novelty_explanation)
        """
        # 1. Feasibility check
        is_feasible = (
            0.0 <= candidate.weather.fog_density <= 100.0
            and 0.0 <= candidate.weather.precipitation <= 100.0
            and -90.0 <= candidate.weather.sun_altitude_angle <= 90.0
            and candidate.actor_config.target_count >= 1
            and candidate.map_name in SUPPORTED_MAPS
        )
        feasibility_score = 1.0 if is_feasible else 0.0
        if not is_feasible:
            return 0.0, ScoreBreakdown(feasibility=0.0), [], "Candidate rejected: parameters violate physical or simulator bounds."

        # Feasibility penalty if unsupported parameters were requested
        if candidate.unsupported_features:
            feasibility_score *= max(0.2, 1.0 - (0.2 * len(candidate.unsupported_features)))

        # 2. Historical failure evidence
        conditions = candidate.to_scenario_conditions()
        similar_failures = self.store.find_similar_failures(
            {"weather.fog_density": candidate.weather.fog_density, "weather.precipitation": candidate.weather.precipitation},
            tolerance=tolerance,
        )

        severity_weights = {"low": 1.0, "medium": 2.0, "high": 3.0, "critical": 4.0}
        type_weights = {
            "missed_detection": 1.3,
            "false_positive": 1.1,
            "poor_localization": 1.0,
            "confidence_degradation": 0.8,
            "low_confidence": 0.6,
        }

        raw_failure_sum = 0.0
        evidence_records: list[dict[str, Any]] = []
        seen_evidence_runs: set[str] = set()

        for f in similar_failures:
            sev_w = severity_weights.get(str(f.severity).lower(), 1.0)
            typ_w = type_weights.get(str(f.failure_type).lower(), 1.0)
            raw_failure_sum += sev_w * typ_w

            if f.run_id and f.run_id not in seen_evidence_runs:
                seen_evidence_runs.add(f.run_id)
                evidence_records.append(
                    {
                        "run_id": f.run_id,
                        "failure_type": f.failure_type,
                        "severity": f.severity,
                        "object_class": f.object_class,
                        "iou": f.iou,
                        "confidence": f.confidence,
                    }
                )

        # Saturating normalization into [0, 1]
        failure_evidence_score = 1.0 - math.exp(-raw_failure_sum / 8.0) if raw_failure_sum > 0 else 0.0

        # 3. Coverage novelty
        tested_fogs = [
            float(r.scenario_conditions.get("weather", {}).get("fog_density", 0.0))
            for r in history_runs
            if isinstance(r.scenario_conditions.get("weather"), dict)
        ]
        tested_precips = [
            float(r.scenario_conditions.get("weather", {}).get("precipitation", 0.0))
            for r in history_runs
            if isinstance(r.scenario_conditions.get("weather"), dict)
        ]

        novelty_explanations: list[str] = []
        if not tested_fogs:
            fog_novelty = 1.0
            novelty_explanations.append("fog_density explores unbenchmarked baseline space (no prior runs)")
        else:
            min_dist_fog = min(abs(candidate.weather.fog_density - tf) for tf in tested_fogs)
            fog_novelty = min(1.0, (min_dist_fog / 35.0))
            if fog_novelty > 0.5:
                novelty_explanations.append(
                    f"fog_density={candidate.weather.fog_density:.1f} is {min_dist_fog:.1f} units away from tested points"
                )

        if not tested_precips:
            precip_novelty = 1.0
            novelty_explanations.append("precipitation explores unbenchmarked baseline space")
        else:
            min_dist_precip = min(abs(candidate.weather.precipitation - tp) for tp in tested_precips)
            precip_novelty = min(1.0, (min_dist_precip / 35.0))
            if precip_novelty > 0.5:
                novelty_explanations.append(
                    f"precipitation={candidate.weather.precipitation:.1f} is {min_dist_precip:.1f} units away from tested points"
                )

        # Low sun angle glare novelty
        if -10.0 <= candidate.weather.sun_altitude_angle <= 15.0:
            glare_novelty = 0.85
            novelty_explanations.append(f"low sun altitude ({candidate.weather.sun_altitude_angle:.1f} deg) tests low-angle glare")
        else:
            glare_novelty = 0.4

        coverage_novelty_score = (fog_novelty * 0.45) + (precip_novelty * 0.40) + (glare_novelty * 0.15)
        coverage_novelty_score = min(1.0, max(0.0, coverage_novelty_score))

        # 4. Condition similarity depth
        similarity_score = min(1.0, len(similar_failures) / 6.0)

        # 5. Composite overall score
        is_cold_start = len(history_runs) == 0
        if is_cold_start:
            overall = coverage_novelty_score * feasibility_score
        else:
            overall = (
                self.weights["failure_evidence"] * failure_evidence_score
                + self.weights["coverage_novelty"] * coverage_novelty_score
                + self.weights["condition_similarity"] * similarity_score
            ) * feasibility_score

        overall = round(min(1.0, max(0.0, overall)), 4)
        breakdown = ScoreBreakdown(
            failure_evidence=round(failure_evidence_score, 4),
            coverage_novelty=round(coverage_novelty_score, 4),
            condition_similarity=round(similarity_score, 4),
            feasibility=round(feasibility_score, 4),
        )

        novelty_str = "; ".join(novelty_explanations) if novelty_explanations else "Standard tested parameter neighborhood."
        return overall, breakdown, evidence_records, novelty_str

    def rank_candidates(
        self,
        candidates: Sequence[ScenarioCandidate],
        *,
        allow_duplicates: bool = False,
    ) -> list[RankedScenario]:
        """Score and rank candidates deterministically, avoiding duplicates.

        Parameters
        ----------
        candidates:
            Sequence of candidates to evaluate.
        allow_duplicates:
            Whether to allow scenarios identical to prior runs or earlier candidates.

        Returns
        -------
        list[RankedScenario]
            Ranked scenarios ordered by descending overall score.
        """
        history_runs = self.store.list_runs(strict=False)
        is_cold_start = len(history_runs) == 0

        # Track existing test conditions to avoid duplicates
        existing_signatures: list[tuple[float, float, float, int, str]] = []
        for r in history_runs:
            w = r.scenario_conditions.get("weather", {}) if isinstance(r.scenario_conditions, dict) else {}
            a = r.scenario_conditions.get("actor_configuration", {}) if isinstance(r.scenario_conditions, dict) else {}
            sig = (
                float(w.get("fog_density", 0.0)),
                float(w.get("precipitation", 0.0)),
                float(w.get("sun_altitude_angle", 60.0)),
                int(a.get("target_count", 2)),
                str(r.scenario_conditions.get("map", "Town01")),
            )
            existing_signatures.append(sig)

        accepted_signatures: list[tuple[float, float, float, int, str]] = []
        ranked_list: list[RankedScenario] = []

        for cand in candidates:
            cand_sig = (
                cand.weather.fog_density,
                cand.weather.precipitation,
                cand.weather.sun_altitude_angle,
                cand.actor_config.target_count,
                cand.map_name,
            )

            # Check duplicate against existing history
            is_dup_history = any(
                abs(cand_sig[0] - es[0]) <= 1.0
                and abs(cand_sig[1] - es[1]) <= 1.0
                and abs(cand_sig[2] - es[2]) <= 3.0
                and cand_sig[3] == es[3]
                and cand_sig[4] == es[4]
                for es in existing_signatures
            )

            # Check duplicate against already accepted candidates in this batch
            is_dup_batch = any(
                abs(cand_sig[0] - asig[0]) <= 2.0
                and abs(cand_sig[1] - asig[1]) <= 2.0
                and abs(cand_sig[2] - asig[2]) <= 4.0
                and cand_sig[3] == asig[3]
                and cand_sig[4] == asig[4]
                for asig in accepted_signatures
            )

            if (is_dup_history or is_dup_batch) and not allow_duplicates:
                continue

            overall, breakdown, evidence, novelty_str = self.score_candidate(
                cand,
                history_runs=history_runs,
            )

            # Build selection reasoning narrative
            if is_cold_start:
                reason = (
                    f"Selected in cold-start mode (no prior historical runs). "
                    f"Prioritizes coverage novelty ({breakdown.coverage_novelty:.2f}) across "
                    f"{cand.map_name} with {cand.weather_preset} preset (fog={cand.weather.fog_density:.1f}, "
                    f"precip={cand.weather.precipitation:.1f}) to establish baseline detection performance."
                )
            elif evidence:
                fail_summary = f"{len(evidence)} historical failures"
                lead_fail = evidence[0]
                reason = (
                    f"Selected with overall score {overall:.3f}. Recommended because similar conditions "
                    f"(fog~{cand.weather.fog_density:.1f}, precip~{cand.weather.precipitation:.1f}) exhibited "
                    f"{fail_summary} (e.g. {lead_fail['failure_type']} [{lead_fail['severity'].upper()}] in run {lead_fail['run_id']}). "
                    f"Coverage novelty score is {breakdown.coverage_novelty:.2f}."
                )
            else:
                reason = (
                    f"Selected with overall score {overall:.3f}. Recommended for exploratory novelty "
                    f"({breakdown.coverage_novelty:.2f}) under {cand.weather_preset} preset with no previous failure records."
                )

            if cand.unsupported_features:
                reason += f" Note: Contains unsupported parameters ({', '.join(cand.unsupported_features)}) flagged for future work."

            ranked = RankedScenario(
                candidate_id=cand.candidate_id,
                scenario_id=cand.scenario_id,
                overall_score=overall,
                score_breakdown=breakdown,
                weights=self.weights,
                cold_start=is_cold_start,
                selection_reason=reason,
                historical_evidence=evidence,
                novelty_explanation=novelty_str,
                unsupported_features=cand.unsupported_features,
                scenario_conditions=cand.to_scenario_conditions(),
                scenario_config=cand.to_runner_config(),
            )
            ranked_list.append(ranked)
            accepted_signatures.append(cand_sig)

        ranked_list.sort(key=lambda r: (r.overall_score, r.candidate_id), reverse=True)
        return ranked_list

    def generate_and_rank(
        self,
        num_candidates: int = 20,
        *,
        seed: int | None = None,
        allow_duplicates: bool = False,
        unsupported_parameters: Sequence[str] | None = None,
    ) -> list[RankedScenario]:
        """Convenience method to generate candidates and rank them in one step."""
        candidates = self.generate_candidates(
            num_candidates=num_candidates,
            seed=seed,
            unsupported_parameters=unsupported_parameters,
        )
        return self.rank_candidates(candidates, allow_duplicates=allow_duplicates)

    def save_recommendations(
        self,
        recommendations: Sequence[RankedScenario],
        destination: str | Path,
    ) -> Path:
        """Persist ranked recommendations to a formatted JSON document."""
        dest_path = Path(destination).resolve()
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "generator_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "cold_start": recommendations[0].cold_start if recommendations else False,
            "weights": self.weights,
            "total_ranked": len(recommendations),
            "recommendations": [r.model_dump(mode="json") for r in recommendations],
        }

        dest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        logger.info(f"Saved {len(recommendations)} scenario recommendations to {dest_path}")
        return dest_path

    @staticmethod
    def load_recommendations(source: str | Path) -> list[RankedScenario]:
        """Load previously saved scenario recommendations from JSON."""
        src_path = Path(source).resolve()
        if not src_path.is_file():
            raise FileNotFoundError(f"Recommendations file not found at {src_path}")

        data = json.loads(src_path.read_text(encoding="utf-8"))
        raw_list = data.get("recommendations", [])
        return [RankedScenario.model_validate(item) for item in raw_list]


def generate_and_rank_scenarios(
    num_candidates: int = 20,
    history_dir: str | Path | None = None,
    *,
    seed: int | None = None,
    output_path: str | Path | None = None,
    **kwargs: Any,
) -> list[RankedScenario]:
    """Top-level convenience function to generate, rank, and optionally save scenarios."""
    generator = ScenarioGenerator(history_dir=history_dir, seed=seed, **kwargs)
    ranked = generator.generate_and_rank(num_candidates=num_candidates, seed=seed)
    if output_path is not None:
        generator.save_recommendations(ranked, output_path)
    return ranked


class RandomScenarioGenerator:
    """Generates valid candidate scenarios uniformly at random across supported bounds.

    Used as an unbiased, reproducible testing baseline that operates under the exact
    same parameter bounds, map choices, and validation rules as the guided generator.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.rng = random.Random(seed)

    def generate_candidates(
        self,
        count: int = 10,
        *,
        seed: int | None = None,
    ) -> list[ScenarioCandidate]:
        """Sample valid scenarios uniformly over the supported parameter domain."""
        if count <= 0:
            raise ValueError("count must be a positive integer.")
        rng = random.Random(seed) if seed is not None else self.rng
        candidates: list[ScenarioCandidate] = []
        target_classes_pool = [c for c in sorted(SUPPORTED_EVALUATION_CLASSES) if c in {"car", "pedestrian", "truck", "bicycle"}]

        for i in range(1, count + 1):
            cand_uuid = f"{rng.getrandbits(24):06x}"
            cand_id = f"random_cand_{i:03d}_{cand_uuid}"
            scenario_id = f"random_scen_{i:03d}_{cand_uuid}"

            fog = rng.uniform(0.0, 100.0)
            precip = rng.uniform(0.0, 100.0)
            cloud = rng.uniform(0.0, 100.0)
            sun_alt = rng.uniform(-15.0, 85.0)
            sun_az = rng.uniform(0.0, 360.0)
            wet = min(100.0, max(0.0, precip * rng.uniform(0.8, 1.2)))
            wind = rng.uniform(0.0, 80.0)

            target_count = rng.randint(1, 4)
            ego_spawn = rng.randint(0, 5)
            selected_map = rng.choice(SUPPORTED_MAPS)

            k_types = rng.randint(1, min(len(target_classes_pool), 2))
            chosen_types = rng.sample(target_classes_pool, k_types)

            weather_params = WeatherParameters(
                cloudiness=cloud,
                precipitation=precip,
                precipitation_deposits=wet,
                wind_intensity=wind,
                fog_density=fog,
                wetness=wet,
                sun_azimuth_angle=sun_az,
                sun_altitude_angle=sun_alt,
            )

            actor_config = ActorConfiguration(
                target_count=target_count,
                ego_spawn_index=ego_spawn,
                target_types=chosen_types,
                traffic_vehicles=rng.randint(0, 8),
                traffic_pedestrians=rng.randint(0, 4),
                traffic_bicycles=rng.randint(0, 2),
            )

            preset = match_closest_weather_preset(
                cloudiness=cloud,
                precipitation=precip,
                fog_density=fog,
                sun_altitude_angle=sun_alt,
                wetness=wet,
            )

            candidates.append(
                ScenarioCandidate(
                    candidate_id=cand_id,
                    scenario_id=scenario_id,
                    map_name=selected_map,
                    weather=weather_params,
                    actor_config=actor_config,
                    weather_preset=preset,
                    fixed_delta_seconds=0.05,
                )
            )

        return candidates


def main() -> int:
    """CLI utility for generating and ranking next-best perception testing scenarios."""
    parser = argparse.ArgumentParser(
        description="Propose and rank next-best CARLA perception-testing scenarios."
    )
    parser.add_argument("--history-dir", type=Path, default=None, help="Custom history directory.")
    parser.add_argument("--candidates", type=int, default=20, help="Number of candidate scenarios to generate.")
    parser.add_argument("--top-k", type=int, default=5, help="Number of top ranked recommendations to display.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible candidate sampling.")
    parser.add_argument("--allow-duplicates", action="store_true", help="Allow duplicate or near-duplicate candidates.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "runs" / "scenario_recommendations.json",
        help="Path to save ranked scenarios JSON.",
    )
    parser.add_argument(
        "--weights",
        nargs="+",
        metavar="KEY=VAL",
        default=[],
        help="Custom score weights, e.g. --weights failure_evidence=0.5 coverage_novelty=0.5",
    )
    args = parser.parse_args()

    custom_weights = {}
    for item in args.weights:
        k, sep, v = item.partition("=")
        if not sep:
            parser.error(f"Weights must be formatted as KEY=VAL, got '{item}'")
        try:
            custom_weights[k.strip()] = float(v.strip())
        except ValueError:
            parser.error(f"Invalid weight value in '{item}'")

    generator = ScenarioGenerator(
        history_dir=args.history_dir,
        weights=custom_weights or None,
        seed=args.seed,
    )

    print("=" * 70)
    print("  EDGEFORGE -- Next-Best Scenario Generator")
    print("=" * 70)
    print(f"  Historical Store: {generator.store.root}")
    print(f"  Generating:       {args.candidates} candidates (seed={args.seed})")
    print(f"  Weights:          {generator.weights}")
    print("=" * 70)

    ranked = generator.generate_and_rank(
        num_candidates=args.candidates,
        seed=args.seed,
        allow_duplicates=args.allow_duplicates,
    )

    if not ranked:
        print("No valid candidates generated.")
        return 1

    generator.save_recommendations(ranked, args.output)

    top_display = ranked[: args.top_k]
    mode_str = "COLD-START (Exploration)" if ranked[0].cold_start else "FAILURE-GUIDED"
    print(f"\nTop {len(top_display)} Recommendations [{mode_str}]:\n")

    for idx, r in enumerate(top_display, start=1):
        cond = r.scenario_conditions
        weather = cond.get("weather", {})
        print(f"  #{idx:d} | Score: {r.overall_score:.3f} | {r.scenario_id}")
        print(f"      Map: {cond.get('map')} | Preset: {r.scenario_config.get('weather')}")
        print(
            f"      Weather: fog={weather.get('fog_density', 0.0):.1f}%, "
            f"precip={weather.get('precipitation', 0.0):.1f}%, "
            f"sun_alt={weather.get('sun_altitude_angle', 0.0):.1f} deg"
        )
        print(
            f"      Breakdown: fail_evidence={r.score_breakdown.failure_evidence:.2f}, "
            f"novelty={r.score_breakdown.coverage_novelty:.2f}, "
            f"similarity={r.score_breakdown.condition_similarity:.2f}"
        )
        print(f"      Why: {r.selection_reason}")
        if r.historical_evidence:
            print(f"      Prior Evidence: {len(r.historical_evidence)} matching run failures")
        if r.unsupported_features:
            print(f"      [!] Unsupported Features Flagged: {', '.join(r.unsupported_features)}")
        print()

    print(f"Full ranked scenarios saved to: {args.output}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
