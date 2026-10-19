# EdgeForge Simulation Repository — Current Status & Technical Audit

**Generated:** October 17, 2026  
**Repository:** `EdgeForge-simulation`  
**Target Environment:** Windows, Python 3.10+, CARLA 0.9.16, React 18 / Vite  
**Inspection Type:** Evidence-based static analysis of code, configurations, logs, and verification runs (Zero file modifications, zero synthetic metric fabrication).

---

## Executive Summary

EdgeForge is an autonomous driving perception and edge-case validation platform structured in two complementary layers:
1. **Python Core:** A modular pipeline connecting CARLA simulation (or pure-Python mock doubles) to YOLOv8 object detection, IoU multi-object tracking, monocular distance/relative-speed estimation, explainable rule-based risk scoring, ground-truth bounding box validation, failure categorization, and failure-guided scenario generation.
2. **Frontend Dashboard:** A React 18/Vite web application providing an offline presentation demo and a dedicated live monitoring dashboard communicating with an in-process FastAPI service.

**Current Operational Reality:** The software architecture, algorithmic validation math, Pydantic contracts, and API streaming protocols are complete and verified by automated unit/integration test suites (12 camera/API tests, 8 frontend tests, 20 Scenario Lab tests). Live multi-camera streaming (Front, Right-Side, Top-Down) has been verified via headless smoke test against CARLA 0.9.16. However, full closed-loop automated testing with dense traffic in CARLA crashed during Windows initialization, meaning live end-to-end browser visualization with non-empty YOLO detections and live failure generation remains unverified in real time.

---

## 1. Architecture & Structure

### Repository File Tree & Component Roles

```text
EdgeForge-env/
├── .env / .env.example              # CARLA host/port, YOLO weights, camera & risk config
├── pyproject.toml / requirements.txt# Python dependencies, pytest, and lint configs
├── runs/                            # Validation reports, failure records & benchmark storage
│   ├── benchmarks/                  # Benchmark execution outputs (e.g. bmk_777_mock)
│   └── history/                     # RunHistoryStore (runs/*.json, failures/*.jsonl)
├── edgeforge/                       # Core Python Package
│   ├── main.py                      # CLI entry point (demo mode & --sim scenario orchestration)
│   ├── api.py                       # Read-only FastAPI service, WebSocket, & MJPEG encoder
│   ├── config/settings.py           # Centralized Pydantic BaseSettings
│   ├── data/
│   │   ├── models.py                # Typed contracts: DetectedObject, RiskAssessment, PerceptionFailureRecord
│   │   └── history.py               # RunHistoryStore: atomic persistence, indexing, coverage query
│   ├── perception/
│   │   ├── camera.py                # BGR frame validation, resize, & normalization
│   │   ├── detector.py              # Ultralytics YOLO adapter & COCO-to-domain mapping
│   │   ├── tracker.py               # Frame-to-frame IoU association & object ID tracking
│   │   ├── distance_estimator.py    # Monocular camera geometry & closing-speed estimation
│   │   ├── pipeline.py              # End-to-end perception pipeline orchestration
│   │   ├── validation.py            # CARLA 3D-to-2D GT projection, 1-to-1 IoU matching, failure detection
│   │   └── yolo_camera_test.py      # Standalone single-camera live YOLO producer
│   ├── analysis/
│   │   └── risk_engine.py           # Deterministic heuristic hazard & closing-speed risk engine
│   ├── scenarios/
│   │   ├── configs/                 # Declarative scenario JSONs (e.g. default_scenario.json)
│   │   ├── generator.py             # Next-best scenario generator (coverage novelty + failure history)
│   │   ├── executor.py              # ScenarioExecutionManager & parameter bounds validator
│   │   └── benchmark.py             # Closed-loop benchmark (Failure-guided vs Uniform random)
│   ├── simulation/
│   │   ├── carla_client.py          # CARLA connection lifecycle, sync mode, & weather presets
│   │   ├── actor_manager.py         # Ego vehicle & TrafficManager NPC traffic spawner
│   │   ├── sensor_manager.py        # Front, top-down camera mounts & collision sensors
│   │   ├── scenario_runner.py       # Synchronous scenario frame loop & backend selector
│   │   ├── validate_carla_perception.py # Standalone CLI for live CARLA GT-versus-YOLO validation
│   │   └── mock_*.py                # Synthetic test doubles for offline validation
│   └── utils/logger.py              # Loguru structured logging wrapper
└── frontend/                        # React 18 / Vite / Tailwind Dashboard
    ├── src/
    │   ├── pages/                   # Overview, LiveSimulation, ScenarioLab, FailureAnalysis, CoverageExplorer
    │   ├── components/layout/       # CameraFeed.jsx (front and top-down MJPEG views)
    │   ├── hooks/                   # useLiveSimulation.js (WebSocket with REST polling fallback)
    │   ├── services/                # liveSimulation.js, cameraFeed.js (API client endpoints)
    │   └── data/                    # Bundled offline presentation demo dataset & labels
    └── planning/                    # Phase 0–6 roadmap and contract specifications
```

