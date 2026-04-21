# Aurora Industries — Grafana Demo Guide
## "Push This Button, Watch That Graph"

> **Quick start:** Open the simulator UI, open Grafana Nav Home side-by-side, set time range to **Last 15 minutes**, and enable **10s auto-refresh** on all dashboards.

---

## Dashboard Quick Reference

| Dashboard | URL | Best For |
|-----------|-----|----------|
| **Nav Home** | `/d/aurora-nav-home` | Start here — live KPIs + 1-click navigation |
| **4. Plant Overview** | `/d/aurora-plant-overview` | OEE, press pressures, oven temps, production |
| **5. Asset Telemetry** | `/d/aurora-asset-telemetry` | Conveyor speeds, robot accuracy, sprayer flow |
| **6. Power & Energy** | `/d/aurora-power-monitoring` | kW per asset, power factor, THD, grid frequency |
| **7. Faults & Alarms** | `/d/aurora-faults-alarms` | Scenario timeline, jam events, fault indicators |

**Grafana:** `https://grafana.iotdemozone.com`  
**Simulator UI:** `http://aurora.iotdemozone.com:8081` (or `http://localhost:8081`)

---

## Simulator Controls

The Aurora simulator UI has a **Scenario** dropdown and buttons at the top. Each button calls:

```
POST /api/scenario/{scenario_id}
```

You can also trigger scenarios via API directly:
```bash
curl -X POST http://aurora.iotdemozone.com:8081/api/scenario/conveyor_cv01_jam
curl -X POST http://aurora.iotdemozone.com:8081/api/scenario/normal  # reset
```

Other controls:
| Button | API | What It Does |
|--------|-----|-------------|
| **Start** | `POST /api/start` | Begin publishing all 111 streams |
| **Stop** | `POST /api/stop` | Pause publishing |
| **Reset** | `POST /api/reset` | Back to normal, counters zeroed |
| **Trigger DPP** | `POST /api/trigger_dpp` | Fire a batch-complete DPP event |

---

## Scenario-by-Scenario Demo Playbook

---

### 🟢 SCENARIO 1 — Normal Operation (Baseline)

**Simulator button:** `Normal Operation`  
**API:** `POST /api/scenario/normal`

**What to show in Grafana:**

| Dashboard | Panel | What You See |
|-----------|-------|-------------|
| **Plant Overview** | OEE — PR01 / PR02 / OV01 | Green tiles, ~85%+ OEE |
| **Plant Overview** | OEE History | Flat stable lines |
| **Plant Overview** | Press Hydraulic Pressure | PR01/PR02 holding steady ~200–220 bar |
| **Plant Overview** | Oven Zone Temperatures | All 4 zones stable at setpoint ~200°C |
| **Asset Telemetry** | Conveyor Speed History | All CVs running at design speed |
| **Power & Energy** | Power Factor | All assets ≥ 0.95 |

**Demo talking point:** *"This is your baseline — everything green. Any deviation from these patterns is signal."*

---

### 🟡 SCENARIO 2 — PR01 Hydraulic Pump Wear (Early Stage)

**Simulator button:** `PR01 — Hydraulic Pump Wear`  
**API:** `POST /api/scenario/press_PR01_hydraulic_degradation`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana — open these panels:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | **Press Hydraulic Pressure (bar)** | PR01 line starts a **slow decline** from ~215 bar toward 190 bar | 1–2 min |
| **Plant Overview** | OEE — PR01 | Slowly drifts from green → yellow as cycle time rises | 3–5 min |
| **Faults & Alarms** | **Press Fault Indicators — PR01 Hydraulic Pressure** | Line crosses into yellow zone | 1 min |
| **Faults & Alarms** | Conveyor Jam Events | No jam yet, but PR01 speed change is visible | 2 min |

**Demo talking point:** *"No alarm has fired yet. Hydraulic pressure is declining gradually — this is the AI catching a pump wearing out weeks before it fails. Traditional threshold-based monitoring misses this entirely."*

---

### 🔴 SCENARIO 3 — OV01 Zone 2 Heater Failure

**Simulator button:** `OV01 — Zone 2 Heater Element Failure`  
**API:** `POST /api/scenario/oven_zone2_heater_failure`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | **Oven Zone Temperatures (°C)** | `zone2_temp_c` **drops dramatically** from 200°C to ~90°C | Immediate |
| **Plant Overview** | OEE — OV01 | Drops to red (parts not curing correctly) | 1–2 min |
| **Faults & Alarms** | Alarm Events bar chart | Spike on line_03_curing assets | Immediate |
| **Faults & Alarms** | Oven Sync Loss panel | Zone3 temp spike as controller tries to compensate | 1 min |

