import { useState, useRef, useEffect } from 'react'
import { runDemoReset } from '../../services/pipeline-api.js'
import clsx from 'clsx'

/**
 * DemoResetModal
 * Opens with a confirmation prompt, then runs the full demo reset
 * with a live step-by-step log and a summary on completion.
 */
export default function DemoResetModal({ onClose }) {
  const [phase, setPhase] = useState('confirm')  // 'confirm' | 'running' | 'done' | 'error'
  const [log,   setLog]   = useState([])
  const [summary, setSummary] = useState(null)
  const [error,   setError]   = useState(null)
  const logRef = useRef(null)

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log])

  function addLog(msg, type) {
    setLog(prev => [...prev, { msg, type, id: Date.now() + Math.random() }])
  }

  async function handleRun() {
    setPhase('running')
    setLog([])
    try {
      const result = await runDemoReset(addLog)
      setSummary(result)
      setPhase('done')
    } catch (e) {
      setError(e.message)
      setPhase('error')
    }
  }

  const lineColor = {
    section: 'text-brand-400 font-semibold mt-2',
    ok:      'text-emerald-400',
    warn:    'text-amber-400',
    info:    'text-gray-300',
  }

  const lineIcon = {
    section: '▸',
    ok:      '✓',
    warn:    '⚠',
    info:    '·',
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[520px] max-h-[85vh] bg-gray-900 border border-gray-700 rounded-xl shadow-2xl flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-brand-600/20 flex items-center justify-center">
              <i className="fa-solid fa-rotate text-brand-400 text-sm" />
            </div>
            <div>
              <div className="text-white font-semibold text-sm">Demo Reset</div>
              <div className="text-gray-500 text-[11px]">Pipeline Studio · IoTAuto GmbH</div>
            </div>
          </div>
          {phase !== 'running' && (
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-lg flex items-center justify-center text-gray-500
                         hover:text-white hover:bg-gray-700 transition-colors"
            >
              <i className="fa-solid fa-xmark text-xs" />
            </button>
          )}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto min-h-0">

          {/* ── Confirm ─────────────────────────────────────────────────────── */}
          {phase === 'confirm' && (
            <div className="p-5 space-y-4">
              <p className="text-gray-300 text-sm leading-relaxed">
                This will <span className="text-white font-medium">flush all transient demo data</span> and
                reseed a clean, realistic state in Pipeline Studio:
              </p>
              <div className="bg-gray-800 rounded-lg p-4 space-y-2 text-xs text-gray-400">
                {[
                  ['fa-trash',           'text-red-400',     'Flush all anomalies, quality issues, insights & notifications'],
                  ['fa-heart-pulse',     'text-green-400',   'Reset all 113 flows + 3 locations to healthy baseline'],
                  ['fa-triangle-exclamation', 'text-amber-400', '10 realistic anomalies (Frankfurt · Munich · Ingolstadt)'],
                  ['fa-chart-line',      'text-blue-400',    '6 quality issues (3 unresolved)'],
                  ['fa-lightbulb',       'text-yellow-400',  '9 AI insights (3 action-required)'],
                  ['fa-bell',            'text-purple-400',  '5 notifications (2 unread)'],
                  ['fa-tower-broadcast', 'text-brand-400',   'Simulator scenario → Normal Operation'],
                ].map(([icon, color, label]) => (
                  <div key={label} className="flex items-start gap-2.5">
                    <i className={`fa-solid ${icon} ${color} w-4 text-center mt-0.5 flex-shrink-0`} />
                    <span>{label}</span>
                  </div>
                ))}
              </div>
              <div className="bg-amber-900/30 border border-amber-700/40 rounded-lg p-3 flex items-start gap-2.5">
                <i className="fa-solid fa-triangle-exclamation text-amber-400 text-xs mt-0.5 flex-shrink-0" />
                <p className="text-amber-300 text-xs leading-relaxed">
                  All existing anomalies, quality issues and insights will be permanently deleted.
                </p>
              </div>
            </div>
          )}

          {/* ── Running ─────────────────────────────────────────────────────── */}
          {(phase === 'running' || phase === 'done' || phase === 'error') && (
            <div
              ref={logRef}
              className="p-4 font-mono text-[11px] space-y-0.5 overflow-y-auto"
              style={{ maxHeight: '340px' }}
            >
              {log.map(entry => (
                <div key={entry.id} className={clsx('flex items-start gap-2', lineColor[entry.type] || 'text-gray-300')}>
                  <span className="flex-shrink-0 w-3 text-center opacity-70">{lineIcon[entry.type] || '·'}</span>
                  <span className="leading-relaxed">{entry.msg}</span>
                </div>
              ))}
              {phase === 'running' && (
                <div className="flex items-center gap-2 text-brand-400 mt-1">
                  <i className="fa-solid fa-spinner fa-spin text-[10px]" />
                  <span>Running…</span>
                </div>
              )}
            </div>
          )}

          {/* ── Done summary ────────────────────────────────────────────────── */}
          {phase === 'done' && summary && (
            <div className="px-4 pb-4">
              <div className="bg-emerald-900/30 border border-emerald-700/40 rounded-lg p-4">
                <div className="flex items-center gap-2 mb-3">
                  <i className="fa-solid fa-circle-check text-emerald-400 text-sm" />
                  <span className="text-emerald-300 font-semibold text-sm">Reset complete — ready to demo!</span>
                </div>
                <div className="grid grid-cols-3 gap-2 text-center">
                  {[
                    [summary.anomalies, 'Anomalies', 'text-amber-400'],
                    [summary.quality,   'Quality Issues', 'text-blue-400'],
                    [summary.insights,  'Insights', 'text-yellow-400'],
                    [summary.notifs,    'Notifications', 'text-purple-400'],
                    [summary.flows,     'Flows Reset', 'text-green-400'],
                    [summary.locations, 'Locations', 'text-brand-400'],
                  ].map(([val, label, color]) => (
                    <div key={label} className="bg-gray-800/60 rounded-lg p-2">
                      <div className={clsx('text-lg font-bold leading-none', color)}>{val}</div>
                      <div className="text-gray-500 text-[10px] mt-0.5">{label}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ── Error ───────────────────────────────────────────────────────── */}
          {phase === 'error' && (
            <div className="px-4 pb-4">
              <div className="bg-red-900/30 border border-red-700/40 rounded-lg p-4 flex items-start gap-2.5">
                <i className="fa-solid fa-circle-xmark text-red-400 text-sm flex-shrink-0 mt-0.5" />
                <div>
                  <div className="text-red-300 font-semibold text-sm mb-1">Reset failed</div>
                  <div className="text-red-400 text-xs font-mono">{error}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-gray-800 flex items-center justify-end gap-3 flex-shrink-0">
          {phase === 'confirm' && (
            <>
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white
                           hover:bg-gray-800 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleRun}
                className="px-5 py-2 rounded-lg text-sm font-semibold bg-brand-600
                           hover:bg-brand-500 text-white transition-colors flex items-center gap-2"
              >
                <i className="fa-solid fa-rotate text-xs" />
                Reset Demo
              </button>
            </>
          )}

          {phase === 'running' && (
            <span className="text-gray-500 text-xs">Please wait…</span>
          )}

          {(phase === 'done' || phase === 'error') && (
            <>
              <a
                href="https://pipeline.iotdemozone.com"
                target="_blank"
                rel="noreferrer"
                className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white
                           hover:bg-gray-800 transition-colors flex items-center gap-2"
              >
                <i className="fa-solid fa-arrow-up-right-from-square text-[10px]" />
                Open Pipeline Studio
              </a>
              <button
                onClick={onClose}
                className="px-5 py-2 rounded-lg text-sm font-semibold bg-gray-700
                           hover:bg-gray-600 text-white transition-colors"
              >
                Close
              </button>
            </>
          )}
        </div>

      </div>
    </div>
  )
}
