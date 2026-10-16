import { useCallback, useEffect, useRef, useState } from 'react'
import { createLiveSimulationClient } from '@/services/liveSimulation.js'

const POLL_INTERVAL_MS = 5000

function readBackendUrl() {
  return import.meta.env.VITE_EDGEFORGE_API_URL?.trim() ?? ''
}

function readMessageSnapshot(message) {
  const parsed = JSON.parse(message)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('Live update must be a JSON object.')
  }
  return parsed.snapshot && typeof parsed.snapshot === 'object'
    ? parsed.snapshot
    : parsed
}

export function useLiveSimulation() {
  const baseUrl = readBackendUrl()
  const [connection, setConnection] = useState({
    state: baseUrl ? 'connecting' : 'not-configured',
    message: baseUrl
      ? 'Checking the configured backend…'
      : 'Set VITE_EDGEFORGE_API_URL to connect to a live backend.',
  })
  const [status, setStatus] = useState(null)
  const [snapshot, setSnapshot] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading] = useState(Boolean(baseUrl))
  const [refreshKey, setRefreshKey] = useState(0)
  const [reportMessage, setReportMessage] = useState('')
  const clientRef = useRef(null)

  const retry = useCallback(() => {
    setRefreshKey((current) => current + 1)
  }, [])

  const requestLatestReport = useCallback(async () => {
    const client = clientRef.current
    if (!client) {
      setReportMessage('Configure the backend URL before requesting a report.')
      return
    }
    try {
      await client.getReport()
      setReportMessage('Report response received from the backend.')
    } catch (error) {
      setReportMessage(error instanceof Error ? error.message : 'Report request failed.')
    }
  }, [])

  useEffect(() => {
    if (!baseUrl) {
      setLoading(false)
      setConnection({
        state: 'not-configured',
        message: 'Live data is unavailable until a backend URL is configured.',
      })
      return undefined
    }

    let stopped = false
    let socket = null
    let pollTimer = null
    let pollController = null
    let source = 'REST'
    let requestInProgress = false
    let client
    try {
      client = createLiveSimulationClient(baseUrl)
    } catch (error) {
      setLoading(false)
      setConnection({
        state: 'disconnected',
        message: error instanceof Error ? error.message : 'Invalid backend URL.',
      })
      return undefined
    }
    clientRef.current = client

    const refresh = async (initial = false) => {
      if (requestInProgress || stopped) return
      requestInProgress = true
      pollController?.abort()
      pollController = new AbortController()
      if (initial) setLoading(true)
      try {
        const result = await client.loadSnapshot(pollController.signal)
        if (stopped) return
        setStatus(result.status)
        setSnapshot(result.snapshot)
        setLastUpdated(new Date())
        setConnection({
          state: 'connected',
          source,
          message: source === 'WebSocket'
            ? 'Receiving live updates.'
            : 'Connected; refreshing from REST.',
        })
        setReportMessage('')
      } catch (error) {
        if (stopped || error?.name === 'AbortError') return
        setConnection({
          state: 'disconnected',
          source,
          message: error instanceof Error ? error.message : 'Backend request failed.',
        })
      } finally {
        requestInProgress = false
        if (initial && !stopped) setLoading(false)
      }
    }

    const startSocket = () => {
      try {
        socket = client.createWebSocket()
        socket.onopen = () => {
          if (stopped) return
          source = 'WebSocket'
          setConnection({
            state: 'connected',
            source,
            message: 'Receiving live updates.',
          })
        }
        socket.onmessage = (event) => {
          if (stopped) return
          try {
            const nextSnapshot = readMessageSnapshot(event.data)
            setSnapshot((previous) =>
              previous ? { ...previous, ...nextSnapshot } : nextSnapshot,
            )
            if (nextSnapshot.status !== undefined) setStatus(nextSnapshot.status)
            setLastUpdated(new Date())
            setConnection({
              state: 'connected',
              source: 'WebSocket',
              message: 'Receiving live updates.',
            })
          } catch (error) {
            setConnection({
              state: 'degraded',
              source: 'REST',
              message: error instanceof Error
                ? error.message
                : 'Received an invalid WebSocket update.',
            })
          }
        }
        socket.onerror = () => {
          if (stopped) return
          source = 'REST'
          setConnection((current) => ({
            ...current,
            state: current.state === 'connected' ? 'degraded' : current.state,
            source,
            message: current.state === 'connected'
              ? 'WebSocket unavailable; showing backend REST snapshots.'
              : 'WebSocket unavailable; checking the REST endpoint.',
          }))
        }
        socket.onclose = () => {
          if (stopped) return
          source = 'REST'
          setConnection((current) => ({
            ...current,
            state: current.state === 'disconnected' ? 'disconnected' : 'degraded',
            source,
            message: 'WebSocket closed; falling back to backend REST snapshots.',
          }))
        }
      } catch (error) {
        source = 'REST'
        setConnection((current) => ({
          ...current,
          state: current.state === 'connected' ? 'degraded' : current.state,
          source,
          message: error instanceof Error
            ? `${error.message} REST snapshots will still be checked.`
            : 'WebSocket unavailable; REST snapshots will still be checked.',
        }))
      }
    }

    refresh(true).then(startSocket)
    pollTimer = window.setInterval(() => refresh(false), POLL_INTERVAL_MS)

    return () => {
      stopped = true
      clientRef.current = null
      if (pollTimer !== null) window.clearInterval(pollTimer)
      pollController?.abort()
      if (socket && socket.readyState < 2) socket.close()
    }
  }, [baseUrl, refreshKey])

  return {
    connection,
    status,
    snapshot,
    lastUpdated,
    loading,
    retry,
    requestLatestReport,
    reportMessage,
    backendConfigured: Boolean(baseUrl),
  }
}

export default useLiveSimulation
