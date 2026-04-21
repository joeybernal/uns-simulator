import { useSimStore } from '../../store/sim.store.js'

function fmtUp(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  return h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s`
}

export default function TopBar() {
  const running        = useSimStore((s) => s.running)
  const mqttConnected  = useSimStore((s) => s.mqttConnected)
  const totalPublished = useSimStore((s) => s.totalPublished)
  const rate           = useSimStore((s) => s.rate)
  const uptime         = useSimStore((s) => s.uptime)
  const scenario       = useSimStore((s) => s.scenario)
  const scenarios      = useSimStore((s) => s.scenarios)
  const wsReady        = useSimStore((s) => s.wsReady)
  const start          = useSimStore((s) => s.start)
  const stop           = useSimStore((s) => s.stop)
  const activeScenario = scenarios.find((s) => s.id === scenario)

  return (
    <header className="h-14 bg-gray-900 border-b border-gray-800 flex items-center px-5 gap-4 flex-shrink-0">
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${mqttConnected ? 'bg-emerald-400 live-dot' : 'bg-red-500'}`} />
        <span className={`text-xs font-medium ${mqttConnected ? 'text-emerald-400' : 'text-red-400'}`}>
          {mqttConnected ? 'MQTT' : 'MQTT Offline'}
        </span>
      </div>
      <div className="h-4 w-px bg-gray-700" />
      <div className="flex items-center gap-1.5 text-xs text-gray-500">
        <span className={`w-1.5 h-1.5 rounded-full ${wsReady ? 'bg-brand-400' : 'bg-gray-600'}`} />
        <span>WS</span>
      </div>
      <div className="hidden md:flex items-center gap-4 text-xs text-gray-400">
        <span>Rate: <b className="text-white">{rate} msg/s</b></span>
        <span>Total: <b className="text-white">{totalPublished.toLocaleString()}</b></span>
        {running && uptime > 0 && <span>Up: <b className="text-white">{fmtUp(uptime)}</b></span>}
      </div>
      {scenario !== 'normal' && activeScenario && (
        <div className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-900/40 border border-amber-700/50">
          <i className="fa-solid fa-bolt text-amber-400 text-[10px]" />
          <span className="text-[11px] text-amber-300 font-medium">{activeScenario.label}</span>
        </div>
      )}
      <div className="flex-1" />
      <button onClick={running ? stop : start}
        className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-sm font-bold transition-colors ${
          running ? 'bg-red-600 hover:bg-red-700 text-white' : 'bg-emerald-600 hover:bg-emerald-700 text-white'}`}>
        <i className={`fa-solid ${running ? 'fa-stop' : 'fa-play'} text-xs`} />
        {running ? 'Stop All' : 'Start All'}
      </button>
      <span className="hidden xl:block text-[10px] text-gray-600 font-mono">mqtt.iotdemozone.com</span>
    </header>
  )
}
