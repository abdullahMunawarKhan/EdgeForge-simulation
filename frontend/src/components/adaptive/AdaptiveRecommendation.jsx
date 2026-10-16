import { useEffect, useMemo, useState } from 'react'
import { PageSection } from '@/components/layout/PageSection.jsx'
import {
  buildAdaptiveRecommendations,
  prettyFieldLabel,
  prettyFieldValue,
  EXAMPLE_ANCHOR_SCENARIO,
} from './adaptiveEngine.js'
import { DEFAULT_SCENARIO } from '@/data/labels.js'

/**
 * Phase 5 — Adaptive Next-Test Recommendation module.
 *
 * Integration contract (coordinates with Phase 0 shared JSDoc contracts):
 *
 * @typedef {Object} AdaptiveRecommendationProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [description]
 * @property {import('@/types').DemoRunResult|null} [latestResult]           - most recent run (from Scenario Lab / lastRun)
 * @property {import('@/types').FailureRecord[]} [failureRecords]           - from FailureAnalysis
 * @property {import('@/types').CoverageItem[]} [coverageItems]             - from CoverageExplorer
 * @property {string|null} [selectedFailureId]                              - from FailureAnalysis / PageDemoState
 * @property {Partial<import('@/types').ScenarioConfig>} [currentScenario]  - current Scenario Lab state, used as fallback anchor
 * @property {(cfg: import('@/types').ScenarioConfig) => void} [onRunNextScenario]  - the primary integration callback
 * @property {() => void} [onResetExample]                                  - optional reset action
 */

/**
 * @param {AdaptiveRecommendationProps} p
 */
export function AdaptiveRecommendation({
  eyebrow = '05 · Adaptive Next-Test',
  title = 'What Should EDGEFORGE Test Next?',
  description = 'Three signals — failure history, coverage gaps, and project-defined risk priorities — are combined deterministically into scenario variations. The anchor scenario is held constant where it matters, and only high-signal parameters are varied to investigate the failure-associated region.',
  latestResult = null,
  failureRecords = [],
  coverageItems = [],
  selectedFailureId = null,
  currentScenario = {},
  onRunNextScenario,
  onResetExample,
}) {
  const model = useMemo(
    () => buildAdaptiveRecommendations({ latestResult, failureRecords, coverageItems, selectedFailureId, currentScenario }),
    [latestResult, failureRecords, coverageItems, selectedFailureId, currentScenario],
  )

  const [selectedIdx, setSelectedIdx] = useState(0)
  const [confirmation, setConfirmation] = useState(null)

  useEffect(() => {
    setSelectedIdx(0)
    setConfirmation(null)
  }, [model.anchor.scenario.weather, model.anchor.scenario.lighting, model.anchor.scenario.roadUser])

  const selected = model.prioritized[selectedIdx] ?? null

  const onPick = (idx) => {
    setSelectedIdx(idx)
    setConfirmation(null)
  }

  const onRun = () => {
    if (!selected) return
    setConfirmation({ kind: 'selected', text: 'Illustrative next scenario selected.', scenario: selected.scenario })
    onRunNextScenario?.(selected.scenario)
  }

  const onReset = () => {
    setConfirmation({ kind: 'reset', text: 'Reset to example fixture.' })
    onResetExample?.()
  }

  const anchorSourceLabel = {
    latest_run: 'Latest run',
    selected_failure: 'Selected failure',
    top_failure: 'Top-severity failure',
    current: 'Scenario Lab',
  }[model.anchor.source] ?? 'Scenario Lab'

  return (
    <PageSection id="next-test" className="pt-10">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <div className="chip chip-accent">{eyebrow}</div>
            <div className="chip chip-warning">Illustrative · prototype method</div>
          </div>
          <h2 className="text-xl font-semibold tracking-tight md:text-2xl">{title}</h2>
          <p className="max-w-3xl text-xs text-text-muted md:text-sm">{description}</p>
        </div>
        {onResetExample ? (
          <button type="button" className="btn btn-ghost self-start" onClick={onReset}>
            Reset to example fixture
          </button>
        ) : null}
      </div>

      <div className="mt-8 grid gap-4 lg:grid-cols-3">
        <SignalCard
          title="Failure History"
          subtitle="Signal 1 · recent & same-class"
          accent="danger"
          score={model.failureHistory.score}
          signals={model.failureHistory.signals}
          badge="01"
        />
        <SignalCard
          title="Coverage Gaps"
          subtitle="Signal 2 · under-tested / failure-prone cells"
          accent="warning"
          score={model.coverageGaps.score}
          signals={model.coverageGaps.signals}
          badge="02"
        />
        <SignalCard
          title="Project-Defined Risk Priorities"
          subtitle="Signal 3 · VRU class, occlusion, range & speed"
          accent="accent"
          score={model.riskPriorities.score}
          signals={model.riskPriorities.signals}
          badge="03"
        />
      </div>

      <PrioritizationStage
        anchor={model.anchor.scenario}
        anchorSource={anchorSourceLabel}
        anchorNote={model.anchor.note}
        anchorWasFailure={model.anchor.wasFailure}
        candidates={model.prioritized}
        selectedIdx={selectedIdx}
        onSelect={onPick}
      />

      <RecommendationCard
        top={selected}
        anchor={model.anchor.scenario}
        onRun={onRun}
        confirmation={confirmation}
      />

      <div className="mt-6 flex items-start justify-between gap-4 rounded-lg border border-border-subtle bg-bg-elevated px-4 py-3 text-[10px] text-text-subtle">
        <div>
          <div className="field-label text-text-subtle">Prototype disclosure</div>
          <p className="mt-1 max-w-3xl">
            The next-test selection shown here is a prototype concept and is implemented as an
            illustrative, deterministic fixture. It does not claim proven optimization, measured
            efficiency gains, validated safety benefits, or any industry-standard score.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1 text-right">
          <span className="chip chip-accent">Signal blend</span>
          <span>Failure Hist. 40% · Coverage 35% · Risk 25%</span>
        </div>
      </div>
    </PageSection>
  )
}

