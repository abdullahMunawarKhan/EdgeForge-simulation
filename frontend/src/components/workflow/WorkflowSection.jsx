import { useState } from 'react'
import { PageSection, SectionHeader } from '@/components/layout/PageSection.jsx'

/**
 * @typedef {{
 *   id: string,
 *   index: number,
 *   label: string,
 *   summary: string,
 *   detail: string,
 *   input: string,
 *   output: string,
 * }} WorkflowStep
 *
 * @typedef {Object} WorkflowSectionProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [description]
 * @property {WorkflowStep[]} [steps]
 * @property {number} [activeStepIndex]
 * @property {import('@/types').ScenarioConfig} [currentScenario]
 * @property {import('@/types').DemoRunResult|null} [lastRun]
 * @property {(index: number) => void} [onStepClick]
 */

/**
 * @param {WorkflowSectionProps} props
 */
export function WorkflowSection({
  eyebrow = '02 · Workflow',
  title = 'How EDGEFORGE Works',
  description = 'Every test adds insight: what failed, what is still untested, and which scenario is worth running next. The loop feeds itself so the following run concentrates where signal is highest.',
  steps,
  activeStepIndex,
  onStepClick,
}) {
  /** @type {WorkflowStep[]} */
  const defaultSteps = [
    {
      id: 's1',
      index: 1,
      label: 'Scenario Generation',
      summary: 'Compose a 7-axis configuration',
      detail: 'Weather, lighting, traffic, road-user, occlusion, distance and ego speed are combined into a single runnable scenario seed.',
      input: 'Weather + Lighting + Traffic + Road-User + Occlusion + Distance + Ego Speed',
      output: 'Deterministic ScenarioConfig + scenario ID',
    },
    {
      id: 's2',
      index: 2,
      label: 'Simulation & Perception',
      summary: 'Illustrative run + perceived outcome',
      detail: 'The scenario is rendered into a lightweight preview and a synthetic perception outcome is produced for the configured ground truth.',
      input: 'ScenarioConfig + illustrative sensor seed',
      output: 'Camera-frame preview + bounding-box / range / class prediction',
    },
    {
      id: 's3',
      index: 3,
      label: 'Failure Detection',
      summary: 'Compare ground truth vs perception',
      detail: 'Missed objects, wrong classes, range errors and latency breaches are classified, assigned severity, and written to the failure log.',
      input: 'Ground truth annotation vs prediction payload',
      output: 'Classified FailureRecord + severity + replay handle',
    },
    {
      id: 's4',
      index: 4,
      label: 'Coverage & Risk Analysis',
      summary: 'Map the result across dimensions',
      detail: 'The run and any failure are attributed against the 7-axis coverage matrix to surface under-tested and failure-prone combinations.',
      input: 'Run + Failure records against scenario dimensions',
      output: 'Coverage status, failure-prone cells, under-tested gaps',
    },
    {
      id: 's5',
      index: 5,
      label: 'Adaptive Test Selection',
      summary: 'Rank and pick the next test',
      detail: 'Reason signals — Failure History 40%, Coverage Gaps 35%, and Project-Defined Risk Priorities 25% — are blended into a ranked recommendation.',
      input: 'Failure history + coverage matrix + risk weights',
      output: 'Ranked NextTestRecommendation with held-vs-changed axes',
    },
    {
      id: 's6',
      index: 6,
      label: 'Replay / Repeat',
      summary: 'Lock edge cases into the suite',
      detail: 'Reproduced failures are promoted to regression entries so the same edge case must pass on every subsequent model iteration.',
      input: 'Saved FailureRecord + updated perception model',
      output: 'Regression verdict, scenario locked into suite',
    },
  ]
  const theSteps = steps ?? defaultSteps
  const lastIndex = theSteps.length - 1

  const [internalIdx, setInternalIdx] = useState(0)
  const isControlled = typeof activeStepIndex === 'number' && activeStepIndex !== undefined
  const active = isControlled ? activeStepIndex : internalIdx

  const goTo = (idx) => {
    const bounded = Math.max(0, Math.min(lastIndex, idx))
    if (isControlled) {
      onStepClick?.(bounded)
    } else {
      setInternalIdx(bounded)
    }
  }

  const progress = ((active + 1) / theSteps.length) * 100
  const current = theSteps[active]

  return (
    <PageSection id="workflow">
      <SectionHeader eyebrow={eyebrow} title={title} description={description} />

      <div className="mt-4 prose-disclosure flex items-start gap-2">
        <span className="chip chip-accent shrink-0">Conceptual workflow</span>
        <p className="flex-1">
          Illustrative demonstration — the six-step loop shown describes how modules conceptually compose.
          No live CARLA simulation, YOLO inference, or real pipeline execution is running.
        </p>
      </div>

      <div className="mt-6 h-1.5 w-full overflow-hidden rounded-full bg-surface-active border border-border-subtle">
        <div
          className="h-full bg-accent transition-all duration-300 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>
      <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-text-subtle">
        <span>STEP {String(active + 1).padStart(2, '0')} / {String(theSteps.length).padStart(2, '0')}</span>
        <span>FAILURE-GUIDED · CLOSED-LOOP</span>
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <ol className="space-y-2">
          {theSteps.map((s, i) => {
            const isActive = i === active
            const isDone = i < active
            return (
              <li key={s.id}>
                <button
                  type="button"
                  onClick={() => goTo(i)}
                  aria-current={isActive ? 'step' : undefined}
                  className={`w-full panel p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent ${
                    isActive
                      ? 'border-accent/50 bg-surface-active shadow-[0_0_0_1px_rgba(52,211,153,0.15)_inset]'
                      : isDone
                      ? 'border-accent/20 bg-surface/70'
                      : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md border text-[11px] font-semibold ${
                        isActive
                          ? 'bg-accent/15 border-accent/40 text-accent'
                          : isDone
                          ? 'bg-accent/5 border-accent/20 text-accent'
                          : 'bg-surface-active border-border text-text-muted'
                      }`}
                    >
                      {isDone ? '✓' : s.index}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className={`text-sm font-semibold tracking-tight ${isActive ? 'text-text' : isDone ? 'text-text/90' : 'text-text-muted'}`}>
                        {s.label}
                      </div>
                      <div className="text-[11px] text-text-muted mt-0.5">{s.summary}</div>
                    </div>
                  </div>
                </button>
              </li>
            )
          })}
        </ol>

        <div className="panel p-5 flex flex-col">
          <div className="flex items-center justify-between">
            <div>
              <div className="field-label">Current step</div>
              <div className="mt-1 text-lg font-semibold tracking-tight">
                {current?.label}
              </div>
            </div>
            <span className="chip chip-accent font-mono">0{current?.index} / 06</span>
          </div>

          <p className="mt-3 text-xs leading-relaxed text-text-muted">
            {current?.detail}
          </p>

          <div className="divider my-5" />

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-border-subtle bg-bg p-3">
              <div className="flex items-center gap-2">
                <span className="chip">Input</span>
              </div>
              <div className="mt-2 text-xs font-medium text-text">
                {current?.input}
              </div>
            </div>
            <div className="rounded-lg border border-accent/20 bg-accent/[0.04] p-3">
              <div className="flex items-center gap-2">
                <span className="chip chip-accent">Output</span>
              </div>
              <div className="mt-2 text-xs font-medium text-text">
                {current?.output}
              </div>
            </div>
          </div>

          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            <div className="rounded-md border border-border-subtle bg-bg p-3">
              <div className="text-[10px] uppercase tracking-wider text-text-subtle">Inputs</div>
              <div className="mt-1 text-sm font-semibold">7 axes</div>
            </div>
            <div className="rounded-md border border-border-subtle bg-bg p-3">
              <div className="text-[10px] uppercase tracking-wider text-text-subtle">Outputs</div>
              <div className="mt-1 text-sm font-semibold">Failure log + coverage</div>
            </div>
            <div className="rounded-md border border-accent-subtle bg-accent-subtle p-3">
              <div className="text-[10px] uppercase tracking-wider text-accent">Feedback</div>
              <div className="mt-1 text-sm font-semibold text-accent">Adaptive</div>
            </div>
          </div>

          <div className="mt-auto pt-5 flex flex-wrap gap-3">
            <button
              type="button"
              className="btn"
              onClick={() => goTo(active - 1)}
              disabled={active === 0}
            >
              ← Previous
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => goTo(active + 1)}
              disabled={active === lastIndex}
            >
              {active === lastIndex ? 'Finish review' : 'Next Step →'}
            </button>
            <div className="ml-auto hidden items-center gap-1.5 sm:flex">
              {theSteps.map((_s, i) => (
                <span
                  key={i}
                  className={`h-1.5 w-5 rounded-full transition ${
                    i === active
                      ? 'bg-accent'
                      : i < active
                      ? 'bg-accent/40'
                      : 'bg-surface-active'
                  }`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>
    </PageSection>
  )
}

export default WorkflowSection
