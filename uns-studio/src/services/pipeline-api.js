/**
 * Pipeline API client — used by Demo Reset to call api.iotdemozone.com
 * directly from the browser with the service key.
 */

const PIPELINE_API = 'https://api.iotdemozone.com'
const SERVICE_KEY  = '636313eb95b09e9a0cc96fb80813aa9bbe01221b596478996c2034fbc56314ba'
const SIM_API      = 'https://sim-api.iotdemozone.com'

// Read the stored simulator API key from Zustand persisted state
function _getSimApiKey() {
  try {
    const raw = localStorage.getItem('uns-sim-api-key')
    if (!raw) return ''
    const state = JSON.parse(raw)
    return state?.state?.apiKey || ''
  } catch {
    return ''
  }
}

// ── helper ────────────────────────────────────────────────────────────────────
async function req(base, path, method = 'GET', body = null, { token = null, simKey = null } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (token)  headers['Authorization'] = `Bearer ${token}`
  if (simKey) headers['X-API-Key'] = simKey
  const opts = { method, headers }
  if (body) opts.body = JSON.stringify(body)
  const res = await fetch(`${base}${path}`, opts)
  const json = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(json?.error || json?.message || `HTTP ${res.status}`)
  return json
}

// ── Demo Reset ────────────────────────────────────────────────────────────────
/**
 * Run the full demo reset sequence, calling `onStep(msg, type)` for each log line.
 * type = 'ok' | 'warn' | 'info' | 'section'
 */
