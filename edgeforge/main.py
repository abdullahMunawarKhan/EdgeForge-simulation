"""
EdgeForge – main entry point.

This script wires together the platform modules (config → logger →
camera processor → object detector → risk engine) and runs a small
demonstration on a synthetic NumPy image.

**No CARLA is required to run this file.**  It exercises the full
perception/risk pipeline in a self-contained way so developers can
verify that the foundation works before the simulator is plugged in.

Usage (from the edgeforge/ directory)::

    python main.py

Conceptual pipeline::

    Dummy frame  ──▶  CameraProcessor  ──▶  ObjectDetector  ──▶  RiskEngine  ──▶  RiskAssessment

TODO:
  * Plug in the CARLA simulation layer (camera → real frames).
  * Replace the synthetic demo frame with real CARLA RGB sensor data.
  * Feed real DetectedObjects from the perception layer into RiskEngine.
  * Expose this pipeline over FastAPI (FastAPI + uvicorn are in requirements.txt).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Make the parent directory importable so ``from edgeforge.X import Y`` works
# regardless of whether this script is invoked as ``python main.py`` from
# inside the edgeforge folder, or as ``python -m edgeforge.main``.
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_PARENT = _THIS_DIR.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import numpy as np

from edgeforge.analysis import RiskEngine
from edgeforge.config import settings
from edgeforge.data.models import DetectedObject, RiskLevel, VehicleState
from edgeforge.perception import CameraProcessor, ObjectDetector
from edgeforge.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1. Print a nicely formatted banner / status summary
# ---------------------------------------------------------------------------
def print_banner() -> None:
    border = "=" * 64
    print()
    print(border)
    print(f"  {settings.PROJECT_NAME}  v{settings.VERSION}")
    if settings.DEBUG:
        print("  (DEBUG mode enabled)")
    print(border)
    print(f"  Config loaded from: {settings.__class__.__name__}")
    print(f"  CARLA target:       {settings.CARLA_HOST}:{settings.CARLA_PORT}")
    print(f"  Camera defaults:    {settings.CAMERA_WIDTH}x{settings.CAMERA_HEIGHT} "
          f"@ {settings.CAMERA_FOV}° FOV")
    print(f"  Risk threshold:     {settings.RISK_THRESHOLD}")
    print(border)
    print()


# ---------------------------------------------------------------------------
# 2. Construct a dummy frame + a few synthetic DetectedObjects so the
#    pipeline produces a non-trivial RiskAssessment in the demo.
# ---------------------------------------------------------------------------
def make_dummy_frame(width: int, height: int) -> np.ndarray:
    """Build a synthetic 8-bit BGR image (OpenCV convention) that looks
    like a valid frame to CameraProcessor.

    The content doesn't matter – the detector returns an empty list
    anyway in this starter build – but the shape and dtype are realistic.
    """
    rng = np.random.default_rng(seed=42)
    # Start from a soft blue background, then add some noise so the frame
    # isn't trivially empty.
    base = np.full((height, width, 3), (180, 140, 90), dtype=np.uint8)
    noise = rng.integers(0, 40, size=(height, width, 3), dtype=np.uint8)
    frame = cv2_add_uint8_safe(base, noise)
    return frame


def cv2_add_uint8_safe(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Element-wise add of two uint8 arrays with saturation (like cv2.add)."""
    tmp = a.astype(np.uint16) + b.astype(np.uint16)
    return np.clip(tmp, 0, 255).astype(np.uint8)


def make_demo_detected_objects() -> list[DetectedObject]:
    """Return a handful of fake DetectedObjects so RiskEngine can run.

    These are *not* produced by the ObjectDetector (which rightly returns
    an empty list).  They are injected in the demo to showcase the
    RiskEngine layer independently.
    """
    return [
        DetectedObject(
            object_id="car_001",
            object_type="car",
            confidence=0.92,
            distance=18.0,
            relative_speed=-8.0,  # closing at 8 m/s
            bbox=[600.0, 320.0, 860.0, 500.0],
        ),
        DetectedObject(
            object_id="ped_001",
            object_type="pedestrian",
            confidence=0.78,
            distance=45.0,
            relative_speed=-1.0,
            bbox=[200.0, 340.0, 235.0, 430.0],
        ),
        DetectedObject(
            object_id="car_002",
            object_type="car",
            confidence=0.85,
            distance=120.0,
            relative_speed=+5.0,  # moving away
            bbox=[950.0, 360.0, 1050.0, 440.0],
        ),
    ]


