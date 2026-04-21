# Aurora Industries — UNS / MQTT Topic Reference

**Plant:** Battery Case Plant, Leipzig DE  
**Product:** BAT-CASE-AL-001 (Aluminium EV Battery Case Shells)  
**Customer:** BMW-GROUP-DE  
**Broker:** `mqtt.iotdemozone.com:1883`  
**Total streams:** 111  
**Namespace root:** `aurora/`

---

## UNS Hierarchy Overview

```
aurora/
├── line_01_assembly/
│   ├── cell_01/
│   │   ├── press_PR01/          ← Hydraulic stamping press
│   │   ├── conveyor_CV01/       ← Belt conveyor (feed)
│   │   └── robot_R1/            ← Welding robot
│   ├── cell_02/
│   │   ├── press_PR02/          ← Hydraulic stamping press
│   │   ├── conveyor_CV02/       ← Belt conveyor (exit)
│   │   └── robot_R2/            ← Material handling robot
│   ├── analytics/
│   │   ├── anomaly/             ← AI anomaly detection scores
│   │   └── pdm/                 ← Predictive maintenance RUL
│   └── rfid/                    ← Part tracking entry/exit
├── line_02_painting/
│   ├── cell_01/
│   │   ├── conveyor_CV03/       ← Belt conveyor
│   │   ├── robot_R3/            ← Spray positioning robot
│   │   ├── sprayer_SP01/        ← Electrostatic paint sprayer
│   │   └── sprayer_SP02/        ← Electrostatic paint sprayer
│   └── analytics/
│       └── pdm/
├── line_03_curing/
│   ├── cell_01/
│   │   ├── oven_OV01/           ← 4-zone curing oven
│   │   └── conveyor_CV04/       ← Belt conveyor (oven feed)
│   └── analytics/
│       ├── anomaly/
│       └── pdm/
├── line_04_inspection/
│   ├── cell_01/
│   │   └── vision_CMM01/        ← Vision + CMM dimensional inspection
│   ├── cell_02/
│   │   ├── leak_test_LT01/      ← Pressure leak test
│   │   └── process/             ← DPP step_status events
│   └── rfid/                    ← Inspection entry tracking
├── utilities/
│   ├── compressor_CP01/         ← Main compressed air compressor
│   ├── air_network/             ← Zone pressure distribution
│   └── analytics/
├── quality/
│   └── spc/                     ← SPC control charts
├── erp/
│   ├── production_orders/       ← SAP production orders
│   ├── materials/               ← Material stock + consumption
│   └── quality/                 ← Quality holds
├── mes/
│   ├── batch_tracking           ← MES batch status
│   ├── work_orders/             ← Active work orders
│   └── shift/                   ← Shift summary
└── plant/
    ├── energy/                  ← Plant-level energy rollup
    ├── kpi/                     ← OEE, FPY
    ├── process/                 ← Unit tracking
    └── environment/             ← Factory floor sensors
```

---

## Topic Details by Section

### LINE 01 — Assembly

#### Press PR01 — Hydraulic Stamping Press
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_01_assembly/cell_01/press_PR01/telemetry` | PLC | 5s | `hydraulic_pressure_bar`, `oil_temperature_c`, `press_force_kn`, `die_temp_c`, `die_wear_pct`, `die_cycle_count`, `lube_pressure_bar`, `vibration_mm_s` | pressure: 205–215 bar, oil temp: 45–55°C, force: 720–780 kN, die temp: 35–45°C |
| `aurora/line_01_assembly/cell_01/press_PR01/power` | PLC | 5s | `total_kw`, `power_factor`, `thd_pct`, `phases.A/B/C.current_a`, `phases.A/B/C.voltage_v` | 14–18 kW, PF: 0.88–0.93, THD < 3% |
| `aurora/line_01_assembly/cell_01/press_PR01/energy` | MES | 30s | `current_kw`, `total_kwh`, `energy_per_cycle_wh`, `co2_total_kg` | 16.8 kW nominal, ~0.185 kWh/unit |
| `aurora/line_01_assembly/cell_01/press_PR01/performance` | MES | 30s | `oee`, `cycle_time_s`, `cycle_time_target_s`, `operational_status`, `production_rate_hr`, `scrap_count_shift` | OEE: 75–82%, cycle time: 7.6–8.4s, status: Running |
| `aurora/line_01_assembly/cell_01/press_PR01/spc` | QMS | 15s | `parameter`, `value`, `ucl`, `lcl`, `in_control`, `sigma_level`, `cpk`, `trend` | Cpk ≥ 1.33, in_control: true |
| `aurora/line_01_assembly/cell_01/press_PR01/lube` | PLC | 30s | `reservoir_level_pct`, `supply_pressure_bar`, `flow_rate_ml_min`, `oil_temp_c`, `filter_dp_bar` | reservoir: 50–95%, pressure: 3.8–4.6 bar, flow: 100–150 ml/min |
| `aurora/line_01_assembly/cell_01/press_PR01/health` | SCADA | 30s | `overall_score`, `components.HydraulicPump`, `components.MainSeal`, `components.Accumulator`, `components.Die` | overall ≥ 80%, all components ≥ 70% |
| `aurora/line_01_assembly/cell_01/press_PR01/alarms` | PLC | 60s | `active_alarms[]`, `alarm_count`, `alarm_code`, `severity` | alarm_count: 0 |
| `aurora/line_01_assembly/cell_01/press_PR01/process_params` | MES | 30s | `recipe_id`, `parameters.hydraulic_pressure_sp`, `parameters.stroke_speed_sp_mm_s`, `actual_vs_setpoint_ok` | deviation_pct < 1.0% |
| `aurora/line_01_assembly/analytics/anomaly/press_PR01` | AI | 30s | `anomaly_score`, `anomaly_level`, `contributing_signals[]`, `recommended_action` | score < 0.1, level: LOW |
| `aurora/line_01_assembly/analytics/pdm/press_PR01` | AI | 60s | `min_health_score`, `min_rul_days`, `maintenance_urgency`, `next_recommended_date`, `cost_if_ignored_eur` | urgency: OK, RUL > 90 days |

**Fault signals for PR01:**
- `hydraulic_pressure_bar` < 200 bar → pump wear / seal leak
- `oil_temperature_c` > 60°C → pump inefficiency
- `die_wear_pct` > 70% → schedule die change
- `die_temp_c` > 55°C → surface oxidation, accelerated wear
- `vibration_mm_s` > 4.0 → bearing wear
- `lube_pressure_bar` < 2.5 → lube system failure

---

#### Press PR02 — Hydraulic Stamping Press (Line 1, Cell 2)
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_01_assembly/cell_02/press_PR02/telemetry` | PLC | 5s | Same fields as PR01 | Same as PR01 |
| `aurora/line_01_assembly/cell_02/press_PR02/power` | PLC | 5s | 3-phase power | 14–18 kW |
| `aurora/line_01_assembly/cell_02/press_PR02/energy` | MES | 30s | Energy rollup | 16.8 kW nominal |
| `aurora/line_01_assembly/cell_02/press_PR02/performance` | MES | 30s | OEE, cycle time | OEE 75–82% |
| `aurora/line_01_assembly/cell_02/press_PR02/spc` | QMS | 15s | SPC chart | Cpk ≥ 1.33 |
| `aurora/line_01_assembly/cell_02/press_PR02/lube` | PLC | 30s | Lube system | See PR01 |
| `aurora/line_01_assembly/cell_02/press_PR02/health` | SCADA | 30s | Health scores | overall ≥ 80% |
| `aurora/line_01_assembly/cell_02/press_PR02/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/line_01_assembly/cell_02/press_PR02/process_params` | MES | 30s | Recipe params | deviation_pct < 1.0% |
| `aurora/line_01_assembly/analytics/anomaly/press_PR02` | AI | 30s | Anomaly score | score < 0.1 |

