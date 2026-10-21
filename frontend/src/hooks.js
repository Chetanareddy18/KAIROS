import { useCallback, useEffect, useRef, useState } from 'react'
import { api, errMsg } from './api'

/** GET a resource, optionally re-polling every `interval` ms. */
export function useApi(path, { interval = 0, params, enabled = true } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(enabled)
  const key = JSON.stringify(params || {})
  const alive = useRef(true)

  const load = useCallback(async () => {
    if (!enabled || !path) return
    try {
      const r = await api.get(path, { params })
      if (alive.current) { setData(r.data); setError('') }
    } catch (e) {
      if (alive.current) setError(errMsg(e))
    } finally {
      if (alive.current) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key, enabled])

  useEffect(() => {
    alive.current = true
    load()
    if (!interval) return () => { alive.current = false }
    const id = setInterval(load, interval)
    return () => { alive.current = false; clearInterval(id) }
  }, [load, interval])

  return { data, error, loading, reload: load, setData }
}

/** Wrap an async action with busy/error state. */
export function useAction() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const run = useCallback(async (fn) => {
    setBusy(true); setError('')
    try { return await fn() }
    catch (e) { setError(errMsg(e)); return undefined }
    finally { setBusy(false) }
  }, [])
  return { busy, error, run, setError }
}
