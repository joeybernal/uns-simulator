# Aurora Industries — Three-Layer Intelligence Demo Guide
## InfluxDB × TerminusDB × BaSyx AAS

> **The pitch:** *"Most companies have data. Some have dashboards. Aurora has a knowledge graph that knows WHY something is happening, WHAT assets are involved, and WHAT to do — in seconds, not hours."*

---

## The Architecture You're Demonstrating

```
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — InfluxDB  "What is happening?"                           │
│  111 live UNS streams: pressure, temp, speed, OEE, kW, quality      │
│  Grafana dashboards — visual anomaly detection                       │
│  Updates every 5 seconds                                             │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  scenario tag on every measurement
┌──────────────────────────▼───────────────────────────────────────────┐
│  LAYER 2 — TerminusDB  "WHY is it happening? Who is affected?"      │
│  Asset graph: press_PR01 → feeds → conveyor_CV01 → feeds → Line 01  │
│  FaultScenario docs: description, ai_hint, affected_assets           │
│  ScenarioEvent history: every activation with timestamp              │
│  PlantState: current scenario, mqtt_connected, last_updated          │
│  Updates on every scenario change (event-driven)                     │
└──────────────────────────┬───────────────────────────────────────────┘
                           │  aas_id link per asset
┌──────────────────────────▼───────────────────────────────────────────┐
│  LAYER 3 — BaSyx AAS  "What IS this asset?"                         │
│  press_PR01: Manufacturer SCHULER, RatedForce 2500 kN               │
│  Submodels: NameplateData, TechnicalData, MaintenanceSchedule        │
│  Updates: lifecycle events only (slow)                               │
└──────────────────────────────────────────────────────────────────────┘
```

### Why this matters for the audience

| If you're talking to... | Lead with... |
|------------------------|--------------|
| **Plant Manager** | OEE impact + €/min cost of each fault scenario |
| **IT/OT Architect** | How UNS decouples data producers from consumers |
| **AI/Data team** | TerminusDB graph queries that no time-series DB can answer |
| **C-Suite** | 15-min demo → 3 fault types → total € impact avoided |

---

## Live System URLs

| System | URL | Credentials |
|--------|-----|-------------|
| **Simulator UI** | `https://aurora-api.iotdemozone.com` / port 8081 | API Key: `acf894b44d993ad68df2d06efe28593c` |
| **Grafana** | `https://grafana.iotdemozone.com` | (ask presenter) |
| **TerminusDB** | `https://terminusdb.iotdemozone.com` | admin / (ask presenter) |
| **BaSyx AAS** | `https://aurora-aas.iotdemozone.com` | (ask presenter) |
| **InfluxDB** | `https://influxdb.iotdemozone.com` | Org: Deloitte / Bucket: Aurora |

---

## Before You Start (2 min setup)

```bash
# 1. Verify all systems green
curl -s https://aurora-api.iotdemozone.com/health
# Expected: {"status":"ok","running":true,"mqtt":true,"streams":111}

# 2. Reset to clean baseline
curl -s -X POST https://aurora-api.iotdemozone.com/api/scenario/normal \
  -H "X-API-Key: acf894b44d993ad68df2d06efe28593c"

# 3. Check TerminusDB PlantState shows normal
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:<pass>" | python3 -m json.tool
```

**Browser setup:**
- Tab 1: Simulator UI
- Tab 2: Grafana Nav Home (Last 15 min, 10s refresh)
- Tab 3: TerminusDB UI or API (for graph queries)
- Tab 4: BaSyx AAS UI (for asset specs)

---

---

# DEMO FLOW A — The 5-Minute Executive Demo

> One narrative, three slides of live data. No scrolling.

## Step 1 — "Here's your plant in real-time" (1 min)
- Open Grafana **Nav Home**
- Point to OEE tiles: "79% across the plant. Every press, oven, robot — live."
- Point to total published: "111 data streams, updating every 5 seconds."

## Step 2 — "Watch what happens when a conveyor jams" (2 min)
```bash
curl -X POST https://aurora-api.iotdemozone.com/api/scenario/conveyor_cv01_jam \
  -H "X-API-Key: acf894b44d993ad68df2d06efe28593c"
```
- Switch to **Asset Telemetry** → CV01 speed drops to zero instantly
- Point to PR01 OEE starting to fall: *"The press behind it is now starved."*
- **Now open TerminusDB:** Show the `ScenarioEvent` that was just written + the `FaultScenario` doc:

```bash
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=ScenarioEvent&count=1" \
  -u "admin:<pass>"
```