**Demo talking point:** *"Zone 2 drops 110°C instantly. Parts going through right now will be undercured — a quality risk that flows downstream. The MES is also placing a batch hold at the same time."*

---

### 🔴 SCENARIO 4 — CV01 Belt Jam (Line 1 Blocked)

**Simulator button:** `CV01 — Belt Jam`  
**API:** `POST /api/scenario/conveyor_cv01_jam`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Asset Telemetry** | **Conveyor Speed History** | **CV01 line drops to 0 m/s** instantly | Immediate |
| **Asset Telemetry** | Conveyor Motor Current | CV01 current spike then drop | Immediate |
| **Asset Telemetry** | CV01 Belt Tension (N) | Tension drops sharply as belt stops | Immediate |
| **Plant Overview** | OEE — PR01 | Starts declining (press starved of parts) | 1–2 min |
| **Faults & Alarms** | **Conveyor Jam Events — Speed Drop to Zero** | CV01 flat line at 0 m/s visible | Immediate |
| **Faults & Alarms** | Alarm Events bar chart | Spike on CV01 | Immediate |

**Demo talking point:** *"CV01 just stopped. The press behind it is now starved — watch the PR01 OEE start to fall. This cascade from one belt jam to production loss is visible in real-time across two dashboards."*

---

### 🟡 SCENARIO 5 — SP02 Paint Filter Blockage

**Simulator button:** `SP02 — Paint Filter Progressive Blockage`  
**API:** `POST /api/scenario/paint_filter_blockage`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Asset Telemetry** | **Sprayer SP02 — Flow Rate & Atomizing Pressure** | `supply_pressure_bar` and `atomisation_pressure_bar` both fall | 1 min |
| **Asset Telemetry** | **Sprayer SP02 — Coat Thickness & Uniformity** | `coat_thickness_um` declining below 60µm threshold | 2 min |
| **Faults & Alarms** | **Sprayer Filter Blockage — Filter ΔP (bar)** | Filter differential pressure rising toward 0.5 bar (red) | 1 min |

**Demo talking point:** *"Filter pressure differential is the leading indicator — it rises over 2 hours before coat thickness falls below spec. This is predictive maintenance: you see the degradation in the ΔP graph before any quality failure."*

---

### 🔴 SCENARIO 6 — Energy Anomaly (Compressor Off-Hours)

**Simulator button:** `Energy Anomaly — Compressor Off-Hours`  
**API:** `POST /api/scenario/energy_anomaly_night_shift`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Power & Energy** | **Power Consumption (kW) — Per Asset** | `compressor_CP01` line rises 35% above baseline | Immediate |
| **Power & Energy** | **Total Harmonic Distortion (THD %)** | CP01 THD spikes above 8% red threshold | Immediate |
| **Power & Energy** | **Power Factor — Per Asset** | CP01 power factor drops to ~0.73 (red) | Immediate |
| **Power & Energy** | Grid Frequency | Minor fluctuation under extra load | 1 min |

**Demo talking point:** *"The compressor is drawing 35% more power than normal. Power factor has fallen to 0.73 — that means reactive losses. THD is elevated at 8.5% which causes heat stress on equipment. This would only be caught in a monthly energy audit without this monitoring."*

---

### 🔴 SCENARIO 7 — Multi-Asset Cascade (Hydraulic Seal Leak → Quality Escape)

**Simulator button:** `Cascade Failure — Hydraulic Leak → Quality Escape`  
**API:** `POST /api/scenario/multi_asset_cascade`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana — this is the flagship demo:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | **Press Hydraulic Pressure** | PR01 drops to ~195 bar, oscillating | Immediate |
| **Plant Overview** | OEE — PR01 | Falls as press force is insufficient | 1 min |
| **Faults & Alarms** | **Press Fault Indicators — PR01 Hydraulic Pressure** | Line drops into red zone | Immediate |
| **Faults & Alarms** | Alarm Events bar chart | PR01 alarm spikes | 30s |

**Demo talking point:** *"Hydraulic seal leak → reduced press force → underdimensioned casings going through to inspection → 18% defect rate at CMM. No single alarm fired. Only by correlating press pressure + force deviation + inspection results does the AI identify the root cause. That's the power of the UNS — data from 4 different systems in one place."*

---

### 🔴 SCENARIO 8 — Oven Thermal Runaway

**Simulator button:** `OV01 — Thermal Runaway`  
**API:** `POST /api/scenario/oven_thermal_runaway`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | **Oven Zone Temperatures (°C)** | **All 4 zones spike simultaneously** 20-25°C above setpoint | Immediate |
| **Plant Overview** | OEE — OV01 | Drops as batch is held | 1 min |
| **Faults & Alarms** | Alarm Events bar chart | All 4 zone alarms fire at once | Immediate |
| **Faults & Alarms** | Oven Sync Loss panel | Dramatic spike on all temperature lines | Immediate |

