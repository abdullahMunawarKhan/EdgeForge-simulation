# Phase 3 — Scenario Lab & Illustrative Simulation Preview (React JSX)

## Coding Agent Prompt

Build only the Scenario Lab and its illustrative scene preview for EDGEFORGE. Use Phase 0 shared JavaScript contracts/design tokens. Keep this module self-contained; do not implement failure dashboard, coverage explorer, or adaptive recommendation panel.

### Purpose
Let a jury member configure a scenario and see a clearly labelled illustrative result. Communicate what EDGEFORGE could configure before an actual CARLA simulation is connected.

### Scenario controls
Provide compact, accessible controls for:
- Weather: Clear / Rain / Fog
- Lighting: Day / Sunset / Night
- Traffic density: Low / Medium / High
- Road user: Vehicle / Pedestrian / Cyclist
- Occlusion: None / Partial / High
- Distance: Near / Medium / Far

Show a live configuration summary and readable scenario label/ID. Use plain JavaScript objects matching the shared `ScenarioConfig` shape.

### Preview panel
Create a lightweight visual panel with:
- Road / driving-scene image, CSS illustration, or available asset.
- Camera-view framing.
- Optional illustrative bounding boxes/labels.
- Selected conditions displayed as overlays or badges.
- `DEMO MODE` / `PREVIEW` status.

The scene can adapt labels, overlay treatment, or weather tint based on selected controls. Do not build a complex 3D simulator. If WebGL is not required, do not add Three.js for this module.

### Run interaction
Button label: `Run Illustrative Scenario`

On click:
1. Show a brief simulated progress state using React state and CSS animation (no custom timers unless already supported by the project's established pattern).
2. Display a deterministic mock result based on selected config.
3. Show a concise outcome, e.g. `Illustrative missed detection` or `No illustrative failure detected`.
4. Expose the result through a callback or documented plain object so the integrator can pass it to Failure Analysis and Adaptive Recommendation.
5. Provide `Run Again` or `Reset` behavior.

Visible disclosure is mandatory:
`Illustrative output — no live CARLA simulation or YOLO inference is running.`

Use deterministic rules/sample fixtures, not unseeded random values. Never present confidence or metric values as actual model results.

### Suggested component contract
Export `ScenarioLab`. Suggested props:
- `initialConfig`
- `onScenarioChange(config)`
- `onRunComplete(result)`

Use JSDoc comments to document callback payloads if needed. Keep internal form state local unless shared page-level state is agreed.

### Design and accessibility
- Dark technical panel, green active controls, orange only for warnings.
- Clear separation between controls and visual preview.
- Responsive stack on mobile.
- Labels, keyboard operation, visible focus states, reduced-motion support.

### Constraints
- No live CARLA, YOLO, backend, API, database, or model training.
- Do not implement unrelated sections.
- Do not edit shared app shell or global contracts unless assigned.

### Acceptance criteria
- Every control changes the summary.
- Run action shows progress then a stable illustrative result.
- Result callback emits the agreed object shape.
- Disclosure text is visible.
- Module renders independently and is ready for integration.
