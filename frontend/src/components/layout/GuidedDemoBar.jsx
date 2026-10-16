import { GUIDED_STEPS } from '@/hooks/useGuidedDemo.js'

/**
 * @typedef {Object} GuidedDemoBarProps
 * @property {import('@/hooks/useGuidedDemo.js').GuidedStep|null} current
 * @property {number} currentIndex
 * @property {boolean} active
 * @property {() => void} onStart
 * @property {() => void} onPrev
 * @property {() => void|Promise<void>} onNext
 * @property {() => void} onExit
 * @property {(idx: number) => void} onGoTo
 */

/**
 * Sticky, compact, projector-friendly guide. Desktop pill-style control.
 * - Inactive: just one small "Start Guided Demo" CTA on the right.
 * - Active: step title, prev/step-pill skip-list, exit always-visible exit button.
 *
 * @param {GuidedDemoBarProps} p
 */
export function GuidedDemoBar({ current, currentIndex, active, onStart, onPrev, onNext, onExit, onGoTo }) {
  return (
    <div
      className="pointer-events-none fixed inset-x-0 bottom-3 z-50 flex justify-center px-3 md:bottom-4 md:px-6">
      <div className="pointer-events-auto w-full max-w-4xl">
        {!active ? (
        <div className="panel flex items-center justify-between gap-3 px-4 py-2.5">
          <div className="flex items-center gap-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent/15 border border-accent-subtle">
              <span className="text-[11px] font-bold text-accent">▶</span>
            </div>
            <div className="min-w-0">
              <div className="text-[11px] font-medium tracking-tight">Guided jury demo</div>
              <div className="text-[10px] text-text-muted">6 steps · skip anytime.</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select
              aria-label="Jump to guided demo step"
              onChange={(e) => onGoTo?.(Number(e.target.value))}
              className="h-8 rounded-md border border-border bg-surface-active px-2 text-[10px] text-text-muted"
              defaultValue=""
            >
              <option value="" disabled>Jump to step…</option>
              {GUIDED_STEPS.map((s, i) => (
                <option key={s.id} value={i}>{s.title}</option>
              ))}
            </select>
            <button type="button" className="btn btn-primary h-8 px-3 text-[11px]" onClick={onStart}>
              Start Guided Demo
            </button>
          </div>
        </div>
      ) : (
        <div className="panel px-4 py-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md bg-accent/15 border border-accent-subtle">
                <span className="text-[11px] font-bold text-accent">
                  {Math.min(currentIndex + 1, GUIDED_STEPS.length)}/{GUIDED_STEPS.length}
                </span>
              </div>
              <div className="min-w-0">
                <div className="truncate text-[12px] font-semibold tracking-tight">
                  {current?.title}
                </div>
                <div className="truncate text-[10px] text-text-muted">
                  {current?.hint}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <select
                aria-label="Guided demo step picker"
                value={currentIndex}
                onChange={(e) => onGoTo?.(Number(e.target.value))}
                className="h-8 rounded-md border border-border bg-surface-active px-2 text-[10px] text-text"
              >
                {GUIDED_STEPS.map((s, i) => (
                  <option key={s.id} value={i}>{s.title}</option>
                ))}
              </select>
              <button
                type="button"
                className="btn h-8 px-3 text-[11px]"
                onClick={onPrev}
                disabled={currentIndex === 0}
              >
                ← Back
              </button>
              <button
                type="button"
                className="btn btn-primary h-8 px-4 text-[11px]"
                onClick={onNext}
              >
                {current?.cta ?? (currentIndex === GUIDED_STEPS.length - 1 ? 'Finish' : 'Next →')}
              </button>
              <button
                type="button"
                className="btn btn-ghost h-8 px-3 text-[11px]"
                aria-label="Exit guided demo"
                onClick={onExit}
              >
                Exit
              </button>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <ol className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
              {GUIDED_STEPS.map((s, i) => {
                const on = i === currentIndex
                const done = i < currentIndex
                return (
                  <li key={s.id} className="flex min-w-0 items-center">
                    <button
                      type="button"
                      aria-current={on ? 'step' : undefined}
                      onClick={() => onGoTo(i)}
                      className={`chip h-7 min-w-[28px] rounded-md px-2 text-[10px] ${
                        on ? 'chip-accent' : done ? 'border-accent/25 text-accent/75' : ''
                      }`}
                    >
                      {done ? '✓ ' : ''}{i + 1}
                    </button>
                    {i < GUIDED_STEPS.length - 1 ? (
                      <span className="mx-0.5 h-px w-3 flex-shrink-0 bg-border-subtle" />
                    ) : null}
                  </li>
                )
              })}
            </ol>
          </div>
          <div className="mt-2 rounded-md border border-border-subtle bg-bg px-3 py-2.5">
            <p className="text-[11px] text-text-muted">{current?.description}</p>
            <div className="mt-1 text-[10px] text-text-subtle">
              Skippable · manual exploration is always available.
            </div>
          </div>
        </div>
      )}
      </div>
    </div>
  )
}

export default GuidedDemoBar
