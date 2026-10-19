import assert from 'node:assert/strict'
import { after, test } from 'node:test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const vite = await createServer({
  root: frontendRoot,
  configFile: resolve(frontendRoot, 'vite.config.js'),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})
const { CoverageExplorer } = await vite.ssrLoadModule(
  '/src/components/coverage/CoverageExplorer.jsx',
)

after(async () => {
  await vite.close()
})

test('renders API run metrics, preserving zero and marking missing values unavailable', () => {
  const markup = renderToStaticMarkup(
    React.createElement(CoverageExplorer, {
      historyState: 'available',
      historyData: {
        runs: [
          {
            run_id: 'run-with-metrics',
            scenario_id: 'scenario-clear',
            scenario_metrics: {
              collision_count: 0,
              lane_invasion_count: 1,
              max_risk_score: 0,
              time_above_threshold: 0,
            },
          },
          {
            run_id: 'legacy-run',
            scenario_id: 'scenario-legacy',
          },
        ],
        failures: [],
        coverage: {},
      },
    }),
  )

  assert.match(markup, /Completed run evaluation metrics/)
  assert.match(markup, /run-with-metrics/)
  assert.match(markup, /legacy-run/)
  assert.match(markup, /Collisions/)
  assert.match(markup, /Peak risk/)
  assert.match(markup, /0\.00/)
  assert.match(markup, /0\.0 s/)
  assert.match(markup, /Unavailable/)
})

test('renders an empty history response without evaluation metrics', () => {
  const markup = renderToStaticMarkup(
    React.createElement(CoverageExplorer, {
      historyState: 'available',
      historyData: { runs: [], failures: [], coverage: {} },
    }),
  )

  assert.match(markup, /No completed runs are available/)
})
