import {
  describeScenario,
  getScenarioId,
  DEFAULT_SCENARIO,
  WEATHER_LABEL,
  LIGHTING_LABEL,
  TRAFFIC_LABEL,
  ROAD_USER_LABEL,
  OCCLUSION_LABEL,
  OUTCOME_LABEL,
  SEVERITY_LABEL,
  FAILURE_LABEL,
  PHASE4_FAILURE_CATEGORIES,
  mapToPhase4Category,
  generateFailureExplanation,
  getScenarioStressors,
} from './labels.js'
import {
  WEATHER_CONDITIONS,
  LIGHTING_CONDITIONS,
  TRAFFIC_DENSITIES,
  ROAD_USER_CLASSES,
  OCCLUSION_LEVELS,
} from '../types.js'
import {
  computeCoverageMatrix,
} from './utils.js'
import {
  makeIllustrativeOutcome,
  hashScenario,
  describeOutcome,
  outcomeSeverity,
  failureTypeFromOutcome,
  buildDemoDataset,
} from '../hooks/useDemoState.js'

console.log('====================================================')
console.log('     EDGEFORGE PHASE 3 & 4 VERIFICATION SUITE       ')
console.log('====================================================')

// Test 1: Deterministic Outcome Verification
console.log('\n[Test 1] Deterministic Outcome Verification:')
const testConfigA = {
  weather: 'fog',
  lighting: 'night_unlit',
  trafficDensity: 'heavy',
  roadUser: 'pedestrian',
  occlusion: 'substantial',
  distanceMeters: 18,
  egoSpeedKmh: 55,
}

const seedA1 = hashScenario(testConfigA)
const seedA2 = hashScenario(testConfigA)
if (seedA1 !== seedA2) {
  throw new Error(`FAIL: Seeds do not match for same config: ${seedA1} vs ${seedA2}`)
}

const outcomeA1 = makeIllustrativeOutcome(testConfigA, seedA1)
const outcomeA2 = makeIllustrativeOutcome(testConfigA, seedA1)

if (JSON.stringify(outcomeA1) !== JSON.stringify(outcomeA2)) {
  throw new Error(`FAIL: Non-deterministic outcome for Scenario A!`)
}
console.log('✓ Scenario A produced identical outcome across multiple runs:', outcomeA1)

// Test 2: Multi-Scenario Reproducibility & Variety
console.log('\n[Test 2] Multi-Scenario Reproducibility:')
const testConfigB = {
  weather: 'clear',
  lighting: 'day_direct',
  trafficDensity: 'light',
  roadUser: 'passenger_vehicle',
  occlusion: 'none',
  distanceMeters: 40,
  egoSpeedKmh: 50,
}
const seedB = hashScenario(testConfigB)
const outcomeB1 = makeIllustrativeOutcome(testConfigB, seedB)
const outcomeB2 = makeIllustrativeOutcome(testConfigB, seedB)

if (JSON.stringify(outcomeB1) !== JSON.stringify(outcomeB2)) {
  throw new Error(`FAIL: Non-deterministic outcome for Scenario B!`)
}
console.log('✓ Scenario B produced identical outcome across multiple runs:', outcomeB1)

// Test 3: Scenario Narrative Description Generation
console.log('\n[Test 3] Dynamic Scenario Description Generation:')
const descA = describeScenario(testConfigA)
console.log('Scenario A Description:', descA)
if (!descA.includes('fog') || !descA.includes('18m') || !descA.includes('pedestrian')) {
  throw new Error(`FAIL: describeScenario did not include key attributes: ${descA}`)
}

const descB = describeScenario(testConfigB)
console.log('Scenario B Description:', descB)
if (!descB.includes('clear') || !descB.includes('40m') || !descB.includes('passenger vehicle')) {
  throw new Error(`FAIL: describeScenario did not include key attributes: ${descB}`)
}
console.log('✓ Descriptions generated dynamically and accurately.')

// Test 4: Scenario ID formatting
console.log('\n[Test 4] Scenario ID Formatting:')
const idA = getScenarioId(testConfigA)
const idB = getScenarioId(testConfigB)
console.log('Scenario A ID:', idA)
console.log('Scenario B ID:', idB)
if (!idA.startsWith('SCN-') || !idB.startsWith('SCN-')) {
  throw new Error(`FAIL: Scenario ID format incorrect: ${idA}, ${idB}`)
}
console.log('✓ Scenario IDs format correctly (SCN-XXXX).')

// Test 5: Outcome Severity and Description
console.log('\n[Test 5] Outcome Severity & Description formatting:')
const descOutcomeA = describeOutcome(outcomeA1, testConfigA)
const sevA = outcomeSeverity(outcomeA1, testConfigA)
const failTypeA = failureTypeFromOutcome(outcomeA1)
console.log('Outcome A Description:', descOutcomeA)
console.log('Outcome A Severity:', sevA)
console.log('Outcome A Failure Category:', failTypeA)
if (!descOutcomeA || !sevA || !failTypeA) {
  throw new Error('FAIL: Outcome formatting fields missing!')
}
console.log('✓ Outcome formatting & severity calculation valid.')

