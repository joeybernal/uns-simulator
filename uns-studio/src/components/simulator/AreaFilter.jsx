import { useSimStore } from '../../store/sim.store.js'
import clsx from 'clsx'

export default function AreaFilter() {
  const areas      = useSimStore((s) => s.areasForLocation())
  const activeArea = useSimStore((s) => s.activeArea)
  const setArea    = useSimStore((s) => s.setArea)
  if (!areas.length) return null
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] text-gray-500 font-medium">Area:</span>
      <button onClick={() => setArea('')}
        className={clsx('px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
          !activeArea ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
        All
      </button>
      {areas.map((a) => (
        <button key={a} onClick={() => setArea(a)}
          className={clsx('px-2 py-0.5 rounded text-[10px] font-medium transition-colors',
            activeArea === a ? 'bg-brand-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700')}>
          {a}
        </button>
      ))}
    </div>
  )
}
