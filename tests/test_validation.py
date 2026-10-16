from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

import numpy as np
import pytest

from edgeforge.data.models import DetectedObject, PerceptionFailureRecord
from edgeforge.perception.validation import (
    SUPPORTED_EVALUATION_CLASSES,
    DetectionMatch,
    FailureSeverityRules,
    GroundTruthObject,
    RunValidationMetrics,
    ValidationMetrics,
    aggregate_run_metrics,
    carla_actor_class,
    evaluate_detections,
    export_failure_report,
    export_run_report,
    extract_carla_ground_truth,
    project_carla_actor_bbox,
)
from edgeforge.simulation.validate_carla_perception import _select_target_spawn_points


@dataclass
class _Location:
    x: float
    y: float
    z: float


@dataclass
class _Transform:
    location: _Location
    forward: _Location

    def get_forward_vector(self):
        return self.forward


class _CameraTransform:
    def get_inverse_matrix(self):
        return np.eye(4)


class _BoundingBox:
    def __init__(self, vertices):
        self.vertices = vertices

    def get_world_vertices(self, _):
        return self.vertices


class _Actor:
    def __init__(self, actor_id, type_id, vertices=()):
        self.id = actor_id
        self.type_id = type_id
        self.bounding_box = _BoundingBox(vertices)
        self.transform = object()

    def get_transform(self):
        return self.transform


def _box_vertices(x_min, x_max, y_min=-1, y_max=1, z_min=-1, z_max=1):
    return [
        _Location(x_min, y_min, z_min),
        _Location(x_min, y_max, z_min),
        _Location(x_max, y_max, z_min),
        _Location(x_max, y_min, z_min),
        _Location(x_min, y_min, z_max),
        _Location(x_min, y_max, z_max),
        _Location(x_max, y_max, z_max),
        _Location(x_max, y_min, z_max),
    ]


@pytest.mark.parametrize(
    ("type_id", "expected"),
    [
        ("walker.pedestrian.0001", "pedestrian"),
        ("vehicle.tesla.model3", "car"),
        ("vehicle.carlamotors.carlacola", "truck"),
        ("vehicle.kawasaki.ninja", "motorcycle"),
        ("traffic.traffic_light", "traffic_light"),
        ("static.prop.streetbarrier", None),
    ],
)
def test_carla_actor_class_mapping(type_id, expected):
    assert carla_actor_class(_Actor(1, type_id)) == expected


def test_project_actor_bbox_in_front_of_camera():
    actor = _Actor(12, "vehicle.tesla.model3", _box_vertices(9, 11))

    bbox = project_carla_actor_bbox(actor, _CameraTransform(), 100, 100, 90)

    assert bbox == pytest.approx((44.44, 44.44, 55.56, 55.56), abs=0.02)


def test_project_actor_bbox_clips_near_plane_and_ignores_behind_camera():
    camera = _CameraTransform()
    crossing_actor = _Actor(12, "vehicle.tesla.model3", _box_vertices(-1, 1))
    behind_actor = _Actor(13, "vehicle.tesla.model3", _box_vertices(-3, -1))

    clipped = project_carla_actor_bbox(crossing_actor, camera, 100, 100, 90)

    assert clipped is not None
    assert clipped[0] == 0
    assert clipped[2] == 100
    assert project_carla_actor_bbox(behind_actor, camera, 100, 100, 90) is None


def test_extract_ground_truth_filters_ego_unsupported_and_unselected_actors():
    ego = _Actor(1, "vehicle.tesla.model3")
    target = _Actor(2, "vehicle.tesla.model3", _box_vertices(9, 11))
    unselected = _Actor(3, "walker.pedestrian.0001", _box_vertices(9, 11))
    unsupported = _Actor(4, "static.prop.streetbarrier", _box_vertices(9, 11))

    truth = extract_carla_ground_truth(
        [ego, target, unselected, unsupported],
        ego,
        _CameraTransform(),
        100,
        100,
        90,
        actor_ids={2, 4},
    )

    assert [(item.actor_id, item.object_type) for item in truth] == [(2, "car")]


