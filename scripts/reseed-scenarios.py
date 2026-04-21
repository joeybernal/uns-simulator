#!/usr/bin/env python3
"""
reseed-scenarios.py
Re-seeds all 15 FaultScenario documents in TerminusDB with enriched data:
  - ai_answer (full AI response text)
  - root_cause
  - what_it_shows
  - how_to_demo
  - data_sources
  - oee_impact_pct, cost_per_minute_eur, undetected_cost_eur, detection_value_eur
  - demo_duration_min
  - affected_assets (linked Asset refs, resolved from valid TerminusDB assets)

Run:
  python3 scripts/reseed-scenarios.py
"""

import sys, json, base64, urllib.request, urllib.error

TERMINUS = "https://terminusdb.iotdemozone.com"
TERMINUS_USER = "admin"
TERMINUS_PASS = "8Cv7R#ME"
TERMINUS_TEAM = "admin"
TERMINUS_DB   = "aurora"
AURORA_API    = "https://aurora-api.iotdemozone.com"
AURORA_KEY    = "acf894b44d993ad68df2d06efe28593c"

AUTH = base64.b64encode(f"{TERMINUS_USER}:{TERMINUS_PASS}".encode()).decode()
HEADERS = {"Content-Type": "application/json", "Authorization": f"Basic {AUTH}"}
DOC_BASE = f"{TERMINUS}/api/document/{TERMINUS_TEAM}/{TERMINUS_DB}"

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def tput(path, body):
    url = f"{DOC_BASE}{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="PUT", headers=HEADERS)
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.status, json.loads(r.read())

