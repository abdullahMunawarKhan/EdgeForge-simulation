"""
EdgeForge – main entry point.

Two modes of operation are supported:

Synthetic demo (no CARLA required)::

    python main.py

Wires CameraProcessor → ObjectDetector → RiskEngine together and runs
the full perception/risk pipeline on a synthetic NumPy frame so the
platform foundation can be verified without a running simulator.

Live CARLA simulation (requires CARLA server)::

    python main.py --sim [path/to/scenario.json]

Loads a JSON scenario config, connects to the CARLA server, runs the
scenario in synchronous mode, and for every simulated tick pipes:

    CARLA RGB frame  →  CameraProcessor  →  ObjectDetector  →  RiskEngine
    CARLA Vehicle   ─────────────────────────────────────────┘

Conceptual pipeline (both modes)::

    Frame source  ──▶  CameraProcessor  ──▶  DetectedObjects  ──▶  RiskEngine  ──▶  RiskAssessment
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Make the parent directory importable so ``from edgeforge.X import Y`` works
# regardless of whether this script is invoked as ``python main.py`` from
# inside the edgeforge folder, or as ``python -m edgeforge.main``.
# ---------------------------------------------------------------------------
_THIS_DIR = Path(__file__).resolve().parent
_PARENT = _THIS_DIR.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import cv2
import numpy as np

from edgeforge.analysis import RiskEngine
from edgeforge.config import settings
from edgeforge.data.models import DetectedObject, RiskLevel, VehicleState
from edgeforge.perception import (
    CameraProcessor,
    ObjectDetector,
    PerceptionPipeline,
    adapt_ground_truth_detections,
)
from edgeforge.utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1. Print a nicely formatted banner / status summary
# ---------------------------------------------------------------------------
def print_banner(mode: str = "DEMO") -> None:
    border = "=" * 64
    print()
    print(border)
    print(f"  {settings.PROJECT_NAME}  v{settings.VERSION}   [mode: {mode}]")
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
    """Build a synthetic 8-bit BGR image (OpenCV convention)."""
    rng = np.random.default_rng(seed=42)
    base = np.full((height, width, 3), (180, 140, 90), dtype=np.uint8)
    noise = rng.integers(0, 40, size=(height, width, 3), dtype=np.uint8)
    frame = cv2_add_uint8_safe(base, noise)
    return frame


def cv2_add_uint8_safe(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Element-wise add of two uint8 arrays with saturation (like cv2.add)."""
    tmp = a.astype(np.uint16) + b.astype(np.uint16)
    return np.clip(tmp, 0, 255).astype(np.uint8)


def make_demo_detected_objects() -> list[DetectedObject]:
    """Return fake DetectedObjects so RiskEngine can run in demo mode."""
    return [
        DetectedObject(
            object_id="car_001",
            object_type="car",
            confidence=0.92,
            distance=18.0,
            relative_speed=-8.0,
            bbox=[600.0, 320.0, 860.0, 500.0],
            timestamp=datetime.utcnow(),
        ),
        DetectedObject(
            object_id="ped_001",
            object_type="pedestrian",
            confidence=0.78,
            distance=45.0,
            relative_speed=-1.0,
            bbox=[200.0, 340.0, 235.0, 430.0],
            timestamp=datetime.utcnow(),
        ),
        DetectedObject(
            object_id="car_002",
            object_type="car",
            confidence=0.85,
            distance=120.0,
            relative_speed=+5.0,
            bbox=[950.0, 360.0, 1050.0, 440.0],
            timestamp=datetime.utcnow(),
        ),
    ]