def test_evaluate_detections_matches_by_class_and_only_once():
    predictions = [
        {"bbox": [0, 0, 10, 10], "object_type": "car"},
        {"bbox": [0, 0, 10, 10], "object_type": "car"},
        {"bbox": [20, 20, 30, 30], "object_type": "person"},
    ]
    truth = [
        GroundTruthObject(101, "car", (0, 0, 10, 10)),
        GroundTruthObject(102, "pedestrian", (20, 20, 30, 30)),
    ]

    metrics = evaluate_detections(predictions, truth, iou_threshold=0.5)

    assert metrics.true_positives == 1
    assert metrics.false_positive_indices == (1, 2)
    assert metrics.missed_ground_truth_indices == (1,)
    assert metrics.precision == pytest.approx(1 / 3)
    assert metrics.recall == pytest.approx(1 / 2)
    assert metrics.f1 == pytest.approx(0.4)


def test_evaluate_detections_handles_empty_inputs_and_no_matches():
    empty = evaluate_detections([], [])
    no_matches = evaluate_detections(
        [{"bbox": [0, 0, 10, 10], "object_type": "car"}],
        [GroundTruthObject(1, "truck", (0, 0, 10, 10))],
    )

    assert (empty.precision, empty.recall, empty.f1) == (0.0, 0.0, 0.0)
    assert no_matches.false_positives == 1
    assert no_matches.missed_detections == 1
    assert {failure.failure_type for failure in no_matches.failure_records} == {
        "false_positive",
        "missed_detection",
    }


@pytest.mark.parametrize(
    ("prediction", "truth"),
    [
        (
            [{"bbox": [0, 0, float("nan"), 1], "object_type": "car"}],
            [],
        ),
        ([{"bbox": [0, 0, 0, 1], "object_type": "car"}], []),
        ([{"object_type": "car"}], []),
        ([], [GroundTruthObject(1, "car", (0, 0, 0, 1))]),
    ],
)
def test_evaluate_detections_records_invalid_boxes_without_crashing(prediction, truth):
    metrics = evaluate_detections(prediction, truth, frame_id=10)

    assert metrics.false_positives == len(prediction)
    assert metrics.missed_detections == len(truth)
    assert [failure.failure_type for failure in metrics.failure_records] == [
        "invalid_box"
    ] * (len(prediction) + len(truth))
    assert all(failure.frame_id == 10 for failure in metrics.failure_records)


def test_evaluate_detections_rejects_invalid_iou_threshold():
    with pytest.raises(ValueError):
        evaluate_detections([], [], float("nan"))


def test_projection_rejects_invalid_camera_parameters():
    actor = _Actor(1, "vehicle.tesla.model3", _box_vertices(9, 11))

    with pytest.raises(ValueError, match="dimensions"):
        project_carla_actor_bbox(actor, _CameraTransform(), 0, 100, 90)
    with pytest.raises(ValueError, match="FOV"):
        project_carla_actor_bbox(actor, _CameraTransform(), 100, 100, 180)


def test_target_spawn_selection_prioritizes_nearby_forward_spawn_points():
    ego = _Transform(_Location(0, 0, 0), _Location(1, 0, 0))
    spawn_points = [
        _Transform(_Location(0, 0, 0), _Location(1, 0, 0)),
        _Transform(_Location(20, 0, 0), _Location(1, 0, 0)),
        _Transform(_Location(10, 1, 0), _Location(1, 0, 0)),
        _Transform(_Location(-10, 0, 0), _Location(1, 0, 0)),
        _Transform(_Location(15, 20, 0), _Location(1, 0, 0)),
    ]

    selected = _select_target_spawn_points(ego, spawn_points, ego_spawn_index=0)

    assert [index for index, _ in selected] == [2, 1]


