# Phase 0 — Project Foundation & Shared Contracts (JavaScript)

## Coding Agent Prompt

Act as the frontend lead for EDGEFORGE. Prepare only the project foundation and integration contracts for a modular, team-built website demonstration. Do not implement all page sections.

### 1. Inspect first
- Inspect the repository, existing React/Vite setup, scripts, package manager, styling system, and dependencies.
- Preserve existing working configuration. Do not replace the project structure without a clear reason.
- If the repo is empty, initialize a minimal React + Vite app using JavaScript and JSX.

### 2. JavaScript-only requirement
- Use `.jsx` for React components and `.js` for utilities, data and hooks.
- Do not use TypeScript, `.ts`, `.tsx`, interfaces, type aliases, generics, or TS-only syntax.
- Use concise JSDoc comments where useful to document shared object shapes and callback arguments.
- Do not add TypeScript dependencies or configuration.

### 3. Establish design tokens
Create a small set of reusable tokens for:
- Background: deep navy / near-black.
- Surface: slightly lighter dark panels.
- Text: white and cool gray.
- Primary accent: restrained electric green.
- Warning accent: limited orange.
- Border, muted text, spacing, radii, and subtle shadows.

The style should feel like an automotive ADAS engineering platform and align with the EDGEFORGE presentation. Avoid excessive neon, gradients, glass effects, or animation.

### 4. Establish app shell
Create only the minimal application shell needed to mount independent page sections. A placeholder Home page is sufficient. Do not create hero, workflow, scenario lab, analytics, coverage, or adaptive module content.

### 5. Define shared JavaScript data contracts
Create a shared `src/data/demoSchema.js` file containing JSDoc typedefs or documented example objects for:
- `ScenarioConfig`: weather, lighting, traffic density, road user, occlusion, and distance.
- `DemoRunResult`: run identifier, scenario config, illustrative outcome, and display message.
- `FailureRecord`: ID, scenario config, object class, failure type, severity label, and replay status.
- `CoverageItem`: scenario dimensions / combination and illustrative status (tested, under-tested, failure-prone).
- `NextTestRecommendation`: reason signals and recommended ScenarioConfig.

Use plain JavaScript objects and arrays. Keep definitions small and practical. JSDoc is documentation only; do not add runtime complexity.

### 6. Define module integration points
Document suggested component names and props for:
- `HeroSection`
- `PlatformOverview`
- `WorkflowSection`
- `ScenarioLab`
- `FailureAnalysis`
- `CoverageExplorer`
- `AdaptiveRecommendation`
- `BenefitsSection`
- `SiteFooter`

Each component should be independently importable and should not require knowledge of another component's internal state. Document a sensible shared page-level demo state interface in JSDoc or README; do not add a global state library.

### 7. Suggested structure
Follow current conventions, but aim for:

```text
src/
  components/
    layout/
    hero/
    overview/
    workflow/
    scenario/
    analysis/
    coverage/
    adaptive/
    shared/
  data/
    demoSchema.js
  hooks/
  pages/
  styles/
```

### Constraints
- Do not add a backend, database, authentication, live CARLA integration, or YOLO inference.
- Do not add Three.js or other heavy packages at this stage.
- Avoid implementing visual modules assigned to later phases.
- Do not redesign unrelated project files.

### Acceptance criteria
- App starts with the repository's run command.
- Shared tokens and JavaScript contracts are documented or implemented.
- Placeholder page mounts without errors.
- Other team members can implement their own components against the agreed contracts.
- Provide changed-file list, run command, and module integration notes.
