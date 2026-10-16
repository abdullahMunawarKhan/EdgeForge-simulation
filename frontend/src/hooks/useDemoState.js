import { useCallback, useMemo, useState } from 'react'
import { DEFAULT_SCENARIO, ROAD_USER_LABEL, getScenarioId } from '../data/labels.js'
import { uid, nowISO } from '../data/utils.js'


/**
 * Computes a deterministic numeric hash from the 7 scenario axes.
 * This guarantees the exact same scenario always produces the exact same seed.
 *
 * @param {import('@/types').ScenarioConfig} cfg
 * @returns {number}
 */
export function hashScenario(cfg) {
  if (!cfg) return 42
  const str = `${cfg.weather}|${cfg.lighting}|${cfg.trafficDensity}|${cfg.roadUser}|${cfg.occlusion}|${cfg.distanceMeters}|${cfg.egoSpeedKmh}`
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i)
    hash = ((hash << 5) - hash) + char
    hash |= 0
  }
  return Math.abs(hash)
}

/**
 * Deterministic illustrative outcome generator. The returned IllustrativeOutcome
 * evaluates scenario edge-case difficulty purely based on configuration axes and deterministic seed.
 *
 * @param {import('@/types').ScenarioConfig} cfg
 * @param {number} seed
 * @returns {import('@/types').IllustrativeOutcome}
 */
export function makeIllustrativeOutcome(cfg, seed = hashScenario(cfg)) {
  const rng = (n) => ((Math.sin(seed * 9301 + n * 49297) + 1) / 2)
  
  const hardWeather = cfg.weather === 'heavy_rain' || cfg.weather === 'fog' || cfg.weather === 'snow' || cfg.weather === 'night_rain'
  const badLight = cfg.lighting === 'night_unlit' || cfg.lighting === 'dawn_dusk' || cfg.lighting === 'tunnel_entry' || cfg.lighting === 'tunnel_exit'
  const close = (cfg.distanceMeters ?? 35) < 20
  const far = (cfg.distanceMeters ?? 35) > 60
  const occluded = cfg.occlusion === 'substantial' || cfg.occlusion === 'fully_occluded'
  const partialOccluded = cfg.occlusion === 'partial'
  const highSpeed = (cfg.egoSpeedKmh ?? 50) > 75
  const heavyTraffic = cfg.trafficDensity === 'heavy' || cfg.trafficDensity === 'gridlock'
  const vulnerableActor = cfg.roadUser === 'pedestrian' || cfg.roadUser === 'bicycle' || cfg.roadUser === 'motorcycle' || cfg.roadUser === 'animal'

  // Calculate environmental failure probability
  let pFail = 0.06
  if (hardWeather) pFail += 0.20
  if (badLight) pFail += 0.18
  if (far) pFail += 0.12
  if (highSpeed) pFail += 0.10
  if (heavyTraffic) pFail += 0.08
  if (occluded) pFail += 0.32
  else if (partialOccluded) pFail += 0.16
  if (vulnerableActor && (hardWeather || badLight)) pFail += 0.10
  if (close && !occluded && !hardWeather) pFail -= 0.06

  const clampedFailProb = Math.max(0.04, Math.min(0.94, pFail))
  const roll = rng(1)

  if (roll < clampedFailProb) {
    const failureRoll = rng(2)
    
    // False negative (Missed detection) - high in severe occlusion/weather/unlit night
    if (failureRoll < 0.40 || cfg.occlusion === 'fully_occluded') {
      return {
        kind: 'false_negative',
        confidence: Math.round((0.15 + rng(3) * 0.25) * 100) / 100,
        trueClass: cfg.roadUser,
        detectedClass: undefined,
        trueDistanceMeters: cfg.distanceMeters,
        distanceEstimateMeters: undefined,
        latencyMs: 90 + Math.round(rng(4) * 180),
      }
    }
    
    // Classification error - confusion between classes under adverse lighting/occlusion
    if (failureRoll < 0.65) {
      /** @type {import('@/types').RoadUserClass} */
      const altClass =
        cfg.roadUser === 'pedestrian' ? 'bicycle' :
        cfg.roadUser === 'bicycle' ? 'motorcycle' :
        cfg.roadUser === 'passenger_vehicle' ? 'heavy_truck' :
        cfg.roadUser === 'animal' ? 'pedestrian' : 'passenger_vehicle'
      return {
        kind: 'classification_error',
        confidence: Math.round((0.48 + rng(3) * 0.22) * 100) / 100,
        trueClass: cfg.roadUser,
        detectedClass: altClass,
        trueDistanceMeters: cfg.distanceMeters,
        distanceEstimateMeters: cfg.distanceMeters,
        latencyMs: 70 + Math.round(rng(4) * 120),
      }
    }
    
    // Range estimation error
    if (failureRoll < 0.85) {
      const under = rng(5) > 0.5
      const estDistance = under
        ? Math.max(2, Math.round(cfg.distanceMeters * (0.45 + rng(6) * 0.25)))
        : Math.round(cfg.distanceMeters * (1.35 + rng(6) * 0.55))
      return {
        kind: 'range_error',
        confidence: Math.round((0.65 + rng(3) * 0.20) * 100) / 100,
        trueClass: cfg.roadUser,
        detectedClass: cfg.roadUser,
        trueDistanceMeters: cfg.distanceMeters,
        distanceEstimateMeters: estDistance,
        latencyMs: 65 + Math.round(rng(4) * 100),
      }
    }
    
    // Latency breach (Perception pipeline overloaded or degraded)
    return {
      kind: 'latency_breach',
      confidence: Math.round((0.80 + rng(3) * 0.15) * 100) / 100,
      trueClass: cfg.roadUser,
      detectedClass: cfg.roadUser,
      trueDistanceMeters: cfg.distanceMeters,
      distanceEstimateMeters: cfg.distanceMeters,
      latencyMs: 310 + Math.round(rng(4) * 250),
    }
  }

  // Detected OK - Clean detection with slight realistic sensory variance
  const distVariance = (rng(7) - 0.5) * 1.5
  return {
    kind: 'detected_ok',
    confidence: Math.round((0.88 + rng(3) * 0.10) * 100) / 100,
    trueClass: cfg.roadUser,
    detectedClass: cfg.roadUser,
    trueDistanceMeters: cfg.distanceMeters,
    distanceEstimateMeters: Math.max(1, Math.round((cfg.distanceMeters + distVariance) * 10) / 10),
    latencyMs: 45 + Math.round(rng(4) * 45),
  }
}