def test_failure_classification_includes_poor_localization_and_preserves_metrics():
    prediction = {
        "bbox": [4, 0, 14, 10],
        "object_type": "car",
        "confidence": 0.8,
    }
    truth = GroundTruthObject(55, "car", (0, 0, 10, 10))

    metrics = evaluate_detections(
        [prediction],
        [truth],
        iou_threshold=0.5,
        scenario_conditions={"weather": {"rain": 50}},
        frame_id=123,
        scenario_id="rain-test",
    )

    assert (metrics.true_positives, metrics.false_positives, metrics.missed_detections) == (
        0,
        1,
        1,
    )
    assert [failure.failure_type for failure in metrics.failure_records] == [
        "poor_localization"
    ]
    failure = metrics.failure_records[0]
    assert failure.object_class == "car"
    assert failure.confidence == 0.8
    assert failure.predicted_bbox == prediction["bbox"]
    assert failure.ground_truth_bbox == list(truth.bbox)
    assert failure.iou == pytest.approx(6 / 14)
    assert failure.severity == "high"
    assert failure.scenario_conditions == {"weather": {"rain": 50}}
    assert (failure.frame_id, failure.scenario_id, failure.actor_id) == (
        123,
        "rain-test",
        55,
    )


def test_low_confidence_and_confidence_degradation_require_valid_baseline():
    prediction = DetectedObject(
        object_type="car",
        confidence=0.2,
        bbox=[0, 0, 10, 10],
        timestamp=datetime.now(timezone.utc),
    )
    truth = [GroundTruthObject(9, "car", (0, 0, 10, 10))]

    with_baseline = evaluate_detections(
        [prediction],
        truth,
        baseline_confidence={"car": 0.8},
    )
    without_baseline = evaluate_detections([prediction], truth)

    assert {failure.failure_type for failure in with_baseline.failure_records} == {
        "low_confidence",
        "confidence_degradation",
    }
    degradation = next(
        failure
        for failure in with_baseline.failure_records
        if failure.failure_type == "confidence_degradation"
    )
    assert degradation.confidence == 0.2
    assert degradation.baseline_confidence == 0.8
    assert "confidence_degradation" not in {
        failure.failure_type for failure in without_baseline.failure_records
    }


def test_default_low_confidence_threshold_flags_near_threshold_detections():
    metrics = evaluate_detections(
        [{"bbox": [0, 0, 10, 10], "object_type": "car", "confidence": 0.55}],
        [],
    )

    low_confidence = next(
        failure
        for failure in metrics.failure_records
        if failure.failure_type == "low_confidence"
    )
    assert low_confidence.severity == "medium"


def test_configurable_severity_and_missing_metadata_are_safe():
    rules = FailureSeverityRules(
        low_confidence_threshold=0.6,
        confidence_degradation_margin=0.25,
        severity_by_type={"false_positive": "critical"},
    )
    metrics = evaluate_detections(
        [{"bbox": [0, 0, 5, 5], "object_type": "unknown", "confidence": 0.9}],
        [],
        severity_rules=rules,
    )

    assert metrics.failure_records[0].failure_type == "false_positive"
    assert metrics.failure_records[0].severity == "critical"
    assert metrics.failure_records[0].scenario_conditions == {}
    assert metrics.failure_records[0].scenario_id is None
    assert metrics.failure_records[0].frame_id is None


def test_failure_severity_rules_reject_invalid_configuration():
    with pytest.raises(ValueError, match="Unknown failure types"):
        FailureSeverityRules(severity_by_type={"typo": "high"})
    with pytest.raises(ValueError, match="Unknown failure severities"):
        FailureSeverityRules(severity_by_type={"false_positive": "urgent"})
    with pytest.raises(ValueError, match="low_confidence_threshold"):
        FailureSeverityRules(low_confidence_threshold=1.5)


