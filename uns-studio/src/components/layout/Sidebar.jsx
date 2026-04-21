import { useState } from 'react'
import { useSimStore, LOCATION_META } from '../../store/sim.store.js'
import ScenarioModal from '../simulator/ScenarioModal.jsx'
import clsx from 'clsx'

const LOC_ICON  = { Frankfurt: 'fa-industry', Munich: 'fa-car', Ingolstadt: 'fa-hammer' }
const ACTIVE_BG = { blue: 'bg-blue-600', violet: 'bg-violet-600', amber: 'bg-amber-600' }

const SCENARIO_ACTIVE = {
  emerald: 'bg-emerald-700 text-white border-emerald-600',
  amber:   'bg-amber-700  text-white border-amber-600',
  red:     'bg-red-800    text-white border-red-700',
}
const SCENARIO_IDLE = 'border-gray-700 text-gray-400 hover:border-gray-600 hover:text-white'

export default function Sidebar() {
  const streams        = useSimStore((s) => s.streams)
  const activeLocation = useSimStore((s) => s.activeLocation)
  const setLocation    = useSimStore((s) => s.setLocation)
  const stats          = useSimStore((s) => s.statsByLocation())
  const scenarios      = useSimStore((s) => s.scenarios)
  const scenario       = useSimStore((s) => s.scenario)
  const setScenario    = useSimStore((s) => s.setScenario)

  const [previewScenario, setPreviewScenario] = useState(null)

  const openModal = (e, sc) => {
    e.stopPropagation()
    setPreviewScenario(sc)
  }
  const closeModal = () => setPreviewScenario(null)

  return (
    <>
      <aside className="w-60 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col h-full">

        {/* Logo */}
        <div className="h-14 flex items-center px-4 border-b border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center">
              <i className="fa-solid fa-tower-broadcast text-white text-xs" />
            </div>
            <div>
              <div className="text-white font-bold text-sm leading-none">UNS Simulator</div>
              <div className="text-gray-500 text-[10px] mt-0.5">IoTAuto GmbH</div>
            </div>
          </div>
        </div>

        {/* Locations */}
        <div className="px-3 pt-4 pb-2 flex-shrink-0">
          <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1 mb-2">
            Locations
          </div>

          <button
            onClick={() => setLocation('all')}
            className={clsx(
              'w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors mb-0.5',
              activeLocation === 'all'
                ? 'bg-brand-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            )}
          >
            <span className="flex items-center gap-2.5">
              <i className="fa-solid fa-globe w-4 text-center text-xs" />All Locations
            </span>
            <span className="text-[10px] opacity-70">{streams.length}</span>
          </button>

          {Object.entries(LOCATION_META).map(([loc, meta]) => {
            const s = stats[loc] || {}
            return (
              <button
                key={loc}
                onClick={() => setLocation(loc)}
                className={clsx(
                  'w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm font-medium transition-colors mb-0.5',
                  activeLocation === loc
                    ? `${ACTIVE_BG[meta.color] || 'bg-brand-600'} text-white`
                    : 'text-gray-400 hover:text-white hover:bg-gray-800'
                )}
              >
                <span className="flex items-center gap-2.5">
                  <i className={`fa-solid ${LOC_ICON[loc] || 'fa-building'} w-4 text-center text-xs`} />
                  <span className="flex-1 text-left">
                    <span className="block leading-none">{meta.label}</span>
                    <span className="text-[10px] opacity-60 font-normal">{meta.subtitle}</span>
                  </span>
                </span>
                <span className="text-[10px] opacity-70">{s.total || 0}</span>
              </button>
            )
          })}
        </div>

        {/* Fault Scenarios */}
        <div className="flex-1 overflow-y-auto px-3 pb-3">
          <div className="text-[10px] font-bold text-gray-500 uppercase tracking-widest px-1 mb-2 mt-1">
            Fault Scenarios
          </div>

          <div className="space-y-1">
            {scenarios.map((sc) => {
              const isActive = scenario === sc.id
              return (
                <div key={sc.id} className="group relative">
                  <button
                    onClick={() => setScenario(sc.id)}
                    className={clsx(
                      'w-full text-left px-2.5 py-2 pr-8 rounded-lg border text-xs transition-all',
                      isActive
                        ? (SCENARIO_ACTIVE[sc.color] || 'bg-brand-700 text-white border-brand-600')
                        : SCENARIO_IDLE
                    )}
                  >
                    <div className="font-medium leading-snug">{sc.label}</div>
                    {isActive && (
                      <div className="text-[10px] opacity-70 mt-1 leading-relaxed line-clamp-2">
                        {sc.description}
                      </div>
                    )}
                  </button>

                  {/* Info button */}
                  <button
                    onClick={(e) => openModal(e, sc)}
                    title="View scenario guide"
                    className={clsx(
                      'absolute right-1.5 top-1/2 -translate-y-1/2',
                      'w-5 h-5 rounded flex items-center justify-center transition-all',
                      'opacity-0 group-hover:opacity-100',
                      isActive
                        ? 'opacity-60 hover:opacity-100 text-white/70 hover:text-white hover:bg-white/10'
                        : 'text-gray-500 hover:text-white hover:bg-gray-700'
                    )}
                  >
                    <i className="fa-solid fa-circle-info text-[10px]" />
                  </button>
                </div>
              )
            })}
          </div>
        </div>

        {/* External links */}
        <div className="px-3 pb-3 border-t border-gray-800 pt-3 flex-shrink-0">
          <a
            href="https://pipeline.iotdemozone.com"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs text-gray-500
                       hover:text-gray-300 hover:bg-gray-800 transition-colors"
          >
            <i className="fa-solid fa-arrow-up-right-from-square text-[10px]" />
            Pipeline Studio
          </a>
          <a
            href="https://selfserv.iotdemozone.com"
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2 px-2.5 py-2 rounded-lg text-xs text-gray-500
                       hover:text-gray-300 hover:bg-gray-800 transition-colors"
          >
            <i className="fa-solid fa-arrow-up-right-from-square text-[10px]" />
            Self-Serve Portal
          </a>
        </div>

      </aside>

      {/* Modal portal */}
      {previewScenario && (
        <ScenarioModal scenario={previewScenario} onClose={closeModal} />
      )}
    </>
  )
}
