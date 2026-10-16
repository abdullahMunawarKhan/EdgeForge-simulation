import React from 'react'
import {
  WEATHER_LABEL,
  LIGHTING_LABEL,
  TRAFFIC_LABEL,
  ROAD_USER_LABEL,
  OCCLUSION_LABEL,
  OUTCOME_LABEL,
} from '@/data/labels.js'

/**
 * @typedef {Object} SimulationPreviewProps
 * @property {import('@/types').ScenarioConfig} scenario
 * @property {import('@/types').DemoRunResult|null} [lastRun]
 * @property {boolean} [isRunning]
 */

/**
 * Realistic vector actor rendering for each ADAS object class
 * @param {{ roadUser: import('@/types').RoadUserClass, className?: string }} props
 */
function ActorGraphic({ roadUser, className = '' }) {
  switch (roadUser) {
    case 'pedestrian':
      return (
        <svg viewBox="0 0 64 120" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Head */}
          <circle cx="32" cy="16" r="10" />
          {/* Torso & Jacket */}
          <path d="M22 30 C22 28, 42 28, 42 30 L46 64 C46 66, 42 68, 38 68 L36 68 L36 90 L40 114 C40 116, 36 118, 32 118 C28 118, 24 116, 24 114 L28 90 L28 68 L26 68 C22 68, 18 66, 18 64 Z" />
          {/* Left Arm */}
          <path d="M22 32 L12 56 C11 58, 13 60, 15 60 L18 60 L24 42 Z" opacity="0.85" />
          {/* Right Arm */}
          <path d="M42 32 L52 56 C53 58, 51 60, 49 60 L46 60 L40 42 Z" opacity="0.85" />
        </svg>
      )
    case 'bicycle':
      return (
        <svg viewBox="0 0 120 100" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Wheels */}
          <circle cx="26" cy="74" r="20" fill="none" stroke="currentColor" strokeWidth="4" />
          <circle cx="94" cy="74" r="20" fill="none" stroke="currentColor" strokeWidth="4" />
          <circle cx="26" cy="74" r="4" />
          <circle cx="94" cy="74" r="4" />
          {/* Frame */}
          <path d="M26 74 L54 74 L78 48 L46 48 Z" fill="none" stroke="currentColor" strokeWidth="4" />
          <path d="M54 74 L46 48 L48 38" fill="none" stroke="currentColor" strokeWidth="4" />
          <path d="M94 74 L76 34 L84 34" fill="none" stroke="currentColor" strokeWidth="4" />
          {/* Rider Head & Helmet */}
          <circle cx="64" cy="18" r="9" />
          <path d="M56 16 C56 10, 72 10, 74 16 Z" />
          {/* Rider Body & Arms */}
          <path d="M62 26 L52 46 L76 42 L80 36 Z" />
          <path d="M50 48 L56 68 L64 74" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
        </svg>
      )
    case 'motorcycle':
      return (
        <svg viewBox="0 0 130 95" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Big Wheels */}
          <circle cx="28" cy="68" r="22" fill="none" stroke="currentColor" strokeWidth="6" />
          <circle cx="102" cy="68" r="22" fill="none" stroke="currentColor" strokeWidth="6" />
          {/* Motorcycle Body & Engine */}
          <path d="M30 68 L60 68 L92 50 L102 68 L80 72 L45 74 Z" opacity="0.9" />
          <path d="M48 52 L78 38 L96 40 L88 56 Z" />
          {/* Headlight */}
          <polygon points="102,42 116,40 114,48 102,46" fill="#FDE047" />
          {/* Rider Helmet & Body */}
          <circle cx="62" cy="16" r="10" />
          <path d="M58 24 L46 46 L74 44 L86 40 Z" />
        </svg>
      )
    case 'passenger_vehicle':
      return (
        <svg viewBox="0 0 140 80" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Car Profile / Rear-Quarter */}
          <path d="M8 58 C8 52, 14 48, 24 48 L36 48 L54 24 C58 20, 68 18, 92 18 L114 26 C124 30, 134 42, 136 52 L136 62 C136 66, 132 68, 126 68 L118 68 C118 60, 110 54, 102 54 C94 54, 86 60, 86 68 L50 68 C50 60, 42 54, 34 54 C26 54, 18 60, 18 68 L12 68 C9 68, 8 64, 8 58 Z" />
          {/* Windows */}
          <path d="M56 26 L80 26 L80 44 L44 44 Z" fill="#0B1220" opacity="0.8" />
          <path d="M86 26 L108 30 L118 44 L86 44 Z" fill="#0B1220" opacity="0.8" />
          {/* Wheels */}
          <circle cx="34" cy="68" r="13" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          <circle cx="102" cy="68" r="13" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          {/* Tail light & Headlight */}
          <rect x="8" y="49" width="6" height="8" rx="2" fill="#EF4444" />
          <rect x="130" y="50" width="6" height="8" rx="2" fill="#FDE047" />
        </svg>
      )
    case 'heavy_truck':
      return (
        <svg viewBox="0 0 160 90" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Cargo Container */}
          <rect x="6" y="10" width="102" height="62" rx="3" opacity="0.9" />
          <line x1="26" y1="10" x2="26" y2="72" stroke="#0B1220" strokeWidth="2" opacity="0.4" />
          <line x1="56" y1="10" x2="56" y2="72" stroke="#0B1220" strokeWidth="2" opacity="0.4" />
          <line x1="86" y1="10" x2="86" y2="72" stroke="#0B1220" strokeWidth="2" opacity="0.4" />
          {/* Cab */}
          <path d="M110 24 L138 24 L154 48 L154 74 L110 74 Z" />
          <polygon points="116,28 136,28 148,46 116,46" fill="#0B1220" opacity="0.85" />
          {/* Wheels */}
          <circle cx="22" cy="76" r="11" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          <circle cx="44" cy="76" r="11" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          <circle cx="88" cy="76" r="11" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          <circle cx="138" cy="76" r="11" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          {/* Cab light */}
          <rect x="150" y="52" width="4" height="10" fill="#FDE047" />
        </svg>
      )
    case 'emergency_vehicle':
      return (
        <svg viewBox="0 0 150 85" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Ambulance body */}
          <path d="M10 22 L105 22 L120 32 L144 48 L144 70 L10 70 Z" opacity="0.95" />
          {/* Red Cross */}
          <rect x="52" y="34" width="20" height="6" rx="1" fill="#EF4444" />
          <rect x="59" y="27" width="6" height="20" rx="1" fill="#EF4444" />
          {/* Windshield */}
          <polygon points="106,26 118,34 136,46 106,46" fill="#0B1220" opacity="0.8" />
          {/* Wheels */}
          <circle cx="34" cy="72" r="12" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          <circle cx="118" cy="72" r="12" fill="#1E293B" stroke="currentColor" strokeWidth="3" />
          {/* Flashing Emergency Light Beacon */}
          <rect x="56" y="14" width="16" height="7" rx="2" fill="#3B82F6" className="animate-pulse" />
          <rect x="72" y="14" width="16" height="7" rx="2" fill="#EF4444" className="animate-pulse" />
        </svg>
      )
    case 'construction_vehicle':
      return (
        <svg viewBox="0 0 150 90" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Loader Body */}
          <rect x="36" y="32" width="62" height="42" rx="3" fill="#EAB308" />
          <path d="M50 16 L84 16 L94 32 L44 32 Z" fill="#CA8A04" />
          <polygon points="52,18 80,18 88,30 48,30" fill="#0B1220" opacity="0.8" />
          {/* Arm & Bucket */}
          <path d="M94 48 L126 34 L142 62 L124 72 Z" fill="#713F12" />
          {/* Tracks / Large Wheels */}
          <circle cx="48" cy="74" r="14" fill="#1E293B" stroke="currentColor" strokeWidth="4" />
          <circle cx="86" cy="74" r="14" fill="#1E293B" stroke="currentColor" strokeWidth="4" />
          {/* Hazard Beacon */}
          <circle cx="66" cy="12" r="4" fill="#F97316" className="animate-pulse" />
        </svg>
      )
    case 'animal':
      return (
        <svg viewBox="0 0 110 90" className={`w-full h-full drop-shadow-md ${className}`} fill="currentColor">
          {/* Deer / Large Animal Silhouette */}
          <path d="M84 14 L88 4 M84 14 L94 8 M84 14 L90 22 L80 26 L76 18 Z" />
          <path d="M76 22 L68 38 L30 38 C24 38, 20 44, 20 52 L20 62 L24 84 L30 84 L34 64 L56 64 L58 84 L64 84 L68 54 L76 46 Z" />
          <path d="M68 54 L72 84 L76 84 L74 54" />
          <path d="M20 52 L14 48 L18 58 Z" />
        </svg>
      )
    default:
      return (
        <div className="w-12 h-16 rounded bg-text/80 flex items-center justify-center text-[9px] font-mono text-bg">
          ACTOR
        </div>
      )
  }
}

