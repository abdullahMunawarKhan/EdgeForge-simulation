import assert from 'node:assert/strict'
import test from 'node:test'
import {
  buildBackendUrl,
  buildWebSocketUrl,
  createLiveSimulationClient,
  formatBox,
  formatConfidence,
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

test('live values format missing confidence and malformed boxes as unavailable', () => {
  assert.equal(formatConfidence(null), 'Unavailable')
  assert.equal(formatConfidence(0.875), '87.5%')
  assert.equal(formatBox([1.3, 2, 9, 10]), '1, 2, 9, 10')
  assert.equal(formatBox([1, 2, Number.NaN, 10]), 'Unavailable')
})