---

#### Conveyors — Line 01
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_01_assembly/cell_01/conveyor_CV01/telemetry` | PLC | 5s | `speed_ms`, `speed_setpoint_ms`, `belt_tension_n`, `bearing_temp_c`, `motor_current_a`, `jam_detected`, `units_on_belt` | speed: 1.9–2.1 m/s, tension: 800–900 N, bearing: 30–45°C |
| `aurora/line_01_assembly/cell_01/conveyor_CV01/power` | PLC | 5s | 3-phase power | 3.0–4.0 kW |
| `aurora/line_01_assembly/cell_01/conveyor_CV01/energy` | MES | 30s | Energy rollup | 3.5 kW nominal |
| `aurora/line_01_assembly/cell_01/conveyor_CV01/health` | SCADA | 60s | Health scores | overall ≥ 80% |
| `aurora/line_01_assembly/cell_01/conveyor_CV01/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/line_01_assembly/cell_02/conveyor_CV02/telemetry` | PLC | 5s | Same fields | speed: 1.4–1.6 m/s |
| `aurora/line_01_assembly/cell_02/conveyor_CV02/power` | PLC | 5s | 3-phase power | 3.0–4.0 kW |
| `aurora/line_01_assembly/cell_02/conveyor_CV02/energy` | MES | 30s | Energy rollup | 3.5 kW nominal |
| `aurora/line_01_assembly/cell_02/conveyor_CV02/health` | SCADA | 60s | Health scores | overall ≥ 80% |
| `aurora/line_01_assembly/cell_02/conveyor_CV02/alarms` | PLC | 60s | Alarms | alarm_count: 0 |

**Fault signals for CV01:**
- `speed_ms` = 0 AND `jam_detected` = true → belt jam (CRITICAL)
- `belt_tension_n` > 180 N → jammed object
- `bearing_temp_c` > 65°C → bearing failure
- `motor_current_a` = 0 → motor/VFD fault

---

#### Robots — Line 01
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_01_assembly/cell_01/robot_R1/telemetry` | PLC | 5s | `state`, `task`, `position_error_mm`, `joint_temps_c[]`, `joint_torques_nm[]`, `cycle_time_s`, `teach_point_offset_mm`, `path_accuracy_mm` | position_error < 0.5mm, path_accuracy < 0.15mm |
| `aurora/line_01_assembly/cell_01/robot_R1/power` | PLC | 5s | 3-phase power | 4.5–6.5 kW |
| `aurora/line_01_assembly/cell_01/robot_R1/health` | SCADA | 60s | `components.JointA1`, `components.JointA2`, `components.WristUnit`, `components.TCP_Calibration` | all ≥ 75% |
| `aurora/line_01_assembly/cell_01/robot_R1/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/line_01_assembly/analytics/pdm/robot_R1` | AI | 60s | PdM RUL | urgency: OK |
| `aurora/line_01_assembly/cell_02/robot_R2/telemetry` | PLC | 5s | Same as R1 (task: MaterialHandling) | position_error < 0.5mm |
| `aurora/line_01_assembly/cell_02/robot_R2/power` | PLC | 5s | 3-phase power | 4.5–6.5 kW |
| `aurora/line_01_assembly/cell_02/robot_R2/health` | SCADA | 60s | Health scores | all ≥ 75% |
| `aurora/line_01_assembly/cell_02/robot_R2/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/line_01_assembly/analytics/pdm/robot_R2` | AI | 60s | PdM RUL | urgency: OK |

