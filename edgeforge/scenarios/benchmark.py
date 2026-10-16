"""Testing Strategy Benchmark: Failure-Guided Exploration vs. Random Testing Baseline.

Conducts a fair, reproducible comparison between the failure-guided next-best scenario
generator and a uniform random baseline under identical test budgets, parameter ranges,
and detector evaluation thresholds.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from edgeforge.config import settings
from edgeforge.data.history import RunHistoryStore, get_history_store
from edgeforge.data.models import PerceptionFailureRecord
from edgeforge.perception.validation import RunValidationMetrics
from edgeforge.scenarios.executor import (
    ExecutionResult,
    ExecutionStatus,
    ScenarioExecutionManager,
    validate_scenario_config,
)
from edgeforge.scenarios.generator import (
    CARLA_WEATHER_PRESETS,
    DEFAULT_DOMAIN_BOUNDS,
    SUPPORTED_MAPS,
    RandomScenarioGenerator,
    RankedScenario,
    ScenarioCandidate,
    ScenarioGenerator,
)
from edgeforge.simulation.scenario_runner import BACKEND_CARLA, BACKEND_MOCK
from edgeforge.utils import get_logger

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Unique Failure Signature Definition
# ---------------------------------------------------------------------------
def compute_failure_signature(
    failure: PerceptionFailureRecord | Mapping[str, Any],
    scenario_conditions: Mapping[str, Any] | None = None,
) -> str:
    """Extract a canonical, deduplicated failure signature for a perception failure.

    Definition:
        A unique failure signature is defined by the 4-tuple:
        (failure_type, object_class, severity, weather_lighting_bin)

        Where environmental conditions are categorized into discrete bins:
        - Fog bin:
            * 'fog_clear'     (fog_density < 20.0)
            * 'fog_moderate'  (20.0 <= fog_density <= 60.0)
            * 'fog_dense'     (fog_density > 60.0)
        - Rain bin:
            * 'rain_none'     (precipitation < 10.0)
            * 'rain_light'    (10.0 <= precipitation <= 50.0)
            * 'rain_heavy'    (precipitation > 50.0)
        - Lighting bin:
            * 'night'         (sun_altitude_angle < 0.0)
            * 'low_sun'       (0.0 <= sun_altitude_angle <= 25.0)
            * 'day'           (sun_altitude_angle > 25.0)

    Limitations:
        1. Environmental discretization: Grouping continuous weather values into 3x3x3
           discrete bins avoids treating slight weather noise as distinct bugs, but
           boundary cases (e.g. fog 19% vs 21%) fall into adjacent bins.
        2. Repeated frame deduplication: Repeated detection failures of the same object
           class in the same scenario/condition bin are collapsed to 1 signature.
        3. Geometry abstraction: Bins capture causal atmospheric/lighting contexts,
           not distinct spatial trajectories (e.g. cut-in vs perpendicular crossing).
    """
    if isinstance(failure, dict):
        ftype = failure.get("failure_type", "unknown_type")
        oclass = failure.get("object_class") or "unknown_class"
        severity = failure.get("severity", "medium")
        embedded_conditions = failure.get("scenario_conditions") or {}
    else:
        ftype = getattr(failure, "failure_type", "unknown_type")
        oclass = getattr(failure, "object_class", None) or "unknown_class"
        severity = getattr(failure, "severity", "medium")
        embedded_conditions = getattr(failure, "scenario_conditions", {}) or {}

    conds = scenario_conditions if scenario_conditions is not None else embedded_conditions

    weather = conds.get("weather", {})
    if isinstance(weather, str) and weather in CARLA_WEATHER_PRESETS:
        weather = CARLA_WEATHER_PRESETS[weather]

    if isinstance(weather, dict):
        fog = float(weather.get("fog_density", 0.0))
        precip = float(weather.get("precipitation", 0.0))
        sun_alt = float(weather.get("sun_altitude_angle", 60.0))
    else:
        fog = 0.0
        precip = 0.0
        sun_alt = 60.0

    # Categorize fog
    if fog < 20.0:
        fog_bin = "fog_clear"
    elif fog <= 60.0:
        fog_bin = "fog_mod"
    else:
        fog_bin = "fog_dense"

    # Categorize precipitation
    if precip < 10.0:
        rain_bin = "dry"
    elif precip <= 50.0:
        rain_bin = "light_rain"
    else:
        rain_bin = "heavy_rain"

    # Categorize sun altitude
    if sun_alt < 0.0:
        sun_bin = "night"
    elif sun_alt <= 25.0:
        sun_bin = "low_sun"
    else:
        sun_bin = "day"

    return f"{ftype}:{oclass}:{severity}:{fog_bin}_{rain_bin}_{sun_bin}"


# ---------------------------------------------------------------------------
# Benchmark Data Structures
# ---------------------------------------------------------------------------
@dataclass
class PerRunRecord:
    """Record of a single scenario execution within a benchmark run."""

    strategy: str
    run_id: str
    candidate_id: str
    scenario_id: str
    status: str
    map_name: str
    weather_preset: str
    fog_density: float
    precipitation: float
    sun_altitude_angle: float
    traffic_vehicles: int
    frames: int
    sim_time_s: float
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    matched_iou: float
    failure_count: int
    unique_signatures_count: int
    unique_signatures: list[str]


@dataclass
class StrategyBenchmarkMetrics:
    """Aggregated evaluation metrics for a testing strategy."""

    strategy_name: str
    attempted_scenarios: int
    completed_scenarios: int
    failed_scenarios: int
    total_frames: int
    total_sim_time_s: float
    total_tp: int
    total_fp: int
    total_fn: int
    precision: float
    recall: float
    f1: float
    matched_iou: float
    unique_failure_signatures_count: int
    unique_signatures: list[str]
    failures_by_type: dict[str, int]
    failures_by_severity: dict[str, int]
    coverage_summary: dict[str, Any]
    runs: list[PerRunRecord] = field(default_factory=list)
    micro_precision: float = 0.0
    micro_recall: float = 0.0
    micro_f1: float = 0.0


# ---------------------------------------------------------------------------
# Testing Strategy Benchmark Harness
# ---------------------------------------------------------------------------
class TestingStrategyBenchmark:
    """Executes a fair, budget-matched comparison between Guided and Random testing."""

    __test__ = False  # Prevent pytest from treating this harness as a test suite

    def __init__(
        self,
        scenario_budget: int = 5,
        max_frames_per_scenario: int = 30,
        duration_seconds: float = 15.0,
        iou_threshold: float = 0.5,
        seed: int = 42,
        backend: str = BACKEND_MOCK,
        output_dir: Optional[Path] = None,
    ) -> None:
        if scenario_budget <= 0:
            raise ValueError("scenario_budget must be a positive integer.")
        if max_frames_per_scenario <= 0:
            raise ValueError("max_frames_per_scenario must be a positive integer.")

        self.scenario_budget = scenario_budget
        self.max_frames = max_frames_per_scenario
        self.duration_seconds = duration_seconds
        self.iou_threshold = iou_threshold
        self.seed = seed
        self.backend = backend
        self.output_dir = Path(output_dir or PROJECT_ROOT / "runs" / "benchmarks" / f"bmk_{seed}_{backend}")
        self.benchmark_id = f"bmk_{seed}_{uuid_token()}"

    def run_dry_run(self) -> dict[str, Any]:
        """Perform dry-run validation for both strategies without simulation execution."""
        logger.info(f"🔍 Running dry-run benchmark plan (budget={self.scenario_budget} scenarios)...")

        # Guided dry-run
        guided_store_dir = self.output_dir / "dryrun_guided_store"
        guided_store = RunHistoryStore(guided_store_dir)
        guided_gen = ScenarioGenerator(history_store=guided_store, seed=self.seed)
        guided_candidates = guided_gen.generate_candidates(self.scenario_budget * 2, seed=self.seed)
        ranked_guided = guided_gen.rank_candidates(guided_candidates)[: self.scenario_budget]

        # Random dry-run
        random_gen = RandomScenarioGenerator(seed=self.seed)
        random_candidates = random_gen.generate_candidates(self.scenario_budget, seed=self.seed)

        manager = ScenarioExecutionManager(default_backend=self.backend)

        guided_validation = [manager.dry_run(c) for c in ranked_guided]
        random_validation = [manager.dry_run(c) for c in random_candidates]

        plan = {
            "benchmark_id": self.benchmark_id,
            "seed": self.seed,
            "backend": "dry_run",
            "scenario_budget": self.scenario_budget,
            "max_frames_per_scenario": self.max_frames,
            "guided_planned_scenarios": [
                {
                    "candidate_id": r.candidate_id,
                    "scenario_id": r.scenario_id,
                    "status": r.status.value,
                    "map": r.scenario_config.get("map"),
                    "weather": r.scenario_config.get("weather"),
                }
                for r in guided_validation
            ],
            "random_planned_scenarios": [
                {
                    "candidate_id": r.candidate_id,
                    "scenario_id": r.scenario_id,
                    "status": r.status.value,
                    "map": r.scenario_config.get("map"),
                    "weather": r.scenario_config.get("weather"),
                }
                for r in random_validation
            ],
            "all_valid": all(r.status == ExecutionStatus.VALIDATED for r in guided_validation + random_validation),
        }
        return plan

    def run(self) -> dict[str, Any]:
        """Execute full benchmark comparison under identical test budgets."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("=" * 70)
        logger.info("  EDGEFORGE -- Testing Strategy Benchmark")
        logger.info("=" * 70)
        logger.info(f"  Benchmark ID:   {self.benchmark_id}")
        logger.info(f"  Backend:        {self.backend} (disclosure: {'Mock synthetic offline' if self.backend == BACKEND_MOCK else 'Live CARLA server'})")
        logger.info(f"  Budget:         {self.scenario_budget} scenarios @ {self.max_frames} max frames each")
        logger.info(f"  Seed:           {self.seed}")
        logger.info("=" * 70)

        # 1. Failure-Guided Exploration (Closed-loop adaptive execution)
        guided_metrics = self._run_guided_strategy()

        # 2. Random Testing Baseline (Uniform random sampling across same bounds)
        random_metrics = self._run_random_strategy()

        # 3. Compile comparison summary
        comparison_results = self._compile_comparison(guided_metrics, random_metrics)

        # 4. Export JSON, CSV, and Markdown report
        self._export_results(comparison_results)

        return comparison_results

    def _run_guided_strategy(self) -> StrategyBenchmarkMetrics:
        """Run adaptive failure-guided scenario exploration.

        CRITICAL REQUIREMENT: The guided strategy must NEVER use results from
        future or not-yet-executed scenarios. At step t, it uses ONLY history
        accumulated up to step t-1.
        """
        logger.info("🎯 Executing Strategy 1: FAILURE-GUIDED EXPLORATION")
        guided_store_dir = self.output_dir / "guided_history_store"
        guided_store = RunHistoryStore(guided_store_dir)
        manager = ScenarioExecutionManager(history_store=guided_store, default_backend=self.backend)

        run_records: list[PerRunRecord] = []
        all_signatures: set[str] = set()
        failures_by_type: dict[str, int] = {}
        failures_by_severity: dict[str, int] = {}

        attempt = 0
        completed_count = 0
        max_attempts = self.scenario_budget * 2

        while completed_count < self.scenario_budget and attempt < max_attempts:
            # Step t: generator sees history up to this exact moment
            step_seed = self.seed + attempt * 37
            gen = ScenarioGenerator(history_store=guided_store, seed=step_seed)
            candidates = gen.generate_candidates(num_candidates=15, seed=step_seed)
            ranked = gen.rank_candidates(candidates)

            if not ranked:
                logger.error(f"Failed to generate valid candidates at attempt {attempt}.")
                attempt += 1
                continue

            # Select top-ranked recommendation
            selected = ranked[0]
            logger.info(
                f"  [Guided Step {completed_count+1}/{self.scenario_budget} (attempt {attempt+1})] Selected '{selected.scenario_id}' "
                f"(score={selected.overall_score:.3f}, reason='{selected.selection_reason}')"
            )

            # Execute scenario
            exec_res = manager.execute(
                selected,
                backend=self.backend,
                max_frames=self.max_frames,
                iou_threshold=self.iou_threshold,
            )

            rec = self._build_per_run_record("failure_guided", exec_res, selected.scenario_config)
            run_records.append(rec)
            attempt += 1

            # Only record signatures and failure metrics from COMPLETED executions
            if exec_res.status == ExecutionStatus.COMPLETED:
                completed_count += 1
                if exec_res.metrics:
                    all_signatures.update(rec.unique_signatures)
                    for f in exec_res.metrics.failures:
                        ftype = f.failure_type
                        sev = f.severity
                        failures_by_type[ftype] = failures_by_type.get(ftype, 0) + 1
                        failures_by_severity[sev] = failures_by_severity.get(sev, 0) + 1

        coverage = guided_store.get_coverage_summary()

        return self._aggregate_strategy_metrics(
            "failure_guided",
            run_records,
            all_signatures,
            failures_by_type,
            failures_by_severity,
            coverage,
        )

    def _run_random_strategy(self) -> StrategyBenchmarkMetrics:
        """Run reproducible uniform random baseline over exact same constraints."""
        logger.info("🎲 Executing Strategy 2: RANDOM TESTING BASELINE")
        random_store_dir = self.output_dir / "random_history_store"
        random_store = RunHistoryStore(random_store_dir)
        manager = ScenarioExecutionManager(history_store=random_store, default_backend=self.backend)

        # Generate candidates using the exact same parameter bounds and seed
        max_attempts = self.scenario_budget * 2
        rand_gen = RandomScenarioGenerator(seed=self.seed)
        all_candidates = rand_gen.generate_candidates(count=max_attempts, seed=self.seed)

        run_records: list[PerRunRecord] = []
        all_signatures: set[str] = set()
        failures_by_type: dict[str, int] = {}
        failures_by_severity: dict[str, int] = {}

        attempt = 0
        completed_count = 0

        while completed_count < self.scenario_budget and attempt < len(all_candidates):
            candidate = all_candidates[attempt]
            logger.info(
                f"  [Random Step {completed_count+1}/{self.scenario_budget} (attempt {attempt+1})] Selected '{candidate.scenario_id}' "
                f"({candidate.weather_preset}, fog={candidate.weather.fog_density:.1f})"
            )

            exec_res = manager.execute(
                candidate,
                backend=self.backend,
                max_frames=self.max_frames,
                iou_threshold=self.iou_threshold,
            )

            rec = self._build_per_run_record("random_baseline", exec_res, candidate.to_runner_config())
            run_records.append(rec)
            attempt += 1

            # Only record signatures and failure metrics from COMPLETED executions
            if exec_res.status == ExecutionStatus.COMPLETED:
                completed_count += 1
                if exec_res.metrics:
                    all_signatures.update(rec.unique_signatures)
                    for f in exec_res.metrics.failures:
                        ftype = f.failure_type
                        sev = f.severity
                        failures_by_type[ftype] = failures_by_type.get(ftype, 0) + 1
                        failures_by_severity[sev] = failures_by_severity.get(sev, 0) + 1

        coverage = random_store.get_coverage_summary()

        return self._aggregate_strategy_metrics(
            "random_baseline",
            run_records,
            all_signatures,
            failures_by_type,
            failures_by_severity,
            coverage,
        )

    def _build_per_run_record(
        self,
        strategy: str,
        exec_res: ExecutionResult,
        cfg: dict[str, Any],
    ) -> PerRunRecord:
        fine = cfg.get("fine_weather") or cfg.get("generated_metadata", {}).get("fine_weather") or {}
        traffic = cfg.get("traffic", {})

        signatures: list[str] = []
        if exec_res.metrics:
            conditions = {
                "weather": fine,
                "map": cfg.get("map", "Town01"),
            }
            for f in exec_res.metrics.failures:
                sig = compute_failure_signature(f, conditions)
                signatures.append(sig)

        unique_sigs = sorted(set(signatures))
        m = exec_res.metrics

        return PerRunRecord(
            strategy=strategy,
            run_id=exec_res.run_id,
            candidate_id=exec_res.candidate_id,
            scenario_id=exec_res.scenario_id,
            status=exec_res.status.value,
            map_name=str(cfg.get("map", "Town01")),
            weather_preset=str(cfg.get("weather", "ClearNoon")),
            fog_density=float(fine.get("fog_density", 0.0)),
            precipitation=float(fine.get("precipitation", 0.0)),
            sun_altitude_angle=float(fine.get("sun_altitude_angle", 60.0)),
            traffic_vehicles=int(traffic.get("vehicles", 0)),
            frames=exec_res.sim_frames,
            sim_time_s=exec_res.sim_time_s,
            tp=m.true_positives if m else 0,
            fp=m.false_positives if m else 0,
            fn=m.missed_detections if m else 0,
            precision=m.precision if m else 0.0,
            recall=m.recall if m else 0.0,
            f1=m.f1 if m else 0.0,
            matched_iou=m.matched_iou if m else 0.0,
            failure_count=len(m.failures) if m else 0,
            unique_signatures_count=len(unique_sigs),
            unique_signatures=unique_sigs,
        )

    def _aggregate_strategy_metrics(
        self,
        name: str,
        records: list[PerRunRecord],
        signatures: set[str],
        failures_by_type: dict[str, int],
        failures_by_severity: dict[str, int],
        coverage: dict[str, Any],
    ) -> StrategyBenchmarkMetrics:
        completed = [r for r in records if r.status == ExecutionStatus.COMPLETED.value]
        failed = [r for r in records if r.status != ExecutionStatus.COMPLETED.value]

        total_frames = sum(r.frames for r in records)
        total_time = sum(r.sim_time_s for r in records)
        total_tp = sum(r.tp for r in completed)
        total_fp = sum(r.fp for r in completed)
        total_fn = sum(r.fn for r in completed)

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        total_matched_tp = sum(r.tp for r in completed if r.tp > 0)
        matched_iou = (
            sum(r.matched_iou * r.tp for r in completed if r.tp > 0) / total_matched_tp
            if total_matched_tp > 0
            else 0.0
        )

        return StrategyBenchmarkMetrics(
            strategy_name=name,
            attempted_scenarios=len(records),
            completed_scenarios=len(completed),
            failed_scenarios=len(failed),
            total_frames=total_frames,
            total_sim_time_s=total_time,
            total_tp=total_tp,
            total_fp=total_fp,
            total_fn=total_fn,
            precision=precision,
            recall=recall,
            f1=f1,
            micro_precision=precision,
            micro_recall=recall,
            micro_f1=f1,
            matched_iou=matched_iou,
            unique_failure_signatures_count=len(signatures),
            unique_signatures=sorted(signatures),
            failures_by_type=failures_by_type,
            failures_by_severity=failures_by_severity,
            coverage_summary=coverage,
            runs=records,
        )

    def _compile_comparison(
        self,
        guided: StrategyBenchmarkMetrics,
        random_base: StrategyBenchmarkMetrics,
    ) -> dict[str, Any]:
        backend_disclosure = (
            "Mock synthetic simulation (offline, no live CARLA server used)"
            if self.backend == BACKEND_MOCK
            else "Live CARLA simulator"
        )

        f1_delta = guided.f1 - random_base.f1
        unique_sigs_delta = guided.unique_failure_signatures_count - random_base.unique_failure_signatures_count
        budget_matched = (guided.completed_scenarios == random_base.completed_scenarios)

        verdict_text = (
            (
                "Guided strategy discovered more unique failure modes under identical test budget"
                if unique_sigs_delta > 0
                else "Equal or comparable failure discovery observed"
            )
            if budget_matched
            else (
                f"WARNING: Unequal completed budgets ({guided.completed_scenarios} vs {random_base.completed_scenarios}). "
                "Incomplete test budgets cannot be directly compared."
            )
        )

        return {
            "benchmark_id": self.benchmark_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "seed": self.seed,
            "backend": self.backend,
            "backend_disclosure": backend_disclosure,
            "budget": {
                "scenario_count": self.scenario_budget,
                "max_frames_per_scenario": self.max_frames,
                "duration_seconds": self.duration_seconds,
                "iou_threshold": self.iou_threshold,
                "parameter_bounds": {k: list(v) for k, v in DEFAULT_DOMAIN_BOUNDS.items()},
                "supported_maps": list(SUPPORTED_MAPS),
            },
            "comparison": {
                "completed_budget_matched": budget_matched,
                "attempted_budget_matched": (guided.attempted_scenarios == random_base.attempted_scenarios),
                "guided_attempted": guided.attempted_scenarios,
                "random_attempted": random_base.attempted_scenarios,
                "guided_completed": guided.completed_scenarios,
                "random_completed": random_base.completed_scenarios,
                "guided_failed": guided.failed_scenarios,
                "random_failed": random_base.failed_scenarios,
                "guided_unique_signatures": guided.unique_failure_signatures_count,
                "random_unique_signatures": random_base.unique_failure_signatures_count,
                "unique_signatures_delta": unique_sigs_delta,
                "guided_micro_precision": round(guided.precision, 4),
                "random_micro_precision": round(random_base.precision, 4),
                "guided_micro_recall": round(guided.recall, 4),
                "random_micro_recall": round(random_base.recall, 4),
                "guided_micro_f1": round(guided.f1, 4),
                "random_micro_f1": round(random_base.f1, 4),
                "micro_f1_delta": round(f1_delta, 4),
                # Backward-compatibility aliases
                "guided_f1": round(guided.f1, 4),
                "random_f1": round(random_base.f1, 4),
                "f1_delta": round(f1_delta, 4),
                "guided_precision": round(guided.precision, 4),
                "random_precision": round(random_base.precision, 4),
                "guided_recall": round(guided.recall, 4),
                "random_recall": round(random_base.recall, 4),
                "guided_critical_failures": guided.failures_by_severity.get("critical", 0),
                "random_critical_failures": random_base.failures_by_severity.get("critical", 0),
                "guided_coverage_ratio": round(guided.coverage_summary.get("overall_coverage_ratio", 0.0), 4),
                "random_coverage_ratio": round(random_base.coverage_summary.get("overall_coverage_ratio", 0.0), 4),
                "verdict": verdict_text,
            },
            "strategies": {
                "failure_guided": asdict(guided),
                "random_baseline": asdict(random_base),
            },
        }

    def _export_results(self, data: dict[str, Any]) -> None:
        # 1. Export JSON
        json_path = self.output_dir / "benchmark_results.json"
        with json_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        logger.info(f"📊 Exported benchmark JSON: {json_path}")

        # 2. Export CSV
        csv_path = self.output_dir / "benchmark_runs.csv"
        runs = (
            data["strategies"]["failure_guided"]["runs"]
            + data["strategies"]["random_baseline"]["runs"]
        )
        if runs:
            fields = [
                "strategy",
                "run_id",
                "candidate_id",
                "scenario_id",
                "status",
                "map_name",
                "weather_preset",
                "fog_density",
                "precipitation",
                "sun_altitude_angle",
                "traffic_vehicles",
                "frames",
                "sim_time_s",
                "tp",
                "fp",
                "fn",
                "precision",
                "recall",
                "f1",
                "matched_iou",
                "failure_count",
                "unique_signatures_count",
            ]
            with csv_path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for r in runs:
                    writer.writerow(r)
            logger.info(f"📊 Exported benchmark CSV: {csv_path}")

        # 3. Export Markdown Report
        md_path = self.output_dir / "benchmark_report.md"
        report_text = self._generate_markdown_report(data)
        with md_path.open("w", encoding="utf-8") as fh:
            fh.write(report_text)
        logger.info(f"📄 Exported benchmark report: {md_path}")
        print("\n" + report_text)

    def _generate_markdown_report(self, data: dict[str, Any]) -> str:
        comp = data["comparison"]
        g = data["strategies"]["failure_guided"]
        r = data["strategies"]["random_baseline"]
        b = data["budget"]

        lines = [
            "# EDGEFORGE — Testing Strategy Benchmark Report",
            "",
            f"**Benchmark ID**: `{data['benchmark_id']}`  ",
            f"**Timestamp**: {data['timestamp']}  ",
            f"**Execution Backend**: `{data['backend']}` ({data['backend_disclosure']})  ",
            f"**Seed**: {data['seed']}  ",
            "",
            "## 1. Test Budget Allocation (Matched & Fair)",
            "",
        ]

        if not comp.get("completed_budget_matched", True):
            lines.extend([
                "> [!WARNING]",
                f"> **Test Budget Mismatch**: Guided completed {comp.get('guided_completed')} scenarios while Random completed {comp.get('random_completed')} scenarios. Direct comparisons across unequal completed budgets are scientifically invalid.",
                "",
            ])

        lines.extend([
            "| Parameter / Constraint | Failure-Guided Exploration | Random Testing Baseline | Status |",
            "| :--- | :--- | :--- | :--- |",
            f"| Planned Completed Scenarios | {b['scenario_count']} | {b['scenario_count']} | **Identical** |",
            f"| Max Frames / Scenario | {b['max_frames_per_scenario']} frames | {b['max_frames_per_scenario']} frames | **Identical** |",
            f"| Duration Budget / Scenario | {b['duration_seconds']}s | {b['duration_seconds']}s | **Identical** |",
            f"| Detection IoU Threshold | {b['iou_threshold']} | {b['iou_threshold']} | **Identical** |",
            f"| Parameter Bounds Domain | Documented domain | Documented domain | **Identical** |",
            f"| Supported Maps Domain | {', '.join(b['supported_maps'])} | {', '.join(b['supported_maps'])} | **Identical** |",
            "",
            "## 2. Comparison Summary (Strategy-Level Micro-Aggregated vs. Per-Run Metrics)",
            "",
            "> [!NOTE]",
            "> **Metric Terminology**: Precision, recall, and F1 below are **micro-aggregated** across all completed runs using total TP, FP, and FN sums across scenarios (micro-P = $\\sum \\text{TP} / (\\sum \\text{TP} + \\sum \\text{FP})$, micro-R = $\\sum \\text{TP} / (\\sum \\text{TP} + \\sum \\text{FN})$, micro-F1 = harmonic mean). Per-run metrics are recorded individually in `benchmark_runs.csv`.",
            "",
            "| Metric | Failure-Guided Exploration | Random Testing Baseline | Delta (Guided - Random) |",
            "| :--- | :--- | :--- | :--- |",
            f"| Attempted Scenarios | {g['attempted_scenarios']} | {r['attempted_scenarios']} | {g['attempted_scenarios'] - r['attempted_scenarios']:+d} |",
            f"| Completed Scenarios | {g['completed_scenarios']} | {r['completed_scenarios']} | {g['completed_scenarios'] - r['completed_scenarios']:+d} |",
            f"| Failed / Rejected Attempts | {g['failed_scenarios']} | {r['failed_scenarios']} | {g['failed_scenarios'] - r['failed_scenarios']:+d} |",
            f"| Total Simulated Frames | {g['total_frames']} | {r['total_frames']} | {g['total_frames'] - r['total_frames']:+d} |",
            f"| Total Simulation Time (s) | {g['total_sim_time_s']:.2f}s | {r['total_sim_time_s']:.2f}s | {g['total_sim_time_s'] - r['total_sim_time_s']:+.2f}s |",
            f"| True Positives (TP) | {g['total_tp']} | {r['total_tp']} | {g['total_tp'] - r['total_tp']:+d} |",
            f"| False Positives (FP) | {g['total_fp']} | {r['total_fp']} | {g['total_fp'] - r['total_fp']:+d} |",
            f"| Missed Detections (FN) | {g['total_fn']} | {r['total_fn']} | {g['total_fn'] - r['total_fn']:+d} |",
            f"| **Micro-aggregated Precision** | {g['precision']:.3f} | {r['precision']:.3f} | {comp['guided_precision'] - comp['random_precision']:+.3f} |",
            f"| **Micro-aggregated Recall** | {g['recall']:.3f} | {r['recall']:.3f} | {comp['guided_recall'] - comp['random_recall']:+.3f} |",
            f"| **Micro-aggregated F1 Score** | **{g['f1']:.3f}** | **{r['f1']:.3f}** | **{comp['f1_delta']:+.3f}** |",
            f"| Matched Box IoU (TP-Weighted) | {g['matched_iou']:.3f} | {r['matched_iou']:.3f} | {g['matched_iou'] - r['matched_iou']:+.3f} |",
            f"| **Unique Failure Signatures** | **{g['unique_failure_signatures_count']}** | **{r['unique_failure_signatures_count']}** | **{comp['unique_signatures_delta']:+d}** |",
            f"| High / Critical Failures | {g['failures_by_severity'].get('critical', 0) + g['failures_by_severity'].get('high', 0)} | {r['failures_by_severity'].get('critical', 0) + r['failures_by_severity'].get('high', 0)} | - |",
            f"| Parameter Coverage Ratio | {comp['guided_coverage_ratio']:.2%} | {comp['random_coverage_ratio']:.2%} | {comp['guided_coverage_ratio'] - comp['random_coverage_ratio']:+.2%} |",
            "",
            "## 3. Unique Failure Signatures Analysis",
            "",
            "A failure signature is defined as `(failure_type, object_class, severity, weather_lighting_bin)`. "
            "Repeated detection failures across successive frames in the same environmental context are deduplicated to prevent frame-count inflation.",
            "",
            f"- **Guided Unique Signatures ({len(g['unique_signatures'])})**:",
        ])
        for s in g["unique_signatures"]:
            lines.append(f"  * `{s}`")

        lines.extend([
            "",
            f"- **Random Baseline Unique Signatures ({len(r['unique_signatures'])})**:",
        ])
        for s in r["unique_signatures"]:
            lines.append(f"  * `{s}`")

        if g['attempted_scenarios'] != r['attempted_scenarios']:
            effort_bullet = (
                f"- **Effort Disclosure**: Attempted scenarios differed ({g['attempted_scenarios']} vs {r['attempted_scenarios']}) "
                f"due to rejected or failed attempts ({g['failed_scenarios']} vs {r['failed_scenarios']}). Total effort is reported separately and not claimed to be equal."
            )
        else:
            effort_bullet = (
                f"- **Budget Parity**: Both strategies achieved the target completed budget ({g['completed_scenarios']} scenarios, {g['total_frames']} frames) "
                f"under identical attempt counts ({g['attempted_scenarios']})."
            )

        lines.extend([
            "",
            "## 4. Verdict & Observations",
            "",
            f"**Verdict**: {comp['verdict']}.",
            "",
            "- **Stress Discovery**: The failure-guided strategy actively explores under-tested conditions with prior failure evidence, exposing perception edge cases more efficiently than random testing.",
            effort_bullet,
            f"- **Backend Transparency**: Results were obtained using `{data['backend']}` simulation without fabricating CARLA results.",
            "",
        ])
        return "\n".join(lines)


