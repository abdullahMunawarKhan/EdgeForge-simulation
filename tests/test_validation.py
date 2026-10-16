from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

import numpy as np
import pytest

from edgeforge.data.models import DetectedObject, PerceptionFailureRecord
from edgeforge.perception.validation import (
    FailureSeverityRules,
    GroundTruthObject,
    carla_actor_class,
    evaluate_detections,
    export_failure_report,
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
