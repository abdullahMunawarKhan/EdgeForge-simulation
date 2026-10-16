# EDGEFORGE — Phase-Wise Website Development Prompts (React JSX + JavaScript)

These prompts split the EDGEFORGE jury-demo website into smaller, independently assignable tasks. Assign each phase to a team member or coding agent, then integrate through the shared contracts below.

## Technology decision
- **React + Vite + JavaScript (JSX)** — frontend foundation.
- **Tailwind CSS** — styling, if already configured or approved by the integrator.
- **Lucide React** — icons, if installed.
- **Framer Motion** — optional motion.
- **Recharts** — optional charts for coverage / failure summaries.
- **Three.js** — optional; not required for the first version.

Use `.jsx` for React components and `.js` for utility, data, and hook files. Do not use TypeScript, `.ts`, `.tsx`, interfaces, type aliases, or TypeScript-only syntax. Use concise JSDoc comments only where a shared object shape or callback contract needs clarification.

## Recommended implementation order

| Phase | Module | Parallelization |
|---|---|---|
| 0 | Project foundation, shared design tokens and component contracts | First; required before parallel work |
| 1 | Navbar, hero and platform overview | After Phase 0 |
| 2 | Interactive workflow demonstration | After Phase 0 |
| 3 | Scenario Lab and illustrative simulation preview | After Phase 0 |
| 4 | Failure analysis and coverage explorer | After Phase 0; use agreed sample-data shape |
| 5 | Adaptive next-test recommendation | Agree props with Phases 3 and 4 first |
| 6 | Integration, guided walkthrough, responsive polish and QA | After modules are merged |

Phases 1–4 can be developed in parallel in separate branches or clearly separated files after Phase 0. Phase 5 should coordinate its data and callbacks with the Scenario Lab and analysis modules. Phase 6 is the integration pass.

## How to use
1. Give the coding agent only the prompt for its assigned phase, plus this README if useful.
2. Ask it to inspect the repository before changing files.
3. Keep each module in its own component folder and branch.
4. Do not let multiple agents edit `App.jsx`, global styles, shared data contracts, or package configuration simultaneously.
5. Merge one module at a time and run the app after each merge.
6. If a dependency module is not ready, use the agreed props and a local temporary mock rather than duplicating its implementation.

## Shared product and design contract
- Product: **EDGEFORGE — ADAS Edge-Case Validation & Failure Intelligence Platform**
- Tagline: **Forge the edge cases. Find the failures. Validate before the road.**
- Team: **Team NextGen**
- Event: **KPIT SPARKLES 2027 — Simulation Theme**
- Visual identity: dark navy / near-black background, white and cool-gray typography, restrained electric-green highlights, limited orange for warnings or emphasis, fine borders and clean technical panels.
- Product loop: **Scenario Generation → Simulation & Perception → Failure Detection → Coverage & Risk Analysis → Adaptive Test Selection → Repeat**
- Frontend is a **concept demonstration**. Unless a real integration exists, runs, detections, metrics, coverage and recommendations are illustrative/mock data.
- Do not claim live CARLA execution, YOLO inference, validated accuracy, proven efficiency gains, production readiness, or ADAS certification.
- Keep components responsive, accessible, keyboard-friendly, and easy to replace with real APIs later.

## Suggested shared folder structure
Adapt to the repository instead of forcing a rewrite:

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
  hooks/
  pages/
  styles/
```

## Shared integration rules
- Use the repository's existing React/Vite setup and package manager.
- Use JavaScript and JSX only. Component files use `.jsx`; utilities, data, and hooks use `.js`.
- Use existing Tailwind and icon/chart dependencies. Add dependencies only when necessary and tell the integrator first.
- Components should accept data and callbacks through props; avoid tightly coupling modules to each other's internal state.
- Use one shared demo state at the page level or a small shared hook once agreed. Do not create multiple competing sources of truth.
- Use JSDoc comments for shared object and callback expectations, not TypeScript declarations.
- Avoid editing `App.jsx`, global CSS, shared data contracts or package files from parallel module branches unless the integrator assigns that work.
- Use semantic HTML, visible focus states, accessible labels and reduced-motion support.
- All CTAs must work. No decorative, inert buttons.
- Keep demo data deterministic so the presentation behaves consistently.

## Handoff checklist for every phase
Each contributor should report:
1. Files created or modified.
2. Component export names and props.
3. Dependencies added, if any.
4. How to render or test the component.
5. Any assumptions, placeholders, or integration needs.
