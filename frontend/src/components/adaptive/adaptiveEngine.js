/**
 * Deterministic adaptive next-test engine. No random rankings.
 *
 * Every candidate score is a weighted composition of 3 signals (Phase 5 spec):
 *   1. Failure History              — recent/selected failures + their class
 *   2. Coverage Gaps                — under-tested / untested / failure-prone cells
 *   3. Project-Defined Risk Priorities — VRU class, close-range, occlusions, speed
 *
 * The "top" recommendation keeps the hardest-looking axis values from the anchor
 * scenario fixed and varies only 1 or 2 specific axes to probe the failure region.
 */

import { DEFAULT_SCENARIO } from '@/data/labels.js'
import { OCCLUSION_LEVELS, TRAFFIC_DENSITIES } from '@/types.js'

/**
 * @typedef {Object} SignalContribution
 * @property {string} label
 * @property {string} description
 * @property {number} weight
 *
 * @typedef {Object} Candidate
 * @property {import('@/types').ScenarioConfig} scenario
 * @property {number} score
 * @property {SignalContribution[]} signals
 * @property {string[]} heldConstant
 * @property {string} parameterChanged
 * @property {string} rationaleSummary
 */

const ROAD_USER_RISK = {
  pedestrian: 10,
  bicycle: 8.5,
  motorcycle: 8,
  animal: 6,
  emergency_vehicle: 5,
  passenger_vehicle: 3,
  heavy_truck: 4,
  construction_vehicle: 4.5,
}

const WEATHER_HARDNESS = {
  clear: 0, night_clear: 1.5, rain: 5, night_rain: 6.5, fog: 7, heavy_rain: 8, snow: 7.5,
}

const LIGHTING_HARDNESS = {
  day_direct: 0, day_overcast: 1, dawn_dusk: 5, night_streetlight: 4, night_unlit: 7,
  tunnel_entry: 5.5, tunnel_exit: 6,
}

const OCCLUSION_HARDNESS = { none: 0, partial: 4, substantial: 7.5, fully_occluded: 10 }
const TRAFFIC_HARDNESS = { empty: 0, light: 1.5, moderate: 4, heavy: 7, gridlock: 8.5 }

const FIELD_LABEL = {
  weather: 'Weather',
  lighting: 'Lighting',
  trafficDensity: 'Traffic Density',
  roadUser: 'Road-User Class',
  occlusion: 'Occlusion',
  distanceMeters: 'Distance',
  egoSpeedKmh: 'Ego Speed',
}

const FIELD_VALUE = {
  weather: (v) => v,
  lighting: (v) => v,
  trafficDensity: (v) => v,
  roadUser: (v) => v,
  occlusion: (v) => v,
  distanceMeters: (v) => `${v} m`,
  egoSpeedKmh: (v) => `${v} km/h`,
}

function roadUserRisk(cls) { return ROAD_USER_RISK[cls] ?? 4 }
const clamp01 = (x) => Math.max(0, Math.min(1, x))

/**
 * @param {object} input
 * @param {import('@/types').DemoRunResult|null} [input.latestResult]
 * @param {import('@/types').FailureRecord[]} [input.failureRecords]
 * @param {string|null} [input.selectedFailureId]
 * @param {Partial<import('@/types').ScenarioConfig>} [input.currentScenario]
 * @returns {{ scenario: import('@/types').ScenarioConfig, source: 'latest_run'|'selected_failure'|'top_failure'|'current', wasFailure: boolean, note: string, outcomeKind?: string }}
 */
