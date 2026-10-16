import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

/**
 * Guided jury demo controller.
 * - 6 steps covering hero → scenario → run → failure → coverage → adaptive.
 * - Always skippable. "Exit guided mode" available at any point.
 * - Every step emits a smooth scroll to the target section.
 * - Step-specific action helpers set up a demo-able scenario, auto-run it, select a failure, apply recommendation.
 * - Pure React state; persists in memory only.
 */

/**
 * @typedef {{
 *   id: string,
 *   title: string,
 *   sectionId: string,
 *   description: string,
 *   cta?: string,
 *   hint?: string,
 *   auto?: boolean,
 * }} GuidedStep
 */

/** @type {GuidedStep[]} */
export const GUIDED_STEPS = [
  {
    id: 'welcome',
    title: '1/6 · Welcome',
    sectionId: 'hero',
    description: 'This is EDGEFORGE — an ADAS edge-case validation & failure-intelligence concept. The walkthrough covers: hero → scenario synthesis → illustrative run → failure triage → coverage → adaptive next-test.',
    cta: 'Start guided demo',
    hint: 'You can exit or skip at any time.',
    auto: true,
  },
  {
    id: 'setup_scenario',
    title: '2/6 · Compose a scenario',
    sectionId: 'scenario',
    description: 'The Scenario Lab lets us dial 7 axes. Use the controls (weather, lighting, traffic, road-user, occlusion, distance, ego speed) to build an edge case, then tap Run Scenario.',
    cta: 'Load example scenario',
    hint: 'Tappable — selects a hard scenario and scrolls to controls.',
  },
  {
    id: 'run_scenario',
    title: '3/6 · Illustrative simulation run',
    sectionId: 'scenario',
    description: 'Run the scenario to produce an illustrative perception outcome. The outcome feeds Failure Analysis, Coverage Explorer and the Adaptive module in one deterministic loop.',
    cta: 'Run illustrative scenario',
    hint: 'Produces a sample DemoRunResult used by downstream modules.',
  },
  {
    id: 'failure_triage',
    title: '4/6 · Failure triage',
    sectionId: 'analysis',
    description: 'Each illustrative failure lands in the register with severity, object class, failure type and replay status. Pick a record to open its detail pane, then Queue Replay to push it back into the Scenario Lab.',
    cta: 'Select the top-severity failure',
    hint: 'Highlights a FailureRecord in the register and opens the detail pane.',
  },
  {
    id: 'coverage',
    title: '5/6 · Coverage map',
    sectionId: 'coverage',
    description: 'Coverage Explorer shows where EDGEFORGE has looked. Tested / under-tested / failure-prone cells each feed a different signal into the next-test recommendation.',
    cta: 'Jump to coverage view',
    hint: 'Summaries + heatmap = quick projector view of where risk accumulates.',
  },
  {
    id: 'adaptive',
    title: '6/6 · Adaptive next-test',
    sectionId: 'next-test',
    description: 'Three signals — Failure History, Coverage Gaps, and Project-Defined Risk Priorities — are blended into a ranked next-test list. The #1 pick keeps the failure-region axes fixed and varies only the highest-signal parameters so we investigate around the illustrative failure.',
    cta: 'Apply top recommendation',
    hint: 'Wires the recommended scenario into the Scenario Lab.',
  },
]

/**
 * @typedef {Object} UseGuidedDemoReturn
 * @property {GuidedStep|null} current
 * @property {number} currentIndex
 * @property {boolean} active
 * @property {() => void} start
 * @property {(idx?: number) => void} goTo
 * @property {() => void} next
 * @property {() => void} prev
 * @property {() => void} exit
 * @property {(e?: unknown) => void} dismissBanner
 */

/**
 * @param {object} helpers
 * @property {(cfg: Partial<import('@/types').ScenarioConfig>) => void} [helpers.onScenarioChange]
 * @property {() => void|Promise<void>} [helpers.onRunScenario]
 * @property {(failureId: string|null) => void} [helpers.onSelectFailure]
 * @property {() => import('@/types').FailureRecord[]} [helpers.getFailures]
 * @property {(rec: import('@/types').NextTestRecommendation) => void} [helpers.onApplyRecommendation]
 * @property {() => import('@/types').NextTestRecommendation[]} [helpers.getRecommendations]
 * @returns {UseGuidedDemoReturn}
 */
export function useGuidedDemo(helpers = {}) {
  const [active, setActive] = useState(false)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [bannerOpen, setBannerOpen] = useState(false)
  const autoActionRef = useRef(false)

  const current = active ? GUIDED_STEPS[currentIndex] ?? null : null

  const scrollTo = useCallback((sectionId) => {
    if (typeof window === 'undefined') return
    requestAnimationFrame(() => {
      const el = document.getElementById(sectionId)
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }, [])

  const start = useCallback(() => {
    setActive(true)
    setCurrentIndex(0)
    setBannerOpen(true)
    scrollTo(GUIDED_STEPS[0].sectionId)
  }, [scrollTo])

  const exit = useCallback(() => {
    setActive(false)
    setCurrentIndex(0)
    setBannerOpen(false)
    autoActionRef.current = false
  }, [])

  const dismissBanner = useCallback(() => {
    setBannerOpen(false)
  }, [])

  const goTo = useCallback((idx = 0) => {
    const i = Math.max(0, Math.min(GUIDED_STEPS.length - 1, idx))
    setCurrentIndex(i)
    setBannerOpen(true)
    scrollTo(GUIDED_STEPS[i].sectionId)
  }, [scrollTo])

  const next = useCallback(async () => {
    const step = GUIDED_STEPS[currentIndex]
    if (!step) return
    if (step.id === 'setup_scenario') {
      helpers.onScenarioChange?.({
        weather: 'night_rain', lighting: 'night_unlit', trafficDensity: 'heavy',
        roadUser: 'pedestrian', occlusion: 'partial', distanceMeters: 32, egoSpeedKmh: 55,
      })
    }
    if (step.id === 'run_scenario') {
      await helpers.onRunScenario?.()
    }
    if (step.id === 'failure_triage') {
      const list = helpers.getFailures?.() ?? []
      const sevRank = { low: 0, medium: 1, high: 2, critical: 3 }
      const top = [...list].sort((a, b) => sevRank[b.severity] - sevRank[a.severity] || b.occurrenceCount - a.occurrenceCount)[0]
      helpers.onSelectFailure?.(top?.id ?? null)
    }
    if (step.id === 'adaptive') {
      const list = helpers.getRecommendations?.() ?? []
      if (list[0]) helpers.onApplyRecommendation?.(list[0])
    }
    const nextIdx = Math.min(GUIDED_STEPS.length - 1, currentIndex + 1)
    setCurrentIndex(nextIdx)
    setBannerOpen(true)
    scrollTo(GUIDED_STEPS[nextIdx].sectionId)
  }, [currentIndex, helpers, scrollTo])

  const prev = useCallback(() => {
    const prevIdx = Math.max(0, currentIndex - 1)
    setCurrentIndex(prevIdx)
    setBannerOpen(true)
    scrollTo(GUIDED_STEPS[prevIdx].sectionId)
  }, [currentIndex, scrollTo])

  // First step welcome scroll when toggling on.
  useEffect(() => {
    if (active && autoActionRef.current === false) {
      autoActionRef.current = true
    }
  }, [active])

  return useMemo(() => ({
    current, currentIndex, active, bannerOpen,
    start, goTo, next, prev, exit, dismissBanner,
  }), [
    current, currentIndex, active, bannerOpen,
    start, goTo, next, prev, exit, dismissBanner,
  ])
}
