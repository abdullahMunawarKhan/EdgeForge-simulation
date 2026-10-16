import React from 'react'
import { CoverageExplorer } from '@/components/coverage/index.js'

/**
 * @typedef {Object} CoverageExplorerPageProps
 * @property {import('@/types').PageDemoState} demo
 * @property {(tab: string) => void} [onNavigate]
 */

export function CoverageExplorerPage({ demo, onNavigate }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 md:px-6">
      <CoverageExplorer
        eyebrow="SCENARIO COVERAGE EXPLORER"
        title="SCENARIO-SPACE COVERAGE INTELLIGENCE"
        description="Explore tested, under-tested and failure-prone regions of the illustrative scenario space across multi-dimensional validation slices."
        coverageItems={demo.dataset.coverage}
        runs={demo.dataset.runs}
        failures={demo.dataset.failures}
        onApplyScenario={(cfg) => {
          demo.onScenarioChange(cfg)
          if (onNavigate) {
            onNavigate('scenario-lab')
          }
        }}
        onNavigate={onNavigate}
      />
    </div>
  )
}

export default CoverageExplorerPage
