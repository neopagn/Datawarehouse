import { createContext, useContext, useEffect, useState } from 'react'
import { ApiError, fetchScreen, type Screen, type ScreenPayload } from './api'
import type { Scope } from './scope-logic'

export interface WarehouseStatus {
  code: string | null
  message: string | null
  elapsed: number | null
}

export const StatusContext = createContext<(status: WarehouseStatus) => void>(() => undefined)

const WEEK_DEBOUNCE_MS = 250

export interface ScreenState<S extends Screen> {
  payload: ScreenPayload<S> | null
  error: ApiError | null
  loading: boolean
  retry: () => void
}

/** One screen of the warehouse; a failed load clears the figures rather than leaving old ones under a new filter. */
export function useScreen<S extends Screen>(screen: S, scope: Scope, week: number | undefined, runId: number): ScreenState<S> {
  const report = useContext(StatusContext)
  const [payload, setPayload] = useState<ScreenPayload<S> | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    // Dragging the week slider must not queue one warehouse query per step.
    const timer = setTimeout(() => {
      fetchScreen(screen, { ...scope, week }, runId, controller.signal)
        .then((next) => {
          setPayload(next)
          setError(null)
          setLoading(false)
          report({ code: null, message: null, elapsed: next.elapsed_seconds })
        })
        .catch((reason: Error) => {
          if (reason.name === 'AbortError') return
          const failure = reason instanceof ApiError ? reason : new ApiError('connection', 'Không gọi được API.')
          setPayload(null)
          setError(failure)
          setLoading(false)
          report({ code: failure.code, message: failure.message, elapsed: null })
        })
    }, week === undefined ? 0 : WEEK_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [screen, scope, week, runId, attempt, report])

  return { payload, error, loading, retry: () => setAttempt((value) => value + 1) }
}
