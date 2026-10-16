import React from 'react'
import { ScenarioLab } from '@/components/scenario/index.js'

/**
 * @typedef {Object} ScenarioLabPageProps
 * @property {import('@/types').PageDemoState} demo
 * @property {(tab: string) => void} [onNavigate]
 */

export function ScenarioLabPage({ demo, onNavigate }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 md:px-6">
      <ScenarioLab
        eyebrow="SCENARIO LAB"
        title="SCENARIO VALIDATION CONSOLE"
        description="Configure controlled scenario conditions and execute an illustrative perception validation run."
        scenario={demo.currentScenario}
        lastRun={demo.lastRun}
        isRunning={demo.isRunning}
        recentRuns={demo.dataset.runs}
        onScenarioChange={demo.onScenarioChange}
        onRun={demo.onRunScenario}
        onReset={demo.onResetScenario}
        onNavigate={onNavigate}
      />
    </div>
  )
}

export default ScenarioLabPage
