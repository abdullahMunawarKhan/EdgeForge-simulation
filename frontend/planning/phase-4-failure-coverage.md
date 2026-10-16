# Phase 4 — Failure Analysis & Scenario Coverage Explorer (React JSX)

## Coding Agent Prompt

Implement only two EDGEFORGE modules: Failure Analysis and Scenario Coverage Explorer. Follow Phase 0 shared JavaScript contracts and design tokens. Keep the modules independently importable. Do not implement Scenario Lab or adaptive recommendation engine.

### A. Failure Analysis
Section ID: `failure-analysis`

Purpose: show how model predictions can be compared with simulator ground truth and how a failure can be stored for investigation.

Create:
- A two-column visual comparison: `Simulator Ground Truth` vs `Illustrative Model Prediction`.
- A sample case where a pedestrian exists in ground truth but is absent from prediction, resulting in `Missed Detection`.
- Concise category chips for Missed Detection, False Positive, Poor Localization, and Confidence Degradation.
- A sample failure record with:
  - Failure ID (e.g. `EC-0042`)
  - Object class
  - Failure type
  - Scenario conditions
  - Prototype severity label
  - Replay status such as `Saved for Replay`

Keep sample values in a dedicated JavaScript data file and visibly label them as illustrative. Do not imply that a real model ran.

### B. Coverage Explorer
Section ID: `coverage`

Purpose: explain coverage awareness without implying exhaustive real-world domain coverage.

Create:
- A compact grid/matrix or heatmap for scenario combinations across weather, lighting, traffic, or road-user dimensions.
- Status legend: `Tested`, `Under-tested`, `Failure-prone`.
- A concise summary of sample coverage.
- A small list of illustrative scenario regions associated with sample failures.
- Optional hover/click detail for cells if cleanly implementable.

All counts, percentages, and cell states must be mock/illustrative. Add disclosure:
`Illustrative scenario-space view; not exhaustive real-world driving coverage.`

### Shared data and props
- Use `FailureRecord` and `CoverageItem` object shapes from Phase 0 if available.
- Export separate components, e.g. `FailureAnalysis` and `CoverageExplorer`.
- Accept optional props for records/data so future API integration is straightforward.
- Avoid direct imports from Scenario Lab internals.
- Do not create a second source of truth for shared scenario configuration.
- Use JavaScript objects/arrays and optional JSDoc comments only; no TypeScript.

### Design
- Match dark navy background, high-contrast text, green status accent, limited orange for warnings.
- Use simple charts/progress bars only if they improve comprehension.
- Avoid tiny labels and dense dashboard overload.
- Responsive cards and comparison layout.
- Accessible status labels must not rely on color alone.

### Constraints
- No backend, live model inference, database, CARLA connection, or unsupported accuracy claims.
- Do not implement adaptive test selection in this phase.
- Do not edit app shell or global contracts unless explicitly assigned.

### Acceptance criteria
- Ground-truth and prediction comparison is visually understandable.
- Sample failure record shows all key fields.
- Coverage grid has a clear legend and disclosure.
- Mock data is separated from UI and easy to replace.
- Both modules render independently and are ready for integration.
