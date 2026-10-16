# Phase 5 — Adaptive Next-Test Recommendation (React JSX)

## Coding Agent Prompt

Implement only the Adaptive Test Selection / Next-Best-Test module. This is the main USP showcase for EDGEFORGE. Use Phase 0 shared JavaScript contracts and coordinate the prop/data shape with the Scenario Lab and Failure/Coverage modules before coding.

Do not implement those other modules or duplicate their UI.

### Purpose
Show how EDGEFORGE uses an observed perception failure and coverage insight to recommend a related follow-up scenario, rather than merely running unrelated random scenarios.

### Example illustrative case
- Observed scenario: `Night + Fog + High Traffic + Partially Occluded Pedestrian`
- Observed outcome: `Missed Detection`
- Signals: `Failure History`, `Coverage Gaps`, `Project-Defined Risk Priorities`
- Example next test: keep relevant conditions controlled and vary pedestrian distance or occlusion to investigate the failure-associated region.

This is an explanatory fixture, not a claim that an algorithm has already discovered an actual failure.

### Layout
- Section ID: `next-test`
- Title: `What Should EDGEFORGE Test Next?`
- Three input signal cards: Failure History, Coverage Gaps, and Project-Defined Risk Priorities.
- A central `Scenario Prioritization` stage.
- A prominent `Recommended Next Test` card showing the proposed scenario config and a concise reason.
- A visible explanation of which conditions are held constant and which parameter is changed.
- Disclosure that the selection method is a prototype concept to be implemented and evaluated.

### Interactions
- Receive the latest illustrative result/config from shared state or props when available.
- Display a deterministic recommendation based on the current demo fixture/config.
- `Run Next Scenario` emits the recommended ScenarioConfig via callback, allowing the integrator to update the Scenario Lab.
- Show a small state confirmation such as `Illustrative next scenario selected`.
- Provide a reset/back-to-example action if useful.

Do not use unseeded random rankings. Do not describe a project-defined priority score as an industry-standard metric.

### Suggested component contract
Export `AdaptiveRecommendation`. Suggested props:
- `latestResult`
- `failureRecords`
- `coverageItems`
- `onRunNextScenario(config)`

Adapt to actual shared objects. If upstream modules are not merged, use documented props and local sample fixtures rather than importing their internal files. Use JSDoc only if helpful.

### Design
- Strong visual hierarchy; make the recommendation the focal point.
- Dark automotive-tech theme, green for priority/selected action, restrained orange for risk/alert.
- Simple arrows/connector flow from signals to prioritization to recommendation.
- Keep content concise and projector-readable.

### Constraints
- Do not claim proven optimization, measured efficiency gains, or validated safety benefits.
- No live CARLA, YOLO, backend, database, or ML model is required.
- Do not implement full workflow, Scenario Lab, failure dashboard, or coverage grid.

### Acceptance criteria
- Three signals are visibly connected to a recommendation.
- Recommended test and rationale are understandable.
- Run Next Scenario invokes the agreed callback with a valid config.
- Recommendation is clearly labelled illustrative.
- Module is independent, responsive, and ready for integration.
