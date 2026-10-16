import { useState } from 'react'
import { CameraFeed } from '@/components/layout/CameraFeed.jsx'
import { useLiveSimulation } from '@/hooks/useLiveSimulation.js'
import {
  asDisplayObject,
  formatBox,
  formatConfidence,
  formatValue,
  getSimulationStatusLabel,
} from '@/services/liveSimulation.js'
import {
  createScenarioPreviewPayload,
  DEFAULT_SCENARIO_PREVIEW,
} from '@/services/scenarioPreview.js'

const EXPECTED_ENDPOINTS = [
  'GET /api/v1/simulation/status',
  'GET /api/v1/simulation/snapshot',
  'WS /api/v1/simulation/ws',
  'GET /api/v1/simulation/reports/latest',
  'GET /api/v1/simulation/camera/status',
  'GET /api/v1/simulation/camera/{front|right_side|top_down}/stream (MJPEG)',
]

function ConnectionBadge({ connection }) {
  const isConnected = connection.state === 'connected'
  const isDegraded = connection.state === 'degraded'
  const kind = isConnected ? 'chip-accent' : isDegraded ? 'chip-warning' : 'chip-danger'
  const label = isConnected
    ? `Connected${connection.source ? ` · ${connection.source}` : ''}`
    : connection.state === 'not-configured'
      ? 'Backend URL not configured'
      : connection.state === 'connecting'
        ? 'Connecting'
        : isDegraded
          ? 'Connection degraded'
          : 'Disconnected'

  return <span className={`chip ${kind}`}>{label}</span>
}

function DataCard({ title, children, className = '' }) {
  return (
    <section className={`panel min-w-0 p-4 sm:p-5 ${className}`}>
      <h2 className="text-sm font-semibold">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  )
}

function JsonData({ value, unavailableText = 'Backend has not provided this data.' }) {
  const object = asDisplayObject(value)
  if (!object || Object.keys(object).length === 0) {
    return <p className="text-xs text-text-muted">{unavailableText}</p>
  }
  return (
    <pre className="max-h-72 overflow-auto rounded-lg border border-border-subtle bg-bg p-3 text-[11px] leading-5 text-text-muted">
      {JSON.stringify(object, null, 2)}
    </pre>
  )
}

