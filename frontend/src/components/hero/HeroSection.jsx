import { useState } from 'react'
import { PageSection } from '@/components/layout/PageSection.jsx'

const SCENE_IMAGE = '/hero-adas-scene.jpg'

/**
 * @typedef {Object} HeroSectionProps
 * @property {string} [eyebrow]
 * @property {string} [title]
 * @property {string} [summary]
 * @property {string} [contextLabel]
 * @property {string} [imageSrc]
 * @property {() => void} [onPrimaryAction]
 * @property {() => void} [onSecondaryAction]
 * @property {string} [primaryLabel]
 * @property {string} [secondaryLabel]
 */

/**
 * @param {HeroSectionProps} props
 */
export function HeroSection({
  eyebrow = 'ADAS EDGE-CASE VALIDATION',
  title = 'Forge the edge cases. Find the failures.',
  summary = 'Failure-guided simulation testing for smarter ADAS perception validation.',
  contextLabel = 'KPIT SPARKLES 2027 • SIMULATION',
  imageSrc = SCENE_IMAGE,
  onPrimaryAction,
  onSecondaryAction,
  primaryLabel = 'Explore the Demo',
  secondaryLabel = 'See How It Works',
}) {
  const titleLines = title.split(/(?<=\.)\s+/).filter(Boolean)

  return (
    <PageSection id="hero" className="relative overflow-hidden pt-6 pb-10 md:pt-8 md:pb-12">
      <style>{HERO_MOTION_CSS}</style>

      <div className="pointer-events-none absolute -left-24 top-10 h-72 w-72 rounded-full bg-accent/[0.07] blur-3xl" aria-hidden />

      <div className="relative grid items-center gap-10 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.2fr)] lg:gap-8">
        <div className="relative z-10 max-w-xl space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip chip-accent">{eyebrow}</span>
            <span className="chip">{contextLabel}</span>
          </div>

          <div className="space-y-4">
            <h1 className="text-[2rem] font-semibold leading-[1.12] tracking-tight md:text-5xl md:leading-[1.08]">
              {titleLines.map((line) => (
                <span key={line} className="block">
                  {line}
                </span>
              ))}
            </h1>
            <p className="max-w-md text-sm leading-relaxed text-text-muted md:text-base">
              {summary}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <a href="#scenario" onClick={onPrimaryAction} className="btn btn-primary">
              {primaryLabel}
            </a>
            <a href="#workflow" onClick={onSecondaryAction} className="btn">
              {secondaryLabel}
            </a>
          </div>
        </div>

        <HeroPerceptionStage src={imageSrc} />
      </div>
    </PageSection>
  )
}

/**
 * Cinematic ADAS perception stage. Decorative only — not a live detector.
 * @param {{ src: string }} props
 */
