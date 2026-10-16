import { PageSection, SectionHeader } from '@/components/layout/PageSection.jsx'

/**
 * @typedef {{
 *   id: string,
 *   label: string,
 *   tagline: string,
 *   description: string,
 *   accent?: boolean
 * }} Pillar
 *
 * @typedef {Object} PlatformOverviewProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [description]
 * @property {Pillar[]} [pillars]
 */

/**
 * @param {PlatformOverviewProps} props
 */
export function PlatformOverview({
  eyebrow = '01 · Platform',
  title = 'End-to-End Edge-Case Validation',
  description = 'Six tightly-coupled modules cover the full ADAS validation loop from scenario generation through adaptive test selection, with a single shared engineering view.',
  pillars,
}) {
  /** @type {Pillar[]} */
  const items = pillars ?? [
  {
    id: 'fail',
    label: 'Failure Intelligence',
    tagline: 'Understand where perception breaks',
    description:
      'Compare model predictions with simulator ground truth and structure observed perception failures for investigation.',
  },
  {
    id: 'cov',
    label: 'Coverage Awareness',
    tagline: 'See what has not been tested',
    description:
      'Track explored scenario combinations and identify under-tested and failure-prone regions of the scenario space.',
  },
  {
    id: 'adapt',
    label: 'Adaptive Test Selection',
    tagline: 'Choose what to test next',
    description:
      'Prioritize follow-up scenarios using failure history, coverage gaps and defined risk priorities.',
  },
  {
    id: 'loop',
    label: 'Failure Replay & Regression',
    tagline: 'Turn failures into regression tests',
    description:
      'Preserve important scenarios and replay them against updated perception models to verify whether failures persist.',
  },
]

  return (
    <PageSection id="overview">
      <SectionHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
      />
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
  {items.map((p, i) => (
    <article
  key={p.id}
  className="group relative min-h-[220px] overflow-hidden rounded-xl border border-border-subtle bg-surface p-5 transition-all duration-300 hover:-translate-y-1 hover:border-accent/50 hover:bg-surface-hover focus-within:border-accent/50"
>
  <div
    className="pointer-events-none absolute inset-0 grid-lines opacity-15"
    aria-hidden="true"
  />

  <div
    className="pointer-events-none absolute -right-20 -top-20 h-48 w-48 rounded-full bg-accent/10 blur-3xl transition-all duration-500 group-hover:scale-125 group-hover:bg-accent/20"
    aria-hidden="true"
  />

  <div className="relative flex h-full flex-col">

    {/* Module header */}
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-accent/20 bg-accent/5 font-mono text-xs font-semibold text-accent">
          0{i + 1}
        </span>

        <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-text-subtle">
          MODULE
        </span>
      </div>

      <div className="flex items-center gap-2">
        <span className="status-dot bg-accent" />
        <span className="font-mono text-[9px] uppercase tracking-widest text-text-subtle">
          ACTIVE
        </span>
      </div>
    </div>

    {/* Main content */}
    <div className="mt-7">
      <h3 className="text-lg font-semibold tracking-tight">
        {p.label}
      </h3>

      <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.12em] text-accent">
        {p.tagline}
      </p>

      <p className="mt-4 max-w-lg text-xs leading-5 text-text-muted">
        {p.description}
      </p>
    </div>

    {/* Technical footer */}
    <div className="mt-auto pt-7">
      <div className="flex items-center gap-3">
        <span className="font-mono text-[9px] text-text-subtle">
          EF-{String(i + 1).padStart(2, '0')}
        </span>

        <div className="relative h-px flex-1 overflow-hidden bg-border-subtle">
          <div className="absolute inset-y-0 left-0 w-1/3 bg-accent transition-all duration-500 group-hover:w-3/4" />
        </div>

        <span className="font-mono text-[9px] tracking-widest text-text-subtle">
          READY
        </span>
      </div>
    </div>
  </div>
</article>
  ))}
</div>
    </PageSection>
  )
}

export default PlatformOverview
