import { create } from 'zustand'
import { api, createWebSocket } from '../services/api.js'

// Location colour map matches uns_model.py LOCATION_COLORS
export const LOCATION_META = {
  Frankfurt:  { color: 'blue',   label: 'Frankfurt',  subtitle: 'Paint Shop Line 1' },
  Munich:     { color: 'violet', label: 'Munich',     subtitle: 'Assembly Plant'    },
  Ingolstadt: { color: 'amber',  label: 'Ingolstadt', subtitle: 'Press + Body Shop' },
}

export const useSimStore = create((set, get) => ({
  // ── connection state ──────────────────────────────────────────────────────
  running:        false,
  mqttConnected:  false,
  totalPublished: 0,
  rate:           0,
  uptime:         0,
  scenario:       'normal',

  // ── data ──────────────────────────────────────────────────────────────────
  streams:   [],   // [{id,label,topic,area,source,source_detail,unit,interval,running,value,last_ts,pub_count,location}]
  scenarios: [],   // [{id,label,description,color,fault_key,affected,location}]
  feed:      [],   // last 200 messages

  // ── ui state ──────────────────────────────────────────────────────────────
  activeLocation: 'all',   // 'all' | 'Frankfurt' | 'Munich' | 'Ingolstadt'
  activeArea:     '',
  activeSource:   '',
  feedFilter:     '',
  selectedMsg:    null,
  wsReady:        false,

  _ws: null,

  // ── bootstrap ─────────────────────────────────────────────────────────────
  init: async () => {
    try {
      const data = await api.status()
      get()._applyStatus(data)
    } catch (e) {
      console.error('init failed', e)
    }
    get()._connectWS()
  },

  _applyStatus: (data) => {
    set((s) => {
      const streamMap = {}
      if (s.streams.length) s.streams.forEach((st) => { streamMap[st.id] = st })

      const streams = (data.streams || []).map((st) => ({
        ...streamMap[st.id],
        ...st,
      }))

      return {
        running:        data.running        ?? s.running,
        mqttConnected:  data.mqtt_connected ?? s.mqttConnected,
        totalPublished: data.total_published ?? s.totalPublished,
        rate:           data.rate           ?? s.rate,
        uptime:         data.uptime         ?? s.uptime,
        scenario:       data.scenario       ?? s.scenario,
        streams:        streams.length ? streams : s.streams,
        scenarios:      data.scenarios      || s.scenarios,
        feed:           data.recent_messages
                          ? [...data.recent_messages].reverse()
                          : s.feed,
      }
    })
  },

  _connectWS: () => {
    const existing = get()._ws
    if (existing) { try { existing.close() } catch {} }

    const ws = createWebSocket((ev) => get()._handleWS(ev))
    ws.onopen  = () => set({ wsReady: true })
    ws.onclose = () => {
      set({ wsReady: false })
      setTimeout(() => get()._connectWS(), 2500)
    }
    set({ _ws: ws })
  },

  _handleWS: (ev) => {
    if (ev.type === 'init')   { get()._applyStatus(ev); return }

    if (ev.type === 'stats') {
      set({
        running:        ev.running,
        mqttConnected:  ev.mqtt_connected,
        totalPublished: ev.total_published,
        rate:           ev.rate,
        uptime:         ev.uptime,
        scenario:       ev.scenario,
      })
      return
    }

    if (ev.type === 'message') {
      set((s) => {
        const streams = s.streams.map((st) =>
          st.id === ev.stream_id
            ? { ...st, value: ev.value, last_ts: Date.now() / 1000, pub_count: (st.pub_count || 0) + 1 }
            : st
        )
        const entry = { ts: ev.ts, label: ev.label, topic: ev.topic,
                        source: ev.source, value: ev.value, status: ev.status }
        const feed = [entry, ...s.feed].slice(0, 200)
        return { streams, feed }
      })
      return
    }

    if (ev.type === 'stream_update') {
      set((s) => ({
        streams: s.streams.map((st) =>
          st.id === ev.id ? { ...st, running: ev.running } : st
        ),
      }))
      return
    }

    if (ev.type === 'scenario_change') { set({ scenario: ev.scenario }); return }
    if (ev.type === 'control')         { set({ running: ev.running });   return }
  },

  // ── actions ───────────────────────────────────────────────────────────────
  start:       async () => { await api.start();  set({ running: true  }) },
  stop:        async () => { await api.stop();   set({ running: false }) },

  toggleStream: async (id, isRunning) => {
    isRunning ? await api.stopStream(id) : await api.startStream(id)
    set((s) => ({
      streams: s.streams.map((st) =>
        st.id === id ? { ...st, running: !isRunning } : st
      ),
    }))
  },

  setScenario: async (id) => {
    await api.setScenario(id)
    set({ scenario: id })
  },

  setLocation: (loc) => set({ activeLocation: loc, activeArea: '' }),
  setArea:     (a)   => set({ activeArea: a }),
  setSource:   (s)   => set({ activeSource: s }),
  setFeedFilter:(f)  => set({ feedFilter: f }),
  selectMsg:   (m)   => set({ selectedMsg: m }),

  // ── derived helpers ───────────────────────────────────────────────────────
  visibleStreams: () => {
    const { streams, activeLocation, activeArea, activeSource } = get()
    return streams.filter((s) => {
      if (activeLocation !== 'all' && s.location !== activeLocation) return false
      if (activeArea   && s.area   !== activeArea)   return false
      if (activeSource && s.source !== activeSource) return false
      return true
    })
  },

  areasForLocation: () => {
    const { streams, activeLocation } = get()
    const seen = new Set()
    const out  = []
    streams.forEach((s) => {
      if (activeLocation === 'all' || s.location === activeLocation) {
        if (!seen.has(s.area)) { seen.add(s.area); out.push(s.area) }
      }
    })
    return out
  },

  affectedIds: () => {
    const { scenarios, scenario } = get()
    return new Set(scenarios.find((s) => s.id === scenario)?.affected ?? [])
  },

  statsByLocation: () => {
    const { streams } = get()
    const result = {}
    streams.forEach((s) => {
      const loc = s.location || 'Unknown'
      if (!result[loc]) result[loc] = { total: 0, active: 0, plc: 0, mes: 0, erp: 0, scada: 0 }
      result[loc].total++
      if (s.running) result[loc].active++
      const src = (s.source || '').toLowerCase()
      if (src === 'plc')   result[loc].plc++
      if (src === 'mes')   result[loc].mes++
      if (src === 'erp')   result[loc].erp++
      if (src === 'scada') result[loc].scada++
    })
    return result
  },
}))
