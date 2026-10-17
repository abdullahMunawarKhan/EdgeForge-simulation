import { useCallback, useEffect, useState } from 'react'
import { createLiveSimulationClient } from '@/services/liveSimulation.js'

const REFRESH_INTERVAL_MS = 5000

export function useSimulationHistory() {
  const baseUrl = import.meta.env.VITE_EDGEFORGE_API_URL?.trim() ?? ''
  const [history, setHistory] = useState({
    data: null,
    recommendations: null,
    error: null,
    state: baseUrl ? 'loading' : 'demo',
  })
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    if (!baseUrl) {
      setHistory({
        data: null,
        recommendations: null,
        error: null,
        state: 'demo',
      })
      return undefined
    }

    const controller = new AbortController()
    let active = true

    const refresh = async () => {
      try {
        const client = createLiveSimulationClient(baseUrl)
        const [data, ranked] = await Promise.all([
          client.getHistory(controller.signal),
          client.getRecommendations(controller.signal),
        ])
        if (active) {
          setHistory({
            data,
            recommendations: ranked,
            error: null,
            state: 'available',
          })
        }
      } catch (error) {
        if (!active || controller.signal.aborted) return
        setHistory((current) => ({
          ...current,
          error: error instanceof Error ? error.message : 'History request failed.',
          state: 'error',
        }))
      }
    }

    void refresh()
    const interval = window.setInterval(refresh, REFRESH_INTERVAL_MS)
    return () => {
      active = false
      controller.abort()
      window.clearInterval(interval)
    }
  }, [baseUrl, refreshKey])

  const executeRecommendation = useCallback(async (recommendation) => {
    if (!baseUrl) throw new Error('Configure the EdgeForge backend before execution.')
    const result = await createLiveSimulationClient(baseUrl).executeRecommendation(
      recommendation,
    )
    setRefreshKey((current) => current + 1)
    return result
  }, [baseUrl])

  return { ...history, executeRecommendation }
}
