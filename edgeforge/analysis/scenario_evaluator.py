
"""
Scenario evaluator for EdgeForge.

Calculates risk and event metrics for a completed scenario and exports
the results to CSV or Parquet.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from edgeforge.config.settings import settings
from edgeforge.data.models import ScenarioEvent, ScenarioResult
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)


class ScenarioEvaluator:
    """Calculate scenario-level metrics and export evaluation results."""

    def __init__(
        self,
        risk_threshold: Optional[float] = None,
        output_dir: Optional[str | Path] = None,
        output_format: Optional[str] = None,
    ) -> None:
        self.risk_threshold = (
            settings.RISK_THRESHOLD
            if risk_threshold is None
            else risk_threshold
        )
        self.output_dir = Path(
            output_dir if output_dir is not None else settings.RUN_DIR
        )
        self.output_format = (
            output_format
            if output_format is not None
            else settings.METRICS_FORMAT
        ).lower()

        if not 0.0 <= self.risk_threshold <= 1.0:
            raise ValueError("risk_threshold must be between 0 and 1")

        if self.output_format not in {"csv", "parquet"}:
            raise ValueError("output_format must be 'csv' or 'parquet'")

    def evaluate(
        self,
        scenario: ScenarioResult,
        risk_history: Optional[Iterable[Any]] = None,
    ) -> Dict[str, float]:
        """
        Calculate metrics for one scenario.

        risk_history may contain RiskAssessment objects or dictionaries.
        Each item should have risk_score and timestamp fields.

        time_above_threshold is estimated from consecutive risk samples.
        The last sample has no known following interval and adds no time.
        """
        samples = list(risk_history or [])
        max_risk_score = 0.0
        time_above_threshold = 0.0

        normalized_samples: List[tuple[float, float]] = []

        for sample in samples:
            if isinstance(sample, dict):
                score = float(sample.get("risk_score", 0.0))
                timestamp = sample.get("timestamp")
            else:
                score = float(getattr(sample, "risk_score", 0.0))
                timestamp = getattr(sample, "timestamp", None)

            max_risk_score = max(max_risk_score, score)

            if timestamp is not None:
                if hasattr(timestamp, "timestamp"):
                    timestamp = timestamp.timestamp()
                normalized_samples.append((float(timestamp), score))

        normalized_samples.sort(key=lambda item: item[0])

        for index in range(len(normalized_samples) - 1):
            current_time, current_score = normalized_samples[index]
            next_time, _ = normalized_samples[index + 1]

            if current_score >= self.risk_threshold:
                time_above_threshold += max(
                    0.0, next_time - current_time
                )

        collision_count = sum(
            event.type == "collision" for event in scenario.events
        )
        lane_invasion_count = sum(
            event.type == "lane_invasion" for event in scenario.events
        )

        # A near-collision event counts as TTC < 1 second only when its
        # message explicitly contains a parseable TTC value.
        near_collisions_ttc_below_1s = 0

        for event in scenario.events:
            if event.type != "near_collision":
                continue

            ttc = self._extract_ttc(event.message)
            if ttc is not None and ttc < 1.0:
                near_collisions_ttc_below_1s += 1

        metrics = {
            "max_risk_score": max_risk_score,
            "time_above_threshold": time_above_threshold,
            "near_collisions_ttc_below_1s": float(
                near_collisions_ttc_below_1s
            ),
            "collision_count": float(collision_count),
            "lane_invasion_count": float(lane_invasion_count),
        }

        scenario.metrics.update(metrics)
        logger.info(
            f"Evaluated scenario '{scenario.scenario_name}': {metrics}"
        )
        return metrics

    @staticmethod
    def _extract_ttc(message: str) -> Optional[float]:
        """Extract TTC from messages such as 'TTC=0.7s' or 'TTC: 0.7'."""
        import re

        match = re.search(
            r"\bTTC\s*[:=]\s*(\d+(?:\.\d+)?)\s*(?:s|sec|seconds)?\b",
            message,
            flags=re.IGNORECASE,
        )
        return float(match.group(1)) if match else None

    def export(
        self,
        scenarios: Iterable[ScenarioResult],
        filename: str = "scenario_metrics",
    ) -> Path:
        """Export scenario metrics to the configured CSV or Parquet format."""
        scenarios = list(scenarios)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        suffix = ".csv" if self.output_format == "csv" else ".parquet"
        output_path = self.output_dir / f"{filename}{suffix}"

        rows = []
        for scenario in scenarios:
            row = {
                "scenario_name": scenario.scenario_name,
                "run_id": scenario.run_id,
                "success": scenario.success,
                "exit_status": scenario.exit_status,
                "duration_s": scenario.duration_s,
            }
            row.update(scenario.metrics)
            rows.append(row)

        if self.output_format == "csv":
            fieldnames = list(dict.fromkeys(
                key for row in rows for key in row
            ))
            if not fieldnames:
                fieldnames = [
                    "scenario_name", "run_id", "success", "exit_status",
                    "duration_s", "max_risk_score", "time_above_threshold",
                    "near_collisions_ttc_below_1s", "collision_count",
                    "lane_invasion_count",
                ]

            with output_path.open(
                "w", newline="", encoding="utf-8"
            ) as file:
                writer = csv.DictWriter(file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

        else:
            try:
                import pandas as pd
            except ImportError as exc:
                raise ImportError(
                    "Parquet export requires pandas and a Parquet engine, "
                    "such as pyarrow. Install them before using this format."
                ) from exc

            try:
                pd.DataFrame(rows).to_parquet(output_path, index=False)
            except ImportError as exc:
                raise ImportError(
                    "Parquet export requires a Parquet engine such as pyarrow."
                ) from exc

        logger.info(f"Exported scenario metrics to {output_path}")
        return output_path
