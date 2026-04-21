import { useState } from 'react'
import { useSimStore } from '../../store/sim.store.js'
import clsx from 'clsx'

const SOURCES = ['PLC','MES','ERP','SCADA']

export default function LiveFeed() {
  const feed        = useSimStore((s) => s.feed)
  const running     = useSimStore((s) => s.running)
  const selectedMsg = useSimStore((s) => s.selectedMsg)
  const selectMsg   = useSimStore((s) => s.selectMsg)
  const [filter, setFilter] = useState('')

  const visible = filter ? feed.filter((m) => m.source === filter) : feed

  return (
    <div className="h-full flex flex-col bg-gray-900">
      <div className="flex-shrink-0 flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <span className="text-xs font-semibold text-gray-300 flex items-center gap-2">
          <i className="fa-solid fa-satellite-dish text-brand-400 text-xs" />Live Feed
        </span>
        <span className="text-[10px] text-gray-500">{visible.length}</span>
      </div>

      <div className="flex-shrink-0 flex gap-1 px-2 py-1.5 border-b border-gray-800">
        <button onClick={() => setFilter('')}
          className={clsx('px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
            !filter ? 'bg-brand-600 text-white' : 'text-gray-500 hover:text-gray-300')}>
          All
        </button>
        {SOURCES.map((src) => (
          <button key={src} onClick={() => setFilter(filter === src ? '' : src)}
            className={clsx(`badge-${src}`, 'px-1.5 py-0.5 rounded text-[10px] font-bold transition-all',
              filter === src ? 'ring-1 ring-white/30' : 'opacity-70 hover:opacity-100')}>
            {src}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto font-mono">
        {visible.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-600 text-xs gap-2">
            {running
              ? <><i className="fa-solid fa-circle-notch fa-spin text-xl" /><span>Waiting…</span></>
              : <><i className="fa-solid fa-stop text-xl" /><span>Press Start All</span></>}
          </div>
        )}
        {visible.map((m, i) => (
          <button key={i} onClick={() => selectMsg(selectedMsg === m ? null : m)}
            className={clsx('w-full text-left px-3 py-1.5 border-b border-gray-800/60 text-[11px] transition-colors',
              m.status && m.status !== 'OK' ? 'bg-red-950/20' : '',
              selectedMsg === m ? 'bg-brand-950/40' : 'hover:bg-gray-800/30')}>
            <div className="flex items-center justify-between gap-1 mb-0.5">
              <span className="text-gray-600">{m.ts}</span>
              <span className={`badge-${m.source}`}>{m.source}</span>
            </div>
            <div className="text-gray-300 truncate">{m.label}</div>
            <div className="flex items-center justify-between mt-0.5">
              <span className={clsx('font-bold', m.status && m.status !== 'OK' ? 'text-red-400' : 'text-emerald-400')}>
                {m.value || '—'}
              </span>
              {m.status && m.status !== 'OK' && (
                <span className="text-[9px] text-red-500 font-bold">{m.status}</span>
              )}
            </div>
          </button>
        ))}
      </div>

      {selectedMsg && (
        <div className="flex-shrink-0 border-t border-gray-700 p-3 bg-gray-950 max-h-48 overflow-y-auto">
          <div className="text-[10px] text-gray-500 mb-1 flex items-center gap-1.5">
            <i className="fa-solid fa-code text-brand-500" />Topic
          </div>
          <div className="text-[9px] text-brand-300 font-mono mb-2 break-all leading-relaxed">{selectedMsg.topic}</div>
          <div className="text-[10px] text-gray-500 mb-1">Value</div>
          <div className="text-xs font-bold text-emerald-400 mb-2">{selectedMsg.value}</div>
          <button onClick={() => selectMsg(null)} className="text-[10px] text-gray-600 hover:text-gray-400">
            <i className="fa-solid fa-xmark mr-1" />dismiss
          </button>
        </div>
      )}
    </div>
  )
}