/**
 * Human-readable short description of an illustrative outcome.
 *
 * @param {import('@/types').IllustrativeOutcome} o
 * @param {import('@/types').ScenarioConfig} cfg
 * @returns {string}
 */
export function describeOutcome(o, cfg) {
  const actorName = ROAD_USER_LABEL[cfg.roadUser] || cfg.roadUser || 'Object'
  switch (o.kind) {
    case 'detected_ok':
      return `${actorName} detected at ${o.distanceEstimateMeters ?? cfg.distanceMeters} m · Confidence ${Math.round(o.confidence * 100)}% · Latency ${o.latencyMs ?? 50} ms`
    case 'false_negative':
      return `MISSED ${actorName} at ${o.trueDistanceMeters ?? cfg.distanceMeters} m · Environmental degradation / occlusion induced miss`
    case 'false_positive':
      return `Ghost detection flagged · No ground-truth ${actorName} present`
    case 'classification_error': {
      const detectedName = ROAD_USER_LABEL[o.detectedClass] || o.detectedClass || 'Unknown'
      return `Classified ${actorName} incorrectly as ${detectedName} · Confidence ${Math.round(o.confidence * 100)}%`
    }
    case 'range_error': {
      const err = (o.distanceEstimateMeters ?? 0) - (o.trueDistanceMeters ?? cfg.distanceMeters)
      return `Range ${err < 0 ? 'under' : 'over'}-estimated by ${Math.abs(Math.round(err))} m on ${actorName} (True: ${cfg.distanceMeters} m, Est: ${o.distanceEstimateMeters} m)`
    }
    case 'latency_breach':
      return `Perception latency ${o.latencyMs ?? 300} ms exceeded safety budget for ${actorName} at ${cfg.distanceMeters} m`
    default:
      return ''
  }
}


/**
 * Severity heuristic driven by ego speed, VRU class, and failure kind.
 *
 * @param {import('@/types').IllustrativeOutcome} o
 * @param {import('@/types').ScenarioConfig} cfg
 * @returns {import('@/types').SeverityLabel}
 */
