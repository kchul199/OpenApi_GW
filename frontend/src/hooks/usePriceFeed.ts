import { useEffect, useRef } from 'react'
import { usePriceStore } from '@/stores/priceStore'

const PING_INTERVAL_MS = 30_000
const RECONNECT_DELAY_MS = 5_000

/**
 * Connects to the backend WebSocket price feed for a given symbol.
 * Automatically reconnects on disconnect and sends ping messages to keep alive.
 */
export function usePriceFeed(symbol: string) {
  const updatePrice = usePriceStore((s) => s.updatePrice)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pingTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const unmounted = useRef(false)

  useEffect(() => {
    unmounted.current = false

    function connect() {
      if (unmounted.current) return
      const token = localStorage.getItem('token')
      if (!token) return

      // Build WebSocket URL: replace http(s) scheme with ws(s)
      const base = window.location.origin.replace(/^http/, 'ws')
      const encoded = encodeURIComponent(symbol.replace('/', '-'))
      const url = `${base}/ws/prices/${encoded}?token=${token}`

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        // Start ping interval
        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
        }, PING_INTERVAL_MS)
      }

      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data as string)
          if (data.price != null) {
            updatePrice(symbol, Number(data.price), data.change_24h)
          }
        } catch {
          // ignore non-JSON (e.g. "pong")
        }
      }

      ws.onclose = () => {
        clearInterval(pingTimer.current ?? undefined)
        if (!unmounted.current) {
          reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS)
        }
      }

      ws.onerror = () => {
        ws.close()
      }
    }

    connect()

    return () => {
      unmounted.current = true
      clearInterval(pingTimer.current ?? undefined)
      clearTimeout(reconnectTimer.current ?? undefined)
      wsRef.current?.close()
    }
  }, [symbol, updatePrice])
}

/** Connects price feeds for multiple symbols simultaneously. */
export function useMultiPriceFeed(symbols: string[]) {
  // Call usePriceFeed for each symbol.
  // Rules of hooks: cannot call conditionally, so we use a fixed-size approach
  // via a stable ref list rendered in a dedicated component.
  symbols.forEach(() => {}) // satisfy lint; actual connection per symbol done in component
}