def tget(path):
    url = f"{DOC_BASE}{path}"
    req = urllib.request.Request(url, headers={k:v for k,v in HEADERS.items() if k != "Content-Type"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read().decode()

def aurora_get(path):
    req = urllib.request.Request(f"{AURORA_API}{path}", headers={"X-API-Key": AURORA_KEY})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

# ── Get valid asset_ids from TerminusDB ──────────────────────────────────────

raw = tget("?type=Asset&count=100")
valid_assets = set()
for line in raw.strip().split("\n"):
    if line.strip():
        doc = json.loads(line)
        aid = doc.get("asset_id", "")
        if aid:
            valid_assets.add(aid)
print(f"Valid assets in TerminusDB: {sorted(valid_assets)}\n")

def extract_asset_ids(stream_ids):
    """Resolve stream IDs to known TerminusDB asset_ids."""
    result = []
    seen = set()
    for s in (stream_ids or []):
        matched = None
        for a in valid_assets:
            if a in s:
                matched = a
                break
        if matched and matched not in seen:
            result.append(matched)
            seen.add(matched)
    return result

# ── Enrichment map: scenario_id → extra fields ───────────────────────────────
# These mirror the aurora_model.py FAULT_SCENARIOS dict but add cost data

ENRICHMENT = {
    "normal": {
        "ai_answer": "Normal plant state: PR01 hydraulic_pressure 210 bar, cycle_time 4.2 s, OEE 79.3%. OV01 all zone temps within ±2°C of setpoint. CP01 power 22 kW, PF 0.91, THD 2.1%. All robot position errors < 0.2mm. No health scores below 85%. Rolling 24h FPY: 98.2%. AI anomaly scores all LOW (< 0.1). Energy cost rate: €18.4/hr.",
        "root_cause": "No fault. All systems nominal.",
        "what_it_shows": "Healthy baseline: all 111 UNS streams within expected ranges, OEE 79%, energy at nominal, zero active alarms. Every asset health score ≥ 90%.",
        "how_to_demo": "1. Start here before showing any fault. 2. Open Streams tab — filter to press_PR01 and show all readings green. 3. Open Energy tab — plant kW matches expected shift load. 4. Open Health tab — all bars above 90%. 5. Show the AI hint at top: No anomalies.",
        "data_sources": ["PLC", "MES", "ERP", "AI"],
        "oee_impact_pct": 79.0,
        "cost_per_minute_eur": 0.0,
        "undetected_cost_eur": 0.0,
        "detection_value_eur": 0.0,
        "demo_duration_min": 2,
    },
    "press_PR01_hydraulic_degradation": {
        "ai_answer": "Root cause: Progressive internal wear of the hydraulic pump piston seals. Evidence: pressure 196 bar (nominal 210, alarm 192) trending -0.8 bar/day for 3 days; oil temp +3°C above baseline; pump efficiency -12%. SCADA alarm will not fire until 192 bar — estimated 5 days at current trend. Recommended action: Schedule pump inspection at next planned stop (within 48h). If ignored: pump failure causes unplanned downtime of ~4h + €2,800 repair cost + 180 units lost production. Preventive action cost: €420 (2h labour + filter).",
        "root_cause": "Hydraulic pump piston seal wear causing internal leakage. Oil temp rise confirms energy lost to heat rather than hydraulic work.",
        "what_it_shows": "Sub-threshold degradation that rules-based SCADA alarms completely miss. The SCADA alarm limit is 192 bar — pressure is at 196 bar so no alarm fires. But the AI detects a 3-day downward trend of -0.8 bar/day.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter press_PR01 → show hydraulic_pressure_bar = 196 (alarm 192 — no alarm). 3. Point to oil_temperature_c = 53. 4. Point to pump_efficiency_pct = 74. 5. Health tab → HydraulicPump bar at 78%. 6. Ask AI the question and show the answer with €-impact.",
        "data_sources": ["PLC", "SCADA", "AI"],
        "oee_impact_pct": 76.0,
        "cost_per_minute_eur": 0.0,
        "undetected_cost_eur": 6000.0,
        "detection_value_eur": 5580.0,
        "demo_duration_min": 3,
    },
    "oven_zone2_heater_failure": {
        "ai_answer": "Zone 2 heater element has failed (open-circuit). Zone 2 temp 90°C vs 200°C setpoint — a 110°C shortfall. Cure specification: 200°C for minimum 6.4 min per zone. At 90°C, curing reaction rate is ~8% of nominal — effectively no cure in zone 2. Impact on current batch: 234 units, all have ~55% cure deficiency. Recommendation: (1) STOP line immediately, (2) Quality hold on full batch, (3) Destructive test 5 units. If < 60% spec: scrap batch ~€14,000. Heater repair: replace element (30 min, €85 part).",
        "root_cause": "Zone 2 heating element open-circuit failure. Element fatigue at 90% of rated life. Power SSR shows no current draw on zone 2 circuit.",
        "what_it_shows": "Multi-system correlation: OV01 PLC telemetry (zone temp drop), MES batch system (automatic batch hold triggered), ERP SAP (quality hold document created), DPP (every unit flagged). No human action required — integration does it automatically.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter oven_OV01 → show zone_2_temp_c = 90 (setpoint 200). 3. ERP/MES tab → batch_status = ON_HOLD. 4. Quality tab → FPY dropped to 72%. 5. Ask AI → cure deficiency + disposition logic.",
        "data_sources": ["PLC", "MES", "ERP", "AI"],
        "oee_impact_pct": 71.0,
        "cost_per_minute_eur": 5.0,
        "undetected_cost_eur": 14040.0,
        "detection_value_eur": 14040.0,
        "demo_duration_min": 3,
    },
    "paint_filter_blockage": {
        "ai_answer": "Root cause: SP02 paint filter blocked by accumulated paint solids. Filter DP rose from 0.12 bar to 0.68 bar over 127 minutes (467% increase). This restricted atomisation air from 3.0 bar setpoint to 1.9 bar. Coat thickness correlation: r = -0.94 between filter_dp and coat_thickness — highly causal. Affected: last 45 minutes (~338 parts). Rework cost: €2.4k. Action: Replace SP02 filter now (5 min, €12 part), quality hold on 45-min window. Filter replacement interval: every 8h (current interval was 14h — halve it).",
        "root_cause": "Paint filter clogged with pigment solids. Root cause of rapid blocking: filter replacement interval too long for current paint throughput rate.",
        "what_it_shows": "Gradual drift detected by correlating two separate streams. filter_dp rises slowly (0.12 → 0.68 bar over 2h). coat_thickness falls slowly (80 → 45µm over same window). AI computes correlation r = -0.94.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → sprayer_SP02 → filter_dp_bar = 0.68 (rising), coat_thickness_um = 45 (min 60). 3. Health tab → FilterUnit at 32% (red). 4. Quality tab → FPY falling. 5. Ask AI → correlation r=-0.94, 338 parts, rework cost.",
        "data_sources": ["PLC", "QMS", "MES", "AI"],
        "oee_impact_pct": 77.0,
        "cost_per_minute_eur": 0.0,
        "undetected_cost_eur": 2400.0,
        "detection_value_eur": 2400.0,
        "demo_duration_min": 2,
    },
    "conveyor_cv01_jam": {
        "ai_answer": "CV01 belt jam confirmed: speed = 0 m/s, jam_detected = true, belt_tension_n = 200N (normal 120N). Cascade: PR01 parts buffer emptied in ~90 sec → PR01 operational_status = Starved → OEE contribution = 0. Production loss rate: €210/min. Recovery sequence: (1) LOTO CV01 isolator Panel A Switch 3 — 2 min. (2) Inspect belt return roller zone — 3 min. (3) Remove jammed part — 2 min. (4) Release LOTO, start CV01 at 20% speed 30s. (5) Confirm PR01 restarts from Starved → Running. Total estimated recovery: 15-18 min = €2,625-€3,150 production loss.",
        "root_cause": "Foreign object or part misalignment in CV01 belt return section. Belt tension at 200N (normal 120N) confirms lodged object pulling belt tight.",
        "what_it_shows": "Hard fault with immediate cascading throughput impact across two assets. CV01 jam stops part flow → PR01 enters Starved state → MES work order accumulates downtime → ERP production order freezes.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → conveyor_CV01 → speed=0, jam_detected=true, belt_tension=200N. 3. press_PR01 → operational_status=Starved. 4. ERP/MES tab → downtime_min counting up. 5. Ask AI → LOTO sequence + recovery time + €/min impact.",
        "data_sources": ["PLC", "MES", "ERP", "AI"],
        "oee_impact_pct": 58.0,
        "cost_per_minute_eur": 210.0,
        "undetected_cost_eur": 4200.0,
        "detection_value_eur": 2520.0,
        "demo_duration_min": 3,
    },
    "energy_anomaly_night_shift": {
        "ai_answer": "CP01 consuming 29.7 kW vs 22 kW baseline (+35%). Phase C current 18A vs 12A nominal (50% imbalance). THD: 8.5% (limit 5%). Power factor: 0.73 (expected 0.91). Likely: valve wear or intercooler fouling. Annual excess cost: ~€8,400. Compressor RUL reduced 40% from continuous operation. Recommend: ultrasonic scan for internal valve bypass, intercooler inspection and cleaning.",
        "root_cause": "Compressor internal valve wear or intercooler fouling causing reduced efficiency. Continuous operation to compensate accelerates wear further.",
        "what_it_shows": "Energy waste that would only be caught in a monthly audit without continuous monitoring. Cross-system correlation: high kW + low PF + elevated THD + phase imbalance = degradation signature.",
        "how_to_demo": "1. Switch scenario. 2. Power & Energy dashboard → CP01 total_kw = 29.7 (baseline 22). 3. Power factor panel → CP01 drops to 0.73 (red). 4. THD panel → 8.5% (above 5% limit). 5. Ask AI → annual cost €8,400 + RUL reduction.",
        "data_sources": ["PLC", "SCADA", "AI"],
        "oee_impact_pct": 79.0,
        "cost_per_minute_eur": 0.17,
        "undetected_cost_eur": 8400.0,
        "detection_value_eur": 8400.0,
        "demo_duration_min": 2,
    },
    "multi_asset_cascade": {
        "ai_answer": "Causal chain: PR01 seal leak (-15 bar) → press force deviation (+80 kN) → case wall thickness out of tolerance (+0.3mm) → CMM fail rate 18% (vs 3% baseline). Root cause: PR01 MainSeal (health 42%). Fix seal (€180, 2h) → quality returns to baseline. No single alarm fired — SCADA pressure alarm at 192 bar (actual 195), force deviation alarm at 8% (actual 3.8%), CMM alarm at 20% (actual 18%). Only multi-variate correlation identifies the root cause.",
        "root_cause": "PR01 hydraulic seal leak causing insufficient press force, producing out-of-tolerance parts that fail CMM inspection. Root cause is PR01, not CMM.",
        "what_it_shows": "The most dangerous failure pattern: four systems all within alarm thresholds, but together producing an 18% defect rate. This is the scenario where traditional SCADA fails completely.",
        "how_to_demo": "1. Switch scenario. 2. Plant Overview → PR01 hydraulic pressure 195 bar (no alarm). 3. Faults tab → CMM defect rate 18% (alarm at 20%). 4. TerminusDB → show affected_assets [press_PR01, vision_CMM01]. 5. Ask AI → full causal chain. 6. Point to: same answer took a QA engineer 3 hours yesterday — AI gave it in 3 seconds.",
        "data_sources": ["PLC", "QMS", "MES", "AI"],
        "oee_impact_pct": 74.0,
        "cost_per_minute_eur": 84.0,
        "undetected_cost_eur": 5040.0,
        "detection_value_eur": 4840.0,
        "demo_duration_min": 3,
    },
    "oven_thermal_runaway": {
        "ai_answer": "All zones 20-25°C above setpoint. This is a temperature controller failure (PID loop) — not a single element. Evidence: all 4 zones trending UP simultaneously (single element failure would show one zone DOWN). Exhaust temp: 98°C (normal 85°C). STOP line immediately — paint scorch threshold exceeded at ~215°C. Hold all parts from last 20 min. Inspect PID controller card and zone SSRs. Estimated repair: 2h.",
        "root_cause": "Temperature PID controller fault causing all zones to overheat simultaneously. Distinct from single-element failure which shows one zone low.",
        "what_it_shows": "Immediate hard stop scenario. All four oven zones spike 20-25°C simultaneously — the AI distinguishes controller failure from single-element failure based on the pattern of all zones rising vs one falling.",
        "how_to_demo": "1. Switch scenario. 2. Plant Overview → Oven Zone Temperatures → all 4 zones spike simultaneously. 3. OEE drops immediately. 4. Alarms panel → all 4 zone alarms fire. 5. Ask AI → distinguishes controller fault from element fault.",
        "data_sources": ["PLC", "MES", "AI"],
        "oee_impact_pct": 60.0,
        "cost_per_minute_eur": 180.0,
        "undetected_cost_eur": 3600.0,
        "detection_value_eur": 3600.0,
        "demo_duration_min": 2,
    },
    "robot_R1_weld_drift": {
        "ai_answer": "R1 position error: 0.85mm (limit 0.5mm). JointA1 health: 71% (degrading 0.6%/day). WristUnit health: 68%. Teach-point drift increasing over 72h. At current rate: weld failures detectable in 4-5 days, scrap rate increases in 7-10 days. Recommend: recalibrate teach points now (2h), check joint backlash (JointA1 likely 0.12mm, limit 0.08mm), schedule bearing replacement within 2 weeks.",
        "root_cause": "JointA1 bearing wear causing teach-point drift. Drift is progressive — catches before weld failures appear in downstream quality data.",
        "what_it_shows": "Predictive maintenance before quality impact. Position error 0.85mm is above the 0.5mm limit but below the threshold where welds visibly fail. Shows AI catching degradation 7-10 days before quality problems.",
        "how_to_demo": "1. Switch scenario. 2. Asset Telemetry → Robot Position Error → R1 line at 0.85mm (limit 0.5mm). 3. Health tab → JointA1 = 71%, WristUnit = 68%. 4. Ask AI → degradation rate, days to failure, calibration sequence.",
        "data_sources": ["PLC", "SCADA", "AI"],
        "oee_impact_pct": 77.0,
        "cost_per_minute_eur": 0.0,
        "undetected_cost_eur": 4200.0,
        "detection_value_eur": 4200.0,
        "demo_duration_min": 2,
    },
    "compressed_air_leak": {
        "ai_answer": "Header pressure: 6.38 bar vs 7.5 bar nominal (-15%). Compressor loaded 95% (normal 72%). Leak estimated 4.2 m³/h. Annual energy cost of leak: ~€3,200. Compressor RUL reduced 40% from continuous operation. Total annual impact: ~€5,800 (energy + accelerated wear). Locate with ultrasonic detector starting in Zone A (highest delta between supply and return pressure). Repair: typically pneumatic fitting or hose (€15-50 part, 30 min).",
        "root_cause": "Pneumatic network leak — invisible in any single sensor but detectable from compressor running at 95% load vs 72% normal, plus header pressure drop. Most likely: fitting or hose in Zone A.",
        "what_it_shows": "Cross-layer inference: the leak itself has no sensor, but its effect on compressor load + network pressure reveals its presence. Shows how UNS correlates indirect signals to diagnose invisible faults.",
        "how_to_demo": "1. Switch scenario. 2. Power & Energy → CP01 kW elevated (95% load). 3. Faults tab → compressor outlet pressure dropping, temp rising. 4. Ask AI → leak location estimate, annual cost, repair priority.",
        "data_sources": ["PLC", "SCADA", "AI"],
        "oee_impact_pct": 78.0,
        "cost_per_minute_eur": 0.22,
        "undetected_cost_eur": 5800.0,
        "detection_value_eur": 5800.0,
        "demo_duration_min": 2,
    },
    "tooling_die_wear": {
        "ai_answer": "PR01 die at 70% life (420K/600K cycles). Die temp: 63°C vs 38°C nominal (+66%). Press force deviation: +3.2%. Wall thickness SPC Cpk 0.82 (limit 1.33). Quality escape intersection point predicted at cycle ~540,000 (28,500 cycles remaining = ~53 hours at current rate). Schedule die change within 24h to prevent quality escape. Die change cost: €2,400 (part + 4h labour). Unplanned quality escape cost: €18,000+ (scrap + rework + containment).",
        "root_cause": "Progressive die wear from 420,000 cycles (70% of 600,000 cycle limit). Die surface roughness increasing, releasing more heat, causing dimensional deviation to grow.",
        "what_it_shows": "Predictive tooling lifecycle management. Shows AI predicting exactly when die wear will cause a quality escape — not just that the die is worn, but the specific cycle count where Cpk will fall below 1.33.",
        "how_to_demo": "1. Switch scenario. 2. Plant Overview → Press Hydraulic Pressure widens (die resistance changing). 3. Faults tab → die wear % line at 70%. 4. Quality tab → SPC Cpk trending down toward 1.0. 5. Ask AI → intersection point, schedule recommendation.",
        "data_sources": ["PLC", "SCADA", "MES", "AI"],
        "oee_impact_pct": 75.0,
        "cost_per_minute_eur": 0.0,
        "undetected_cost_eur": 18000.0,
        "detection_value_eur": 15600.0,
        "demo_duration_min": 2,
    },
    "robot_R3_spray_drift": {
        "ai_answer": "R3 TCP offset: 0.72mm (limit 0.3mm). Coat thickness: 52µm (minimum 60µm). Uniformity: 72% (minimum 90%). Spray overlap incorrect — R3 is spraying 0.72mm offset from programmed path. Affected production: last 35 minutes (estimated 262 parts). Recalibrate R3 TCP (20 min), verify gun-to-part distance, quality hold on last 35-min window for re-inspection. Rework: re-spray + cure = €1,800. If TCP not recalibrated: coat thickness will reach 0 µm on far edge in ~2 hours.",
        "root_cause": "R3 tool-centre-point drift from joint wear. Drift increasing over 48h — caught before any complete coating failure.",
        "what_it_shows": "Cross-asset correlation: robot position error → paint quality impact. Two streams from different assets (robot telemetry and sprayer QMS) correlate to confirm root cause.",
        "how_to_demo": "1. Switch scenario. 2. Asset Telemetry → Robot Position Error → R3 at 0.72mm. 3. Sprayer SP02 → coat_thickness_um = 52 (min 60). 4. Ask AI → TCP recalibration sequence, 262 parts affected.",
        "data_sources": ["PLC", "QMS", "MES", "AI"],
        "oee_impact_pct": 76.0,
        "cost_per_minute_eur": 0.0,
        "undetected_cost_eur": 1800.0,
        "detection_value_eur": 1800.0,
        "demo_duration_min": 2,
    },
    "erp_material_shortage": {
        "ai_answer": "ALU_SHEET_2MM: 387 kg remaining (safety stock 500 kg). Consumption rate: 8.25 kg/min. Starvation time: ~47 min at current rate. Options: (1) Expedite PO — 4h lead time → 3 shifts of unplanned downtime (€37,800 loss). (2) Reduce PR01+PR02 rate to 3.7 units/min combined — extends window to 95 min, enabling expedite PO to arrive just in time. (3) Switch both presses to lighter gauge ALU_SHEET_1.5MM — 8% lower unit strength (check spec compliance first). Recommended: Option 2 now, trigger expedite PO simultaneously.",
        "root_cause": "Material planning gap: safety stock threshold not adjusted for increased production rate. Consumption 8.25 kg/min vs planned 6.1 kg/min (current batch is heavier spec than baseline).",
        "what_it_shows": "ERP-to-OT integration: a supply chain event (material stock level) reflected immediately in plant floor operations. Shows UNS connecting IT and OT layers without manual intervention.",
        "how_to_demo": "1. Switch scenario. 2. Plant Overview → OEE declining as work orders are blocked. 3. ERP/MES tab → material_stock = 387 kg (safety stock 500 kg). 4. Ask AI → starvation countdown, options with cost.",
        "data_sources": ["ERP", "MES", "PLC", "AI"],
        "oee_impact_pct": 72.0,
        "cost_per_minute_eur": 210.0,
        "undetected_cost_eur": 37800.0,
        "detection_value_eur": 37800.0,
        "demo_duration_min": 2,
    },
    "quality_escape": {
        "ai_answer": "CMM fail rate 18% (baseline 3%). No single alarm fired. Multi-variate root cause: PR01 force deviation +4.1% (alarm 8%), oven zone 3 +8°C above setpoint (alarm +15°C), die wear 72% (alarm 90%). Combined effect: force deviation shifts wall thickness +0.18mm, oven deviation adds thermal stress causing +0.12mm additional deviation → total +0.30mm exceeds ±0.25mm tolerance. Immediate actions: (1) Hold current batch — estimated 156 units at risk, (2) Adjust PR01 force setpoint -4%, (3) Reset OV01 zone 3 PID offset, (4) Check die wear rate (schedule change if > 75%). Cost of hold: €4,368. Cost if escaped to customer: €28,000+ (warranty, recall risk).",
        "root_cause": "Multi-variate tolerance stack: press force deviation + oven thermal deviation + die wear combine to exceed dimensional tolerance. No single root cause — requires correlation across three systems.",
        "what_it_shows": "The scenario that costs companies the most: a quality escape where no individual signal is alarming, but the combination is fatal. Only multi-variate AI analysis identifies it before customer impact.",
        "how_to_demo": "1. Switch scenario. 2. Show each signal individually — all inside alarm thresholds. 3. Show CMM defect rate = 18%. 4. Ask AI → full multi-variate root cause. 5. Show: traditional SCADA sees nothing, AI sees everything. 6. TerminusDB: query ScenarioEvent history — how many times has this occurred?",
        "data_sources": ["PLC", "QMS", "MES", "ERP", "AI"],
        "oee_impact_pct": 74.0,
        "cost_per_minute_eur": 84.0,
        "undetected_cost_eur": 28000.0,
        "detection_value_eur": 23632.0,
        "demo_duration_min": 3,
    },
}

def severity_of(sc):
    txt = (sc.get("description", "") + sc.get("label", "")).lower()
    if any(w in txt for w in ["runaway", "cascade", "scorch"]): return "emergency"
    if any(w in txt for w in ["escape", "failure", "blocked", "jam", "leak", "shortage"]): return "critical"
    if any(w in txt for w in ["wear", "drift", "drop", "blockage", "anomaly"]): return "warning"
    return "info"

# ── Fetch all scenarios from Aurora API ──────────────────────────────────────

print("Fetching scenarios from Aurora API...")
status = aurora_get("/api/status")
api_scenarios = {s["id"]: s for s in status.get("scenarios", [])}
print(f"  Found {len(api_scenarios)} scenarios\n")

# ── Build enriched documents ─────────────────────────────────────────────────

docs = []
for sc_id, sc in api_scenarios.items():
    enrich = ENRICHMENT.get(sc_id, {})
    raw_affected = sc.get("affected_assets") or sc.get("affected_streams") or []
    asset_ids = extract_asset_ids(raw_affected)
    affected_refs = [{"@type": "@id", "@id": f"Asset/{a}"} for a in asset_ids]

    doc = {
        "@type": "FaultScenario",
        "@id": f"FaultScenario/{sc_id}",
        "scenario_id": sc_id,
        "label": sc.get("label", sc_id),
        "description": sc.get("description", ""),
        "ai_hint": sc.get("ai_hint", ""),
        "severity": severity_of(sc),
        "affected_assets": affected_refs,
        "data_sources": enrich.get("data_sources", ["PLC", "AI"]),
    }

    # Optional enriched fields
    for field in ["ai_answer", "root_cause", "what_it_shows", "how_to_demo",
                  "oee_impact_pct", "cost_per_minute_eur", "undetected_cost_eur",
                  "detection_value_eur", "demo_duration_min"]:
        val = enrich.get(field)
        if val is not None:
            doc[field] = val

    fk = sc.get("fault_key")
    if fk:
        doc["fault_key"] = fk

    docs.append(doc)

print(f"Built {len(docs)} enriched scenario documents")

# ── Replace all FaultScenario documents ──────────────────────────────────────

put_url = f"?author=enrich&message=reseed+enriched+scenarios&replace=true"
try:
    status_code, result = tput(put_url, docs)
    print(f"\n✓ PUT {status_code} — {len(docs)} FaultScenario documents updated")
except urllib.error.HTTPError as e:
    print(f"\nERROR: {e.code}")
    print(e.read().decode()[:500])
    sys.exit(1)

# ── Verify one document ───────────────────────────────────────────────────────

print("\nVerifying multi_asset_cascade:")
raw = tget("/FaultScenario/multi_asset_cascade")
doc = json.loads(raw)
print(f"  label: {doc.get('label')}")
print(f"  severity: {doc.get('severity')}")
print(f"  oee_impact_pct: {doc.get('oee_impact_pct')}")
print(f"  cost_per_minute_eur: {doc.get('cost_per_minute_eur')}")
print(f"  undetected_cost_eur: {doc.get('undetected_cost_eur')}")
print(f"  detection_value_eur: {doc.get('detection_value_eur')}")
print(f"  affected_assets: {[a.split('/')[-1] for a in doc.get('affected_assets', [])]}")
print(f"  data_sources: {doc.get('data_sources')}")
print(f"  ai_hint: {doc.get('ai_hint', '')[:80]}...")

print("\n=== Re-seed complete ===")