export function outcomeSeverity(o, cfg) {
  const speed = cfg.egoSpeedKmh
  const close = cfg.distanceMeters < 25
  const vuln = cfg.roadUser === 'pedestrian' || cfg.roadUser === 'bicycle' || cfg.roadUser === 'motorcycle'
  if (o.kind === 'false_negative' && (close || vuln)) return 'critical'
  if (o.kind === 'false_negative') return 'high'
  if (o.kind === 'latency_breach' && close) return 'critical'
  if (o.kind === 'latency_breach') return 'high'
  if (o.kind === 'classification_error' && vuln) return 'high'
  if (o.kind === 'classification_error') return 'medium'
  if (o.kind === 'range_error' && close) return 'high'
  if (o.kind === 'range_error') return 'medium'
  if (o.kind === 'false_positive' && speed > 60) return 'medium'
  return 'low'
}

/**
 * Maps outcome kind → failure category used by FailureRecord.
 *
 * @param {import('@/types').IllustrativeOutcome} o
 * @returns {import('@/types').FailureCategory}
 */
export function failureTypeFromOutcome(o) {
  switch (o.kind) {
    case 'detected_ok':
      return 'missed_object'
    case 'false_negative':
      return 'missed_object'
    case 'false_positive':
      return 'ghost_detection'
    case 'classification_error':
      return 'wrong_class'
    case 'range_error': {
      const est = o.distanceEstimateMeters ?? 0
      const tru = o.trueDistanceMeters ?? est
      return est < tru ? 'distance_underestimate' : 'distance_overestimate'
    }
    case 'latency_breach':
      return 'late_detection'
    default:
      return 'missed_object'
  }
}

/**
 * @typedef {Object} DemoDataset
 * @property {import('@/types').DemoRunResult[]} runs
 * @property {import('@/types').FailureRecord[]} failures
 * @property {import('@/types').CoverageItem[]} coverage
 * @property {import('@/types').NextTestRecommendation[]} recommendations
 */

/**
 * Builds a deterministic mock dataset so all sections render populated without
 * requiring the user to run scenarios first.
 *
 * @param {number} seedRuns
 * @returns {DemoDataset}
 */
