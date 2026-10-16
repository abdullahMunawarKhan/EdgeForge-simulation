import { PageSection, SectionHeader } from '@/components/layout/PageSection.jsx'

/**
 * @typedef {Object} BenefitsSectionProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [description]
 * @property {Array<{label: string, summary: string, detail: string}>} [items]
 */

/**
 * @param {BenefitsSectionProps} props
 */
export function BenefitsSection({
  eyebrow = 'Why EDGEFORGE',
  title = 'Engineering Outcomes, Not Just Dashboards',
  description = 'Purpose-built for the way ADAS validation teams actually work: fewer missed edge cases, faster reproduction, clearer coverage, and tests that auto-prioritize where risk lives.',
  items,
}) {
  const benefits = items ?? [
    { label: 'More edge cases found pre-road', summary: '7-axis synthesis covers combinations manual test-plans miss.', detail: 'Systematically varies weather, lighting, traffic, road-user, occlusion, distance and ego speed to surface combinations that hand-crafted plans skip.' },
    { label: 'Reproducible failures, faster', summary: 'Every illustrative failure has a deterministic re-run handle.', detail: 'Full ScenarioConfig is persisted per FailureRecord, so any missed object, wrong classification or range error can be replayed on demand.' },
    { label: 'Coverage that guides investment', summary: 'Failure-prone and under-tested cells drive engineering effort.', detail: 'Heatmaps don\'t just visualize coverage — they feed the Adaptive module so the next run goes where risk has accumulated, not where engineering already looked.' },
    { label: 'Regressions get locked in', summary: 'Reproduced edge cases become regression entries.', detail: 'Once a failure is reproduced, the scenario is promoted to the regression set so the same edge case must re-pass on every iteration.' },
  ]

  return (
    <PageSection id="benefits">
      <SectionHeader
        eyebrow={eyebrow}
        title={title}
        description={description}
        actionSlot={<span className="chip">Intended outcomes · concept</span>}
      />
      <div className="mt-6 grid gap-3 md:grid-cols-2">
        {benefits.map((b, i) => (
          <div key={b.label} className="panel p-4">
            <div className="flex items-center justify-between">
              <div className="chip chip-accent">0{i + 1}</div>
            </div>
            <div className="mt-3 space-y-1">
              <div className="text-sm font-semibold tracking-tight">{b.label}</div>
              <div className="text-[11px] font-medium text-accent">{b.summary}</div>
            </div>
            <p className="mt-2 text-xs text-text-muted">{b.detail}</p>
          </div>
        ))}
      </div>
    </PageSection>
  )
}

export default BenefitsSection