**Fault signals for R1:**
- `position_error_mm` > 0.5 → teach point drift (weld quality risk)
- `position_error_mm` > 1.2 → weld failures (scrap risk)
- `teach_point_offset_mm` > 0.5 → recalibration required
- `state` = "Faulted" → emergency stop / collision

---

#### RFID Tracking — Line 01
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_01_assembly/rfid/entry` | PLC | 10s | `tag_id`, `unit_id`, `batch_id`, `product`, `read_success`, `rssi_dbm` | read_success: true, rssi > -50 dBm |
| `aurora/line_01_assembly/rfid/exit` | PLC | 10s | Same fields | read_success: true |

---

### LINE 02 — Painting

#### Robot R3 — Spray Positioning Robot
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_02_painting/cell_01/robot_R3/telemetry` | PLC | 5s | `position_error_mm`, `path_accuracy_mm`, `joint_temps_c[]`, `teach_point_offset_mm`, `cycle_time_s` | position_error < 0.3mm, path_accuracy < 0.1mm |
| `aurora/line_02_painting/cell_01/robot_R3/power` | PLC | 5s | 3-phase power | 3.5–5.0 kW |
| `aurora/line_02_painting/cell_01/robot_R3/health` | SCADA | 60s | `components.TCP_Calibration`, `components.JointA2` | TCP_Calibration ≥ 80%, JointA2 ≥ 80% |
| `aurora/line_02_painting/cell_01/robot_R3/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/line_02_painting/analytics/pdm/robot_R3` | AI | 60s | PdM RUL | urgency: OK |

**Fault signals for R3:**
- `position_error_mm` > 0.3 → TCP drift (coat thickness risk)
- `path_accuracy_mm` > 0.3 → spray pattern offset
- `TCP_Calibration` health < 60% → recalibrate immediately

---

#### Sprayers SP01 & SP02 — Electrostatic Paint Applicators
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_02_painting/cell_01/sprayer_SP01/telemetry` | PLC | 5s | `supply_pressure_bar`, `atomisation_pressure_bar`, `fluid_flow_lpm`, `coat_thickness_um`, `coat_uniformity_pct`, `filter_dp_bar`, `filter_status`, `gun_voltage_kv`, `viscosity_mpa_s` | supply: 3.3–3.7 bar, coat thickness: 70–90µm, uniformity ≥ 90%, filter_dp < 0.3 bar |
| `aurora/line_02_painting/cell_01/sprayer_SP01/power` | PLC | 5s | 3-phase power | 2.5–3.1 kW |
| `aurora/line_02_painting/cell_01/sprayer_SP01/energy` | MES | 30s | Energy rollup | 2.8 kW nominal |
| `aurora/line_02_painting/cell_01/sprayer_SP01/health` | SCADA | 60s | `components.Nozzle`, `components.FluidPump`, `components.FilterUnit`, `components.GunElectrode` | all ≥ 65% |
| `aurora/line_02_painting/cell_01/sprayer_SP01/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/line_02_painting/cell_01/sprayer_SP02/telemetry` | PLC | 5s | Same as SP01 | Same ranges |
| `aurora/line_02_painting/cell_01/sprayer_SP02/power` | PLC | 5s | 3-phase power | 2.5–3.1 kW |
| `aurora/line_02_painting/cell_01/sprayer_SP02/energy` | MES | 30s | Energy rollup | 2.8 kW nominal |
| `aurora/line_02_painting/cell_01/sprayer_SP02/health` | SCADA | 60s | Health scores | all ≥ 65% |
| `aurora/line_02_painting/cell_01/sprayer_SP02/alarms` | PLC | 60s | Alarms | alarm_count: 0 |

**Fault signals for sprayers:**
- `filter_dp_bar` > 0.5 → filter blocked (replace immediately)
- `coat_thickness_um` < 60 → below minimum spec (quality hold)
- `coat_uniformity_pct` < 90 → spray pattern offset
- `filter_status` = "BLOCKED" → production stop required
- `atomisation_pressure_bar` < 2.0 → flow restriction

**Correlation:** `filter_dp_bar` ↑ correlates (r = −0.94) with `coat_thickness_um` ↓ — use together to diagnose filter-driven quality degradation.

---

#### Conveyor CV03 — Painting Line
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_02_painting/cell_01/conveyor_CV03/telemetry` | PLC | 5s | `speed_ms`, `belt_tension_n`, `bearing_temp_c`, `jam_detected` | speed: 0.75–0.85 m/s |
| `aurora/line_02_painting/cell_01/conveyor_CV03/power` | PLC | 5s | 3-phase power | 1.8–2.5 kW |
| `aurora/line_02_painting/cell_01/conveyor_CV03/energy` | MES | 30s | Energy rollup | 2.2 kW nominal |
| `aurora/line_02_painting/cell_01/conveyor_CV03/health` | SCADA | 60s | Health scores | overall ≥ 80% |
| `aurora/line_02_painting/cell_01/conveyor_CV03/alarms` | PLC | 60s | Alarms | alarm_count: 0 |

---

### LINE 03 — Curing