function HeroPerceptionStage({ src }) {
  const [failed, setFailed] = useState(false)

  return (
    <div
      className="relative isolate min-h-[22rem] w-full sm:min-h-[28rem] lg:min-h-[36rem]"
      aria-hidden="true"
    >
      <div className="absolute inset-y-0 -right-4 left-0 overflow-hidden sm:-right-6 lg:-right-8">
        {!failed ? (
          <img
            src={src}
            alt=""
            className="absolute inset-0 h-full w-full scale-105 object-cover object-[68%_48%] opacity-70 saturate-[0.7] contrast-125"
            onError={() => setFailed(true)}
          />
        ) : (
          <div className="absolute inset-0 bg-bg-elevated" />
        )}

        <div className="absolute inset-0 bg-gradient-to-r from-bg via-bg/55 to-transparent max-lg:from-bg/80 max-lg:via-bg/25" />
        <div className="absolute inset-0 bg-gradient-to-t from-bg via-transparent to-bg/40" />
        <div className="absolute inset-0 bg-gradient-to-l from-bg/50 via-transparent to-transparent" />
        <div className="absolute inset-0 opacity-[0.18] mix-blend-screen grid-lines" />

        <svg
          className="absolute inset-0 h-full w-full"
          viewBox="0 0 900 620"
          preserveAspectRatio="xMidYMid slice"
          fill="none"
        >
          <path
            d="M 90 610 C 250 430 320 250 360 90"
            stroke="var(--color-accent)"
            strokeOpacity="0.22"
            strokeWidth="1.2"
          />
          <path
            d="M 810 610 C 650 430 560 250 510 90"
            stroke="var(--color-accent)"
            strokeOpacity="0.22"
            strokeWidth="1.2"
          />
          <path
            d="M 430 610 C 440 390 445 240 448 70"
            stroke="var(--color-accent)"
            strokeOpacity="0.16"
            strokeDasharray="6 10"
            strokeWidth="1"
          />
          <path
            d="M 80 470 Q 450 250 820 470"
            stroke="var(--color-accent)"
            strokeOpacity="0.28"
            strokeWidth="1.4"
          />
          <path
            d="M 150 510 Q 450 330 750 510"
            stroke="var(--color-accent)"
            strokeOpacity="0.12"
            strokeWidth="1"
          />
        </svg>

        <div className="ef-hero-scan pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-transparent via-accent/20 to-transparent" />

        <HudBox
          className="absolute left-[12%] top-[38%] w-[28%] max-w-[11.5rem]"
          tone="accent"
          title="PEDESTRIAN"
          rows={[
            ['DISTANCE', 'NEAR-FIELD'],
            ['CONFIDENCE', 'TRACKED'],
          ]}
        />

        <HudBox
          className="absolute right-[10%] top-[28%] w-[30%] max-w-[12.5rem]"
          tone="warning"
          title="VEHICLE"
          rows={[
            ['DISTANCE', 'LEAD LANE'],
            ['SCENARIO', 'NIGHT RAIN'],
          ]}
        />

        <div className="absolute bottom-4 left-4 right-4 flex items-end justify-between gap-3 sm:bottom-6 sm:left-6">
          <div className="space-y-1">
            <div className="field-label">Scenario</div>
            <div className="font-mono text-[11px] tracking-wide text-text">NIGHT · WET ROAD · URBAN</div>
          </div>
          <div className="chip chip-accent">Illustrative overlay</div>
        </div>
      </div>
    </div>
  )
}

/**
 * @param {{
 *   className?: string,
 *   tone?: 'accent' | 'warning',
 *   title: string,
 *   rows: Array<[string, string]>
 * }} props
 */
function HudBox({ className = '', tone = 'accent', title, rows }) {
  const box =
    tone === 'warning'
      ? 'border-warning/70 shadow-[0_0_18px_var(--color-warning-muted)]'
      : 'border-accent/70 shadow-[0_0_18px_var(--color-accent-muted)]'
  const label = tone === 'warning' ? 'text-warning' : 'text-accent'

  return (
    <div className={className}>
      <div className={`relative aspect-[5/4] border ${box}`}>
        <span className={`absolute -left-px -top-px h-1.5 w-1.5 bg-current ${label}`} />
        <span className={`absolute -right-px -top-px h-1.5 w-1.5 bg-current ${label}`} />
        <span className={`absolute -bottom-px -left-px h-1.5 w-1.5 bg-current ${label}`} />
        <span className={`absolute -bottom-px -right-px h-1.5 w-1.5 bg-current ${label}`} />
      </div>
      <div className="mt-2 space-y-0.5">
        <div className={`font-mono text-[10px] font-medium tracking-[0.16em] ${label}`}>{title}</div>
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-baseline justify-between gap-3 font-mono text-[10px] tracking-wide">
            <span className="text-text-subtle">{k}</span>
            <span className="text-text-muted">{v}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

const HERO_MOTION_CSS = `
  @keyframes ef-hero-scan {
    0% { transform: translateY(-30%); opacity: 0; }
    18% { opacity: 0.55; }
    82% { opacity: 0.35; }
    100% { transform: translateY(280%); opacity: 0; }
  }
  .ef-hero-scan {
    animation: ef-hero-scan 8s ease-in-out infinite;
  }
  @media (prefers-reduced-motion: reduce) {
    .ef-hero-scan { animation: none; opacity: 0.16; transform: none; }
  }
`

export default HeroSection