def test_perception_pipeline_objects_remain_compatible_with_validation():
    detection = DetectedObject(
        object_id="track-3",
        object_type="pedestrian",
        confidence=0.95,
        bbox=[1, 2, 10, 20],
        distance=12.0,
        relative_speed=-1.5,
        timestamp=datetime.now(timezone.utc),
    )
    truth = GroundTruthObject(3, "pedestrian", (1, 2, 10, 20))

    metrics = evaluate_detections([detection], [truth])

    assert metrics.true_positives == 1
    assert metrics.failure_records == ()


@pytest.mark.parametrize(
    ("suffix", "report_format"),
    [(".json", "json"), (".jsonl", "jsonl")],
)
def test_failure_report_exports_json_and_jsonl(tmp_path, suffix, report_format):
    failure = PerceptionFailureRecord(
        failure_type="missed_detection",
        object_class="pedestrian",
        ground_truth_bbox=[1, 2, 3, 4],
        severity="high",
        frame_id=7,
    )
    destination = tmp_path / f"failures{suffix}"

    result = export_failure_report([failure], destination, format=report_format)

    assert result == destination
    content = destination.read_text(encoding="utf-8")
    if report_format == "json":
        assert json.loads(content)[0]["failure_type"] == "missed_detection"
    else:
        assert json.loads(content)["frame_id"] == 7


def test_matched_box_iou_computation():
    """Verify matched-box IoU calculation for single, multiple, and zero matches."""
    # Two matches: one with IoU 1.0 (0-10 vs 0-10), one with IoU 0.6 (0-10 vs 2-10 -> 8/12 = 0.6667)
    predictions = [
        {"bbox": [0, 0, 10, 10], "object_type": "car"},
        {"bbox": [2, 0, 10, 10], "object_type": "pedestrian"},
    ]
    truth = [
        GroundTruthObject(1, "car", (0, 0, 10, 10)),
        GroundTruthObject(2, "pedestrian", (0, 0, 10, 10)),
    ]

    metrics = evaluate_detections(predictions, truth, iou_threshold=0.5)

    assert metrics.true_positives == 2
    assert len(metrics.matches) == 2
    expected_iou = (1.0 + (80.0 / 100.0)) / 2.0  # (1.0 + 0.8) / 2 = 0.9
    assert metrics.matched_iou == pytest.approx(expected_iou)
    assert metrics.matched_box_iou == pytest.approx(expected_iou)
    assert metrics.mean_iou == pytest.approx(expected_iou)

    # Zero matches -> matched_iou is 0.0
    empty_metrics = evaluate_detections([], [])
    assert empty_metrics.matched_iou == 0.0
    assert empty_metrics.matched_box_iou == 0.0


def test_duplicate_predictions_handling():
    """Duplicate predictions for the same object: higher IoU matches as TP, duplicate is FP."""
    truth = [GroundTruthObject(1, "car", (0, 0, 10, 10))]
    predictions = [
        {"bbox": [0, 0, 10, 10], "object_type": "car", "confidence": 0.95},
        {"bbox": [1, 0, 10, 10], "object_type": "car", "confidence": 0.85},
    ]

    metrics = evaluate_detections(predictions, truth, iou_threshold=0.5)

    assert metrics.true_positives == 1
    assert metrics.false_positives == 1
    assert metrics.missed_detections == 0
    assert metrics.precision == pytest.approx(0.5)
    assert metrics.recall == pytest.approx(1.0)
    assert metrics.f1 == pytest.approx(2.0 * 0.5 * 1.0 / 1.5)

    # Ensure the duplicate is recorded as a false positive, NOT poor localization
    fp_records = [f for f in metrics.failure_records if f.failure_type == "false_positive"]
    assert len(fp_records) == 1
    assert fp_records[0].confidence == 0.85
    assert not any(f.failure_type == "poor_localization" for f in metrics.failure_records)


