import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'

export interface Loadable<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

export function useApi<T>(path: string | null): Loadable<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(!!path)
  const [tick, setTick] = useState(0)
  const seq = useRef(0)
  useEffect(() => {
    if (!path) return
    const mine = ++seq.current
    setLoading(true)
    api
      .get<T>(path)
      .then((d) => {
        if (mine === seq.current) {
          setData(d)
          setError(null)
        }
      })
      .catch((e: Error) => {
        if (mine === seq.current) setError(e.message)
      })
      .finally(() => {
        if (mine === seq.current) setLoading(false)
      })
  }, [path, tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, loading, reload }
}