#### Oven OV01 — 4-Zone Curing Oven
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_03_curing/cell_01/oven_OV01/telemetry` | PLC | 5s | `zone1_temp_c`, `zone2_temp_c`, `zone3_temp_c`, `zone4_temp_c`, `zone_setpoints_c[]`, `zone_deviations_c[]`, `fan_speed_rpm`, `exhaust_temp_c`, `conveyor_speed_mpm`, `dwell_time_min`, `gas_flow_m3h` | zone setpoints: [180, 200, 200, 170]°C, deviation: ±5°C, fan: 1400–1500 rpm, dwell: 6.4 min |
| `aurora/line_03_curing/cell_01/oven_OV01/power` | PLC | 5s | 3-phase power | 38–48 kW |
| `aurora/line_03_curing/cell_01/oven_OV01/energy` | MES | 30s | Energy rollup | 45.0 kW nominal |
| `aurora/line_03_curing/cell_01/oven_OV01/health` | SCADA | 30s | `components.Zone1Heater–Zone4Heater`, `components.FanAssembly`, `components.ExhaustSystem` | all ≥ 75% |
| `aurora/line_03_curing/cell_01/oven_OV01/performance` | MES | 30s | `oee`, `zone_temps[]`, `status`, `dwell_time_min` | OEE ≥ 80%, status: normal |
| `aurora/line_03_curing/cell_01/oven_OV01/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/line_03_curing/analytics/anomaly/oven_OV01` | AI | 30s | Anomaly score | score < 0.1 |
| `aurora/line_03_curing/analytics/pdm/oven_OV01` | AI | 60s | PdM RUL per heater zone | urgency: OK |

**Fault signals for OV01:**
- `zone_deviations_c[1]` < −50°C → Zone 2 heater element failure (CRITICAL — batch hold)
- Any zone > setpoint + 15°C → Thermal runaway / PID fault (STOP line)
- `fan_speed_rpm` < 500 → Fan failure (thermal uniformity lost)
- `dwell_time_min` < 5.5 → Undercure (reduce conveyor speed or investigate CV04)
- `exhaust_temp_c` > 105°C → Thermal runaway indicator

**Minimum cure spec:** All zones ≥ 180°C for ≥ 6.4 minutes. Zone 2 failure below 180°C = cure deficiency.

---

#### Conveyor CV04 — Oven Feed Conveyor
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_03_curing/cell_01/conveyor_CV04/telemetry` | PLC | 5s | `speed_ms`, `speed_setpoint_ms`, `belt_tension_n`, `bearing_temp_c`, `motor_current_a` | speed: 0.18–0.22 m/s (tightly controlled for dwell time) |
| `aurora/line_03_curing/cell_01/conveyor_CV04/power` | PLC | 5s | 3-phase power | 1.5–2.1 kW |
| `aurora/line_03_curing/cell_01/conveyor_CV04/energy` | MES | 30s | Energy rollup | 1.8 kW nominal |
| `aurora/line_03_curing/cell_01/conveyor_CV04/health` | SCADA | 60s | Health scores | overall ≥ 80% |
| `aurora/line_03_curing/cell_01/conveyor_CV04/alarms` | PLC | 60s | Alarms | alarm_count: 0 |

**Note:** CV04 speed directly controls oven dwell time. Speed deviation > ±5% affects cure quality. Correlated with `oven_OV01/telemetry.dwell_time_min`.

---

### LINE 04 — Inspection

#### Vision CMM01 — Dimensional Inspection
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_04_inspection/cell_01/vision_CMM01/result` | PLC | 15s | `unit_id`, `batch_id`, `result`, `confidence`, `fail_codes[]`, `disposition` | result: PASS, confidence ≥ 0.97, fail rate < 3% |
| `aurora/line_04_inspection/cell_01/vision_CMM01/dimensions` | QMS | 15s | `measurements.length_mm`, `measurements.width_mm`, `measurements.wall_th_mm`, `measurements.flatness_mm`, `out_of_spec[]`, `pass`, `gage_r_r_pct` | length: 299.9–300.1mm, width: 149.9–150.1mm, wall: 1.85–2.15mm, flatness < 0.12mm |
| `aurora/line_04_inspection/cell_01/vision_CMM01/power` | PLC | 30s | 3-phase power | 1.0–1.4 kW |
| `aurora/line_04_inspection/cell_01/vision_CMM01/health` | SCADA | 60s | `components.CameraA/B`, `components.Lighting`, `components.CalibTarget` | all ≥ 80% |

**Fault signals for CMM01:**
- `fail_codes` = ["DIM-001"] repeatedly → dimensional drift
- `gage_r_r_pct` > 15% → sensor calibration drift
- `out_of_spec` contains "wall_th_mm" → press force or die wear issue upstream
- Fail rate > 5% over 30 min → trigger quality investigation

**Cross-system correlation:** CMM failure rate ↑ + `press_PR01/telemetry.hydraulic_pressure_bar` ↓ → cascade failure scenario. CMM failures without any upstream alarm = multi-variate quality escape.

---

#### Leak Test LT01
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_04_inspection/cell_02/leak_test_LT01/result` | PLC | 20s | `unit_id`, `result`, `confidence`, `fail_codes[]`, `disposition` | result: PASS, fail rate < 1% |
| `aurora/line_04_inspection/cell_02/leak_test_LT01/power` | PLC | 30s | 3-phase power | 0.6–1.0 kW |
| `aurora/line_04_inspection/cell_02/leak_test_LT01/health` | SCADA | 60s | `components.PressureSensor`, `components.FixtureSeal`, `components.FillValve` | all ≥ 75% |

---

