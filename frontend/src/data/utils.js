/**
 * Pure JavaScript utility helpers used across EdgeForge.
 * Kept free of JSX so they can be imported in any environment (Node, web, tests).
 */

/**
 * Short, URL-safe id generator with a readable prefix.
 *
 * @param {string} [prefix='id']
 * @returns {string}
 */
export function uid(prefix = 'id') {
  const hex = Math.random().toString(16).slice(2, 10)
  return `${prefix}_${hex}${Date.now().toString(36).slice(-3)}`
}

/**
 * @returns {string}
 */
export function nowISO() {
  return new Date().toISOString()
}

/**
 * One-line string signature of a scenario, suitable for tables, chips and URLs.
 *
 * @param {Partial<import('@/types').ScenarioConfig>} cfg
 * @param {number} [maxLen=60]
 * @returns {string}
 */
export function formatScenarioSignature(cfg, maxLen = 60) {
  if (!cfg) return ''
  const parts = [
    cfg.weather,
    cfg.lighting,
    cfg.trafficDensity,
    cfg.roadUser,
    cfg.occlusion,
    typeof cfg.distanceMeters === 'number' ? `${cfg.distanceMeters}m` : undefined,
    typeof cfg.egoSpeedKmh === 'number' ? `${cfg.egoSpeedKmh}km/h` : undefined,
  ].filter(Boolean)
  const s = parts.join(' · ')
  if (s.length <= maxLen) return s
  return s.slice(0, Math.max(0, maxLen - 1)) + '…'
}

/**
 * @param {import('@/types').FailureRecord} f
 * @returns {string}
 */
export function summarizeFailure(f) {
  if (!f) return ''
  return `${f.failureType} on ${f.objectClass} (${f.severity})`
}

/**
 * @param {import('@/types').DemoRunResult} r
 * @returns {string}
 */
export function summarizeRun(r) {
  if (!r) return ''
  return r.displayMessage || `Run ${r.runId}`
}

import {
  WEATHER_CONDITIONS,
  LIGHTING_CONDITIONS,
  TRAFFIC_DENSITIES,
  ROAD_USER_CLASSES,
  OCCLUSION_LEVELS,
} from '../types.js'
import {
  WEATHER_LABEL,
  LIGHTING_LABEL,
  TRAFFIC_LABEL,
  ROAD_USER_LABEL,
  OCCLUSION_LABEL,
  DEFAULT_SCENARIO,
} from './labels.js'

/**
 * Computes a deterministic 2D scenario-space coverage matrix from actual demo runs and failures.
 *
 * @param {import('@/types').DemoRunResult[]} [runs]
 * @param {import('@/types').FailureRecord[]} [failures]
 * @param {'weather_occlusion'|'weather_lighting'|'traffic_roadUser'} [viewMode]
 */
export function computeCoverageMatrix(runs = [], failures = [], viewMode = 'weather_occlusion') {
  let dimY = 'weather'
  let dimX = 'occlusion'
  let yKeys = WEATHER_CONDITIONS
  let xKeys = OCCLUSION_LEVELS
  let yLabels = WEATHER_LABEL
  let xLabels = OCCLUSION_LABEL
  let yAxisTitle = 'Weather Condition'
  let xAxisTitle = 'Occlusion Level'

  if (viewMode === 'weather_lighting') {
    dimY = 'weather'
    dimX = 'lighting'
    yKeys = WEATHER_CONDITIONS
    xKeys = LIGHTING_CONDITIONS
    yLabels = WEATHER_LABEL
    xLabels = LIGHTING_LABEL
    yAxisTitle = 'Weather Condition'
    xAxisTitle = 'Lighting / Sun Angle'
  } else if (viewMode === 'traffic_roadUser') {
    dimY = 'trafficDensity'
    dimX = 'roadUser'
    yKeys = TRAFFIC_DENSITIES
    xKeys = ROAD_USER_CLASSES
    yLabels = TRAFFIC_LABEL
    xLabels = ROAD_USER_LABEL
    yAxisTitle = 'Traffic Density'
    xAxisTitle = 'Target Road User'
  }

  const cells = []
  const cellMap = new Map()

  let testedCount = 0
  let underTestedCount = 0
  let failureProneCount = 0
  let untestedCount = 0

  for (const yKey of yKeys) {
    for (const xKey of xKeys) {
      const cellKey = `${yKey}__${xKey}`
      const matchingRuns = runs.filter((r) => r.scenarioConfig?.[dimY] === yKey && r.scenarioConfig?.[dimX] === xKey)
      const matchingFailures = failures.filter((f) => f.scenarioConfig?.[dimY] === yKey && f.scenarioConfig?.[dimX] === xKey)

      const runCount = matchingRuns.length
      const failureCount = matchingFailures.length
      const failureRate = runCount > 0 ? failureCount / runCount : 0

      /** @type {import('@/types').CoverageStatus} */
      let status = 'untested'
      if (runCount === 0) {
        status = 'untested'
        untestedCount++
      } else if (failureCount >= 2 || (runCount >= 2 && failureRate >= 0.25)) {
        status = 'failure_prone'
        failureProneCount++
      } else if (runCount < 2) {
        status = 'under_tested'
        underTestedCount++
      } else {
        status = 'tested'
        testedCount++
      }

      // Find common road users & failure types
      const roadUserCounts = {}
      for (const r of matchingRuns) {
        const u = r.scenarioConfig?.roadUser
        if (u) roadUserCounts[u] = (roadUserCounts[u] || 0) + 1
      }
      const sortedUsers = Object.keys(roadUserCounts).sort((a, b) => roadUserCounts[b] - roadUserCounts[a])
      const commonRoadUser = sortedUsers[0] ? (ROAD_USER_LABEL[sortedUsers[0]] || sortedUsers[0]) : 'None'

      // Pick representative scenario
      const repScenario = matchingRuns[0]?.scenarioConfig || matchingFailures[0]?.scenarioConfig || {
        ...DEFAULT_SCENARIO,
        [dimY]: yKey,
        [dimX]: xKey,
      }

      const cellObj = {
        cellKey,
        yKey,
        xKey,
        yLabel: yLabels[yKey] || yKey,
        xLabel: xLabels[xKey] || xKey,
        runCount,
        failureCount,
        failureRate,
        failureRatePct: Math.round(failureRate * 100),
        status,
        matchingRuns,
        matchingFailures,
        commonRoadUser,
        representativeScenario: repScenario,
      }

      cells.push(cellObj)
      cellMap.set(cellKey, cellObj)
    }
  }

  const totalSlices = cells.length
  const totalRuns = runs.length
  const totalFailures = failures.length
  const overallFailureRate = totalRuns > 0 ? Math.round((totalFailures / totalRuns) * 100) : 0

  const hotZones = [...cells]
    .filter((c) => c.failureCount > 0)
    .sort((a, b) => b.failureCount - a.failureCount || b.failureRate - a.failureRate || b.runCount - a.runCount)
    .slice(0, 4)

  const coverageGaps = [...cells]
    .filter((c) => c.status === 'untested' || c.status === 'under_tested')
    .slice(0, 4)

  return {
    viewMode,
    dimX,
    dimY,
    xKeys,
    yKeys,
    xLabels,
    yLabels,
    xAxisTitle,
    yAxisTitle,
    cells,
    cellMap,
    hotZones,
    coverageGaps,
    summary: {
      totalSlices,
      testedCount,
      underTestedCount,
      failureProneCount,
      untestedCount,
      totalRuns,
      totalFailures,
      overallFailureRate,
    },
  }
}


