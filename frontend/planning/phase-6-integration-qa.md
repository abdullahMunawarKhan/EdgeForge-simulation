# Phase 6 — Integration, Guided Demo, Responsive Polish & QA (JavaScript)

## Coding Agent Prompt

Act as the integration lead for the EDGEFORGE jury-demo website. Integrate the completed modules from Phases 0–5. Do not rewrite finished modules unless a specific integration or quality issue requires a focused fix.

### 1. Inspect and integrate
- Review the current repository and contributor handoff notes.
- Confirm exports, props, shared JavaScript object shapes, data formats, dependencies, and section IDs.
- Use JavaScript and JSX only. Do not introduce TypeScript, `.ts`, `.tsx`, interfaces, or type aliases.
- Integrate modules into one single-page scrolling experience:
  1. Navbar
  2. Hero
  3. Platform Overview
  4. Workflow
  5. Scenario Lab / Simulation Preview
  6. Failure Analysis
  7. Coverage Explorer
  8. Adaptive Next-Test Recommendation
  9. Intended Benefits
  10. Footer
- Keep each section modular. Avoid moving all code into one large page component.

### 2. Shared demo state
Create one clear page-level state or small hook for the data that must flow between modules:
- Current ScenarioConfig
- Latest DemoRunResult
- Illustrative FailureRecord, where applicable
- Recommended next ScenarioConfig
- Current guided-demo step

Use plain JavaScript objects. Use JSDoc comments for the expected object shapes if useful. Avoid duplicate competing state. Keep each component's internal presentation state local.

Expected flow:
1. Scenario Lab emits a config change.
2. Scenario Lab emits an illustrative result after the demo run.
3. Failure Analysis can display the corresponding sample record or a fallback fixture.
4. Coverage view reflects the current illustrative demo state where practical.
5. Adaptive Recommendation receives the latest available result/signals.
6. `Run Next Scenario` updates the Scenario Lab configuration and guides the presenter back to the scenario area.

If a module is not wired to dynamic state, retain a clearly labelled sample fallback.

### 3. Guided jury walkthrough
Add a compact `Start Guided Demo` control if feasible:
- Start at the hero.
- Guide through scenario configuration.
- Show illustrative run result.
- Navigate to failure analysis.
- Navigate to coverage.
- Show next-test recommendation.
- Allow the presenter to exit or explore manually at any time.

Do not make the walkthrough modal-heavy or difficult to control. Every step must remain skippable. Do not imply that the guided tour is executing a real simulator.

### 4. Navigation and layout
- Verify all navbar anchors and CTAs.
- Ensure sticky navigation does not cover section headings after scrolling.
- Confirm mobile menu behavior.
- Ensure a logical visual rhythm, consistent section widths, and responsive grids.
- Check desktop projector/laptop display first, then tablet and mobile.
- Fix horizontal overflow, clipped content, tiny text, and inconsistent card spacing.

### 5. Visual polish
- Align dark navy, white/gray, green, and orange usage across modules.
- Standardize buttons, badges, cards, borders, headings, spacing, and icon sizes.
- Keep animation subtle and respect reduced-motion preferences.
- Verify fallback visuals if images or WebGL are unavailable.
- Do not add Three.js solely for decoration at this late phase.

### 6. Truthfulness and demo disclosures
Verify the website clearly communicates that outputs are illustrative unless actual integrations are present:
- No false claim of live CARLA execution.
- No false claim of actual YOLO inference.
- No fabricated performance or accuracy results.
- No claims of ADAS certification or production readiness.
- Coverage graphics do not claim exhaustive real-world coverage.
- Risk/priority logic is identified as project-defined/prototype logic.

### 7. QA
- Run existing build and lint/test commands, if configured.
- Fix broken imports, runtime errors, console warnings that affect the demo, and inaccessible controls.
- Test scenario control updates, run action, next-test callback, reset, navigation, and guided demo.
- Test keyboard focus and reduced-motion behavior.
- Test at common desktop, tablet, and mobile widths.
- Keep all demo behavior deterministic for repeatable presentation.

### Acceptance criteria
- All modules appear in correct order and share a consistent visual language.
- Scenario configuration, illustrative result, and recommendation are connected coherently.
- All buttons and navigation links work.
- Responsive layouts remain usable.
- Mock/illustrative data is disclosed.
- Build succeeds using repository scripts.

### Final handoff
Report integrated sections and behavior, files created/modified, build/lint/test results, exact run command, known issues/placeholders, and a short recommended presentation path for the jury.
