"""Deterministic offline tests for the Next-Best Scenario Generator (Milestone 4A).

All tests run completely offline and in temporary directories; no CARLA simulator,
Torch, YOLO models, or network connections are required.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from edgeforge.data.history import RunHistoryStore
from edgeforge.data.models import PerceptionFailureRecord
from edgeforge.scenarios.generator import (
    ScenarioCandidate,
    ScenarioGenerator,
    ScoreBreakdown,
    WeatherParameters,
    ActorConfiguration,
    generate_and_rank_scenarios,
    main as generator_main,
)


def _populate_mock_history_with_failures(store: RunHistoryStore) -> None:
    """Helper to populate store with known runs and failures for failure-guided testing."""
    # Run 1: Foggy condition failure (fog=50, precip=10) with missed detections
    f1 = PerceptionFailureRecord(
        run_id="run_hist_01",
        scenario_id="scen_fog_01",
        failure_type="missed_detection",
        severity="critical",
        object_class="car",
        frame_id=10,
        scenario_conditions={"weather": {"fog_density": 50.0, "precipitation": 10.0}},
    )
    f2 = PerceptionFailureRecord(
        run_id="run_hist_01",
        scenario_id="scen_fog_01",
        failure_type="poor_localization",
        severity="high",
        object_class="pedestrian",
        iou=0.38,
        frame_id=20,
        scenario_conditions={"weather": {"fog_density": 50.0, "precipitation": 10.0}},
    )
    store.save_run(
        {
            "run_id": "run_hist_01",
            "scenario_id": "scen_fog_01",
            "frames_processed": 50,
            "true_positives": 30,
            "false_positives": 5,
            "missed_detections": 15,
            "precision": 30 / 35,
            "recall": 30 / 45,
            "f1": 0.75,
            "matched_iou": 0.65,
            "scenario_conditions": {
                "map": "Town01",
                "weather": {"fog_density": 50.0, "precipitation": 10.0, "sun_altitude_angle": 45.0},
                "actor_configuration": {"target_count": 2},
            },
        },
        failures=[f1, f2],
    )

    # Run 2: Clear noon run (fog=0, precip=0) with 100% precision and no failures
    store.save_run(
        {
            "run_id": "run_hist_02",
            "scenario_id": "scen_clear_02",
            "frames_processed": 50,
            "true_positives": 50,
            "false_positives": 0,
            "missed_detections": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0,
            "matched_iou": 0.95,
            "scenario_conditions": {
                "map": "Town01",
                "weather": {"fog_density": 0.0, "precipitation": 0.0, "sun_altitude_angle": 60.0},
                "actor_configuration": {"target_count": 2},
            },
        },
        failures=[],
    )


def test_candidate_generation_bounds_and_validity(tmp_path: Path) -> None:
    """All generated candidates must satisfy physical and simulator parameter bounds."""
    store = RunHistoryStore(tmp_path)
    generator = ScenarioGenerator(history_store=store, seed=123)

    candidates = generator.generate_candidates(num_candidates=30)
    assert len(candidates) == 30

    for cand in candidates:
        assert 0.0 <= cand.weather.fog_density <= 100.0
        assert 0.0 <= cand.weather.precipitation <= 100.0
        assert 0.0 <= cand.weather.cloudiness <= 100.0
        assert -90.0 <= cand.weather.sun_altitude_angle <= 90.0
        assert 0.0 <= cand.weather.sun_azimuth_angle <= 360.0
        assert 0.0 <= cand.weather.wetness <= 100.0
        assert 1 <= cand.actor_config.target_count <= 5
        assert cand.map_name in ("Town01", "Town02", "Town03")
        assert len(cand.actor_config.target_types) >= 1

        # Check export schemas
        runner_cfg = cand.to_runner_config()
        assert "weather" in runner_cfg
        assert "simulation" in runner_cfg
        assert "traffic" in runner_cfg

        conds = cand.to_scenario_conditions()
        assert "weather" in conds
        assert "lighting" in conds
        assert "actor_configuration" in conds


def test_reproducibility_with_fixed_seed(tmp_path: Path) -> None:
    """Generating candidates with the same seed must produce identical results."""
    store = RunHistoryStore(tmp_path)
    gen1 = ScenarioGenerator(history_store=store, seed=42)
    gen2 = ScenarioGenerator(history_store=store, seed=42)

    cands1 = gen1.generate_candidates(num_candidates=10, seed=42)
    cands2 = gen2.generate_candidates(num_candidates=10, seed=42)

    assert len(cands1) == len(cands2)
    for c1, c2 in zip(cands1, cands2):
        assert c1.weather.fog_density == c2.weather.fog_density
        assert c1.weather.precipitation == c2.weather.precipitation
        assert c1.weather.sun_altitude_angle == c2.weather.sun_altitude_angle
        assert c1.actor_config.target_count == c2.actor_config.target_count
        assert c1.map_name == c2.map_name
        assert c1.weather_preset == c2.weather_preset


def test_scoring_from_historical_failure_evidence(tmp_path: Path) -> None:
    """Candidates in the neighborhood of previous failures receive higher failure evidence scores."""
    store = RunHistoryStore(tmp_path)
    _populate_mock_history_with_failures(store)

    generator = ScenarioGenerator(history_store=store)

    # Candidate 1: Close to Run 1 failures (fog=52.0, precip=12.0)
    cand_fail_prone = ScenarioCandidate(
        candidate_id="cand_fail_01",
        scenario_id="scen_fail_test",
        map_name="Town01",
        weather=WeatherParameters(fog_density=52.0, precipitation=12.0),
        actor_config=ActorConfiguration(target_count=2),
    )

    # Candidate 2: In clear noon conditions (fog=0.0, precip=0.0) where no failures occurred
    cand_clear = ScenarioCandidate(
        candidate_id="cand_clear_01",
        scenario_id="scen_clear_test",
        map_name="Town01",
        weather=WeatherParameters(fog_density=0.0, precipitation=0.0),
        actor_config=ActorConfiguration(target_count=2),
    )

    score_fail, break_fail, evidence_fail, _ = generator.score_candidate(
        cand_fail_prone,
        history_runs=store.list_runs(),
    )
    score_clear, break_clear, evidence_clear, _ = generator.score_candidate(
        cand_clear,
        history_runs=store.list_runs(),
    )

    # Candidate near historical failures must have high failure evidence
    assert break_fail.failure_evidence > 0.4
    assert len(evidence_fail) >= 1
    assert any(e["run_id"] == "run_hist_01" for e in evidence_fail)

    # Candidate in clear conditions has zero failure evidence
    assert break_clear.failure_evidence == 0.0
    assert len(evidence_clear) == 0

    assert score_fail > score_clear


def test_novelty_and_coverage_preferences(tmp_path: Path) -> None:
    """Candidates in completely unexplored parameter regions receive high coverage novelty scores."""
    store = RunHistoryStore(tmp_path)
    _populate_mock_history_with_failures(store)

    generator = ScenarioGenerator(history_store=store)
    runs = store.list_runs()

    # Candidate testing extreme unexplored rain & glare (fog=95.0, precip=95.0, sun_alt=2.0)
    cand_novel = ScenarioCandidate(
        candidate_id="cand_novel",
        scenario_id="scen_novel",
        map_name="Town01",
        weather=WeatherParameters(fog_density=95.0, precipitation=95.0, sun_altitude_angle=2.0),
        actor_config=ActorConfiguration(target_count=3),
    )

    # Candidate testing right on top of tested Run 1 (fog=50.0, precip=10.0, sun_alt=45.0)
    cand_tested = ScenarioCandidate(
        candidate_id="cand_tested",
        scenario_id="scen_tested",
        map_name="Town01",
        weather=WeatherParameters(fog_density=50.0, precipitation=10.0, sun_altitude_angle=45.0),
        actor_config=ActorConfiguration(target_count=2),
    )

    _, break_novel, _, note_novel = generator.score_candidate(cand_novel, history_runs=runs)
    _, break_tested, _, note_tested = generator.score_candidate(cand_tested, history_runs=runs)

    assert break_novel.coverage_novelty > break_tested.coverage_novelty
    assert "away from tested points" in note_novel or "low-angle glare" in note_novel


def test_duplicate_rejection(tmp_path: Path) -> None:
    """Duplicate candidates matching prior runs or earlier candidates in a batch are pruned."""
    store = RunHistoryStore(tmp_path)
    _populate_mock_history_with_failures(store)

    generator = ScenarioGenerator(history_store=store)

    # Candidate identical to run_hist_01
    cand_dup_history = ScenarioCandidate(
        candidate_id="cand_dup_hist",
        scenario_id="scen_dup_hist",
        map_name="Town01",
        weather=WeatherParameters(fog_density=50.0, precipitation=10.0, sun_altitude_angle=45.0),
        actor_config=ActorConfiguration(target_count=2),
    )

    # Distinct candidate
    cand_distinct = ScenarioCandidate(
        candidate_id="cand_distinct",
        scenario_id="scen_distinct",
        map_name="Town03",
        weather=WeatherParameters(fog_density=80.0, precipitation=60.0),
        actor_config=ActorConfiguration(target_count=3),
    )

    # Duplicate of cand_distinct
    cand_dup_batch = ScenarioCandidate(
        candidate_id="cand_dup_batch",
        scenario_id="scen_dup_batch",
        map_name="Town03",
        weather=WeatherParameters(fog_density=80.5, precipitation=60.2),
        actor_config=ActorConfiguration(target_count=3),
    )

    # With allow_duplicates=False, duplicate should be omitted
    ranked = generator.rank_candidates(
        [cand_dup_history, cand_distinct, cand_dup_batch],
        allow_duplicates=False,
    )
    ranked_ids = [r.candidate_id for r in ranked]

    assert "cand_distinct" in ranked_ids
    assert "cand_dup_hist" not in ranked_ids
    assert "cand_dup_batch" not in ranked_ids

    # With allow_duplicates=True, all candidates are included
    ranked_all = generator.rank_candidates(
        [cand_dup_history, cand_distinct, cand_dup_batch],
        allow_duplicates=True,
    )
    assert len(ranked_all) == 3


def test_empty_history_and_cold_start_behavior(tmp_path: Path) -> None:
    """When the historical store is empty, generator operates in explicit cold-start mode."""
    empty_store = RunHistoryStore(tmp_path / "empty_store")
    generator = ScenarioGenerator(history_store=empty_store, seed=99)

    ranked = generator.generate_and_rank(num_candidates=5, seed=99)
    assert len(ranked) == 5

    # All recommendations must be marked as cold-start
    for r in ranked:
        assert r.cold_start is True
        assert r.score_breakdown.failure_evidence == 0.0
        assert r.score_breakdown.condition_similarity == 0.0
        assert r.score_breakdown.coverage_novelty > 0.0
        assert "cold-start" in r.selection_reason.lower()
        assert r.historical_evidence == []


def test_ranking_explanations_and_run_references(tmp_path: Path) -> None:
    """Every recommendation provides a selection reason referencing prior run IDs when available."""
    store = RunHistoryStore(tmp_path)
    _populate_mock_history_with_failures(store)

    generator = ScenarioGenerator(history_store=store)

    cand = ScenarioCandidate(
        candidate_id="cand_audit_01",
        scenario_id="scen_audit_01",
        map_name="Town01",
        weather=WeatherParameters(fog_density=51.0, precipitation=11.0),
        actor_config=ActorConfiguration(target_count=2),
    )

    ranked = generator.rank_candidates([cand])
    assert len(ranked) == 1
    top = ranked[0]

    assert top.cold_start is False
    assert "run_hist_01" in top.selection_reason
    assert "missed_detection" in top.selection_reason
    assert len(top.historical_evidence) >= 1
    evidence_item = top.historical_evidence[0]
    assert evidence_item["run_id"] == "run_hist_01"
    assert evidence_item["failure_type"] == "missed_detection"
    assert evidence_item["severity"] == "critical"


def test_json_export_and_reload(tmp_path: Path) -> None:
    """Ranked recommendations can be exported to JSON and reloaded without loss of data."""
    store = RunHistoryStore(tmp_path / "hist")
    _populate_mock_history_with_failures(store)

    generator = ScenarioGenerator(history_store=store, seed=77)
    ranked = generator.generate_and_rank(num_candidates=4, seed=77)

    out_file = tmp_path / "recommendations.json"
    saved_path = generator.save_recommendations(ranked, out_file)
    assert saved_path.is_file()

    # Verify JSON structure
    doc = json.loads(saved_path.read_text(encoding="utf-8"))
    assert doc["generator_version"] == "1.0"
    assert doc["total_ranked"] == len(ranked)
    assert len(doc["recommendations"]) == len(ranked)

    # Reload via static method
    loaded = ScenarioGenerator.load_recommendations(out_file)
    assert len(loaded) == len(ranked)
    for orig, reloaded in zip(ranked, loaded):
        assert orig.candidate_id == reloaded.candidate_id
        assert orig.overall_score == pytest.approx(reloaded.overall_score)
        assert orig.selection_reason == reloaded.selection_reason
        assert orig.scenario_conditions["map"] == reloaded.scenario_conditions["map"]


def test_unsupported_parameters_flagged_and_penalized(tmp_path: Path) -> None:
    """Unsupported parameters (e.g. cut-in, occlusion mesh) are flagged and not treated as supported."""
    store = RunHistoryStore(tmp_path)
    generator = ScenarioGenerator(history_store=store)

    candidates = generator.generate_candidates(
        num_candidates=2,
        seed=10,
        unsupported_parameters=["adversarial_cut_in", "dynamic_occlusion_mesh"],
    )

    for cand in candidates:
        assert "adversarial_cut_in" in cand.unsupported_features
        assert "dynamic_occlusion_mesh" in cand.unsupported_features

    ranked = generator.rank_candidates(candidates)
    assert len(ranked) == 2
    for r in ranked:
        assert "adversarial_cut_in" in r.unsupported_features
        assert "unsupported" in r.selection_reason.lower()
        # Feasibility penalized for unsupported features
        assert r.score_breakdown.feasibility < 1.0


def test_invalid_candidates_rejected_safely(tmp_path: Path) -> None:
    """Candidates with invalid bounds or maps receive score 0.0 with feasibility=0.0."""
    store = RunHistoryStore(tmp_path)
    generator = ScenarioGenerator(history_store=store)

    # Candidate with out-of-bounds fog density
    invalid_cand = ScenarioCandidate(
        candidate_id="cand_invalid",
        scenario_id="scen_invalid",
        map_name="Town01",
        weather=WeatherParameters(fog_density=100.0),  # Valid bound, but we manually alter below
    )
    # Manually bypass Pydantic model validation to simulate corrupted in-memory object
    object.__setattr__(invalid_cand.weather, "fog_density", 250.0)

    score, breakdown, _, note = generator.score_candidate(invalid_cand, history_runs=[])
    assert score == 0.0
    assert breakdown.feasibility == 0.0
    assert "rejected" in note.lower()


def test_convenience_function(tmp_path: Path) -> None:
    """generate_and_rank_scenarios top-level function works as expected."""
    hist_dir = tmp_path / "hist"
    out_file = tmp_path / "out_recommendations.json"

    ranked = generate_and_rank_scenarios(
        num_candidates=3,
        history_dir=hist_dir,
        seed=111,
        output_path=out_file,
    )
    assert len(ranked) == 3
    assert out_file.is_file()


def test_cli_execution(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """CLI utility executes candidate generation, ranking, and output saving."""
    hist_dir = tmp_path / "hist"
    store = RunHistoryStore(hist_dir)
    _populate_mock_history_with_failures(store)

    out_file = tmp_path / "cli_recommendations.json"

    with patch(
        "sys.argv",
        [
            "generator",
            "--history-dir",
            str(hist_dir),
            "--candidates",
            "5",
            "--top-k",
            "2",
            "--seed",
            "42",
            "--output",
            str(out_file),
        ],
    ):
        ret = generator_main()
        assert ret == 0

    assert out_file.is_file()
    captured = capsys.readouterr().out
    assert "Next-Best Scenario Generator" in captured
    assert "Top 2 Recommendations" in captured
    assert "Score:" in captured
