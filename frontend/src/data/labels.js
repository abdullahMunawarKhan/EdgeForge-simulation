/**
 * Default scenario seed used to initialize the Scenario Lab and recommendations.
 * @type {import('@/types').ScenarioConfig}
 */
export const DEFAULT_SCENARIO = {
  weather: 'clear',
  lighting: 'day_direct',
  trafficDensity: 'moderate',
  roadUser: 'pedestrian',
  occlusion: 'none',
  distanceMeters: 35,
  egoSpeedKmh: 50,
  tags: [],
}

/** @type {Record<string, string>} */
export const WEATHER_LABEL = {
  clear: 'Clear',
  rain: 'Rain',
  heavy_rain: 'Heavy Rain',
  fog: 'Fog',
  snow: 'Snow',
  night_clear: 'Night / Clear',
  night_rain: 'Night / Rain',
}

/** @type {Record<string, string>} */
export const LIGHTING_LABEL = {
  day_direct: 'Day — Direct Sun',
  day_overcast: 'Day — Overcast',
  dawn_dusk: 'Dawn / Dusk',
  night_streetlight: 'Night — Lit',
  night_unlit: 'Night — Unlit',
  tunnel_entry: 'Tunnel Entry',
  tunnel_exit: 'Tunnel Exit',
}

/** @type {Record<string, string>} */
export const TRAFFIC_LABEL = {
  empty: 'Empty',
  light: 'Light',
  moderate: 'Moderate',
  heavy: 'Heavy',
  gridlock: 'Gridlock',
}

/** @type {Record<string, string>} */
export const ROAD_USER_LABEL = {
  passenger_vehicle: 'Passenger Vehicle',
  heavy_truck: 'Heavy Truck',
  motorcycle: 'Motorcycle',
  bicycle: 'Bicycle',
  pedestrian: 'Pedestrian',
  animal: 'Animal',
  emergency_vehicle: 'Emergency Vehicle',
  construction_vehicle: 'Construction Vehicle',
}

/** @type {Record<string, string>} */
export const OCCLUSION_LABEL = {
  none: 'None',
  partial: 'Partial',
  substantial: 'Substantial',
  fully_occluded: 'Fully Occluded',
}

/** @type {Record<string, string>} */
export const OUTCOME_LABEL = {
  detected_ok: 'Detected OK',
  false_negative: 'Missed — False Negative',
  false_positive: 'Ghost — False Positive',
  latency_breach: 'Latency Breach',
  classification_error: 'Classification Error',
  range_error: 'Range Estimate Error',
}

/** @type {Record<string, string>} */
export const SEVERITY_LABEL = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
}

/** @type {Record<string, string>} */
export const FAILURE_LABEL = {
  missed_object: 'Missed Object',
  wrong_class: 'Wrong Classification',
  distance_underestimate: 'Distance Underestimated',
  distance_overestimate: 'Distance Overestimated',
  late_detection: 'Late Detection',
  ghost_detection: 'Ghost Detection',
}

/** @type {Record<string, string>} */
export const REPLAY_LABEL = {
  not_attempted: 'Not Attempted',
  queued: 'Queued',
  running: 'Replaying',
  reproduced: 'Reproduced',
  resolved: 'Resolved',
}

/** @type {Record<string, string>} */
export const COVERAGE_LABEL = {
  tested: 'Tested',
  under_tested: 'Under-Tested',
  failure_prone: 'Failure-Prone',
  untested: 'Untested',
}

/**
 * Converts a ScenarioConfig into a concise, natural human-readable description.
 * Example: "Night — Unlit fog scenario with a pedestrian at 18m, heavy traffic, substantial occlusion, and ego speed of 55 km/h."
 *
 * @param {import('@/types').ScenarioConfig} cfg
 * @returns {string}
 */
export function describeScenario(cfg) {
  if (!cfg) return ''
  const w = WEATHER_LABEL[cfg.weather] || cfg.weather || 'Clear'
  const l = LIGHTING_LABEL[cfg.lighting] || cfg.lighting || 'Day'
  const t = (TRAFFIC_LABEL[cfg.trafficDensity] || cfg.trafficDensity || 'Moderate').toLowerCase()
  const u = (ROAD_USER_LABEL[cfg.roadUser] || cfg.roadUser || 'Pedestrian').toLowerCase()
  const o = (OCCLUSION_LABEL[cfg.occlusion] || cfg.occlusion || 'None').toLowerCase()
  const d = cfg.distanceMeters ?? 35
  const s = cfg.egoSpeedKmh ?? 50

  const occlusionText = o === 'none' ? 'no occlusion' : `${o} occlusion`
  return `${l} ${w.toLowerCase()} scenario with a ${u} at ${d}m, ${t} traffic, ${occlusionText}, and ego speed of ${s} km/h.`
}

/**
 * Computes a deterministic scenario identifier from its parameters (e.g. SCN-4F2A).
 *
 * @param {import('@/types').ScenarioConfig} cfg
 * @returns {string}
 */