#### DPP — Digital Product Passport Events
| Topic | Source | Interval | Key Fields | Notes |
|-------|--------|----------|------------|-------|
| `aurora/line_04_inspection/cell_02/process/step_status` | MES | 20s (auto) / manual | `event`, `batch_id`, `product`, `unit_id`, `step`, `status`, `result`, `triggered_by`, `energy_kwh_this_unit`, `co2_kg_this_unit`, `traceability_url` | Auto: continuous per unit. Manual: Trigger DPP button fires `triggered_by: manual_demo` |

**Manual DPP trigger payload:**
```json
{
  "event": "dpp_triggered",
  "batch_id": "BATCH-20260417-001",
  "product": "BAT-CASE-AL-001",
  "unit_id": "UNIT-000157",
  "step": "inspection",
  "status": "complete",
  "result": "pass",
  "triggered_by": "manual_demo",
  "standard": "ISO 27553 / EU Battery Regulation 2023/1542"
}
```

---

#### RFID Tracking — Line 04
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/line_04_inspection/rfid/entry` | PLC | 15s | `tag_id`, `unit_id`, `batch_id`, `read_success`, `rssi_dbm` | read_success: true |

---

### UTILITIES

#### Compressor CP01 — Main Compressed Air
| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/utilities/compressor_CP01/telemetry` | PLC | 10s | `outlet_pressure_bar`, `inlet_temp_c`, `outlet_temp_c`, `flow_rate_m3h`, `vibration_mm_s`, `oil_level_pct`, `loaded_pct`, `dew_point_c`, `run_hours`, `status` | pressure: 7.3–7.7 bar, outlet temp: 70–85°C, loaded: 65–78%, vibration < 3.0 mm/s |
| `aurora/utilities/compressor_CP01/power` | PLC | 5s | `total_kw`, `power_factor`, `thd_pct`, `phases.A/B/C` | 20–24 kW, PF ≥ 0.88, THD < 5%, phase currents balanced (±5%) |
| `aurora/utilities/compressor_CP01/energy` | MES | 30s | Energy rollup | 22 kW nominal |
| `aurora/utilities/compressor_CP01/health` | SCADA | 60s | `components.Piston`, `components.Valve`, `components.Intercooler`, `components.AirFilter` | all ≥ 70% |
| `aurora/utilities/compressor_CP01/alarms` | PLC | 60s | Alarms | alarm_count: 0 |
| `aurora/utilities/analytics/anomaly/compressor_CP01` | AI | 30s | Anomaly score | score < 0.1 |
| `aurora/utilities/analytics/pdm/compressor_CP01` | AI | 60s | PdM RUL | urgency: OK |
| `aurora/utilities/air_network/pressure` | PLC | 10s | `header_pressure_bar`, `zone_a_press_bar`, `zone_b_press_bar`, `zone_c_press_bar`, `total_flow_m3h`, `leak_detected`, `estimated_leak_m3h` | header: 7.1 bar, zones within 0.3 bar of each other, leak_detected: false |

**Fault signals for CP01:**
- `loaded_pct` > 90% sustained → air leak or demand spike
- `outlet_pressure_bar` < 6.5 → insufficient capacity / leak
- Phase C `current_a` > 150% of A and B → valve wear / intercooler fouling
- `thd_pct` > 5% → mechanical load asymmetry (valve flutter)
- `power_factor` < 0.80 → reactive power waste
- `vibration_mm_s` > 6.0 → bearing failure approaching

**Fault signals for air_network:**
- `zone_a_press_bar` significantly lower than B and C → Zone A leak
- `total_flow_m3h` > 35 at normal production → leak or demand anomaly
- `leak_detected` = true + `estimated_leak_m3h` > 2.0 → locate with ultrasonic detector

---

### QUALITY — SPC Control Charts

| Topic | Source | Interval | Parameter | Nominal | UCL / LCL | Alarm Condition |
|-------|--------|----------|-----------|---------|-----------|-----------------|
| `aurora/quality/spc/wall_thickness` | QMS | 20s | `wall_thickness_mm` | 2.000mm | ±0.15mm | Cpk < 1.33 or out of control |
| `aurora/quality/spc/coat_thickness` | QMS | 20s | `coat_thickness_um` | 80µm | ±20µm | Cpk < 1.33 or value < 60µm |
| `aurora/quality/spc/press_force_pr01` | QMS | 10s | `press_force_kn` | 750 kN | ±30 kN | Deviation > 4% sustained |
| `aurora/quality/spc/draw_depth` | QMS | 10s | `draw_depth_mm` | 85.0mm | ±0.5mm | Out of control |

**Key SPC fields:** `value`, `ucl`, `lcl`, `mean`, `in_control`, `cpk`, `sigma_level`, `trend`, `nelson_rules_violated`

**Trending:** `trend` = "UPWARD_DRIFT" present in multi-variate quality escape, die wear, and cascade scenarios. Cpk trajectory is the key predictive signal.

---

### ERP STREAMS — SAP Integration

| Topic | Source | Interval | Key Fields | Notes |
|-------|--------|----------|------------|-------|
| `aurora/erp/production_orders/current` | ERP | 30s | `order_id`, `material`, `quantity_ordered`, `quantity_produced`, `quantity_scrap`, `status`, `customer_id`, `delivery_date`, `alert` | status: IN_PROGRESS / BLOCKED. Alert fires on material shortage |
| `aurora/erp/materials/consumption` | ERP | 60s | `materials[]` with `material_id`, `consumed_kg`, `uom`, `stock_warning`. `total_material_cost_eur`, `waste_pct` | Materials: ALU_SHEET_2MM, PRIMER_COAT, TOPCOAT_GREY, SEALANT_A |
| `aurora/erp/quality/holds` | ERP | 30s | `active_holds[]`, `hold_count`, `total_holds_today` | Each hold: `hold_id`, `batch_id`, `reason`, `severity`, `units_affected` |