export function buildDemoDataset(seedRuns = 60) {
  /** @type {import('@/types').WeatherCondition[]} */
  const weathers = ['clear', 'rain', 'heavy_rain', 'fog', 'night_clear', 'night_rain']
  /** @type {import('@/types').LightingCondition[]} */
  const lightings = ['day_direct', 'day_overcast', 'dawn_dusk', 'night_streetlight', 'night_unlit']
  /** @type {import('@/types').TrafficDensity[]} */
  const traffics = ['light', 'moderate', 'heavy']
  /** @type {import('@/types').RoadUserClass[]} */
  const roadUsers = ['passenger_vehicle', 'heavy_truck', 'motorcycle', 'bicycle', 'pedestrian']
  /** @type {import('@/types').OcclusionLevel[]} */
  const occlusions = ['none', 'partial', 'substantial']

  /** @type {import('@/types').DemoRunResult[]} */
  const runs = []
  /** @type {import('@/types').FailureRecord[]} */
  const failures = []
  /** @type {Map<string, { runCount: number, failureCount: number, combo: Partial<import('@/types').ScenarioConfig> }>} */
  const coverageBuckets = new Map()
  const bucketKey = (w, l) => `${w}__${l}`

  for (let i = 0; i < seedRuns; i++) {
    /** @type {import('@/types').ScenarioConfig} */
    const cfg = {
      id: uid('sc'),
      weather: weathers[i % weathers.length],
      lighting: lightings[(i * 3) % lightings.length],
      trafficDensity: traffics[(i * 5) % traffics.length],
      roadUser: roadUsers[(i * 7) % roadUsers.length],
      occlusion: occlusions[(i * 11) % occlusions.length],
      distanceMeters: 10 + ((i * 13) % 70),
      egoSpeedKmh: 20 + ((i * 17) % 80),
    }
    const outcome = makeIllustrativeOutcome(cfg, hashScenario(cfg))
    const runId = uid('run')
    /** @type {import('@/types').DemoRunResult} */
    const run = {
      runId,
      scenarioConfig: cfg,
      outcome,
      displayMessage: describeOutcome(outcome, cfg),
      startedAt: new Date(Date.now() - i * 60_000).toISOString(),
      durationMs: 180 + ((i * 41) % 520),
    }
    runs.push(run)

    const bkey = bucketKey(cfg.weather, cfg.lighting)
    const prior = coverageBuckets.get(bkey) ?? {
      runCount: 0, failureCount: 0,
      combo: { weather: cfg.weather, lighting: cfg.lighting },
    }
    prior.runCount += 1
    const isFail = outcome.kind !== 'detected_ok'
    if (isFail) prior.failureCount += 1
    coverageBuckets.set(bkey, prior)

    if (isFail) {
      /** @type {import('@/types').FailureRecord} */
      const rec = {
        id: uid('fail'),
        scenarioConfig: cfg,
        objectClass: cfg.roadUser,
        failureType: failureTypeFromOutcome(outcome),
        severity: outcomeSeverity(outcome, cfg),
        replayStatus: /** @type {import('@/types').ReplayStatus[]} */ (['not_attempted', 'queued', 'reproduced', 'resolved'])[i % 4],
        runId,
        firstSeenAt: run.startedAt,
        occurrenceCount: 1 + (i % 4),
        outcome,
      }
      failures.push(rec)
    }
  }

  /** @type {import('@/types').CoverageItem[]} */
  const coverage = [...coverageBuckets.values()].map((b) => {
    const failRate = b.failureCount / Math.max(1, b.runCount)
    /** @type {import('@/types').CoverageStatus} */
    let status = 'untested'
    if (b.runCount >= 3) status = failRate > 0.35 ? 'failure_prone' : failRate > 0.1 ? 'under_tested' : 'tested'
    else if (b.runCount > 0) status = 'under_tested'
    return {
      dimension: 'weather × lighting',
      combination: b.combo,
      status,
      runCount: b.runCount,
      failureCount: b.failureCount,
    }
  })

  const sevRank = (s) => ({ low: 0, medium: 1, high: 2, critical: 3 })[s]
  const topFail = [...failures].sort((a, b) => sevRank(b.severity) - sevRank(a.severity) || b.occurrenceCount - a.occurrenceCount)[0]
  const underTested = coverage.filter((c) => c.status === 'under_tested' || c.status === 'untested')[0]
  const failureProne = coverage.filter((c) => c.status === 'failure_prone')[0]

  /** @type {import('@/types').NextTestRecommendation[]} */
  const recommendations = [
    {
      id: uid('rec'),
      recommendedScenario: {
        ...DEFAULT_SCENARIO,
        weather: underTested?.combination.weather ?? 'heavy_rain',
        lighting: underTested?.combination.lighting ?? 'night_unlit',
        roadUser: 'pedestrian',
        occlusion: 'substantial',
        distanceMeters: 22,
        egoSpeedKmh: 55,
      },
      reasonSignals: [
        { label: 'Coverage gap', description: 'Under-tested weather/lighting cell', weight: 3.2 },
        { label: 'Vulnerable road-user', description: 'Pedestrian class carries high severity', weight: 2.6 },
        { label: 'Occlusion novelty', description: 'Substantial occlusion rarely sampled', weight: 1.8 },
        { label: 'Scenario distance', description: 'Near TTC-relevant distance band', weight: 1.4 },
      ],
      estimatedRiskScore: 8.7,
      rationaleSummary: 'Highest-signal combination: under-tested night/heavy-rain cell with an occluded pedestrian near TTC distance.',
    },
    {
      id: uid('rec'),
      recommendedScenario: {
        ...DEFAULT_SCENARIO,
        weather: failureProne?.combination.weather ?? 'fog',
        lighting: failureProne?.combination.lighting ?? 'tunnel_exit',
        roadUser: topFail?.objectClass ?? 'motorcycle',
        occlusion: 'partial',
        distanceMeters: 48,
        egoSpeedKmh: 70,
      },
      reasonSignals: [
        { label: 'Failure-prone cell', description: 'Historic failure rate above threshold', weight: 3.6 },
        { label: 'Recent failure', description: `${topFail?.failureType ?? 'missed_object'} recurrence`, weight: 2.9 },
        { label: 'High ego speed', description: 'TTC window compresses at 70 km/h', weight: 2.1 },
      ],
      estimatedRiskScore: 7.4,
      rationaleSummary: 'Targets the highest failure-rate bucket and reproduces the top-severity recent failure pattern at highway ego-speed.',
    },
    {
      id: uid('rec'),
      recommendedScenario: {
        ...DEFAULT_SCENARIO,
        weather: 'snow',
        lighting: 'dawn_dusk',
        roadUser: 'bicycle',
        occlusion: 'fully_occluded',
        distanceMeters: 18,
        egoSpeedKmh: 40,
      },
      reasonSignals: [
        { label: 'Low sample count', description: 'Snow + dawn rarely exercised', weight: 2.4 },
        { label: 'VRU + occlusion', description: 'Occluded cyclist at close range', weight: 2.8 },
        { label: 'Urban 40 km/h band', description: 'Urban scenario diversity', weight: 1.2 },
      ],
      estimatedRiskScore: 6.9,
      rationaleSummary: 'Low-sample corner case: occluded cyclist in snow/dawn conditions, targeted at urban speed band diversity.',
    },
  ]

  return { runs, failures, coverage, recommendations }
}