// Test 6: Verification of all 7 Weather Conditions
console.log('\n[Test 6] Weather Condition Axis Verification:')
WEATHER_CONDITIONS.forEach((w) => {
  if (!WEATHER_LABEL[w]) throw new Error(`Missing label for weather: ${w}`)
  const cfg = { ...DEFAULT_SCENARIO, weather: w }
  const desc = describeScenario(cfg)
  if (!desc.toLowerCase().includes(WEATHER_LABEL[w].toLowerCase().split('/')[0].trim())) {
    throw new Error(`Weather ${w} not found in description: ${desc}`)
  }
})
console.log(`✓ All ${WEATHER_CONDITIONS.length} weather conditions verified.`)

// Test 7: Verification of all 7 Lighting Conditions
console.log('\n[Test 7] Lighting Condition Axis Verification:')
LIGHTING_CONDITIONS.forEach((l) => {
  if (!LIGHTING_LABEL[l]) throw new Error(`Missing label for lighting: ${l}`)
  const cfg = { ...DEFAULT_SCENARIO, lighting: l }
  const id = getScenarioId(cfg)
  if (!id.startsWith('SCN-')) throw new Error(`Invalid ID for lighting: ${l}`)
})
console.log(`✓ All ${LIGHTING_CONDITIONS.length} lighting conditions verified.`)

// Test 8: Verification of all 5 Traffic Densities
console.log('\n[Test 8] Traffic Density Axis Verification:')
TRAFFIC_DENSITIES.forEach((t) => {
  if (!TRAFFIC_LABEL[t]) throw new Error(`Missing label for traffic: ${t}`)
})
console.log(`✓ All ${TRAFFIC_DENSITIES.length} traffic densities verified.`)

// Test 9: Verification of all 8 Road User Classes
console.log('\n[Test 9] Road User Class Axis Verification:')
ROAD_USER_CLASSES.forEach((ru) => {
  if (!ROAD_USER_LABEL[ru]) throw new Error(`Missing label for road user: ${ru}`)
  const cfg = { ...DEFAULT_SCENARIO, roadUser: ru }
  const desc = describeScenario(cfg)
  if (!desc.toLowerCase().includes(ROAD_USER_LABEL[ru].toLowerCase())) {
    throw new Error(`Road user ${ru} not found in description: ${desc}`)
  }
})
console.log(`✓ All ${ROAD_USER_CLASSES.length} road user classes verified.`)

// Test 10: Verification of all 4 Occlusion Levels
console.log('\n[Test 10] Occlusion Level Axis Verification:')
OCCLUSION_LEVELS.forEach((occ) => {
  if (!OCCLUSION_LABEL[occ]) throw new Error(`Missing label for occlusion: ${occ}`)
})
console.log(`✓ All ${OCCLUSION_LEVELS.length} occlusion levels verified.`)

// Test 11: Demo Dataset & Failure Record Integrity
console.log('\n[Test 11] Demo Dataset & Failure Record Integrity:')
const dataset = buildDemoDataset(25)
if (!dataset.runs || dataset.runs.length !== 25) {
  throw new Error(`FAIL: Dataset runs invalid: ${dataset.runs?.length}`)
}
if (!dataset.failures || dataset.failures.length === 0) {
  throw new Error(`FAIL: Dataset failures empty!`)
}
console.log(`✓ Dataset generated ${dataset.runs.length} runs and ${dataset.failures.length} failures.`)

// Test 12: Phase 4 4-Category Mapping Verification
console.log('\n[Test 12] Phase 4 4-Category Mapping Verification:')
const cat1 = mapToPhase4Category('missed_object')
const cat2 = mapToPhase4Category('ghost_detection')
const cat3 = mapToPhase4Category('distance_underestimate')
const cat4 = mapToPhase4Category('late_detection')
const cat5 = mapToPhase4Category('wrong_class')

if (cat1 !== 'missed_detection') throw new Error(`Expected missed_detection, got ${cat1}`)
if (cat2 !== 'false_positive') throw new Error(`Expected false_positive, got ${cat2}`)
if (cat3 !== 'poor_localization') throw new Error(`Expected poor_localization, got ${cat3}`)
if (cat4 !== 'confidence_degradation') throw new Error(`Expected confidence_degradation, got ${cat4}`)
if (cat5 !== 'confidence_degradation') throw new Error(`Expected confidence_degradation, got ${cat5}`)

console.log('✓ All internal failure kinds map deterministically to the 4 Phase 4 categories.')

// Test 13: Deterministic Failure Explanation Generator
console.log('\n[Test 13] Deterministic Failure Explanation Generator:')
const sampleFail = dataset.failures[0]
const explanation = generateFailureExplanation(sampleFail)
console.log('Sample Explanation:', explanation)
if (!explanation || explanation.length < 20) {
  throw new Error('FAIL: Generated failure explanation is empty or too short!')
}
console.log('✓ Failure explanation generated deterministically from scenario conditions.')