# ---------------------------------------------------------------------------
# 3. Synthetic demo mode (no CARLA required)
# ---------------------------------------------------------------------------
def run_demo() -> int:
    logger.info(f"{settings.PROJECT_NAME} v{settings.VERSION} starting up…")

    camera_proc = CameraProcessor(
        default_width=settings.CAMERA_WIDTH,
        default_height=settings.CAMERA_HEIGHT,
    )
    detector = ObjectDetector()
    risk_engine = RiskEngine()

    # ---- 3a. Print status ------------------------------------------------
    print("\n[Module Status]")
    status: Dict[str, Any] = {
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

    # ---- 3b. CameraProcessor demo --------------------------------------
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

    # ---- 3c. ObjectDetector --------------------------------------------
    print("\n[ObjectDetector demo]")
    detections = detector.detect(frame)
    print(f"  Detection count from {settings.YOLO_MODEL_PATH}: {len(detections)}")
    assert isinstance(detections, list), "detect() must return a list"

    status_after = detector.get_status()
    print(f"  Calls so far: {status_after['total_detection_calls']}")

    # ---- 3d. RiskEngine using demo objects (injected manually) ---------
    print("\n[RiskEngine demo]")
    ego_state = VehicleState(
        vehicle_id="ego_demo",
        speed=12.0,
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

    # ---- 3e. Baseline check ---------------------------------------------
    baseline = risk_engine.calculate_risk([], ego_state)
    print(f"\n  Baseline (no objects): score={baseline.risk_score}, "
          f"level={baseline.risk_level.value}")
    assert baseline.risk_level == RiskLevel.LOW
    assert baseline.risk_score == 0.0

    logger.success("✅ EdgeForge demo pipeline completed successfully.")
    print("\n✅ All checks passed – platform foundation is ready.")
    print("   Next step (Person 1): run `python main.py --sim` with CARLA server live.")
    print("   YOLO model, confidence, and device are configurable in the root .env.")
    return 0


# ---------------------------------------------------------------------------
# 4. Live CARLA simulation mode (requires running CARLA server)
# ---------------------------------------------------------------------------
def _render_risk_overlay(
    frame: np.ndarray,
    ego_state: Optional[VehicleState],
    detections: List[DetectedObject],
    risk: Optional[Any],  # RiskAssessment or None
) -> np.ndarray:
    """Draw a HUD onto ``frame`` and return a new annotated frame."""
    out = frame.copy()
    h, w = out.shape[:2]

    # Semi-transparent top HUD bar.
    overlay = out.copy()
    cv2.rectangle(overlay, (0, 0), (w, 68), (0, 0, 0), -1)
    out = cv2.addWeighted(overlay, 0.55, out, 0.45, 0)

    if ego_state is not None:
        kmh = ego_state.speed * 3.6
        speed_text = f"{kmh:.0f} km/h"
        cv2.putText(out, speed_text, (14, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        loc_text = (f"x={ego_state.location.x:6.1f} y={ego_state.location.y:6.1f} "
                    f"z={ego_state.location.z:5.1f}")
        cv2.putText(out, loc_text, (14, 52),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)

    # Risk badge (top-right)
    if risk is not None:
        level = risk.risk_level
        color_map = {
            RiskLevel.LOW: (80, 200, 80),
            RiskLevel.MEDIUM: (60, 210, 255),
            RiskLevel.HIGH: (40, 100, 255),
            RiskLevel.CRITICAL: (60, 60, 255),
        }
        bg = color_map.get(level, (180, 180, 180))
        badge_text = f"{level.value}  {risk.risk_score:.2f}"
        (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        bx1, by1 = w - tw - 28, 10
        cv2.rectangle(out, (bx1, by1), (bx1 + tw + 16, by1 + th + 16), tuple(bg), -1)
        cv2.putText(out, badge_text, (bx1 + 8, by1 + th + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)

    # Detection bboxes + per-object distance label.
    for obj in detections:
        if obj.bbox is None:
            continue
        x1, y1, x2, y2 = [int(v) for v in obj.bbox]
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{obj.object_type} {obj.distance:.0f}m ({obj.confidence:.2f})"
        cv2.putText(out, label, (x1, max(0, y1 - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)

    return out


def run_simulation(
    scenario_path: Optional[str],
    headless: bool = False,
    backend: Optional[str] = None,
) -> int:
    """Run the full EdgeForge pipeline backed by a CARLA or mock scenario.

    ``backend``:
      - ``"carla"``  — force real CARLA server (raises if not available)
      - ``"mock"``   — force pure-Python synthetic sim (no server needed)
      - ``"detect"`` — try CARLA; on failure fall back to mock (default)
    """
    if scenario_path is None:
        scenario_path = str(
            _THIS_DIR / "scenarios" / "configs" / "default_scenario.json"
        )

    # --- Local imports – only the scenario_runner module is strictly
    # required; mock mode does NOT import `carla` so this works even if
    # the CARLA wheel isn't installed.
    from edgeforge.simulation import ScenarioRunner, SensorFrame
    from edgeforge.api import runtime, start_api_server

    # --- Build the pipeline once (reused every tick) ---------------------
    camera_proc = CameraProcessor(
        default_width=settings.CAMERA_WIDTH,
        default_height=settings.CAMERA_HEIGHT,
    )
    detector = ObjectDetector()
    perception_pipeline = PerceptionPipeline(
        camera_processor=camera_proc,
        detector=detector,
    )
    risk_engine = RiskEngine()

    # Instantiate the runner directly to access mock ground truth.
    runner = ScenarioRunner.from_config(scenario_path, backend=backend)
    api_server = start_api_server()
    scenario_info = getattr(runner, "info", None)
    scenario_conditions = {
        "scenario_id": getattr(scenario_info, "name", None),
        "scenario_name": getattr(scenario_info, "name", None),
        "weather_preset": getattr(scenario_info, "weather_preset", None),
        "map": getattr(scenario_info, "map_name", None),
        "backend": runner.backend,
    }
    runtime.start(runner.backend, scenario_conditions)

    logger.success(
        f"Pipeline ready [backend={runner.backend}]: "
        "CameraProcessor → ObjectDetector → RiskEngine (waiting for scenario) ..."
    )

    window_open = not headless
    last_risk = None
    last_detections: List[DetectedObject] = []
    def on_frame(frame: SensorFrame) -> None:
        nonlocal window_open, last_risk, last_detections

        pipeline_detections: List[DetectedObject] | None = None
        camera_frame: np.ndarray | None = None
        # --- A) RGB frame through CameraProcessor (validation + optional resize)
        if frame.rgb is not None and camera_proc.is_valid_frame(frame.rgb):
            rgb = frame.rgb
            info = camera_proc.get_frame_info(rgb)
            if info.width != settings.CAMERA_WIDTH or info.height != settings.CAMERA_HEIGHT:
                rgb = camera_proc.resize_frame(
                    rgb, width=settings.CAMERA_WIDTH, height=settings.CAMERA_HEIGHT
                )
            camera_frame = rgb
            # --- B) Run perception detections --------------------------------
            if runner.backend == "mock":
                mock_detections = adapt_ground_truth_detections(
                    runner.latest_mock_ground_truth_detections,
                    source_size=(info.width, info.height),
                    target_size=(rgb.shape[1], rgb.shape[0]),
                )
                last_detections = perception_pipeline.process_frame(
                    rgb,
                    timestamp=frame.timestamp,
                    raw_detections=mock_detections,
                )
            else:
                last_detections = perception_pipeline.process_frame(
                    rgb,
                    timestamp=frame.timestamp,
                )
            pipeline_detections = last_detections
        else:
            last_detections = []

        # --- C) Risk assessment -------------------------------------------
        if frame.vehicle_state is not None:
            last_risk = risk_engine.calculate_risk(last_detections, frame.vehicle_state)

            if frame.frame_number % 40 == 0:
                kmh = frame.vehicle_state.speed * 3.6
                logger.info(
                    f"[frame {frame.frame_number}] sim={frame.timestamp:7.2f}s | "
                    f"ego={kmh:5.1f} km/h | dets={len(last_detections):2d} | "
                    f"risk={last_risk.risk_score:.2f} {last_risk.risk_level.value}"
                )

        pipeline_status = perception_pipeline.get_status()
        resolved_detections = (
            last_detections if runner.backend == "mock" else pipeline_detections
        )
        runtime.publish_frame(
            backend=runner.backend,
            frame_id=frame.frame_number,
            timestamp=frame.timestamp,
            detections=resolved_detections,
            scenario_conditions=scenario_conditions,
            metrics={
                "frames_processed": pipeline_status["frames_processed"],
                "detection_count": (
                    len(resolved_detections)
                    if resolved_detections is not None
                    else None
                ),
                "pipeline": pipeline_status,
            },
            risk_assessment=last_risk,
            camera_frame=camera_frame if runner.backend == "carla" else None,
            camera_frames=frame.camera_views if runner.backend == "carla" else None,
        )

        # --- D) Hazard / lane events (log if fired) -----------------------
        for event in frame.collision_events:
            logger.critical(
                f"💥 COLLISION at sim={event['timestamp']:.2f}s with "
                f"{event['other_actor']} impulse={event['impulse_norm']:.1f}"
            )
        for event in frame.lane_invasions:
            logger.warning(
                f"🛣  LANE INVASION at sim={event['timestamp']:.2f}s: "
                f"{event['crossed_markings']}"
            )

        # --- E) Render & display (optional, skipped in headless) ----------
        if window_open and frame.rgb is not None:
            hud = _render_risk_overlay(
                frame.rgb, frame.vehicle_state, last_detections, last_risk
            )
            cv2.imshow("EdgeForge — Live Risk HUD (press Q to quit)", hud)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                window_open = False
                raise KeyboardInterrupt()

    try:
        with runner.run() as stream:
            for frame in stream:
                on_frame(frame)
    except KeyboardInterrupt:
        print("\n🛑 Simulation stopped by user.")
    finally:
        runtime.stop()
        api_server.should_exit = True
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

    logger.success("✅ Simulation run complete.")
    return 0


# ---------------------------------------------------------------------------
# 5. CLI dispatcher
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        prog="edgeforge",
        description="EdgeForge autonomous-driving risk-assessment platform.",
    )
    parser.add_argument(
        "--sim",
        nargs="?",
        const="__DEFAULT__",
        default=None,
        metavar="SCENARIO_JSON",
        help="Run a simulation (CARLA or synthetic mock). Provide a scenario JSON "
             "path, or omit to use the default scenario.",
    )
    parser.add_argument(
        "--backend",
        choices=["carla", "mock", "detect"],
        default="detect",
        help="Simulation backend. 'detect' tries CARLA then falls back to mock "
             "(default). Use --mock to force mock mode with one flag.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Shortcut: --backend=mock (forces synthetic simulation; no CARLA required).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="With --sim: skip the OpenCV display window (server / CI runs).",
    )

    args = parser.parse_args()

    effective_backend = "mock" if args.mock else args.backend

    if args.sim is not None:
        scenario_path: Optional[str] = None
        if args.sim != "__DEFAULT__":
            # Also accept a tiny convenience syntax: --sim backend=mock
            raw = args.sim
            if isinstance(raw, str) and raw.startswith("backend="):
                effective_backend = raw.split("=", 1)[1]
            else:
                scenario_path = raw
        mode_label = {
            "carla": "SIM(CARLA)",
            "mock": "SIM(MOCK)",
            "detect": "SIM(AUTO)",
        }[effective_backend]
        print_banner(mode=mode_label)
        return run_simulation(
            scenario_path=scenario_path,
            headless=args.headless,
            backend=effective_backend,
        )

    print_banner(mode="DEMO")
    return run_demo()


if __name__ == "__main__":
    raise SystemExit(main())