/**
 * Shared page demo-state hook. One source of truth. Module owners should read
 * only the props their component needs and must not mutate sibling state directly.
 *
 * @returns {import('@/types').PageDemoState & { dataset: DemoDataset, isRunning: boolean }}
 */
export function useDemoState() {
  const [dataset, setDataset] = useState(() => buildDemoDataset(56))
  const [currentScenario, setCurrentScenario] = useState({ ...DEFAULT_SCENARIO })
  const [lastRun, setLastRun] = useState(null)
  const [selectedFailureId, setSelectedFailureId] = useState(null)
  const [isRunning, setIsRunning] = useState(false)
  const [recommendations, setRecommendations] = useState(dataset.recommendations)

  const onScenarioChange = useCallback((cfg) => {
    setCurrentScenario((prev) => ({ ...prev, ...cfg }))
  }, [])

  const onRunScenario = useCallback(async () => {
    setIsRunning(true)
    await new Promise((r) => setTimeout(r, 600))
    const seed = hashScenario(currentScenario)
    const outcome = makeIllustrativeOutcome(currentScenario, seed)
    const runHex = (Math.abs(seed ^ 0xA5C3)).toString(16).toUpperCase().padStart(4, '0').slice(-4)
    const runId = `RUN-${runHex}`
    const scenarioId = getScenarioId(currentScenario)
    const scenarioWithId = { ...currentScenario, id: scenarioId }
    
    /** @type {import('@/types').DemoRunResult} */
    const result = {
      runId,
      scenarioConfig: scenarioWithId,
      outcome,
      displayMessage: describeOutcome(outcome, currentScenario),
      startedAt: nowISO(),
      durationMs: 220 + ((seed * 41) % 360),
    }
    setLastRun(result)
    if (outcome.kind !== 'detected_ok') {
      /** @type {import('@/types').FailureRecord} */
      const rec = {
        id: `FAIL-${runHex}`,
        scenarioConfig: scenarioWithId,
        objectClass: currentScenario.roadUser,
        failureType: failureTypeFromOutcome(outcome),
        severity: outcomeSeverity(outcome, currentScenario),
        replayStatus: 'not_attempted',
        runId,
        firstSeenAt: result.startedAt,
        occurrenceCount: 1,
        outcome,
      }
      setDataset((prev) => ({
        ...prev,
        runs: [result, ...prev.runs.filter((r) => r.runId !== runId)],
        failures: [rec, ...prev.failures.filter((f) => f.id !== rec.id)],
      }))
    } else {
      setDataset((prev) => ({
        ...prev,
        runs: [result, ...prev.runs.filter((r) => r.runId !== runId)],
      }))
    }
    setIsRunning(false)
  }, [currentScenario])


  const onResetScenario = useCallback(() => {
    setCurrentScenario({ ...DEFAULT_SCENARIO })
    setLastRun(null)
  }, [])

  const onSelectFailure = useCallback((failureId) => {
    setSelectedFailureId(failureId)
  }, [])

  const onApplyRecommendation = useCallback((rec) => {
    setCurrentScenario({ ...rec.recommendedScenario })
    setRecommendations((prev) => prev.map((r) => ({ ...r, id: r.id })))
  }, [])

  return useMemo(() => ({
    currentScenario,
    lastRun,
    selectedFailureId,
    recommendations,
    dataset,
    isRunning,
    onScenarioChange,
    onRunScenario,
    onResetScenario,
    onSelectFailure,
    onApplyRecommendation,
  }), [
    currentScenario, lastRun, selectedFailureId, recommendations, dataset, isRunning,
    onScenarioChange, onRunScenario, onResetScenario, onSelectFailure, onApplyRecommendation,
  ])
}

