import { useSimStore, LOCATION_META } from '../../store/sim.store.js'
import clsx from 'clsx'

const BORDER = { blue:'border-blue-700/50', violet:'border-violet-700/50', amber:'border-amber-700/50' }
const TEXT   = { blue:'text-blue-400',      violet:'text-violet-400',      amber:'text-amber-400'      }
const BG     = { blue:'bg-blue-950/40',     violet:'bg-violet-950/40',     amber:'bg-amber-950/40'     }

export default function LocationStats() {
  const streams        = useSimStore((s) => s.streams)
  const running        = useSimStore((s) => s.running)
  const activeLocation = useSimStore((s) => s.activeLocation)
  const setLocation    = useSimStore((s) => s.setLocation)
  const stats          = useSimStore((s) => s.statsByLocation())

  return (
    <div className="grid grid-cols-4 gap-3">
      <button onClick={() => setLocation('all')}
        className={clsx('card p-3 text-left transition-all hover:border-brand-600/50',
          activeLocation === 'all' ? 'border-brand-600/70 bg-brand-950/30' : '')}>
        <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-1.5">All Locations</div>
        <div className="text-2xl font-bold text-white">{streams.length}</div>
        <div className="text-[10px] text-gray-500 mt-0.5">total streams</div>
        <div className="mt-2">
          {running
            ? <span className="text-[10px] text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 live-dot" />Publishing
              </span>
            : <span className="text-[10px] text-gray-500">Stopped</span>}
        </div>
      </button>
      {Object.entries(LOCATION_META).map(([loc, meta]) => {
        const s = stats[loc] || { total:0, plc:0, mes:0, erp:0, scada:0 }
        const c = meta.color
        return (
          <button key={loc} onClick={() => setLocation(loc)}
            className={clsx('card p-3 text-left transition-all', BORDER[c],
              activeLocation === loc ? `${BG[c]}` : 'hover:border-gray-600/70')}>
            <div className={clsx('text-[10px] uppercase tracking-widest mb-1.5 font-semibold', TEXT[c])}>
              {meta.label}
            </div>
            <div className="text-2xl font-bold text-white">{s.total}</div>
            <div className="text-[10px] text-gray-500 mt-0.5">{meta.subtitle}</div>
            <div className="flex gap-2 mt-2">
              {[['PLC','blue'],['MES','purple'],['ERP','amber'],['SCADA','emerald']].map(([src,clr]) => (
                <span key={src} className={`text-[9px] font-bold text-${clr}-400`}>{src} {s[src.toLowerCase()]||0}</span>
              ))}
            </div>
          </button>
        )
      })}
    </div>
  )
}
