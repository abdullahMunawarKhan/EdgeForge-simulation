import React, { useState, useEffect } from 'react'
import { PageSection, SectionHeader } from '@/components/layout/PageSection.jsx'
import { SimulationPreview } from './SimulationPreview.jsx'
import {
  DEFAULT_SCENARIO,
  WEATHER_LABEL,
  LIGHTING_LABEL,
  TRAFFIC_LABEL,
  ROAD_USER_LABEL,
  OCCLUSION_LABEL,
  OUTCOME_LABEL,
  SEVERITY_LABEL,
  describeScenario,
  getScenarioId,
  getScenarioStressors,
} from '@/data/labels.js'
import {
  WEATHER_CONDITIONS,
  LIGHTING_CONDITIONS,
  TRAFFIC_DENSITIES,
  ROAD_USER_CLASSES,
  OCCLUSION_LEVELS,
} from '@/types.js'

/**
 * @typedef {Object} ScenarioLabProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [description]
 * @property {import('@/types').ScenarioConfig} scenario
 * @property {import('@/types').DemoRunResult|null} [lastRun]
 * @property {boolean} [isRunning]
 * @property {import('@/types').DemoRunResult[]} [recentRuns]
 * @property {(cfg: Partial<import('@/types').ScenarioConfig>) => void} [onScenarioChange]
 * @property {() => void} [onRun]
 * @property {() => void} [onReset]
 */

/**
 * Standard ADAS edge case presets for quick testing
 */
const SCENARIO_PRESETS = [
  {
    name: 'Night Fog Pedestrian',
    description: 'High-severity VRU edge case with substantial occlusion and unlit night',
    badge: 'CRITICAL VRU',
    config: {
      weather: 'fog',
      lighting: 'night_unlit',
      trafficDensity: 'heavy',
      roadUser: 'pedestrian',
      occlusion: 'substantial',
      distanceMeters: 18,
      egoSpeedKmh: 55,
    },
  },
  {
    name: 'Tunnel Exit Cyclist',
    description: 'Sudden dynamic range shift with partially occluded cyclist at close range',
    badge: 'DYNAMIC RANGE',
    config: {
      weather: 'clear',
      lighting: 'tunnel_exit',
      trafficDensity: 'moderate',
      roadUser: 'bicycle',
      occlusion: 'partial',
      distanceMeters: 28,
      egoSpeedKmh: 45,
    },
  },
  {
    name: 'Highway Heavy Rain Truck',
    description: 'High-speed spray and adverse visibility against commercial vehicle',
    badge: 'HIGHWAY TTC',
    config: {
      weather: 'heavy_rain',
      lighting: 'day_overcast',
      trafficDensity: 'heavy',
      roadUser: 'heavy_truck',
      occlusion: 'partial',
      distanceMeters: 65,
      egoSpeedKmh: 95,
    },
  },
  {
    name: 'Urban Nominal Baseline',
    description: 'Direct daylight baseline driving scenario with unobstructed visibility',
    badge: 'BASELINE',
    config: {
      weather: 'clear',
      lighting: 'day_direct',
      trafficDensity: 'light',
      roadUser: 'passenger_vehicle',
      occlusion: 'none',
      distanceMeters: 40,
      egoSpeedKmh: 50,
    },
  },
]

/**
 * Phase 3 & 4 — Scenario Validation Console & Simulation Preview
 * @param {ScenarioLabProps} props
 */