**Material safety stock levels:**
| Material | Safety Stock | Consumption Rate |
|----------|-------------|-----------------|
| ALU_SHEET_2MM | 500 kg | ~8.25 kg/min (both presses) |
| PRIMER_COAT | 50 kg | ~0.15 kg/min |
| TOPCOAT_GREY | 50 kg | ~0.15 kg/min |
| SEALANT_A | 20 kg | ~0.07 kg/min |

---

### MES STREAMS — Manufacturing Execution System

| Topic | Source | Interval | Key Fields | Notes |
|-------|--------|----------|------------|-------|
| `aurora/mes/batch_tracking` | MES | 20s | `batch_id`, `product`, `order_id`, `work_order_id`, `shift`, `units_started`, `units_passed`, `units_rework`, `units_scrap`, `first_pass_yield_pct`, `batch_status`, `oee_batch` | batch_status: IN_PROGRESS / ON_HOLD |
| `aurora/mes/work_orders/active` | MES | 30s | `work_order_id`, `operation`, `machine_id`, `operator_id`, `status`, `downtime_min`, `downtime_reason`, `tooling_id`, `program_id` | status: IN_PROGRESS / WAITING_MATERIAL / DOWNTIME |
| `aurora/mes/shift/summary` | MES | 60s | `shift`, `planned_units`, `actual_units`, `oee_pct`, `availability_pct`, `performance_pct`, `quality_pct`, `scrap_count`, `rework_count`, `downtime_min`, `energy_kwh_shift` | Shift summary updated every minute |

---

### PLANT-LEVEL STREAMS

| Topic | Source | Interval | Key Fields | Normal Range |
|-------|--------|----------|------------|--------------|
| `aurora/plant/energy/total` | SCADA | 30s | `total_kwh`, `current_kw`, `energy_intensity_kwh_per_unit`, `co2_kg_today`, `cost_eur_today` | current_kw: 85–120 kW, intensity ~0.185 kWh/unit |
| `aurora/plant/kpi/oee` | MES | 30s | `oee_pct`, `availability_pct`, `performance_pct`, `quality_pct`, `units_produced_shift`, `scrap_count`, `shift` | OEE ~79%, quality ~98% |
| `aurora/plant/process/unit_id` | MES | 10s | `current_unit`, `batch_id`, `product`, `line_01/02/03/04_status` | all line statuses: Running |
| `aurora/plant/environment/floor` | SCADA | 60s | `temperature_c`, `humidity_rh_pct`, `co2_ppm`, `noise_db`, `lighting_lux`, `particulate_um3` | temp: 20–23°C, humidity: 40–55%, CO2 < 800 ppm |

---

### LINE ENERGY ROLLUPS

| Topic | Source | Interval | Key Fields |
|-------|--------|----------|------------|
| `aurora/line_01_assembly/energy/total` | SCADA | 30s | `total_kw`, `period_kwh` — sum of PR01+PR02+CV01+CV02+R1+R2 (~65 kW nominal) |
| `aurora/line_02_painting/energy/total` | SCADA | 30s | `total_kw`, `period_kwh` — sum of SP01+SP02+CV03+R3 (~13 kW nominal) |
| `aurora/line_03_curing/energy/total` | SCADA | 30s | `total_kw`, `period_kwh` — sum of OV01+CV04 (~47 kW nominal) |
| `aurora/line_04_inspection/energy/total` | SCADA | 30s | `total_kw`, `period_kwh` — sum of CMM01+LT01 (~2 kW nominal) |

---

## Scenario → Topics Cross-Reference

### Which topics to watch for each demo scenario:

