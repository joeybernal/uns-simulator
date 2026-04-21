# Aurora Industries — Master Demo Guide
## From Raw Data to AI-Powered Intelligence: Building the Optimal OEE Stack

> **The story in one sentence:** *We start with a factory full of data no one can read, and end with an AI that tells you exactly what's broken, why, what it costs, and what to do — in under 3 seconds.*

---

## Table of Contents

1. [The Architecture Story](#1-the-architecture-story)
2. [Live System URLs & Credentials](#2-live-system-urls--credentials)
3. [Pre-Demo Setup (5 min)](#3-pre-demo-setup-5-min)
4. [LEVEL 1 — UNS: The Foundation](#4-level-1--uns-the-foundation)
5. [LEVEL 2 — Grafana: Making Data Visible](#5-level-2--grafana-making-data-visible)
6. [LEVEL 3 — TerminusDB: Adding Context & Relationships](#6-level-3--terminusdb-adding-context--relationships)
7. [LEVEL 4 — Digital Twin (AAS): Asset Identity & Specs](#7-level-4--digital-twin-aas-asset-identity--specs)
8. [LEVEL 5 — AI: The Intelligent Layer](#8-level-5--ai-the-intelligent-layer)
9. [Complete Scenario Playbook](#9-complete-scenario-playbook)
10. [Demo Flow Templates](#10-demo-flow-templates)
11. [The Value Story in Numbers](#11-the-value-story-in-numbers)
12. [Talking Points Cheat Sheet](#12-talking-points-cheat-sheet)
13. [Quick Reference — All APIs](#13-quick-reference--all-apis)

---

# 1. The Architecture Story

## The Problem We're Solving

A modern manufacturing plant generates **millions of data points per day**. Traditionally:
- SCADA watches one system at a time
- Alarms fire only when a threshold is crossed
- Root cause analysis takes hours of manual investigation across 4–6 different systems
- Predictive insights are impossible — you react, you don't predict
- OEE is measured the next day, not in real-time

**Aurora demonstrates what happens when you connect everything, layer intelligence on top, and let AI answer in seconds what used to take hours.**

---

## The Five Layers — Each One Better Than the Last

```
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 5 — AI Agent  "What should I DO? What will happen next?"        │
│  Synthesises all 4 layers in one call                                   │
│  Answers: root cause, € impact, recovery procedure, ETA                 │
│  Response time: < 3 seconds                                              │
└─────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — BaSyx AAS  "What IS this asset?"                            │
│  press_PR01: Manufacturer SCHULER, RatedForce 2500 kN                   │
│  Submodels: NameplateData, TechnicalData, MaintenanceSchedule, DPP      │
│  Updates: lifecycle events only (permanent record)                       │
└─────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — TerminusDB  "WHY is it happening? Who is affected?"         │
│  Graph: press_PR01 → feeds → CV01 → feeds → Line 01                    │
│  FaultScenario docs: ai_hint, description, affected_assets              │
│  ScenarioEvent history: timestamped, git-versioned                       │
│  PlantState: active scenario, last_updated, mqtt_connected              │
│  Updates: event-driven (on every scenario change)                        │
└─────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — Grafana (InfluxDB)  "What is happening RIGHT NOW?"          │
│  111 live UNS streams: pressure, temp, OEE, kW, position, flow          │
│  Visual anomaly detection — trends, thresholds, correlations             │
│  Updates: every 5 seconds                                                │
└─────────────────────────────────┬───────────────────────────────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — UNS (MQTT → InfluxDB)  "Collect everything"                 │
│  Unified Namespace: all 111 factory streams in one broker               │
│  Topic structure: aurora/<line>/<cell>/<type>/<measurement>              │
│  Every system speaks one language                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why each layer matters

| Layer | Without it | With it |
|-------|-----------|---------|
| **UNS** | 6 silos, 6 integrations, no correlation | One broker, all data available to all consumers |
| **Grafana** | Engineers staring at SCADA screens, manually correlating | Visual anomaly detection, pattern recognition, 5s refresh |
| **TerminusDB** | Alarm fires — root cause takes 2h of investigation | Graph traversal traces causal chain in < 1s |
| **BaSyx AAS** | No one knows the pump's rated life or who owns it | Every asset has a permanent digital identity, specs, certs |
| **AI** | A human must interpret all 4 layers | AI synthesises all layers in one natural-language answer |

---

# 2. Live System URLs & Credentials

| System | URL | Credentials |
|--------|-----|-------------|
| **Simulator API** | `https://aurora-api.iotdemozone.com` | API Key: `acf894b44d993ad68df2d06efe28593c` |
| **Grafana** | `https://grafana.iotdemozone.com` | admin / R66jVVd0We |
| **InfluxDB** | `https://influxdb.iotdemozone.com` | Org: Deloitte / Bucket: Aurora |
| **TerminusDB** | `https://terminusdb.iotdemozone.com` | admin / 8Cv7R#ME |
| **BaSyx AAS** | `https://aurora-aas.iotdemozone.com` | (open) |

### Grafana Dashboard URLs

```
Nav Home:        https://grafana.iotdemozone.com/d/aurora-nav-home
Plant Overview:  https://grafana.iotdemozone.com/d/aurora-plant-overview
Asset Telemetry: https://grafana.iotdemozone.com/d/aurora-asset-telemetry
Power & Energy:  https://grafana.iotdemozone.com/d/aurora-power-monitoring
Faults & Alarms: https://grafana.iotdemozone.com/d/aurora-faults-alarms
MES / Batch:     https://grafana.iotdemozone.com/d/aurora-mes-batch
```

---

# 3. Pre-Demo Setup (5 min)

**Run this before every demo:**

```bash
KEY="acf894b44d993ad68df2d06efe28593c"

# 1. Check all systems
echo "=== System Health ===" && \
curl -sf https://aurora-api.iotdemozone.com/health && \
curl -sf "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:8Cv7R#ME" | python3 -c "import sys,json; d=json.load(sys.stdin); print('PlantState:', d['active_scenario'])" && \
curl -sf https://grafana.iotdemozone.com/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('Grafana:', d['database'])"

# 2. Reset to clean baseline
curl -s -X POST https://aurora-api.iotdemozone.com/api/scenario/normal \
  -H "X-API-Key: $KEY"

echo "=== Ready! ==="
```

**Expected output:**
```
{"status":"ok","running":true,"mqtt":true,"streams":111}
PlantState: normal
Grafana: ok
{"ok":true,"scenario":"normal"}
=== Ready! ===
```

**Browser tabs to open:**
- Tab 1: Simulator (optional — use curl for demos)
- Tab 2: Grafana Nav Home — Last 15 min, 10s refresh
- Tab 3: TerminusDB (for graph layer demos)
- Tab 4: BaSyx AAS (for digital twin demos)

---

# 4. LEVEL 1 — UNS: The Foundation

## What is the UNS and why does it matter?

The **Unified Namespace (UNS)** is the single MQTT broker that every system in the Aurora plant publishes to and subscribes from. It is the information backbone.

### The Problem It Solves

**Before UNS — Spaghetti Integration:**
```
SCADA ──────────────→ MES
  ↕                    ↕
ERP ←────────────── Quality
  ↕
Energy Management
```
Every system has a point-to-point integration. 5 systems = 20 integrations. Adding a new consumer means re-integrating everything. Data is siloed, stale, and inconsistent.

**After UNS — Star Topology:**
```
        SCADA
          ↑↓
  ERP ←──MQTT──→ InfluxDB
          ↑↓
       Quality
          ↑↓
   Energy Management
```
Every system publishes what it knows. Every consumer subscribes to what it needs. Zero point-to-point integrations. Adding a new tool = subscribe to existing topics.

### The Aurora UNS Structure

```
aurora/
  line_01_press/
    press_PR01/
      telemetry/             → hydraulic_pressure, cycle_time, press_force, oee
      alarms/                → fault events with severity + timestamp
      health/                → health_score, rul_days
    press_PR02/
      telemetry/
  line_02_weld/
    robot_R1/
      telemetry/             → position_error, weld_current, cycle_time
    robot_R2/
  line_03_paint/
    conveyor_CV01/
      telemetry/             → belt_speed, motor_current, tension
    sprayer_SP01/
      telemetry/             → flow_rate, atomisation_pressure, coat_thickness
    oven_OV01/
      telemetry/             → zone1_temp, zone2_temp, zone3_temp, zone4_temp
  line_04_inspection/
    vision_CMM01/
      telemetry/             → defect_rate, measurement_result
  energy/
    compressor_CP01/
      power/                 → active_power_kw, power_factor, thd
  mes/
    batch/                   → work_order_id, units_in_progress, hold_flag
  erp/
    inventory/               → material_id, quantity_kg, safety_stock_kg
```

**111 streams. All updating every 5 seconds. All in one place.**

### The UNS Value Statement

> *"Before the UNS, getting a question like 'why is our defect rate up today?' required a meeting between the SCADA team, the MES team, and the quality team. With the UNS, that question is answered by a Flux query in 2 seconds — because all the data is already in the same place."*

---

# 5. LEVEL 2 — Grafana: Making Data Visible

## What Grafana Adds

The UNS collects everything. Grafana answers the question: **"What am I looking at?"**

With 111 streams updating every 5 seconds, you need:
- **Visual pattern recognition** — humans spot anomalies better on graphs than in numbers
- **Correlation** — see two related signals side-by-side simultaneously
- **Thresholds** — know when a value is outside normal range
- **History** — see trends, not just current values

---

## Grafana Dashboard Architecture

| Dashboard | Focus | Best For |
|-----------|-------|----------|
| **Nav Home** | KPI tiles + navigation | Exec overview, starting point |
| **4. Plant Overview** | OEE, press, oven, production rate | Plant manager |
| **5. Asset Telemetry** | Conveyors, robots, sprayers | Maintenance engineer |
| **6. Power & Energy** | kW, power factor, THD, grid | Energy manager |
| **7. Faults & Alarms** | Scenario timeline, alarms + TerminusDB context | Operations, AI demos |
| **8. MES / Batch** | Work orders, batch lifecycle, DPP | MES/ERP team |

---

## 🟢 Scenario GF-0 — Normal Baseline

**API:** `POST /api/scenario/normal`

**What to show:**
- Open **Nav Home** → All OEE tiles green (~79%)
- Open **Plant Overview** → PR01/PR02 pressure stable ~210 bar, oven zones ~200°C
- Open **Asset Telemetry** → All conveyors at design speed, robots < 0.2mm position error
- Open **Power & Energy** → Power factor ≥ 0.95, THD < 3%

> **Talking point:** *"79% OEE across the plant. This is your baseline — the AI's reference state. Every deviation from these patterns is signal. 111 streams, all in the green."*

---

## 🔴 Scenario GF-1 — Conveyor Jam (Hard Fault, Immediate)

**API:** `POST /api/scenario/conveyor_cv01_jam`

**Executive version (30 seconds):**
> Trigger it, switch to Asset Telemetry, point to CV01 speed dropping to zero. *"The conveyor just stopped. Watch the press OEE behind it start to fall — the press is being starved of parts. This is real-time cascade detection."*

**Technical version:**

| Dashboard | Panel | What Changes | Time |
|-----------|-------|-------------|------|
| Asset Telemetry | **Conveyor Speed History** | CV01 → 0 m/s instantly | Immediate |
| Asset Telemetry | Conveyor Motor Current | Spike then drop | Immediate |
| Asset Telemetry | CV01 Belt Tension (N) | Tension drops sharply | Immediate |
| Plant Overview | OEE — PR01 | Starts declining | 1–2 min |
| Faults & Alarms | Alarm Events | Spike on CV01 | Immediate |

> **Talking point:** *"One signal directly caused four downstream effects. Without the UNS, these four signals live in four different systems. Here, you see all of them simultaneously."*

**Reset:** `POST /api/scenario/normal`

---

## 🔴 Scenario GF-2 — Oven Zone 2 Heater Failure

**API:** `POST /api/scenario/oven_zone2_heater_failure`

| Dashboard | Panel | What Changes | Time |
|-----------|-------|-------------|------|
| Plant Overview | **Oven Zone Temperatures** | Zone 2 drops 200°C → 90°C | Immediate |
| Plant Overview | OEE — OV01 | Drops to red | 1–2 min |
| Faults & Alarms | Alarm Events | Spike on oven assets | Immediate |

> **Talking point:** *"Zone 2 drops 110°C. Parts going through right now will be undercured — a quality risk. The MES has placed an automatic batch hold on 156 units. Without this integration, you'd find out during quality inspection, hours later."*

**Reset:** `POST /api/scenario/normal`

---

## 🔴 Scenario GF-3 — Oven Thermal Runaway (Emergency)

**API:** `POST /api/scenario/oven_thermal_runaway`

| Dashboard | Panel | What Changes | Time |
|-----------|-------|-------------|------|
| Plant Overview | **Oven Zone Temperatures** | **All 4 zones spike +20–25°C** | Immediate |
| Plant Overview | OEE — OV01 | Emergency stop | Immediate |
| Faults & Alarms | All zone alarms | Fire simultaneously | Immediate |

> **Talking point:** *"All four zones overshoot simultaneously — this is a temperature controller failure, not a single element. A single-zone failure looks very different. The AI distinguishes these patterns and knows immediately: this requires immediate shutdown, not just a zone setpoint adjustment."*

**Reset:** `POST /api/scenario/normal`

---

## 🟡 Scenario GF-4 — PR01 Hydraulic Pump Wear (Pre-Alarm, Predictive)

**API:** `POST /api/scenario/press_PR01_hydraulic_degradation`

| Dashboard | Panel | What Changes | Time |
|-----------|-------|-------------|------|
| Plant Overview | **Press Hydraulic Pressure** | PR01 slowly declining ~215 → 190 bar | 1–2 min |
| Plant Overview | OEE — PR01 | Drifts green → yellow | 3–5 min |
| Faults & Alarms | Press Fault Indicators | Line crosses yellow zone | 1 min |

> **Key demo point:** *"No alarm has fired. The SCADA threshold is 192 bar — pressure is at 196. Traditional systems see nothing. The AI catches a pump wearing out weeks before it fails. That is the difference between predictive and reactive maintenance."*

**Reset:** `POST /api/scenario/normal`

---

## 🟡 Scenario GF-5 — Energy Anomaly (Compressor Running Inefficiently)

**API:** `POST /api/scenario/energy_anomaly_night_shift`

| Dashboard | Panel | What Changes | Time |
|-----------|-------|-------------|------|
| Power & Energy | **Power Consumption (kW)** | CP01 rises 35% above baseline | Immediate |
| Power & Energy | **THD (%)** | CP01 THD spikes → 8.5% | Immediate |
| Power & Energy | **Power Factor** | CP01 drops to 0.73 | Immediate |

> **Talking point:** *"Compressor running 35% over baseline. Power factor at 0.73 — that's reactive loss on the grid bill. THD at 8.5% causes heat stress on the motor windings. This would only be caught in a monthly energy audit without this monitoring. Annual excess cost: €8,400."*

**Reset:** `POST /api/scenario/normal`

---

## 🔴 Scenario GF-6 — Multi-Asset Cascade (The Flagship — No Alarms Fire)

**API:** `POST /api/scenario/multi_asset_cascade`

This is the most important demo. Show Faults & Alarms + Plant Overview side by side.

| Signal | Value | Alarm threshold | Status |
|--------|-------|-----------------|--------|
| PR01 hydraulic pressure | 195 bar | 192 bar | ✅ No alarm |
| PR01 press force deviation | +3.8% | 8% threshold | ✅ No alarm |
| OV01 zone 3 temp | +6°C | +15°C threshold | ✅ No alarm |
| CMM defect rate | 18% | 20% threshold | ✅ No alarm |

> **Talking point:** *"Every. Single. Alarm. Is. Green. But we have an 18% defect rate, costing €5,040 in scrap right now. No single threshold was exceeded. Only by correlating four signals across three systems does the picture emerge. This is why you need more than dashboards. You need context."*

**That context is Layer 3 — TerminusDB.**

**Reset:** `POST /api/scenario/normal`

---

## 🔴 Scenario GF-7 — Quality Escape (Multi-Variate Root Cause)

**API:** `POST /api/scenario/quality_escape`

Three signals, all inside thresholds, all slightly off:
- PR01 force deviation: +4.1% (alarm at 8%)
- OV01 zone 3: +8°C (alarm at +15°C)
- PR01 die wear: 72% (alarm at 90%)
- CMM defect rate: 18% (alarm at 20%)

> **Talking point:** *"18% defect rate but no alarm fired. The combination of three sub-threshold signals creates a tolerance stack-up that pushes parts out of spec. This is the scenario that costs companies millions — a quality escape where no individual signal alarmed, but the combination was fatal. Only AI on top of the UNS can detect this."*

**Reset:** `POST /api/scenario/normal`

---

## 🟡 Scenario GF-8 — Compressed Air Leak (Invisible Without Correlation)

**API:** `POST /api/scenario/compressed_air_leak`

| Dashboard | Panel | What Changes | Time |
|-----------|-------|-------------|------|
| Power & Energy | **Power Consumption** | CP01 line rises (overcompensating) | Immediate |
| Faults & Alarms | Compressor Outlet | Pressure drops, temp rises | 1 min |

> **Talking point:** *"The leak is in the pneumatic pipe network — there's no direct sensor on the leak itself. But the compressor running at 95% load instead of 65% is the tell. Combined with zone pressure differential, the AI pinpoints the leak location to within 10 metres. One invisible problem, visible through a correlating signal."*

**Reset:** `POST /api/scenario/normal`

---

# 6. LEVEL 3 — TerminusDB: Adding Context & Relationships

## What TerminusDB Adds to the Stack

Grafana answers *"What is happening?"* TerminusDB answers *"WHY is it happening and what is connected?"*

### The Fundamental Limitation of Time-Series Databases

InfluxDB is outstanding at answering: *"What was press PR01's hydraulic pressure over the last hour?"*

It cannot answer:
- *"What other assets are affected if PR01 fails?"*
- *"How many times has this scenario been active in the last 30 days?"*
- *"Trace the causal chain from the CMM defect rate back to the root cause"*
- *"What work orders were open during the cascade failure?"*

These are **graph questions**. TerminusDB is a graph database.

### The TerminusDB Graph Structure

```
Plant ──contains──→ Line 01 ──contains──→ press_PR01
                                                │
                              ──feeds──────→ conveyor_CV01
                                                │
                              ──feeds──────→ oven_OV01
                                                │
                              feeds─────────→ CMM01

FaultScenario/multi_asset_cascade
  ──affected_assets──→ [press_PR01, vision_CMM01]
  ──ai_hint──────────→ "Hydraulic seal -15 bar → force +3.8% → 18% CMM fail"
  ──severity─────────→ critical

ScenarioEvent [timestamped activations — git-versioned history]
  ──scenario──→ FaultScenario/multi_asset_cascade
  ──activated_at──→ 2026-04-21T10:28:57Z
  ──triggered_by──→ api

PlantState [single document, always current]
  ──active_scenario──→ FaultScenario/multi_asset_cascade
  ──last_updated──────→ 2026-04-21T10:28:57Z
```

### InfluxDB vs TerminusDB vs AAS — Side by Side

| Dimension | InfluxDB | TerminusDB | BaSyx AAS |
|-----------|----------|------------|-----------|
| **Data type** | Measurements (numbers) | Relationships & events | Identity & specs |
| **Time model** | Time series (rolling 30d) | Git-versioned history | Versioned (permanent) |
| **Query** | Flux (`from(bucket:...)`) | WOQL graph traversal | REST / AASX |
| **AI use case** | *"Show me the trend"* | *"What caused this cascade?"* | *"What are the specs?"* |
| **Update rate** | Every 5 seconds | Event-driven | Lifecycle only |
| **Alarm vs insight** | Alarm | Diagnosis | Compliance |

---

## The TerminusDB Demo — "The Graph Knows"

### Setup: Build some history first

```bash
KEY="acf894b44d993ad68df2d06efe28593c"
BASE="https://aurora-api.iotdemozone.com"

curl -sX POST $BASE/api/scenario/press_PR01_hydraulic_degradation -H "X-API-Key: $KEY" && sleep 8
curl -sX POST $BASE/api/scenario/normal -H "X-API-Key: $KEY" && sleep 5
curl -sX POST $BASE/api/scenario/conveyor_cv01_jam -H "X-API-Key: $KEY" && sleep 8
curl -sX POST $BASE/api/scenario/normal -H "X-API-Key: $KEY" && sleep 5
curl -sX POST $BASE/api/scenario/multi_asset_cascade -H "X-API-Key: $KEY" && sleep 8
curl -sX POST $BASE/api/scenario/normal -H "X-API-Key: $KEY"
```

### Query 1: What is the current plant state?

```bash
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=PlantState" \
  -u "admin:8Cv7R#ME" | python3 -m json.tool
```
Returns: `active_scenario`, `last_updated`, `mqtt_connected`

> *"One API call. Current scenario, last update time, system health. An AI agent can check this in its first tool call and immediately knows the context before looking at a single metric."*

### Query 2: What has happened today? (Scenario history)

```bash
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora?type=ScenarioEvent&count=20" \
  -u "admin:8Cv7R#ME" | python3 -c "
import sys, json
for line in sys.stdin:
    if line.strip():
        try:
            e = json.loads(line)
            print(f'{e[\"activated_at\"]} → {e[\"scenario\"].split(\"/\")[-1]}')
        except: pass"
```

> *"TerminusDB keeps a full git-versioned history of every scenario activation. Not just 'a fault happened' — but which fault, when, triggered by whom. You can answer: how many times did this fault occur in the last 30 days? Was it the same shift? Same product batch?"*

### Query 3: Why did the cascade happen? (Context query)

```bash
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora/FaultScenario/multi_asset_cascade" \
  -u "admin:8Cv7R#ME" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('Scenario:', d['scenario_id'])
print('Severity:', d['severity'])
print('AI Hint:', d['ai_hint'])
print('Affected:', [a.split('/')[-1] for a in d.get('affected_assets',[])])"
```

Returns the full context: description, ai_hint, root cause, affected assets.

> *"The graph database is the AI's memory. It doesn't just record the alarm — it stores the full causal chain, the recommended actions, and the € impact. The AI doesn't need to work this out — it was written in at seed time."*

### Query 4: What the Grafana TerminusDB panels show live

Open **Grafana → Faults & Alarms** and scroll to the bottom section:

| Panel | What it shows |
|-------|--------------|
| 📋 **Scenario Event History** | Timestamped list of all scenario activations, auto-updating |
| 🏭 **Asset Operational Status** | All 22 assets with health score, status, area (color-coded) |
| 🔍 **Active Scenario AI Context** | Current scenario: label, severity, ai_hint, root cause |

> *"This panel updates automatically. The moment you trigger a scenario, the AI Context panel shows you what the AI knows about it — before you've asked a single question."*

---

## 🔴 Scenario TD-1 — Cascade with TerminusDB Context (The Full Story)

**API:** `POST /api/scenario/multi_asset_cascade`

### Layer 1 — What you see in Grafana (InfluxDB)
Four signals, all inside alarm thresholds. 18% defect rate. No single alarm.

### Layer 2 — What TerminusDB tells you immediately

```bash
# What does the graph know?
curl -s "https://terminusdb.iotdemozone.com/api/document/admin/aurora/FaultScenario/multi_asset_cascade" \
  -u "admin:8Cv7R#ME" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('AI Hint:', d['ai_hint'][:200])
print('Severity:', d['severity'])
print('Root Cause:', d.get('root_cause','?')[:100])"
```

### Combined answer (what AI would say)
*"Hydraulic seal is leaking (TerminusDB: affected=PR01). This reduces press force by 3.8% (InfluxDB: live trend). Force deviation causes +0.3mm wall thickness variance. CMM detecting 18% fail rate (InfluxDB: CMM stream). Root cause is PR01 MainSeal, not CMM. Fix: replace MainSeal (€180, 2h) → defect rate returns to 3%."*

**Reset:** `POST /api/scenario/normal`

---

# 7. LEVEL 4 — Digital Twin (AAS): Asset Identity & Specs

## What BaSyx AAS Adds

TerminusDB answers *"What role does this asset play and what happened?"*. BaSyx AAS answers *"What IS this asset — its permanent identity, specs, and certifications?"*

### The Three-Layer Information Stack

```
AAS says:          press_PR01 / Manufacturer: SCHULER / RatedForce: 2500 kN
                   Hydraulic pump rated life: 18 months / Last service: 14 months ago
                       ↓ aas_id link
TerminusDB says:   press_PR01 feeds CV01 / health_score: 71% / 12 ScenarioEvents
                       ↓ asset_id tag
InfluxDB says:     pressure: 186.2 bar / oee: 0.76 / cycle_time: 4.8s
```

**Together:** *"The pump is 78% through its 18-month rated life (AAS), pressure is declining at -0.8 bar/day (InfluxDB), and the graph shows CV01 and Line 01 output are next in the causal chain if this pump fails (TerminusDB). Replace it now for €420. Wait and it costs €6,000 + 4h downtime."*

### BaSyx AAS Submodels in Aurora

Each of Aurora's 22 assets has an AAS shell with these submodels:

| Submodel | Contains | AI uses it for |
|----------|---------|----------------|
| **NameplateData** | Manufacturer, model, serial, InstallDate | *"Is this press under warranty?"* |
| **TechnicalData** | RatedForce, ratedSpeed, tolerances, sensor specs | *"What's the rated life of this seal?"* |
| **MaintenanceData** | Last service dates, service intervals, next scheduled | *"Is the pump 78% through its rated life?"* |
| **OperationalData** | RunHours, cycleCount, OEE history | *"How many cycles has this die completed?"* |
| **EnergyEfficiency** | Rated power factor, rated kW, rated THD | *"Is the compressor operating within spec?"* |
| **DPP** | Product passport for every unit produced | *"Which batch was this part from? What were the process conditions?"* |

### Demo: AAS + TerminusDB + InfluxDB Together

**Scenario:** PR01 Hydraulic Degradation

```bash
POST /api/scenario/press_PR01_hydraulic_degradation
```

**Step 1 — InfluxDB (Grafana) shows:** Pressure declining from 215 → 190 bar over 5 min

**Step 2 — TerminusDB says:** FaultScenario `press_PR01_hydraulic_degradation`:
- `ai_hint`: "Pressure trending down -0.8 bar/day over 3 days. Pump efficiency -12%."
- `severity`: warning
- `affected_assets`: press_PR01

**Step 3 — BaSyx AAS says:** press_PR01 → MaintenanceData:
- Hydraulic pump last serviced: 14 months ago
- Rated pump life: 18 months
- **Pump is 78% through rated service life**

**Combined AI answer:**
> *"PR01 hydraulic pump is 78% through its 18-month rated life (AAS). Pressure declining -0.8 bar/day (InfluxDB trend). If this pump fails: CV01 and Line 01 output stop (TerminusDB graph). Preventive replacement: €420 + 4h scheduled. Unplanned failure: €2,800 repair + €4,200 production loss + 180 units scrapped. ROI of acting now: 14:1."*

**Reset:** `POST /api/scenario/normal`

---

## Digital Product Passport (DPP) Demo

**API:**
```bash
# Start from normal state
POST /api/scenario/normal
# Then trigger DPP generation
POST /api/trigger_dpp
```

**What happens:**
1. MES batch-complete event fires on MQTT
2. DPP submodel in BaSyx AAS updates with: batch_id, units_passed, FPY%, process conditions
3. Grafana MES/Batch dashboard shows the DPP event
4. InfluxDB `aurora_dpp` measurement records it with full lineage

> **Talking point:** *"EU Battery Regulation 2023/1542 requires a Digital Product Passport for every battery casing shipped. This is not a manual report — it's generated automatically from the live UNS data. Every sensor reading, every work order, every quality result, linked to each unit. Fully traceable. Audit-ready."*

---

# 8. LEVEL 5 — AI: The Intelligent Layer

## What AI Adds to the Complete Stack

With all four layers in place, an AI agent has everything it needs:
- **UNS/InfluxDB** → 111 live streams, trends, anomalies
- **TerminusDB** → Causal context, scenario history, affected assets, AI hints
- **BaSyx AAS** → Asset specs, rated lives, maintenance records
- **Grafana** → Visual confirmation the AI can reference

An AI agent can answer questions that would take a human engineer 2–3 hours to investigate — **in under 3 seconds**.

---

## Sample AI Agent Queries and Answers

### Query 1: "What is happening at Aurora right now?"

AI calls:
1. `GET /api/status` (or TerminusDB PlantState) → `active_scenario: multi_asset_cascade`
2. TerminusDB: `FaultScenario/multi_asset_cascade` → ai_hint, affected_assets
3. InfluxDB: last 5 min of PR01 pressure + CMM defect rate

**Answer:** *"Aurora plant is in a multi-asset cascade event. Press PR01 hydraulic seal is leaking — pressure at 195 bar (down from 210 normal), causing +3.8% force deviation. CMM defect rate is 18%. Affected assets: PR01, CMM01. No individual alarm has fired. Estimated loss: €210/min. Recommended action: replace PR01 MainSeal immediately."*

---

### Query 2: "Give me the full maintenance context for press PR01"

AI calls:
1. BaSyx AAS: press_PR01 → MaintenanceData + TechnicalData
2. TerminusDB: `Asset/press_PR01` → health_score, last ScenarioEvents
3. InfluxDB: PR01 OEE + pressure trend, last 7 days

**Answer:** *"PR01: SCHULER press, RatedForce 2500 kN, installed 22 months ago. Hydraulic pump: 78% through 18-month rated life — overdue for service. Health score: 71% (TerminusDB). Last 30 days: 3 fault activations (2× hydraulic degradation, 1× cascade). OEE trending down from 85% to 76% over 14 days (InfluxDB). Immediate: schedule hydraulic pump replacement. Next scheduled maintenance: overdue by 4 months."*

---

### Query 3: "We have an 18% defect rate at CMM. What's the root cause?"

AI calls:
1. TerminusDB: query graph for scenarios with vision_CMM01 in affected_assets
2. InfluxDB: correlate CMM defect rate with PR01 force deviation + OV01 zone 3 over past hour
3. BaSyx AAS: vision_CMM01 → CalibrationData (last calibration date)
4. TerminusDB: ScenarioEvent history for multi_asset_cascade + quality_escape

**Answer:** *"Root cause is not the CMM — it's upstream. PR01 press force deviation is +4.1% (InfluxDB), OV01 zone 3 running +8°C over setpoint (InfluxDB). Combined tolerance stack pushes 18% of parts outside spec. CMM calibration also overdue by 2 weeks (AAS). Historical: this pattern last appeared 12 days ago — same shift, same scenario (TerminusDB history). Actions: (1) Adjust PR01 force setpoint -4%, (2) Reset OV01 zone 3 PID, (3) Schedule CMM calibration today."*

---

## Why This Combination is Uniquely Powerful

> **"Why not just use one tool?"**

| Tool alone | What it can't answer |
|-----------|---------------------|
| InfluxDB only | *"Why is this happening? What should I do?"* |
| TerminusDB only | *"What are the actual numbers right now?"* |
| AAS only | *"What is the current operating state?"* |
| AI without all three | Hallucinations, generic answers, no plant-specific context |
| **All three + AI** | **Any question, any depth, in < 3 seconds** |

The UNS is the nervous system. InfluxDB is the short-term memory. TerminusDB is the reasoning engine. AAS is the reference library. AI is the analyst. **Together they are the autonomous operations team that never sleeps.**

---

# 9. Complete Scenario Playbook

## Scenario Reference Table

| ID | Label | Severity | Category | Best For |
|----|-------|----------|----------|----------|
| `normal` | Normal Operation | info | Baseline | Always start here |
| `conveyor_cv01_jam` | CV01 Belt Jam | critical | Hard fault | Executive demo |
| `oven_zone2_heater_failure` | OV01 Zone 2 Heater Failure | critical | Hard fault | MES/batch demo |
| `oven_thermal_runaway` | OV01 Thermal Runaway | critical | Emergency | AI distinguish demo |
| `press_PR01_hydraulic_degradation` | PR01 Hydraulic Pump Wear | warning | Predictive | Predictive maintenance |
| `multi_asset_cascade` | Cascade Failure | critical | Multi-system | Flagship demo |
| `quality_escape` | Quality Escape (Multi-Variate) | critical | Root cause | AI demo |
| `robot_R1_weld_drift` | R1 Weld Robot TCP Drift | warning | Predictive | AI trend demo |
| `robot_R3_spray_drift` | R3 Spray Robot TCP Drift | warning | Predictive | Quality + robot demo |
| `paint_filter_blockage` | SP02 Paint Filter Blockage | warning | Predictive | Predictive maintenance |
| `tooling_die_wear` | PR01 Die Wear | warning | Predictive | Lifecycle demo |
| `compressed_air_leak` | Compressed Air Leak | warning | Energy | Energy/correlation demo |
| `energy_anomaly_night_shift` | Compressor Energy Anomaly | warning | Energy | Energy/ESG demo |
| `erp_material_shortage` | ERP Material Shortage | warning | ERP/MES | IT/OT integration demo |
| `batch_quality_hold` | Batch Quality Hold + DPP | critical | MES/DPP | Compliance/DPP demo |
| `biw_weld_robot1_fault` | BIW Weld Robot1 Fault | warning | Quality | Paint shop demo |
| `ecoat_bath_contamination` | ECoat Bath Contamination | warning | Quality | Paint shop demo |
| `agv_fleet_battery_low` | AGV Fleet Battery Low | warning | Logistics | Intralogistics demo |
| `body_shop_robot1_collision` | Body Shop Robot E-Stop | critical | Safety | Safety demo |
| `cross_site_erp_disruption` | Cross-Site ERP Disruption | warning | ERP | Supply chain demo |

---

## All Scenarios — Full Technical Detail

### 🟢 Normal Operation
**What to show:** Nav Home OEE tiles all green, Plant Overview all values at setpoint
**Value statement:** "This is the reference state. Everything that follows is deviation from this baseline."

---

### 🔴 CV01 Belt Jam
**API:** `POST /api/scenario/conveyor_cv01_jam`

Speed → 0 m/s. Motor current spikes then drops. Tension collapses. Press PR01 starves in 90 seconds.
**Value:** Cascade detection — one event causes downstream effects across 4 assets.
**€ impact:** €210/min while jam persists. Typical undetected duration: 20 min = €4,200.

---

### 🔴 OV01 Zone 2 Heater Failure
**API:** `POST /api/scenario/oven_zone2_heater_failure`

Zone 2 drops from 200°C to 90°C immediately. MES places batch hold (156 units).
**Value:** Automatic batch hold prevents shipping undercured parts. Without integration: quality failure discovered at customer.
**€ impact:** 156 units at risk = €4,368 scrap avoided.

---

### 🔴 OV01 Thermal Runaway
**API:** `POST /api/scenario/oven_thermal_runaway`

All 4 zones spike +20–25°C simultaneously. Controller fault, not element failure.
**Value:** AI pattern distinguishes controller fault from single element failure. Different root cause, different repair.
**€ impact:** Emergency shutdown vs scheduled repair = €12,000 vs €800.

---

### 🟡 PR01 Hydraulic Degradation (Predictive)
**API:** `POST /api/scenario/press_PR01_hydraulic_degradation`

Pressure slowly declines from 215 → 190 bar. No alarm fires (threshold 192 bar).
**Value:** Pre-alarm detection. AI catches the trend, not the threshold breach.
**€ impact:** Preventive pump replacement €420 vs unplanned failure €6,000 + 4h downtime.

---

### 🔴 Multi-Asset Cascade (No Alarms Fire)
**API:** `POST /api/scenario/multi_asset_cascade`

PR01 seal leak → force deviation → wall thickness out of spec → CMM 18% fail rate. Zero alarms.
**Value:** The flagship: correlation of 4 sub-threshold signals. Only possible with UNS + graph context.
**€ impact:** 180 units scrap × €28 = €5,040 if undetected per shift.

---

### 🔴 Quality Escape (Multi-Variate)
**API:** `POST /api/scenario/quality_escape`

PR01 force +4.1%, OV01 zone 3 +8°C, die wear 72%. Tolerance stack = 18% defect rate. No alarms.
**Value:** Multi-variate root cause detection. No single system can identify this — requires UNS correlation.
**€ impact:** €500/hr quality loss if undetected. Detection ROI: find in 3 seconds vs 3 hours of investigation.

---

### 🟡 Robot R1 Weld Drift (Predictive)
**API:** `POST /api/scenario/robot_R1_weld_drift`

Position error drifts from 0.1mm → 0.85mm over 5 minutes.
**Value:** 0.85mm on a structural weld joint = potential defect. AI detects the drift trend before weld failures appear downstream.
**€ impact:** Teach-point recalibration: 30 min. Undetected weld defects: 100% scrap + potential recall.

---

### 🟡 SP02 Paint Filter Blockage (Predictive)
**API:** `POST /api/scenario/paint_filter_blockage`

Filter ΔP rises toward 0.5 bar. Coat thickness starts declining 2 minutes later.
**Value:** Leading vs lagging indicator. ΔP is the early warning; coat thickness is the failure. Traditional monitoring only catches the latter.
**€ impact:** Scheduled filter change: €150. Undetected → coat thickness below spec → repaint or scrap: €3,200/batch.

---

### 🟡 Die Wear / Tooling Lifecycle
**API:** `POST /api/scenario/tooling_die_wear`

Die wear % climbing toward 70% (alarm at 90%). Hydraulic pressure variance widening.
**Value:** Predictive lifecycle management. AI predicts the exact cycle count where Cpk falls below 1.0.
**€ impact:** Planned die replacement: 4h scheduled = €1,200. Unplanned failure: 8h emergency + 400 scrapped parts = €21,200.

---

### 🟡 Compressed Air Leak
**API:** `POST /api/scenario/compressed_air_leak`

CP01 load rises from 65% → 95%. Outlet pressure drops, temperature rises.
**Value:** The leak is invisible directly — only the compressor's overload reveals it. Cross-signal correlation.
**€ impact:** Leak detection and sealing: €800. Continuous undetected operation: €3,500/year energy + compressor life reduction.

---

### 🟡 Energy Anomaly — Compressor Night Shift
**API:** `POST /api/scenario/energy_anomaly_night_shift`

CP01 power +35%, THD 8.5%, power factor 0.73.
**Value:** Energy and ESG monitoring without a separate energy management system. UNS carries energy data alongside process data.
**€ impact:** €8,400/year excess energy. THD damage to motor windings: €15,000 motor replacement if undetected.

---

### 🟡 ERP Material Shortage (IT/OT Integration)
**API:** `POST /api/scenario/erp_material_shortage`

ALU sheet inventory below safety stock. MES blocks new work orders. Press lines continue on current WO.
**Value:** ERP-to-OT integration in action. Supply chain event visible on plant floor 47 minutes before starvation — not after.
**€ impact:** 47-min advance warning = time to issue emergency purchase order. Without integration: line stops = €210/min × 60 min = €12,600.

---

### 🔴 Batch Quality Hold + DPP
**API:** `POST /api/scenario/batch_quality_hold` then `POST /api/trigger_dpp`

OV01 zone 2 -45°C. MES batch hold (156 units). ERP updates production order. DPP flags all 156 units.
**Value:** Full vertical integration: process fault → automatic batch hold → DPP flagging → traceability record. Zero manual intervention.
**€ impact:** 156 units protected from shipping undercured. €4,368 quality liability avoided. EU Battery Regulation compliance maintained.

---

# 10. Demo Flow Templates

## ⚡ 5-Minute Executive Demo

> One story: from raw data to AI diagnosis. No technical details needed.

| Time | Action | Talking Point |
|------|--------|--------------|
| 0:00 | Open **Nav Home** | *"79% OEE across the plant. 111 streams, live, 5-second updates."* |
| 0:45 | `POST /api/scenario/conveyor_cv01_jam` | *"Watch: one conveyor jams."* |
| 1:00 | Switch to **Asset Telemetry** | *"CV01 drops to zero instantly. Watch the press behind it start losing OEE."* |
| 1:30 | Open **Faults & Alarms** → TerminusDB panel | *"The knowledge graph already knows: CV01 jam → Press PR01 starved → Line 01 affected. No human traced that."* |
| 2:30 | Reset. `POST /api/scenario/multi_asset_cascade` | *"Now the flagship: four signals, all inside alarm thresholds. 18% defect rate."* |
| 3:00 | Show all 4 signal values | *"Every alarm is green. But we're losing €210 a minute in scrap."* |
| 3:30 | Show TerminusDB AI Context panel in Grafana | *"The AI context panel already says: root cause is PR01 MainSeal. €180 fix. Find it in 3 seconds vs 3 hours."* |
| 4:30 | Show € impact table | *"Annual value: €180–400k per plant, depending on size."* |
| 5:00 | Reset | Done |

---

## 🕒 15-Minute Technical Demo (7 Scenarios + 3 Layers)

| Time | Scenario | Focus | Key Point |
|------|---------|-------|-----------|
| 0:00–1:30 | Normal | Nav Home + all 4 dashboards | Baseline — "79% OEE, everything green" |
| 1:30–3:30 | CV01 Jam | Asset Telemetry + Faults | Hard fault, cascade detection |
| 3:30–5:00 | PR01 Degradation | Plant Overview + TerminusDB | Pre-alarm predictive — no threshold crossed |
| 5:00–7:00 | Multi-Asset Cascade | All dashboards + TerminusDB | The flagship: 4 sub-threshold signals |
| 7:00–9:00 | Quality Escape | Faults + TerminusDB | Multi-variate root cause |
| 9:00–11:00 | Energy Anomaly | Power & Energy + AAS | Energy/ESG + compressor spec |
| 11:00–13:00 | Batch Quality Hold + DPP | MES/Batch + BaSyx | Compliance, DPP, traceability |
| 13:00–15:00 | AI Q&A | All layers together | *"Ask me anything about the plant"* |

---

## 🔬 30-Minute Deep-Dive (for AI/Data Architects)

| Time | Topic |
|------|-------|
| 0–5 min | UNS architecture: topic structure, 111 streams, MQTT → InfluxDB pipeline |
| 5–10 min | TerminusDB schema walkthrough: Asset, FaultScenario, ScenarioEvent, PlantState classes |
| 10–15 min | Live graph queries: PlantState, ScenarioEvent history, WOQL asset traversal |
| 15–20 min | BaSyx AAS submodels: how `aas_id` links all three layers |
| 20–25 min | Cascade scenario: show all 4 layers simultaneously |
| 25–30 min | AI agent demo: natural-language queries → cross-layer synthesis |

---

## 🎯 Audience-Specific Openers

| Audience | Start with | Lead with |
|----------|-----------|-----------|
| **Plant Manager** | Nav Home OEE tiles | *"You're running at 79%. These 5 scenarios cost you €180k/year."* |
| **IT/OT Architect** | MQTT topic structure | *"6 systems, one broker. Zero point-to-point integrations."* |
| **AI/Data Team** | TerminusDB WOQL query | *"Graph traversal across assets and causal chains in one API call."* |
| **C-Suite** | € impact table | *"3 fault types prevented = €180k–400k annually per plant."* |
| **Compliance/Legal** | DPP trigger demo | *"EU Battery Regulation 2023/1542 — every unit, fully traceable, automated."* |

---

# 11. The Value Story in Numbers

| Scenario | Without This Stack | With This Stack | Annual Value per Plant |
|----------|-------------------|-----------------|----------------------|
| PR01 pump wear (predictive) | €6,000 unplanned failure + 4h downtime | €420 preventive | **€5,580 × 3 occurrences = €16,740** |
| CV01 belt jam | 20 min detection + 15 min recovery | Instant detection, 8 min recovery | **€2,520 per event × 12/year = €30,240** |
| Multi-asset cascade (no alarm) | 3h root cause investigation + 180 units scrap | Root cause in 3s, batch held | **€5,040/event × 24/year = €120,960** |
| Oven zone failure | Batch shipped undercured → recall risk | Automatic MES batch hold | **€14,040 protected per event × 6/year = €84,240** |
| Energy anomaly | Annual energy audit finds it 6 months late | Detected in hours | **€8,400/year energy + €15k motor life** |
| Quality escape | 2h investigation + 400 units risk | Detected in 3s, traced to root | **€50k/year investigation cost eliminated** |
| **Total** | | | **€180k–€400k/year per plant** |

### The OEE Calculation

A plant running at 79% OEE with this stack achieves:
- **+2–4% OEE** from predictive fault prevention (preventing unplanned downtime)
- **+1–2% OEE** from faster root cause analysis (reducing MTTR)
- **+0.5–1% OEE** from energy optimisation (less downtime due to energy faults)

**At Aurora's scale (annual output: ~€50M revenue), every 1% OEE = ~€500k.**
This stack targets a **3–5% OEE improvement = €1.5M–€2.5M annual value.**

---

# 12. Talking Points Cheat Sheet

## "Why not just use SCADA/existing tools?"

> *"SCADA monitors one system at a time. When the cascade failure happened — PR01 pressure at 195 bar, CMM at 18% defect rate — every SCADA alarm was green. You need correlation across systems, and SCADA was never designed for that. The UNS gives you a single namespace; TerminusDB gives you the relationships. That's the combination SCADA can never replicate."*

## "Why not just use Grafana alerts?"

> *"Grafana alerts fire when a single value crosses a threshold. TerminusDB answers: which assets are affected, what's the causal chain, how many times has this happened, and what did we do last time. That's the difference between an alarm and a diagnosis. Grafana tells you a pipe is leaking. TerminusDB tells you which pipe, what it feeds, and how to fix it."*

## "Why TerminusDB specifically?"

> *"Three reasons: (1) It's a graph database — asset relationships are first-class, not a workaround. (2) Git-style versioning — every change is committed with author and timestamp. You can branch the asset graph, make changes, and merge — same as code. (3) WOQL — a composable query language that traverses multi-hop relationships that SQL cannot express in a single query."*

## "Why BaSyx AAS?"

> *"AAS carries the asset's permanent identity — the things that don't change every 5 seconds. When the AI says 'the hydraulic pump is 78% through its rated life', that rated life number comes from AAS, not from a dashboard. It's also the EU's preferred format for Digital Product Passports — if you're building toward Battery Regulation or Ecodesign Regulation compliance, AAS is where you need to be."*

## "How does this scale to 10 plants?"

> *"Every new asset added to BaSyx automatically becomes a node in the TerminusDB graph. Every MQTT topic it publishes gets the same `asset_id` tag — visible in InfluxDB immediately. One `aas_id` field links all three layers. Add a robot — it appears in all three systems automatically. Add a plant — replicate the stack, federate the namespaces. We've designed this to scale horizontally from day one."*

## "What does the AI actually do — isn't it just pattern matching?"

> *"The AI has three things most AI systems don't have when applied to manufacturing: (1) Real-time data via InfluxDB — not stale reports. (2) Causal context via TerminusDB — the graph knows which assets cause which failures. (3) Asset knowledge via AAS — rated specs, maintenance history, certifications. Without all three, AI gives you generic answers. With all three, it gives you plant-specific, actionable recommendations in 3 seconds."*

---

# 13. Quick Reference — All APIs

```bash
KEY="acf894b44d993ad68df2d06efe28593c"
BASE="https://aurora-api.iotdemozone.com"
TBASE="https://terminusdb.iotdemozone.com/api/document/admin/aurora"
TAUTH="-u admin:8Cv7R#ME"

# ── SIMULATOR CONTROLS ──────────────────────────────────────────────────
curl -X POST $BASE/api/start     -H "X-API-Key: $KEY"   # Start publishing
curl -X POST $BASE/api/stop      -H "X-API-Key: $KEY"   # Stop publishing
curl -X POST $BASE/api/reset     -H "X-API-Key: $KEY"   # Reset + normal
curl -X POST $BASE/api/trigger_dpp -H "X-API-Key: $KEY" # Fire DPP event
curl -s        $BASE/health                              # Check health

# ── SCENARIOS — RESET ────────────────────────────────────────────────────
curl -sX POST $BASE/api/scenario/normal               -H "X-API-Key: $KEY"

# ── SCENARIOS — HARD FAULTS ──────────────────────────────────────────────
curl -sX POST $BASE/api/scenario/conveyor_cv01_jam         -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/oven_zone2_heater_failure -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/oven_thermal_runaway      -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/body_shop_robot1_collision -H "X-API-Key: $KEY"

# ── SCENARIOS — PREDICTIVE ───────────────────────────────────────────────
curl -sX POST $BASE/api/scenario/press_PR01_hydraulic_degradation -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/paint_filter_blockage            -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/tooling_die_wear                 -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/robot_R1_weld_drift              -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/robot_R3_spray_drift             -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/compressed_air_leak              -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/primer_robot_bearing             -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/clearcoat_electrode_wear         -H "X-API-Key: $KEY"

# ── SCENARIOS — CASCADE & MULTI-SYSTEM ──────────────────────────────────
curl -sX POST $BASE/api/scenario/multi_asset_cascade   -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/quality_escape        -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/biw_weld_robot1_fault -H "X-API-Key: $KEY"

# ── SCENARIOS — ENERGY ───────────────────────────────────────────────────
curl -sX POST $BASE/api/scenario/energy_anomaly_night_shift -H "X-API-Key: $KEY"

# ── SCENARIOS — ERP/MES ──────────────────────────────────────────────────
curl -sX POST $BASE/api/scenario/erp_material_shortage      -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/cross_site_erp_disruption  -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/batch_quality_hold         -H "X-API-Key: $KEY"

# ── SCENARIOS — PAINT SHOP ───────────────────────────────────────────────
curl -sX POST $BASE/api/scenario/ecoat_bath_contamination    -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/pretreatment_filter_clog    -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/pretreatment_tank_overheat  -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/curing_oven_temp_runaway    -H "X-API-Key: $KEY"
curl -sX POST $BASE/api/scenario/agv_fleet_battery_low       -H "X-API-Key: $KEY"

# ── TERMINUSDB QUERIES ───────────────────────────────────────────────────
# Current plant state
curl -s "$TBASE?type=PlantState" $TAUTH | python3 -m json.tool

# Scenario event history (last 20)
curl -s "$TBASE?type=ScenarioEvent&count=20" $TAUTH | \
  python3 -c "import sys,json; [print(json.loads(l)['activated_at'],'→',json.loads(l)['scenario'].split('/')[-1]) for l in sys.stdin if l.strip()]"

# Specific scenario definition + AI hints
curl -s "$TBASE/FaultScenario/multi_asset_cascade" $TAUTH | python3 -m json.tool

# All assets
curl -s "$TBASE?type=Asset&count=30" $TAUTH | \
  python3 -c "import sys,json; [print(json.loads(l).get('asset_id','?'), json.loads(l).get('area','?'), json.loads(l).get('health_score','?')) for l in sys.stdin if l.strip()]"
```

---

*Aurora Industries Digital Twin Demo — Master Guide*
*Stack: UNS (MQTT) → InfluxDB → Grafana | TerminusDB | BaSyx AAS | AI*
*Last updated: 2026-04-21 | uns-simulator main branch*
