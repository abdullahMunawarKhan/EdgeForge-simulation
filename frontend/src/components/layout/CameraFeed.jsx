import { useEffect, useState } from 'react'
import { buildCameraFeedUrls } from '@/services/cameraFeed.js'

const CAMERA_STATUS_POLL_MS = 1500
const CAMERA_VIEWS = [
  { id: 'front', label: 'Front', yoloOverlay: true },
  { id: 'top_down', label: 'Top-Down', yoloOverlay: false },
]

function emptyCamera(state, message) {
  return {
    state,
    available: false,
    message,
    frameId: null,
    fps: null,
    streamUrl: null,
  }
}

export function CameraFeed() {
  const baseUrl = import.meta.env.VITE_EDGEFORGE_API_URL?.trim() ?? ''
  const [cameras, setCameras] = useState(() =>
    Object.fromEntries(
      CAMERA_VIEWS.map(({ id }) => [
        id,
        emptyCamera(
          baseUrl ? 'connecting' : 'not-configured',
          baseUrl
            ? 'Checking the backend for a live CARLA camera feed.'
            : 'Configure the backend URL to check for a live CARLA camera feed.',
        ),
      ]),
    ),
  )
  const [retryKey, setRetryKey] = useState(0)
  const [streamConnected, setStreamConnected] = useState({})
  const [streamErrors, setStreamErrors] = useState({})

  useEffect(() => {
    if (!baseUrl) {
      setCameras(
        Object.fromEntries(
          CAMERA_VIEWS.map(({ id }) => [
            id,
            emptyCamera(
              'not-configured',
              'Live camera unavailable because VITE_EDGEFORGE_API_URL is not configured.',
            ),
          ]),
        ),
      )
      return undefined
    }

    let cancelled = false
    let timer
    let controller
    let urls
    setStreamConnected({})
    setStreamErrors({})

    try {
      urls = buildCameraFeedUrls(baseUrl)
    } catch (error) {
      setCameras(
        Object.fromEntries(
          CAMERA_VIEWS.map(({ id }) => [
            id,
            emptyCamera(
              'disconnected',
              error instanceof Error ? error.message : 'Invalid backend URL.',
            ),
          ]),
        ),
      )
      return undefined
    }

    const poll = async () => {
      controller = new AbortController()
      try {
        const response = await fetch(urls.status, { signal: controller.signal })
        const payload = await response.json()
        if (!response.ok) {
          throw new Error(payload.detail ?? `Camera status returned HTTP ${response.status}.`)
        }
        if (cancelled) return
        const reported = payload.cameras ?? { front: payload }
        setCameras(
          Object.fromEntries(
            CAMERA_VIEWS.map(({ id }) => {
              const status = reported[id] ?? emptyCamera(
                'disconnected',
                `The ${id.replace('_', '-')} camera is unavailable from this backend.`,
              )
              return [
                id,
                {
                  state: status.available ? 'connected' : status.status ?? 'disconnected',
                  available: status.available === true,
                  message: status.message ?? 'Camera status unavailable.',
                  frameId: status.frame_id ?? null,
                  fps: status.fps ?? null,
                  streamUrl: status.available ? urls.cameras[id] : null,
                },
              ]
            }),
          ),
        )
      } catch (error) {
        if (cancelled || error?.name === 'AbortError') return
        setCameras(
          Object.fromEntries(
            CAMERA_VIEWS.map(({ id }) => [
              id,
              emptyCamera(
                'disconnected',
                error instanceof Error
                  ? error.message
                  : 'Could not reach the camera endpoint.',
              ),
            ]),
          ),
        )
      } finally {
        if (!cancelled) timer = window.setTimeout(poll, CAMERA_STATUS_POLL_MS)
      }
    }

    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      controller?.abort()
    }
  }, [baseUrl, retryKey])

  const retry = () => {
    setStreamConnected({})
    setStreamErrors({})
    setRetryKey((current) => current + 1)
  }

  return (
    <section className="panel mt-5 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-subtle p-4 sm:px-5">
        <div>
          <h2 className="text-sm font-semibold">Live CARLA camera views</h2>
          <p className="mt-1 text-xs text-text-muted">
            Front and top-down views from the existing ego vehicle. YOLO detections
            are overlaid on the front view.
          </p>
        </div>
        <button type="button" className="btn" onClick={retry}>
          Retry cameras
        </button>
      </div>

      <div className="grid gap-3 bg-bg p-3 sm:grid-cols-2 sm:p-4">
        {CAMERA_VIEWS.map((view) => {
          const camera = cameras[view.id]
          const connected = camera.available && streamConnected[view.id]
          const badge = connected
            ? 'Connected'
            : camera.state === 'not-configured'
              ? 'Backend URL not configured'
              : camera.available
                ? 'Opening stream'
                : camera.state === 'connecting'
                  ? 'Connecting'
                  : 'Disconnected'

          return (
            <article
              key={view.id}
              className="min-w-0 overflow-hidden rounded-xl border border-border-subtle bg-bg-elevated"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle px-3 py-2">
                <h3 className="text-xs font-semibold">{view.label}</h3>
                <span className={`chip ${
                  connected
                    ? 'chip-accent'
                    : camera.state === 'connecting' || camera.available
                      ? 'chip-warning'
                      : 'chip-danger'
                }`}>
                  {badge}
                </span>
              </div>

              {camera.available && camera.streamUrl ? (
                <img
                  key={`${camera.streamUrl}-${retryKey}`}
                  className="aspect-video w-full bg-bg object-contain"
                  src={camera.streamUrl}
                  alt={`Live CARLA ${view.label} camera view${
                    view.yoloOverlay ? ' with YOLO bounding boxes' : ''
                  }`}
                  onLoad={() => {
                    setStreamConnected((current) => ({ ...current, [view.id]: true }))
                    setStreamErrors((current) => ({ ...current, [view.id]: '' }))
                  }}
                  onError={() => {
                    setStreamConnected((current) => ({ ...current, [view.id]: false }))
                    setStreamErrors((current) => ({
                      ...current,
                      [view.id]: 'The camera stream disconnected or could not be opened.',
                    }))
                    setCameras((current) => ({
                      ...current,
                      [view.id]: {
                        ...current[view.id],
                        state: 'disconnected',
                        available: false,
                        message: 'The camera stream disconnected or could not be opened.',
                        streamUrl: null,
                      },
                    }))
                  }}
                />
              ) : (
                <div className="flex aspect-video items-center justify-center bg-bg px-4 text-center">
                  <div>
                    <p className="text-xs font-medium">No live frame available</p>
                    <p className="mt-1 text-[11px] text-text-muted">{camera.message}</p>
                  </div>
                </div>
              )}

              <div className="space-y-1 border-t border-border-subtle px-3 py-2 text-[10px] text-text-muted">
                <p>Frame: {camera.frameId ?? 'Unavailable'} · FPS: {
                  typeof camera.fps === 'number' ? camera.fps.toFixed(1) : 'Unavailable'
                }</p>
                <p>{view.yoloOverlay
                  ? 'YOLO overlay: supported'
                  : 'YOLO overlay: not provided for this view'}</p>
                {streamErrors[view.id] ? (
                  <p className="text-danger" role="status">{streamErrors[view.id]}</p>
                ) : null}
              </div>
            </article>
          )
        })}
      </div>

      <p className="border-t border-border-subtle px-4 py-3 text-[10px] text-text-subtle sm:px-5">
        Live frames only. No static images or demo frames are used in these views.
      </p>
    </section>
  )
}

export default CameraFeed