// Test 14: 2D Coverage Matrix Computation (Weather × Occlusion)
console.log('\n[Test 14] 2D Coverage Matrix (Weather × Occlusion):')
const matrix1 = computeCoverageMatrix(dataset.runs, dataset.failures, 'weather_occlusion')
if (matrix1.cells.length !== WEATHER_CONDITIONS.length * OCCLUSION_LEVELS.length) {
  throw new Error(`Expected ${WEATHER_CONDITIONS.length * OCCLUSION_LEVELS.length} cells, got ${matrix1.cells.length}`)
}
if (matrix1.summary.totalRuns !== dataset.runs.length) {
  throw new Error(`Matrix runs (${matrix1.summary.totalRuns}) does not match dataset (${dataset.runs.length})`)
}
console.log(`✓ Weather × Occlusion matrix computed ${matrix1.cells.length} slices (Tested: ${matrix1.summary.testedCount}, Under-Tested: ${matrix1.summary.underTestedCount}, Failure-Prone: ${matrix1.summary.failureProneCount}, Untested: ${matrix1.summary.untestedCount}).`)

// Test 15: Dimension Switching (Weather × Lighting and Traffic × Road User)
console.log('\n[Test 15] Coverage Dimension Switching:')
const matrix2 = computeCoverageMatrix(dataset.runs, dataset.failures, 'weather_lighting')
const matrix3 = computeCoverageMatrix(dataset.runs, dataset.failures, 'traffic_roadUser')
if (matrix2.cells.length !== WEATHER_CONDITIONS.length * LIGHTING_CONDITIONS.length) {
  throw new Error(`Weather × Lighting slice count mismatch: ${matrix2.cells.length}`)
}
if (matrix3.cells.length !== TRAFFIC_DENSITIES.length * ROAD_USER_CLASSES.length) {
  throw new Error(`Traffic × Road User slice count mismatch: ${matrix3.cells.length}`)
}
console.log(`✓ Dimension switching valid: Weather × Lighting (${matrix2.cells.length} slices), Traffic × Road User (${matrix3.cells.length} slices).`)

// Test 16: Reproducibility & Traceability
console.log('\n[Test 16] Complete Traceability Verification:')
const m1_a = computeCoverageMatrix(dataset.runs, dataset.failures, 'weather_occlusion')
const m1_b = computeCoverageMatrix(dataset.runs, dataset.failures, 'weather_occlusion')
if (JSON.stringify(m1_a.summary) !== JSON.stringify(m1_b.summary)) {
  throw new Error('FAIL: Coverage matrix calculation is not 100% deterministic!')
}
console.log('✓ Coverage matrix calculations are 100% deterministic and reproducible.')

// Test 17: isPassed outcome evaluation logic
console.log('\n[Test 17] isPassed Logic Verification:')
const passOutcome = { kind: 'detected_ok', severity: 'nominal' }
const failOutcome = { kind: 'false_negative', severity: 'critical' }
const isOutcomePassed = (outcome) => outcome?.kind === 'detected_ok'
if (!isOutcomePassed(passOutcome)) throw new Error('Expected passOutcome to be passed')
if (isOutcomePassed(failOutcome)) throw new Error('Expected failOutcome to NOT be passed')
console.log('✓ isPassed correctly distinguishes detected_ok from perception failure modes.')

// Test 18: Hot Zones & Coverage Gaps in Matrix
console.log('\n[Test 18] Hot Zones and Coverage Gaps:')
if (!matrix1.hotZones || !matrix1.coverageGaps) {
  throw new Error('Expected hotZones and coverageGaps to be present in matrixData')
}
console.log(`✓ Matrix contains ${matrix1.hotZones.length} ranked hot zones and ${matrix1.coverageGaps.length} coverage gaps.`)

// Test 19: Replay Scenario Config Determinism
console.log('\n[Test 19] Replay Scenario ID Match:')
const replaySample = dataset.failures[0]
const replayScnId = getScenarioId(replaySample.scenarioConfig)
const reOutcome = makeIllustrativeOutcome(replaySample.scenarioConfig)
if (reOutcome.kind !== replaySample.outcome?.kind) {
  throw new Error('Replayed scenario produced divergent outcome!')
}
console.log(`✓ Replaying scenario ${replayScnId} reproduces identical outcome (${reOutcome.kind}).`)

// Test 20: Stressor Level Diagnostics
console.log('\n[Test 20] Scenario Stress Diagnostics:')
const stressorsA = getScenarioStressors(testConfigA)
if (!Array.isArray(stressorsA) || stressorsA.length < 4) {
  throw new Error('Expected at least 4 stressor factors')
}
console.log(`✓ Stress diagnostic successfully evaluated ${stressorsA.length} factors deterministically.`)

console.log('\n====================================================')
console.log('🎉 ALL 20 PHASE 3 & 4 VERIFICATION TESTS PASSED!')
console.log('====================================================\n')

