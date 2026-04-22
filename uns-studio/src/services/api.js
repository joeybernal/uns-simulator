// Vite bakes these at build time from .env.production or shell env.
// Hard-coded production fallback ensures the app works even if env
// vars were missing at build time.
const PROD_API = 'https://sim-api.iotdemozone.com'
const PROD_WS  = 'wss://sim-api.iotdemozone.com'

export const API_URL = import.meta.env.VITE_API_URL || PROD_API
export const WS_URL  = import.meta.env.VITE_WS_URL  || PROD_WS

// Retrieve the stored API key from Zustand persisted state.
// We read it directly from localStorage to avoid a circular store dependency.
function _getApiKey() {
  try {
    const raw = localStorage.getItem('uns-sim-api-key')
    if (!raw) return ''
    const state = JSON.parse(raw)
    return state?.state?.apiKey || ''
  } catch {
    return ''
  }
}

async function req(path, opts = {}) {
  const key = _getApiKey()
  const headers = { 'Content-Type': 'application/json' }
  if (key) headers['X-API-Key'] = key
  const res = await fetch(`${API_URL}${path}`, { headers, ...opts })
  if (!res.ok) throw new Error(`${opts.method || 'GET'} ${path} -> ${res.status}`)
  return res.json()
}

export const api = {
  status:      ()   => req('/api/status'),
  start:       ()   => req('/api/start',               { method: 'POST' }),
  stop:        ()   => req('/api/stop',                { method: 'POST' }),
  reset:       ()   => req('/api/reset',               { method: 'POST' }),
  startStream: (id) => req(`/api/streams/${id}/start`, { method: 'POST' }),
  stopStream:  (id) => req(`/api/streams/${id}/stop`,  { method: 'POST' }),
  setScenario: (id) => req(`/api/scenario/${id}`,      { method: 'POST' }),
  // Aurora-specific
  batchStatus: ()   => req('/api/batch_status'),
  triggerDpp:  ()   => req('/api/trigger_dpp',         { method: 'POST' }),
  predemo:     ()   => req('/api/predemo'),
}

export function createWebSocket(onMessage) {
  const wsBase = WS_URL.replace(/^https/, 'wss').replace(/^http/, 'ws')
  const key    = _getApiKey()
  const url    = key ? `${wsBase}/ws?api_key=${encodeURIComponent(key)}` : `${wsBase}/ws`
  const ws     = new WebSocket(url)
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch {}
  }
  return ws
}