**Demo talking point:** *"All four oven zones overshoot simultaneously — this is a temperature controller failure, not a single element. The AI distinguishes this from a single-zone failure and recommends immediate shutdown."*

---

### 🟡 SCENARIO 9 — Robot R1 Weld Drift

**Simulator button:** `R1 — Weld Robot Teach-Point Drift`  
**API:** `POST /api/scenario/robot_R1_weld_drift`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Asset Telemetry** | **Robot Position Error (mm)** | R1 line rises from ~0.1mm to ~0.85mm | 1–2 min |
| **Asset Telemetry** | Robot Cycle Time (s) | R1 cycle time slightly elevated | 1 min |
| **Faults & Alarms** | Robot R3 Spray Drift — Path Accuracy | Analogous path_accuracy decline visible | 1 min |

**Demo talking point:** *"0.85mm position error sounds tiny, but for a weld joint on a battery case it's the difference between a structural weld and a defect. The AI detects the drift trend before any weld failures appear downstream."*

---

### 🟡 SCENARIO 10 — Compressed Air Leak

**Simulator button:** `Compressed Air Leak — Network Pressure Drop`  
**API:** `POST /api/scenario/compressed_air_leak`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Power & Energy** | **Power Consumption (kW) — Per Asset** | CP01 line rises as compressor overcompensates | Immediate |
| **Power & Energy** | Power Factor | CP01 power factor declining | 1 min |
| **Faults & Alarms** | **Compressor — Outlet Temp & Air Pressure** | Outlet pressure drops, outlet temp rises | 1 min |

**Demo talking point:** *"The leak itself is in the pneumatic network — invisible in any single sensor. But the compressor running at 95% load instead of 65% is the tell. Combined with zone pressure differential across the air network, the AI pinpoints the leak location."*

---

### 🟡 SCENARIO 11 — Die Wear / Tooling Lifecycle

**Simulator button:** `PR01 Die Wear — Dimensional Drift`  
**API:** `POST /api/scenario/tooling_die_wear`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | **Press Hydraulic Pressure** | Pressure variations widen as die wears | 1 min |
| **Faults & Alarms** | **Press Die Wear (%) — Fault at >90%** | Die wear % line climbing toward yellow (70%) | Immediate |
| **Plant Overview** | OEE — PR01 | Slight decline as scrap rate increases | 2 min |

**Demo talking point:** *"Die wear is a slow burn — 420,000 cycles used, 180,000 remaining. Without this monitoring you'd only know the die is worn when quality starts failing. The AI predicts the exact cycle count where SPC Cpk will fall below 1.0."*

---

### 🔴 SCENARIO 12 — Robot R3 Spray Drift (Paint Quality)

**Simulator button:** `R3 — Spray Robot TCP Drift`  
**API:** `POST /api/scenario/robot_R3_spray_drift`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Asset Telemetry** | **Robot Position Error (mm)** | R3 line rises to 0.72mm | 1 min |
| **Asset Telemetry** | **Sprayer SP02 — Coat Thickness & Uniformity** | Coat thickness falls to ~52µm (below 60µm min) | 1–2 min |
| **Faults & Alarms** | **Robot R3 Spray Drift — Path Accuracy** | Path accuracy crosses yellow threshold (0.3mm) | 1 min |

**Demo talking point:** *"The robot's TCP has drifted 0.72mm — the spray head is now offset. Coat thickness has fallen from 80µm to 52µm, below the 60µm minimum. Uniformity is 72% versus the 90% required. Two correlated graphs — robot accuracy and coat quality — confirm the root cause."*

---

### 🔴 SCENARIO 13 — ERP Material Shortage

**Simulator button:** `ERP Alert — ALU Sheet Material Shortage`  
**API:** `POST /api/scenario/erp_material_shortage`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | OEE — PR01 | OEE begins declining as starve countdown begins | 2–3 min |
| **Plant Overview** | Production Rate | Production rate flat (work orders blocked) | 2 min |

**Demo talking point:** *"ERP says we have 387 kg of ALU sheet — safety stock is 500 kg. MES has blocked new work orders. Press lines continue running on current WO but in ~47 minutes they'll be starved. This is the ERP-to-OT integration in action — a supply chain event reflected immediately in plant floor metrics."*

---

### 🔴 SCENARIO 14 — Quality Escape (Multi-Variate Root Cause)

**Simulator button:** `Quality Escape — CMM Defect Rate 18%`  
**API:** `POST /api/scenario/quality_escape`  
**Reset:** `POST /api/scenario/normal`

