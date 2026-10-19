import { buildBackendUrl } from './liveSimulation.js'

export function buildCameraFeedUrls(baseUrl) {
  return {
    status: buildBackendUrl(baseUrl, 'api/v1/simulation/camera/status'),
    cameras: {
      front: buildBackendUrl(baseUrl, 'api/v1/simulation/camera/front/stream'),
      top_down: buildBackendUrl(baseUrl, 'api/v1/simulation/camera/top_down/stream'),
    },
  }
}
