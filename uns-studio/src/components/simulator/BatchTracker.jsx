/**
 * BatchTracker — live batch lifecycle panel for Aurora Industries.
 * Polls /api/batch_status and shows the current batch stage, unit counts,
 * FPY, and a DPP trigger button.
 */
import { useEffect, useState, useCallback } from 'react'
import clsx from 'clsx'
import { api } from '../../services/api.js'

const STAGES = ['PLANNED', 'RELEASED', 'PRESSING', 'PAINTING', 'CURING', 'INSPECTING', 'COMPLETE']

const STAGE_ICON = {
  PLANNED:    'fa-file-circle-plus',
  RELEASED:   'fa-file-check',
  PRESSING:   'fa-arrow-down-to-line',
  PAINTING:   'fa-spray-can',
  CURING:     'fa-fire-flame-curved',
  INSPECTING: 'fa-magnifying-glass',
  COMPLETE:   'fa-circle-check',
}

const STAGE_COLOR = {
  PLANNED:    'text-gray-400',
  RELEASED:   'text-blue-400',
  PRESSING:   'text-violet-400',
  PAINTING:   'text-amber-400',
  CURING:     'text-orange-400',
  INSPECTING: 'text-cyan-400',
  COMPLETE:   'text-emerald-400',
}

const STATUS_BADGE = {
  IN_PROGRESS: 'bg-blue-900/50 text-blue-300 border-blue-700/50',
  COMPLETE:    'bg-emerald-900/50 text-emerald-300 border-emerald-700/50',
  ON_HOLD:     'bg-red-900/50 text-red-300 border-red-700/50',
  PLANNED:     'bg-gray-800 text-gray-400 border-gray-700',
  RELEASED:    'bg-gray-800 text-gray-300 border-gray-600',
}

