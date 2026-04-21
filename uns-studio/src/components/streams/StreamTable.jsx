import { useState, useMemo } from 'react'
import { useSimStore } from '../../store/sim.store.js'
import clsx from 'clsx'

function fmtAgo(ts) {
  const d = Math.floor(Date.now() / 1000 - ts)
  return d < 5 ? 'just now' : d < 60 ? `${d}s` : `${Math.floor(d/60)}m ago`
}
const LOC_DOT = { Frankfurt:'bg-blue-400', Munich:'bg-violet-400', Ingolstadt:'bg-amber-400' }

export default function StreamTable() {
  const running        = useSimStore((s) => s.running)
  const toggleStream   = useSimStore((s) => s.toggleStream)
  const visibleStreams  = useSimStore((s) => s.visibleStreams())
  const affected       = useSimStore((s) => s.affectedIds())
  const scenario       = useSimStore((s) => s.scenario)
  const activeLocation = useSimStore((s) => s.activeLocation)
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    if (!search) return visibleStreams
    const q = search.toLowerCase()
    return visibleStreams.filter((s) =>
      s.label.toLowerCase().includes(q) || s.topic.toLowerCase().includes(q) || (s.area||'').toLowerCase().includes(q)
    )
  }, [visibleStreams, search])

  const groups = useMemo(() => {
    const map = {}
    filtered.forEach((s) => {
      const loc = s.location || 'Unknown'
      if (!map[loc]) map[loc] = {}
      const area = s.area || 'General'
      if (!map[loc][area]) map[loc][area] = []
      map[loc][area].push(s)
    })
    return map
  }, [filtered])

  return (
    <div className="h-full flex flex-col">
      <div className="flex-shrink-0 px-3 py-2 border-b border-gray-800">
        <div className="relative">
          <i className="fa-solid fa-magnifying-glass absolute left-3 top-1/2 -translate-y-1/2 text-gray-500 text-xs" />
          <input value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="Search streams, topics, areas…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500" />
          {search && (
            <button onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300">
              <i className="fa-solid fa-xmark text-xs" />
            </button>
          )}
        </div>
      </div>

      <div className="flex-shrink-0 grid grid-cols-[1fr_80px_140px_56px_64px_72px] border-b border-gray-800 bg-gray-900/80">
        {['Stream / Topic','Source','Last Value','Every','Msgs',''].map((h, i) => (
          <div key={i} className="px-3 py-2 text-[10px] font-bold text-gray-500 uppercase tracking-wider">{h}</div>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto">
        {Object.entries(groups).map(([loc, areaMap]) => (
          <div key={loc}>
            {activeLocation === 'all' && (
              <div className="sticky top-0 z-20 px-3 py-1.5 bg-gray-800/90 border-y border-gray-700/50 flex items-center gap-2">
                <span className={clsx('w-2 h-2 rounded-full flex-shrink-0', LOC_DOT[loc] || 'bg-gray-500')} />
                <span className="text-xs font-bold text-gray-200">{loc}</span>
              </div>
            )}
            {Object.entries(areaMap).map(([area, aStreams]) => (
              <div key={area}>
                <div className="px-3 py-1 bg-gray-800/50 border-b border-gray-800">
                  <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">{area}</span>
                  <span className="text-gray-600 text-[10px] ml-2">{aStreams.length}</span>
                </div>
                {aStreams.map((s) => {
                  const isAff = affected.has(s.id) && scenario !== 'normal'
                  const val = s.value || ''
                  const valColor = isAff || val.includes('ALARM') ? 'text-red-400'
                                 : val.includes('WARN') ? 'text-amber-400' : 'text-emerald-400'
                  return (
                    <div key={s.id}
                      className={clsx('grid grid-cols-[1fr_80px_140px_56px_64px_72px] border-b border-gray-800/60',
                        'hover:bg-gray-800/30 transition-colors', isAff ? 'bg-red-950/20' : '')}>
                      <div className="px-3 py-2 flex items-start gap-2 min-w-0">
                        <span className={clsx('w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0',
                          !running ? 'bg-gray-700' : !s.running ? 'bg-gray-600'
                          : isAff ? 'bg-red-500 live-dot' : 'bg-emerald-500 live-dot')} />
                        <div className="min-w-0">
                          <div className="text-xs text-gray-200 font-medium truncate">{s.label}</div>
                          <div className="text-[9px] text-gray-600 font-mono truncate">{s.topic}</div>
                          {s.source_detail && <div className="text-[9px] text-gray-700 truncate">{s.source_detail}</div>}
                        </div>
                      </div>
                      <div className="px-3 py-2 flex items-center">
                        <span className={`badge-${s.source}`}>{s.source}</span>
                      </div>
                      <div className="px-3 py-2 flex flex-col justify-center">
                        <div className={clsx('text-xs font-mono font-bold', valColor)}>{val || '—'}</div>
                        {s.last_ts && <div className="text-[9px] text-gray-600">{fmtAgo(s.last_ts)}</div>}
                      </div>
                      <div className="px-3 py-2 flex items-center text-xs text-gray-500">{s.interval}s</div>
                      <div className="px-3 py-2 flex items-center justify-end text-xs text-gray-500 font-mono">
                        {(s.pub_count||0).toLocaleString()}
                      </div>
                      <div className="px-3 py-2 flex items-center justify-center">
                        <button onClick={() => toggleStream(s.id, s.running)}
                          className={clsx('px-2 py-0.5 rounded text-[10px] font-bold transition-colors',
                            s.running
                              ? 'bg-gray-700 text-gray-300 hover:bg-red-900/50 hover:text-red-400'
                              : 'bg-emerald-900/40 text-emerald-400 hover:bg-emerald-900/70')}>
                          {s.running ? 'Pause' : 'Resume'}
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        ))}
        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center h-48 text-gray-600 gap-2">
            <i className="fa-solid fa-filter text-2xl" />
            <span className="text-sm">No streams match current filters</span>
          </div>
        )}
      </div>

      <div className="flex-shrink-0 border-t border-gray-800 px-3 py-1.5 flex items-center gap-3 text-[10px] text-gray-600">
        <span><b className="text-gray-400">{filtered.length}</b> / {visibleStreams.length} streams</span>
        <span className="ml-auto">{visibleStreams.filter((s)=>s.running).length} active</span>
      </div>
    </div>
  )
}