export function ScenarioLab({
  eyebrow = '03 · Scenario Lab',
  title = 'Scenario Validation Console',
  description = 'Configure controlled environmental, lighting, traffic, and actor parameters across 7 dimensions to stress-test perception robustness. Executing a validation run triggers deterministic evaluation feeding Failure Analysis and Coverage Explorer.',
  scenario = DEFAULT_SCENARIO,
  lastRun = null,
  isRunning = false,
  recentRuns = [],
  onScenarioChange,
  onRun,
  onReset,
  onNavigate,
}) {
  const [activeCategory, setActiveCategory] = useState('environment') // 'environment' | 'complexity' | 'actor' | 'dynamics' | 'presets'
  const [executionStep, setExecutionStep] = useState(0)

  const scenarioId = getScenarioId(scenario)
  const scenarioNarrative = describeScenario(scenario)
  const stressors = getScenarioStressors(scenario)

  // Multi-step progress animation simulation
  useEffect(() => {
    let timer
    if (isRunning) {
      setExecutionStep(1)
      const t1 = setTimeout(() => setExecutionStep(2), 160)
      const t2 = setTimeout(() => setExecutionStep(3), 320)
      const t3 = setTimeout(() => setExecutionStep(4), 480)
      return () => {
        clearTimeout(t1)
        clearTimeout(t2)
        clearTimeout(t3)
      }
    } else {
      setExecutionStep(0)
    }
    return () => clearTimeout(timer)
  }, [isRunning])

  const updateField = (key, value) => {
    onScenarioChange?.({ [key]: value })
  }

  const applyPreset = (preset) => {
    onScenarioChange?.(preset.config)
  }

  const handleJumpToAnalysis = () => {
    if (onNavigate) {
      onNavigate('failure-analysis')
    } else {
      const analysisEl = document.getElementById('analysis')
      if (analysisEl) {
        analysisEl.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }
    }
  }

  // Execution step labels
  const executionLabels = [
    'INITIALIZING TEST SUITE…',
    'CONFIGURING SCENARIO PARAMETERS…',
    'RUNNING SENSORY SIMULATION…',
    'EVALUATING MODEL PROPOSALS…',
    'FINALIZING VALIDATION VERDICT…',
  ]

  const isPassed = lastRun?.outcome?.kind === 'detected_ok'
  const isFailed = Boolean(lastRun && !isPassed)

  return (
    <PageSection id="scenario">
      <SectionHeader eyebrow={eyebrow} title={title} description={description} />

      <div className="mt-4 prose-disclosure">
        <div className="flex items-start gap-2">
          <span className="chip chip-warning shrink-0">Illustrative output</span>
          <p>
            Validation runs and perception outcomes shown below are generated deterministically from
            the scenario configuration — <strong>no live CARLA simulation or YOLO inference is running.</strong>
            Failures, latencies and coverage metrics are illustrative and are meant to demonstrate how the
            EDGEFORGE validation loop composes when connected to a real simulator stack.
          </p>
        </div>
      </div>

      {/* TOP STATUS STRIP: Mission-Critical Console Header */}
      <div className="mt-6 rounded-lg border border-border-subtle bg-surface/70 p-3.5 backdrop-blur-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="field-label text-[9px]">Scenario ID:</span>
              <span className="font-mono text-accent font-bold bg-accent/10 px-2 py-0.5 rounded border border-accent/20">
                {scenarioId}
              </span>
            </div>
            <span className="text-border hidden sm:inline">|</span>
            <div className="flex items-center gap-1.5 font-mono text-[11px]">
              <span className="text-text-subtle">STATUS:</span>
              <span className={`font-semibold ${isRunning ? 'text-warning' : lastRun ? 'text-accent' : 'text-text-muted'}`}>
                {isRunning ? '● SIMULATING' : lastRun ? (isPassed ? '● COMPLETE (PASSED)' : '● COMPLETE (FAILURE)') : '● READY'}
              </span>
            </div>
            <span className="text-border hidden sm:inline">|</span>
            <div className="flex items-center gap-1.5 font-mono text-[11px] text-text-muted">
              <span className="text-text-subtle">DIMENSIONS:</span>
              <span className="font-semibold text-text">7 AXES ACTIVE</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              className="btn btn-ghost h-7 px-2.5 text-xs text-text-muted hover:text-text"
              onClick={onReset}
              title="Reset scenario to default nominal baseline"
            >
              Reset Baseline
            </button>
          </div>
        </div>
      </div>

      {/* Main Grid: Configurator (Left) + Simulation Preview & Result (Right) */}
      <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1.25fr)]">
        
        {/* LEFT COLUMN: SCENARIO CONFIGURATOR CONSOLE */}
        <div className="panel flex flex-col justify-between p-5">
          <div>
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tracking-tight">Parametric Controls</span>
                <span className="chip chip-accent font-mono text-[9px]">7-AXIS MATRIX</span>
              </div>
              <span className="text-[10px] text-text-subtle font-mono">
                DETERMINISTIC EVALUATION
              </span>
            </div>

            <div className="divider my-3.5" />

            {/* Categorized Engineering Navigation Tabs */}
            <div className="grid grid-cols-5 rounded-lg border border-border-subtle bg-bg p-1 text-center text-xs">
              <button
                type="button"
                onClick={() => setActiveCategory('environment')}
                className={`rounded-md py-1.5 text-[11px] font-medium transition ${
                  activeCategory === 'environment'
                    ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                1. Env
              </button>
              <button
                type="button"
                onClick={() => setActiveCategory('complexity')}
                className={`rounded-md py-1.5 text-[11px] font-medium transition ${
                  activeCategory === 'complexity'
                    ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                2. Scene
              </button>
              <button
                type="button"
                onClick={() => setActiveCategory('actor')}
                className={`rounded-md py-1.5 text-[11px] font-medium transition ${
                  activeCategory === 'actor'
                    ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                3. Actor
              </button>
              <button
                type="button"
                onClick={() => setActiveCategory('dynamics')}
                className={`rounded-md py-1.5 text-[11px] font-medium transition ${
                  activeCategory === 'dynamics'
                    ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                4. Dynamics
              </button>
              <button
                type="button"
                onClick={() => setActiveCategory('presets')}
                className={`rounded-md py-1.5 text-[11px] font-medium transition ${
                  activeCategory === 'presets'
                    ? 'bg-surface text-accent shadow-sm border border-border-subtle'
                    : 'text-text-muted hover:text-text'
                }`}
              >
                Presets
              </button>
            </div>

            {/* TAB CONTENTS */}
            <div className="mt-4 space-y-4 text-xs">
              
              {/* TAB 1: ENVIRONMENT (WEATHER & LIGHTING) */}
              {activeCategory === 'environment' && (
                <div className="space-y-4">
                  {/* Weather Selection */}
                  <div>
                    <div className="flex items-center justify-between">
                      <label className="field-label">Weather Condition</label>
                      <span className="font-mono text-[11px] text-accent font-semibold">
                        {WEATHER_LABEL[scenario.weather]}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                      {WEATHER_CONDITIONS.map((w) => (
                        <button
                          key={w}
                          type="button"
                          onClick={() => updateField('weather', w)}
                          className={`rounded-md px-2.5 py-1.5 text-left text-[11px] font-medium border transition ${
                            scenario.weather === w
                              ? 'border-accent bg-accent/15 text-accent shadow-sm'
                              : 'border-border-subtle bg-bg text-text-muted hover:border-border hover:text-text'
                          }`}
                        >
                          {WEATHER_LABEL[w]}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Lighting Selection */}
                  <div>
                    <div className="flex items-center justify-between">
                      <label className="field-label">Lighting & Illumination</label>
                      <span className="font-mono text-[11px] text-accent font-semibold">
                        {LIGHTING_LABEL[scenario.lighting]}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-1.5">
                      {LIGHTING_CONDITIONS.map((l) => (
                        <button
                          key={l}
                          type="button"
                          onClick={() => updateField('lighting', l)}
                          className={`rounded-md px-2.5 py-1.5 text-left text-[11px] font-medium border transition ${
                            scenario.lighting === l
                              ? 'border-accent bg-accent/15 text-accent shadow-sm'
                              : 'border-border-subtle bg-bg text-text-muted hover:border-border hover:text-text'
                          }`}
                        >
                          {LIGHTING_LABEL[l]}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 2: SCENE COMPLEXITY (TRAFFIC DENSITY & OCCLUSION) */}
              {activeCategory === 'complexity' && (
                <div className="space-y-4">
                  {/* Traffic Density */}
                  <div>
                    <div className="flex items-center justify-between">
                      <label className="field-label">Ambient Traffic Density</label>
                      <span className="font-mono text-[11px] text-accent font-semibold">
                        {TRAFFIC_LABEL[scenario.trafficDensity]}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-5 gap-1.5">
                      {TRAFFIC_DENSITIES.map((t) => (
                        <button
                          key={t}
                          type="button"
                          onClick={() => updateField('trafficDensity', t)}
                          className={`rounded-md py-2 text-center text-[11px] font-medium border transition ${
                            scenario.trafficDensity === t
                              ? 'border-accent bg-accent/15 text-accent shadow-sm'
                              : 'border-border-subtle bg-bg text-text-muted hover:border-border hover:text-text'
                          }`}
                        >
                          {TRAFFIC_LABEL[t]}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Occlusion Level */}
                  <div>
                    <div className="flex items-center justify-between">
                      <label className="field-label">Target Occlusion Mask</label>
                      <span className="font-mono text-[11px] text-accent font-semibold">
                        {OCCLUSION_LABEL[scenario.occlusion]}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5">
                      {OCCLUSION_LEVELS.map((occ) => {
                        const maskPct =
                          occ === 'none' ? '0% Mask' :
                          occ === 'partial' ? '~35% Mask' :
                          occ === 'substantial' ? '~75% Mask' : '95% Mask'
                        return (
                          <button
                            key={occ}
                            type="button"
                            onClick={() => updateField('occlusion', occ)}
                            className={`rounded-md p-2 text-left text-[11px] font-medium border transition ${
                              scenario.occlusion === occ
                                ? 'border-accent bg-accent/15 text-accent shadow-sm'
                                : 'border-border-subtle bg-bg text-text-muted hover:border-border hover:text-text'
                            }`}
                          >
                            <div>{OCCLUSION_LABEL[occ]}</div>
                            <div className="text-[10px] text-text-subtle font-mono">{maskPct}</div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: TARGET ACTOR */}
              {activeCategory === 'actor' && (
                <div className="space-y-4">
                  <div>
                    <div className="flex items-center justify-between">
                      <label className="field-label">Target Road User (Actor Class)</label>
                      <span className="font-mono text-[11px] text-accent font-semibold">
                        {ROAD_USER_LABEL[scenario.roadUser]}
                      </span>
                    </div>
                    <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-1.5">
                      {ROAD_USER_CLASSES.map((ru) => (
                        <button
                          key={ru}
                          type="button"
                          onClick={() => updateField('roadUser', ru)}
                          className={`rounded-md p-2 text-left text-[11px] font-medium border transition ${
                            scenario.roadUser === ru
                              ? 'border-accent bg-accent/15 text-accent shadow-sm'
                              : 'border-border-subtle bg-bg text-text-muted hover:border-border hover:text-text'
                          }`}
                        >
                          <div className="truncate">{ROAD_USER_LABEL[ru]}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 4: DYNAMICS (DISTANCE & SPEED) */}
              {activeCategory === 'dynamics' && (
                <div className="space-y-4">
                  {/* Distance Slider */}
                  <div className="rounded-md border border-border-subtle bg-bg p-3">
                    <div className="flex items-center justify-between">
                      <label htmlFor="dist-slider-2" className="field-label">Target Actor Distance</label>
                      <span className="font-mono text-sm font-bold text-accent">
                        {scenario.distanceMeters ?? 35} m
                      </span>
                    </div>
                    <input
                      id="dist-slider-2"
                      type="range"
                      min="5"
                      max="100"
                      step="1"
                      value={scenario.distanceMeters ?? 35}
                      onChange={(e) => updateField('distanceMeters', Number(e.target.value))}
                      className="mt-2 w-full accent-accent cursor-pointer"
                    />
                    <div className="mt-1 flex items-center justify-between text-[10px] text-text-subtle font-mono">
                      <span>5m (Critical TTC)</span>
                      <span>35m (Urban)</span>
                      <span>65m (Highway)</span>
                      <span>100m</span>
                    </div>
                    <div className="mt-2.5 flex gap-1.5">
                      {[10, 25, 50, 80].map((d) => (
                        <button
                          key={d}
                          type="button"
                          onClick={() => updateField('distanceMeters', d)}
                          className={`flex-1 rounded py-1 text-[10px] font-mono border transition ${
                            scenario.distanceMeters === d
                              ? 'border-accent bg-accent/15 text-accent'
                              : 'border-border-subtle bg-surface text-text-muted hover:text-text'
                          }`}
                        >
                          {d}m
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Ego Speed Slider */}
                  <div className="rounded-md border border-border-subtle bg-bg p-3">
                    <div className="flex items-center justify-between">
                      <label htmlFor="speed-slider-2" className="field-label">Ego Vehicle Velocity</label>
                      <span className="font-mono text-sm font-bold text-accent">
                        {scenario.egoSpeedKmh ?? 50} km/h
                      </span>
                    </div>
                    <input
                      id="speed-slider-2"
                      type="range"
                      min="10"
                      max="130"
                      step="5"
                      value={scenario.egoSpeedKmh ?? 50}
                      onChange={(e) => updateField('egoSpeedKmh', Number(e.target.value))}
                      className="mt-2 w-full accent-accent cursor-pointer"
                    />
                    <div className="mt-1 flex items-center justify-between text-[10px] text-text-subtle font-mono">
                      <span>10 km/h</span>
                      <span>50 km/h (City)</span>
                      <span>80 km/h (Arterial)</span>
                      <span>130 km/h</span>
                    </div>
                    <div className="mt-2.5 flex gap-1.5">
                      {[30, 50, 80, 120].map((s) => (
                        <button
                          key={s}
                          type="button"
                          onClick={() => updateField('egoSpeedKmh', s)}
                          className={`flex-1 rounded py-1 text-[10px] font-mono border transition ${
                            scenario.egoSpeedKmh === s
                              ? 'border-accent bg-accent/15 text-accent'
                              : 'border-border-subtle bg-surface text-text-muted hover:text-text'
                          }`}
                        >
                          {s} km/h
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 5: BENCHMARK PRESETS */}
              {activeCategory === 'presets' && (
                <div className="space-y-2">
                  <div className="field-label">Industry Benchmark Edge Cases</div>
                  <div className="grid gap-2">
                    {SCENARIO_PRESETS.map((p) => (
                      <button
                        key={p.name}
                        type="button"
                        onClick={() => applyPreset(p)}
                        className="rounded-md border border-border-subtle bg-bg p-2.5 text-left transition hover:border-accent/60 hover:bg-surface-hover"
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-text">{p.name}</span>
                          <span className="chip text-[9px] px-1.5 py-0 font-mono text-accent bg-accent/10 border-accent/30">
                            {p.badge}
                          </span>
                        </div>
                        <p className="mt-1 text-[10px] text-text-muted leading-relaxed">{p.description}</p>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* LIVE SCENARIO SIGNATURE & CONFIGURATION COMPLETENESS */}
            <div className="mt-4 rounded-lg border border-border-subtle bg-bg p-3 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="field-label text-accent">Scenario Signature</span>
                <span className="font-mono text-[10px] text-text-subtle font-semibold">{scenarioId}</span>
              </div>
              <p className="font-mono text-[11px] text-text font-medium leading-relaxed bg-surface/50 p-2 rounded border border-border-subtle">
                {WEATHER_LABEL[scenario.weather]} + {LIGHTING_LABEL[scenario.lighting]} + {TRAFFIC_LABEL[scenario.trafficDensity]} Traffic + {ROAD_USER_LABEL[scenario.roadUser]} + {OCCLUSION_LABEL[scenario.occlusion]} Occl + {scenario.distanceMeters}m + {scenario.egoSpeedKmh}km/h
              </p>

              {/* Validation Readiness Indicator */}
              <div className="pt-1.5 border-t border-border-subtle flex items-center justify-between text-[10px]">
                <div className="flex items-center gap-1.5">
                  <span className="text-text-subtle">Configuration Completeness:</span>
                  <span className="text-accent font-mono font-bold">100% · 7/7 Dimensions Valid</span>
                </div>
                <div className="h-1.5 w-24 rounded-full bg-surface-active overflow-hidden border border-border-subtle">
                  <div className="h-full bg-accent w-full" />
                </div>
              </div>
            </div>
          </div>

          {/* EXECUTE ACTION BUTTON */}
          <div className="mt-5 pt-2">
            <button
              type="button"
              className="btn btn-primary w-full py-2.5 text-sm font-semibold shadow-md transition-all active:scale-[0.99]"
              disabled={isRunning}
              onClick={onRun}
            >
              {isRunning ? (
                <span className="flex items-center gap-2">
                  <svg className="h-4 w-4 animate-spin text-[#05120C]" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                  </svg>
                  {executionLabels[executionStep] || 'EXECUTING SIMULATION…'}
                </span>
              ) : (
                <span className="flex items-center justify-center gap-2 font-bold tracking-wide">
                  <span>▶</span> EXECUTE VALIDATION RUN
                </span>
              )}
            </button>
          </div>
        </div>

        {/* RIGHT COLUMN: SIMULATION PREVIEW & EXECUTION INTELLIGENCE RESULT */}
        <div className="flex flex-col gap-4">
          
          {/* HERO SIMULATION PREVIEW VIEWPORT */}
          <SimulationPreview
            scenario={scenario}
            lastRun={lastRun}
            isRunning={isRunning}
          />

          {/* RESULT REVEAL & "WHY THIS RESULT?" INTELLIGENCE PANEL */}
          <div className="panel p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tracking-tight">Validation Result & Diagnostic</span>
                {lastRun && (
                  <span className="chip chip-accent font-mono text-[9px]">{lastRun.runId}</span>
                )}
              </div>
              {lastRun && (
                <span className="font-mono text-[10px] text-text-subtle">
                  Latency: {lastRun.outcome.latencyMs ?? 55} ms · {lastRun.durationMs}ms sim
                </span>
              )}
            </div>

            <div className="divider my-3" />

            {isRunning ? (
              <div className="rounded-md border border-accent/30 bg-accent/5 p-5 text-center space-y-2">
                <div className="chip chip-accent mx-auto animate-pulse font-mono text-[10px]">
                  TEST IN PROGRESS · EVALUATING PERCEPTION PIPELINE
                </div>
                <div className="text-xs font-mono text-text-muted">
                  {executionLabels[executionStep] || 'Processing scenario parameters…'}
                </div>
                <div className="mx-auto h-1.5 w-48 rounded-full bg-surface-active overflow-hidden border border-border-subtle">
                  <div
                    className="h-full bg-accent transition-all duration-200"
                    style={{ width: `${(executionStep + 1) * 20}%` }}
                  />
                </div>
              </div>
            ) : lastRun ? (
              <div className="space-y-3 text-xs">
                {/* Result Reveal Banner */}
                <div className={`rounded-md border p-3 ${
                  isPassed
                    ? 'border-accent/40 bg-accent/10'
                    : 'border-danger/40 bg-danger/10'
                }`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${isPassed ? 'bg-accent' : 'bg-danger animate-pulse'}`} />
                      <span className="font-bold text-sm text-text">
                        {isPassed ? '✓ DETECTION VALIDATED' : '⚠ PERCEPTION FAILURE DETECTED'}
                      </span>
                    </div>
                    <span className={`chip ${isPassed ? 'chip-accent' : 'chip-danger'} font-mono text-[9px] font-bold`}>
                      {OUTCOME_LABEL[lastRun.outcome.kind] || lastRun.outcome.kind}
                    </span>
                  </div>
                  
                  <p className="mt-2 text-xs font-medium leading-relaxed text-text">
                    {lastRun.displayMessage}
                  </p>
                </div>

                {/* WHY THIS RESULT? Deterministic Stressors Diagnostic */}
                <div className="rounded-md border border-border-subtle bg-bg p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="field-label text-accent font-semibold">Diagnostic Stressor Breakdown</span>
                    <span className="text-[9px] font-mono text-text-subtle">Deterministic Root Stressors</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                    {stressors.map((st) => (
                      <div key={st.factor} className="rounded border border-border-subtle bg-surface p-2 text-center">
                        <div className="text-[9px] text-text-subtle uppercase truncate">{st.factor}</div>
                        <div className={`mt-0.5 font-bold font-mono text-xs ${
                          st.level === 'HIGH' ? 'text-danger' : st.level === 'MEDIUM' ? 'text-warning' : 'text-accent'
                        }`}>
                          {st.level}
                        </div>
                        <div className="text-[8.5px] text-text-subtle font-mono truncate mt-0.5">{st.note}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Direct Action Link to Failure Analysis */}
                {isFailed && (
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] text-text-subtle">
                      Recorded in Failure Register as active incident.
                    </span>
                    <button
                      type="button"
                      onClick={handleJumpToAnalysis}
                      className="btn btn-ghost h-7 px-2.5 text-[11px] text-accent font-semibold hover:bg-accent/10"
                    >
                      Inspect in Incident Console →
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="rounded-md border border-border-subtle bg-bg p-6 text-center text-xs text-text-subtle">
                Ready for validation. Click <span className="text-accent font-semibold">▶ EXECUTE VALIDATION RUN</span> to evaluate scenario perception response.
              </div>
            )}
          </div>

          {/* RECENT RUN HISTORY */}
          {recentRuns.length > 0 && (
            <div className="panel p-4">
              <div className="flex items-center justify-between">
                <div className="text-xs font-semibold tracking-tight text-text-muted">Recent Run History</div>
                <span className="chip text-[9px]">{recentRuns.length} runs</span>
              </div>
              <div className="mt-2.5 divide-y divide-border-subtle overflow-hidden rounded-md border border-border-subtle bg-bg">
                {recentRuns.slice(0, 3).map((r) => (
                  <div
                    key={r.runId}
                    className="flex items-center justify-between gap-3 px-3 py-2 text-xs hover:bg-surface-hover transition"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[10px] font-semibold text-accent">{r.runId}</span>
                        <span className="text-[10px] text-text-subtle">
                          {ROAD_USER_LABEL[r.scenarioConfig.roadUser]} · {r.scenarioConfig.distanceMeters}m
                        </span>
                      </div>
                      <div className="truncate text-[10px] text-text-muted mt-0.5">
                        {r.displayMessage}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => onScenarioChange?.(r.scenarioConfig)}
                      className="btn btn-ghost h-6 px-2 text-[10px]"
                      title="Load this scenario configuration"
                    >
                      Load
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </PageSection>
  )
}

export default ScenarioLab
