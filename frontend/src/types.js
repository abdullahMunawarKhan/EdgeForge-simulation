/**
 * @typedef {'clear'|'rain'|'heavy_rain'|'fog'|'snow'|'night_clear'|'night_rain'} WeatherCondition
 * @typedef {'day_direct'|'day_overcast'|'dawn_dusk'|'night_streetlight'|'night_unlit'|'tunnel_entry'|'tunnel_exit'} LightingCondition
 * @typedef {'empty'|'light'|'moderate'|'heavy'|'gridlock'} TrafficDensity
 * @typedef {'passenger_vehicle'|'heavy_truck'|'motorcycle'|'bicycle'|'pedestrian'|'animal'|'emergency_vehicle'|'construction_vehicle'} RoadUserClass
 * @typedef {'none'|'partial'|'substantial'|'fully_occluded'} OcclusionLevel
 *
 * @typedef {Object} ScenarioConfig
 * @property {string} [id]
 * @property {WeatherCondition} weather
 * @property {LightingCondition} lighting
 * @property {TrafficDensity} trafficDensity
 * @property {RoadUserClass} roadUser
 * @property {OcclusionLevel} occlusion
 * @property {number} distanceMeters
 * @property {number} egoSpeedKmh
 * @property {string[]} [tags]
 *
 * @typedef {'detected_ok'|'false_negative'|'false_positive'|'latency_breach'|'classification_error'|'range_error'} OutcomeKind
 * @typedef {'low'|'medium'|'high'|'critical'} SeverityLabel
 *
 * @typedef {Object} IllustrativeOutcome
 * @property {OutcomeKind} kind
 * @property {number} confidence
 * @property {RoadUserClass} [detectedClass]
 * @property {RoadUserClass} [trueClass]
 * @property {number} [distanceEstimateMeters]
 * @property {number} [trueDistanceMeters]
 * @property {number} [latencyMs]
 *
 * @typedef {Object} DemoRunResult
 * @property {string} runId
 * @property {ScenarioConfig} scenarioConfig
 * @property {IllustrativeOutcome} outcome
 * @property {string} displayMessage
 * @property {string} startedAt
 * @property {number} durationMs
 *
 * @typedef {'missed_object'|'wrong_class'|'distance_underestimate'|'distance_overestimate'|'late_detection'|'ghost_detection'} FailureCategory
 * @typedef {'not_attempted'|'queued'|'running'|'reproduced'|'resolved'} ReplayStatus
 *
 * @typedef {Object} FailureRecord
 * @property {string} id
 * @property {ScenarioConfig} scenarioConfig
 * @property {RoadUserClass} objectClass
 * @property {FailureCategory} failureType
 * @property {SeverityLabel} severity
 * @property {ReplayStatus} replayStatus
 * @property {string} [runId]
 * @property {string} firstSeenAt
 * @property {number} occurrenceCount
 *
 * @typedef {'tested'|'under_tested'|'failure_prone'|'untested'} CoverageStatus
 *
 * @typedef {Object} CoverageItem
 * @property {string} dimension
 * @property {Partial<ScenarioConfig>} combination
 * @property {CoverageStatus} status
 * @property {number} runCount
 * @property {number} failureCount
 *
 * @typedef {Object} ReasonSignal
 * @property {string} label
 * @property {string} description
 * @property {number} weight
 *
 * @typedef {Object} NextTestRecommendation
 * @property {string} id
 * @property {ReasonSignal[]} reasonSignals
 * @property {ScenarioConfig} recommendedScenario
 * @property {number} estimatedRiskScore
 * @property {string} rationaleSummary
 *
 * Shared page-level demo state contract. All modules communicate through this
 * interface via props; do not import sibling internal state directly.
 *
 * @typedef {Object} PageDemoState
 * @property {ScenarioConfig} currentScenario
 * @property {DemoRunResult|null} lastRun
 * @property {string|null} selectedFailureId
 * @property {NextTestRecommendation[]} recommendations
 * @property {(cfg: Partial<ScenarioConfig>) => void} onScenarioChange
 * @property {() => void|Promise<void>} onRunScenario
 * @property {(failureId: string|null) => void} onSelectFailure
 * @property {(rec: NextTestRecommendation) => void} onApplyRecommendation
 */

/** @type {WeatherCondition[]} */
export const WEATHER_CONDITIONS = [
  'clear', 'rain', 'heavy_rain', 'fog', 'snow', 'night_clear', 'night_rain',
]

/** @type {LightingCondition[]} */
export const LIGHTING_CONDITIONS = [
  'day_direct', 'day_overcast', 'dawn_dusk', 'night_streetlight', 'night_unlit', 'tunnel_entry', 'tunnel_exit',
]

/** @type {TrafficDensity[]} */
export const TRAFFIC_DENSITIES = ['empty', 'light', 'moderate', 'heavy', 'gridlock']

/** @type {RoadUserClass[]} */
export const ROAD_USER_CLASSES = [
  'passenger_vehicle', 'heavy_truck', 'motorcycle', 'bicycle',
  'pedestrian', 'animal', 'emergency_vehicle', 'construction_vehicle',
]

/** @type {OcclusionLevel[]} */
export const OCCLUSION_LEVELS = ['none', 'partial', 'substantial', 'fully_occluded']

/** @type {SeverityLabel[]} */
export const SEVERITY_LABELS = ['low', 'medium', 'high', 'critical']

/** @type {CoverageStatus[]} */
export const COVERAGE_STATUSES = ['tested', 'under_tested', 'failure_prone', 'untested']
