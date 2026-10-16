# EdgeForge — Product and Resume Reference

> A practical reference to the EdgeForge product, its implemented capabilities,
> architecture, verification status, and resume-ready descriptions.

## 1. Product at a glance

**EdgeForge** is an autonomous-driving perception and edge-case validation
platform built around the CARLA simulator. It connects simulated camera frames
to a computer-vision pipeline, estimates object distance and relative speed,
calculates explainable driving-risk assessments, and compares detections with
CARLA actor ground truth. A React dashboard provides both an explicitly
labelled static presentation mode and a separate live-data mode backed by a
read-only FastAPI service.

The product is designed to work in layers:

1. **Simulation:** CARLA or a Python mock backend supplies sensor frames and
   vehicle state.
2. **Perception:** Camera frames are checked and passed through YOLO detection,
   IoU tracking, and monocular distance/relative-speed estimation.
3. **Analysis:** A deterministic, rule-based risk engine scores the observed
   scene.
4. **Validation:** Projected CARLA actor boxes are matched to detections to
   produce object-detection metrics and structured failure records.
5. **Presentation:** A React/Vite application shows a static demo or data
   reported by the live backend; it does not silently mix the two.

**Important status qualification:** a controlled live smoke test has verified
the three managed CARLA camera feeds through the in-process API. The full
default traffic scenario and the live React browser presentation are not yet
verified end to end. Refer to
[Verification and live-readiness](#10-verification-and-live-readiness) before
describing the entire live chain as operational.

## 2. Problem and intended users

EdgeForge is intended to help autonomous-driving and ADAS teams exercise
perception systems in controllable simulated scenes and inspect where object
detection may fail. It brings together:

- A simulator-facing path for obtaining camera images and vehicle state.
- A shared typed interface between simulation, perception, and analysis.
- A baseline object-detection validation method using simulator ground truth.
- Structured records that make missed or poor detections easier to investigate.
- A dashboard that distinguishes actual live backend data from presentation
  examples.

It is a research and engineering platform, not a production autonomous-driving
stack. Its risk scoring is a transparent heuristic, not a certified safety
model.

## 3. Implemented capabilities

### Simulation and scenario execution

- A scenario runner supports a CARLA backend, a pure-Python mock backend, and
  an automatic detection mode that tries CARLA and can fall back to mock.
- Scenario configuration is JSON-based. The checked-in starter scenario is an
  urban Town03 scenario with a 60-second duration, an ego vehicle, configured
  traffic, an RGB camera, and collision/lane-invasion sensors.
- The managed runner owns the active CARLA client, actors, and sensors. The
  dashboard camera stream reuses its front RGB camera rather than launching a
  second camera pipeline.
- A headless mode is available for environments without an OpenCV display.
- CARLA-dependent utilities and validation require a reachable CARLA server
  and a compatible CARLA Python API installation.

### Perception pipeline

The core flow in `edgeforge/perception/pipeline.py` is:

```text
BGR camera frame
  → frame validation / camera processing
  → YOLO object detection
  → IoU-based multi-object tracking
  → monocular distance and relative-speed estimation
  → typed DetectedObject records
  → risk assessment
```

- The YOLO adapter returns detections with class, confidence, class ID, and
  image-space bounding box. Known COCO classes are mapped to domain labels
  such as `pedestrian`, `car`, `bicycle`, and `traffic_light`; other classes
  can be retained.
- The tracker associates detections using bounding-box IoU and maintains
  object identities over time.
- The distance estimator derives approximate distance from image geometry and
  uses temporal tracking to estimate relative speed. These are estimates, not
  direct ground-truth measurements.
- Shared Pydantic models, including `DetectedObject`, `VehicleState`,
  `RiskAssessment`, and `PerceptionFailureRecord`, define layer boundaries.
- The perception modules and mock simulation can be exercised without a
  running CARLA server.

### Explainable risk engine

`edgeforge/analysis/risk_engine.py` calculates a deterministic risk score in
the range 0–1. The current heuristic combines:

- A distance factor: nearer objects contribute more risk.
- A closing-speed factor: objects approaching the ego vehicle contribute more
  risk.
- A modest ego-speed amplifier.
- The highest per-object hazard as the overall score, with LOW, MEDIUM, HIGH,
  and CRITICAL buckets.

The engine also returns a human-readable explanation and IDs of contributing
objects. Missing distance or relative-speed information is represented as
incomplete context; this is not a learned model or full time-to-collision
calculation.

### CARLA ground-truth validation and failure reporting

`edgeforge/perception/validation.py` implements a CARLA-facing validation
workflow:

- Maps supported CARLA actor blueprints to detector-style object classes.
- Projects actor 3D bounding boxes into camera image coordinates using camera
  transforms and field of view, including clipping at the near plane.
- Matches predictions to ground truth by class and IoU using one-to-one
  associations.
- Calculates frame-level true positives, false positives, missed detections,
  precision, recall, and F1.
- Creates structured failure records for missed detections, false positives,
  poor localization, low confidence, confidence degradation where a valid
  baseline is available, and invalid boxes.
- Captures relevant conditions, class, confidence, boxes, IoU, severity, frame
  or scenario IDs, and actor ID when available.
- Supports configurable thresholds/severity rules and JSON or JSONL export.
- Handles absent metadata and invalid boxes without treating malformed data as
  a valid match.

The reproducible live validation entry point is
`python -m edgeforge.simulation.validate_carla_perception`; it requires CARLA
and is not a substitute for a live run having been verified.

### Dashboard and presentation modes

The frontend is a React 18 application built with Vite and styled with the
existing Tailwind/CSS design system. The landing page and static dashboard
remain the presentation fallback.

- **Static Demo** retains bundled sample runs, failures, scenario exploration,
  coverage views, failure analysis, adaptive recommendations, and guided-demo
  interactions. Demo content is presentation data, not output from a live
  CARLA run.
- **Live Simulation** reads the configured backend only. It shows connection
  state, status, snapshot values, detections, scenario conditions, metrics,
  risk assessment, and failure data when the backend publishes them.
- The live client uses REST snapshots/status and WebSocket updates, with REST
  polling for refresh/fallback. Missing backend data is shown as unavailable;
  the page does not replace it with static sample values.
- A disconnected live page gives a visible status and a direct switch to
  Static Demo.
- Live scenario controls for rain, fog, road wetness, traffic density, and
  lighting are a **local preview only**. They do not call a scenario-generation
  endpoint or change CARLA.

### Live API and camera stream

The FastAPI app exposes read-only endpoints:

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/simulation/status` | Current publishing/connection state and latest identifiers |
| `GET /api/v1/simulation/snapshot` | Latest available pipeline snapshot |
| `WS /api/v1/simulation/ws` | Initial snapshot followed by newly published snapshots |
| `GET /api/v1/simulation/reports/latest` | Latest saved Phase 4 validation report, if present |
| `GET /api/v1/simulation/camera/status` | Availability and frame/FPS metadata for all three views |
| `GET /api/v1/simulation/camera/front/stream` | MJPEG front view with pipeline YOLO overlays |
| `GET /api/v1/simulation/camera/right_side/stream` | MJPEG right-side RGB view |
| `GET /api/v1/simulation/camera/top_down/stream` | MJPEG top-down RGB view |

The managed runner attaches front, right-side, and top-down sensors to the
existing ego vehicle; top-down is mounted 20 metres above it with pitch
`-90°`. It publishes only same-simulator-frame images. The camera JPEG encoder
uses a bounded background queue so stale frames can be dropped instead of
holding up the simulation callback. YOLO boxes are overlaid on the front view
from the existing perception pipeline; side and top-down are live RGB views
without those front-camera detections. The old `/camera/stream` route remains a
front-view alias.

The API runtime stores data in process memory. For live snapshots and camera
frames, start the API from the same frame-producing process; a separately
launched API process will not share that in-memory state. The managed runner
publishes frames from its `PerceptionPipeline`. The standalone
`edgeforge.perception.yolo_camera_test` can also run as the sole CARLA producer:
it starts the API in-process and publishes its actual Front frames and YOLO
detections. Do not run that script alongside the managed runner or another API
process; it creates its own CARLA actors and needs the configured API port.
Simulation start/stop and scenario-control endpoints are intentionally not
implemented.

## 4. Architecture and key code areas

```text
CARLA / mock scenario runner
  ├─ RGB camera + vehicle state + scenario metadata
  ├─ collision and lane-invasion events
  └─ managed sensor/actor lifecycle
         ↓
PerceptionPipeline
  ├─ CameraProcessor
  ├─ ObjectDetector (YOLO)
  ├─ ObjectTracker (IoU)
  └─ DistanceEstimator
         ↓
DetectedObject[] ──→ RiskEngine ──→ RiskAssessment
         │
         ├─→ FastAPI in-process runtime ──→ REST / WebSocket
         │                                       └─→ three MJPEG views (front annotated; side/top-down RGB)
         └─→ CARLA ground-truth validation ──→ metrics / failure report

React/Vite frontend
  ├─ Static Demo: bundled presentation dataset
  └─ Live Simulation: configured API data only
```

Key files:

- `edgeforge/main.py` — CLI, mock/demo mode, CARLA/mock simulation orchestration,
  pipeline and risk wiring, and API publication.
- `edgeforge/simulation/scenario_runner.py` — scenario lifecycle and backend
  selection.
- `edgeforge/simulation/sensor_manager.py` — managed CARLA sensor and frame
  delivery.
- `edgeforge/perception/camera.py` — frame validation and image processing.
- `edgeforge/perception/detector.py` — YOLO adapter and class normalization.
- `edgeforge/perception/tracker.py` — IoU matching and track state.
- `edgeforge/perception/distance_estimator.py` — distance and relative-speed
  estimates.
- `edgeforge/perception/pipeline.py` — end-to-end perception composition.
- `edgeforge/analysis/risk_engine.py` — explainable deterministic risk score.
- `edgeforge/perception/validation.py` — ground-truth projection, matching,
  metrics, and failure reports.
- `edgeforge/data/models.py` — shared Pydantic data contracts.
- `edgeforge/config/settings.py` — environment-backed project settings.
- `edgeforge/api.py` — read-only API, live runtime state, and MJPEG encoder/
  stream.
- `frontend/src/pages/HomePage.jsx` — mode selection and preservation of the
  static dashboard.
- `frontend/src/pages/LiveSimulationPage.jsx` — live status, data, and
  preview-only scenario controls.
- `frontend/src/components/layout/CameraFeed.jsx` — camera stream status and
  view.
- `frontend/src/services/liveSimulation.js` and
  `frontend/src/services/cameraFeed.js` — frontend API URL construction and
  client behavior.

## 5. Technology stack

| Area | Technologies |
|---|---|
| Language/runtime | Python 3.10+ (project metadata), JavaScript, JSX |
| Simulation | CARLA Python API, managed scenario/sensor runner, mock simulator |
| Perception | Ultralytics YOLO, PyTorch, NumPy, OpenCV |
| Tracking/geometry | IoU association, camera projection, monocular estimates |
| Data contracts/config | Pydantic, pydantic-settings, python-dotenv |
| Backend | FastAPI, Uvicorn, REST, WebSocket, MJPEG |
| Frontend | React 18, Vite, Tailwind CSS |
| Quality | pytest, pytest-cov, Node test runner, Ruff/mypy configuration |

The CARLA API distribution is installed separately to match the CARLA server
version. The selected model weights and CUDA/PyTorch build are environment
dependent; a GPU is optional for development but may improve YOLO inference
performance when correctly configured.

## 6. Configuration and running

### Configuration

The root `.env` is local configuration and should not be committed. Use
`.env.example` as the template. `edgeforge/config/settings.py` centralizes
settings for:

- CARLA host, port, and connection timeout.
- API host and port.
- Camera dimensions, field of view, and capture tick.
- YOLO model path, device, confidence threshold, and tracker thresholds.
- Risk threshold and output directories.

Environment variables override values in the root `.env`, which override
declared defaults. For remote dashboard access, bind the backend to an
appropriate interface, configure the backend CORS allowlist, open the backend
port as needed, and set the frontend's `VITE_EDGEFORGE_API_URL` to the backend
address. The CARLA address and dashboard backend address are separate settings.

### Common development commands

Run commands from the repository root unless noted:

```powershell
# Foundation/demo mode; does not require a running CARLA server
python -m edgeforge.main

# Synthetic simulation backend; no CARLA server required
python -m edgeforge.main --sim --backend mock --headless

# Force a real CARLA run (requires the configured server)
python -m edgeforge.main --sim --backend carla --headless

# Run Python tests
pytest

# Run only tests that do not require CARLA
pytest -m "not carla"

# Frontend development server
cd frontend
npm install
npm run dev

# Frontend tests and production build
npm test
npm run build
```

The project API starts as part of the simulation command. Do not run a separate
`uvicorn edgeforge.api:app` process expecting it to see the simulation's
in-memory data. Configure `VITE_EDGEFORGE_API_URL` in `frontend/.env.local`,
then restart Vite after changing the frontend environment file.

To generate the live CARLA perception validation report, start/ensure CARLA is
available and run:

```powershell
python -m edgeforge.simulation.validate_carla_perception
```

The latest-report API reads `runs/phase4-live-validation.json` when a report
exists.

## 7. Verification and test coverage

The automated suite includes offline/mock tests for:

- Shared settings, models, camera processing, detector behavior, and risk
  levels.
- Mock simulation client, actors, sensors, and scenario execution.
- Pipeline integration and distance/relative-speed output.
- CARLA actor projection and class-aware detection matching with test doubles.
- Precision/recall/F1, failure classifications, severity rules, JSON/JSONL
  serialization, and malformed input handling.
- API disconnected and available states, REST data, WebSocket snapshots,
  report handling, camera availability, MJPEG framing, and stream cleanup.
- Frontend API URL construction, unavailable/error states, preview defaults and
  payload shape, and camera feed URL behavior.

**Current camera-change verification:** the full Python suite and Python
compilation passed; the focused camera/API tests passed (12 tests); all 8
frontend tests and the Vite production build passed. Ruff was not installed in
the environment.

Unit tests with mocks establish application behavior under controlled
conditions; they do not prove that the remote CARLA server, GPU, YOLO model,
network, and browser all work together in real time.

## 8. Current limitations and pending integration

- **The managed three-view camera path was live-smoke-tested.** On 2026-10-16,
  CARLA 0.9.16 at the configured host accepted the client; front, right-side,
  and top-down camera statuses all reported available on the same frame ID,
  and each MJPEG endpoint returned HTTP 200 with a multipart response. The
  smoke scenario ran with one ego vehicle and no background traffic; after
  shutdown, CARLA reported zero remaining vehicles, walkers, and RGB sensors.
- **The full default traffic scenario is not verified.** An attempt to start
  the default traffic-heavy scenario terminated unexpectedly during Windows
  startup. The successful live camera smoke used a temporary zero-traffic
  scenario instead.
- **Live browser rendering and non-empty live detections remain unverified.**
  The live API stream was exercised, but the React dashboard was not connected
  to that short run in a browser. YOLO weights loaded during the smoke, but the
  observed detection count was zero.
- **GPU inference is environment-dependent.** A GPU-equipped CARLA PC must
  have compatible GPU drivers, PyTorch/CUDA, model weights, and configuration.
- **Scenario controls are preview-only.** Rain, fog, wetness, traffic, and
  lighting controls currently prepare a local payload; no backend endpoint
  applies them to CARLA.
- **YOLO overlays currently apply to the front view only.** Side and top-down
  are live camera feeds; front-camera detections are not projected onto those
  different viewpoints.
- **No simulation-control endpoints exist.** The API is read-only by design;
  start/stop, scenario generation, and configuration changes need a safe
  control/lifecycle design before implementation.
- **Validation metrics require a validation run/report.** The normal live
  snapshot reports pipeline status and counts, not precision/recall unless
  validation data is separately produced.
- **Perception estimates have scope limits.** Monocular distance and relative
  speed are approximate. Risk scoring is heuristic and is not lane-aware,
  weather-aware, or a certified safety assessment.
- **Additional sensors and advanced models remain future work.** LiDAR and
  sensor fusion, learned risk prediction, and broader scenario-matrix
  execution are not established as complete live capabilities.
- **Static Demo data is not live evidence.** Keep that distinction explicit in
  presentations and portfolio material.

## 9. Resume-ready material

### One-line project description

> Built EdgeForge, a CARLA-based ADAS perception-validation platform combining
> YOLO object detection, temporal tracking, monocular distance estimation,
> explainable risk scoring, ground-truth evaluation, and a React monitoring
> dashboard.

### Resume bullets

Choose only bullets that match the work you personally performed, and retain
the live-verification qualification where applicable.

- Designed a modular Python perception pipeline integrating camera-frame
  validation, YOLO detections, IoU object tracking, and monocular
  distance/relative-speed estimates using shared Pydantic contracts.
- Implemented a deterministic, explainable risk engine that combines object
  proximity and closing speed into risk scores and severity bands with
  contributing-object explanations.
- Built CARLA ground-truth evaluation using projected actor bounding boxes and
  class-aware IoU matching; calculated precision, recall, F1, false positives,
  and missed detections.
- Added structured perception-failure records for localization, confidence,
  missed-detection, false-positive, and invalid-box issues, with configurable
  severity rules and JSON/JSONL export.
- Developed a read-only FastAPI interface with REST snapshots, WebSocket live
  updates, validation-report access, and an MJPEG stream sourced from the
  three synchronized views attached to the managed CARLA ego vehicle.
- Extended a React/Vite dashboard with a clearly separated live mode and
  offline static demo, explicit disconnected/unavailable states, and
  preview-only scenario configuration.
- Added mock-based Python/API and frontend tests to exercise offline behavior
  without requiring a running CARLA instance.

### Project description for a resume or portfolio

**EdgeForge | ADAS Edge-Case Perception Validation Platform**

Developed a modular simulation and perception-validation platform connecting
CARLA camera output to a YOLO-based detection and tracking pipeline, approximate
distance/relative-speed estimation, and an explainable rule-based risk engine.
Implemented CARLA actor-box projection and IoU-based matching to evaluate
precision, recall, F1, missed detections, and false positives, with structured
failure reports. Built a FastAPI live-data interface and a React dashboard
that preserves a separate offline demo mode. Live CARLA/GPU/browser end-to-end
operation remains pending validation against an available CARLA server.

### Skills represented by the project

Python · React · JavaScript · FastAPI · CARLA · computer vision · YOLO ·
PyTorch · OpenCV · NumPy · Pydantic · REST APIs · WebSockets · simulation ·
object tracking · IoU evaluation · test automation · frontend integration

### Claims to avoid until verified or implemented

- Do not claim a complete live CARLA-to-browser deployment has been tested.
- Do not claim the preview controls modify CARLA weather or traffic.
- Do not claim the camera selector supports multiple live viewpoints.
- Do not describe heuristic risk scores as a learned, production, or certified
  safety model.
- Do not quote detection accuracy or latency without a reproducible measured
  validation report and the associated scenario/model/hardware details.
- Do not present bundled Static Demo records as actual simulation results.

## 10. Verification and live-readiness

The controlled camera integration smoke test verified the CARLA connection,
managed camera sensors, and three API streams. A complete product demonstration
still requires all of the following to be confirmed together:

1. CARLA is running on the configured host/port and accepts a client
   connection.
2. The CARLA Python API version is compatible with the server.
3. The managed runner receives fresh synchronized frames from all three
   cameras. **Verified in the controlled smoke test.**
4. The configured YOLO weights load on the selected CPU/GPU device.
   **Weights loaded on CPU; a non-empty detection was not observed.**
5. The perception pipeline publishes useful detections and estimated object
   fields. **Not yet verified with a positive live detection.**
6. The in-process FastAPI service publishes all three MJPEG streams.
   **HTTP 200 responses and live frame availability verified.**
7. The React frontend is configured with the backend URL and visibly displays
   all three live feeds, metadata, and detections. **Not yet verified in a
   browser during the live run.**
8. CARLA ground-truth validation completes and produces a report, if reporting
   metrics is part of the demonstration. **Not verified in this smoke test.**

Describe the three-camera CARLA-to-API path as live-smoke-tested, while
qualifying full dashboard presentation, positive YOLO detections, and the
default traffic scenario as still unverified.