| Scenario | Primary Topics | What changes | Threshold |
|----------|---------------|--------------|-----------|
| **PR01 Hydraulic Pump Wear** | `.../press_PR01/telemetry`, `.../health`, `.../analytics/pdm/press_PR01` | `hydraulic_pressure_bar` ↓, `oil_temperature_c` ↑, HydraulicPump health ↓ | pressure 196 vs alarm 192 (below alarm!) |
| **OV01 Zone 2 Heater Failure** | `.../oven_OV01/telemetry`, `aurora/erp/quality/holds`, `aurora/mes/batch_tracking` | `zone2_temp_c` = 90 vs 200°C setpoint, batch ON_HOLD | zone_deviations[1] = −110°C |
| **SP02 Paint Filter Blockage** | `.../sprayer_SP02/telemetry`, `.../health`, `aurora/quality/spc/coat_thickness` | `filter_dp_bar` ↑ 0.68, `coat_thickness_um` ↓ 45 | filter_dp > 0.5 bar; coat < 60µm |
| **CV01 Belt Jam** | `.../conveyor_CV01/telemetry`, `.../press_PR01/performance`, `aurora/mes/work_orders/active` | `speed_ms` = 0, `jam_detected` = true, PR01 status = Starved | speed = 0, tension > 180 N |
| **Energy Anomaly (Compressor)** | `.../compressor_CP01/power`, `.../health`, `.../analytics/anomaly/compressor_CP01` | `total_kw` = 29.7 vs 22, Phase C = 18A vs 12A, THD = 8.5% | thd > 5%, phase imbalance > 30% |
| **Cascade Failure** | `.../press_PR01/telemetry`, `.../health`, `.../vision_CMM01/result`, `aurora/erp/quality/holds` | PR01 pressure ↓, oil_leak = true, CMM fail rate = 18% | MainSeal health < 50% |
| **OV01 Thermal Runaway** | `.../oven_OV01/telemetry`, `aurora/mes/batch_tracking`, `aurora/erp/quality/holds` | All zones 20–27°C above setpoint, batch ON_HOLD | zone overshoot > 15°C |
| **R1 Weld Robot Drift** | `.../robot_R1/telemetry`, `.../health`, `.../analytics/pdm/robot_R1` | `position_error_mm` = 0.85, JointA1=71%, WristUnit=68% | position_error > 0.5mm |
| **Compressed Air Leak** | `aurora/utilities/air_network/pressure`, `.../compressor_CP01/telemetry` | zone_a_press < 6.1 vs zone_b/c ~7.1, `loaded_pct` = 95% | zone pressure differential > 0.8 bar |
| **PR01 Die Wear** | `.../press_PR01/telemetry`, `aurora/quality/spc/wall_thickness`, `.../health` | `die_wear_pct` = 70, `die_temp_c` = 63, Cpk = 0.82 | die_wear > 70%, Cpk < 1.33 |
| **R3 Spray TCP Drift** | `.../robot_R3/telemetry`, `.../sprayer_SP01/telemetry`, `.../health` | R3 `position_error_mm` = 0.72, coat = 52µm, uniformity = 72% | position_error > 0.3mm; coat < 60µm |
| **ERP Material Shortage** | `aurora/erp/materials/consumption`, `aurora/erp/production_orders/current`, `aurora/mes/work_orders/active` | ALU_SHEET_2MM = 387 kg vs 500 safety, WO = WAITING_MATERIAL | stock < safety level |
| **Quality Escape** | `.../vision_CMM01/result`, `.../press_PR01/telemetry`, `.../oven_OV01/telemetry`, `.../health` | CMM fail 18%, PR01 force +4.1% (no alarm), OV01 z3 +8°C (no alarm) | No single alarm fires — AI only |
| **Batch Quality Hold** | `.../oven_OV01/telemetry`, `aurora/mes/batch_tracking`, `aurora/erp/quality/holds` | zone_2 = 155°C (−45°C deviation), batch ON_HOLD, 156 units held | zone deviation > 25°C |

---

## Topic + Field Value Lookup (Quick Reference)

### Fault Value Table — What You See vs What's Normal

| Field | Asset | Normal | Fault Value | Scenario | Source Topic |
|-------|-------|--------|-------------|----------|--------------|
| `hydraulic_pressure_bar` | press_PR01 | 205–215 | 195–198 | Hydraulic Pump Wear, Cascade | `.../press_PR01/telemetry` |
| `oil_temperature_c` | press_PR01 | 45–55°C | 58–65°C | Hydraulic Pump Wear | `.../press_PR01/telemetry` |
| `die_wear_pct` | press_PR01 | < 60% | 70% | Die Wear | `.../press_PR01/telemetry` |
| `die_temp_c` | press_PR01 | 35–45°C | 63°C | Die Wear | `.../press_PR01/telemetry` |
| `zone2_temp_c` | oven_OV01 | 198–202°C | 90°C | Zone 2 Heater Failure | `.../oven_OV01/telemetry` |
| `zone2_temp_c` | oven_OV01 | 198–202°C | 155°C | Batch Quality Hold | `.../oven_OV01/telemetry` |
| `zone_deviations_c[]` | oven_OV01 | ±2°C all zones | +22 to +27°C | Thermal Runaway | `.../oven_OV01/telemetry` |
| `filter_dp_bar` | sprayer_SP02 | 0.10–0.20 | 0.68 | Paint Filter Blockage | `.../sprayer_SP02/telemetry` |
| `coat_thickness_um` | sprayer_SP01/02 | 70–90µm | 45–52µm | Filter Blockage / R3 TCP Drift | `.../sprayer_SP01/telemetry` |
| `coat_uniformity_pct` | sprayer_SP01/02 | ≥ 90% | 72% | R3 TCP Drift | `.../sprayer_SP01/telemetry` |
| `speed_ms` | conveyor_CV01 | 1.9–2.1 | 0.0 | Belt Jam | `.../conveyor_CV01/telemetry` |
| `jam_detected` | conveyor_CV01 | false | true | Belt Jam | `.../conveyor_CV01/telemetry` |
| `position_error_mm` | robot_R1 | < 0.3mm | 0.85mm | Weld Robot Drift | `.../robot_R1/telemetry` |
| `position_error_mm` | robot_R3 | < 0.2mm | 0.72mm | R3 TCP Drift | `.../robot_R3/telemetry` |
| `total_kw` (CP01) | compressor_CP01 | 20–24 kW | 29.7 kW | Energy Anomaly | `.../compressor_CP01/power` |
| `thd_pct` | compressor_CP01 | < 3% | 8.5% | Energy Anomaly | `.../compressor_CP01/power` |
| `loaded_pct` | compressor_CP01 | 65–78% | 95% | Air Leak | `.../compressor_CP01/telemetry` |
| `zone_a_press_bar` | air_network | ~7.1 | 6.1 | Air Leak | `aurora/utilities/air_network/pressure` |
| `wall_thickness_mm` | vision_CMM01 | 1.85–2.15mm | ~2.3mm | Cascade / Die Wear | `.../vision_CMM01/dimensions` |
| `cpk` (wall_thickness) | QMS | ≥ 1.33 | 0.82 | Die Wear, Quality Escape | `aurora/quality/spc/wall_thickness` |
| `fail_rate` (CMM) | vision_CMM01 | ~3% | 18% | Cascade, Quality Escape | `.../vision_CMM01/result` |
| `stock_warning` | ERP | false | true | Material Shortage | `aurora/erp/materials/consumption` |
| `batch_status` | MES | IN_PROGRESS | ON_HOLD | Multiple oven scenarios | `aurora/mes/batch_tracking` |
| `first_pass_yield_pct` | MES | 97–99% | 72–82% | Quality scenarios | `aurora/mes/batch_tracking` |