def test_multiple_predictions_competing_for_ground_truth_greedy_iou():
    """Greedy selection assigns the prediction with the highest IoU to the ground truth."""
    truth = [GroundTruthObject(10, "car", (0, 0, 10, 10))]
    predictions = [
        {"bbox": [4, 0, 10, 10], "object_type": "car", "confidence": 0.7},  # IoU = 60/100 = 0.6
        {"bbox": [1, 0, 10, 10], "object_type": "car", "confidence": 0.9},  # IoU = 90/100 = 0.9
    ]

    metrics = evaluate_detections(predictions, truth, iou_threshold=0.5)

    assert metrics.true_positives == 1
    assert metrics.matches[0].prediction_index == 1
    assert metrics.matches[0].iou == pytest.approx(0.9)
    assert metrics.false_positives == 1
    assert metrics.false_positive_indices == (0,)


def test_multiple_ground_truth_competing_for_one_prediction():
    """One prediction overlapping two ground truths matches the highest IoU; the other is missed."""
    predictions = [{"bbox": [0, 0, 10, 10], "object_type": "car", "confidence": 0.9}]
    truth = [
        GroundTruthObject(1, "car", (0, 0, 10, 10)),   # IoU = 1.0
        GroundTruthObject(2, "car", (2, 0, 10, 10)),   # IoU = 0.8
    ]

    metrics = evaluate_detections(predictions, truth, iou_threshold=0.5)

    assert metrics.true_positives == 1
    assert metrics.false_positives == 0
    assert metrics.missed_detections == 1
    assert metrics.matches[0].ground_truth_index == 0
    assert metrics.missed_ground_truth_indices == (1,)
    assert [f.failure_type for f in metrics.failure_records] == ["missed_detection"]
    assert metrics.failure_records[0].actor_id == 2


def test_evaluation_classes_excludes_unsupported_classes():
    """Predictions outside evaluation_classes must NOT be counted as false positives."""
    predictions = [
        {"bbox": [0, 0, 10, 10], "object_type": "car", "confidence": 0.9},
        {"bbox": [20, 20, 30, 30], "object_type": "traffic_cone", "confidence": 0.85},
        {"bbox": [40, 40, 50, 50], "object_type": "dog", "confidence": 0.80},
    ]
    truth = [GroundTruthObject(1, "car", (0, 0, 10, 10))]

    metrics = evaluate_detections(
        predictions,
        truth,
        evaluation_classes=["car", "pedestrian"],
    )

    assert metrics.true_positives == 1
    assert metrics.false_positives == 0
    assert metrics.missed_detections == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.excluded_prediction_count == 2
    assert len(metrics.failure_records) == 0


def test_excluded_classes_parameter():
    """Explicitly excluded classes are filtered out and do not produce false positives."""
    predictions = [
        {"bbox": [0, 0, 10, 10], "object_type": "car", "confidence": 0.9},
        {"bbox": [20, 20, 30, 30], "object_type": "bicycle", "confidence": 0.85},
    ]
    truth = [GroundTruthObject(1, "car", (0, 0, 10, 10))]

    metrics = evaluate_detections(
        predictions,
        truth,
        excluded_classes=["bicycle"],
    )

    assert metrics.true_positives == 1
    assert metrics.false_positives == 0
    assert metrics.excluded_prediction_count == 1
    assert len(metrics.failure_records) == 0


def test_carla_actor_class_dict_duck_typing():
    """carla_actor_class correctly extracts class names from dictionary actor representations."""
    assert carla_actor_class({"type_id": "vehicle.audi.etron"}) == "car"
    assert carla_actor_class({"type_id": "vehicle.diamondback.century"}) == "bicycle"
    assert carla_actor_class({"type_id": "walker.pedestrian.0002"}) == "pedestrian"
    assert carla_actor_class({"object_type": "vehicle.yamaha.yzf"}) == "motorcycle"
    assert carla_actor_class({"type_id": "static.prop.box"}) is None


