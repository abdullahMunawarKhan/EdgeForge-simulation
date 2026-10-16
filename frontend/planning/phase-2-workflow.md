# Phase 2 — Interactive EDGEFORGE Workflow (React JSX)

## Coding Agent Prompt

Implement only the workflow demonstration module for EDGEFORGE. Use the shared design system and JavaScript contracts from Phase 0. Do not implement the landing page, Scenario Lab, failure analytics, coverage explorer, or adaptive recommendation module.

### Purpose
Explain the EDGEFORGE feedback loop clearly to hackathon judges:

**Scenario Generation → Simulation & Perception → Failure Detection → Coverage & Risk Analysis → Adaptive Test Selection → Replay / Repeat**

### Layout
- Section ID: `workflow`
- Section title: `How EDGEFORGE Works`
- Short subtitle explaining that each test contributes insights for choosing a useful next scenario.
- A connected stepper, flow diagram, or timeline.
- Six steps with clear numbering, icons, active state, and concise labels.
- Responsive behavior: horizontal on wide screens; stacked or scrollable stepper on small screens.

### Interactions
- Selecting a step updates a detail panel.
- `Previous` and `Next Step` controls navigate the sequence.
- Keep selected state obvious and keyboard accessible.
- Optional simple progress indicator.
- No live simulation or API calls.

### Step descriptions
1. **Scenario Generation** — Configure weather, lighting, traffic, road users, occlusion, and distance.
2. **Simulation & Perception** — Run a virtual scenario and obtain an illustrative camera frame and object predictions.
3. **Failure Detection** — Compare model predictions against simulator ground truth to identify missed detections, false positives, or localization errors.
4. **Coverage & Risk Analysis** — Update scenario coverage and identify relevant gaps or failure-associated conditions.
5. **Adaptive Test Selection** — Prioritize candidate follow-up scenarios using failure history, coverage gaps, and project-defined risk priorities.
6. **Replay / Repeat** — Preserve a scenario and rerun it for repeatable investigation or regression checks.

For each step, show a short `Input` and `Output` line, using conceptual examples. Clearly label the whole module `Conceptual workflow — illustrative demonstration`.

### Design
- Match the EDGEFORGE dark automotive-tech theme.
- Use green for active/completed stages and muted surfaces for inactive stages.
- Fine borders and simple connectors; avoid clutter.
- Text must be readable on a projector.

### Integration
- Export a self-contained component such as `WorkflowSection`.
- Use ordinary JavaScript props and callbacks if shared page state is needed; document expected arguments in JSDoc.
- Use section ID `workflow`.
- Do not modify `App.jsx`, global styles, or shared data contracts unless assigned.

### Constraints
- Do not add a backend, CARLA control, YOLO inference, or unrelated page sections.
- Do not make claims that the workflow is experimentally validated.

### Acceptance criteria
- All six steps can be selected.
- Previous/next controls work and handle first/last step boundaries.
- Layout is responsive and keyboard accessible.
- Handoff includes files, exports, props, and integration notes.