export function LiveSimulationPage({ onSwitchToStatic }) {
  const live = useLiveSimulation()
  const [scenarioConfiguration, setScenarioConfiguration] = useState(
    DEFAULT_SCENARIO_PREVIEW,
  )
  const [previewPrepared, setPreviewPrepared] = useState(false)
  const scenarioPayload = createScenarioPreviewPayload(scenarioConfiguration)
  const snapshot = live.snapshot ?? {}
  const detections = Array.isArray(snapshot.detections) ? snapshot.detections : null
  const failures = Array.isArray(snapshot.failures) ? snapshot.failures : null
  const scenarioConditions =
    snapshot.scenario_conditions ?? snapshot.scenarioConditions ?? null
  const metrics = asDisplayObject(snapshot.metrics)
  const simulationStatus =
    snapshot.simulation_status ?? snapshot.simulationStatus ?? live.status

  const updateWeather = (key, value) => {
    setScenarioConfiguration((current) => ({
      ...current,
      weather: {
        ...current.weather,
        [key]: Number(value),
      },
    }))
    setPreviewPrepared(false)
  }

  const updateChoice = (key, value) => {
    setScenarioConfiguration((current) => ({ ...current, [key]: value }))
    setPreviewPrepared(false)
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 md:px-6">
      <header className="flex flex-col gap-4 border-b border-border-subtle pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="field-label text-accent">EDGEFORGE · LIVE SIMULATION</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            CARLA perception monitor
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-text-muted">
            Live mode displays backend-reported simulation state only. It never fills
            missing live data with the Static Demo sample dataset.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          <ConnectionBadge connection={live.connection} />
          <button type="button" className="btn" onClick={live.retry} disabled={live.loading}>
            {live.loading ? 'Checking…' : 'Retry connection'}
          </button>
        </div>
      </header>

      <div className="mt-5 rounded-lg border border-border-subtle bg-bg-elevated p-4" role="status">
        <p className="text-sm font-medium">
          {live.connection.state === 'connected'
            ? `Backend ${getSimulationStatusLabel(simulationStatus)}`
            : live.connection.state === 'connecting'
              ? 'Checking backend availability…'
              : 'Live simulation data is unavailable'}
        </p>
        <p className="mt-1 text-xs text-text-muted">{live.connection.message}</p>
        {live.lastUpdated ? (
          <p className="mt-2 text-[10px] text-text-subtle">
            Last backend update: {live.lastUpdated.toLocaleTimeString()}
          </p>
        ) : null}
        {!live.backendConfigured || live.connection.state === 'disconnected' ? (
          <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-text-muted">
              Live data is unavailable. Switch modes to explore the bundled presentation
              data without disguising it as simulation output.
            </p>
            <button type="button" className="btn btn-primary" onClick={onSwitchToStatic}>
              Switch to Static Demo
            </button>
          </div>
        ) : null}
      </div>

      {!live.backendConfigured ? (
        <div className="mt-5 panel p-4">
          <h2 className="text-sm font-semibold">Backend configuration required</h2>
          <p className="mt-2 text-xs text-text-muted">
            Set <code>VITE_EDGEFORGE_API_URL</code> in <code>frontend/.env.local</code>,
            then restart the frontend dev server. No CARLA connection or sample data
            is used by this page.
          </p>
        </div>
      ) : null}

      {live.loading && !live.snapshot ? (
        <div className="mt-5 panel p-8 text-center" aria-live="polite">
          <p className="text-sm font-medium">Loading live simulation data…</p>
          <p className="mt-1 text-xs text-text-muted">Contacting the configured backend.</p>
        </div>
      ) : null}

      <CameraFeed />

      <DataCard title="Scenario controls — preview only" className="mt-5">
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <span className="chip chip-warning">Preview — CARLA integration pending</span>
          <p className="text-xs text-text-muted">
            Adjust the scenario configuration locally. This preview does not change
            or generate a scenario in CARLA.
          </p>
        </div>

        <div className="grid gap-5 lg:grid-cols-2">
          <div className="space-y-4">
            {[
              ['precipitation', 'Rain intensity'],
              ['fog_density', 'Fog density'],
              ['wetness', 'Road wetness'],
            ].map(([key, label]) => (
              <label className="block" htmlFor={`scenario-${key}`} key={key}>
                <span className="mb-2 flex items-center justify-between text-xs">
                  <span className="font-medium">{label}</span>
                  <span className="font-mono text-text-muted">
                    {scenarioConfiguration.weather[key]}%
                  </span>
                </span>
                <input
                  id={`scenario-${key}`}
                  className="range-inline"
                  type="range"
                  min="0"
                  max="100"
                  step="1"
                  value={scenarioConfiguration.weather[key]}
                  onChange={(event) => updateWeather(key, event.target.value)}
                  aria-label={label}
                />
              </label>
            ))}

            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="field-label">Traffic density</span>
                <select
                  className="field-input mt-1"
                  value={scenarioConfiguration.traffic_density}
                  onChange={(event) => updateChoice('traffic_density', event.target.value)}
                >
                  {['Low', 'Moderate', 'High'].map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="field-label">Lighting</span>
                <select
                  className="field-input mt-1"
                  value={scenarioConfiguration.lighting}
                  onChange={(event) => updateChoice('lighting', event.target.value)}
                >
                  {['Day', 'Dawn/Dusk', 'Night'].map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </select>
              </label>
            </div>

            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setPreviewPrepared(true)}
            >
              Generate Scenario
            </button>
          </div>

          <div className="rounded-lg border border-border-subtle bg-bg p-4">
            <p className="field-label">Scenario summary</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="chip">Rain {scenarioConfiguration.weather.precipitation}%</span>
              <span className="chip">Fog {scenarioConfiguration.weather.fog_density}%</span>
              <span className="chip">Wetness {scenarioConfiguration.weather.wetness}%</span>
              <span className="chip">Traffic {scenarioConfiguration.traffic_density}</span>
              <span className="chip">Lighting {scenarioConfiguration.lighting}</span>
            </div>
            <pre className="mt-4 overflow-x-auto rounded-md border border-border-subtle bg-surface p-3 text-[11px] leading-5 text-text-muted">
              {JSON.stringify(scenarioPayload, null, 2)}
            </pre>
            {previewPrepared ? (
              <p className="mt-3 text-xs text-text-muted" role="status">
                Preview payload prepared locally only. No request was sent and CARLA
                was not changed.
              </p>
            ) : null}
          </div>
        </div>
      </DataCard>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {[
          ['Simulation', getSimulationStatusLabel(simulationStatus)],
          ['Frame', formatValue(snapshot.frame_id ?? snapshot.frameId)],
          ['Detections', detections ? String(detections.length) : 'Unavailable'],
          ['Failures', failures ? String(failures.length) : 'Unavailable'],
        ].map(([label, value]) => (
          <div className="panel p-4" key={label}>
            <p className="field-label">{label}</p>
            <p className="mt-2 truncate text-lg font-semibold">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <DataCard title="Live detections">
          {detections === null ? (
            <p className="text-xs text-text-muted">
              Detection data is not available in the backend response.
            </p>
          ) : detections.length === 0 ? (
            <p className="text-xs text-text-muted">
              No detections were reported for the latest snapshot.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-left text-xs">
                <thead className="text-[10px] uppercase tracking-wide text-text-subtle">
                  <tr>
                    <th className="pb-2 pr-3 font-medium">Class</th>
                    <th className="pb-2 pr-3 font-medium">Confidence</th>
                    <th className="pb-2 pr-3 font-medium">Box (x1,y1,x2,y2)</th>
                    <th className="pb-2 font-medium">Distance</th>
                  </tr>
                </thead>
                <tbody>
                  {detections.map((item, index) => (
                    <tr className="border-t border-border-subtle" key={item.id ?? item.object_id ?? index}>
                      <td className="py-2 pr-3">{item.object_class ?? item.object_type ?? 'Unavailable'}</td>
                      <td className="py-2 pr-3">{formatConfidence(item.confidence)}</td>
                      <td className="py-2 pr-3 font-mono text-[10px]">{formatBox(item.bbox)}</td>
                      <td className="py-2">{formatValue(item.distance, ' m')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataCard>

        <DataCard title="Scenario conditions">
          <JsonData value={scenarioConditions} />
        </DataCard>

        <DataCard title="Perception metrics">
          <JsonData value={metrics} />
        </DataCard>

        <DataCard title="Failure records">
          {failures === null ? (
            <p className="text-xs text-text-muted">
              Failure records are not available in the backend response.
            </p>
          ) : failures.length === 0 ? (
            <p className="text-xs text-text-muted">
              The backend reported no failure records for the latest snapshot.
            </p>
          ) : (
            <ul className="max-h-72 space-y-2 overflow-auto">
              {failures.map((failure, index) => (
                <li
                  className="rounded-md border border-border-subtle bg-bg p-3"
                  key={failure.id ?? `${failure.frame_id ?? 'frame'}-${index}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium">
                      {failure.failure_type ?? 'Unclassified failure'}
                    </span>
                    <span className="chip chip-warning">
                      {failure.severity ?? 'Severity unavailable'}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-text-muted">
                    {failure.object_class ?? 'Class unavailable'}
                    {' · confidence '}
                    {formatConfidence(failure.confidence)}
                    {' · frame '}
                    {formatValue(failure.frame_id)}
                  </p>
                  {failure.message ? (
                    <p className="mt-1 text-[11px] text-text-subtle">{failure.message}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </DataCard>
      </div>

      <DataCard title="Controls and reports" className="mt-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-medium">Simulation controls unavailable</p>
            <p className="mt-1 text-xs text-text-muted">
              The backend provides read-only simulation data and validation reports.
              Start/stop and scenario-configuration endpoints are intentionally not
              implemented, so those controls remain disabled.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn" disabled title="No backend control endpoint exists yet">
              Start simulation
            </button>
            <button
              type="button"
              className="btn"
              onClick={live.requestLatestReport}
              disabled={!live.backendConfigured}
            >
              Fetch latest report
            </button>
          </div>
        </div>
        {live.reportMessage ? (
          <p className="mt-3 text-xs text-text-muted" role="status">{live.reportMessage}</p>
        ) : null}
      </DataCard>

      <details className="mt-4 rounded-lg border border-border-subtle p-4">
        <summary className="cursor-pointer text-xs font-medium">
          Required backend API contract
        </summary>
        <p className="mt-2 text-xs text-text-muted">
          These read-only routes provide pipeline data when the simulation is running.
          Missing pipeline or validation data is returned as unavailable rather than
          being filled with sample values.
        </p>
        <ul className="mt-3 space-y-1 font-mono text-[10px] text-text-subtle">
          {EXPECTED_ENDPOINTS.map((endpoint) => <li key={endpoint}>{endpoint}</li>)}
        </ul>
      </details>
    </div>
  )
}

export default LiveSimulationPage
