const API_PATHS = {
  status: 'api/v1/simulation/status',
  snapshot: 'api/v1/simulation/snapshot',
  report: 'api/v1/simulation/reports/latest',
  configuration: 'api/v1/simulation/configuration',
  websocket: 'api/v1/simulation/ws',
}

function parseBaseUrl(baseUrl) {
  const value = String(baseUrl ?? '').trim()
  if (!value) throw new Error('VITE_EDGEFORGE_API_URL is not configured.')

  let url
  try {
    url = new URL(value)
  } catch {
    throw new Error('VITE_EDGEFORGE_API_URL must be a valid absolute URL.')
  }

  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error('VITE_EDGEFORGE_API_URL must use HTTP or HTTPS.')
  }
  url.search = ''
  url.hash = ''
  url.pathname = `${url.pathname.replace(/\/+$/, '')}/`
  return url
}

export function buildBackendUrl(baseUrl, path) {
  const base = parseBaseUrl(baseUrl)
  return new URL(path.replace(/^\/+/, ''), base).toString()
}

export function buildWebSocketUrl(baseUrl) {
  const url = new URL(buildBackendUrl(baseUrl, API_PATHS.websocket))
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.toString()
}

async function requestJson(fetchImpl, url, init) {
  let response
  try {
    response = await fetchImpl(url, init)
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'Network request failed.'
    throw new Error(`Cannot reach the EdgeForge backend: ${detail}`)
  }

  if (!response.ok) {
    const endpoint = new URL(url).pathname
    const availability =
      response.status === 404 ? 'This backend endpoint is not implemented.' : 'Request failed.'
    throw new Error(`${availability} ${endpoint} returned HTTP ${response.status}.`)
  }

  try {
    return await response.json()
  } catch {
    throw new Error(`Backend returned invalid JSON from ${new URL(url).pathname}.`)
  }
}

export function createLiveSimulationClient(baseUrl, fetchImpl = globalThis.fetch) {
  const statusUrl = buildBackendUrl(baseUrl, API_PATHS.status)
  const snapshotUrl = buildBackendUrl(baseUrl, API_PATHS.snapshot)

  return {
    async loadSnapshot(signal) {
      const status = await requestJson(fetchImpl, statusUrl, { signal })
      const snapshot = await requestJson(fetchImpl, snapshotUrl, { signal })
      if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot)) {
        throw new Error('Backend snapshot must be a JSON object.')
      }
      return { status, snapshot }
    },

    getReport(signal) {
      return requestJson(
        fetchImpl,
        buildBackendUrl(baseUrl, API_PATHS.report),
        { signal },
      )
    },

    updateConfiguration(configuration, signal) {
      return requestJson(
        fetchImpl,
        buildBackendUrl(baseUrl, API_PATHS.configuration),
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(configuration),
          signal,
        },
      )
    },

    createWebSocket(WebSocketConstructor = globalThis.WebSocket) {
      if (typeof WebSocketConstructor !== 'function') {
        throw new Error('This browser does not support WebSockets.')
      }
      return new WebSocketConstructor(buildWebSocketUrl(baseUrl))
    },
  }
}

export function getSimulationStatusLabel(status) {
  if (typeof status === 'string') return status
  if (status && typeof status === 'object') {
    return status.status ?? status.state ?? status.simulation_status ?? 'Status unavailable'
  }
  return 'Status unavailable'
}

export function formatValue(value, suffix = '') {
  if (value === null || value === undefined || value === '') return 'Unavailable'
  if (typeof value === 'number' && !Number.isFinite(value)) return 'Unavailable'
  return `${value}${suffix}`
}

export function formatConfidence(value) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 'Unavailable'
  return `${(value * 100).toFixed(1)}%`
}

export function formatBox(box) {
  if (
    !Array.isArray(box) ||
    box.length !== 4 ||
    !box.every((coordinate) => typeof coordinate === 'number' && Number.isFinite(coordinate))
  ) {
    return 'Unavailable'
  }
  return box.map((coordinate) => Math.round(coordinate)).join(', ')
}

export function asDisplayObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value
}