---

## 2. Connections & Interface Verification

| Connection | Status | Evidence & Verification Details |
|---|---|---|
| **Frontend ↔ FastAPI** | **Verified** | Configured via `VITE_EDGEFORGE_API_URL` (default: `http://127.0.0.1:8000`). `useLiveSimulation.js` fetches `/status`, opens WebSocket `/ws`, and gracefully degrades to 5000ms polling on REST `/snapshot`. CORS middleware allows ports 5173 and 5174. |
| **CARLA ↔ Python** | **Verified** | Target configured in `.env` (`CARLA_HOST=192.168.96.145`, `CARLA_PORT=2001`). Connects via `carla.Client` with synchronous mode (`fixed_delta_seconds=0.05`). Teardown safely restores original world settings. |
| **API / WebSocket Streaming** | **Verified** | In `api.py`, `WS /api/v1/simulation/ws` sends initial snapshot and pushes new snapshots on version increment. REST fallback `/api/v1/simulation/snapshot` functions concurrently. |
| **2 CARLA Camera Feeds** | **Verified (Headless) / Unverified (Browser)** | `sensor_manager.py` attaches front `(x=1.5, z=2.4)` and top-down `(z=20.0, pitch=-90°)` cameras. Background thread encodes JPEGs. Endpoints `/api/v1/simulation/camera/{front,top_down}/stream` stream multipart MJPEG. Live browser rendering with moving traffic remains unverified. |

---

## 3. YOLO Perception Pipeline

* **Tested Object Classes:** 80 COCO classes normalized through `COCO_CLASS_MAP` in `detector.py`. Primary evaluated classes in `validation.py` (`SUPPORTED_EVALUATION_CLASSES`): `car`, `pedestrian`, `truck`, `bus`, `motorcycle`, `bicycle`, `traffic_light`, `stop_sign`.
* **Bounding Boxes & Coordinates:** Evaluated in pixel coordinates `[x1, y1, x2, y2]`. Scaled and validated via `CameraProcessor`.
* **Confidence Scores:** Range `[0.0, 1.0]`. Default detector threshold is 0.15; configured threshold in `.env` is 0.5.
* **Propagation to API & Dashboard:**
  * In `main.py`, `process_frame()` emits `DetectedObject` instances to `runtime.publish_frame()`.
  * `api.py` includes detections in `snapshot["detections"]` (REST & WebSocket).
  * `render_detections()` overlays bounding boxes, class labels, and confidence directly onto the Front camera MJPEG stream.
* **Verification Gap:** Live smoke test utilized zero-traffic scenario, yielding `len(detections) == 0`. Live perception inference in real time under active traffic has not been demonstrated end-to-end.

---

## 4. Traffic & Scenario Generation Parameters

| Parameter | Implemented in Code? | Applied to CARLA? | Verification Notes |
|---|---|---|---|
| **Weather (Presets)** | Yes | Yes | `carla_client.set_weather_preset()` supports all standard presets (e.g. `ClearNoon`, `WetSunset`). |
| **Weather (Continuous)** | Yes | Yes | `carla_client.set_weather()` applies `cloudiness`, `precipitation`, `fog_density`, `wetness`, `wind_intensity`. |
| **Lighting / Sun Angle** | Yes | Yes | `sun_altitude_angle` (-15° to 85°) and `sun_azimuth_angle` (0° to 360°) applied to world settings. |
| **Traffic Density** | Yes | Yes | `actor_manager.spawn_traffic()` spawns counts for `vehicles`, `pedestrians`, and `bicycles`. |
| **Actor Movement** | Yes | Yes | Vehicles navigate via `TrafficManager` autopilot. Pedestrians navigate via `controller.ai.walker` across navmesh. |
| **Actor Distance** | Partial | Partial | Controlled target distances (8m–35m) are applied only in `validate_carla_perception.py`. Default scenario has no fine-grained distance control. |
| **Occlusion** | Partial | Natural only | Visual occlusion occurs naturally in 3D CARLA rendering. Dynamic occlusion meshes are rejected as unsupported (`KNOWN_UNSUPPORTED_PARAMETERS`). |
| **Actor Behaviour** | No | No | Parameters like `adversarial_cut_in`, `emergency_braking_trigger`, and `pedestrian_jaywalking_trajectory` are explicitly rejected by `generator.py` and `executor.py`. |
| **Frontend Live Controls** | UI only | **No** | Weather/traffic sliders on `LiveSimulationPage.jsx` are strictly **local preview-only** and do not command CARLA. |

