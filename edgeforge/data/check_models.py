"""
Quick validation checks for the shared EdgeForge data contracts.
"""

from edgeforge.data.models import (
    AgentAction,
    DetectedObject,
    LaneInfo,
    LidarPointCloud,
    RiskAssessment,
    RiskLevel,
    ScenarioEvent,
    ScenarioResult,
    VehicleState,
)


def expect_rejected(factory, label: str) -> None:
    try:
        factory()
    except Exception:
        print(f" OK rejected: {label}")
    else:
        raise AssertionError(f"Expected rejection: {label}")


def main() -> None:
    # ------------------------------------------------------------------
    # Required fields
    # ------------------------------------------------------------------

    assert set(ScenarioEvent.model_fields) >= {
        "type",
        "severity",
        "timestamp",
        "message",
    }
    print(" OK ScenarioEvent has ['type', 'severity', 'timestamp', 'message']")

    assert set(ScenarioResult.model_fields) >= {
        "scenario_name",
        "success",
        "exit_status",
        "duration_s",
        "events",
        "metrics",
    }
    print(
        " OK ScenarioResult has "
        "['scenario_name', 'success', 'exit_status', 'duration_s', 'events', 'metrics']"
    )

    assert set(AgentAction.model_fields) >= {
        "throttle",
        "steer",
        "brake",
    }
    print(" OK AgentAction has ['throttle', 'steer', 'brake']")

    assert set(LaneInfo.model_fields) >= {
        "lane_id",
        "lateral_offset_m",
        "is_invading",
    }
    print(" OK LaneInfo has ['lane_id', 'lateral_offset_m', 'is_invading']")

    assert set(LidarPointCloud.model_fields) >= {
        "timestamp",
        "channels",
        "points",
    }
    print(" OK LidarPointCloud has ['timestamp', 'channels', 'points']")

    # ------------------------------------------------------------------
    # Valid sample objects
    # ------------------------------------------------------------------

    event = ScenarioEvent(
        type="near_collision",
        severity="warning",
        timestamp=1.5,
        message="Pedestrian detected at low TTC.",
    )

    ScenarioResult(
        scenario_name="test_scenario",
        run_id="run_001",
        success=True,
        exit_status="completed",
        duration_s=10.5,
        events=[event],
        metrics={"max_risk": 0.8},
    )

    AgentAction(
        throttle=0.5,
        steer=-0.2,
        brake=0.0,
    )

    LaneInfo(
        lane_id=1,
        lane_width_m=3.5,
        lateral_offset_m=0.2,
        is_invading=False,
    )

    LidarPointCloud(
        timestamp=1.0,
        channels=16,
        points=[(1.0, 2.0, 3.0)],
    )

    print(" OK valid samples")

    # ------------------------------------------------------------------
    # Invalid ScenarioEvent checks
    # ------------------------------------------------------------------

    expect_rejected(
        lambda: ScenarioEvent(
            type="unknown_event",
            severity="info",
            timestamp=1.0,
        ),
        "unknown event type",
    )

    expect_rejected(
        lambda: ScenarioEvent(
            type="collision",
            severity="unknown",
            timestamp=1.0,
        ),
        "unknown severity",
    )

    expect_rejected(
        lambda: ScenarioEvent(
            type="collision",
            severity="critical",
            timestamp=-1.0,
        ),
        "negative timestamp",
    )

    # ------------------------------------------------------------------
    # Invalid AgentAction checks
    # ------------------------------------------------------------------

    expect_rejected(
        lambda: AgentAction(throttle=0.0, steer=0.0, brake=1.1),
        "brake > 1",
    )

    expect_rejected(
        lambda: AgentAction(throttle=0.0, steer=0.0, brake=-0.1),
        "brake < 0",
    )

    expect_rejected(
        lambda: AgentAction(throttle=-0.1, steer=0.0, brake=0.0),
        "throttle < 0",
    )

    expect_rejected(
        lambda: AgentAction(throttle=1.1, steer=0.0, brake=0.0),
        "throttle > 1",
    )

    expect_rejected(
        lambda: AgentAction(throttle=0.0, steer=-1.1, brake=0.0),
        "steer < -1",
    )

    expect_rejected(
        lambda: AgentAction(throttle=0.0, steer=1.1, brake=0.0),
        "steer > 1",
    )

    # ------------------------------------------------------------------
    # Existing contract checks
    # ------------------------------------------------------------------

    assert set(DetectedObject.model_fields) >= {
        "object_type",
        "confidence",
        "bbox",
        "distance",
        "object_id",
        "relative_speed",
    }
    print(
        " OK existing DetectedObject has "
        "['object_type', 'confidence', 'bbox', 'distance', "
        "'object_id', 'relative_speed']"
    )

    assert set(RiskAssessment.model_fields) >= {
        "risk_score",
        "risk_level",
        "reason",
        "contributing_objects",
    }
    print(
        " OK existing RiskAssessment has "
        "['risk_score', 'risk_level', 'reason', 'contributing_objects']"
    )

    assert "speed" in VehicleState.model_fields
    print(" OK existing VehicleState has ['speed']")

    # Confirm enum is still available.
    assert RiskLevel.LOW.value == "LOW"

    print(" ALL MODEL CHECKS PASSED")


if __name__ == "__main__":
    main()