> *"The graph database knows: CV01 jam → affects press_PR01 → affects Line 01 throughput. It doesn't just record the alarm — it records the causal chain. An AI agent can query this in one call."*

## Step 3 — "The AI answer" (2 min)
Ask an AI agent: *"What is the active scenario at Aurora, which assets are affected, and what should the operator do?"*

The agent queries:
1. **TerminusDB** → `PlantState.active_scenario` = `conveyor_cv01_jam`, `affected_assets` = [CV01, PR01]
2. **InfluxDB** → Last 5 min of CV01 speed + PR01 OEE
3. **BaSyx AAS** → CV01 asset spec (belt type, rated load)

Combined answer: *"CV01 belt jam confirmed. Press PR01 now starved — losing €210/min. Recovery: LOTO Panel A Switch 3, clear return roller, restart CV01 at 20% for 30s. ETA 15 min."*

---

---

# DEMO FLOW B — The 15-Minute Technical Demo

> Seven scenarios, three layers, one narrative arc.

---

## SCENARIO 0 — Baseline (2 min)
**API:** `POST /api/scenario/normal`

### What to show
| Layer | What to open | What to say |
|-------|-------------|-------------|
| **InfluxDB** (Grafana) | Plant Overview → OEE tiles | "All green. 79% OEE. This is the AI's baseline." |
| **TerminusDB** | PlantState document | "Knowledge graph shows scenario=normal, 22 assets connected." |
| **AAS** (BaSyx) | press_PR01 shell | "This is PR01's digital passport — specs, certs, rated force 2500 kN." |

**Talking point:** *"Three layers. InfluxDB tells you the numbers. TerminusDB tells you the relationships. AAS tells you the specs. Alone, none of these is enough. Together, they answer any question."*

---

## SCENARIO 1 — Early Pump Wear (Pre-Alarm) (3 min)
**API:** `POST /api/scenario/press_PR01_hydraulic_degradation`

### The story
> *"No alarm has fired. The SCADA threshold is 192 bar — pressure is at 196. Traditional systems see nothing. But three correlated signals tell a different story."*

### Layer 1 — InfluxDB (Grafana)
| Panel | Value | Meaning |
|-------|-------|---------|
| Press Hydraulic Pressure | 196 bar (declining) | Below nominal 210, above alarm 192 |
| OEE — PR01 | 76% (drifting) | Cycle time slightly elevated |
| Power — PR01 | Slightly elevated | Internal pump leakage = energy waste |

### Layer 2 — TerminusDB query
```bash
# What does the graph know about this scenario?
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora/FaultScenario/press_PR01_hydraulic_degradation" \
  -u "admin:<pass>" | python3 -m json.tool
```
Returns:
- `ai_hint`: *"Pressure trending down -0.8 bar/day over 3 days. Pump efficiency -12%. Recommend inspection within 5 days."*
- `affected_assets`: press_PR01
- `severity`: warning
- `ScenarioEvent.activated_at`: timestamp of when demo triggered this

### Layer 3 — BaSyx AAS
Open press_PR01 AAS shell → **MaintenanceData submodel**:
- Hydraulic pump last serviced: 14 months ago
- Rated pump life: 18 months
- Shows pump is 78% through its service life

### The combined AI answer
*"Pump is 78% through rated life (AAS). Pressure declining -0.8 bar/day (InfluxDB trend). Graph context: if this pump fails, conveyor CV01 and Line 01 output are next in the causal chain (TerminusDB). Preventive cost: €420. Unplanned failure cost: €2,800 + 4h downtime + 180 units lost."*

**Key demo point:** *"Without TerminusDB, you know the pressure number but not what it means. Without AAS, you don't know the pump's age. Without InfluxDB, you can't see the trend. You need all three."*

**Reset:** `POST /api/scenario/normal`

---

## SCENARIO 2 — Cascade Failure (Flagship) (3 min)
**API:** `POST /api/scenario/multi_asset_cascade`

### The story
> *"The most dangerous failure is the one no single alarm catches. Four systems involved. Zero alarms fired."*

### Layer 1 — InfluxDB (Grafana)
Open Faults & Alarms + Plant Overview side by side:

| Signal | Value | Alarm threshold | Status |
|--------|-------|-----------------|--------|
| PR01 hydraulic pressure | 195 bar | 192 bar | ✅ No alarm |
| PR01 press force deviation | +3.8% | 8% threshold | ✅ No alarm |
| OV01 zone 3 temp | +6°C | +15°C threshold | ✅ No alarm |
| CMM defect rate | 18% | 20% threshold | ✅ No alarm |