---

## 5. AI Pipeline Tracing & Loop Continuity

```text
[1. Scenario Generator] (generator.py)
        │ Proposes Candidate Scenario (Weather, Map, Traffic)
        ▼
[2. Scenario Runner] (scenario_runner.py / carla_client.py)
        │ Applies parameters, spawns ego vehicle & TrafficManager actors
        ▼
[3. Sensor Manager] (sensor_manager.py)
        │ Emits 3 synchronized BGR frames (Front, Right-Side, Top-Down)
        ▼
[4. Perception Pipeline] (detector.py + tracker.py + distance_estimator.py)
        │ YOLO inference → IoU tracking → monocular distance & closing speed
        ▼
[5. Risk Engine] (risk_engine.py)
        │ Deterministic heuristic score [0.0–1.0], hazard level, contributing IDs
        ▼
[6. FastAPI Runtime] (api.py)
        │ Emits REST snapshots, WebSocket updates, and 3 MJPEG video streams
        ▼
[7. React Dashboard] (LiveSimulationPage.jsx + CameraFeed.jsx)
        │ Displays HUD, detections table, risk level, and video feeds
        │
   ═════╪══════════════════════════════════════════════════════════════════
   CRITICAL GAP: The live loop breaks here during runtime simulation.
   ═════╪══════════════════════════════════════════════════════════════════
        │
        ├─► [8. Ground-Truth Validation] (validation.py)
        │   * Projects CARLA 3D actor boxes to 2D camera coordinates.
        │   * Matches 1-to-1 with YOLO predictions (IoU >= 0.5).
        │   * NOT CALLED by main.py during simulation runs!
        │   * Only executed in offline validate_carla_perception.py CLI.
        │
        ├─► [9. Failure Detection & Fingerprinting] (validation.py / benchmark.py)
        │   * Categorizes: missed_detection, false_positive, poor_localization, low_confidence.
        │   * Fingerprints: (failure_type, object_class, severity, weather_lighting_bin).
        │
        ├─► [10. Historical Store] (history.py)
        │   * Persists runs/<run_id>.json and failures/<run_id>.jsonl.
        │
        └─► [11. Next-Best Scenario] (generator.py)
            * Ranks next test using coverage novelty + failure history.
            * Closed loop runs in offline benchmark.py, NOT live in dashboard.
```

---

## 6. Failure Fingerprints, History & Logging

* **Failure Fingerprint Signature:** Implemented in `benchmark.py` via `compute_failure_signature()`. Uses a canonical 4-tuple: `(failure_type, object_class, severity, weather_lighting_bin)`.
* **Storage Architecture:** `edgeforge/data/history.py` implements `RunHistoryStore`. It stores complete run metadata in `runs/<run_id>.json` and line-delimited records in `failures/<run_id>.jsonl` using atomic tempfile writes and fsync.
* **Query & Indexing:** `index.json` maintains an aggregate summary for rapid retrieval. The store provides `get_run()`, `get_run_failures()`, `filter_failures()`, and `compute_coverage()`.
* **Reproducibility & Replay:** Deterministic execution is supported via fixed random seeds (`random.Random(42)`) and synchronous delta steps (`0.05s`). However, no UI button exists to replay a historical run.
* **Existing Run Logs in Workspace:**
  * `runs/history/runs/` and `runs/history/failures/` are currently empty in the repository.
  * Latest validation report read by the API is `runs/phase4-live-validation.json` (produced by running `validate_carla_perception.py`).

---

## 7. PPT Roadmap Alignment & Status Classification

Classifications:
* **Verified:** Code exists, automated unit/integration tests pass, and functionality confirmed.
* **Partial:** Substantial code exists and works in isolation/tests, but lacks live integration or has restricted scope.
* **Unverified:** Implemented in code, but pending end-to-end execution against live simulator/browser with real traffic.
* **Missing:** Not implemented or explicitly excluded from the current scope.
* **Blocked:** Implementation attempted or planned, but obstructed by external runtime crashes or dependencies.