/**
 * @param {{
 *   title: string,
 *   subtitle: string,
 *   score: number,
 *   signals: { label: string, description: string, weight: number }[],
 *   accent: 'danger'|'warning'|'accent',
 *   badge: string
 * }} p
 */
function SignalCard({ title, subtitle, score, signals, accent, badge }) {
  const chipClass =
    accent === 'danger' ? 'chip-danger' : accent === 'warning' ? 'chip-warning' : 'chip-accent'
  const dotClass =
    accent === 'danger' ? 'bg-danger' : accent === 'warning' ? 'bg-warning' : 'bg-accent'
  return (
    <div className="panel relative overflow-hidden p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="chip">{badge}</span>
            <span className={`chip ${chipClass}`}>Signal</span>
          </div>
          <div className="mt-3 text-sm font-semibold tracking-tight">{title}</div>
          <div className="text-[11px] text-text-muted">{subtitle}</div>
        </div>
        <div className="text-right">
          <div className="field-label">Score</div>
          <div className={`text-xl font-bold tracking-tight ${dotClass.replace('bg-', 'text-').replace('/.*', '')}`}>
            {score.toFixed(2)}
          </div>
        </div>
      </div>
      <div className="divider my-4" />
      <ul className="space-y-2">
        {signals.length === 0 ? (
          <li className="text-[11px] text-text-subtle">No signal contributions for this anchor.</li>
        ) : signals.slice(0, 5).map((s) => (
          <li key={s.label + s.weight} className="flex items-start gap-2 text-[11px]">
            <span className={`status-dot mt-1.5 ${dotClass}`} />
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2">
                <div className="font-medium text-text">{s.label}</div>
                <div className="font-mono text-text-subtle">×{s.weight.toFixed(2)}</div>
              </div>
              <div className="text-text-muted">{s.description}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/**
 * @param {{
 *   anchor: import('@/types').ScenarioConfig,
 *   anchorSource: string,
 *   anchorNote: string,
 *   anchorWasFailure: boolean,
 *   candidates: { scenario: import('@/types').ScenarioConfig, score: number, heldConstant: string[], parameterChanged: string, rationaleSummary: string }[],
 *   selectedIdx: number,
 *   onSelect: (idx: number) => void
 * }} p
 */
function PrioritizationStage({ anchor, anchorSource, anchorNote, anchorWasFailure, candidates, selectedIdx, onSelect }) {
  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
      <div className="panel p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="field-label">Anchor scenario</div>
            <div className="mt-1 text-sm font-semibold tracking-tight">{anchorSource}</div>
          </div>
          <span className={`chip ${anchorWasFailure ? 'chip-danger' : 'chip-accent'}`}>
            {anchorWasFailure ? 'Illustrative failure' : 'Clean anchor'}
          </span>
        </div>
        <div className="divider my-4" />
        <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-[11px]">
          {Object.entries({
            weather: anchor.weather,
            lighting: anchor.lighting,
            trafficDensity: anchor.trafficDensity,
            roadUser: anchor.roadUser,
            occlusion: anchor.occlusion,
            distanceMeters: `${anchor.distanceMeters} m`,
            egoSpeedKmh: `${anchor.egoSpeedKmh} km/h`,
          }).map(([k, v]) => (
            <div key={k} className="rounded-md border border-border-subtle bg-bg p-2">
              <div className="text-text-subtle">{prettyFieldLabel(k)}</div>
              <div className="mt-0.5 font-medium">{String(v)}</div>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-[10px] text-text-subtle">{anchorNote}</p>
      </div>

      <div className="panel overflow-hidden">
        <div className="flex items-center justify-between border-b border-border-subtle px-4 py-3">
          <div>
            <div className="field-label">Scenario Prioritization</div>
            <div className="mt-1 text-sm font-semibold tracking-tight">
              {candidates.length} candidates · ranked by blended signal score
            </div>
          </div>
          <ArrowFlow />
        </div>
        <div className="divide-y divide-border-subtle">
          {candidates.map((c, i) => {
            const active = i === selectedIdx
            return (
              <button
                type="button"
                key={`${c.parameterChanged}-${i}`}
                onClick={() => onSelect(i)}
                className={`flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-surface-hover ${active ? 'bg-surface-active' : ''}`}
              >
                <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md bg-bg border border-border text-[11px] font-semibold">
                  #{i + 1}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    <div className="text-xs font-medium">{c.parameterChanged}</div>
                    <div className="text-[10px] text-text-subtle">
                      Held: {c.heldConstant.map(prettyFieldLabel).join(', ')}
                    </div>
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-[11px] text-text-muted">{c.rationaleSummary}</div>
                </div>
                <div className="text-right">
                  <div className="field-label">Score</div>
                  <div className={`text-base font-bold tracking-tight ${active ? 'text-accent' : ''}`}>
                    {c.score.toFixed(2)}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function ArrowFlow() {
  return (
    <div className="flex items-center gap-1.5 text-[10px] text-text-subtle">
      <span className="chip chip-danger">Signal 1</span>
      <span>→</span>
      <span className="chip chip-warning">Signal 2</span>
      <span>→</span>
      <span className="chip chip-accent">Signal 3</span>
      <span>→</span>
      <span className="chip">Blend</span>
    </div>
  )
}

/**
 * @param {{
 *   top: { scenario: import('@/types').ScenarioConfig, score: number, heldConstant: string[], parameterChanged: string, rationaleSummary: string, signals: {label:string,description:string,weight:number}[] } | null,
 *   anchor: import('@/types').ScenarioConfig,
 *   onRun: () => void,
 *   confirmation: null | { kind: string, text: string, scenario?: import('@/types').ScenarioConfig }
 * }} p
 */
function RecommendationCard({ top, anchor, onRun, confirmation }) {
  if (!top) {
    return (
      <div className="mt-6 panel p-8 text-center">
        <span className="chip chip-accent mx-auto">Recommendation</span>
        <p className="mt-3 text-xs text-text-muted">No candidates produced from the current fixture.</p>
      </div>
    )
  }
  const diff = diffFields(anchor, top.scenario)

  return (
    <div className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
      <div className="panel relative overflow-hidden p-5 border-accent/30 shadow-[0_0_0_1px_rgba(52,211,153,0.12)_inset]">
        <div className="absolute -right-16 -top-16 h-52 w-52 rounded-full bg-accent/5 blur-3xl" aria-hidden />
        <div className="relative">
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip chip-accent">Recommended Next Test</span>
            <span className="chip">#1 pick · score {top.score.toFixed(2)}</span>
            <span className="chip chip-warning">Illustrative</span>
          </div>
          <p className="mt-4 text-sm font-medium md:text-base">{top.rationaleSummary}</p>

          <div className="mt-5 grid gap-4 md:grid-cols-2">
            <HeldChangedBlock
              title="Held constant"
              subtitle="Controlled conditions retained from the anchor"
              rows={top.heldConstant.map((k) => ({
                label: prettyFieldLabel(k),
                value: prettyFieldValue(k, resolveField(anchor, k)),
              }))}
              variant="accent"
            />
            <HeldChangedBlock
              title="Parameter changed"
              subtitle="Probe region around the illustrative failure"
              rows={diff.map((d) => ({
                label: prettyFieldLabel(d.key),
                value: `${prettyFieldValue(d.key, d.from)} → ${prettyFieldValue(d.key, d.to)}`,
              }))}
              variant="warning"
            />
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onRun}
              className="btn btn-primary h-10 px-5 text-sm"
            >
              Run Next Scenario
            </button>
            <div className="text-[11px] text-text-subtle">
              Callback invokes the agreed <code className="rounded border border-border bg-bg px-1.5 py-0.5">onRunNextScenario(config)</code>.
            </div>
          </div>

          {confirmation ? (
            <div className="mt-4 flex items-start gap-2 rounded-md border border-accent-subtle bg-accent-subtle px-3 py-2.5 text-[11px] text-accent">
              <span className="status-dot mt-1 bg-accent" />
              <div className="flex-1">
                <div className="font-medium">{confirmation.text}</div>
                {confirmation.scenario ? (
                  <div className="mt-0.5 text-[10px] text-accent/80">
                    Config: {prettyConfigBrief(confirmation.scenario)}
                  </div>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <div className="panel p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="field-label">Ranked signal contributions</div>
            <div className="mt-1 text-sm font-semibold tracking-tight">Top reasons for this pick</div>
          </div>
        </div>
        <div className="divider my-4" />
        <ul className="space-y-2">
          {top.signals.slice(0, 6).map((s, i) => {
            const max = Math.max(1, ...top.signals.map((ss) => ss.weight))
            const pct = Math.round((s.weight / max) * 100)
            const tone = i < 2 ? 'bg-accent' : i < 4 ? 'bg-warning' : 'bg-border'
            return (
              <li key={s.label + s.weight} className="rounded-md border border-border-subtle bg-bg p-2.5 text-[11px]">
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium">{s.label}</div>
                  <div className="font-mono text-text-subtle">×{s.weight.toFixed(2)}</div>
                </div>
                <div className="mt-1 text-text-muted">{s.description}</div>
                <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-surface-active">
                  <div className={`h-full ${tone}`} style={{ width: `${pct}%` }} />
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

/**
 * @param {{ title: string, subtitle: string, rows: Array<{label:string,value:string}>, variant: 'accent'|'warning' }} p
 */
function HeldChangedBlock({ title, subtitle, rows, variant }) {
  const chip = variant === 'accent' ? 'chip-accent' : 'chip-warning'
  return (
    <div className="rounded-lg border border-border-subtle bg-bg p-3.5">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-[11px] font-semibold">{title}</div>
          <div className="text-[10px] text-text-subtle">{subtitle}</div>
        </div>
        <span className={`chip ${chip}`}>{rows.length}</span>
      </div>
      <ul className="mt-3 space-y-1.5 text-[11px]">
        {rows.map((r) => (
          <li key={r.label + r.value} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 hover:bg-surface">
            <div className="text-text-muted">{r.label}</div>
            <div className="font-medium text-text">{r.value}</div>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** @param {Partial<import('@/types').ScenarioConfig>} obj @param {string} key */
function resolveField(obj, key) {
  // @ts-ignore
  return obj[key]
}

/** @param {import('@/types').ScenarioConfig} a @param {import('@/types').ScenarioConfig} b */
function diffFields(a, b) {
  /** @type {Array<{ key: string, from: unknown, to: unknown }>} */
  const out = []
  const keys = /** @type {Array<keyof import('@/types').ScenarioConfig>} */ (
    ['weather', 'lighting', 'trafficDensity', 'roadUser', 'occlusion', 'distanceMeters', 'egoSpeedKmh']
  )
  for (const k of keys) if (a[k] !== b[k]) out.push({ key: k, from: a[k], to: b[k] })
  return out
}

/** @param {Partial<import('@/types').ScenarioConfig>} c */
function prettyConfigBrief(c) {
  return [
    c.weather, c.lighting, c.roadUser, c.occlusion,
    typeof c.distanceMeters === 'number' ? `${c.distanceMeters}m` : null,
    typeof c.egoSpeedKmh === 'number' ? `${c.egoSpeedKmh}km/h` : null,
  ].filter(Boolean).join(' · ')
}

// Silent reference to keep example-anchor import discoverable by consumers.
void EXAMPLE_ANCHOR_SCENARIO
void DEFAULT_SCENARIO

export default AdaptiveRecommendation