*"Every single alarm is green. But we have an 18% defect rate."*

### Layer 2 — TerminusDB
```bash
# Show the causal chain stored in the graph
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora/FaultScenario/multi_asset_cascade" \
  -u "admin:<pass>"
```
Returns `affected_assets`: [press_PR01, vision_CMM01] — graph knows both assets are involved.

```bash
# WOQL query: what assets are linked to press_PR01?
curl -s -X POST "https://terminusdb.iotdemozone.com/api/woql/admin/aurora" \
  -u "admin:<pass>" \
  -H "Content-Type: application/json" \
  -d '{"query": {"@type":"Using","collection":"admin/aurora","query":{"@type":"Select","variables":["Asset","Scenario"],"query":{"@type":"And","and":[{"@type":"Triple","subject":{"@type":"NodeValue","node":"FaultScenario/multi_asset_cascade"},"predicate":{"@type":"NodeValue","node":"affected_assets"},"object":{"@type":"Variable","name":"Asset"}}]}}}}'
```

### Layer 3 — BaSyx AAS
Open press_PR01 AAS → **TechnicalData submodel** → Hydraulic seal part number → last replaced 22 months ago (rated life 24 months).

### The combined AI answer
*"Hydraulic seal is 92% through rated life (AAS). Seal leak causing -15 bar → press force deviation +3.8% (InfluxDB). Force deviation causes wall thickness out-of-tolerance by +0.3mm. CMM detecting 18% fail rate as result. Graph context (TerminusDB): root cause is PR01, not CMM. Fix: replace PR01 MainSeal (€180, 2h) → defect rate returns to 3% baseline."*

**Key demo point:** *"The graph database is the AI's memory. It doesn't just see the alarm — it traces the causal chain back to the root cause, across four systems, in under 3 seconds."*

**Reset:** `POST /api/scenario/normal`

---

## SCENARIO 3 — Quality Escape Multi-Variate (3 min)
**API:** `POST /api/scenario/quality_escape`

### The story
> *"This is the scenario that costs companies millions — a quality escape where no individual signal is alarming, but the combination is fatal."*

### Layer 1 — InfluxDB
Three signals, all inside alarm thresholds, all slightly off:
- PR01 force deviation: +4.1% (alarm at 8%)
- OV01 zone 3: +8°C (alarm at +15°C)
- PR01 die wear: 72% (alarm at 90%)
- CMM defect rate: 18% (alarm at 20%)

### Layer 2 — TerminusDB — the demo query
```bash
# How many times has quality_escape been triggered?
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=ScenarioEvent" \
  -u "admin:<pass>" | grep quality_escape | wc -l
```

```bash
# What does the graph say about the scenario history?
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=ScenarioEvent&count=20" \
  -u "admin:<pass>" | grep "activated_at"
```
*"TerminusDB keeps a full git-versioned history of every scenario activation. You can answer: how many times did this fault occur in the last 30 days? Was it the same shift? Same product?"*

### Layer 3 — BaSyx AAS
open vision_CMM01 AAS → **CalibrationData submodel** → last calibration 6 weeks ago (recommended 4 weeks).

### Combined answer
*"Multi-variate root cause: PR01 force +4.1% + OV01 zone 3 +8°C + die at 72% life (AAS). Combined tolerance stack pushed 18% of parts out of spec. No single alarm fired. CMM calibration is also overdue (AAS: 6 weeks, recommended 4 weeks) which may be masking additional defects. Immediate actions: (1) Hold current batch, (2) Adjust PR01 force setpoint -4%, (3) Reset OV01 zone 3 PID, (4) Schedule CMM calibration."*

**Reset:** `POST /api/scenario/normal`

---

## SCENARIO 4 — Energy Waste + Cost Impact (2 min)
**API:** `POST /api/scenario/energy_anomaly_night_shift`

### Layer 1 — InfluxDB (Power & Energy dashboard)
| Metric | Normal | Fault | Δ |
|--------|--------|-------|---|
| CP01 power (kW) | 22 | 29.7 | +35% |
| Power factor | 0.91 | 0.73 | -20% |
| THD | 2.1% | 8.5% | +300% |

### Layer 2 — TerminusDB
FaultScenario doc: `ai_hint` = *"Annual excess cost: ~€8,400. Compressor RUL reduced 40% from continuous operation."*

### Layer 3 — BaSyx AAS
Compressor CP01 → **EnergyEfficiencyData submodel** → rated power factor 0.92, rated THD < 3%.