def test_aggregate_run_metrics_micro_averaging():
    """Run aggregation must micro-average counts rather than averaging frame-level metrics."""
    # Frame 1: 1 TP, 0 FP -> frame precision = 1.0
    f1 = ValidationMetrics(
        iou_threshold=0.5,
        prediction_count=1,
        ground_truth_count=1,
        true_positives=1,
        false_positives=0,
        missed_detections=0,
        precision=1.0,
        recall=1.0,
        f1=1.0,
        matches=(DetectionMatch(0, 0, 0.9),),
        false_positive_indices=(),
        missed_ground_truth_indices=(),
        failure_records=(),
        matched_iou=0.9,
    )
    # Frame 2: 0 TP, 9 FP -> frame precision = 0.0
    failure = PerceptionFailureRecord(
        failure_type="false_positive",
        object_class="car",
        severity="medium",
        frame_id=2,
    )
    f2 = ValidationMetrics(
        iou_threshold=0.5,
        prediction_count=9,
        ground_truth_count=0,
        true_positives=0,
        false_positives=9,
        missed_detections=0,
        precision=0.0,
        recall=0.0,
        f1=0.0,
        matches=(),
        false_positive_indices=tuple(range(9)),
        missed_ground_truth_indices=(),
        failure_records=(failure,),
        matched_iou=0.0,
    )

    # Frame-averaged precision would be (1.0 + 0.0)/2 = 0.5 (WRONG!)
    # Micro-averaged precision is TP / (TP + FP) = 1 / (1 + 9) = 0.10 (CORRECT!)
    run = aggregate_run_metrics(
        [f1, f2],
        scenario_id="scenario-test-42",
        parameters={"fixed_delta": 0.05},
    )

    assert run.frames_processed == 2
    assert run.predictions == 10
    assert run.true_positives == 1
    assert run.false_positives == 9
    assert run.missed_detections == 0
    assert run.precision == pytest.approx(0.10)
    assert run.recall == pytest.approx(1.0)
    assert run.f1 == pytest.approx(2.0 * 0.10 * 1.0 / 1.10)
    assert run.matched_iou == pytest.approx(0.9)
    assert run.scenario_id == "scenario-test-42"
    assert run.parameters == {"fixed_delta": 0.05}
    assert len(run.failures) == 1

    d = run.to_dict()
    assert d["precision"] == pytest.approx(0.10)
    assert d["matched_iou"] == pytest.approx(0.9)
    assert d["failure_count"] == 1


def test_aggregate_run_metrics_empty_run():
    """Aggregating an empty sequence of frame metrics produces zeroed metrics safely."""
    run = aggregate_run_metrics([])

    assert run.frames_processed == 0
    assert run.predictions == 0
    assert run.ground_truth_objects == 0
    assert run.true_positives == 0
    assert run.false_positives == 0
    assert run.missed_detections == 0
    assert run.precision == 0.0
    assert run.recall == 0.0
    assert run.f1 == 0.0
    assert run.matched_iou == 0.0
    assert run.failures == ()