export async function runDemoReset(onStep) {
  const step  = (msg) => onStep(msg, 'info')
  const ok    = (msg) => onStep(msg, 'ok')
  const warn  = (msg) => onStep(msg, 'warn')
  const sec   = (msg) => onStep(msg, 'section')

  // ── STEP 1 · Auth ──────────────────────────────────────────────────────────
  sec('Authenticating…')
  let token
  try {
    const r = await req(PIPELINE_API, '/auth/service-token', 'POST', { api_key: SERVICE_KEY })
    token = r.data.token
    ok('Service token obtained')
  } catch (e) {
    throw new Error(`Auth failed: ${e.message}`)
  }

  const api = (method, path, body) => req(PIPELINE_API, path, method, body, { token })

  // ── STEP 2 · Discover ─────────────────────────────────────────────────────
  sec('Discovering flows & locations…')
  const [flowsR, locsR] = await Promise.all([
    api('GET', '/flows?limit=300'),
    api('GET', '/locations?limit=50'),
  ])
  const flows     = flowsR?.data?.items || []
  const locations = locsR?.data?.items  || []
  step(`Found ${flows.length} flows across ${locations.length} locations`)

  const locMap = {}
  for (const l of locations) locMap[l.location_name] = l.location_id

  // ── STEP 3 · Flush ────────────────────────────────────────────────────────
  sec('Flushing transient data…')
  const farFuture = Math.floor(Date.now() / 1000) + 365 * 86400

  // Bulk delete anomalies
  let totalDeleted = 0
  for (const sev of ['HIGH', 'MEDIUM', 'LOW']) {
    try {
      const r = await api('DELETE', '/bulk/anomalies', {
        filters: { older_than: farFuture, severity: sev },
        confirm_deletion: true,
      })
      totalDeleted += r?.data?.deleted_count || 0
    } catch (e) {
      warn(`Anomaly bulk flush (${sev}): ${e.message}`)
    }
  }
  ok(`Flushed anomalies (${totalDeleted} deleted)`)

  // Flush quality issues via per-flow route
  let qiFlushed = 0
  for (const flow of flows) {
    try {
      const r = await api('GET', `/flows/${flow.flow_id}/quality-issues?limit=100`)
      const items = r?.data?.items || []
      for (const item of items) {
        try { await api('DELETE', `/quality-issues/${item.issue_id}`) ; qiFlushed++ } catch {}
      }
    } catch {}
  }
  ok(`Flushed ${qiFlushed} quality issues`)

  // Flush insights via per-flow route
  let insFlushed = 0
  for (const flow of flows) {
    try {
      const r = await api('GET', `/flows/${flow.flow_id}/insights?limit=100`)
      const items = r?.data?.items || []
      for (const item of items) {
        try { await api('DELETE', `/insights/${item.insight_id}`) ; insFlushed++ } catch {}
      }
    } catch {}
  }
  ok(`Flushed ${insFlushed} insights`)

  // Flush notifications
  let notifFlushed = 0
  try {
    const r = await api('GET', '/notifications?limit=500')
    const items = r?.data?.items || []
    for (const n of items) {
      try { await api('DELETE', `/notifications/${n.notification_id}`) ; notifFlushed++ } catch {}
    }
  } catch {}
  ok(`Flushed ${notifFlushed} notifications`)

  // ── STEP 4 · Reset health ─────────────────────────────────────────────────
  sec('Resetting flow & location health…')
  let flowsReset = 0
  for (const flow of flows) {
    try {
      await api('PUT', `/flows/${flow.flow_id}`, {
        flow_status:    0,
        ai_health_score: +(Math.random() * 8 + 92).toFixed(1),
        ai_priority:    'normal',
      })
      flowsReset++
    } catch {}
  }
  ok(`Reset ${flowsReset} flows to healthy`)

  for (const loc of locations) {
    try {
      await api('PUT', `/locations/${loc.location_id}`, {
        loc_name:        loc.location_name,
        location_status: 0,
        slo_target:      '99.5',
        slo_status:      '99.5',
        error_budget:    '100',
      })
    } catch {}
  }
  ok(`Reset ${locations.length} locations to healthy`)

  // ── STEP 5 · Reseed ───────────────────────────────────────────────────────
  sec('Seeding realistic demo data…')
  const now = Math.floor(Date.now() / 1000)

  function flowsForLoc(locName) {
    const lid = locMap[locName]
    if (!lid) return []
    return flows.filter(f => f.location_id === lid).map(f => f.flow_id)
  }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)] }
  function rand(min, max) { return +(Math.random() * (max - min) + min).toFixed(2) }

  // Anomalies
  const ANOMALIES = [
    { loc: 'Frankfurt',  type: 'TIMING_ANOMALY',    sev: 'HIGH',   desc: 'Filter01 differential pressure rising — flow rate drop detected (possible clog)' },
    { loc: 'Frankfurt',  type: 'DATA_QUALITY',      sev: 'MEDIUM', desc: 'Pretreatment bath conductivity drifting outside control limits' },
    { loc: 'Frankfurt',  type: 'PATTERN_DEVIATION', sev: 'LOW',    desc: 'ECoat bath temperature variance elevated vs 7-day baseline' },
    { loc: 'Frankfurt',  type: 'MESSAGE_RATE',      sev: 'LOW',    desc: 'Primer robot PLC heartbeat interval slightly irregular' },
    { loc: 'Munich',     type: 'TIMING_ANOMALY',    sev: 'MEDIUM', desc: 'BIW WeldRobot01 cycle time 18% above nominal — possible electrode wear' },
    { loc: 'Munich',     type: 'DATA_QUALITY',      sev: 'LOW',    desc: 'AGV02 position jitter outside ±2 mm tolerance on Station 7 approach' },
    { loc: 'Munich',     type: 'PATTERN_DEVIATION', sev: 'LOW',    desc: 'Adhesive dispenser pressure variance increased over last 4 hours' },
    { loc: 'Ingolstadt', type: 'PAYLOAD_SIZE',      sev: 'LOW',    desc: 'Press01 stamping force telemetry packets intermittently oversized' },
    { loc: 'Ingolstadt', type: 'TIMING_ANOMALY',    sev: 'MEDIUM', desc: 'Hemming Station01 Z-axis positioning slow — servo response degraded' },
    { loc: 'Ingolstadt', type: 'DATA_QUALITY',      sev: 'LOW',    desc: 'Body shop environment sensor humidity reading 3σ above seasonal mean' },
  ]
  let createdAnomalies = 0
  for (const a of ANOMALIES) {
    const fids = flowsForLoc(a.loc)
    if (!fids.length) { warn(`No flows for ${a.loc} (anomaly skipped)`); continue }
    const fid = pick(fids)
    try {
      await api('POST', `/flows/${fid}/anomalies`, {
        flow_id: fid, anomaly_type: a.type, severity: a.sev,
        deviation: rand(0.4, 4.5), description: a.desc,
        detected_ts: now - Math.floor(Math.random() * 7200 + 300),
      })
      createdAnomalies++
    } catch (e) { warn(`Anomaly failed: ${e.message}`) }
  }
  ok(`Created ${createdAnomalies} anomalies`)

  // Quality issues
  const QUALITY = [
    { loc: 'Frankfurt',  type: 'STALE_DATA',      sev: 'MEDIUM', impact: 0.25, resolved: false,
      desc: 'Clearcoat oven Zone3 temperature sensor reporting stale values (15 min gap)',
      sugg: 'Check OPC-UA gateway reconnect; verify PLC tag subscription still active' },
    { loc: 'Frankfurt',  type: 'MISSING_DATA',    sev: 'LOW',    impact: 0.10, resolved: true,
      desc: 'Inspection camera vision system missed 2 frames during shift change',
      sugg: 'Increase buffer size on SCADA side; stagger shift-change restarts' },
    { loc: 'Munich',     type: 'SCHEMA_MISMATCH', sev: 'HIGH',   impact: 0.60, resolved: false,
      desc: "FinalAssembly ERP order payload missing required field 'batch_ref'",
      sugg: 'Update ERP export template to include batch_ref; align with UNS schema v2.1' },
    { loc: 'Munich',     type: 'DUPLICATE_DATA',  sev: 'LOW',    impact: 0.05, resolved: true,
      desc: 'Conveyor speed sensor publishing duplicate readings at 500ms boundary',
      sugg: 'Add deduplication filter in MQTT bridge; review PLC scan cycle alignment' },
    { loc: 'Ingolstadt', type: 'INVALID_MESSAGE', sev: 'MEDIUM', impact: 0.35, resolved: false,
      desc: 'Press02 stamping force value outside physical range (>9800 kN recorded)',
      sugg: 'Verify sensor calibration; add range validation in uns_model.py generator' },
    { loc: 'Ingolstadt', type: 'MISSING_DATA',    sev: 'LOW',    impact: 0.08, resolved: true,
      desc: 'Body shop humidity sensor dropped 12 readings during overnight maintenance',
      sugg: 'Configure sensor to buffer locally during planned downtime windows' },
  ]
  let createdQI = 0
  for (const q of QUALITY) {
    const fids = flowsForLoc(q.loc)
    if (!fids.length) continue
    const body = {
      flow_id: pick(fids), issue_type: q.type, severity: q.sev,
      impact: q.impact, description: q.desc, suggestion: q.sugg,
      occurred_ts: now - Math.floor(Math.random() * 14400 + 600),
    }
    if (q.resolved) {
      body.resolved_ts = now - Math.floor(Math.random() * 3600 + 60)
      body.resolution_notes = 'Resolved via automated remediation pipeline.'
    }
    try { await api('POST', '/quality-issues', body); createdQI++ }
    catch (e) { warn(`Quality issue failed: ${e.message}`) }
  }
  ok(`Created ${createdQI} quality issues`)

  // Insights
  const INSIGHTS = [
    { loc: 'Frankfurt',  type: 'PREDICTION',     cat: 'MAINTENANCE', conf: 0.87, action: true,
      desc: 'Filter01 differential pressure trend projects clog in 4-6 hours. Recommend scheduled flush during next shift break.' },
    { loc: 'Frankfurt',  type: 'OPTIMIZATION',   cat: 'QUALITY',     conf: 0.79, action: false,
      desc: 'ECoat bath temperature control within ±0.5°C for last 48h — consistently above 6-sigma quality threshold.' },
    { loc: 'Frankfurt',  type: 'RECOMMENDATION', cat: 'PERFORMANCE', conf: 0.82, action: false,
      desc: 'Primer Robot01 publish interval could be relaxed from 1s to 2s without SLO impact — reduces MQTT broker load by ~12%.' },
    { loc: 'Munich',     type: 'PREDICTION',     cat: 'MAINTENANCE', conf: 0.91, action: true,
      desc: 'WeldRobot01 electrode wear indicator at 78% capacity. Predicted replacement window: next 3-5 shifts. Schedule during Shift C.' },
    { loc: 'Munich',     type: 'OPTIMIZATION',   cat: 'PERFORMANCE', conf: 0.74, action: false,
      desc: 'AGV02 route optimisation opportunity detected — avg travel time to Station 7 could decrease 8% with updated path planning.' },
    { loc: 'Munich',     type: 'ALERT',          cat: 'QUALITY',     conf: 0.95, action: true,
      desc: "ERP schema mismatch on FinalAssembly flow causing batch traceability gaps. Immediate schema alignment required before end-of-shift audit." },
    { loc: 'Ingolstadt', type: 'PREDICTION',     cat: 'MAINTENANCE', conf: 0.83, action: false,
      desc: 'Hemming Station01 servo motor temperature trending +2°C/day. Expected thermal limit reached in ~6 days.' },
    { loc: 'Ingolstadt', type: 'RECOMMENDATION', cat: 'COST',        conf: 0.68, action: false,
      desc: 'Press shop environment monitoring sample rate (10s) could be reduced to 30s during non-production hours — reduces storage costs ~40%.' },
    { loc: 'Ingolstadt', type: 'OPTIMIZATION',   cat: 'PERFORMANCE', conf: 0.77, action: false,
      desc: 'Body shop PLC streams at 90% SLO compliance (target 99.5%). Consider increasing alert interval threshold from 10× to 15× default.' },
  ]
  let createdIns = 0
  for (const ins of INSIGHTS) {
    const fids = flowsForLoc(ins.loc)
    if (!fids.length) continue
    const genTs = now - Math.floor(Math.random() * 3600)
    try {
      await api('POST', '/insights', {
        flow_id: pick(fids), insight_type: ins.type, category: ins.cat,
        description: ins.desc, confidence: ins.conf,
        action_required: ins.action,
        generated_ts: genTs, expires_ts: genTs + 7 * 86400,
      })
      createdIns++
    } catch (e) { warn(`Insight failed: ${e.message}`) }
  }
  ok(`Created ${createdIns} insights`)

  // Notifications
  const NOTIFS = [
    { title: '⚠️  Filter Clog Alert',
      message: 'Frankfurt/PaintShop/Line1/Pretreatment — Filter01 differential pressure threshold exceeded. Maintenance ticket created.' },
    { title: '🔧  Maintenance Prediction',
      message: 'Munich/Assembly/BIW — WeldRobot01 electrode replacement recommended within 3 shifts (78% wear). Schedule during Shift C.' },
    { title: '📋  Schema Mismatch Detected',
      message: "Munich/Assembly/FinalAssembly ERP flow missing 'batch_ref' field. Batch traceability impacted. Schema update required." },
    { title: '✅  Demo Reset Complete',
      message: 'Pipeline Studio database has been reset to a clean demo state. All IoTAuto GmbH streams are active and healthy.' },
    { title: '📊  Weekly SLO Report',
      message: 'All 3 locations met SLO targets last week. Frankfurt 99.8% · Munich 99.6% · Ingolstadt 99.7%.' },
  ]
  let createdNotifs = 0
  for (const n of NOTIFS) {
    try { await api('POST', '/notifications', { title: n.title, message: n.message, type: 'info' }); createdNotifs++ }
    catch (e) { warn(`Notification failed: ${e.message}`) }
  }
  ok(`Created ${createdNotifs} notifications`)

  // ── STEP 6 · Reset simulator scenario ────────────────────────────────────
  sec('Resetting simulator to Normal Operation…')
  try {
    const simKey = _getSimApiKey()
    await req(SIM_API, '/api/scenario/normal', 'POST', null, { simKey })
    ok('Simulator scenario → Normal Operation')
  } catch (e) {
    warn(`Could not reset simulator scenario: ${e.message}`)
  }

  return {
    flows:     flows.length,
    locations: locations.length,
    anomalies: createdAnomalies,
    quality:   createdQI,
    insights:  createdIns,
    notifs:    createdNotifs,
  }
}