/**
 * Main Illustrative Simulation Preview component
 * @param {SimulationPreviewProps} props
 */
export function SimulationPreview({ scenario, lastRun, isRunning = false }) {
  const { weather, lighting, trafficDensity, roadUser, occlusion, distanceMeters, egoSpeedKmh } = scenario

  // Perspective calculation: distance 5m (close) -> 100m (far)
  const clampedDist = Math.max(5, Math.min(100, distanceMeters ?? 35))
  const normDist = (clampedDist - 5) / 95 // 0.0 (near) to 1.0 (far)

  // Scale: Near (1.45) to Far (0.45)
  const actorScale = 1.45 - normDist * 1.0
  // Vertical position: Near (bottom of road 72%) to Far (horizon 41%)
  const actorBottomPct = 26 + (1 - normDist) * 36
  // Horizontal lane position
  const actorLeftPct = 50 + (normDist - 0.5) * 8

  // Estimated TTC = distance (m) / (egoSpeed (km/h) * 0.27778 m/s)
  const speedMps = Math.max(1, (egoSpeedKmh ?? 50) * (1000 / 3600))
  const ttcSeconds = (clampedDist / speedMps).toFixed(1)

  // Environment styling helpers
  const getSkyStyle = () => {
    switch (lighting) {
      case 'day_direct':
        return 'bg-gradient-to-b from-[#1E3A8A] via-[#0284C7] to-[#38BDF8]'
      case 'day_overcast':
        return 'bg-gradient-to-b from-[#1E293B] via-[#334155] to-[#64748B]'
      case 'dawn_dusk':
        return 'bg-gradient-to-b from-[#311042] via-[#7C2D12] to-[#F59E0B]'
      case 'night_streetlight':
        return 'bg-gradient-to-b from-[#030712] via-[#0B1329] to-[#111C3A]'
      case 'night_unlit':
        return 'bg-gradient-to-b from-[#020408] via-[#050B14] to-[#0A101D]'
      case 'tunnel_entry':
      case 'tunnel_exit':
        return 'bg-gradient-to-b from-[#090D16] via-[#111827] to-[#1E293B]'
      default:
        return 'bg-gradient-to-b from-[#070B14] via-[#0F172A] to-[#1E293B]'
    }
  }

  // Outcome evaluation state for perception overlay
  const hasOutcome = Boolean(lastRun?.outcome)
  const outcomeKind = lastRun?.outcome?.kind
  const isMissed = outcomeKind === 'false_negative'
  const isClassMismatch = outcomeKind === 'classification_error'
  const isRangeError = outcomeKind === 'range_error'
  const isLatencyBreach = outcomeKind === 'latency_breach'
  const isDetectedOk = outcomeKind === 'detected_ok'
  const isPassed = outcomeKind === 'detected_ok'

  return (
    <div className="relative flex flex-col w-full overflow-hidden rounded-lg border border-border bg-bg shadow-panel">
      {/* Top HUD Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle bg-surface/90 px-3 py-2 text-[11px] backdrop-blur-sm">
        <div className="flex items-center gap-2">
          <span className="chip chip-accent flex items-center gap-1.5 font-mono text-[9px] font-bold">
            <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
            ILLUSTRATIVE PREVIEW
          </span>
          <span className="text-text-subtle font-mono text-[10px] hidden sm:inline">
            CAMERA_FRONT_120° · 1920×1080 · 30 FPS · RAW SENSOR STREAM
          </span>
        </div>

        {/* Telemetry quick readout */}
        <div className="flex items-center gap-3 font-mono text-[10px]">
          <div className="flex items-center gap-1 text-text-muted">
            <span className="text-text-subtle">SPD:</span>
            <span className="font-bold text-accent">{egoSpeedKmh} km/h</span>
          </div>
          <div className="flex items-center gap-1 text-text-muted">
            <span className="text-text-subtle">RANGE:</span>
            <span className="font-bold text-text">{distanceMeters} m</span>
          </div>
          <div className="flex items-center gap-1 text-text-muted">
            <span className="text-text-subtle">TTC:</span>
            <span className={`font-bold ${Number(ttcSeconds) < 2.0 ? 'text-danger' : 'text-text'}`}>
              {ttcSeconds}s
            </span>
          </div>
        </div>
      </div>

      {/* Main Simulation Canvas Viewport */}
      <div className="relative aspect-[16/9] w-full select-none overflow-hidden">
        {/* Sky Background */}
        <div className={`absolute inset-0 transition-colors duration-500 ${getSkyStyle()}`} />

        {/* Sun / Moon / Horizon Glow */}
        {lighting === 'day_direct' && (
          <div className="absolute top-4 right-16 h-14 w-14 rounded-full bg-yellow-100 opacity-90 blur-[1px] shadow-[0_0_50px_rgba(253,224,71,0.8)]" />
        )}
        {lighting === 'dawn_dusk' && (
          <div className="absolute top-12 right-24 h-16 w-16 rounded-full bg-orange-400 opacity-80 blur-[2px] shadow-[0_0_60px_rgba(249,115,22,0.9)]" />
        )}
        {(lighting === 'night_streetlight' || lighting === 'night_clear') && (
          <div className="absolute top-5 right-12 h-8 w-8 rounded-full bg-slate-200 opacity-80 blur-[1px] shadow-[0_0_20px_rgba(255,255,255,0.4)]" />
        )}

        {/* Tunnel Architecture Overlay */}
        {(lighting === 'tunnel_entry' || lighting === 'tunnel_exit') && (
          <div className="absolute inset-0 z-10 pointer-events-none">
            <div className="absolute top-0 inset-x-0 h-16 bg-[#111827] border-b-4 border-[#374151] flex items-center justify-center">
              <span className="text-[10px] font-mono tracking-widest text-text-subtle">TUNNEL PORTAL · RESTRICTED SPEED ZONE</span>
            </div>
            <div className="absolute top-16 inset-x-0 flex justify-around px-8">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-2 w-8 bg-amber-200 shadow-[0_0_15px_rgba(251,191,36,0.8)] rounded-full" />
              ))}
            </div>
          </div>
        )}

        {/* Perspective Road Geometry */}
        <svg className="absolute inset-0 w-full h-full" viewBox="0 0 800 450" preserveAspectRatio="none">
          <defs>
            <linearGradient id="roadGradient" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stopColor="#0B1220" />
              <stop offset="100%" stopColor="#182234" />
            </linearGradient>
            <linearGradient id="headlightBeam" x1="50%" y1="100%" x2="50%" y2="0%">
              <stop offset="0%" stopColor="rgba(254, 240, 138, 0.45)" />
              <stop offset="65%" stopColor="rgba(254, 240, 138, 0.15)" />
              <stop offset="100%" stopColor="rgba(254, 240, 138, 0)" />
            </linearGradient>
            <radialGradient id="streetlightPool" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(253, 230, 138, 0.35)" />
              <stop offset="100%" stopColor="rgba(253, 230, 138, 0)" />
            </radialGradient>
          </defs>

          {/* Roadbed */}
          <polygon points="340,180 460,180 780,450 20,450" fill="url(#roadGradient)" />
          {/* Shoulders */}
          <polygon points="330,180 340,180 20,450 0,450" fill="#243048" />
          <polygon points="460,180 470,180 800,450 780,450" fill="#243048" />

          {/* Night Headlights Projection */}
          {(lighting === 'night_unlit' || weather === 'night_rain' || weather === 'night_clear') && (
            <polygon points="370,210 430,210 700,450 100,450" fill="url(#headlightBeam)" />
          )}

          {/* Streetlight Cones */}
          {lighting === 'night_streetlight' && (
            <>
              <ellipse cx="400" cy="240" rx="90" ry="25" fill="url(#streetlightPool)" />
              <ellipse cx="400" cy="330" rx="160" ry="40" fill="url(#streetlightPool)" />
            </>
          )}

          {/* Center Lines */}
          <line x1="400" y1="180" x2="400" y2="450" stroke="#F8FAFC" strokeWidth="4" strokeDasharray="16 16" opacity="0.75" />
          <line x1="370" y1="180" x2="240" y2="450" stroke="#E2E8F0" strokeWidth="3" strokeDasharray="12 14" opacity="0.6" />
          <line x1="430" y1="180" x2="560" y2="450" stroke="#E2E8F0" strokeWidth="3" strokeDasharray="12 14" opacity="0.6" />

          {/* Distance Calibration Marks */}
          <g opacity="0.4" stroke="#38BDF8" strokeWidth="1" strokeDasharray="4 4" fill="none">
            <line x1="358" y1="215" x2="442" y2="215" />
            <text x="446" y="218" fill="#38BDF8" fontSize="9" fontFamily="monospace">75m</text>
            <line x1="335" y1="260" x2="465" y2="260" />
            <text x="470" y="263" fill="#38BDF8" fontSize="10" fontFamily="monospace">50m</text>
            <line x1="295" y1="330" x2="505" y2="330" />
            <text x="512" y="334" fill="#38BDF8" fontSize="11" fontFamily="monospace">25m</text>
            <line x1="230" y1="410" x2="570" y2="410" />
            <text x="580" y="414" fill="#38BDF8" fontSize="12" fontFamily="monospace">10m</text>
          </g>
        </svg>

        {/* Ambient Traffic Indicators */}
        {trafficDensity !== 'empty' && (
          <div className="absolute inset-0 pointer-events-none">
            <div
              className="absolute text-slate-400 drop-shadow-sm transition-all duration-300"
              style={{ bottom: '48%', left: '33%', width: '42px', height: '26px' }}
            >
              <ActorGraphic roadUser="passenger_vehicle" className="text-slate-500 opacity-85" />
            </div>

            {(trafficDensity === 'moderate' || trafficDensity === 'heavy' || trafficDensity === 'gridlock') && (
              <div
                className="absolute text-slate-400 drop-shadow-sm transition-all duration-300"
                style={{ bottom: '38%', right: '27%', width: '56px', height: '32px' }}
              >
                <ActorGraphic roadUser="heavy_truck" className="text-slate-600 opacity-75" />
              </div>
            )}

            {(trafficDensity === 'heavy' || trafficDensity === 'gridlock') && (
              <>
                <div
                  className="absolute text-slate-400 transition-all duration-300"
                  style={{ bottom: '60%', left: '42%', width: '28px', height: '18px' }}
                >
                  <ActorGraphic roadUser="passenger_vehicle" className="text-slate-600 opacity-60" />
                </div>
                <div
                  className="absolute text-slate-400 transition-all duration-300"
                  style={{ bottom: '54%', right: '38%', width: '32px', height: '20px' }}
                >
                  <ActorGraphic roadUser="passenger_vehicle" className="text-slate-500 opacity-65" />
                </div>
              </>
            )}
          </div>
        )}

        {/* Target Road User Actor Container */}
        <div
          className="absolute z-20 transition-all duration-500 ease-out"
          style={{
            bottom: `${actorBottomPct}%`,
            left: `${actorLeftPct}%`,
            transform: `translate(-50%, 0) scale(${actorScale})`,
            transformOrigin: 'bottom center',
            width: roadUser === 'pedestrian' ? '40px' : roadUser === 'bicycle' ? '60px' : '72px',
            height: roadUser === 'pedestrian' ? '70px' : roadUser === 'bicycle' ? '55px' : '45px',
          }}
        >
          {/* Target Actor Graphic */}
          <div className="relative w-full h-full">
            <ActorGraphic
              roadUser={roadUser}
              className={`transition-colors ${
                lighting === 'night_unlit' ? 'text-slate-200' : 'text-slate-100'
              }`}
            />

            {/* Occlusion Object Masking Actor */}
            {occlusion !== 'none' && (
              <div
                className="absolute bottom-0 right-0 z-30 pointer-events-none rounded-sm border border-slate-700 bg-slate-900/95 shadow-lg flex items-center justify-center text-[7px] text-text-subtle font-mono"
                style={{
                  width:
                    occlusion === 'partial' ? '45%' :
                    occlusion === 'substantial' ? '75%' : '95%',
                  height: '85%',
                  transform: 'translateX(20%)',
                }}
              >
                <div className="truncate px-0.5 text-center">
                  {occlusion === 'partial' ? 'BARRIER' : 'PARKED VEH'}
                </div>
              </div>
            )}

            {/* Ground Truth Bounding Box */}
            <div className="absolute -inset-1 rounded border border-cyan-400/60 pointer-events-none">
              <span className="absolute -top-3.5 left-0 rounded bg-cyan-950/90 px-1 py-0.2 text-[8px] font-mono font-bold text-cyan-300 border border-cyan-500/40 whitespace-nowrap">
                GT: {ROAD_USER_LABEL[roadUser]} · {distanceMeters}m
              </span>
            </div>

            {/* Illustrative Perception Model Prediction Overlay */}
            {hasOutcome && !isRunning && (
              <div
                className={`absolute -inset-2 rounded pointer-events-none transition-all duration-300 ${
                  isDetectedOk
                    ? 'border-2 border-accent bg-accent/10 shadow-[0_0_15px_rgba(52,211,153,0.3)]'
                    : isMissed
                    ? 'border-2 border-dashed border-danger bg-danger/10 shadow-[0_0_15px_rgba(248,113,113,0.3)]'
                    : isClassMismatch
                    ? 'border-2 border-warning bg-warning/10 shadow-[0_0_15px_rgba(251,146,60,0.3)]'
                    : isRangeError
                    ? 'border-2 border-yellow-400 bg-yellow-400/10'
                    : 'border-2 border-danger bg-danger/10'
                }`}
              >
                {/* Result Pill Badge */}
                <div
                  className={`absolute -bottom-5 left-1/2 -translate-x-1/2 whitespace-nowrap rounded px-1.5 py-0.5 text-[8.5px] font-mono font-bold shadow-md border ${
                    isDetectedOk
                      ? 'bg-accent text-[#05120C] border-accent'
                      : isMissed
                      ? 'bg-danger text-white border-danger'
                      : isClassMismatch
                      ? 'bg-warning text-[#0B1220] border-warning'
                      : 'bg-yellow-400 text-[#0B1220] border-yellow-400'
                  }`}
                >
                  {isDetectedOk
                    ? `DETECTED · ${Math.round((lastRun?.outcome?.confidence ?? 0.95) * 100)}%`
                    : isMissed
                    ? 'MISSED DETECTION (FN)'
                    : isClassMismatch
                    ? `PRED: ${ROAD_USER_LABEL[lastRun?.outcome?.detectedClass] || 'UNKNOWN'}`
                    : isRangeError
                    ? `RANGE ERR: ${lastRun?.outcome?.distanceEstimateMeters}m`
                    : 'LATENCY BREACH'}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Atmospheric Weather Overlay Effects */}
        {weather === 'fog' && (
          <div className="absolute inset-0 z-25 pointer-events-none bg-gradient-to-t from-slate-300/40 via-slate-400/50 to-slate-300/65 backdrop-blur-[2px] transition-opacity duration-300" />
        )}

        {(weather === 'rain' || weather === 'heavy_rain' || weather === 'night_rain') && (
          <div className="absolute inset-0 z-25 pointer-events-none overflow-hidden opacity-75">
            <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <pattern id="rainPattern" width="40" height="40" patternUnits="userSpaceOnUse">
                  <line x1="0" y1="0" x2="15" y2="35" stroke="#93C5FD" strokeWidth={weather === 'heavy_rain' ? '1.8' : '1.2'} opacity="0.6" />
                  <line x1="20" y1="5" x2="35" y2="40" stroke="#93C5FD" strokeWidth={weather === 'heavy_rain' ? '1.8' : '1.2'} opacity="0.5" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#rainPattern)" />
            </svg>
          </div>
        )}

        {weather === 'snow' && (
          <div className="absolute inset-0 z-25 pointer-events-none overflow-hidden opacity-85">
            <div className="absolute inset-0 bg-white/10" />
            <svg className="w-full h-full" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <pattern id="snowPattern" width="60" height="60" patternUnits="userSpaceOnUse">
                  <circle cx="10" cy="15" r="2.5" fill="#FFFFFF" opacity="0.8" />
                  <circle cx="35" cy="45" r="3" fill="#FFFFFF" opacity="0.75" />
                  <circle cx="50" cy="20" r="2" fill="#FFFFFF" opacity="0.9" />
                </pattern>
              </defs>
              <rect width="100%" height="100%" fill="url(#snowPattern)" />
            </svg>
          </div>
        )}

        {/* Perception HUD Overlay Card (Top Right) */}
        {hasOutcome && !isRunning && (
          <div className="absolute top-3 right-3 z-30 pointer-events-none rounded-md border border-border-subtle/80 bg-bg/85 p-2 backdrop-blur-md text-[9px] font-mono text-text-subtle shadow-lg max-w-[190px]">
            <div className="flex items-center justify-between border-b border-border-subtle/60 pb-1 text-[8.5px] font-bold text-accent">
              <span>ILLUSTRATIVE MODEL HUD</span>
              <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
            </div>
            <div className="mt-1 space-y-0.5">
              <div className="flex justify-between">
                <span>TARGET:</span>
                <span className="font-semibold text-text">{ROAD_USER_LABEL[roadUser]}</span>
              </div>
              <div className="flex justify-between">
                <span>CONFIDENCE:</span>
                <span className="font-semibold text-accent">{Math.round((lastRun?.outcome?.confidence ?? 0.85) * 100)}%</span>
              </div>
              <div className="flex justify-between">
                <span>TRUE RANGE:</span>
                <span className="font-semibold text-text">{distanceMeters} m</span>
              </div>
              <div className="flex justify-between">
                <span>ESTIMATE:</span>
                <span className="font-semibold text-text">{lastRun?.outcome?.distanceEstimateMeters ? `${lastRun.outcome.distanceEstimateMeters} m` : 'N/A'}</span>
              </div>
              <div className="flex justify-between">
                <span>LATENCY:</span>
                <span className="font-semibold text-text">{lastRun?.outcome?.latencyMs ?? 55} ms</span>
              </div>
              <div className="flex justify-between pt-0.5 border-t border-border-subtle/50 font-bold">
                <span>VERDICT:</span>
                <span className={isPassed ? 'text-accent' : 'text-danger'}>
                  {OUTCOME_LABEL[lastRun?.outcome?.kind] || 'EVALUATED'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Environmental Readout HUD (Bottom Left) */}
        <div className="absolute bottom-3 left-3 z-30 pointer-events-none rounded border border-border-subtle/60 bg-bg/80 px-2 py-1 backdrop-blur-sm text-[9px] font-mono text-text-subtle shadow hidden sm:block">
          <div className="flex items-center gap-2">
            <span>{WEATHER_LABEL[weather]}</span>
            <span>·</span>
            <span>{LIGHTING_LABEL[lighting]}</span>
            <span>·</span>
            <span>{OCCLUSION_LABEL[occlusion]} Occl</span>
          </div>
        </div>

        {/* Running Scan Animation */}
        {isRunning && (
          <div className="absolute inset-0 z-30 pointer-events-none">
            <div className="h-full w-full bg-accent/5 flex flex-col justify-between p-4">
              <div className="w-full h-1 bg-gradient-to-r from-transparent via-accent to-transparent animate-pulse" />
              <div className="chip chip-accent mx-auto animate-bounce font-mono text-xs shadow-lg">
                RUNNING SENSORY SIMULATION SCAN…
              </div>
              <div className="w-full h-1 bg-gradient-to-r from-transparent via-accent to-transparent animate-pulse" />
            </div>
          </div>
        )}

        {/* Camera Reticle Brackets */}
        <div className="absolute inset-3 pointer-events-none border border-border-subtle/40 rounded">
          <div className="absolute top-0 left-0 h-4 w-4 border-t-2 border-l-2 border-accent" />
          <div className="absolute top-0 right-0 h-4 w-4 border-t-2 border-r-2 border-accent" />
          <div className="absolute bottom-0 left-0 h-4 w-4 border-b-2 border-l-2 border-accent" />
          <div className="absolute bottom-0 right-0 h-4 w-4 border-b-2 border-r-2 border-accent" />
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-4 w-4 pointer-events-none">
            <div className="absolute top-1/2 inset-x-0 h-[1px] bg-accent/30" />
            <div className="absolute left-1/2 inset-y-0 w-[1px] bg-accent/30" />
          </div>
        </div>
      </div>

      {/* Bottom Status / Honest Disclosure Bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border-subtle bg-surface px-3 py-2 text-[10px] text-text-subtle">
        <div className="flex items-center gap-1.5 flex-wrap font-mono">
          <span className="font-semibold text-text-muted">SCENE CONFIG:</span>
          <span className="text-text">{WEATHER_LABEL[weather]}</span>
          <span>·</span>
          <span className="text-text">{LIGHTING_LABEL[lighting]}</span>
          <span>·</span>
          <span className="text-text">{TRAFFIC_LABEL[trafficDensity]} Traffic</span>
          <span>·</span>
          <span className="text-text">{OCCLUSION_LABEL[occlusion]} Occlusion</span>
        </div>
        <div className="italic text-text-subtle">
          Illustrative mock output · No live CARLA simulation or YOLO inference is running.
        </div>
      </div>
    </div>
  )
}

export default SimulationPreview
