import React from 'react'
import { FailureAnalysis } from '@/components/analysis/index.js'

/**
 * @typedef {Object} FailureAnalysisPageProps
 * @property {import('@/types').PageDemoState} demo
 * @property {(tab: string) => void} [onNavigate]
 */

export function FailureAnalysisPage({ demo, onNavigate }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 md:px-6">
      <FailureAnalysis
        eyebrow="FAILURE ANALYSIS"
        title="PERCEPTION VALIDATION INCIDENT CONSOLE"
        description="Inspect perception failures by comparing Simulator Ground Truth against Illustrative Model Predictions. Every failure is categorized into Missed Detection, False Positive, Poor Localization, or Confidence Degradation with deterministic root-cause attribution."
        failures={demo.dataset.failures}
        selectedFailureId={demo.selectedFailureId}
        onSelectFailure={demo.onSelectFailure}
        onReplay={(f) => {
          demo.onScenarioChange(f.scenarioConfig)
          if (onNavigate) {
            onNavigate('scenario-lab')
          }
        }}
        onNavigate={onNavigate}
      />
    </div>
  )
}

export default FailureAnalysisPage
