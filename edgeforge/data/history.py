"""Historical run and perception failure storage for EdgeForge.

Provides a structured, local, file-based persistence store for simulation
validation runs and perception failure records.

Directory Layout
----------------
<history_dir>/
├── index.json               Fast summary index of all stored runs
├── runs/
│   ├── <run_id>.json        Complete run metadata, parameters, and metrics
└── failures/
    └── <run_id>.jsonl       Line-delimited JSON of all failure records for the run

Inspection & Backup
-------------------
- Inspect runs:
    python -m edgeforge.data.history --list
    python -m edgeforge.data.history --summary
    python -m edgeforge.data.history --scenarios
    python -m edgeforge.data.history --run <run_id>
    python -m edgeforge.data.history --failures <run_id>
- Import existing validation reports:
    python -m edgeforge.data.history --import-metrics runs/metrics.json --import-failures runs/failures.jsonl
- Backup:
    Simply copy or archive (zip/tar) the entire history root folder.
    All files use human-readable JSON and JSONL formats with no proprietary binaries.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from edgeforge.config.settings import PROJECT_ROOT, settings
from edgeforge.data.failure_fingerprints import compute_failure_signature
from edgeforge.data.models import HistoricalRunRecord, PerceptionFailureRecord
from edgeforge.utils.logger import get_logger

logger = get_logger(__name__)

SEVERITY_ORDER: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

DEFAULT_COVERAGE_BOUNDS: dict[str, tuple[float, float]] = {
    "weather.fog_density": (0.0, 100.0),
    "weather.precipitation": (0.0, 100.0),
    "weather.cloudiness": (0.0, 100.0),
    "weather.sun_altitude_angle": (-15.0, 85.0),
    "weather.sun_azimuth_angle": (0.0, 360.0),
    "weather.wetness": (0.0, 100.0),
    "weather.wind_intensity": (0.0, 100.0),
}


def _flatten_dict(d: Mapping[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
    """Recursively flatten nested mappings (e.g. weather.fog_density)."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, Mapping):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class RunHistoryStore:
    """Structured file-based persistence store for simulation validation history."""

    def __init__(self, history_dir: str | Path | None = None) -> None:
        if history_dir is not None:
            self.root = Path(history_dir).resolve()
        else:
            self.root = (PROJECT_ROOT / settings.HISTORY_DIR).resolve()

        self.runs_dir = self.root / "runs"
        self.failures_dir = self.root / "failures"
        self.index_path = self.root / "index.json"
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create storage directories if they do not exist."""
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.failures_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write_text(self, target_path: Path, content: str) -> None:
        """Write content to target_path atomically using a temporary file and fsync."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.parent / f".{target_path.name}.{uuid4().hex}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, target_path)
        except Exception:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    def run_path(self, run_id: str) -> Path:
        """Get file path for a run's JSON metadata."""
        return self.runs_dir / f"{run_id}.json"

    def failures_path(self, run_id: str) -> Path:
        """Get file path for a run's JSONL failure records."""
        return self.failures_dir / f"{run_id}.jsonl"

    def has_run(self, run_id: str) -> bool:
        """Check if a run with the given ID exists in the store."""
        return self.run_path(run_id).is_file()

    def _coerce_run_record(
        self,
        run_record: HistoricalRunRecord | Mapping[str, Any] | Any,
        run_id: str | None = None,
        scenario_id: str | None = None,
    ) -> HistoricalRunRecord:
        """Normalize various input formats into a validated HistoricalRunRecord."""
        if isinstance(run_record, HistoricalRunRecord):
            updates: dict[str, Any] = {}
            if run_id and run_record.run_id != run_id:
                updates["run_id"] = run_id
            if scenario_id and run_record.scenario_id != scenario_id:
                updates["scenario_id"] = scenario_id
            return run_record.model_copy(update=updates) if updates else run_record

        if hasattr(run_record, "to_dict"):
            raw_data = dict(run_record.to_dict())
        elif isinstance(run_record, Mapping):
            raw_data = dict(run_record)
        else:
            raise TypeError(
                f"Unsupported run_record type: {type(run_record)}. Expected HistoricalRunRecord, "
                "RunValidationMetrics, or dict."
            )

        # Handle full report dictionary from validate_carla_perception
        if "metrics" in raw_data and isinstance(raw_data["metrics"], Mapping):
            metrics_dict = dict(raw_data["metrics"])
            scenario_dict = (
                dict(raw_data["scenario"])
                if isinstance(raw_data.get("scenario"), Mapping)
                else {}
            )

            # Preserve conditions: weather, lighting, camera, actor_configuration, map
            conditions: dict[str, Any] = {}
            for src in (metrics_dict.get("scenario_conditions"), raw_data.get("scenario_conditions")):
                if isinstance(src, Mapping):
                    conditions.update(src)
            if scenario_dict:
                for key in ("weather", "lighting", "camera", "map"):
                    if key in scenario_dict and key not in conditions and scenario_dict[key] is not None:
                        conditions[key] = scenario_dict[key]
                if "actor_configuration" not in conditions:
                    actor_cfg: dict[str, Any] = {}
                    for k in ("ego_spawn_index", "ego_actor_id", "target_vehicles", "target_count"):
                        if scenario_dict.get(k) is not None:
                            actor_cfg[k] = scenario_dict[k]
                    if actor_cfg:
                        conditions["actor_configuration"] = actor_cfg

            # Preserve parameters: fixed_delta_seconds, etc.
            parameters: dict[str, Any] = {}
            for src in (metrics_dict.get("parameters"), raw_data.get("parameters")):
                if isinstance(src, Mapping):
                    parameters.update(src)
            if scenario_dict:
                for k in ("fixed_delta_seconds", "fixed_delta"):
                    if k in scenario_dict and k not in parameters and scenario_dict[k] is not None:
                        parameters[k] = scenario_dict[k]

            # Preserve metadata without inventing None values
            metadata: dict[str, Any] = {}
            if isinstance(raw_data.get("metadata"), Mapping):
                metadata.update({k: v for k, v in raw_data["metadata"].items() if v is not None})
            for k in ("server", "map", "detector", "failure_rules"):
                if raw_data.get(k) is not None and k not in metadata:
                    metadata[k] = raw_data[k]

            data: dict[str, Any] = {
                "run_id": (
                    run_id
                    or raw_data.get("run_id")
                    or scenario_dict.get("run_id")
                    or metrics_dict.get("run_id")
                ),
                "scenario_id": (
                    scenario_id
                    or raw_data.get("scenario_id")
                    or scenario_dict.get("scenario_id")
                    or metrics_dict.get("scenario_id")
                    or "unspecified_scenario"
                ),
                "timestamp": raw_data.get("timestamp") or metrics_dict.get("timestamp"),
                "iou_threshold": metrics_dict.get("iou_threshold", 0.5),
                "frames_processed": metrics_dict.get("frames_processed", 0),
                "predictions": metrics_dict.get("predictions", 0),
                "ground_truth_objects": metrics_dict.get("ground_truth_objects", 0),
                "true_positives": metrics_dict.get("true_positives", 0),
                "false_positives": metrics_dict.get("false_positives", 0),
                "missed_detections": metrics_dict.get("missed_detections", 0),
                "precision": metrics_dict.get("precision", 0.0),
                "recall": metrics_dict.get("recall", 0.0),
                "f1": metrics_dict.get("f1", 0.0),
                "matched_iou": metrics_dict.get("matched_iou", 0.0),
                "scenario_conditions": conditions,
                "parameters": parameters,
                "failure_count": metrics_dict.get("failure_count", 0),
                "metadata": metadata,
            }
        else:
            data = raw_data.copy()
            # If scenario conditions are supplied at top-level
            if "scenario_conditions" not in data or not data["scenario_conditions"]:
                conditions = {}
                for key in ("weather", "lighting", "camera", "actor_configuration", "map"):
                    if key in data and data[key] is not None:
                        conditions[key] = data[key]
                if conditions:
                    data["scenario_conditions"] = conditions

            if "metadata" in data and isinstance(data["metadata"], Mapping):
                data["metadata"] = {k: v for k, v in data["metadata"].items() if v is not None}

        if run_id:
            data["run_id"] = run_id
        if scenario_id:
            data["scenario_id"] = scenario_id

        if not data.get("run_id"):
            data["run_id"] = (
                f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
            )

        if not data.get("scenario_id"):
            data["scenario_id"] = "unspecified_scenario"

        # Remove None values for default factory fields
        if data.get("timestamp") is None:
            data.pop("timestamp", None)

        return HistoricalRunRecord.model_validate(data)

    def _coerce_failures(
        self,
        failures: Sequence[PerceptionFailureRecord | Mapping[str, Any]] | None,
        source: Any,
        record: HistoricalRunRecord,
        run_id: str,
        scenario_id: str,
    ) -> list[PerceptionFailureRecord]:
        """Normalize failure records from parameters or source, inheriting parent conditions."""
        raw_failures: Sequence[Any]
        if failures is not None:
            raw_failures = failures
        elif hasattr(source, "failures") and getattr(source, "failures"):
            raw_failures = getattr(source, "failures")
        elif isinstance(source, Mapping) and "failures" in source:
            raw_failures = source["failures"] or []
        else:
            raw_failures = []

        # Extract parent conditions from the validated HistoricalRunRecord
        parent_conditions = dict(record.scenario_conditions or {})

        output: list[PerceptionFailureRecord] = []
        for item in raw_failures:
            if isinstance(item, PerceptionFailureRecord):
                updates: dict[str, Any] = {}
                if item.run_id != run_id:
                    updates["run_id"] = run_id
                if not item.scenario_id and scenario_id:
                    updates["scenario_id"] = scenario_id
                if not item.scenario_conditions and parent_conditions:
                    updates["scenario_conditions"] = dict(parent_conditions)
                    updates["fingerprint"] = compute_failure_signature(
                        item,
                        scenario_conditions=parent_conditions,
                    )
                output.append(item.model_copy(update=updates) if updates else item)
            elif isinstance(item, Mapping):
                f_dict = dict(item)
                f_dict["run_id"] = run_id
                if not f_dict.get("scenario_id") and scenario_id:
                    f_dict["scenario_id"] = scenario_id
                if not f_dict.get("scenario_conditions") and parent_conditions:
                    f_dict["scenario_conditions"] = dict(parent_conditions)
                output.append(PerceptionFailureRecord.model_validate(f_dict))
            else:
                raise TypeError(
                    f"Unsupported failure record item type: {type(item)}. "
                    "Expected PerceptionFailureRecord or dict."
                )
        return output

    def save_run(
        self,
        run_record: HistoricalRunRecord | Mapping[str, Any] | Any,
        failures: Sequence[PerceptionFailureRecord | Mapping[str, Any]] | None = None,
        *,
        run_id: str | None = None,
        scenario_id: str | None = None,
        scenario_metrics: Mapping[str, float] | None = None,
        overwrite: bool = False,
    ) -> HistoricalRunRecord:
        """Persist a completed validation run and its failure records atomically.

        Parameters
        ----------
        run_record:
            A HistoricalRunRecord, RunValidationMetrics, or dict describing run results.
        failures:
            Optional sequence of PerceptionFailureRecord objects or failure dicts.
        run_id:
            Optional explicit run identifier.
        scenario_id:
            Optional explicit scenario identifier.
        overwrite:
            If False, raises FileExistsError if a run with the resolved run_id already exists.

        Returns
        -------
        HistoricalRunRecord:
            The saved, validated historical run record.
        """
        record = self._coerce_run_record(run_record, run_id=run_id, scenario_id=scenario_id)
        if scenario_metrics is not None:
            record = HistoricalRunRecord.model_validate(
                record.model_dump() | {"scenario_metrics": dict(scenario_metrics)}
            )
        resolved_run_id = record.run_id

        run_file = self.run_path(resolved_run_id)
        was_existing = run_file.exists()
        if was_existing and not overwrite:
            raise FileExistsError(
                f"Run '{resolved_run_id}' already exists in historical store at {run_file}. "
                "Pass overwrite=True to allow replacement."
            )

        failure_objs = self._coerce_failures(
            failures,
            run_record,
            record,
            resolved_run_id,
            record.scenario_id,
        )

        # Update failure_count on record if not matching
        if record.failure_count != len(failure_objs):
            record = record.model_copy(update={"failure_count": len(failure_objs)})

        failures_file = self.failures_path(resolved_run_id)
        serialized_failures = "".join(
            json.dumps(f.model_dump(mode="json"), sort_keys=True, allow_nan=False) + "\n"
            for f in failure_objs
        )
        serialized_run = json.dumps(
            record.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"

        try:
            # 1. Atomically write failure records JSONL
            self._atomic_write_text(failures_file, serialized_failures)

            # 2. Atomically write run metadata JSON
            self._atomic_write_text(run_file, serialized_run)

            # 3. Update index.json
            self._update_index_entry(record)
        except Exception:
            # If writing a brand-new run was interrupted, clean up newly created partial files
            if not was_existing:
                if run_file.exists():
                    try:
                        run_file.unlink()
                    except OSError:
                        pass
                if failures_file.exists():
                    try:
                        failures_file.unlink()
                    except OSError:
                        pass
            raise

        logger.info(
            f"Saved historical run '{resolved_run_id}' (scenario='{record.scenario_id}', "
            f"failures={len(failure_objs)}) to {self.root}"
        )
        return record

    def get_run(self, run_id: str) -> HistoricalRunRecord:
        """Load a stored run by its ID.

        Raises KeyError if the run does not exist, or ValueError if the file is corrupted.
        """
        path = self.run_path(run_id)
        if not path.is_file():
            raise KeyError(f"Run '{run_id}' not found in historical store at {path}.")

        try:
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except Exception as exc:
            raise ValueError(f"Corrupted run record JSON for '{run_id}' at {path}: {exc}") from exc

        try:
            return HistoricalRunRecord.model_validate(data)
        except Exception as exc:
            raise ValueError(f"Invalid run record schema for '{run_id}' at {path}: {exc}") from exc

    def get_run_failures(
        self,
        run_id: str,
        *,
        strict: bool = True,
    ) -> list[PerceptionFailureRecord]:
        """Load all failure records for a specific run.

        Parameters
        ----------
        run_id:
            The run ID to load failures for.
        strict:
            If True, raises ValueError if any line is malformed JSON.
            If False, logs a warning and skips corrupted lines.
        """
        path = self.failures_path(run_id)
        if not path.is_file():
            return []

        try:
            raw_text = path.read_text(encoding="utf-8")
        except Exception as exc:
            if strict:
                raise ValueError(f"Could not read failure records file '{path}': {exc}") from exc
            logger.warning(f"Could not read failure records file '{path}': {exc}")
            return []

        records: list[PerceptionFailureRecord] = []
        for line_no, line in enumerate(raw_text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = PerceptionFailureRecord.model_validate_json(stripped)
                records.append(record)
            except Exception as exc:
                if strict:
                    raise ValueError(
                        f"Malformed failure record in '{path}' at line {line_no}: {exc}"
                    ) from exc
                logger.warning(
                    f"Skipping malformed failure record in '{path}' at line {line_no}: {exc}"
                )

        return records

    def list_runs(
        self,
        scenario_id: str | None = None,
        *,
        strict: bool = False,
    ) -> list[HistoricalRunRecord]:
        """List all stored runs, optionally filtered by scenario_id.

        Parameters
        ----------
        scenario_id:
            Optional scenario filter.
        strict:
            If True, errors on any malformed run file. If False, skips corrupted files.
        """
        runs: list[HistoricalRunRecord] = []
        for file_path in sorted(self.runs_dir.glob("*.json")):
            run_id = file_path.stem
            try:
                run = self.get_run(run_id)
                if scenario_id is None or run.scenario_id == scenario_id:
                    runs.append(run)
            except Exception as exc:
                if strict:
                    raise
                logger.warning(f"Skipping malformed run file '{file_path}': {exc}")

        runs.sort(key=lambda r: (r.timestamp, r.run_id), reverse=True)
        return runs

    def __len__(self) -> int:
        """Return total number of stored runs."""
        return len(self.list_runs(strict=False))

    # Alias for convenient appending
    add_run = save_run

    def get_tested_scenarios(self) -> list[str]:
        """Return a sorted list of unique scenario IDs that have been tested."""
        scenarios: set[str] = set()
        for run in self.list_runs(strict=False):
            if run.scenario_id:
                scenarios.add(run.scenario_id)
        return sorted(scenarios)

    def get_failures(
        self,
        scenario_id: str | None = None,
        run_id: str | None = None,
        failure_type: str | None = None,
        min_severity: str | None = None,
        *,
        strict: bool = False,
    ) -> list[PerceptionFailureRecord]:
        """Query failure records across runs with optional filtering.

        Parameters
        ----------
        scenario_id:
            Optional filter by scenario.
        run_id:
            Optional filter by specific run.
        failure_type:
            Optional filter by failure type (e.g. 'missed_detection', 'poor_localization').
        min_severity:
            Optional filter by minimum severity ('low', 'medium', 'high', 'critical').
        strict:
            Whether to raise on malformed failure lines.
        """
        min_sev_score = SEVERITY_ORDER.get(str(min_severity).lower(), 1) if min_severity else 1

        if run_id:
            target_run_ids = [run_id]
        else:
            target_run_ids = [r.run_id for r in self.list_runs(scenario_id=scenario_id, strict=strict)]

        matched_failures: list[PerceptionFailureRecord] = []
        for rid in target_run_ids:
            failures = self.get_run_failures(rid, strict=strict)
            for f in failures:
                if failure_type and f.failure_type != failure_type:
                    continue
                f_sev_score = SEVERITY_ORDER.get(str(f.severity).lower(), 1)
                if f_sev_score < min_sev_score:
                    continue
                matched_failures.append(f)

        return matched_failures

    def find_similar_failures(
        self,
        conditions: Mapping[str, Any],
        *,
        tolerance: float = 5.0,
        strict: bool = False,
    ) -> list[PerceptionFailureRecord]:
        """Find historical failures that occurred under similar scenario conditions.

        Compares flattened condition keys (e.g. 'weather.fog_density' or 'fog_density').
        Numeric conditions match if abs(stored - target) <= tolerance.
        Categorical conditions (e.g. 'map') match by case-insensitive string equality.
        """
        flat_target = _flatten_dict(conditions)
        matching_failures: list[PerceptionFailureRecord] = []

        for run in self.list_runs(strict=strict):
            flat_run_cond = _flatten_dict(run.scenario_conditions)
            matches_all = True

            for target_k, target_v in flat_target.items():
                stored_v = None
                if target_k in flat_run_cond:
                    stored_v = flat_run_cond[target_k]
                else:
                    for k, v in flat_run_cond.items():
                        if k == target_k or k.endswith("." + target_k) or target_k.endswith("." + k):
                            stored_v = v
                            break

                if stored_v is None:
                    matches_all = False
                    break

                if (
                    isinstance(target_v, (int, float))
                    and isinstance(stored_v, (int, float))
                    and not isinstance(target_v, bool)
                    and not isinstance(stored_v, bool)
                ):
                    if abs(float(stored_v) - float(target_v)) > tolerance:
                        matches_all = False
                        break
                else:
                    if str(stored_v).lower() != str(target_v).lower():
                        matches_all = False
                        break

            if matches_all:
                matching_failures.extend(self.get_run_failures(run.run_id, strict=strict))

        return matching_failures

    def get_coverage_summary(self) -> dict[str, Any]:
        """Summarize explored scenarios, parameter ranges, and failure distributions."""
        runs = self.list_runs(strict=False)
        scenario_counts: dict[str, int] = {}
        type_counts: dict[str, int] = {}
        severity_counts: dict[str, int] = {}
        condition_values: dict[str, list[float]] = {}
        parameter_values: dict[str, list[float]] = {}
        total_failures = 0

        for run in runs:
            scenario_counts[run.scenario_id] = scenario_counts.get(run.scenario_id, 0) + 1
            flat_cond = _flatten_dict(run.scenario_conditions)
            for k, v in flat_cond.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    condition_values.setdefault(k, []).append(float(v))

            flat_params = _flatten_dict(run.parameters)
            for k, v in flat_params.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    parameter_values.setdefault(k, []).append(float(v))

            for f in self.get_run_failures(run.run_id, strict=False):
                total_failures += 1
                type_counts[f.failure_type] = type_counts.get(f.failure_type, 0) + 1
                severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

        condition_coverage: dict[str, dict[str, Any]] = {}
        for k, values in condition_values.items():
            if values:
                condition_coverage[k] = {
                    "min": min(values),
                    "max": max(values),
                    "distinct_count": len(set(values)),
                }

        parameter_coverage: dict[str, dict[str, Any]] = {}
        for k, values in parameter_values.items():
            if values:
                parameter_coverage[k] = {
                    "min": min(values),
                    "max": max(values),
                    "distinct_count": len(set(values)),
                }

        # Compute overall coverage ratio across standard domain bounds
        ratios = []
        for param_key, (domain_min, domain_max) in DEFAULT_COVERAGE_BOUNDS.items():
            cov_entry = None
            for k, v in condition_coverage.items():
                if k == param_key or k.endswith("." + param_key) or param_key.endswith("." + k):
                    cov_entry = v
                    break
            if cov_entry is not None:
                domain_span = max(1e-9, domain_max - domain_min)
                tested_span = max(0.0, min(float(cov_entry["max"]), domain_max) - max(float(cov_entry["min"]), domain_min))
                ratios.append(min(1.0, max(0.0, tested_span / domain_span)))
            else:
                ratios.append(0.0)
        overall_cov = round(sum(ratios) / len(ratios), 4) if ratios else 0.0

        return {
            "total_runs": len(runs),
            "total_failures": total_failures,
            "overall_coverage_ratio": overall_cov,
            "tested_scenarios": sorted(scenario_counts.keys()),
            "scenario_run_counts": scenario_counts,
            "failures_by_type": type_counts,
            "failures_by_severity": severity_counts,
            "condition_coverage": condition_coverage,
            "parameter_coverage": parameter_coverage,
        }

    def get_unexplored_conditions(
        self,
        domain_bounds: Mapping[str, tuple[float, float]],
    ) -> dict[str, dict[str, Any]]:
        """Identify unexplored condition parameter ranges given domain bounds.

        Parameters
        ----------
        domain_bounds:
            Mapping of parameter key (e.g. 'fog_density' or 'weather.precipitation')
            to (min_allowed, max_allowed) domain bounds.

        Returns
        -------
        Dictionary detailing tested range, coverage ratio, and remaining unexplored intervals.
        """
        summary = self.get_coverage_summary()
        coverage = summary.get("condition_coverage", {})
        result: dict[str, dict[str, Any]] = {}

        for param_key, (domain_min, domain_max) in domain_bounds.items():
            cov_entry = None
            for k, v in coverage.items():
                if k == param_key or k.endswith("." + param_key) or param_key.endswith("." + k):
                    cov_entry = v
                    break

            if cov_entry is None:
                result[param_key] = {
                    "tested_range": None,
                    "untested_intervals": [(float(domain_min), float(domain_max))],
                    "coverage_ratio": 0.0,
                }
            else:
                tested_min = float(cov_entry["min"])
                tested_max = float(cov_entry["max"])
                untested: list[tuple[float, float]] = []
                if domain_min < tested_min:
                    untested.append((float(domain_min), float(tested_min)))
                if tested_max < domain_max:
                    untested.append((float(tested_max), float(domain_max)))

                domain_span = max(1e-9, domain_max - domain_min)
                tested_span = max(0.0, min(tested_max, domain_max) - max(tested_min, domain_min))
                coverage_ratio = min(1.0, max(0.0, tested_span / domain_span))

                result[param_key] = {
                    "tested_range": (tested_min, tested_max),
                    "untested_intervals": untested,
                    "coverage_ratio": round(coverage_ratio, 4),
                }

        return result

    def import_validation_report(
        self,
        metrics_path: str | Path,
        failures_path: str | Path | None = None,
        *,
        run_id: str | None = None,
        scenario_id: str | None = None,
        overwrite: bool = False,
        strict: bool = True,
    ) -> HistoricalRunRecord:
        """Import an existing exported metrics JSON and optional failures JSON/JSONL into history."""
        m_path = Path(metrics_path)
        if not m_path.is_file():
            raise FileNotFoundError(f"Validation metrics report not found at {m_path}")

        try:
            metrics_data = json.loads(m_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Could not parse validation metrics JSON from {m_path}: {exc}") from exc

        failure_records: list[PerceptionFailureRecord] = []
        if failures_path is not None:
            f_path = Path(failures_path)
            if not f_path.is_file():
                raise FileNotFoundError(f"Validation failures report not found at {f_path}")

            try:
                f_text = f_path.read_text(encoding="utf-8").strip()
            except Exception as exc:
                raise ValueError(f"Could not read failures report at {f_path}: {exc}") from exc

            if f_text:
                if f_path.suffix.lower() in {".jsonl", ".ndjson"}:
                    for line_no, line in enumerate(f_text.splitlines(), start=1):
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            failure_records.append(
                                PerceptionFailureRecord.model_validate_json(stripped)
                            )
                        except Exception as exc:
                            if strict:
                                raise ValueError(
                                    f"Malformed failure record in '{f_path}' at line {line_no}: {exc}"
                                ) from exc
                            logger.warning(
                                f"Skipping malformed failure record in '{f_path}' at line {line_no}: {exc}"
                            )
                else:
                    try:
                        loaded = json.loads(f_text)
                    except Exception as exc:
                        raise ValueError(f"Could not parse failure JSON from {f_path}: {exc}") from exc
                    if isinstance(loaded, list):
                        for item in loaded:
                            failure_records.append(PerceptionFailureRecord.model_validate(item))
                    elif isinstance(loaded, dict):
                        failure_records.append(PerceptionFailureRecord.model_validate(loaded))
        elif "failures" in metrics_data and isinstance(metrics_data["failures"], list):
            for item in metrics_data["failures"]:
                failure_records.append(PerceptionFailureRecord.model_validate(item))

        return self.save_run(
            metrics_data,
            failures=failure_records,
            run_id=run_id,
            scenario_id=scenario_id,
            overwrite=overwrite,
        )

    def delete_run(self, run_id: str) -> bool:
        """Delete a run and its failures from the store."""
        run_file = self.run_path(run_id)
        failures_file = self.failures_path(run_id)
        deleted = False

        if run_file.exists():
            run_file.unlink()
            deleted = True
        if failures_file.exists():
            failures_file.unlink()

        if deleted:
            self._remove_index_entry(run_id)
        return deleted

    def _update_index_entry(self, record: HistoricalRunRecord) -> None:
        """Update or insert index.json entry for a run."""
        index = self._load_or_rebuild_index()
        index["runs"][record.run_id] = {
            "run_id": record.run_id,
            "scenario_id": record.scenario_id,
            "timestamp": record.timestamp,
            "failure_count": record.failure_count,
            "precision": record.precision,
            "recall": record.recall,
            "f1": record.f1,
            "matched_iou": record.matched_iou,
        }
        index["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._atomic_write_text(self.index_path, json.dumps(index, indent=2, sort_keys=True) + "\n")
        except Exception as exc:
            logger.warning(f"Could not update index.json: {exc}")

    def _remove_index_entry(self, run_id: str) -> None:
        """Remove a run entry from index.json."""
        index = self._load_or_rebuild_index()
        if run_id in index.get("runs", {}):
            del index["runs"][run_id]
            index["updated_at"] = datetime.now(timezone.utc).isoformat()
            try:
                self._atomic_write_text(self.index_path, json.dumps(index, indent=2, sort_keys=True) + "\n")
            except Exception as exc:
                logger.warning(f"Could not update index.json: {exc}")

    def _load_or_rebuild_index(self) -> dict[str, Any]:
        """Load index.json or rebuild it if missing or corrupted."""
        if self.index_path.is_file():
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "runs" in data:
                    return data
            except Exception:
                pass
        return self.rebuild_index()

    def rebuild_index(self) -> dict[str, Any]:
        """Scan runs/ and rebuild index.json from on-disk run records."""
        runs_map: dict[str, Any] = {}
        for run_file in self.runs_dir.glob("*.json"):
            run_id = run_file.stem
            try:
                run = self.get_run(run_id)
                runs_map[run.run_id] = {
                    "run_id": run.run_id,
                    "scenario_id": run.scenario_id,
                    "timestamp": run.timestamp,
                    "failure_count": run.failure_count,
                    "precision": run.precision,
                    "recall": run.recall,
                    "f1": run.f1,
                    "matched_iou": run.matched_iou,
                }
            except Exception as exc:
                logger.warning(f"Skipping {run_file} during index rebuild: {exc}")

        index_data = {
            "version": "1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "runs": runs_map,
        }
        try:
            self._atomic_write_text(self.index_path, json.dumps(index_data, indent=2, sort_keys=True) + "\n")
        except Exception as exc:
            logger.warning(f"Could not write rebuilt index.json: {exc}")
        return index_data


def get_history_store(history_dir: str | Path | None = None) -> RunHistoryStore:
    """Return an initialized RunHistoryStore instance."""
    return RunHistoryStore(history_dir)


def save_run_to_history(
    run_record: Any,
    failures: Any = None,
    history_dir: str | Path | None = None,
    **kwargs: Any,
) -> HistoricalRunRecord:
    """Convenience function to save a run to the history store."""
    return RunHistoryStore(history_dir).save_run(run_record, failures, **kwargs)


def load_run_from_history(
    run_id: str,
    history_dir: str | Path | None = None,
) -> HistoricalRunRecord:
    """Convenience function to load a run record from history."""
    return RunHistoryStore(history_dir).get_run(run_id)


def list_historical_runs(
    scenario_id: str | None = None,
    history_dir: str | Path | None = None,
    *,
    strict: bool = False,
) -> list[HistoricalRunRecord]:
    """Convenience function to list runs in the historical store."""
    return RunHistoryStore(history_dir).list_runs(scenario_id=scenario_id, strict=strict)


def load_failures_from_history(
    run_id: str | None = None,
    scenario_id: str | None = None,
    failure_type: str | None = None,
    min_severity: str | None = None,
    history_dir: str | Path | None = None,
    *,
    strict: bool = False,
) -> list[PerceptionFailureRecord]:
    """Convenience function to query historical failures."""
    return RunHistoryStore(history_dir).get_failures(
        scenario_id=scenario_id,
        run_id=run_id,
        failure_type=failure_type,
        min_severity=min_severity,
        strict=strict,
    )


def import_report_to_history(
    metrics_path: str | Path,
    failures_path: str | Path | None = None,
    history_dir: str | Path | None = None,
    **kwargs: Any,
) -> HistoricalRunRecord:
    """Convenience function to import a validation report into history."""
    return RunHistoryStore(history_dir).import_validation_report(
        metrics_path,
        failures_path,
        **kwargs,
    )


def main() -> int:
    """CLI utility for inspecting and managing the EdgeForge historical store."""
    parser = argparse.ArgumentParser(
        description="Inspect and manage the EdgeForge simulation run history."
    )
    parser.add_argument("--history-dir", type=Path, default=None, help="Custom history directory.")
    parser.add_argument("--list", action="store_true", help="List all stored runs.")
    parser.add_argument("--summary", action="store_true", help="Print scenario coverage summary.")
    parser.add_argument("--scenarios", action="store_true", help="List tested scenario IDs.")
    parser.add_argument("--run", type=str, help="Show details for a specific run ID.")
    parser.add_argument("--failures", type=str, help="List failure records for a specific run ID.")
    parser.add_argument("--import-metrics", type=Path, help="Import a validation report JSON.")
    parser.add_argument("--import-failures", type=Path, help="Optional failure JSON/JSONL for import.")
    parser.add_argument("--rebuild-index", action="store_true", help="Rebuild index.json from disk.")
    args = parser.parse_args()

    store = RunHistoryStore(args.history_dir)

    if args.import_metrics:
        imported = store.import_validation_report(
            args.import_metrics,
            failures_path=args.import_failures,
        )
        print(f"Successfully imported run '{imported.run_id}' (scenario='{imported.scenario_id}').")
        return 0

    if args.rebuild_index:
        idx = store.rebuild_index()
        print(f"Rebuilt index with {len(idx.get('runs', {}))} runs.")
        return 0

    if args.list:
        runs = store.list_runs()
        print(f"Stored runs ({len(runs)} total):")
        for r in runs:
            print(
                f"  - {r.run_id:30s} | scenario: {r.scenario_id:25s} | "
                f"P: {r.precision:.2f} R: {r.recall:.2f} F1: {r.f1:.2f} | "
                f"failures: {r.failure_count:3d} | {r.timestamp}"
            )
        return 0

    if args.summary:
        summary = store.get_coverage_summary()
        print(json.dumps(summary, indent=2))
        return 0

    if args.scenarios:
        scenarios = store.get_tested_scenarios()
        print(f"Tested scenarios ({len(scenarios)}):")
        for s in scenarios:
            print(f"  - {s}")
        return 0

    if args.run:
        try:
            r = store.get_run(args.run)
            print(json.dumps(r.model_dump(mode="json"), indent=2))
        except KeyError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.failures:
        try:
            failures = store.get_run_failures(args.failures)
            print(f"Failures for run '{args.failures}' ({len(failures)} total):")
            for f in failures:
                print(
                    f"  - [{f.severity.upper()}] {f.failure_type} | class: {f.object_class} | "
                    f"conf: {f.confidence} | iou: {f.iou} | frame: {f.frame_id}"
                )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    parser.print_help()
    return 0


__all__ = [
    "RunHistoryStore",
    "get_history_store",
    "save_run_to_history",
    "load_run_from_history",
    "list_historical_runs",
    "load_failures_from_history",
    "import_report_to_history",
]


if __name__ == "__main__":
    raise SystemExit(main())