export function pickAnchorScenario({
  latestResult = null,
  failureRecords = [],
  selectedFailureId = null,
  currentScenario = {},
}) {
  if (latestResult && latestResult.outcome && latestResult.outcome.kind !== 'detected_ok') {
    return {
      scenario: latestResult.scenarioConfig,
      source: 'latest_run',
      wasFailure: true,
      note: 'Latest run produced an illustrative perception failure.',
      outcomeKind: latestResult.outcome.kind,
    }
  }
  if (selectedFailureId) {
    const sel = failureRecords.find((f) => f.id === selectedFailureId)
    if (sel) {
      return {
        scenario: sel.scenarioConfig,
        source: 'selected_failure',
        wasFailure: true,
        note: 'Selected failure record in the register.',
        outcomeKind: sel.failureType === 'missed_object' ? 'false_negative' : 'classification_error',
      }
    }
  }
  const sevRank = { low: 0, medium: 1, high: 2, critical: 3 }
  const topFail = [...failureRecords].sort((a, b) => {
    return sevRank[b.severity] - sevRank[a.severity] || b.occurrenceCount - a.occurrenceCount
  })[0]
  if (topFail) {
    return {
      scenario: topFail.scenarioConfig,
      source: 'top_failure',
      wasFailure: true,
      note: 'Top-severity failure in the log.',
      outcomeKind: topFail.failureType === 'missed_object' ? 'false_negative' : 'classification_error',
    }
  }
  if (latestResult) {
    return {
      scenario: latestResult.scenarioConfig,
      source: 'latest_run',
      wasFailure: false,
      note: 'Latest run was clean; exploring the neighbourhood.',
      outcomeKind: latestResult.outcome.kind,
    }
  }
  /** @type {import('@/types').ScenarioConfig} */
  const scn = { ...DEFAULT_SCENARIO, ...currentScenario }
  return {
    scenario: scn,
    source: 'current',
    wasFailure: false,
    note: 'Current scenario in the Scenario Lab.',
  }
}

/**
 * Signal 1 — Failure History.
 * @param {{ anchor: Partial<import('@/types').ScenarioConfig>, anchorWasFailure: boolean, failures: import('@/types').FailureRecord[] }} p
 * @returns {{ score: number, signals: SignalContribution[] }}
 */
function scoreFailureHistory({ anchor, anchorWasFailure, failures }) {
  /** @type {SignalContribution[]} */
  const signals = []
  if (anchorWasFailure) {
    signals.push({
      label: 'Recent failure anchor',
      description: 'Anchor scenario itself ended in an illustrative perception failure.',
      weight: 4.2,
    })
  }
  const sameClass = failures.filter((f) => f.objectClass === anchor.roadUser)
  if (sameClass.length) {
    const occ = Math.min(6, sameClass.reduce((s, f) => s + f.occurrenceCount, 0))
    signals.push({
      label: 'Same-class failures',
      description: `${sameClass.length} record(s) share the anchor road-user class.`,
      weight: 1.8 + occ * 0.25,
    })
  }
  const sameEnv = failures.filter((f) =>
    f.scenarioConfig.weather === anchor.weather || f.scenarioConfig.lighting === anchor.lighting
  ).length
  if (sameEnv) {
    signals.push({
      label: 'Same-region environment',
      description: `${sameEnv} record(s) share anchor weather or lighting.`,
      weight: 1.1 + sameEnv * 0.15,
    })
  }
  return { score: signals.reduce((a, s) => a + s.weight, 0), signals }
}

/**
 * Signal 2 — Coverage Gaps.
 * @param {{ anchor: Partial<import('@/types').ScenarioConfig>, coverage: import('@/types').CoverageItem[] }} p
 * @returns {{ score: number, signals: SignalContribution[] }}
 */
