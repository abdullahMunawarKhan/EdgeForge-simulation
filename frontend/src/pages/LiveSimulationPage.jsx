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
  'POST /api/v1/simulation/start',
  'POST /api/v1/simulation/stop',
  'PUT /api/v1/simulation/configuration',
  'GET /api/v1/simulation/snapshot',
  'GET /api/v1/simulation/history',
  'GET /api/v1/scenarios/recommendations',
  'POST /api/v1/scenarios/execute (mock)',
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

function DataCard({ title, badge, children, className = '' }) {
  return (
    <section className={`panel min-w-0 p-4 sm:p-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{title}</h2>
        {badge}
      </div>
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

function RiskBadge({ level }) {
  const normalized = String(level ?? 'NOMINAL').toUpperCase()
  let kind = 'chip-accent'
  if (normalized === 'CRITICAL') kind = 'chip-danger'
  else if (normalized === 'HIGH') kind = 'chip-warning'
  else if (normalized === 'MEDIUM') kind = 'chip-warning'

  return <span className={`chip font-semibold ${kind}`}>{normalized}</span>
}

export function LiveSimulationPage({ onSwitchToStatic }) {
  const live = useLiveSimulation()
  const [selectedBackend, setSelectedBackend] = useState('mock')
  const [scenarioConfiguration, setScenarioConfiguration] = useState(
    DEFAULT_SCENARIO_PREVIEW,
  )
  const scenarioPayload = createScenarioPreviewPayload(scenarioConfiguration)
  const snapshot = live.snapshot ?? {}
  const detections = Array.isArray(snapshot.detections) ? snapshot.detections : null
  const failures = Array.isArray(snapshot.failures) ? snapshot.failures : null
  const scenarioConditions =
    snapshot.scenario_conditions ?? snapshot.scenarioConditions ?? null
  const metrics = asDisplayObject(snapshot.metrics)
  const riskAssessment = asDisplayObject(snapshot.risk_assessment ?? snapshot.riskAssessment)
  const simulationStatus =
    snapshot.simulation_status ?? snapshot.simulationStatus ?? live.status

  const isRunning =
    simulationStatus === 'running' ||
    live.status?.is_running === true ||
    (typeof simulationStatus === 'object' && simulationStatus?.status === 'running')

  const activeBackend = snapshot.backend ?? live.status?.backend ?? null

  const getPerceptionSourceBadge = () => {
    if (!isRunning && !activeBackend) {
      return {
        label: 'IDLE — READY',
        kind: 'chip',
        description: 'Simulation is not currently active.',
      }
    }
    const normalized = String(activeBackend || '').toLowerCase()
    if (normalized === 'mock') {
      return {
        label: 'MOCK DATA — SYNTHETIC DETECTIONS',
        kind: 'chip chip-warning font-semibold',
        description: 'Using synthetic mock projections. YOLO inference is bypassed.',
      }
    }
    if (normalized === 'carla') {
      const hasInferenceConfirmed =
        (detections && detections.length > 0) ||
        (typeof snapshot.frame_id === 'number' && snapshot.frame_id > 0)
      if (isRunning && hasInferenceConfirmed) {
        return {
          label: 'CARLA + YOLO — LIVE INFERENCE',
          kind: 'chip chip-accent font-semibold',
          description: 'Live CARLA RGB camera stream with real YOLOv8 object detections.',
        }
      }
      return {
        label: 'CARLA + YOLO — VERIFYING LIVE PIPELINE',
        kind: 'chip chip-accent font-semibold animate-pulse',
        description: 'Connecting to CARLA server and verifying live perception pipeline.',
      }
    }
    return {
      label: 'PERCEPTION STATUS UNKNOWN',
      kind: 'chip',
      description: '',
    }
  }

  const sourceBadge = getPerceptionSourceBadge()

  const updateWeather = (key, value) => {
    setScenarioConfiguration((current) => ({
      ...current,
      weather: {
        ...current.weather,
        [key]: Number(value),
      },
    }))
  }

  const updateChoice = (key, value) => {
    setScenarioConfiguration((current) => ({ ...current, [key]: value }))
  }

  const handleStartSimulation = async () => {
    await live.startSimulation({
      backend: selectedBackend,
      scenario: scenarioConfiguration,
    })
  }

  const handleStopSimulation = async () => {
    await live.stopSimulation()
  }

  const handleApplyConfiguration = async () => {
    await live.updateConfiguration(scenarioConfiguration)
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 md:px-6">
      <header className="flex flex-col gap-4 border-b border-border-subtle pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="field-label text-accent">EDGEFORGE · LIVE SIMULATION</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight sm:text-3xl">
            Live perception & simulation monitor
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-text-muted">
            Direct real-time link to the EdgeForge simulation runtime. Controls allow
            starting/stopping the mock simulation and updating environmental stress parameters.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          <ConnectionBadge connection={live.connection} />
          <button
            type="button"
            className="btn"
            onClick={live.retry}
            disabled={live.loading || live.actionLoading}
          >
            {live.loading ? 'Checking…' : 'Refresh'}
          </button>
        </div>
      </header>

      {/* Action Notification Banners */}
      {live.actionError ? (
        <div className="mt-4 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400" role="alert">
          <strong className="font-semibold">Action Failed: </strong>
          {live.actionError}
        </div>
      ) : null}

      {live.actionSuccess ? (
        <div className="mt-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-400" role="status">
          <strong className="font-semibold">Success: </strong>
          {live.actionSuccess}
        </div>
      ) : null}

      <div className="mt-5 rounded-lg border border-border-subtle bg-bg-elevated p-4" role="status">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">
              {live.connection.state === 'connected'
                ? `Backend: ${getSimulationStatusLabel(simulationStatus)}${activeBackend ? ` (${activeBackend.toUpperCase()})` : ''}`
                : live.connection.state === 'connecting'
                  ? 'Checking backend availability…'
                  : 'Live simulation backend is disconnected'}
            </p>
            <p className="mt-1 text-xs text-text-muted">{live.connection.message}</p>
            {live.lastUpdated ? (
              <p className="mt-1 text-[10px] text-text-subtle">
                Last update: {live.lastUpdated.toLocaleTimeString()}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {!isRunning ? (
              <div className="flex items-center gap-1.5 rounded-lg border border-border-subtle bg-bg p-1 text-xs">
                <button
                  type="button"
                  className={`px-3 py-1 font-medium rounded transition-colors ${
                    selectedBackend === 'mock'
                      ? 'bg-accent/20 text-accent font-semibold border border-accent/40'
                      : 'text-text-muted hover:text-text'
                  }`}
                  onClick={() => setSelectedBackend('mock')}
                  disabled={Boolean(live.actionLoading)}
                >
                  Mock Engine
                </button>
                <button
                  type="button"
                  className={`px-3 py-1 font-medium rounded transition-colors ${
                    selectedBackend === 'carla'
                      ? 'bg-accent/20 text-accent font-semibold border border-accent/40'
                      : 'text-text-muted hover:text-text'
                  }`}
                  onClick={() => setSelectedBackend('carla')}
                  disabled={Boolean(live.actionLoading)}
                >
                  CARLA Simulator
                </button>
              </div>
            ) : null}

            {isRunning ? (
              <button
                type="button"
                className="btn btn-danger font-semibold px-4 py-2"
                onClick={handleStopSimulation}
                disabled={Boolean(live.actionLoading)}
              >
                {live.actionLoading === 'stop' ? 'Stopping…' : '⏹ Stop Simulation'}
              </button>
            ) : (
              <button
                type="button"
                className="btn btn-primary font-semibold px-4 py-2"
                onClick={handleStartSimulation}
                disabled={Boolean(live.actionLoading) || !live.backendConfigured}
              >
                {live.actionLoading === 'start'
                  ? 'Starting…'
                  : selectedBackend === 'carla'
                    ? '▶ Start CARLA Simulation'
                    : '▶ Start Mock Simulation'}
              </button>
            )}

            <button
              type="button"
              className="btn text-xs"
              onClick={live.requestLatestReport}
              disabled={!live.backendConfigured || Boolean(live.actionLoading)}
            >
              Latest Report
            </button>
          </div>
        </div>

        {!live.backendConfigured || live.connection.state === 'disconnected' ? (
          <div className="mt-3 flex flex-col gap-3 border-t border-border-subtle pt-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-text-muted">
              Live simulation backend is not reachable. You can explore the bundled
              presentation dataset in Static Demo mode.
            </p>
            <button type="button" className="btn btn-secondary text-xs" onClick={onSwitchToStatic}>
              Switch to Static Demo
            </button>
          </div>
        ) : null}
      </div>

      {!live.backendConfigured ? (
        <div className="mt-5 panel p-4">
          <h2 className="text-sm font-semibold">Backend configuration required</h2>
          <p className="mt-2 text-xs text-text-muted">
            Set <code>VITE_EDGEFORGE_API_URL=http://127.0.0.1:8000</code> in <code>frontend/.env.local</code>.
          </p>
        </div>
      ) : null}

      {/* Camera Streams */}
      <CameraFeed />

      {/* Live Interactive Scenario Controls */}
      <DataCard title="Live Scenario Parameters & Environmental Controls" className="mt-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className={`chip ${isRunning ? 'chip-accent' : 'chip-warning'}`}>
              {isRunning ? 'Simulation Running' : 'Pending Configuration'}
            </span>
            <p className="text-xs text-text-muted">
              Adjust weather, lighting, and traffic stress parameters dynamically.
            </p>
          </div>

          <button
            type="button"
            className="btn btn-primary text-xs"
            onClick={handleApplyConfiguration}
            disabled={Boolean(live.actionLoading) || !live.backendConfigured}
          >
            {live.actionLoading === 'config' ? 'Applying…' : '⚡ Apply to Simulation'}
          </button>
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
          </div>

          <div className="rounded-lg border border-border-subtle bg-bg p-4">
            <p className="field-label">Active Scenario Summary</p>
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
          </div>
        </div>
      </DataCard>

      {/* Real-time Status Metric Cards */}
      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {[
          ['Simulation Status', getSimulationStatusLabel(simulationStatus)],
          ['Frame ID', formatValue(snapshot.frame_id ?? snapshot.frameId)],
          ['Active Detections', detections ? String(detections.length) : '0'],
          ['Risk Score', riskAssessment ? `${(riskAssessment.risk_score * 100).toFixed(0)}%` : 'Nominal'],
          ['Validation Failures', failures ? String(failures.length) : '0'],
        ].map(([label, value]) => (
          <div className="panel p-4" key={label}>
            <p className="field-label">{label}</p>
            <p className="mt-2 truncate text-lg font-semibold">{value}</p>
          </div>
        ))}
      </div>

      {/* Driving Risk Engine Live Analysis */}
      {riskAssessment ? (
        <section className="panel mt-5 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle pb-3">
            <div>
              <h2 className="text-sm font-semibold">Live Driving Risk Assessment</h2>
              <p className="text-xs text-text-muted mt-0.5">
                Explainable rule-based scoring combining proximity and closing speed.
              </p>
            </div>
            <RiskBadge level={riskAssessment.risk_level} />
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-border-subtle bg-bg p-3">
              <p className="field-label">Risk Score</p>
              <div className="mt-2 flex items-baseline gap-2">
                <span className="text-2xl font-bold font-mono">
                  {riskAssessment.risk_score?.toFixed(2) ?? '0.00'}
                </span>
                <span className="text-xs text-text-muted">/ 1.00</span>
              </div>
              <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-border-subtle">
                <div
                  className={`h-full transition-all duration-300 ${
                    riskAssessment.risk_score >= 0.7
                      ? 'bg-red-500'
                      : riskAssessment.risk_score >= 0.4
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                  }`}
                  style={{ width: `${Math.min(100, (riskAssessment.risk_score ?? 0) * 100)}%` }}
                />
              </div>
            </div>

            <div className="rounded-lg border border-border-subtle bg-bg p-3 md:col-span-2">
              <p className="field-label">Risk Assessment Explanation</p>
              <p className="mt-2 text-xs leading-relaxed text-text">
                {riskAssessment.explanation || 'Nominal driving conditions. No immediate collision hazard detected.'}
              </p>
              {Array.isArray(riskAssessment.contributing_objects) && riskAssessment.contributing_objects.length > 0 ? (
                <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                  <span className="text-[10px] uppercase text-text-subtle font-mono">Hazards:</span>
                  {riskAssessment.contributing_objects.map((objId) => (
                    <span key={objId} className="chip chip-warning text-[10px]">
                      {objId}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          </div>
        </section>
      ) : null}

      {/* Live Detections & Scenario Conditions */}
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <DataCard
          title="Live Object Detections (Perception Pipeline)"
          badge={
            <span className={sourceBadge.kind} title={sourceBadge.description}>
              {sourceBadge.label}
            </span>
          }
        >
          {detections === null ? (
            <p className="text-xs text-text-muted">
              {activeBackend === 'carla' && isRunning
                ? 'Verifying live CARLA perception pipeline… awaiting first frame detections.'
                : 'Detection data is not available in the backend response.'}
            </p>
          ) : detections.length === 0 ? (
            <p className="text-xs text-text-muted">
              No detections reported for current frame.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[500px] text-left text-xs">
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
                      <td className="py-2 pr-3 font-medium text-text">
                        {item.object_class ?? item.object_type ?? 'Object'}
                      </td>
                      <td className="py-2 pr-3 font-mono">{formatConfidence(item.confidence)}</td>
                      <td className="py-2 pr-3 font-mono text-[10px] text-text-muted">{formatBox(item.bbox)}</td>
                      <td className="py-2 font-mono">{formatValue(item.distance, ' m')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataCard>

        <DataCard title="Live Scenario Conditions">
          <JsonData value={scenarioConditions} />
        </DataCard>

        <DataCard title="Perception Metrics">
          <JsonData value={metrics} />
        </DataCard>

        <DataCard title="Failure Records & Diagnostics">
          {failures === null ? (
            <p className="text-xs text-text-muted">
              Failure records are not active in the current stream.
            </p>
          ) : failures.length === 0 ? (
            <p className="text-xs text-text-muted">
              No perception failures reported for the active tick.
            </p>
          ) : (
            <ul className="max-h-72 space-y-2 overflow-auto">
              {failures.map((failure, index) => (
                <li
                  className="rounded-md border border-border-subtle bg-bg p-3"
                  key={failure.failure_id ?? `${failure.frame_id ?? 'frame'}-${index}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="text-xs font-medium">
                      {failure.failure_type ?? 'Unclassified failure'}
                    </span>
                    <span className="chip chip-warning">
                      {failure.severity ?? 'Medium'}
                    </span>
                  </div>
                  <p className="mt-1 text-[11px] text-text-muted">
                    {failure.object_class ?? 'Class unavailable'}
                    {' · confidence '}
                    {formatConfidence(failure.confidence)}
                    {' · frame '}
                    {formatValue(failure.frame_id)}
                  </p>
                  <p className="mt-1 break-all font-mono text-[10px] text-text-subtle">
                    ID: {failure.failure_id ?? 'Unavailable'}
                    {' · fingerprint: '}
                    {failure.fingerprint ?? 'Unavailable'}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </DataCard>
      </div>

      <details className="mt-6 rounded-lg border border-border-subtle p-4">
        <summary className="cursor-pointer text-xs font-medium">
          EdgeForge REST & WebSocket Integration Contract
        </summary>
        <p className="mt-2 text-xs text-text-muted">
          Active API routes powering the live dashboard:
        </p>
        <ul className="mt-3 space-y-1 font-mono text-[10px] text-text-subtle">
          {EXPECTED_ENDPOINTS.map((endpoint) => <li key={endpoint}>{endpoint}</li>)}
        </ul>
      </details>
    </div>
  )
}

export default LiveSimulationPage