export function getScenarioId(cfg) {
  if (cfg?.id && cfg.id.startsWith('SCN-')) return cfg.id
  const key = `${cfg.weather}_${cfg.lighting}_${cfg.trafficDensity}_${cfg.roadUser}_${cfg.occlusion}_${cfg.distanceMeters}_${cfg.egoSpeedKmh}`
  let hash = 0
  for (let i = 0; i < key.length; i++) {
    hash = ((hash << 5) - hash) + key.charCodeAt(i)
    hash |= 0
  }
  const hex = Math.abs(hash).toString(16).toUpperCase().padStart(4, '0').slice(-4)
  return `SCN-${hex}`
}

/**
 * 4 High-Level User-Facing Phase 4 Failure Categories
 * @type {Record<string, { id: string, label: string, shortDesc: string, badgeClass: string, color: string }>}
 */
export const PHASE4_FAILURE_CATEGORIES = {
  missed_detection: {
    id: 'missed_detection',
    label: 'Missed Detection',
    shortDesc: 'Ground-truth actor omitted by perception model',
    badgeClass: 'chip-danger',
    color: '#F87171',
  },
  false_positive: {
    id: 'false_positive',
    label: 'False Positive',
    shortDesc: 'Ghost detection flagged where no ground-truth actor existed',
    badgeClass: 'chip-warning',
    color: '#FB923C',
  },
  poor_localization: {
    id: 'poor_localization',
    label: 'Poor Localization',
    shortDesc: 'Spatial bounding box or range estimate exceeded error tolerance',
    badgeClass: 'chip-warning',
    color: '#FBBF24',
  },
  confidence_degradation: {
    id: 'confidence_degradation',
    label: 'Confidence Degradation',
    shortDesc: 'Classification confusion or inference latency breached safety budget',
    badgeClass: 'chip-accent',
    color: '#38BDF8',
  },
}

/**
 * Maps internal outcome kinds / failure categories to Phase 4 analysis categories.
 * @param {string} [kindOrType]
 * @returns {'missed_detection'|'false_positive'|'poor_localization'|'confidence_degradation'}
 */
export function mapToPhase4Category(kindOrType) {
  switch (kindOrType) {
    case 'false_negative':
    case 'missed_object':
      return 'missed_detection'
    case 'false_positive':
    case 'ghost_detection':
      return 'false_positive'
    case 'range_error':
    case 'distance_underestimate':
    case 'distance_overestimate':
      return 'poor_localization'
    case 'latency_breach':
    case 'late_detection':
    case 'classification_error':
    case 'wrong_class':
    default:
      return 'confidence_degradation'
  }
}

/**
 * Deterministic engineering explanation generator for a FailureRecord.
 *
 * @param {import('@/types').FailureRecord} f
 * @returns {string}
 */
export function generateFailureExplanation(f) {
  if (!f || !f.scenarioConfig) return ''
  const actor = ROAD_USER_LABEL[f.objectClass] || f.objectClass || 'Actor'
  const weather = WEATHER_LABEL[f.scenarioConfig.weather] || f.scenarioConfig.weather || 'Clear'
  const lighting = LIGHTING_LABEL[f.scenarioConfig.lighting] || f.scenarioConfig.lighting || 'Day'
  const occlusion = OCCLUSION_LABEL[f.scenarioConfig.occlusion] || f.scenarioConfig.occlusion || 'None'
  const dist = f.scenarioConfig.distanceMeters ?? 35
  const cat = mapToPhase4Category(f.failureType)

  if (cat === 'missed_detection') {
    return `${actor} omitted from perception output at ${dist}m under ${weather} conditions with ${lighting} and ${occlusion.toLowerCase()} occlusion. Environmental attenuation and boundary masking suppressed detection activation.`
  }
  if (cat === 'false_positive') {
    return `Ghost detection flagged in ${weather} conditions with ${lighting}. Reflective surface artifacts or particulate noise triggered spurious object proposal.`
  }
  if (cat === 'poor_localization') {
    const isUnder = f.failureType === 'distance_underestimate'
    return `Range estimate error on ${actor} (${dist}m ground truth). ${weather} particulate scatter biased monocular depth estimation toward ${isUnder ? 'underestimation' : 'overestimation'}.`
  }
  // confidence_degradation / classification / latency
  if (f.failureType === 'wrong_class') {
    return `Classification confusion on ${actor} under ${lighting} illumination. High feature degradation and adverse contrast led to misclassification.`
  }
  return `Perception inference latency exceeded safety budget for ${actor} at ${dist}m with ego speed of ${f.scenarioConfig.egoSpeedKmh ?? 50} km/h. Pipeline throughput degraded under ${weather} conditions.`
}

/**
 * Computes deterministic primary stressor levels from a ScenarioConfig.
 *
 * @param {import('@/types').ScenarioConfig} cfg
 * @returns {{ factor: string, level: 'HIGH'|'MEDIUM'|'LOW'|'NOMINAL', note: string }[]}
 */