function scoreCoverageGaps({ anchor, coverage }) {
  /** @type {SignalContribution[]} */
  const signals = []
  const cell = coverage.find((c) =>
    c.combination.weather === anchor.weather && c.combination.lighting === anchor.lighting
  )
  if (!cell) {
    signals.push({
      label: 'Unobserved coverage cell',
      description: 'No runs yet for this weather × lighting combination.',
      weight: 3.8,
    })
    return { score: 3.8, signals }
  }
  if (cell.status === 'failure_prone') {
    signals.push({
      label: 'Failure-prone cell',
      description: `${cell.failureCount} failures in ${cell.runCount} runs in this cell.`,
      weight: 3.6,
    })
  } else if (cell.status === 'under_tested') {
    signals.push({
      label: 'Under-tested cell',
      description: `Only ${cell.runCount} run(s) in this coverage cell.`,
      weight: 2.6,
    })
  } else if (cell.status === 'untested') {
    signals.push({
      label: 'Untested cell',
      description: 'Anchor combination has zero runs.',
      weight: 3.2,
    })
  } else {
    signals.push({
      label: 'Tested anchor cell',
      description: 'Stable, but surrounding cells are still worth probing.',
      weight: 0.8,
    })
  }
  const neighbours = coverage.filter((c) =>
    (c.combination.weather === anchor.weather || c.combination.lighting === anchor.lighting) && c !== cell
  )
  const weak = neighbours.filter((c) =>
    c.status === 'under_tested' || c.status === 'untested' || c.status === 'failure_prone'
  ).length
  if (weak) {
    signals.push({
      label: 'Surrounding coverage gaps',
      description: `${weak} near-axis neighbours are weak in this coverage neighbourhood.`,
      weight: 0.9 + weak * 0.2,
    })
  }
  return { score: signals.reduce((a, s) => a + s.weight, 0), signals }
}

/**
 * Signal 3 — Project-Defined Risk Priorities. Illustrative project-only weights;
 * not an industry-standard metric.
 *
 * @param {Partial<import('@/types').ScenarioConfig>} anchor
 * @returns {{ score: number, signals: SignalContribution[] }}
 */
function scoreRiskPriorities(anchor) {
  /** @type {SignalContribution[]} */
  const signals = []
  const cls = anchor.roadUser ?? 'pedestrian'
  const clsRisk = roadUserRisk(cls)
  if (clsRisk >= 8) {
    signals.push({
      label: 'Vulnerable road-user',
      description: `${cls} carries high project priority.`,
      weight: Number((clsRisk * 0.35).toFixed(2)),
    })
  } else {
    signals.push({
      label: 'Road-user priority',
      description: `${cls} is in the weighted class set.`,
      weight: Number((clsRisk * 0.2).toFixed(2)),
    })
  }
  const dist = anchor.distanceMeters ?? 40
  if (dist < 30) {
    signals.push({
      label: 'Close range',
      description: '< 30 m — TTC-relevant distance band.',
      weight: Number((2.2 * clamp01((30 - dist) / 20)).toFixed(2)),
    })
  }
  const occ = anchor.occlusion ?? 'none'
  const occH = OCCLUSION_HARDNESS[occ] ?? 0
  if (occH >= 4) {
    signals.push({
      label: 'Occlusion risk',
      description: `${occ} occlusion increases miss likelihood.`,
      weight: Number((occH * 0.2).toFixed(2)),
    })
  }
  const speed = anchor.egoSpeedKmh ?? 50
  if (speed >= 60) {
    signals.push({
      label: 'Ego-speed priority',
      description: `${speed} km/h — shorter perception-time window.`,
      weight: Number((0.035 * (speed - 50)).toFixed(2)),
    })
  }
  return { score: signals.reduce((a, s) => a + s.weight, 0), signals }
}

const bumpStep = (arr, val, step = 1) => {
  const i = arr.indexOf(val)
  return arr[Math.min(arr.length - 1, i + step)]
}

const harderWeather = (w) => {
  const order = ['clear', 'night_clear', 'rain', 'night_rain', 'fog', 'heavy_rain', 'snow']
  const i = order.indexOf(w)
  if (i < 0) return 'rain'
  return order[Math.min(order.length - 1, i + 2)]
}

