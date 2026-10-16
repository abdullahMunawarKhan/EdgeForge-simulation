import React from 'react'
import {
  WEATHER_LABEL,
  ROAD_USER_LABEL,
  OUTCOME_LABEL,
  SEVERITY_LABEL,
  getScenarioId,
  mapToPhase4Category,
  PHASE4_FAILURE_CATEGORIES,
} from '@/data/labels.js'
import { computeCoverageMatrix } from '@/data/utils.js'

/**
 * @typedef {Object} OverviewPageProps
 * @property {import('@/types').PageDemoState} demo
 * @property {(tab: string) => void} onNavigate
 */

export function OverviewPage({ demo, onNavigate }) {
  const runs = demo.dataset.runs || []
  const failures = demo.dataset.failures || []
  const totalRuns = runs.length
  const totalFailures = failures.length
  const failureRatePct = totalRuns > 0 ? ((totalFailures / totalRuns) * 100).toFixed(1) : '0.0'

  // Compute coverage matrix to determine failure prone slices count
  const matrix = computeCoverageMatrix(runs, failures, 'weather_occlusion')
  const failureProneSlicesCount = matrix.failureProneCount

  // Latest run / validation result
  const latestRun = demo.lastRun || runs[0] || null
  const latestScenarioId = latestRun ? getScenarioId(latestRun.scenarioConfig) : 'SCN-DEFAULT'
  const isLatestPassed = latestRun?.outcome?.kind === 'detected_ok'
  const latestOutcomeKind = latestRun?.outcome?.kind || 'nominal'
  const latestSeverity = latestRun?.outcome?.severity || 'nominal'

  // Most recent runs list (top 6)
  const recentRuns = runs.slice(0, 8)

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 md:px-6 space-y-8">
      {/* HERO COMMAND CENTER HEADER */}
      <div className="relative overflow-hidden rounded-2xl border border-border-subtle bg-gradient-to-b from-surface/90 via-surface/60 to-bg/80 p-6 md:p-10 backdrop-blur-xl shadow-panel">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-accent/5 blur-3xl pointer-events-none" />
        <div className="absolute -left-20 -bottom-20 h-80 w-80 rounded-full bg-blue-500/5 blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-3xl space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3 py-1 text-xs font-mono font-bold text-accent">
            <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
            AUTONOMOUS SYSTEM VALIDATION WORKBENCH
          </div>

          <h1 className="text-3xl font-black tracking-tight text-text sm:text-5xl">
            EDGEFORGE
          </h1>

          <p className="text-sm md:text-base text-text-muted leading-relaxed">
            Scenario-driven perception validation, failure analysis and scenario-space coverage.
            Continuously probe edge-case safety envelopes for autonomous perception systems under controlled multi-axis stress.
          </p>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              onClick={() => onNavigate('scenario-lab')}
              className="btn btn-primary text-xs font-semibold px-4 py-2.5 shadow-sm active:scale-95 flex items-center gap-2"
              type="button"
            >
              <span>▶</span>
              <span>OPEN SCENARIO LAB</span>
            </button>
            <button
              onClick={() => onNavigate('failure-analysis')}
              className="btn btn-secondary text-xs font-semibold px-4 py-2.5 active:scale-95 flex items-center gap-2"
              type="button"
            >
              <span>⚠</span>
              <span>VIEW FAILURE ANALYSIS</span>
            </button>
            <button
              onClick={() => onNavigate('coverage')}
              className="btn btn-secondary text-xs font-semibold px-4 py-2.5 active:scale-95 flex items-center gap-2"
              type="button"
            >
              <span>▦</span>
              <span>EXPLORE COVERAGE</span>
            </button>
          </div>
        </div>
      </div>

      {/* COMPACT SYSTEM PIPELINE */}
      <div className="rounded-xl border border-border-subtle bg-surface/70 p-5 backdrop-blur-sm">
        <div className="flex items-center justify-between border-b border-border-subtle pb-3 mb-4">
          <div className="flex items-center gap-2">
            <span className="chip chip-accent font-mono text-[9px] font-bold">SYSTEM WORKFLOW</span>
            <span className="text-xs font-bold text-text uppercase tracking-wider">
              CLOSED-LOOP VALIDATION PIPELINE
            </span>
          </div>
          <span className="text-[10px] font-mono text-text-subtle hidden sm:inline">
            CONTINUOUS TRACEABILITY
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-center">
          {[
            { step: '01', title: 'SCENARIO', desc: '7-Axis Controlled Synthesis', target: 'scenario-lab' },
            { step: '02', title: 'SIMULATION', desc: 'Raw Sensor & Dynamics Preview', target: 'scenario-lab' },
            { step: '03', title: 'PERCEPTION', desc: 'Bounding & Latency Proposals', target: 'scenario-lab' },
            { step: '04', title: 'VALIDATION', desc: 'Deterministic Ground Truth Compare', target: 'scenario-lab' },
            { step: '05', title: 'FAILURE ANALYSIS', desc: '4-Category Incident Triage', target: 'failure-analysis' },
            { step: '06', title: 'COVERAGE', desc: '2D Scenario Space Heatmaps', target: 'coverage' },
          ].map((item, idx) => (
            <button
              key={item.step}
              onClick={() => onNavigate(item.target)}
              type="button"
              className="group flex flex-col items-center justify-between p-3 rounded-lg border border-border-subtle bg-bg/60 hover:bg-surface hover:border-accent/40 transition text-left"
            >
              <div className="w-full flex items-center justify-between text-[10px] font-mono text-text-subtle mb-2">
                <span className="font-bold text-accent group-hover:text-accent-hover">{item.step}</span>
                <span className="text-[9px] opacity-60">→</span>
              </div>
              <div className="w-full">
                <div className="text-xs font-bold text-text group-hover:text-accent transition">
                  {item.title}
                </div>
                <div className="text-[10px] text-text-muted mt-0.5 line-clamp-2">
                  {item.desc}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* LIVE SYSTEM METRICS & LATEST VALIDATION GRID */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Left 2 Cols: Live System Summary Metrics */}
        <div className="lg:col-span-2 space-y-6">
          <div className="rounded-xl border border-border-subtle bg-surface/70 p-6 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4 border-b border-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
                <h2 className="text-sm font-bold tracking-wide text-text uppercase font-mono">
                  LIVE SYSTEM TELEMETRY
                </h2>
              </div>
              <span className="chip text-[9px] font-mono font-semibold">SHARED STATE</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="rounded-lg border border-border-subtle bg-bg/70 p-4">
                <div className="text-[10px] font-mono text-text-subtle uppercase">TOTAL RUNS</div>
                <div className="mt-1 text-2xl font-black text-text font-mono">{totalRuns}</div>
                <div className="mt-1 text-[10px] text-text-muted">Synthesized executions</div>
              </div>

              <div className="rounded-lg border border-border-subtle bg-bg/70 p-4">
                <div className="text-[10px] font-mono text-text-subtle uppercase">TOTAL FAILURES</div>
                <div className="mt-1 text-2xl font-black text-danger font-mono">{totalFailures}</div>
                <div className="mt-1 text-[10px] text-text-muted">Perception breaches</div>
              </div>

              <div className="rounded-lg border border-border-subtle bg-bg/70 p-4">
                <div className="text-[10px] font-mono text-text-subtle uppercase">FAILURE RATE</div>
                <div className="mt-1 text-2xl font-black text-amber-400 font-mono">{failureRatePct}%</div>
                <div className="mt-1 text-[10px] text-text-muted">Edge-case stress yield</div>
              </div>

              <div className="rounded-lg border border-border-subtle bg-bg/70 p-4">
                <div className="text-[10px] font-mono text-text-subtle uppercase">FAILURE SLICES</div>
                <div className="mt-1 text-2xl font-black text-accent font-mono">{failureProneSlicesCount}</div>
                <div className="mt-1 text-[10px] text-text-muted">High-risk hot zones</div>
              </div>
            </div>

            {/* Failure Categories Breakdown */}
            <div className="mt-6 pt-4 border-t border-border-subtle">
              <div className="text-[11px] font-mono text-text-subtle mb-3 uppercase font-bold">
                FAILURE CLASSIFICATION BREAKDOWN
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                {Object.entries(PHASE4_FAILURE_CATEGORIES).map(([catKey, cat]) => {
                  const count = failures.filter((f) => mapToPhase4Category(f.failureType) === catKey).length
                  return (
                    <div key={catKey} className="rounded-md border border-border-subtle bg-bg/50 p-2.5 flex flex-col justify-between">
                      <span className="text-[10px] text-text-muted">{cat.label}</span>
                      <span className="text-base font-bold text-text mt-1">{count}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>

          {/* RECENT VALIDATION RUNS TABLE */}
          <div className="rounded-xl border border-border-subtle bg-surface/70 p-6 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4 border-b border-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold tracking-wide text-text uppercase font-mono">
                  RECENT VALIDATION RUNS
                </h2>
                <span className="chip font-mono text-[9px]">LATEST {recentRuns.length}</span>
              </div>
              <button
                onClick={() => onNavigate('scenario-lab')}
                className="text-xs text-accent hover:underline font-mono"
                type="button"
              >
                OPEN WORKSPACE →
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-border-subtle text-[10px] text-text-subtle uppercase">
                    <th className="pb-2 font-semibold">RUN ID</th>
                    <th className="pb-2 font-semibold">SCENARIO</th>
                    <th className="pb-2 font-semibold">WEATHER</th>
                    <th className="pb-2 font-semibold">TARGET</th>
                    <th className="pb-2 font-semibold">VERDICT</th>
                    <th className="pb-2 font-semibold">SEVERITY</th>
                    <th className="pb-2 text-right font-semibold">ACTION</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border-subtle/50">
                  {recentRuns.map((r) => {
                    const scnId = getScenarioId(r.scenarioConfig)
                    const isOk = r.outcome?.kind === 'detected_ok'
                    return (
                      <tr key={r.runId} className="hover:bg-surface/90 transition">
                        <td className="py-2.5 font-bold text-accent">{r.runId}</td>
                        <td className="py-2.5 text-text-muted">{scnId}</td>
                        <td className="py-2.5 text-text-muted">{WEATHER_LABEL[r.scenarioConfig.weather]}</td>
                        <td className="py-2.5 text-text">{ROAD_USER_LABEL[r.scenarioConfig.roadUser]}</td>
                        <td className="py-2.5">
                          <span
                            className={`inline-flex items-center gap-1 text-[10px] font-bold ${
                              isOk ? 'text-accent' : 'text-danger'
                            }`}
                          >
                            <span>{isOk ? '✓' : '⚠'}</span>
                            <span>{OUTCOME_LABEL[r.outcome?.kind] || 'EVALUATED'}</span>
                          </span>
                        </td>
                        <td className="py-2.5">
                          <span className={`chip text-[9px] ${r.outcome?.severity === 'critical' ? 'chip-danger' : r.outcome?.severity === 'high' ? 'border-amber-500/30 text-amber-400 bg-amber-500/10' : 'chip-accent'}`}>
                            {SEVERITY_LABEL[r.outcome?.severity] || 'Nominal'}
                          </span>
                        </td>
                        <td className="py-2.5 text-right">
                          <button
                            onClick={() => {
                              demo.onScenarioChange(r.scenarioConfig)
                              onNavigate('scenario-lab')
                            }}
                            className="text-[10px] text-accent hover:underline px-2 py-0.5 rounded bg-accent/10 border border-accent/20"
                            type="button"
                          >
                            REPLAY
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right 1 Col: Latest Validation Summary & Quick Actions */}
        <div className="space-y-6">
          <div className="rounded-xl border border-border-subtle bg-surface/70 p-6 backdrop-blur-sm">
            <div className="flex items-center justify-between mb-4 border-b border-border-subtle pb-3">
              <span className="chip chip-accent font-mono text-[9px] font-bold">LATEST EXECUTION</span>
              <span className="text-[10px] font-mono text-text-subtle">{latestRun?.runId || 'RUN-0000'}</span>
            </div>

            {latestRun ? (
              <div className="space-y-4 text-xs font-mono">
                <div className="rounded-lg border border-border-subtle bg-bg/80 p-4 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-text-subtle">SCENARIO ID:</span>
                    <span className="font-bold text-accent">{latestScenarioId}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-subtle">TARGET OBJECT:</span>
                    <span className="font-semibold text-text">
                      {ROAD_USER_LABEL[latestRun.scenarioConfig.roadUser]}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-subtle">CONDITIONS:</span>
                    <span className="text-text-muted">
                      {WEATHER_LABEL[latestRun.scenarioConfig.weather]} · {latestRun.scenarioConfig.egoSpeedKmh} km/h
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-text-subtle">RANGE:</span>
                    <span className="text-text font-bold">{latestRun.scenarioConfig.distanceMeters} m</span>
                  </div>
                  <div className="pt-2 border-t border-border-subtle flex justify-between items-center">
                    <span className="text-text-subtle">VERDICT:</span>
                    <span
                      className={`font-bold ${
                        isLatestPassed ? 'text-accent' : 'text-danger'
                      }`}
                    >
                      {isLatestPassed ? '✓ VALIDATED' : '⚠ PERCEPTION FAILURE'}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-text-subtle">SEVERITY:</span>
                    <span className="chip chip-danger text-[9px]">{SEVERITY_LABEL[latestSeverity]}</span>
                  </div>
                </div>

                <div className="space-y-2 pt-2">
                  <button
                    onClick={() => {
                      demo.onScenarioChange(latestRun.scenarioConfig)
                      onNavigate('scenario-lab')
                    }}
                    className="w-full btn btn-primary text-xs py-2 font-semibold flex items-center justify-center gap-2"
                    type="button"
                  >
                    <span>▶</span>
                    <span>OPEN IN SCENARIO LAB</span>
                  </button>

                  <button
                    onClick={() => onNavigate('failure-analysis')}
                    className="w-full btn btn-secondary text-xs py-2 font-semibold flex items-center justify-center gap-2"
                    type="button"
                  >
                    <span>⚠</span>
                    <span>VIEW FAILURE ANALYSIS</span>
                  </button>

                  <button
                    onClick={() => onNavigate('coverage')}
                    className="w-full btn btn-secondary text-xs py-2 font-semibold flex items-center justify-center gap-2"
                    type="button"
                  >
                    <span>▦</span>
                    <span>EXPLORE COVERAGE MATRIX</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="p-6 text-center text-text-subtle text-xs">
                No runs executed yet. Open Scenario Lab to execute your first validation run.
              </div>
            )}
          </div>

          {/* Quick Guidance Box */}
          <div className="rounded-xl border border-border-subtle bg-surface/50 p-5 text-xs text-text-muted space-y-2.5">
            <div className="flex items-center gap-2 text-text font-bold font-mono">
              <span className="text-accent">ℹ</span>
              <span>ENGINEERING PRINCIPLES</span>
            </div>
            <p className="text-[11px] leading-relaxed">
              EDGEFORGE enforces deterministic ADAS validation. Every scenario signature produces identical simulation states, Ground Truth comparisons, and incident taxonomy.
            </p>
            <div className="pt-2 border-t border-border-subtle/60 text-[10px] font-mono text-text-subtle">
              SIM ENGINE: DETERMINISTIC DEMO · NO STOCHASTIC JITTER
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default OverviewPage
