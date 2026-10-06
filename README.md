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