const harderLighting = (l) => {
  const order = ['day_direct', 'day_overcast', 'night_streetlight', 'dawn_dusk', 'tunnel_entry', 'tunnel_exit', 'night_unlit']
  const i = order.indexOf(l)
  if (i < 0) return 'night_unlit'
  return order[Math.min(order.length - 1, i + 2)]
}

/**
 * @param {import('@/types').ScenarioConfig} anchor
 * @param {boolean} wasFailure
 */
function buildCandidates(anchor, wasFailure) {
  /** @type {Array<{ scenario: import('@/types').ScenarioConfig, held: string[], changed: string, rationale: string }>} */
  const plans = []
  const baseEnv = ['weather', 'lighting']

  if (wasFailure) {
    plans.push({
      scenario: {
        ...anchor,
        distanceMeters: Math.max(5, Math.round(anchor.distanceMeters * 0.65)),
        occlusion: bumpStep(OCCLUSION_LEVELS, anchor.occlusion, 1),
      },
      held: [...baseEnv, 'roadUser', 'trafficDensity', 'egoSpeedKmh'],
      changed: 'distanceMeters, occlusion',
      rationale: 'Keep the failure-associated environment fixed; pull the road-user closer and raise occlusion to probe around the missed-detection region.',
    })
    plans.push({
      scenario: { ...anchor, occlusion: OCCLUSION_LEVELS[OCCLUSION_LEVELS.length - 1] },
      held: [...baseEnv, 'roadUser', 'distanceMeters', 'egoSpeedKmh', 'trafficDensity'],
      changed: 'occlusion',
      rationale: 'Maximize occlusion on the same road-user and environment to stress-test the miss pattern.',
    })
    plans.push({
      scenario: {
        ...anchor,
        distanceMeters: Math.max(8, Math.round(anchor.distanceMeters * 0.85)),
        trafficDensity: bumpStep(TRAFFIC_DENSITIES, anchor.trafficDensity, 1),
      },
      held: [...baseEnv, 'roadUser', 'occlusion', 'egoSpeedKmh'],
      changed: 'distanceMeters, trafficDensity',
      rationale: 'Near-TTC range plus denser traffic compounds sensor load; recreates the anchor failure with more surrounding clutter.',
    })
    plans.push({
      scenario: {
        ...anchor,
        egoSpeedKmh: Math.min(110, Math.round(anchor.egoSpeedKmh * 1.25)),
        distanceMeters: Math.max(10, Math.round(anchor.distanceMeters * 0.9)),
      },
      held: [...baseEnv, 'roadUser', 'occlusion', 'trafficDensity'],
      changed: 'egoSpeedKmh, distanceMeters',
      rationale: 'Shorter TTC window at higher ego speed while keeping the anchor failure conditions.',
    })
  } else {
    plans.push({
      scenario: { ...anchor, weather: harderWeather(anchor.weather) },
      held: ['lighting', 'roadUser', 'occlusion', 'trafficDensity', 'egoSpeedKmh', 'distanceMeters'],
      changed: 'weather',
      rationale: 'Move to the adjacent harder-weather cell while keeping the road-user fixed.',
    })
    plans.push({
      scenario: { ...anchor, lighting: harderLighting(anchor.lighting) },
      held: ['weather', 'roadUser', 'occlusion', 'trafficDensity', 'egoSpeedKmh', 'distanceMeters'],
      changed: 'lighting',
      rationale: 'Harder lighting on the same scenario to probe the perceptual edge of the current setup.',
    })
    plans.push({
      scenario: { ...anchor, occlusion: 'substantial', distanceMeters: 25 },
      held: ['weather', 'lighting', 'roadUser', 'trafficDensity', 'egoSpeedKmh'],
      changed: 'occlusion, distanceMeters',
      rationale: 'Substantial occlusion around a VRU at close range to test a classic under-tested pattern.',
    })
    plans.push({
      scenario: { ...anchor, egoSpeedKmh: 70, distanceMeters: 45 },
      held: ['weather', 'lighting', 'roadUser', 'occlusion', 'trafficDensity'],
      changed: 'egoSpeedKmh, distanceMeters',
      rationale: 'Probe the highway ego-speed regime on the same road-user class.',
    })
  }

  /** @type {Candidate[]} */
  return plans.map((p) => ({
    scenario: p.scenario,
    score: 0,
    signals: [],
    heldConstant: p.held,
    parameterChanged: p.changed,
    rationaleSummary: p.rationale,
  }))
}