# ---------------------------------------------------------------------------
# 3. Orchestrate the demo
# ---------------------------------------------------------------------------
def run_demo() -> int:
    logger.info(f"{settings.PROJECT_NAME} v{settings.VERSION} starting up…")

    # ---- 3a. Initialise pipeline modules ---------------------------------
    camera_proc = CameraProcessor(
        default_width=settings.CAMERA_WIDTH,
        default_height=settings.CAMERA_HEIGHT,
    )
    detector = ObjectDetector()
    risk_engine = RiskEngine()

    # ---- 3b. Print status ------------------------------------------------
    print("\n[Module Status]")
    status = {
        "camera_processor": {
            "default_size": f"{camera_proc.default_width}x{camera_proc.default_height}"
        },
        "object_detector": detector.get_status(),
        "risk_engine": {
            "thresholds": {
                "MEDIUM": risk_engine.LEVEL_MEDIUM,
                "HIGH": risk_engine.LEVEL_HIGH,
                "CRITICAL": risk_engine.LEVEL_CRITICAL,
            }
        },
    }
    print(json.dumps(status, indent=2))

    # ---- 3c. Create a dummy frame and run it through CameraProcessor -----
    print("\n[CameraProcessor demo]")
    frame = make_dummy_frame(settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT)
    info = camera_proc.get_frame_info(frame)
    print(f"  Input frame:  {info.width}x{info.height}, "
          f"{info.channels} ch, dtype={info.dtype}, empty={info.empty}")
    assert not info.empty, "Frame should not be reported as empty"
    assert camera_proc.is_valid_frame(frame), "Frame should pass validation"

    small = camera_proc.resize_frame(frame, width=640, height=360)
    small_info = camera_proc.get_frame_info(small)
    print(f"  Resized to:   {small_info.width}x{small_info.height}")

    # ---- 3d. Run ObjectDetector ------------------------------------------
    print("\n[ObjectDetector demo]")
    detections = detector.detect(frame)
    print(f"  Detection count (placeholder): {len(detections)} "
          f"(expected 0 – real YOLO not yet integrated)")
    assert isinstance(detections, list), "detect() must return a list"

    status_after = detector.get_status()
    print(f"  Calls so far: {status_after['total_detection_calls']}")

    # ---- 3e. RiskEngine using demo objects (injected manually) -----------
    print("\n[RiskEngine demo]")
    ego_state = VehicleState(
        vehicle_id="ego_demo",
        speed=12.0,  # m/s ≈ 43 km/h
        acceleration=0.5,
    )
    demo_objects = make_demo_detected_objects()
    assessment = risk_engine.calculate_risk(demo_objects, ego_state)

    print(f"  Ego speed:      {ego_state.speed * 3.6:.1f} km/h")
    print(f"  Objects passed: {len(demo_objects)}")
    print(f"  Risk score:     {assessment.risk_score:.3f}  "
          f"[{assessment.risk_level.value}]")
    print(f"  Reason:         {assessment.reason}")
    if assessment.contributing_objects:
        print(f"  Contributors:   {', '.join(assessment.contributing_objects)}")
    print(f"  Level is enum member: {isinstance(assessment.risk_level, RiskLevel)}")

    # ---- 3f. Also confirm baseline (no objects → LOW / 0) ----------------
    baseline = risk_engine.calculate_risk([], ego_state)
    print(f"\n  Baseline (no objects): score={baseline.risk_score}, "
          f"level={baseline.risk_level.value}")
    assert baseline.risk_level == RiskLevel.LOW
    assert baseline.risk_score == 0.0

    # -----------------------------------------------------------------------
    logger.success("✅ EdgeForge demo pipeline completed successfully.")
    print("\n✅ All checks passed – platform foundation is ready.")
    print("   Next step: plug in the CARLA simulation layer in edgeforge/simulation")
    return 0


# ---------------------------------------------------------------------------
def main() -> int:
    print_banner()
    return run_demo()


if __name__ == "__main__":
    raise SystemExit(main())