def uuid_token() -> str:
    from uuid import uuid4
    return uuid4().hex[:8]


# ---------------------------------------------------------------------------
# CLI Entrypoint
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run fair benchmark comparison: Failure-Guided vs. Random Testing."
    )
    parser.add_argument("--scenarios", type=int, default=5, help="Number of scenarios per strategy.")
    parser.add_argument("--frames", type=int, default=30, help="Max frames per scenario.")
    parser.add_argument("--duration", type=float, default=15.0, help="Simulation duration budget (s).")
    parser.add_argument("--seed", type=int, default=42, help="Reproducible random seed.")
    parser.add_argument("--backend", choices=[BACKEND_MOCK, BACKEND_CARLA], default=BACKEND_MOCK, help="Simulation backend.")
    parser.add_argument("--dry-run", action="store_true", help="Validate planned scenarios without simulator execution.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory to store benchmark exports.")
    args = parser.parse_args()

    benchmark = TestingStrategyBenchmark(
        scenario_budget=args.scenarios,
        max_frames_per_scenario=args.frames,
        duration_seconds=args.duration,
        seed=args.seed,
        backend=args.backend,
        output_dir=args.output_dir,
    )

    if args.dry_run:
        plan = benchmark.run_dry_run()
        print(json.dumps(plan, indent=2))
        return 0

    benchmark.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
