import React, { useState, useMemo } from 'react'
import { PageSection } from '@/components/layout/PageSection.jsx'
import { computeCoverageMatrix } from '@/data/utils.js'
import {
  WEATHER_LABEL,
  LIGHTING_LABEL,
  TRAFFIC_LABEL,
  ROAD_USER_LABEL,
  OCCLUSION_LABEL,
  COVERAGE_LABEL,
  describeScenario,
} from '@/data/labels.js'

/**
 * @typedef {Object} CoverageExplorerProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [description]
 * @property {import('@/types').CoverageItem[]} [coverageItems]
 * @property {import('@/types').DemoRunResult[]} [runs]
 * @property {import('@/types').FailureRecord[]} [failures]
 * @property {Object|null} [historyData]
 * @property {'demo'|'loading'|'available'|'error'} [historyState]
 * @property {string|null} [historyError]
 * @property {(cfg: Partial<import('@/types').ScenarioConfig>) => void} [onApplyScenario]
 * @property {(tab: string) => void} [onNavigate]
 */

export function CoverageExplorer({
  eyebrow = '04-B · Coverage Explorer',
  title = 'Coverage Explorer',
  description = 'Projector view of multi-dimensional validation coverage: where EDGEFORGE has looked, where failures accumulate, and which combinations remain under-tested or fully untested.',
  runs = [],
  failures = [],
  historyData = null,
  historyState = 'demo',
  historyError = null,
  onApplyScenario,
  onNavigate,
}) {
  const [viewMode, setViewMode] = useState('weather_occlusion') // 'weather_occlusion' | 'weather_lighting' | 'traffic_roadUser'
  const [selectedCellKey, setSelectedCellKey] = useState(null)

  // Compute 2D matrix data deterministically from actual runs and failures
  const matrixData = useMemo(() => {
    return computeCoverageMatrix(runs, failures, viewMode)
  }, [runs, failures, viewMode])

  // Active selected cell
  const activeCell = useMemo(() => {
    if (selectedCellKey && matrixData.cellMap.has(selectedCellKey)) {
      return matrixData.cellMap.get(selectedCellKey)
    }
    const firstProne = matrixData.cells.find((c) => c.status === 'failure_prone')
    if (firstProne) return firstProne
    const firstTested = matrixData.cells.find((c) => c.status === 'tested' || c.status === 'under_tested')
    return firstTested || matrixData.cells[0] || null
  }, [matrixData, selectedCellKey])

  const handleOpenScenarioInLab = (cfg) => {
    if (!cfg) return
    onApplyScenario?.(cfg)
    if (onNavigate) {
      onNavigate('scenario-lab')
    }
  }

  const { summary, hotZones = [], coverageGaps = [] } = matrixData

  if (historyState !== 'demo') {
    const coverage = historyData?.coverage ?? {}
    const conditionCoverage = coverage.condition_coverage ?? {}
    const persistedRuns = Array.isArray(historyData?.runs) ? historyData.runs : []
    const scenarioMetricDefinitions = [
      { key: 'collision_count', label: 'Collisions', format: (value) => String(value) },
      { key: 'lane_invasion_count', label: 'Lane invasions', format: (value) => String(value) },
      { key: 'max_risk_score', label: 'Peak risk', format: (value) => value.toFixed(2) },
      {
        key: 'time_above_threshold',
        label: 'Time above risk threshold',
        format: (value) => `${value.toFixed(1)} s`,
      },
    ]
    return (
      <PageSection id="coverage">
        <div className="mb-6">
          <div className="chip chip-warning">{eyebrow}</div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight md:text-3xl">
            Persisted Run Coverage
          </h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">
            Coverage calculated from runs stored by the configured EdgeForge history API.
            Dimensions are shown only when they were recorded in scenario metadata.
          </p>
        </div>
        {historyState === 'loading' ? (
          <p className="text-sm text-text-muted">Loading persisted run coverage…</p>
        ) : historyState === 'error' ? (
          <p className="rounded-lg border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
            Could not load persisted run coverage: {historyError}
          </p>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-border-subtle bg-surface/80 px-4 py-3">
                <div className="text-[11px] text-text-subtle">Persisted runs</div>
                <div className="mt-1 font-mono text-xl font-bold text-text">
                  {coverage.total_runs ?? 0}
                </div>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface/80 px-4 py-3">
                <div className="text-[11px] text-text-subtle">Persisted failures</div>
                <div className="mt-1 font-mono text-xl font-bold text-text">
                  {coverage.total_failures ?? 0}
                </div>
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface/80 px-4 py-3">
                <div className="text-[11px] text-text-subtle">Recorded domain coverage</div>
                <div className="mt-1 font-mono text-xl font-bold text-text">
                  {Number.isFinite(coverage.overall_coverage_ratio)
                    ? `${(coverage.overall_coverage_ratio * 100).toFixed(1)}%`
                    : 'Unavailable'}
                </div>
              </div>
            </div>
            <div className="mt-5 rounded-lg border border-border-subtle bg-surface/70 p-4">
              <h3 className="text-sm font-semibold text-text">Recorded scenario conditions</h3>
              {Object.keys(conditionCoverage).length === 0 ? (
                <p className="mt-2 text-xs text-text-muted">
                  No numeric scenario-condition ranges have been recorded.
                </p>
              ) : (
                <dl className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(conditionCoverage).map(([name, values]) => (
                    <div key={name} className="rounded border border-border-subtle p-3">
                      <dt className="text-xs font-medium text-text">{name}</dt>
                      <dd className="mt-1 text-[11px] text-text-muted">
                        {`min ${values.min} · max ${values.max} · ${values.distinct_count} distinct`}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
            <div className="mt-5 rounded-lg border border-border-subtle bg-surface/70 p-4">
              <h3 className="text-sm font-semibold text-text">Completed run evaluation metrics</h3>
              {persistedRuns.length === 0 ? (
                <p className="mt-2 text-xs text-text-muted">
                  No completed runs are available.
                </p>
              ) : (
                <div className="mt-3 space-y-3">
                  {persistedRuns.map((run, index) => {
                    const metrics =
                      run.scenario_metrics && typeof run.scenario_metrics === 'object' &&
                      !Array.isArray(run.scenario_metrics)
                        ? run.scenario_metrics
                        : {}
                    return (
                      <div
                        key={run.run_id ?? `${run.scenario_id ?? 'run'}-${index}`}
                        className="rounded border border-border-subtle p-3"
                      >
                        <div className="text-xs font-medium text-text">
                          {run.run_id ?? 'Run ID unavailable'}
                          {run.scenario_id ? ` · ${run.scenario_id}` : ''}
                        </div>
                        <dl className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                          {scenarioMetricDefinitions.map(({ key, label, format }) => {
                            const value = metrics[key]
                            const available = typeof value === 'number' && Number.isFinite(value)
                            return (
                              <div key={key}>
                                <dt className="text-[11px] text-text-subtle">{label}</dt>
                                <dd className="mt-1 text-xs font-mono text-text">
                                  {available ? format(value) : 'Unavailable'}
                                </dd>
                              </div>
                            )
                          })}
                        </dl>
                      </div>
                    )
                  })}
                </div>
              )}
              <p className="mt-3 text-[11px] text-text-muted">
                Missing values are unavailable; recorded zero values are shown as zero.
              </p>
            </div>
            <div className="mt-4 text-xs text-text-muted">
              {Array.isArray(coverage.tested_scenarios) && coverage.tested_scenarios.length > 0
                ? `Scenarios: ${coverage.tested_scenarios.join(', ')}`
                : 'No scenarios are recorded yet.'}
            </div>
          </>
        )}
      </PageSection>
    )
  }

  if (runs.length === 0) {
    return (
      <PageSection id="coverage">
        <div className="py-12 text-center space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-surface px-3 py-1 text-xs font-mono text-text-subtle">
            SCENARIO SPACE
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-text">Coverage Explorer</h1>
          <p className="text-sm text-text-muted max-w-md mx-auto">
            See which scenario conditions have been tested and where validation gaps remain.
          </p>
          <div className="mt-8 rounded-xl border border-border-subtle bg-surface/50 p-10 max-w-lg mx-auto space-y-4">
            <div className="text-base font-semibold text-text">No coverage data yet</div>
            <p className="text-xs text-text-muted leading-relaxed">
              Run scenarios in Scenario Lab to begin building multi-dimensional validation coverage across weather, lighting, traffic, and actor parameters.
            </p>
            <button
              onClick={() => onNavigate?.('scenario-lab')}
              className="btn btn-primary text-xs font-semibold px-4 py-2"
              type="button"
            >
              Open Scenario Lab →
            </button>
          </div>
        </div>
      </PageSection>
    )
  }

  return (
    <PageSection id="coverage">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="chip chip-warning">{eyebrow}</div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight md:text-3xl">{title}</h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">{description}</p>
        </div>
      </div>

      <div className="mb-6 prose-disclosure">
        <div className="flex items-start gap-2">
          <span className="chip chip-warning shrink-0">Illustrative scenario-space</span>
          <p>
            Coverage heatmaps, hot-zone and coverage-gap lists are projections of the illustrative dataset —
            they do not represent exhaustive real-world scenario coverage nor the results of a real CARLA/YOLO
            validation campaign. The view is intended to demonstrate how the EDGEFORGE coverage projector UX
            composes when wired to real run logs.
          </p>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 1: PAGE HEADER & SUMMARY                                          */}
      {/* ========================================================================= */}
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border-subtle pb-6">
          <div>
            <h3 className="text-xl font-bold tracking-tight text-text">Coverage Snapshot</h3>
            <p className="mt-1 text-xs text-text-muted">
              Quick projector view of where validation has been concentrated so far.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onNavigate?.('failure-analysis')}
              className="btn btn-secondary text-xs font-medium px-3.5 py-1.5 flex items-center gap-1.5 hover:border-accent/40"
              type="button"
            >
              <span>⚠</span>
              <span>View Failure Cases →</span>
            </button>
          </div>
        </div>

        {/* SECTION 2: SCENARIO COVERAGE SUMMARY COUNTERS */}
        <div className="space-y-2">
          <div className="text-xs font-bold uppercase tracking-wider text-text-subtle font-mono">
            SCENARIO COVERAGE
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-lg border border-accent/30 bg-accent/5 px-4 py-3">
              <div className="text-[11px] font-medium text-accent">Tested</div>
              <div className="mt-1 text-2xl font-bold text-accent font-mono">{summary.testedCount}</div>
            </div>

            <div className="rounded-lg border border-warning/30 bg-warning/5 px-4 py-3">
              <div className="text-[11px] font-medium text-warning">Under-Tested</div>
              <div className="mt-1 text-2xl font-bold text-warning font-mono">{summary.underTestedCount}</div>
            </div>

            <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3">
              <div className="text-[11px] font-medium text-danger">Failure-Prone</div>
              <div className="mt-1 text-2xl font-bold text-danger font-mono">{summary.failureProneCount}</div>
            </div>

            <div className="rounded-lg border border-border-subtle bg-surface/80 px-4 py-3">
              <div className="text-[11px] font-medium text-text-subtle">Untested</div>
              <div className="mt-1 text-2xl font-bold text-text-muted font-mono">{summary.untestedCount}</div>
            </div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 3 & 4: "WHERE HAVE WE TESTED?" + SELECTED SCENARIO SLICE         */}
      {/* ========================================================================= */}
      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] items-start">
        
        {/* LEFT: COVERAGE MATRIX (VISUAL CENTERPIECE) */}
        <div className="rounded-xl border border-border-subtle bg-surface/70 p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-bold text-text">Where have we tested?</h2>
              <p className="text-xs text-text-muted mt-0.5">
                Each cell represents a combination of scenario conditions.
              </p>
            </div>

            {/* View Mode Selector */}
            <div className="flex items-center gap-1.5 text-xs font-mono">
              <span className="text-text-subtle hidden sm:inline">View by:</span>
              <div className="inline-flex rounded-lg border border-border-subtle bg-bg p-1">
                <button
                  type="button"
                  onClick={() => { setViewMode('weather_occlusion'); setSelectedCellKey(null); }}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                    viewMode === 'weather_occlusion'
                      ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                      : 'text-text-muted hover:text-text'
                  }`}
                >
                  Weather × Occlusion
                </button>
                <button
                  type="button"
                  onClick={() => { setViewMode('weather_lighting'); setSelectedCellKey(null); }}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                    viewMode === 'weather_lighting'
                      ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                      : 'text-text-muted hover:text-text'
                  }`}
                >
                  Weather × Lighting
                </button>
                <button
                  type="button"
                  onClick={() => { setViewMode('traffic_roadUser'); setSelectedCellKey(null); }}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                    viewMode === 'traffic_roadUser'
                      ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                      : 'text-text-muted hover:text-text'
                  }`}
                >
                  Traffic × Road User
                </button>
              </div>
            </div>
          </div>

          {/* Simple Legend */}
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs bg-bg/80 px-3 py-2 rounded-lg border border-border-subtle">
            <span className="text-[11px] font-medium text-text-subtle">Legend:</span>
            <div className="flex flex-wrap items-center gap-4 text-[11px] font-mono">
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-accent/30 border border-accent text-accent" />
                <span className="text-text">● Tested</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-warning/30 border border-warning text-warning" />
                <span className="text-text">● Under-Tested</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-danger/30 border border-danger text-danger" />
                <span className="text-text">● Failure-Prone</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm bg-surface border border-border-subtle text-text-subtle" />
                <span className="text-text-muted">● Untested</span>
              </div>
            </div>
          </div>

          {/* Matrix Table */}
          <div className="overflow-x-auto rounded-lg border border-border-subtle bg-bg p-2">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr>
                  <th className="p-2 text-left text-[11px] font-mono text-text-subtle uppercase border-b border-border-subtle">
                    {matrixData.yAxisTitle}
                  </th>
                  {matrixData.xKeys.map((xKey) => (
                    <th
                      key={xKey}
                      className="p-2 text-center text-[11px] font-mono text-text-subtle uppercase border-b border-border-subtle min-w-[70px]"
                    >
                      {matrixData.xLabels[xKey] || xKey}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle/50">
                {matrixData.yKeys.map((yKey) => (
                  <tr key={yKey} className="hover:bg-surface-hover/40 transition">
                    <td className="p-2 font-medium text-text text-[11px] whitespace-nowrap">
                      {matrixData.yLabels[yKey] || yKey}
                    </td>
                    {matrixData.xKeys.map((xKey) => {
                      const cellKey = `${yKey}__${xKey}`
                      const cell = matrixData.cellMap.get(cellKey)
                      const isSelected = activeCell?.cellKey === cellKey

                      const bgStyle =
                        cell.status === 'tested' ? 'bg-accent/15 border-accent/40 text-accent hover:bg-accent/25' :
                        cell.status === 'under_tested' ? 'bg-warning/15 border-warning/40 text-warning hover:bg-warning/25' :
                        cell.status === 'failure_prone' ? 'bg-danger/20 border-danger/50 text-danger hover:bg-danger/30 font-bold' :
                        'bg-surface/30 border-border-subtle text-text-subtle hover:bg-surface/70'

                      return (
                        <td key={xKey} className="p-1 text-center">
                          <button
                            type="button"
                            onClick={() => setSelectedCellKey(cellKey)}
                            className={`w-full rounded-md p-1.5 border transition flex flex-col items-center justify-center gap-0.5 min-h-[44px] ${bgStyle} ${
                              isSelected ? 'ring-2 ring-accent shadow-md scale-[1.03]' : ''
                            }`}
                          >
                            <div className="flex items-center gap-1 font-mono text-[11px]">
                              {cell.status === 'tested' && <span>✓</span>}
                              {cell.status === 'failure_prone' && <span>⚠</span>}
                              {cell.status === 'under_tested' && <span>?</span>}
                              {cell.status === 'untested' && <span>—</span>}
                              <span>{cell.runCount > 0 ? `${cell.runCount}r` : ''}</span>
                            </div>
                            {cell.failureCount > 0 && (
                              <span className="text-[9px] font-mono text-danger">
                                {cell.failureCount} fail
                              </span>
                            )}
                          </button>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* RIGHT: SELECTED SCENARIO SLICE */}
        {activeCell ? (
          <div className="rounded-xl border border-border-subtle bg-surface/80 p-5 space-y-5">
            <div className="flex items-center justify-between border-b border-border-subtle pb-3">
              <div>
                <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle font-mono">
                  SELECTED SCENARIO SLICE
                </div>
                <h3 className="text-base font-bold text-text mt-0.5">
                  {activeCell.yLabel} + {activeCell.xLabel}
                </h3>
              </div>

              <span className={`chip ${
                activeCell.status === 'tested' ? 'chip-accent' :
                activeCell.status === 'failure_prone' ? 'chip-danger' :
                activeCell.status === 'under_tested' ? 'chip-warning' : ''
              } font-bold text-[10px]`}>
                {COVERAGE_LABEL[activeCell.status] || activeCell.status}
              </span>
            </div>

            {/* Test Runs & Failure Stats */}
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-lg border border-border-subtle bg-bg p-2.5 text-center">
                <div className="text-[10px] text-text-subtle uppercase font-mono">Test Runs</div>
                <div className="mt-1 text-lg font-bold text-text font-mono">{activeCell.runCount}</div>
              </div>
              <div className="rounded-lg border border-border-subtle bg-bg p-2.5 text-center">
                <div className="text-[10px] text-text-subtle uppercase font-mono">Failures</div>
                <div className={`mt-1 text-lg font-bold font-mono ${activeCell.failureCount > 0 ? 'text-danger' : 'text-text'}`}>
                  {activeCell.failureCount}
                </div>
              </div>
              <div className="rounded-lg border border-border-subtle bg-bg p-2.5 text-center">
                <div className="text-[10px] text-text-subtle uppercase font-mono">Failure Rate</div>
                <div className={`mt-1 text-lg font-bold font-mono ${activeCell.failureRatePct > 0 ? 'text-danger' : 'text-accent'}`}>
                  {activeCell.failureRatePct}%
                </div>
              </div>
            </div>

            {/* Status & Short Explanation */}
            <div className="rounded-lg border border-border-subtle bg-bg p-3.5 space-y-1.5 text-xs">
              <div className="font-semibold text-text">
                {activeCell.status === 'failure_prone'
                  ? 'This condition has produced failures in multiple validation runs.'
                  : activeCell.status === 'under_tested'
                  ? 'This condition has low test volume and needs additional scenario runs.'
                  : activeCell.status === 'tested'
                  ? 'This condition has been tested with consistent pass rates.'
                  : 'No scenario runs have been recorded for this condition yet.'}
              </div>
            </div>

            {/* Why This Matters */}
            <div className="space-y-1">
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle">
                Why this matters
              </div>
              <div className="rounded-lg border border-border-subtle bg-bg p-3 text-xs text-text-muted leading-relaxed">
                {activeCell.status === 'failure_prone' ? (
                  `Adverse combination of ${activeCell.yLabel} and ${activeCell.xLabel} creates sensory attenuation and boundary masking, leading to repeated perception failures.`
                ) : activeCell.status === 'under_tested' ? (
                  `Validating safety requires sufficient test sample density across ${activeCell.yLabel} conditions to rule out latent perception vulnerabilities.`
                ) : activeCell.status === 'tested' ? (
                  `Perception models consistently detect targets under ${activeCell.yLabel} with ${activeCell.xLabel}.`
                ) : (
                  `Untested conditions leave safety blindspots in the validation envelope.`
                )}
              </div>
            </div>

            {/* Representative Scenario */}
            <div className="space-y-1">
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle">
                Representative Scenario
              </div>
              <div className="rounded-lg border border-border-subtle bg-surface p-3 text-xs text-text font-medium">
                {describeScenario(activeCell.representativeScenario)}
              </div>
            </div>

            {/* Actions */}
            <div className="pt-2 border-t border-border-subtle space-y-2">
              <button
                type="button"
                onClick={() => handleOpenScenarioInLab(activeCell.representativeScenario)}
                className="btn btn-primary w-full py-2.5 text-xs font-semibold shadow-md flex items-center justify-center gap-2"
              >
                <span>▶</span>
                <span>Configure in Scenario Lab & Replay</span>
              </button>

              {activeCell.failureCount > 0 && (
                <button
                  type="button"
                  onClick={() => onNavigate?.('failure-analysis')}
                  className="btn btn-secondary w-full py-2 text-xs font-medium text-text-muted hover:text-text"
                >
                  View Failure Cases in Incident Console →
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-border-subtle bg-surface/50 p-12 text-center text-xs text-text-subtle">
            Select a cell in the coverage matrix to inspect its test volume, failure concentration, and representative scenario.
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* SECTION 5 & 6: FAILURE-PRONE AREAS + COVERAGE GAPS                        */}
      {/* ========================================================================= */}
      <div className="mt-10 grid gap-6 md:grid-cols-2">
        
        {/* SECTION 6: CONDITIONS WITH REPEATED FAILURES */}
        <div className="rounded-xl border border-danger/30 bg-surface/70 p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-border-subtle pb-3">
            <div className="flex items-center gap-2">
              <span className="text-danger font-bold">⚠</span>
              <h2 className="text-sm font-bold text-text">Conditions with repeated failures</h2>
            </div>
            <span className="chip chip-danger text-[9px] font-mono">PRIORITY</span>
          </div>

          <p className="text-xs text-text-muted">
            Scenario combinations with the highest failure concentration.
          </p>

          <div className="space-y-2 max-h-60 overflow-y-auto">
            {hotZones.length === 0 ? (
              <div className="p-4 text-center text-xs text-text-subtle">
                No high-risk failure clusters detected.
              </div>
            ) : (
              hotZones.map((hz) => (
                <div
                  key={hz.cellKey}
                  className="rounded-lg border border-danger/20 bg-bg p-3 flex items-center justify-between gap-3 text-xs"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-text truncate">
                      {hz.yLabel} + {hz.xLabel}
                    </div>
                    <div className="text-[11px] text-text-muted font-mono mt-0.5">
                      {hz.failureCount} failures / {hz.runCount} runs ({hz.failureRatePct}% failure rate)
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCellKey(hz.cellKey)
                      handleOpenScenarioInLab(hz.representativeScenario)
                    }}
                    className="btn btn-secondary text-[11px] px-2.5 py-1 text-accent font-semibold shrink-0"
                  >
                    Test in Lab →
                  </button>
                </div>
              ))
            )}
          </div>
        </div>

        {/* SECTION 5: WHERE SHOULD WE TEST MORE? (COVERAGE GAPS) */}
        <div className="rounded-xl border border-warning/30 bg-surface/70 p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-border-subtle pb-3">
            <div className="flex items-center gap-2">
              <span className="text-warning font-bold">?</span>
              <h2 className="text-sm font-bold text-text">Where should we test more?</h2>
            </div>
            <span className="chip chip-warning text-[9px] font-mono">COVERAGE GAPS</span>
          </div>

          <p className="text-xs text-text-muted">
            Under-tested or unverified scenario boundaries requiring additional test runs.
          </p>

          <div className="space-y-2 max-h-60 overflow-y-auto">
            {coverageGaps.length === 0 ? (
              <div className="p-4 text-center text-xs text-text-subtle">
                Full coverage achieved across all slices.
              </div>
            ) : (
              coverageGaps.map((cg) => (
                <div
                  key={cg.cellKey}
                  className="rounded-lg border border-warning/20 bg-bg p-3 flex items-center justify-between gap-3 text-xs"
                >
                  <div className="min-w-0 flex-1">
                    <div className="font-bold text-text truncate">
                      {cg.yLabel} + {cg.xLabel}
                    </div>
                    <div className="text-[11px] text-text-muted font-mono mt-0.5">
                      Status: <span className="text-warning font-semibold">{cg.status === 'untested' ? 'Untested (0 runs)' : `Under-Tested (${cg.runCount} run)`}</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCellKey(cg.cellKey)
                      handleOpenScenarioInLab(cg.representativeScenario)
                    }}
                    className="btn btn-secondary text-[11px] px-2.5 py-1 text-warning font-semibold shrink-0"
                  >
                    Run Test →
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </PageSection>
  )
}

export default CoverageExplorer
