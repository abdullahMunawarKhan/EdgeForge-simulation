/**
 * @typedef {Object} SiteFooterProps
 * @property {import('react').ReactNode} [brandMark]
 * @property {string} [brandName]
 * @property {string} [tagline]
 */

/**
 * @param {import('react').ReactNode} brandMark
 * @returns {import('react').ReactNode}
 */
export function SiteFooter({
  brandName = 'EDGEFORGE',
  tagline = 'Forge the edge cases. Find the failures. Validate before the road.',
  mode = 'static',
}) {
  return (
    <footer className="border-t border-border-subtle mt-24">
      <div className="mx-auto max-w-6xl px-4 py-10 md:px-6">
        <div className="grid gap-10 md:grid-cols-3">
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-accent/10 border border-accent-subtle">
                <span className="text-[13px] font-bold tracking-tight text-accent">E</span>
              </div>
              <span className="text-[14px] font-semibold tracking-tight">{brandName}</span>
            </div>
            <p className="mt-3 max-w-xs text-xs text-text-muted">{tagline}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="chip">ADAS Validation</span>
              <span className="chip">Edge-Case Intelligence</span>
              <span className="chip chip-warning">Prototype</span>
            </div>
          </div>

          <div>
            <div className="field-label">Product</div>
            <ul className="mt-3 space-y-2 text-xs text-text-muted">
              <li><a className="hover:text-text" href="#overview">Platform Overview</a></li>
              <li><a className="hover:text-text" href="#workflow">Validation Workflow</a></li>
              <li><a className="hover:text-text" href="#scenario">Scenario Lab</a></li>
              <li><a className="hover:text-text" href="#analysis">Failure Analysis</a></li>
              <li><a className="hover:text-text" href="#coverage">Coverage Explorer</a></li>
            </ul>
          </div>

          <div>
            <div className="field-label">Team & Event</div>
            <ul className="mt-3 space-y-2 text-xs text-text-muted">
              <li>Team NextGen</li>
              <li>KPIT SPARKLES 2027</li>
              <li>Simulation Theme · Jury Demonstration</li>
            </ul>
          </div>
        </div>

        <div className="divider mt-10" />

        <div className="mt-6 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
          <p className="text-[10px] text-text-subtle">
            © {new Date().getFullYear()} EDGEFORGE — Team NextGen. For demonstration purposes only.
          </p>
        </div>
      </div>
    </footer>
  )
}

export default SiteFooter
