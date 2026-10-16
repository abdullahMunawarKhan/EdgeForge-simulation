const MODES = [
  { id: 'live', label: 'Live Simulation' },
  { id: 'static', label: 'Static Demo' },
]

/**
 * @param {{ mode: 'live'|'static', onChange: (mode: 'live'|'static') => void }} props
 */
export function ModeSelector({ mode, onChange }) {
  return (
    <div className="border-b border-border-subtle bg-bg-elevated">
      <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between md:px-6">
        <div>
          <div className="field-label">Workspace mode</div>
          <p className="mt-1 text-xs text-text-muted" aria-live="polite">
            {mode === 'static'
              ? 'DEMO DATA · Bundled sample data; no simulator or backend required.'
              : 'LIVE DATA · Only values received from the configured backend are shown.'}
          </p>
        </div>
        <div
          className="inline-flex w-fit rounded-lg border border-border-subtle bg-bg p-1"
          role="group"
          aria-label="Choose dashboard mode"
        >
          {MODES.map((item) => {
            const active = mode === item.id
            return (
              <button
                key={item.id}
                type="button"
                aria-pressed={active}
                onClick={() => onChange(item.id)}
                className={`rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  active
                    ? 'bg-accent text-[#05120C]'
                    : 'text-text-muted hover:bg-surface-hover hover:text-text'
                }`}
              >
                {item.label}
                {item.id === 'static' ? <span className="ml-1.5 text-[9px]">DEMO</span> : null}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

export default ModeSelector