### Combined answer
*"CP01 running 35% over baseline. Power factor penalty visible (AAS rates 0.92, actual 0.73). TerminusDB graph context: this scenario has been active before — check if this is a shift pattern (AI detected night-shift recurrence). Annual impact: €8,400 excess energy + reduced compressor life. Fix: valve wear inspection or intercooler cleaning."*

**Reset:** `POST /api/scenario/normal`

---

## SCENARIO 5 — DPP + Full Traceability (2 min)
**API:** `POST /api/scenario/normal` (start from clean state)
**Then:** `POST /api/trigger_dpp`

### The story
> *"Every unit that leaves this plant has a Digital Product Passport. Watch it get created in real time."*

```bash
curl -X POST https://aurora-api.iotdemozone.com/api/trigger_dpp \
  -H "X-API-Key: acf894b44d993ad68df2d06efe28593c"
```

### What to show
1. **MES tab** in simulator: batch_id, units_passed, FPY%
2. **InfluxDB** `aurora_dpp` measurement: batch_complete event with all fields
3. **BaSyx AAS**: DPP submodel updated — `traceability_url` pointing to `https://dpp.aurora-industries.de/batch/...`
4. **TerminusDB**: Could link batch events here as future enhancement

**Talking point:** *"EU Battery Regulation 2023/1542 requires this passport for every battery casing. It's not a manual report — it's generated automatically from the live UNS data. Every sensor reading, every work order, every quality result, linked to the unit."*

---

---

# DEMO FLOW C — The TerminusDB Graph Value Demo

> For AI/data audiences who want to see graph queries in action.

## Setup: trigger 3 different scenarios to build history

```bash
KEY="acf894b44d993ad68df2d06efe28593c"
BASE="https://aurora-api.iotdemozone.com"

curl -X POST $BASE/api/scenario/press_PR01_hydraulic_degradation -H "X-API-Key: $KEY" && sleep 10
curl -X POST $BASE/api/scenario/normal -H "X-API-Key: $KEY" && sleep 5
curl -X POST $BASE/api/scenario/conveyor_cv01_jam -H "X-API-Key: $KEY" && sleep 10
curl -X POST $BASE/api/scenario/normal -H "X-API-Key: $KEY" && sleep 5
curl -X POST $BASE/api/scenario/quality_escape -H "X-API-Key: $KEY" && sleep 10
curl -X POST $BASE/api/scenario/normal -H "X-API-Key: $KEY"
```

## Query 1: What scenarios have been active today?
```bash
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=ScenarioEvent&count=20" \
  -u "admin:<pass>" | python3 -c "
import sys, json
for line in sys.stdin:
    if line.strip():
        e = json.loads(line)
        print(f'{e[\"activated_at\"]} → {e[\"scenario\"].split(\"/\")[-1]}')"
```

## Query 2: What is the current plant state?
```bash
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:<pass>" | python3 -m json.tool
```

## Query 3: Which assets are affected by the current scenario?
```bash
SCENARIO=$(curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:<pass>" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d['active_scenario'].split('/')[-1])")

curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora/FaultScenario/$SCENARIO" \
  -u "admin:<pass>" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Scenario:', d['scenario_id'])
print('Severity:', d['severity'])
print('AI Hint:', d['ai_hint'][:100])
print('Affected:', [a.split('/')[-1] for a in d.get('affected_assets',[])])"
```

## Query 4: TerminusDB vs InfluxDB — the difference in one query
InfluxDB: *"What was press_PR01's hydraulic pressure over the last hour?"*
→ Returns a time series of numbers.

TerminusDB: *"What scenarios was press_PR01 involved in, and what was their combined € impact?"*
→ Returns a graph traversal: PR01 → involved in → [hydraulic_degradation, multi_asset_cascade, quality_escape, die_wear] → each has a kpi_impact → sum = €X,XXX

This is the query no time-series database can answer.

---

---

# Talking Points Cheat Sheet

## "Why not just use Grafana alerts?"
> *"Grafana alerts fire when a single value crosses a threshold. TerminusDB answers: which assets are affected, what's the causal chain, how many times has this happened, and what did we do last time. That's the difference between an alarm and a diagnosis."*

## "Why TerminusDB specifically?"
> *"Three reasons: (1) It's a graph database — relationships between assets are first-class. (2) It has git-style versioning — every change is committed with an author and timestamp. You can branch the asset graph, make changes, and merge. (3) It exposes WOQL — a composable query language that can traverse the graph in ways SQL can't."*

## "How does InfluxDB know about TerminusDB events?"
> *"They share a common key: `scenario` tag in InfluxDB = `FaultScenario/{id}` in TerminusDB. The Flux query hint stored in each ScenarioEvent tells you exactly how to join them: `from(bucket:'Aurora') |> filter(fn:(r) => r.scenario == 'multi_asset_cascade')`."*