/**
 * Produces the full adaptive-model output. Deterministic for a given fixture.
 *
 * @param {object} input
 * @param {import('@/types').DemoRunResult|null} [input.latestResult]
 * @param {import('@/types').FailureRecord[]} [input.failureRecords]
 * @param {import('@/types').CoverageItem[]} [input.coverageItems]
 * @param {string|null} [input.selectedFailureId]
 * @param {Partial<import('@/types').ScenarioConfig>} [input.currentScenario]
 * @returns {{
 *   anchor: { scenario: import('@/types').ScenarioConfig, source: string, wasFailure: boolean, note: string, outcomeKind?: string },
 *   failureHistory: { score: number, signals: SignalContribution[] },
 *   coverageGaps: { score: number, signals: SignalContribution[] },
 *   riskPriorities: { score: number, signals: SignalContribution[] },
 *   prioritized: Candidate[],
 * }}
 */
export function buildAdaptiveRecommendations({
  latestResult = null,
  failureRecords = [],
  coverageItems = [],
  selectedFailureId = null,
  currentScenario = {},
}) {
  const anchor = pickAnchorScenario({ latestResult, failureRecords, selectedFailureId, currentScenario })
  const failureHistory = scoreFailureHistory({ anchor: anchor.scenario, anchorWasFailure: anchor.wasFailure, failures: failureRecords })
  const coverageGaps = scoreCoverageGaps({ anchor: anchor.scenario, coverage: coverageItems })
  const riskPriorities = scoreRiskPriorities(anchor.scenario)

  const candidates = buildCandidates(anchor.scenario, anchor.wasFailure)
  /** @type {Candidate[]} */
  const scored = candidates.map((c) => {
    const fh = scoreFailureHistory({ anchor: c.scenario, anchorWasFailure: anchor.wasFailure, failures: failureRecords })
    const cg = scoreCoverageGaps({ anchor: c.scenario, coverage: coverageItems })
    const rp = scoreRiskPriorities(c.scenario)
    // Weighted blend per spec-signal priority
    const weighted = fh.score * 0.4 + cg.score * 0.35 + rp.score * 0.25
    /** @type {SignalContribution[]} */
    const signals = [...fh.signals, ...cg.signals, ...rp.signals]
      .sort((a, b) => b.weight - a.weight)
      .map((s) => ({ ...s, weight: Number(s.weight.toFixed(2)) }))
    return {
      ...c,
      score: Number(weighted.toFixed(2)),
      signals,
    }
  })

  scored.sort((a, b) => b.score - a.score || (b.signals[0]?.weight ?? 0) - (a.signals[0]?.weight ?? 0))

  return { anchor, failureHistory, coverageGaps, riskPriorities, prioritized: scored }
}

/** Pretty field labels for the "held constant / changed" rows. */
export function prettyFieldLabel(key) { return FIELD_LABEL[key] ?? key }
export function prettyFieldValue(key, value) { return FIELD_VALUE[key] ? FIELD_VALUE[key](value) : value }

export { DEFAULT_SCENARIO as _ds }

/** Example fixture described in the Phase 5 prompt. Used as a stable fall-back. */
export const EXAMPLE_ANCHOR_SCENARIO = {
  weather: 'night_rain',
  lighting: 'night_unlit',
  trafficDensity: 'heavy',
  roadUser: 'pedestrian',
  occlusion: 'partial',
  distanceMeters: 32,
  egoSpeedKmh: 55,
}