def test_export_run_report_persists_metrics_and_failures(tmp_path):
    """export_run_report saves run-level metrics JSON and failure records JSONL."""
    failure = PerceptionFailureRecord(
        failure_type="poor_localization",
        object_class="truck",
        predicted_bbox=[0, 0, 10, 10],
        ground_truth_bbox=[0, 0, 15, 15],
        iou=0.44,
        severity="high",
        frame_id=15,
        scenario_id="run-exp-1",
    )
    run = RunValidationMetrics(
        frames_processed=10,
        predictions=12,
        ground_truth_objects=10,
        true_positives=8,
        false_positives=4,
        missed_detections=2,
        precision=8 / 12,
        recall=8 / 10,
        f1=2 * (8 / 12) * (8 / 10) / ((8 / 12) + (8 / 10)),
        matched_iou=0.82,
        iou_threshold=0.5,
        failures=(failure,),
        scenario_id="run-exp-1",
        scenario_conditions={"weather": {"fog_density": 20.0}},
        parameters={"fixed_delta_seconds": 0.05},
    )

    metrics_dest = tmp_path / "metrics.json"
    failures_dest = tmp_path / "failures.jsonl"

    m_path, f_path = export_run_report(
        run,
        metrics_dest,
        failures_destination=failures_dest,
        failure_format="jsonl",
    )

    assert m_path.exists()
    assert f_path.exists()

    metrics_data = json.loads(metrics_dest.read_text(encoding="utf-8"))
    assert metrics_data["scenario_id"] == "run-exp-1"
    assert metrics_data["true_positives"] == 8
    assert metrics_data["matched_iou"] == 0.82
    assert metrics_data["parameters"] == {"fixed_delta_seconds": 0.05}

    failure_line = json.loads(failures_dest.read_text(encoding="utf-8").strip())
    assert failure_line["failure_type"] == "poor_localization"
    assert failure_line["object_class"] == "truck"
    assert failure_line["frame_id"] == 15


def test_evaluation_classes_excludes_invalid_box_out_of_scope():
    """Out-of-scope classes with invalid/missing bboxes are excluded cleanly without FP or failure records."""
    predictions = [
        {"bbox": [0, 0, 10, 10], "object_type": "car", "confidence": 0.9},
        {"bbox": None, "object_type": "traffic_cone", "confidence": 0.8},
        {"bbox": [0, 0, float("nan"), 1], "object_type": "dog", "confidence": 0.7},
    ]
    truth = [
        GroundTruthObject(1, "car", (0, 0, 10, 10)),
        GroundTruthObject(2, "bird", (0, 0, 0, 0)),
    ]

    metrics = evaluate_detections(
        predictions,
        truth,
        evaluation_classes=["car"],
    )

    assert metrics.true_positives == 1
    assert metrics.false_positives == 0
    assert metrics.missed_detections == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1 == 1.0
    assert metrics.excluded_prediction_count == 2
    assert metrics.excluded_ground_truth_count == 1
    assert len(metrics.failure_records) == 0


def test_run_id_preservation_across_validation_pipeline(tmp_path):
    """run_id is preserved across evaluation, aggregation, and file exports."""
    prediction = {"bbox": [0, 0, 10, 10], "object_type": "car", "confidence": 0.3}
    truth = [GroundTruthObject(1, "car", (0, 0, 10, 10))]

    metrics = evaluate_detections(
        [prediction],
        truth,
        scenario_id="scenario-alpha",
        run_id="run-omega-001",
        frame_id=42,
    )

    assert len(metrics.failure_records) > 0
    assert metrics.failure_records[0].scenario_id == "scenario-alpha"
    assert metrics.failure_records[0].run_id == "run-omega-001"
    assert metrics.failure_records[0].frame_id == 42

    run = aggregate_run_metrics(
        [metrics],
        scenario_id="scenario-alpha",
        run_id="run-omega-001",
        parameters={"fixed_delta": 0.05},
    )

    assert run.scenario_id == "scenario-alpha"
    assert run.run_id == "run-omega-001"
    assert run.to_dict()["run_id"] == "run-omega-001"
    assert run.failures[0].run_id == "run-omega-001"

    metrics_dest = tmp_path / "run_metrics.json"
    failures_dest = tmp_path / "run_failures.jsonl"
    export_run_report(
        run,
        metrics_dest,
        failures_destination=failures_dest,
        failure_format="jsonl",
    )

    exported_metrics = json.loads(metrics_dest.read_text(encoding="utf-8"))
    assert exported_metrics["scenario_id"] == "scenario-alpha"
    assert exported_metrics["run_id"] == "run-omega-001"

    exported_failure = json.loads(failures_dest.read_text(encoding="utf-8").strip())
    assert exported_failure["scenario_id"] == "scenario-alpha"
    assert exported_failure["run_id"] == "run-omega-001"