export function getScenarioStressors(cfg) {
  if (!cfg) return []
  const stressors = []

  // Occlusion
  if (cfg.occlusion === 'substantial' || cfg.occlusion === 'fully_occluded') {
    stressors.push({ factor: 'Occlusion', level: 'HIGH', note: '~75-95% Target Masking' })
  } else if (cfg.occlusion === 'partial') {
    stressors.push({ factor: 'Occlusion', level: 'MEDIUM', note: '~35% Boundary Masking' })
  } else {
    stressors.push({ factor: 'Occlusion', level: 'NOMINAL', note: 'Direct Line of Sight' })
  }

  // Weather Attenuation
  if (cfg.weather === 'fog' || cfg.weather === 'heavy_rain' || cfg.weather === 'night_rain' || cfg.weather === 'snow') {
    stressors.push({ factor: 'Atmospheric Attenuation', level: 'HIGH', note: 'Severe particulate/water scatter' })
  } else if (cfg.weather === 'rain') {
    stressors.push({ factor: 'Atmospheric Attenuation', level: 'MEDIUM', note: 'Moderate droplet scatter' })
  } else {
    stressors.push({ factor: 'Atmospheric Attenuation', level: 'NOMINAL', note: 'Clear optical path' })
  }

  // Illumination & Contrast
  if (cfg.lighting === 'night_unlit' || cfg.lighting === 'tunnel_entry' || cfg.lighting === 'tunnel_exit') {
    stressors.push({ factor: 'Illumination Contrast', level: 'HIGH', note: 'Extreme dynamic range / Low lux' })
  } else if (cfg.lighting === 'dawn_dusk' || cfg.lighting === 'night_streetlight') {
    stressors.push({ factor: 'Illumination Contrast', level: 'MEDIUM', note: 'Non-uniform ambient lighting' })
  } else {
    stressors.push({ factor: 'Illumination Contrast', level: 'NOMINAL', note: 'Balanced daylight illumination' })
  }

  // Range & TTC Stress
  const dist = cfg.distanceMeters ?? 35
  const speed = cfg.egoSpeedKmh ?? 50
  if (dist <= 18 || (speed >= 80 && dist <= 35)) {
    stressors.push({ factor: 'Spatial Safety Margin', level: 'HIGH', note: 'Compressed TTC (<1.5s)' })
  } else if (dist <= 35 || speed >= 70) {
    stressors.push({ factor: 'Spatial Safety Margin', level: 'MEDIUM', note: 'Moderate response window' })
  } else {
    stressors.push({ factor: 'Spatial Safety Margin', level: 'NOMINAL', note: 'Adequate braking distance' })
  }

  return stressors
}

/**
 * Structured engineering breakdown for Failure Analysis.
 *
 * @param {import('@/types').FailureRecord} f
 */
export function getStructuredFailureBreakdown(f) {
  if (!f) return null
  const cat = mapToPhase4Category(f.failureType)
  const actor = ROAD_USER_LABEL[f.objectClass] || f.objectClass || 'Actor'
  const w = WEATHER_LABEL[f.scenarioConfig?.weather] || 'Clear'
  const l = LIGHTING_LABEL[f.scenarioConfig?.lighting] || 'Day'
  const o = OCCLUSION_LABEL[f.scenarioConfig?.occlusion] || 'None'
  const dist = f.scenarioConfig?.distanceMeters ?? 35
  const speed = f.scenarioConfig?.egoSpeedKmh ?? 50

  const contributing = [
    `${w} atmospheric conditions`,
    `${l} illumination environment`,
    `${o} target actor occlusion`,
    `${dist}m range at ${speed} km/h ego speed`,
  ]

  let rootCause = 'Optical sensor SNR degradation'
  let observedEffect = 'Object proposal threshold unmet'
  let safetyImpact = 'Critical VRU safety envelope compromised'

  if (cat === 'missed_detection') {
    rootCause = 'Boundary feature masking & low contrast attenuation'
    observedEffect = 'Perception detector produced zero proposals for active road user'
    safetyImpact = 'Unmitigated collision hazard on active vehicle trajectory'
  } else if (cat === 'false_positive') {
    rootCause = 'Particulate backscatter & reflective noise artifact'
    observedEffect = 'Spurious bounding box proposal flagged with false confidence'
    safetyImpact = 'Phantom braking risk and unexpected deceleration hazard'
  } else if (cat === 'poor_localization') {
    rootCause = 'Atmospheric haze distorting monocular depth cues'
    observedEffect = 'Range estimate deviated significantly from synthetic ground truth'
    safetyImpact = 'TTC calculation distortion triggering inaccurate AEB timing'
  } else {
    rootCause = 'Visual ambiguity / pipeline feature extraction bottleneck'
    observedEffect = 'Classification confusion or inference latency exceeding 100ms safety budget'
    safetyImpact = 'Delayed emergency avoidance activation in dense traffic'
  }

  return {
    rootCause,
    contributing,
    observedEffect,
    safetyImpact,
  }
}