**Watch in Grafana — this is the advanced demo:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | **Press Hydraulic Pressure** | Slight increase in pressure variance (subtle!) | 1 min |
| **Plant Overview** | **Oven Zone Temperatures** | Zone 3 running +8°C above setpoint (subtle!) | 1 min |
| **Faults & Alarms** | **Alarm Events** | Alarm bar spike on inspection assets | Immediate |
| **Faults & Alarms** | **Press Fault Indicators** | Pressure deviation within threshold but trending | 1 min |

**Demo talking point:** *"18% defect rate at CMM — but look at the individual sensors. Press pressure deviation is +4.1% (alarm is at 8%). Oven zone 3 is +8°C (alarm is at 15°C). Die wear at 28%. No single alarm fired. Only by correlating all three does the AI identify the root cause. This is why you need AI on top of the UNS."*

---

### 🔴 SCENARIO 15 — Batch Quality Hold (MES + ERP + DPP Integration)

**Simulator button:** `Batch Quality Hold — MES + ERP + DPP Integration`  
**API:** `POST /api/scenario/batch_quality_hold`  
**Reset:** `POST /api/scenario/normal`  
**Then click:** `Trigger DPP` button (or `POST /api/trigger_dpp`)

**Watch in Grafana:**

| Dashboard | Panel | What Changes | Time to See |
|-----------|-------|-------------|-------------|
| **Plant Overview** | **Oven Zone Temperatures** | Zone 2 drops to 155°C (setpoint 200°C, -45°C deviation) | Immediate |
| **Plant Overview** | OEE — OV01 | Drops as batch is held | 1 min |
| **Faults & Alarms** | Alarm Events | Spike on oven and MES streams | Immediate |

**Demo talking point:** *"Oven zone 2 at 155°C — that's a 45°C deviation. MES automatically places batch on hold: 156 units. ERP updates the production order. DPP flags all 156 units automatically. Then hit 'Trigger DPP' to fire the batch-complete event and watch the digital product passport update."*

---

## Power User Tips

### Setting Up Side-by-Side

1. Open simulator UI in browser tab 1
2. Open Grafana Nav Home in browser tab 2
3. Set Grafana time range: **Last 15 minutes**
4. Set refresh: **10s** (already set on all Aurora dashboards)
5. Click a scenario in tab 1, switch to tab 2 immediately

### Resetting Between Demos

Always reset after a scenario:
```bash
curl -X POST http://aurora.iotdemozone.com:8081/api/reset
```
Or click the **Reset** button in the UI. This returns all values to normal baseline within 2–3 publish cycles (20–30 seconds).

### Recommended Demo Flow (15-min live demo)

| Time | Action | Dashboard |
|------|--------|-----------|
| 0:00 | Start on Nav Home, explain 4 dashboards | Nav Home |
| 1:00 | Show Normal baseline — "everything green" | Plant Overview |
| 2:30 | Click CV01 Jam — point to speed dropping to zero | Asset Telemetry |
| 4:00 | Reset, click Oven Thermal Runaway — all 4 zones spike | Plant Overview |
| 6:00 | Reset, click Energy Anomaly — power factor + THD | Power & Energy |
| 9:00 | Reset, click Multi-Asset Cascade — "the flagship" | Plant Overview + Faults |
| 13:00 | Reset, click Batch Quality Hold + Trigger DPP | Faults + (BaSyx) |

### Quick Demo (5-min)

| Time | Action | Dashboard |
|------|--------|-----------|
| 0:00 | Nav Home → quick KPI overview | Nav Home |
| 1:00 | CV01 Jam → conveyor to zero | Asset Telemetry → Faults |
| 3:00 | Reset → Oven Thermal Runaway → all zones spike | Plant Overview |
| 5:00 | Reset → Energy Anomaly → THD + power factor | Power & Energy |

---

## Grafana URL Summary

```
Nav Home:        https://grafana.iotdemozone.com/d/aurora-nav-home
Plant Overview:  https://grafana.iotdemozone.com/d/aurora-plant-overview
Asset Telemetry: https://grafana.iotdemozone.com/d/aurora-asset-telemetry
Power & Energy:  https://grafana.iotdemozone.com/d/aurora-power-monitoring
Faults & Alarms: https://grafana.iotdemozone.com/d/aurora-faults-alarms
```

## Related Documentation

- [`MQTT_TOPIC_REFERENCE.md`](MQTT_TOPIC_REFERENCE.md) — Full list of 111 UNS topics and their fields
- [`grafana/README.md`](grafana/README.md) — Dashboard import instructions
- [`grafana/dashboards/`](grafana/dashboards/) — All dashboard JSON files (importable)
- `aurora_model.py` — Full scenario definitions, affected streams, health degradation curves
- `aurora_simulator.py` — FastAPI server, `/api/scenario/{id}` endpoint