| Roadmap Milestone / Phase | Classification | Evidence & Status Summary |
|---|---|---|
| **Phase 0: Foundation & Contracts** | **Verified** | Shared Pydantic schemas (`models.py`), settings loader (`settings.py`), logging (`logger.py`), and TypeScript/JSDoc types (`types.js`). |
| **Phase 1: Landing Page & Overview** | **Verified** | Hero component, platform overview, navigation tabs, metrics summary cards. Fully functional in React. |
| **Phase 2: Workflow Demonstration** | **Verified** | Interactive 5-step workflow explorer showcasing the perception-to-validation pipeline. |
| **Phase 3: Scenario Lab & Preview** | **Partial** | Declarative scenario authoring, parameter sliders, and 2D canvas preview function properly. Live parameter application to CARLA is **Missing** (controls are local preview-only). |
| **Phase 4: Ground-Truth Validation** | **Partial** | Complete 3D-to-2D box projection, IoU matching, metric calculation (`precision`, `recall`, `f1`), and failure categorization implemented in `validation.py`. However, it is **Missing** from `main.py` live loops and requires manual CLI execution. |
| **Phase 4A: Failure History & Storage** | **Verified** | `RunHistoryStore` in `history.py` provides atomic JSON/JSONL persistence, summary indexing, and coverage matrix computation. |
| **Phase 5: Next-Best Scenario Generator** | **Partial** | Ranking engine in `generator.py` combines failure evidence, coverage novelty, and similarity. Frontend displays recommendations. Automated closed-loop dispatch to CARLA from the UI is **Missing**. |
| **Phase 6: Two-Camera Live Dashboard** | **Unverified** | 2-view MJPEG streaming (`front`, `top_down`); live browser rendering with real traffic and active detections remains unverified. |
| **CARLA Traffic Simulation** | **Blocked** | Default scenario with 5 vehicles, 10 pedestrians, and 2 bicycles in Town03 causes Windows startup crash. |
| **Advanced Perception (LiDAR / Fusion)** | **Missing** | LiDAR, radar, and sensor fusion disabled in scenario configs; monocular RGB only. |
| **Adversarial Behaviors (Cut-in, Jaywalking)** | **Missing** | Explicitly classified as `KNOWN_UNSUPPORTED_PARAMETERS` in `generator.py`. |

---

## 8. Critical Blockers, Issues & Prioritized Next Steps

### Critical Blockers & Broken Connections
1. **CARLA Traffic Initialization Crash:** Attempting to run `python -m edgeforge.main --sim` with the default traffic scenario terminated unexpectedly on Windows during actor allocation.
2. **Disconnected Live Validation:** `edgeforge/main.py` executes perception and risk scoring, but **does not call** `validation.py` to evaluate ground truth or generate `PerceptionFailureRecord`s during the live run.
3. **Read-Only API Surface:** The FastAPI service only implements `GET` and `WS` endpoints. There are no endpoints to accept scenario configs, start/stop simulations, or apply parameter changes from the dashboard.
4. **Static Demo vs. Live Data Disconnect:** The frontend Scenario Lab, Failure Analysis, and Coverage pages rely on bundled static sample fixtures (`src/data/`) unless a static file `runs/phase4-live-validation.json` is manually generated.
5. **No Non-Zero Detections Live:** Because the smoke test ran with zero background traffic, no bounding box detections were recorded live on the camera feeds.

### Launch Commands for Implemented Capabilities

```powershell
# 1. Run Foundation Demo (No CARLA required; verifies pipeline & risk engine)
python -m edgeforge.main

# 2. Run Synthetic Mock Simulation with Live Dashboard API
python -m edgeforge.main --sim --backend mock --headless

# 3. Run Standalone CARLA Front-Camera + YOLO Producer
python -m edgeforge.perception.yolo_camera_test

# 4. Run Controlled Live CARLA Ground-Truth Validation (Outputs JSON & JSONL)
python -m edgeforge.simulation.validate_carla_perception --frames 50

# 5. Run Offline Closed-Loop Testing Strategy Benchmark
python -m edgeforge.scenarios.benchmark --iterations 10 --dry-run

# 6. Launch Frontend Dashboard
cd frontend
npm run dev
```

### Top 5 Prioritized Tasks

1. **Fix CARLA Traffic Spawning on Windows:** Debug and stabilize NPC actor allocation in `actor_manager.py` (specifically reducing spawn count or staggering batches) to prevent crashes in Town03.
2. **Wire Validation into the Live Simulation Loop:** Modify `main.py` so that when running against CARLA with ground truth available, `evaluate_detections()` is invoked every N frames and failures are streamed to `api.py`.
3. **Verify Live Browser Rendering with Active Detections:** Run the live simulation with a single foreground vehicle, open `http://localhost:5173/live`, and verify that bounding boxes and distance metrics render in real time on the Front camera view.
4. **Add Simulation Control Endpoints to FastAPI:** Implement `POST /api/v1/simulation/scenarios/run` and `POST /api/v1/simulation/control` to allow the Scenario Lab and Adaptive Recommendation modules to trigger runs directly.
5. **Populate Historical Run Store with Initial Validation Baseline:** Run a controlled 10-scenario validation sequence to generate real historical data in `runs/history/`, populating the Failure Analysis and Coverage Explorer heatmaps with authentic test data.
