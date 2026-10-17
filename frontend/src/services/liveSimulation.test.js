import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildBackendUrl,
  buildWebSocketUrl,
  createLiveSimulationClient,
  formatBox,
  formatConfidence,
  formatValue,
} from './liveSimulation.js'

test('backend and WebSocket URLs use configured origin and preserve path prefix', () => {
  assert.equal(
    buildBackendUrl('https://sim.example.test/edgeforge/', '/api/v1/simulation/status'),
    'https://sim.example.test/edgeforge/api/v1/simulation/status',
  )
  assert.equal(
    buildWebSocketUrl('https://sim.example.test/edgeforge'),
    'wss://sim.example.test/edgeforge/api/v1/simulation/ws',
  )
})

test('live client reads status and live snapshot from REST endpoints', async () => {
  const requestedPaths = []
  const fetchMock = async (url) => {
    const { pathname } = new URL(url)
    requestedPaths.push(pathname)
    const payload = pathname.endsWith('/status')
      ? { status: 'running' }
      : { detections: [{ object_type: 'car', confidence: 0.9 }] }
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }

  const result = await createLiveSimulationClient(
    'http://localhost:8123',
    fetchMock,
  ).loadSnapshot()

  assert.deepEqual(requestedPaths, [
    '/api/v1/simulation/status',
    '/api/v1/simulation/snapshot',
  ])
  assert.deepEqual(result.status, { status: 'running' })
  assert.equal(result.snapshot.detections[0].confidence, 0.9)
})

test('live client reads persisted simulation history from the history endpoint', async () => {
  const requested = []
  const history = { runs: [{ run_id: 'run-1' }], failures: [], coverage: { total_runs: 1 } }
  const client = createLiveSimulationClient('http://localhost:8123', async (url) => {
    requested.push(new URL(url).pathname)
    return new Response(JSON.stringify(history), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })

  assert.deepEqual(await client.getHistory(), history)
  assert.deepEqual(requested, ['/api/v1/simulation/history'])
})

test('live client requests ranked recommendations and executes the exact mock config', async () => {
  const requests = []
  const recommendation = {
    candidate_id: 'cand-1',
    scenario_id: 'scenario-1',
    scenario_config: {
      name: 'scenario-1',
      candidate_id: 'cand-1',
      fine_weather: { fog_density: 68 },
    },
  }
  const client = createLiveSimulationClient('http://localhost:8123', async (url, init) => {
    requests.push({
      url: new URL(url),
      method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(init.body) : null,
    })
    return new Response(JSON.stringify({ recommendations: [recommendation] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  })

  const ranked = await client.getRecommendations(undefined, { count: 7, seed: 31 })
  assert.equal(ranked.recommendations[0].scenario_id, 'scenario-1')
  assert.equal(requests[0].url.pathname, '/api/v1/scenarios/recommendations')
  assert.equal(requests[0].url.searchParams.get('count'), '7')
  assert.equal(requests[0].url.searchParams.get('seed'), '31')

  await client.executeRecommendation(recommendation, undefined, { maxFrames: 3 })
  assert.equal(requests[1].url.pathname, '/api/v1/scenarios/execute')
  assert.equal(requests[1].method, 'POST')
  assert.deepEqual(requests[1].body, {
    candidate_id: 'cand-1',
    scenario_config: recommendation.scenario_config,
    backend: 'mock',
    max_frames: 3,
  })
})

test('live client reports unavailable endpoint instead of inventing data', async () => {
  const client = createLiveSimulationClient(
    'http://localhost:8123',
    async () => new Response('Not found', { status: 404 }),
  )

  await assert.rejects(
    client.loadSnapshot(),
    /This backend endpoint is not implemented.*\/api\/v1\/simulation\/status/,
  )
})

test('live client reports network failures clearly', async () => {
  const client = createLiveSimulationClient(
    'http://localhost:8123',
    async () => {
      throw new TypeError('fetch failed')
    },
  )

  await assert.rejects(client.loadSnapshot(), /Cannot reach the EdgeForge backend/)
})

test('live values format missing confidence, malformed boxes, and floats cleanly', () => {
  assert.equal(formatConfidence(null), 'Unavailable')
  assert.equal(formatConfidence(0.875), '87.5%')
  assert.equal(formatBox([1.3, 2, 9, 10]), '1, 2, 9, 10')
  assert.equal(formatBox([1, 2, Number.NaN, 10]), 'Unavailable')
  assert.equal(formatValue(240.00000000000006, ' m'), '240 m')
  assert.equal(formatValue(224.34, ' m'), '224.3 m')
  assert.equal(formatValue(null, ' m'), 'Unavailable')
})

test('live client can start and stop simulation via API', async () => {
  const requests = []
  const fetchMock = async (url, init) => {
    const { pathname } = new URL(url)
    requests.push({
      pathname,
      method: init?.method,
      body: init?.body ? JSON.parse(init.body) : null,
    })
    return new Response(
      JSON.stringify({
        status: pathname.endsWith('/start') ? 'started' : 'stopped',
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      },
    )
  }

  const client = createLiveSimulationClient('http://localhost:8123', fetchMock)
  const startRes = await client.startSimulation({ backend: 'mock' })
  assert.equal(startRes.status, 'started')
  assert.equal(requests[0].method, 'POST')
  assert.equal(requests[0].pathname, '/api/v1/simulation/start')
  assert.equal(requests[0].body.backend, 'mock')

  const startCarlaRes = await client.startSimulation({ backend: 'carla' })
  assert.equal(startCarlaRes.status, 'started')
  assert.equal(requests[1].pathname, '/api/v1/simulation/start')
  assert.equal(requests[1].body.backend, 'carla')

  const stopRes = await client.stopSimulation()
  assert.equal(stopRes.status, 'stopped')
  assert.equal(requests[2].method, 'POST')
  assert.equal(requests[2].pathname, '/api/v1/simulation/stop')
})

test('live client can get and update configuration via API', async () => {
  const requests = []
  const fetchMock = async (url, init) => {
    const { pathname } = new URL(url)
    requests.push({
      pathname,
      method: init?.method,
      body: init?.body ? JSON.parse(init.body) : null,
    })
    return new Response(
      JSON.stringify({
        status: 'success',
        configuration: init?.body ? JSON.parse(init.body) : {},
      }),
      {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      },
    )
  }

  const client = createLiveSimulationClient('http://localhost:8123', fetchMock)
  await client.updateConfiguration({ weather: { precipitation: 40 } })
  assert.equal(requests[0].method, 'PUT')
  assert.equal(requests[0].pathname, '/api/v1/simulation/configuration')
  assert.equal(requests[0].body.weather.precipitation, 40)

  await client.getConfiguration()
  assert.equal(requests[1].pathname, '/api/v1/simulation/configuration')
})
