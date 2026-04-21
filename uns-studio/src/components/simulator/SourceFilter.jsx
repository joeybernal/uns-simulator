import { useSimStore } from '../../store/sim.store.js'
import clsx from 'clsx'

const SOURCES = ['PLC','MES','ERP','SCADA']

export default function SourceFilter() {
  const activeSource = useSimStore((s) => s.activeSource)
  const setSource    = useSimStore((s) => s.setSource)
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[10px] text-gray-500 font-medium">Source:</span>
      <button onClick={() => setSource('')}
        className={clsx('px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
          !activeSource ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
        All
      </button>
      {SOURCES.map((src) => (
        <button key={src} onClick={() => setSource(activeSource === src ? '' : src)}
          className={clsx(`badge-${src}`, 'px-2 py-0.5 rounded text-[10px] font-bold transition-all',
            activeSource === src ? 'ring-1 ring-white/40' : 'opacity-75 hover:opacity-100')}>
          {src}
        </button>
      ))}
    </div>
  )
}
