import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useDemoState } from '@/hooks/useDemoState.js'
import { useGuidedDemo } from '@/hooks/useGuidedDemo.js'
import { Navbar, PageShell, SiteFooter, GuidedDemoBar, ModeSelector } from '@/components/layout/index.js'
import { ErrorBoundary } from '@/components/common/ErrorBoundary.jsx'
import { HeroSection } from '@/components/hero/HeroSection.jsx'
import { PlatformOverview } from '@/components/overview/PlatformOverview.jsx'
import { WorkflowSection } from '@/components/workflow/WorkflowSection.jsx'
import { ScenarioLab } from '@/components/scenario/ScenarioLab.jsx'
import { FailureAnalysis } from '@/components/analysis/FailureAnalysis.jsx'
import { CoverageExplorer } from '@/components/coverage/CoverageExplorer.jsx'
import { AdaptiveRecommendation } from '@/components/adaptive/AdaptiveRecommendation.jsx'
import { BenefitsSection } from '@/components/shared/BenefitsSection.jsx'
import { buildAdaptiveRecommendations } from '@/components/adaptive/adaptiveEngine.js'
import { LiveSimulationPage } from '@/pages/LiveSimulationPage.jsx'

function readModeFromUrl() {
  if (typeof window === 'undefined') return 'static'
  return new URLSearchParams(window.location.search).get('mode') === 'live'
    ? 'live'
    : 'static'
}

const scrollTo = (id) => {
  if (typeof window === 'undefined') return
  const el = document.getElementById(id)
  if (el) {
    requestAnimationFrame(() =>
      el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    )
    if (window.history?.replaceState) {
      window.history.replaceState(null, '', `#${id}`)
    }
  }
}

export function HomePage() {
  const demo = useDemoState()
  const [mode, setMode] = useState(readModeFromUrl)

  const changeMode = useCallback((nextMode) => {
    setMode(nextMode)
    if (typeof window === 'undefined') return

    const nextUrl = new URL(window.location.href)
    if (nextMode === 'live') nextUrl.searchParams.set('mode', 'live')
    else nextUrl.searchParams.delete('mode')
    window.history.pushState(null, '', nextUrl)
  }, [])

  useEffect(() => {
    const syncMode = () => setMode(readModeFromUrl())
    window.addEventListener('popstate', syncMode)
    return () => window.removeEventListener('popstate', syncMode)
  }, [])

  const recommendations = useMemo(
    () =>
      buildAdaptiveRecommendations({
        latestResult: demo.lastRun,
        failureRecords: demo.dataset.failures,
        coverageItems: demo.dataset.coverage,
        selectedFailureId: demo.selectedFailureId,
        currentScenario: demo.currentScenario,
      }),
    [demo.lastRun, demo.dataset.failures, demo.dataset.coverage, demo.selectedFailureId, demo.currentScenario]
  )

  const guided = useGuidedDemo({
    onScenarioChange: demo.onScenarioChange,
    onRunScenario: demo.onRunScenario,
    onSelectFailure: demo.onSelectFailure,
    getFailures: () => demo.dataset.failures,
    onApplyRecommendation: (rec) => {
      const cfg = rec?.scenario ?? rec?.recommendedScenario
      if (cfg) demo.onScenarioChange(cfg)
      scrollTo('scenario')
    },
    getRecommendations: () => recommendations.prioritized,
  })

  const handleRunNext = useCallback(
    (cfg) => {
      demo.onScenarioChange(cfg)
      setTimeout(() => scrollTo('scenario'), 60)
    },
    [demo]
  )

  return (
    <PageShell>
      {mode === 'static' ? <Navbar brandName="EDGEFORGE" /> : null}
      <ModeSelector mode={mode} onChange={changeMode} />

      <main id="main" className="min-h-[calc(100vh-140px)]">
        <ErrorBoundary onReset={() => scrollTo('hero')}>
          {mode === 'live' ? (
            <LiveSimulationPage onSwitchToStatic={() => changeMode('static')} />
          ) : (
            <>
              <HeroSection
                onPrimaryAction={() => scrollTo('scenario')}
                onSecondaryAction={() => scrollTo('workflow')}
              />
              <PlatformOverview />
              <WorkflowSection />
              <ScenarioLab
                scenario={demo.currentScenario}
                lastRun={demo.lastRun}
                isRunning={demo.isRunning}
                recentRuns={demo.dataset.runs}
                onScenarioChange={demo.onScenarioChange}
                onRun={demo.onRunScenario}
                onReset={demo.onResetScenario}
                onNavigate={(target) => {
                  if (target === 'failure-analysis') scrollTo('failure-analysis')
                  if (target === 'scenario-lab' || target === 'scenario') scrollTo('scenario')
                }}
              />
              <FailureAnalysis
                failures={demo.dataset.failures}
                selectedFailureId={demo.selectedFailureId}
                onSelectFailure={demo.onSelectFailureId}
                onReplay={(f) => {
                  if (f?.scenarioConfig) demo.onScenarioChange(f.scenarioConfig)
                  scrollTo('scenario')
                }}
                onNavigate={(target) => {
                  if (target === 'coverage') scrollTo('coverage')
                  if (target === 'scenario-lab') scrollTo('scenario')
                }}
              />
              <CoverageExplorer
                runs={demo.dataset.runs}
                failures={demo.dataset.failures}
                onApplyScenario={(cfg) => {
                  demo.onScenarioChange(cfg)
                  scrollTo('scenario')
                }}
                onNavigate={(target) => {
                  if (target === 'failure-analysis') scrollTo('failure-analysis')
                  if (target === 'scenario-lab') scrollTo('scenario')
                }}
              />
              <AdaptiveRecommendation
                latestResult={demo.lastRun}
                failureRecords={demo.dataset.failures}
                coverageItems={demo.dataset.coverage}
                selectedFailureId={demo.selectedFailureId}
                currentScenario={demo.currentScenario}
                onRunNextScenario={handleRunNext}
              />
              <BenefitsSection />
            </>
          )}
        </ErrorBoundary>
      </main>

      <SiteFooter mode={mode} />

      {mode === 'static' ? (
        <GuidedDemoBar
          current={guided.current}
          currentIndex={guided.currentIndex}
          active={guided.active}
          onStart={guided.start}
          onNext={guided.next}
          onPrev={guided.prev}
          onGoTo={guided.goTo}
          onExit={guided.exit}
        />
      ) : null}
    </PageShell>
  )
}

export default HomePage