export default function BatchTracker() {
  const [batch, setBatch]     = useState(null)
  const [dppLoading, setDppLoading] = useState(false)
  const [dppResult, setDppResult]   = useState(null)
  const [error, setError]     = useState(null)

  const fetchBatch = useCallback(async () => {
    try {
      const data = await api.batchStatus()
      setBatch(data)
      setError(null)
    } catch (e) {
      setError('Batch API unavailable')
    }
  }, [])

  useEffect(() => {
    fetchBatch()
    const id = setInterval(fetchBatch, 3000)
    return () => clearInterval(id)
  }, [fetchBatch])

  const triggerDpp = async () => {
    setDppLoading(true)
    setDppResult(null)
    try {
      const r = await api.triggerDpp()
      setDppResult({ ok: true, msg: `DPP queued · ${r.batch_id}` })
    } catch {
      setDppResult({ ok: false, msg: 'DPP trigger failed' })
    } finally {
      setDppLoading(false)
      setTimeout(() => setDppResult(null), 4000)
    }
  }

  if (error) return (
    <div className="card p-3">
      <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-1">Batch Tracker</div>
      <div className="text-xs text-red-400">{error}</div>
    </div>
  )

  if (!batch) return (
    <div className="card p-3 animate-pulse">
      <div className="h-3 w-24 bg-gray-800 rounded mb-2" />
      <div className="h-5 w-32 bg-gray-800 rounded" />
    </div>
  )

  const stageIdx = STAGES.indexOf(batch.current_stage)
  const fpy      = batch.fpy_pct ?? 0

  return (
    <div className="card p-3 space-y-3">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[10px] text-gray-500 uppercase tracking-widest mb-0.5">Aurora Batch</div>
          <div className="text-sm font-bold text-white leading-none">{batch.batch_id}</div>
          <div className="text-[10px] text-gray-500 mt-0.5">{batch.order_id} · {batch.work_order_id}</div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={clsx('text-[10px] font-bold px-2 py-0.5 rounded border',
            STATUS_BADGE[batch.batch_status] ?? 'bg-gray-800 text-gray-400 border-gray-700')}>
            {batch.batch_status}
          </span>
          <span className="text-[10px] text-gray-500">{batch.completion_pct}% complete</span>
        </div>
      </div>

      {/* Stage pipeline */}
      <div className="flex items-center gap-0.5 overflow-x-auto pb-0.5">
        {STAGES.map((s, i) => {
          const done    = i < stageIdx
          const current = i === stageIdx
          const future  = i > stageIdx
          return (
            <div key={s} className="flex items-center gap-0.5 flex-shrink-0">
              <div className={clsx('flex flex-col items-center gap-0.5 px-1.5 py-1 rounded',
                current ? 'bg-brand-900/60 border border-brand-700/60'
                : done   ? 'bg-gray-800/60'
                :           'opacity-30')}>
                <i className={clsx(`fa-solid ${STAGE_ICON[s]} text-[10px]`,
                  current ? 'text-brand-300' : done ? STAGE_COLOR[s] : 'text-gray-600')} />
                <span className={clsx('text-[8px] font-medium leading-none',
                  current ? 'text-brand-300' : done ? 'text-gray-400' : 'text-gray-600')}>
                  {s.slice(0,4)}
                </span>
              </div>
              {i < STAGES.length - 1 && (
                <div className={clsx('w-2 h-px flex-shrink-0', done ? 'bg-gray-500' : 'bg-gray-800')} />
              )}
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      {batch.current_stage !== 'PLANNED' && batch.current_stage !== 'RELEASED' && (
        <div>
          <div className="flex justify-between text-[9px] text-gray-500 mb-1">
            <span>Stage progress</span>
            <span>{batch.stage_progress_pct}%</span>
          </div>
          <div className="h-1 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-brand-500 rounded-full transition-all duration-700"
              style={{ width: `${batch.stage_progress_pct}%` }}
            />
          </div>
        </div>
      )}

      {/* Unit counts */}
      <div className="grid grid-cols-4 gap-1.5">
        {[
          { label: 'Started',  value: batch.units_started,  color: 'text-white' },
          { label: 'Passed',   value: batch.units_passed,   color: 'text-emerald-400' },
          { label: 'Rework',   value: batch.units_rework,   color: 'text-amber-400' },
          { label: 'Scrap',    value: batch.units_scrap,    color: 'text-red-400' },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-gray-800/60 rounded px-2 py-1.5 text-center">
            <div className={clsx('text-sm font-bold leading-none', color)}>{value}</div>
            <div className="text-[9px] text-gray-500 mt-0.5">{label}</div>
          </div>
        ))}
      </div>

      {/* FPY bar */}
      <div>
        <div className="flex justify-between text-[9px] mb-1">
          <span className="text-gray-500 uppercase tracking-wider">First-Pass Yield</span>
          <span className={clsx('font-bold', fpy >= 98 ? 'text-emerald-400' : fpy >= 90 ? 'text-amber-400' : 'text-red-400')}>
            {fpy}%
          </span>
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div
            className={clsx('h-full rounded-full transition-all duration-700',
              fpy >= 98 ? 'bg-emerald-500' : fpy >= 90 ? 'bg-amber-500' : 'bg-red-500')}
            style={{ width: `${Math.min(fpy, 100)}%` }}
          />
        </div>
      </div>

      {/* DPP trigger */}
      <div className="flex items-center justify-between gap-2 pt-1 border-t border-gray-800">
        <div>
          <div className="text-[9px] text-gray-500">
            {batch.completed_batches?.length ?? 0} batches completed today
          </div>
          {batch.dpp_triggered && (
            <div className="text-[9px] text-brand-400 mt-0.5">
              <i className="fa-solid fa-passport mr-1" />DPP triggered
            </div>
          )}
        </div>
        <button
          onClick={triggerDpp}
          disabled={dppLoading}
          className={clsx(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold transition-colors',
            dppLoading
              ? 'bg-gray-700 text-gray-500 cursor-not-allowed'
              : 'bg-brand-600 hover:bg-brand-700 text-white'
          )}
        >
          <i className={`fa-solid ${dppLoading ? 'fa-circle-notch fa-spin' : 'fa-passport'} text-[10px]`} />
          {dppLoading ? 'Queuing…' : 'Trigger DPP'}
        </button>
      </div>

      {/* DPP feedback */}
      {dppResult && (
        <div className={clsx('text-[10px] px-2 py-1.5 rounded border',
          dppResult.ok
            ? 'bg-emerald-950/50 text-emerald-300 border-emerald-700/50'
            : 'bg-red-950/50 text-red-300 border-red-700/50')}>
          <i className={`fa-solid ${dppResult.ok ? 'fa-circle-check' : 'fa-circle-xmark'} mr-1.5`} />
          {dppResult.msg}
        </div>
      )}
    </div>
  )
}
