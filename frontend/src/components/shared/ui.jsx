/**
 * Small UI helpers + utilities used across modules. Keep these stable so
 * parallel branches can safely depend on them.
 */

/**
 * @param {Object} p
 * @param {'ok'|'warn'|'danger'|'neutral'} p.kind
 * @param {import('react').ReactNode} p.children
 */
export function StatusPill({ kind, children }) {
  const k =
    kind === 'ok' ? 'chip-accent' :
    kind === 'warn' ? 'chip-warning' :
    kind === 'danger' ? 'chip-danger' : ''
  return <span className={`chip ${k}`}>{children}</span>
}

/**
 * @param {{ label: string, value: string }} p
 */
export function DimensionChip({ label, value }) {
  return (
    <span className="chip">
      <span className="text-text-subtle">{label}:</span>
      <span className="text-text">{value}</span>
    </span>
  )
}

/**
 * @param {{ cfg: Partial<import('@/types').ScenarioConfig> }} p
 */
export function ScenarioChips({ cfg }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {cfg.weather ? <DimensionChip label="Weather" value={cfg.weather} /> : null}
      {cfg.lighting ? <DimensionChip label="Lighting" value={cfg.lighting} /> : null}
      {cfg.trafficDensity ? <DimensionChip label="Traffic" value={cfg.trafficDensity} /> : null}
      {cfg.roadUser ? <DimensionChip label="Road user" value={cfg.roadUser} /> : null}
      {cfg.occlusion ? <DimensionChip label="Occlusion" value={cfg.occlusion} /> : null}
      {typeof cfg.distanceMeters === 'number' ? <DimensionChip label="Distance" value={`${cfg.distanceMeters} m`} /> : null}
      {typeof cfg.egoSpeedKmh === 'number' ? <DimensionChip label="Ego speed" value={`${cfg.egoSpeedKmh} km/h`} /> : null}
    </div>
  )
}

/**
 * @param {{ title: string, description: string, accentLabel?: string }} p
 */
export function EmptyPlaceholder({ title, description, accentLabel = 'Placeholder' }) {
  return (
    <div className="panel p-6 text-center">
      <span className="chip chip-accent mx-auto">{accentLabel}</span>
      <h4 className="mt-3 text-sm font-semibold">{title}</h4>
      <p className="mt-1 text-xs text-text-muted">{description}</p>
    </div>
  )
}

import {
  formatScenarioSignature,
  summarizeFailure,
  summarizeRun,
  uid,
  nowISO,
} from '@/data/utils.js'

export {
  formatScenarioSignature,
  summarizeFailure,
  summarizeRun,
  uid,
  nowISO,
}

