# Phase 1 — Navbar, Hero & Platform Overview (React JSX)

## Coding Agent Prompt

Build only the EDGEFORGE landing-page module: navigation, hero, and platform overview. Inspect the repository and follow the shared contracts/design tokens from Phase 0. Use JavaScript and JSX only. Do not implement workflow, Scenario Lab, failure analysis, coverage explorer, or adaptive testing.

### Product context
EDGEFORGE is a proposed simulation-based ADAS perception validation platform that learns from observed perception failures and scenario coverage to guide what should be tested next. This is a jury-facing concept demonstration, not a live simulator.

### A. Navbar
Create a responsive top navigation containing:
- EDGEFORGE wordmark.
- Links: Overview, Workflow, Scenario Lab, Failure Analysis, Coverage, Next Test.
- Primary CTA: `Explore Demo`.
- Mobile menu with accessible open/close behavior.

Use anchor IDs agreed with the integrator. Navigation should scroll to sections; links to modules not yet merged can point to their planned IDs. Do not implement a separate router unless the existing project requires it.

### B. Hero
Include:
- Eyebrow: `ADAS EDGE-CASE VALIDATION`
- Heading: `Forge the edge cases. Find the failures.`
- Supporting copy: `Failure-guided simulation testing for smarter ADAS perception validation.`
- Primary CTA: `Explore the Demo`
- Secondary CTA: `See How It Works`
- Context label: `KPIT SPARKLES 2027 • SIMULATION`

Visual direction:
- Dark automotive engineering aesthetic.
- One clear vehicle / road / perception-sensing visual.
- Optional restrained detection boxes, lane guides, sensor arcs, or scenario labels.
- Use a static image, CSS scene, or available project asset. Do not create a complex 3D scene in this phase.
- Provide a fallback if an image asset is unavailable.

### C. Platform Overview
Create four concise feature cards:
1. **Failure Intelligence** — Compare model predictions with simulator ground truth and structure observed failures.
2. **Coverage Awareness** — Track explored scenario combinations and identify under-tested regions.
3. **Adaptive Test Selection** — Prioritize follow-up scenarios using failure history, coverage gaps, and defined risk priorities.
4. **Failure Replay & Regression** — Preserve scenarios and replay them against updated perception models.

Use suitable Lucide icons if installed, concise copy, consistent card dimensions, and restrained hover/focus states.

### Design and accessibility
- Follow shared dark navy, white/gray, green and limited orange palette.
- Responsive at desktop, tablet and mobile widths.
- Semantic headings, accessible nav labels, visible keyboard focus.
- Avoid dense text, excessive effects, and tiny text.
- Respect reduced-motion preferences.

### Constraints
- Implement only navbar, hero, and overview.
- Do not edit shared contracts or global styles unless explicitly assigned.
- Do not claim live CARLA/YOLO operation or proven performance.
- Make each CTA perform a meaningful scroll/navigation action.

### Expected handoff
Report files changed, component exports/props, required assets/dependencies, and integration instructions. Ensure the app builds with the existing setup.
