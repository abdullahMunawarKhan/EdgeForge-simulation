import React, { useState, useMemo } from 'react'
import { PageSection } from '@/components/layout/PageSection.jsx'
import {
  WEATHER_LABEL,
  LIGHTING_LABEL,
  TRAFFIC_LABEL,
  ROAD_USER_LABEL,
  OCCLUSION_LABEL,
  OUTCOME_LABEL,
  SEVERITY_LABEL,
  PHASE4_FAILURE_CATEGORIES,
  mapToPhase4Category,
  generateFailureExplanation,
  getStructuredFailureBreakdown,
  getScenarioId,
} from '@/data/labels.js'
import { ROAD_USER_CLASSES, WEATHER_CONDITIONS, SEVERITY_LABELS } from '@/types.js'

/**
 * @typedef {Object} FailureAnalysisProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [description]
 * @property {import('@/types').FailureRecord[]} [failures]
 * @property {string|null} [selectedFailureId]
 * @property {(failureId: string|null) => void} [onSelectFailure]
 * @property {(failure: import('@/types').FailureRecord) => void} [onReplay]
 * @property {(tab: string) => void} [onNavigate]
 */

const CATEGORY_EXPLANATIONS = {
  missed_detection: 'Target was present but the illustrative model did not detect it.',
  false_positive: 'An obstacle was detected where no real object existed in the scene.',
  poor_localization: 'Target was detected, but estimated range or bounding box was inaccurate.',
  confidence_degradation: 'Target was detected, but prediction confidence or latency breached safety margins.',
}