---

## Multi-Topic Correlation Patterns

### How Topics Work Together to Show Scenarios

**Pattern 1: Hydraulic Leak → Quality Cascade** (Cascade Failure scenario)
```
press_PR01/telemetry.hydraulic_pressure_bar ↓ (195 bar)
press_PR01/telemetry.oil_leak_detected = true
  → 8 minutes later →
vision_CMM01/result.result = FAIL (rate 18%)
vision_CMM01/dimensions.wall_th_mm = 2.3 (over tolerance)
erp/quality/holds.hold_count > 0
```
No single alarm fires. AI needed to trace PR01 → CMM.

**Pattern 2: Filter DP → Coat Thickness** (Paint Filter scenario)
```
sprayer_SP02/telemetry.filter_dp_bar rising 0.12 → 0.68 over 127 min
  ↓ (correlation r = -0.94)
sprayer_SP02/telemetry.coat_thickness_um falling 80 → 45
quality/spc/coat_thickness.cpk falling below 1.33
quality/spc/coat_thickness.trend = UPWARD_DRIFT
```
Two streams must be viewed together. Threshold alarm on coat_thickness fires too late.

**Pattern 3: Die Wear → Dimensional Drift** (Die Wear scenario)
```
press_PR01/telemetry.die_wear_pct increasing toward 70%
press_PR01/telemetry.die_temp_c increasing 38 → 63°C
  ↓
quality/spc/wall_thickness.cpk declining 1.33 → 0.82
quality/spc/wall_thickness.trend = UPWARD_DRIFT
health/press_PR01.components.Die = 30% (red)
analytics/pdm/press_PR01.min_rul_days → 111 hours
```
Quality escape projected at 470K cycles. PdM stream gives exact time window.

**Pattern 4: Sub-Threshold Combination** (Quality Escape scenario)
```
press_PR01/telemetry.press_force_deviation_pct = +4.1% (alarm at 8% — no alarm)
oven_OV01/telemetry.zone_3_temp = setpoint + 8°C (alarm at 15°C — no alarm)
health/press_PR01.components.Die = 28% (health score only)
  ↓ combined effect:
vision_CMM01/result fail rate = 18%
mes/batch_tracking.first_pass_yield_pct = 82%
erp/quality/holds.hold_count = 1
```
**This is the AI showcase scenario**: nothing individual is alarming. Only cross-system AI analysis finds the root cause.

**Pattern 5: Compressed Air Leak Detection**
```
utilities/compressor_CP01/telemetry.loaded_pct = 95% (was 72%)
utilities/compressor_CP01/power.total_kw = 29.7 (was 22)
  ↓ (pressure distribution)
utilities/air_network/pressure.zone_a_press_bar = 6.1 (zones B=7.1, C=7.2)
utilities/air_network/pressure.leak_detected = true
utilities/air_network/pressure.estimated_leak_m3h = 4.2
```
Zone A pressure differential points to leak location. Compressor load increase confirms.

**Pattern 6: ERP-to-OT Integration** (Material Shortage scenario)
```
erp/materials/consumption.materials[0].stock_warning = true (ALU_SHEET_2MM = 387 kg)
erp/production_orders/current.status = BLOCKED
erp/production_orders/current.alert = "Material shortage..."
  ↓ (ISA-95 L4 → L3 → L2)
mes/work_orders/active.status = WAITING_MATERIAL
plant/process/unit_id.line_01_status → "Running" (countdown to Starved)
```
Shows ISA-95 hierarchy in action: business event → shopfloor impact.

**Pattern 7: Oven Event → Full Integration Stack** (Batch Quality Hold)
```
line_03_curing/oven_OV01/telemetry.zone_2_temp_c = 155 (-45°C deviation)
  ↓ automatic cascade (no human action)
mes/batch_tracking.batch_status = ON_HOLD
erp/quality/holds.active_holds[0].hold_id = "QH-BATCH-001"
line_04_inspection/cell_02/process/step_status — 156 units flagged
```
Shows MES → ERP → DPP integration happening automatically from one OT sensor event.

---

## Publish Rate Summary

| Interval | Streams | Topics |
|----------|---------|--------|
| 5s (high-freq) | 33 | PLC telemetry, 3-phase power for all assets |
| 10s | 6 | Compressor telemetry, air network, plant process, RFID |
| 15s | 5 | CMM inspection, SPC press force, draw depth |
| 20s | 5 | Leak test, MES batch, DPP events, SPC wall/coat |
| 30s | 33 | Energy rollups, MES performance, health (fast), ERP orders |
| 60s | 26 | Health (slow), alarms, PdM, MES shift, ERP materials |

**Total published per minute at 7.5 msg/s:** ~450 messages

---

## Broker Connection Details

| Parameter | Value |
|-----------|-------|
| Host | `mqtt.iotdemozone.com` |
| Port | `1883` (MQTT) |
| Username | `admin` |
| Subscribe topic | `aurora/#` |
| QoS | 0 (telemetry), 1 (alarms, DPP events) |
| Retained | No |
| Client ID pattern | `aurora-sim-{timestamp}` |

**MQTT Explorer filter:** Subscribe to `aurora/#` — all 111 streams will appear sorted by hierarchy, mirroring the Streams tab in the simulator dashboard.
