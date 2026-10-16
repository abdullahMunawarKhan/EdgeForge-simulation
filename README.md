# EdgeForge 🚗💨

> Autonomous driving simulation and risk-analysis platform built on CARLA.

EdgeForge wires a **CARLA** simulation layer into a **typed perception → risk-analysis pipeline** with a clean FastAPI dashboard surface. The stack is intentionally split so that non-simulation modules (config, data, perception, analysis, utils) are testable **without a running CARLA instance**.

---

## 📁 Project Layout

```
EdgeForge-env/
├── .venv/                         <-- (gitignored) local interpreter
├── .gitignore                     <-- global ignores (Python, .env, CARLA, ML weights)
├── .gitattributes                 <-- cross-platform line endings / binary tags
├── pyproject.toml                 <-- pytest, ruff, mypy, packaging
│
└── edgeforge/                     <-- the EdgeForge Python package
    ├── main.py                    <-- entry point (demo / serve / run CLI)
    ├── requirements.txt           <-- starter deps (install with pip)
    ├── .env.example               <-- copy to `.env` and customise
    │
    ├── analysis/                  <-- RiskEngine + (soon) ScenarioEvaluator
    │   └── risk_engine.py
    ├── config/                    <-- pydantic-settings global config
    │   └── settings.py
    ├── data/                      <-- shared Pydantic models & contracts
    │   └── models.py
    ├── perception/                <-- CameraProcessor + ObjectDetector + tracking
    │   ├── camera.py
    │   └── detector.py
    ├── scenarios/
    │   ├── configs/               <-- hand-authored scenario JSON
    │   │   └── default_scenario.json
    │   └── generated/             <-- (gitignored JSON, keep the .gitkeep)
    ├── simulation/                <-- **ONLY** place that imports carla
    │   ├── camera_test.py
    │   ├── spawn_vehicle.py
    │   └── test_connection.py
    └── utils/
        └── logger.py              <-- Loguru get_logger(__name__)
```

---

## 🚀 Quick Start (5 commands)

```bash
# 1. (Optional, recommended) Use the pre-created .venv or make your own:
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# 2. Install dependencies
cd edgeforge
pip install -r requirements.txt

# 3. Create your environment file
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux

# 4. Run the self-contained demo pipeline (no CARLA needed!)
python main.py demo

# 5. Later — start CARLA, then run your first scenario
python main.py run scenarios/configs/default_scenario.json
```

## Live Dashboard API

The read-only FastAPI service starts in the same process as its frame producer
so endpoints can share the real pipeline state. Choose one CARLA producer. To
run the managed scenario pipeline from the repository root:

```powershell
$env:API_HOST = "127.0.0.1"
$env:API_PORT = "8000"
python -m edgeforge.main --sim --backend carla --headless
```

Set `VITE_EDGEFORGE_API_URL=http://127.0.0.1:8000` in
`frontend/.env.local`, then start the frontend. The backend defaults to
`127.0.0.1:8000`; to access it from another computer, set `API_HOST=0.0.0.0`,
allow the port through the backend computer's firewall, and configure
`EDGEFORGE_CORS_ORIGINS` with the dashboard's exact origin. Configure the
frontend URL with the backend computer's LAN address, not the CARLA address.

To use the standalone YOLO camera test as the dashboard's Front-camera
producer instead, stop the managed simulation and any separate API process,
then run this from the repository root:

```powershell
python -m edgeforge.perception.yolo_camera_test
```

The script starts the API on the configured `API_HOST`/`API_PORT` and publishes
its real Front frames and YOLO detections to that in-process API. Run only one
copy of the script; it spawns its own CARLA vehicle and cameras. Do not run it
at the same time as the managed scenario runner, which also owns CARLA actors
and the API port.

Implemented endpoints:

- `GET /api/v1/simulation/status`
- `GET /api/v1/simulation/snapshot`
- `WS /api/v1/simulation/ws`
- `GET /api/v1/simulation/reports/latest`
- `GET /api/v1/simulation/camera/status`
- `GET /api/v1/simulation/camera/front/stream` (MJPEG)
- `GET /api/v1/simulation/camera/right_side/stream` (MJPEG)
- `GET /api/v1/simulation/camera/top_down/stream` (MJPEG)

When no simulation is publishing, status is `disconnected` and live fields are
unavailable; no sample data is returned. The snapshot includes measured pipeline
frame/detection counts and pipeline status, not validation precision/recall unless
those values are present in the saved validation report. The latest report is
read from `runs/phase4-live-validation.json`; generate it with
`python -m edgeforge.simulation.validate_carla_perception` while CARLA is
available. Simulation start/stop and configuration endpoints are not implemented.

Do not run a separate `uvicorn edgeforge.api:app` process for live simulation
data: a separately launched process has no access to its producer's in-memory
pipeline and will correctly report disconnected.

The managed `ScenarioRunner` attaches front, right-side, and top-down RGB
sensors to its existing ego vehicle. Camera images are published only when
captured on the same simulator frame. The top-down mount is 20 metres above the
ego with pitch `-90°`. The front view uses detections from the existing
`PerceptionPipeline` and is annotated on a bounded background encoder queue;
the side and top-down views are live RGB feeds without YOLO boxes, since those
boxes are produced from the front-camera pipeline. The old
`/api/v1/simulation/camera/stream` route remains a front-view alias. The
standalone `edgeforge.perception.yolo_camera_test` script also publishes its
Front frames and detections to an API it starts in the same process; use it
instead of, not alongside, the managed simulation.

---

## 🐍 Running Tests

```bash
pytest                          # all tests
pytest -m "not carla"           # skip tests that need a running CARLA server
pytest --cov=edgeforge          # with coverage
```

---

## 🔐 Secrets / Env Files

**Never commit a real `.env` file.** The root `.gitignore` already blocks:

```
.env
.env.*
!.env.example
```

Copy `.env.example` → `.env` and fill in your local values. `pydantic-settings` will pick them up automatically.

---

## 🧱 Architectural Rules (non-negotiable)

1. **Simulation code is quarantined.** Only `edgeforge/simulation/**` is allowed to `import carla`. Everything else must work offline.
2. **Typed contracts between layers.** Data crosses package boundaries as `pydantic` models from `edgeforge/data/models.py`. See: `VehicleState`, `DetectedObject`, `RiskAssessment`.
3. **Deterministic starter implementations.** Before YOLO/CARLA plug in, every module returns a **clearly-labelled** placeholder result — never fake "detections" or pretend AI is working.
4. **Pytest green on every PR.** Tests that actually need CARLA are tagged `@pytest.mark.carla` and skipped by default in CI.

---

## 🤝 Team Workflow

See the chat history / your internal docs for the **team-of-4 role breakdown** (Simulation · Perception · Risk+Data · Platform+UI). Weekly integration slot: Friday 3–5pm end-to-end pipeline run.

---

## 🛣️ Roadmap (high-level)

| Quarter | Milestone |
|---|---|
| Q0 (now) | ✅ Foundation: typed modules + demo pipeline run without CARLA |
| Q1 | CARLA integration + YOLO 2D detection + rule-based RiskEngine |
| Q2 | Distance estimation + tracker + scenario matrix generator |
| Q3 | FastAPI dashboard, scenario-evaluator metrics, Parquet exports |
| Q4 | LiDAR, sensor fusion, learned risk model, public demo |
