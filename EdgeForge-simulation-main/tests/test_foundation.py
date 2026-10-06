"""Smoke tests for the EdgeForge foundation layer.

None of these tests require CARLA or any ML models.
They validate:
  * Settings load with safe defaults
  * get_logger returns a usable logger
  * CameraProcessor validates frames correctly
  * ObjectDetector returns an empty list on valid input
  * RiskEngine produces expected RiskLevel enum values + boundary scores
"""

from __future__ import annotations

import numpy as np
import pytest

from edgeforge.analysis import RiskEngine
from edgeforge.config import settings
from edgeforge.data import DetectedObject, RiskLevel, VehicleState
from edgeforge.perception import CameraProcessor, ObjectDetector
from edgeforge.utils import get_logger


# ---- Settings ---------------------------------------------------------------
def test_settings_defaults_populated() -> None:
    assert settings.PROJECT_NAME == "EdgeForge"
    assert settings.CAMERA_WIDTH > 0
    assert settings.CAMERA_HEIGHT > 0
    assert 0.0 <= settings.RISK_THRESHOLD <= 1.0


# ---- Logger -----------------------------------------------------------------
def test_get_logger_returns_something_callable() -> None:
    log = get_logger("tests")
    assert log is not None
    log.info("hello from pytest")  # must not raise


# ---- CameraProcessor --------------------------------------------------------
def test_camera_processor_rejects_none_and_shapes() -> None:
    cp = CameraProcessor(640, 360)
    assert not cp.is_valid_frame(None)
    assert not cp.is_valid_frame(np.array([]))
    assert not cp.is_valid_frame(np.zeros((5, 5, 5, 5)))  # 4D nope

    info = cp.get_frame_info(None)
    assert info.empty is True
    assert info.width == 0


def test_camera_processor_accepts_uint8_bgr() -> None:
    cp = CameraProcessor()
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    assert cp.is_valid_frame(frame)
    info = cp.get_frame_info(frame)
    assert (info.width, info.height, info.channels) == (200, 100, 3)


def test_camera_processor_resize() -> None:
    cp = CameraProcessor()
    frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    small = cp.resize_frame(frame, 640, 360)
    assert small.shape[:2] == (360, 640)


# ---- ObjectDetector ---------------------------------------------------------
def test_detector_returns_empty_list_on_valid_frame() -> None:
    det = ObjectDetector()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = det.detect(frame)
    assert isinstance(result, list)
    assert len(result) == 0


def test_detector_handles_none_gracefully() -> None:
    det = ObjectDetector()
    assert det.detect(None) == []


def test_detector_status_shows_no_model_loaded() -> None:
    det = ObjectDetector()
    status = det.get_status()
    assert status["module"] == "object_detector"
    assert status["model_loaded"] is False
    assert status["status"] == "initialized"


# ---- RiskEngine -------------------------------------------------------------
def test_risk_engine_empty_list_is_low() -> None:
    engine = RiskEngine()
    ego = VehicleState(speed=10.0)
    out = engine.calculate_risk([], ego)
    assert out.risk_level == RiskLevel.LOW
    assert out.risk_score == pytest.approx(0.0, abs=1e-9)


def test_risk_engine_close_and_climbing_is_high_or_critical() -> None:
    engine = RiskEngine()
    ego = VehicleState(speed=20.0)
    hazards = [
        DetectedObject(
            object_id="danger",
            object_type="pedestrian",
            confidence=0.9,
            distance=3.0,
            relative_speed=-20.0,  # hard closing speed
        )
    ]
    out = engine.calculate_risk(hazards, ego)
    # 3m + 20m/s closing → should be in HIGH or CRITICAL
    assert out.risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}
    assert out.risk_score >= 0.55
    assert "danger" in out.contributing_objects
    assert len(out.reason) > 0


def test_risk_level_enum_values() -> None:
    # Sanity check so the dashboard colour scheme has stable labels.
    assert {r.value for r in RiskLevel} == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
