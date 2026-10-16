import assert from 'node:assert/strict'
import test from 'node:test'
import {
  createScenarioPreviewPayload,
  DEFAULT_SCENARIO_PREVIEW,
} from './scenarioPreview.js'

test('scenario preview defaults match the requested configuration', () => {
  assert.deepEqual(DEFAULT_SCENARIO_PREVIEW, {
    weather: {
      precipitation: 70,
      fog_density: 40,
      wetness: 80,
    },
    traffic_density: 'Moderate',
    lighting: 'Day',
  })
})

test('scenario preview payload preserves normalized backend field names', () => {
  const payload = createScenarioPreviewPayload({
    weather: {
      precipitation: '55',
      fog_density: '25',
      wetness: '90',
    },
    traffic_density: 'High',
    lighting: 'Night',
  })

  assert.deepEqual(payload, {
    weather: {
      precipitation: 55,
      fog_density: 25,
      wetness: 90,
    },
    traffic_density: 'High',
    lighting: 'Night',
  })
})
