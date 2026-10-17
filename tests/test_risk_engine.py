
from edgeforge.analysis.risk_engine import RiskEngine
from edgeforge.data.models import (
    DetectedObject,
    RiskAssessment,
    RiskLevel,
    VehicleState,
)


def make_object(object_id, object_type, distance, relative_speed):
    """Create a detected object for testing."""
    return DetectedObject(
        object_id=object_id,
        object_type=object_type,
        confidence=0.95,
        distance=distance,
        relative_speed=relative_speed,
    )


def make_vehicle(speed=0.0):
    """VehicleState speed is measured in metres per second."""
    return VehicleState(speed=speed)


def test_no_objects_returns_zero_risk():
    engine = RiskEngine()

    result = engine.calculate_risk([], make_vehicle())

    assert isinstance(result, RiskAssessment)
    assert result.risk_score == 0.0
    assert result.risk_level == RiskLevel.LOW
    assert result.contributing_objects == []


def test_closer_object_has_higher_risk_than_farther_object():
    engine = RiskEngine()

    close_result = engine.calculate_risk(
        [make_object("close", "car", 5.0, -2.0)],
        make_vehicle(),
    )
    far_result = engine.calculate_risk(
        [make_object("far", "car", 40.0, -2.0)],
        make_vehicle(),
    )

    assert close_result.risk_score > far_result.risk_score


def test_pedestrian_weight_is_greater_than_car_weight():
    engine = RiskEngine()

    pedestrian_result = engine.calculate_risk(
        [make_object("ped-1", "pedestrian", 15.0, -2.0)],
        make_vehicle(),
    )
    car_result = engine.calculate_risk(
        [make_object("car-1", "car", 15.0, -2.0)],
        make_vehicle(),
    )

    assert pedestrian_result.risk_score > car_result.risk_score


def test_faster_ego_vehicle_does_not_reduce_risk():
    engine = RiskEngine()
    objects = [make_object("car-1", "car", 15.0, -2.0)]

    slow_result = engine.calculate_risk(objects, make_vehicle(speed=0.0))
    fast_result = engine.calculate_risk(objects, make_vehicle(speed=20.0))

    assert fast_result.risk_score >= slow_result.risk_score


def test_multiple_hazards_do_not_reduce_risk():
    engine = RiskEngine()

    one_result = engine.calculate_risk(
        [make_object("car-1", "car", 15.0, -2.0)],
        make_vehicle(),
    )
    two_result = engine.calculate_risk(
        [
            make_object("car-1", "car", 15.0, -2.0),
            make_object("ped-1", "pedestrian", 12.0, -2.0),
        ],
        make_vehicle(),
    )

    assert two_result.risk_score >= one_result.risk_score


def test_risk_score_stays_between_zero_and_one():
    engine = RiskEngine()

    result = engine.calculate_risk(
        [
            make_object("ped-1", "pedestrian", 1.0, -10.0),
            make_object("car-1", "car", 2.0, -8.0),
            make_object("bike-1", "bicycle", 3.0, -6.0),
        ],
        make_vehicle(speed=30.0),
    )

    assert 0.0 <= result.risk_score <= 1.0


def test_incomplete_measurements_are_explicit_when_no_object_contributes():
    result = RiskEngine().calculate_risk(
        [make_object("unknown", "car", None, None)],
        make_vehicle(),
    )

    assert result.risk_score == 0.0
    assert "risk assessment is incomplete" in result.reason


def test_incomplete_measurements_are_explicit_alongside_known_hazards():
    result = RiskEngine().calculate_risk(
        [
            make_object("known-hazard", "car", 3.0, -10.0),
            make_object("partially-known", "pedestrian", 8.0, None),
        ],
        make_vehicle(),
    )

    assert result.risk_score > 0.0
    assert "known-hazard" in result.contributing_objects
    assert "risk assessment is incomplete" in result.reason