export function FailureAnalysis({
  eyebrow = '04-A · Failure Analysis',
  title = 'Failure Analysis & Triage',
  description = 'Every illustrative failure lands in the register with a severity rank, object class, failure type and replay handle. Pick a record to view the ground-truth vs perception comparison and queue it for replay in the Scenario Lab.',
  failures = [],
  selectedFailureId = null,
  onSelectFailure,
  onReplay,
  onNavigate,
}) {
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [severityFilter, setSeverityFilter] = useState('all')
  const [roadUserFilter, setRoadUserFilter] = useState('all')
  const [weatherFilter, setWeatherFilter] = useState('all')
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)

  // Compute category counts
  const categoryCounts = useMemo(() => {
    const counts = {
      all: failures.length,
      missed_detection: 0,
      false_positive: 0,
      poor_localization: 0,
      confidence_degradation: 0,
    }
    for (const f of failures) {
      const cat = mapToPhase4Category(f.failureType)
      if (counts[cat] !== undefined) counts[cat]++
    }
    return counts
  }, [failures])

  // Filtered failure cases
  const filteredFailures = useMemo(() => {
    return failures.filter((f) => {
      const cat = mapToPhase4Category(f.failureType)
      if (categoryFilter !== 'all' && cat !== categoryFilter) return false
      if (severityFilter !== 'all' && f.severity !== severityFilter) return false
      if (roadUserFilter !== 'all' && f.objectClass !== roadUserFilter) return false
      if (weatherFilter !== 'all' && f.scenarioConfig?.weather !== weatherFilter) return false
      return true
    })
  }, [failures, categoryFilter, severityFilter, roadUserFilter, weatherFilter])

  // Active selected failure
  const activeFailure = useMemo(() => {
    if (selectedFailureId) {
      const found = failures.find((f) => f.id === selectedFailureId)
      if (found) return found
    }
    return filteredFailures[0] || failures[0] || null
  }, [failures, selectedFailureId, filteredFailures])

  // Active failure helper attributes
  const activeCategory = activeFailure ? mapToPhase4Category(activeFailure.failureType) : null
  const activeCatMeta = activeCategory ? PHASE4_FAILURE_CATEGORIES[activeCategory] : null
  const activeExplanation = activeFailure ? generateFailureExplanation(activeFailure) : ''
  const structuredBreakdown = activeFailure ? getStructuredFailureBreakdown(activeFailure) : null
  const activeScenarioId = activeFailure?.scenarioConfig ? getScenarioId(activeFailure.scenarioConfig) : 'SCN-????'

  // Extract outcome values
  const outcome = activeFailure?.outcome || {}
  const trueDistance = outcome.trueDistanceMeters ?? activeFailure?.scenarioConfig?.distanceMeters ?? 35
  const estDistance = outcome.distanceEstimateMeters
  const detectedClass = outcome.detectedClass
  const trueClass = outcome.trueClass ?? activeFailure?.objectClass ?? 'pedestrian'
  const confidence = outcome.confidence !== undefined ? Math.round(outcome.confidence * 100) : 45
  const latencyMs = outcome.latencyMs ?? 85
  const distanceDelta = estDistance !== undefined ? (estDistance - trueDistance).toFixed(1) : null
  const isClassMatch = detectedClass === trueClass
  const isLatencyBreach = latencyMs > 100

  // Most common failure category name
  const mostCommonCat = useMemo(() => {
    let topKey = 'missed_detection'
    let max = 0
    Object.entries(categoryCounts).forEach(([k, count]) => {
      if (k !== 'all' && count > max) {
        max = count
        topKey = k
      }
    })
    return PHASE4_FAILURE_CATEGORIES[topKey]?.label || 'Missed Detection'
  }, [categoryCounts])

  const handleReplayClick = () => {
    if (!activeFailure) return
    onReplay?.(activeFailure)
    if (onNavigate) {
      onNavigate('scenario-lab')
    }
  }

  const hasActiveFilters =
    categoryFilter !== 'all' ||
    severityFilter !== 'all' ||
    roadUserFilter !== 'all' ||
    weatherFilter !== 'all'

  const resetFilters = () => {
    setCategoryFilter('all')
    setSeverityFilter('all')
    setRoadUserFilter('all')
    setWeatherFilter('all')
  }

  if (failures.length === 0) {
    return (
      <PageSection id="failure-analysis">
        <div className="py-12 text-center space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-border-subtle bg-surface px-3 py-1 text-xs font-mono text-text-subtle">
            VALIDATION INCIDENTS
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-text">Failure Analysis &amp; Triage</h1>
          <p className="text-sm text-text-muted max-w-md mx-auto">
            Understand what went wrong during scenario validation.
          </p>
          <div className="mt-8 rounded-xl border border-border-subtle bg-surface/50 p-10 max-w-lg mx-auto space-y-4">
            <div className="text-base font-semibold text-text">No failures recorded</div>
            <p className="text-xs text-text-muted leading-relaxed">
              Run scenarios in Scenario Lab to generate illustrative perception validation results and inspect any failure cases.
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
    <PageSection id="failure-analysis">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="chip chip-danger">{eyebrow}</div>
          <h2 className="mt-2 text-2xl font-bold tracking-tight md:text-3xl">{title}</h2>
          <p className="mt-1 max-w-3xl text-sm text-text-muted">{description}</p>
        </div>
      </div>

      <div className="mb-6 prose-disclosure">
        <div className="flex items-start gap-2">
          <span className="chip chip-danger shrink-0">Illustrative triage</span>
          <p>
            Failure records below are illustrative and generated deterministically from scenario configurations
            scenario-space fixtures. No live CARLA simulator runs, YOLO inference, or real perception model
            outputs are produced. Ground-truth vs observed comparison visualizations are placeholders demonstrating
            showing how the triage UX composes when connected to a real validation stack.
          </p>
        </div>
      </div>
      {/* ========================================================================= */}
      {/* SECTION 1: PAGE HEADER & COMPACT SUMMARY ROW                              */}
      {/* ========================================================================= */}
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border-subtle pb-6">
          <div>
            <h1 className="text-3xl font-black tracking-tight text-text">Failure Analysis</h1>
            <p className="mt-1 text-sm text-text-muted">
              Understand what went wrong during scenario validation
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onNavigate?.('coverage')}
              className="btn btn-secondary text-xs font-medium px-3.5 py-1.5 flex items-center gap-1.5 hover:border-accent/40"
              type="button"
            >
              <span>▦</span>
              <span>View in Coverage →</span>
            </button>
          </div>
        </div>

        {/* Compact Summary Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-lg border border-border-subtle bg-surface/80 px-4 py-3">
            <div className="text-[11px] font-medium text-text-subtle">Total Cases</div>
            <div className="mt-1 text-xl font-bold text-text font-mono">{failures.length}</div>
          </div>

          <div className="rounded-lg border border-danger/30 bg-danger/5 px-4 py-3">
            <div className="text-[11px] font-medium text-danger">Failures</div>
            <div className="mt-1 text-xl font-bold text-danger font-mono">{failures.length}</div>
          </div>

          <div className="rounded-lg border border-border-subtle bg-surface/80 px-4 py-3">
            <div className="text-[11px] font-medium text-text-subtle">High / Critical</div>
            <div className="mt-1 text-xl font-bold text-warning font-mono">
              {failures.filter((f) => f.severity === 'critical' || f.severity === 'high').length}
            </div>
          </div>

          <div className="rounded-lg border border-border-subtle bg-surface/80 px-4 py-3">
            <div className="text-[11px] font-medium text-text-subtle">Most Common Failure</div>
            <div className="mt-1 text-sm font-bold text-text font-mono truncate">{mostCommonCat}</div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* SECTION 2: FAILURE SUMMARY — "What went wrong?"                          */}
      {/* ========================================================================= */}
      <div className="mt-8 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-text">What went wrong?</h2>
          <span className="text-xs text-text-subtle">Select a category to filter</span>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Object.entries(PHASE4_FAILURE_CATEGORIES).map(([catKey, catMeta]) => {
            const count = categoryCounts[catKey] || 0
            const isSelected = categoryFilter === catKey
            const explanation = CATEGORY_EXPLANATIONS[catKey]

            return (
              <button
                key={catKey}
                type="button"
                onClick={() => setCategoryFilter(isSelected ? 'all' : catKey)}
                className={`rounded-lg p-3.5 text-left border transition-all ${
                  isSelected
                    ? 'border-accent bg-accent/10 shadow-sm'
                    : 'border-border-subtle bg-surface/70 hover:bg-surface hover:border-border'
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-bold text-text">{catMeta.label}</span>
                  <span className={`chip text-[10px] font-mono font-bold ${
                    isSelected ? 'chip-accent' : 'bg-bg text-text-muted border-border-subtle'
                  }`}>
                    {count} {count === 1 ? 'failure' : 'failures'}
                  </span>
                </div>
                <p className="mt-2 text-[11px] text-text-muted leading-relaxed">
                  {explanation}
                </p>
              </button>
            )
          })}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* MAIN TWO-COLUMN WORKBENCH: FAILURE CASES (LEFT) + INSPECTOR (RIGHT)       */}
      {/* ========================================================================= */}
      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)] items-start">
        
        {/* ======================================================================= */}
        {/* SECTION 3: FAILURE REGISTER — "Failure Cases"                          */}
        {/* ======================================================================= */}
        <div className="rounded-xl border border-border-subtle bg-surface/70 p-4 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <h2 className="text-sm font-bold text-text">Failure Cases</h2>
              <p className="text-[11px] text-text-subtle">
                Select a case to see why the validation failed.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
              className={`text-xs px-2.5 py-1 rounded border transition font-mono ${
                showAdvancedFilters || hasActiveFilters
                  ? 'border-accent text-accent bg-accent/10'
                  : 'border-border-subtle text-text-muted hover:text-text'
              }`}
            >
              Filters {hasActiveFilters ? '●' : '▾'}
            </button>
          </div>

          {/* Collapsible Secondary Filter Bar */}
          {showAdvancedFilters && (
            <div className="p-3 rounded-lg border border-border-subtle bg-bg/80 space-y-2.5 text-xs">
              <div className="flex items-center justify-between text-[11px] text-text-subtle font-mono">
                <span>FILTER CONDITIONS</span>
                {hasActiveFilters && (
                  <button
                    type="button"
                    onClick={resetFilters}
                    className="text-accent hover:underline"
                  >
                    Reset all
                  </button>
                )}
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-[10px] text-text-subtle block mb-1">Severity</label>
                  <select
                    value={severityFilter}
                    onChange={(e) => setSeverityFilter(e.target.value)}
                    className="w-full rounded border border-border-subtle bg-surface px-2 py-1 text-[11px] text-text focus:outline-none"
                  >
                    <option value="all">All</option>
                    {SEVERITY_LABELS.map((s) => (
                      <option key={s} value={s}>{SEVERITY_LABEL[s]}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[10px] text-text-subtle block mb-1">Road User</label>
                  <select
                    value={roadUserFilter}
                    onChange={(e) => setRoadUserFilter(e.target.value)}
                    className="w-full rounded border border-border-subtle bg-surface px-2 py-1 text-[11px] text-text focus:outline-none"
                  >
                    <option value="all">All</option>
                    {ROAD_USER_CLASSES.map((ru) => (
                      <option key={ru} value={ru}>{ROAD_USER_LABEL[ru]}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="text-[10px] text-text-subtle block mb-1">Weather</label>
                  <select
                    value={weatherFilter}
                    onChange={(e) => setWeatherFilter(e.target.value)}
                    className="w-full rounded border border-border-subtle bg-surface px-2 py-1 text-[11px] text-text focus:outline-none"
                  >
                    <option value="all">All</option>
                    {WEATHER_CONDITIONS.map((w) => (
                      <option key={w} value={w}>{WEATHER_LABEL[w]}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          )}

          {/* Clean Case Table / List */}
          <div className="max-h-[520px] overflow-y-auto rounded-lg border border-border-subtle bg-bg divide-y divide-border-subtle/60">
            {filteredFailures.length === 0 ? (
              <div className="p-8 text-center text-xs text-text-subtle space-y-2">
                <div>No failure cases match the selected filters.</div>
                <button
                  type="button"
                  onClick={resetFilters}
                  className="text-xs text-accent hover:underline font-mono"
                >
                  Reset filters
                </button>
              </div>
            ) : (
              filteredFailures.map((f) => {
                const isSelected = activeFailure?.id === f.id
                const cat = mapToPhase4Category(f.failureType)
                const catMeta = PHASE4_FAILURE_CATEGORIES[cat]
                const sId = f.scenarioConfig ? getScenarioId(f.scenarioConfig) : 'SCN-????'

                return (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => onSelectFailure?.(f.id)}
                    className={`flex w-full items-center justify-between p-3 text-left transition ${
                      isSelected
                        ? 'bg-surface border-l-4 border-l-accent'
                        : 'hover:bg-surface-hover/60'
                    }`}
                  >
                    <div className="space-y-1 min-w-0 flex-1 pr-3">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-mono font-bold text-accent">{f.id}</span>
                        <span className="text-text-subtle font-mono text-[10px]">·</span>
                        <span className="font-semibold text-text truncate">
                          {ROAD_USER_LABEL[f.objectClass] || f.objectClass}
                        </span>
                      </div>
                      <div className="text-[11px] text-text-muted truncate">
                        {WEATHER_LABEL[f.scenarioConfig?.weather]} · {LIGHTING_LABEL[f.scenarioConfig?.lighting]} · {f.scenarioConfig?.distanceMeters}m
                      </div>
                    </div>

                    <div className="flex flex-col items-end gap-1 shrink-0">
                      <span className={`chip ${catMeta?.badgeClass} text-[9px] py-0 font-bold`}>
                        {catMeta?.label}
                      </span>
                      <span className={`text-[10px] font-mono ${
                        f.severity === 'critical' ? 'text-danger font-bold' :
                        f.severity === 'high' ? 'text-warning font-semibold' : 'text-accent'
                      }`}>
                        {SEVERITY_LABEL[f.severity] || f.severity}
                      </span>
                    </div>
                  </button>
                )
              })
            )}
          </div>

          <div className="text-[11px] text-text-subtle text-right">
            Showing {filteredFailures.length} of {failures.length} cases
          </div>
        </div>

        {/* ======================================================================= */}
        {/* SECTION 4, 5, 6, 7: SELECTED FAILURE INSPECTOR                         */}
        {/* ======================================================================= */}
        {activeFailure ? (
          <div className="rounded-xl border border-border-subtle bg-surface/80 p-5 space-y-6">
            
            {/* Header / Case Identity */}
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle pb-3.5">
              <div>
                <h2 className="text-base font-bold text-text">What happened?</h2>
                <div className="mt-0.5 flex items-center gap-2 text-xs font-mono text-text-subtle">
                  <span className="font-bold text-accent">{activeFailure.id}</span>
                  <span>·</span>
                  <span>Scenario: {activeScenarioId}</span>
                  <span>·</span>
                  <span className="text-danger font-bold uppercase">{activeCatMeta?.label}</span>
                </div>
              </div>

              <span className={`chip ${
                activeFailure.severity === 'critical' ? 'chip-danger' :
                activeFailure.severity === 'high' ? 'chip-warning' : 'chip-accent'
              } text-[10px] font-bold`}>
                {SEVERITY_LABEL[activeFailure.severity]} SEVERITY
              </span>
            </div>

            {/* 1. SCENARIO CONDITIONS */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle">
                1. Scenario Conditions Tested
              </div>
              <div className="rounded-lg border border-border-subtle bg-bg p-3 text-xs">
                <div className="font-medium text-text">
                  {WEATHER_LABEL[activeFailure.scenarioConfig?.weather]} •{' '}
                  {LIGHTING_LABEL[activeFailure.scenarioConfig?.lighting]} •{' '}
                  {TRAFFIC_LABEL[activeFailure.scenarioConfig?.trafficDensity]} Traffic •{' '}
                  {ROAD_USER_LABEL[activeFailure.objectClass]} •{' '}
                  {OCCLUSION_LABEL[activeFailure.scenarioConfig?.occlusion]} Occlusion •{' '}
                  {activeFailure.scenarioConfig?.distanceMeters}m •{' '}
                  {activeFailure.scenarioConfig?.egoSpeedKmh} km/h
                </div>
              </div>
            </div>

            {/* 2. EXPECTED VS OBSERVED (PLAIN LANGUAGE 2 COLUMNS) */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle">
                2. Expected vs Observed
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {/* EXPECTED */}
                <div className="rounded-lg border border-accent/30 bg-accent/5 p-3.5 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-accent">
                    <span>✓</span>
                    <span>EXPECTED (Ground Truth)</span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div>
                      <span className="text-text-subtle">Target: </span>
                      <span className="font-bold text-text">{ROAD_USER_LABEL[trueClass] || trueClass}</span>
                    </div>
                    <div>
                      <span className="text-text-subtle">True Distance: </span>
                      <span className="font-bold font-mono text-text">{trueDistance} m</span>
                    </div>
                    <div>
                      <span className="text-text-subtle">State: </span>
                      <span className="text-text-muted">Target active in ego vehicle path</span>
                    </div>
                  </div>
                </div>

                {/* OBSERVED */}
                <div className="rounded-lg border border-danger/30 bg-danger/5 p-3.5 space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-bold text-danger">
                    <span>⚠</span>
                    <span>OBSERVED (Model Prediction)</span>
                  </div>
                  <div className="space-y-1.5 text-xs">
                    <div>
                      <span className="text-text-subtle">Detected: </span>
                      <span className={`font-bold ${!detectedClass || detectedClass !== trueClass ? 'text-danger' : 'text-text'}`}>
                        {detectedClass ? ROAD_USER_LABEL[detectedClass] : 'Missed (No detection)'}
                      </span>
                    </div>
                    <div>
                      <span className="text-text-subtle">Distance Estimate: </span>
                      <span className="font-mono text-text">
                        {estDistance !== undefined ? `${estDistance} m` : 'N/A (Omitted)'}
                      </span>
                    </div>
                    <div>
                      <span className="text-text-subtle">Confidence & Latency: </span>
                      <span className="font-mono text-text">
                        {confidence}% · {latencyMs} ms {isLatencyBreach ? '(Late)' : ''}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* 3. WHY IT MATTERS (VALIDATION IMPACT) */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle">
                3. Why It Matters
              </div>
              <div className="rounded-lg border border-border-subtle bg-bg p-3 text-xs leading-relaxed text-text">
                {structuredBreakdown?.safetyImpact || (
                  activeCategory === 'missed_detection'
                    ? 'Target road user went entirely undetected at critical distance, creating a high-severity collision hazard.'
                    : activeCategory === 'poor_localization'
                    ? 'Inaccurate depth estimation degrades forward collision warning timing and trajectory planning safety buffers.'
                    : activeCategory === 'false_positive'
                    ? 'Phantom obstacle detection risks sudden phantom braking events in dense traffic.'
                    : 'Degraded confidence or excessive inference latency violates real-time safety response budgets.'
                )}
              </div>
            </div>

            {/* 4. WHY DID THIS FAIL? */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle">
                4. Why Did This Fail?
              </div>
              <div className="rounded-lg border border-border-subtle bg-bg p-3.5 space-y-2 text-xs">
                <div className="font-semibold text-text">
                  Primary Reason: {structuredBreakdown?.rootCause || activeCatMeta?.label}
                </div>
                <p className="text-text-muted leading-relaxed">
                  {activeExplanation}
                </p>
              </div>
            </div>

            {/* 5. CONDITIONS THAT CONTRIBUTED */}
            <div className="space-y-1.5">
              <div className="text-[11px] font-bold uppercase tracking-wider text-text-subtle">
                5. Conditions That Contributed
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <div className="rounded-md border border-border-subtle bg-bg px-2.5 py-1.5 font-mono text-[11px]">
                  <span className="text-text-subtle">Weather: </span>
                  <span className="font-semibold text-text">{WEATHER_LABEL[activeFailure.scenarioConfig?.weather]}</span>
                </div>
                <div className="rounded-md border border-border-subtle bg-bg px-2.5 py-1.5 font-mono text-[11px]">
                  <span className="text-text-subtle">Lighting: </span>
                  <span className="font-semibold text-text">{LIGHTING_LABEL[activeFailure.scenarioConfig?.lighting]}</span>
                </div>
                <div className="rounded-md border border-border-subtle bg-bg px-2.5 py-1.5 font-mono text-[11px]">
                  <span className="text-text-subtle">Occlusion: </span>
                  <span className="font-semibold text-text">{OCCLUSION_LABEL[activeFailure.scenarioConfig?.occlusion]}</span>
                </div>
                <div className="rounded-md border border-border-subtle bg-bg px-2.5 py-1.5 font-mono text-[11px]">
                  <span className="text-text-subtle">Traffic: </span>
                  <span className="font-semibold text-text">{TRAFFIC_LABEL[activeFailure.scenarioConfig?.trafficDensity]}</span>
                </div>
                <div className="rounded-md border border-border-subtle bg-bg px-2.5 py-1.5 font-mono text-[11px]">
                  <span className="text-text-subtle">Distance: </span>
                  <span className="font-semibold text-text">{activeFailure.scenarioConfig?.distanceMeters}m</span>
                </div>
                <div className="rounded-md border border-border-subtle bg-bg px-2.5 py-1.5 font-mono text-[11px]">
                  <span className="text-text-subtle">Speed: </span>
                  <span className="font-semibold text-text">{activeFailure.scenarioConfig?.egoSpeedKmh} km/h</span>
                </div>
              </div>
            </div>

            {/* 6. REPLAY & NATURAL ACTIONS */}
            <div className="pt-2 border-t border-border-subtle flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                onClick={() => onNavigate?.('coverage')}
                className="text-xs text-text-subtle hover:text-accent font-mono"
              >
                Inspect this slice in Coverage Explorer →
              </button>

              <button
                type="button"
                onClick={handleReplayClick}
                className="btn btn-primary px-5 py-2.5 text-xs font-semibold shadow-md active:scale-95 flex items-center gap-2"
              >
                <span>▶</span>
                <div className="text-left">
                  <div>Replay Scenario</div>
                  <div className="text-[9px] font-normal opacity-80">Open in Scenario Lab</div>
                </div>
              </button>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-border-subtle bg-surface/50 p-12 text-center text-xs text-text-subtle">
            Select a failure case from the list to inspect expected vs observed outputs and root cause analysis.
          </div>
        )}
      </div>
    </PageSection>
  )
}

export default FailureAnalysis
