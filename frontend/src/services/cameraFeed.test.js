import assert from 'node:assert/strict'
import test from 'node:test'
import { buildCameraFeedUrls } from './cameraFeed.js'

test('camera feed uses the configured backend origin and API path', () => {
  assert.deepEqual(
    buildCameraFeedUrls('http://localhost:8000/edgeforge'),
    {
      status: 'http://localhost:8000/edgeforge/api/v1/simulation/camera/status',
      cameras: {
        front: 'http://localhost:8000/edgeforge/api/v1/simulation/camera/front/stream',
        top_down: 'http://localhost:8000/edgeforge/api/v1/simulation/camera/top_down/stream',
      },
    },
  )
})
