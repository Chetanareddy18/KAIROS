import axios from 'axios'

export const API_BASE = import.meta.env.VITE_API_URL || '/api/v1'

export function getApiKey() {
  try { return localStorage.getItem('kairos_api_key') || import.meta.env.VITE_KAIROS_API_KEY || '' }
  catch { return import.meta.env.VITE_KAIROS_API_KEY || '' }
}

export function setApiKey(key) {
  try { key ? localStorage.setItem('kairos_api_key', key) : localStorage.removeItem('kairos_api_key') } catch { /* private mode */ }
}

export const api = axios.create({ baseURL: API_BASE, timeout: 300_000 })

api.interceptors.request.use(cfg => {
  const key = getApiKey()
  if (key) cfg.headers['X-API-Key'] = key
  return cfg
})

/** Human-readable error message from an axios error. */
export function errMsg(e) {
  if (!e) return ''
  if (e.response) {
    const d = e.response.data
    const detail = d?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map(x => x.msg).join('; ')
    return `HTTP ${e.response.status}`
  }
  if (e.code === 'ERR_NETWORK') return 'Cannot reach the KAIROS API — is the backend running on port 8000?'
  return e.message || String(e)
}