## "What does BaSyx AAS add?"
> *"AAS carries the asset's identity, specs, and certifications — the things that don't change every 5 seconds. When the AI says 'the hydraulic pump is 78% through its rated life', that rated life number comes from AAS, not from a dashboard. It's the asset's permanent record."*

## "How does this scale?"
> *"Every new asset added to BaSyx automatically becomes a node in the TerminusDB graph. Every MQTT topic it publishes to InfluxDB gets the same `asset_id` tag. One `aas_id` field links all three layers. Add a robot — it appears in all three systems automatically."*

---

# Quick Reference — All Scenario APIs

```bash
KEY="acf894b44d993ad68df2d06efe28593c"
BASE="https://aurora-api.iotdemozone.com/api/scenario"

# Reset
curl -X POST $BASE/normal -H "X-API-Key: $KEY"

# Predictive / Pre-alarm
curl -X POST $BASE/press_PR01_hydraulic_degradation -H "X-API-Key: $KEY"
curl -X POST $BASE/paint_filter_blockage            -H "X-API-Key: $KEY"
curl -X POST $BASE/tooling_die_wear                 -H "X-API-Key: $KEY"
curl -X POST $BASE/robot_R1_weld_drift              -H "X-API-Key: $KEY"
curl -X POST $BASE/compressed_air_leak              -H "X-API-Key: $KEY"

# Hard faults
curl -X POST $BASE/conveyor_cv01_jam                -H "X-API-Key: $KEY"
curl -X POST $BASE/oven_zone2_heater_failure        -H "X-API-Key: $KEY"
curl -X POST $BASE/oven_thermal_runaway             -H "X-API-Key: $KEY"

# Cascade / multi-system
curl -X POST $BASE/multi_asset_cascade              -H "X-API-Key: $KEY"
curl -X POST $BASE/quality_escape                   -H "X-API-Key: $KEY"
curl -X POST $BASE/robot_R3_spray_drift             -H "X-API-Key: $KEY"

# Energy / sustainability
curl -X POST $BASE/energy_anomaly_night_shift       -H "X-API-Key: $KEY"

# ERP/MES integration
curl -X POST $BASE/erp_material_shortage            -H "X-API-Key: $KEY"

# DPP (after triggering any scenario)
curl -X POST https://aurora-api.iotdemozone.com/api/trigger_dpp -H "X-API-Key: $KEY"
```

---

# TerminusDB Quick Reference

```bash
TBASE="https://terminusdb.iotdemozone.com/api/document/admin/aurora"
TAUTH="-u admin:<pass>"

# Live plant state
curl -s "$TBASE?type=PlantState" $TAUTH | python3 -m json.tool

# All scenario activations (history)
curl -s "$TBASE?type=ScenarioEvent&count=50" $TAUTH | \
  python3 -c "import sys,json; [print(json.loads(l)['activated_at'], json.loads(l)['scenario'].split('/')[-1]) for l in sys.stdin if l.strip()]"

# A specific scenario definition
curl -s "$TBASE/FaultScenario/multi_asset_cascade" $TAUTH | python3 -m json.tool

# All assets
curl -s "$TBASE?type=Asset&count=30" $TAUTH | \
  python3 -c "import sys,json; [print(json.loads(l).get('asset_id',''), json.loads(l).get('area','')) for l in sys.stdin if l.strip()]"
```

---

# The Value Story in Numbers

| Scenario | Undetected cost | Detection method | Value of detection |
|----------|----------------|------------------|-------------------|
| PR01 hydraulic pump wear | €2,800 repair + 4h downtime = ~€6k | AI trend detection (sub-threshold) | **€5,580 saved** |
| CV01 belt jam | €210/min × 20 min = €4,200 | Immediate detection, LOTO sequence | **15 min → 8 min recovery = €2,520 saved** |
| Cascade: seal leak → quality | 180 units scrap × €28 = €5,040 | Root cause graph traversal | **€4,840 saved** (find it in 3s vs 3h) |
| Oven zone 2 failure | 234 units scrap = €14,040 | Automatic MES batch hold | **€14,040 protected** |
| Energy anomaly CP01 | €8,400/year excess cost | Cross-layer energy monitoring | **€8,400/year** |
| **Annual plant total** | | | **~€180k–€400k depending on plant size** |

---

*Generated: 2026-04-20 | Aurora Industries demo environment | InfluxDB + TerminusDB + BaSyx AAS*
