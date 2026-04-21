"""
Aurora Industries — UNS Stream Model
=====================================
Battery case manufacturing plant — Leipzig, Germany
Products: BAT-CASE-AL-001 (aluminium EV battery case shells)

Line topology:
  line_01_assembly  → press_PR01, press_PR02, conveyor_CV01/CV02, robot_R1/R2
  line_02_painting  → sprayer_SP01/SP02, conveyor_CV03, robot_R3
  line_03_curing    → oven_OV01, conveyor_CV04
  line_04_inspection→ vision_CMM01, leak_test_LT01

Each asset emits:
  - 3-phase power (V, A, kW, PF per phase + total)
  - Asset-specific process telemetry
  - Performance KPIs (OEE, cycle time, quality)
  - Health scores + RUL per component
  - Alarms
  - Analytics (anomaly score, predictive maintenance score)

AI-demo scenarios inject realistic degradation patterns that an AI can detect
and explain — designed to show value of LLM reasoning over sensor data.
"""
from __future__ import annotations
import math
import random
import time
from typing import Any, Callable

# ─────────────────────────────────────────────────────────────────────────────
# Shared simulation state (mutable, reset on /api/reset)
# ─────────────────────────────────────────────────────────────────────────────
class _SharedState:
    def __init__(self):
        self.reset()

    def reset(self):
        self.t0           = time.time()
        self.cycle_count  = {a: random.randint(100_000, 600_000) for a in _ASSET_IDS}
        self.kwh_total    = {a: round(random.uniform(10_000, 80_000), 1) for a in _ASSET_IDS}
        self.health       = {a: {**_default_health(a)} for a in _ASSET_IDS}
        self.batch_seq    = 1
        self.unit_seq     = 1
        self.current_batch= _new_batch(1)
        self.current_product = "BAT-CASE-AL-001"
        self.shift        = "A"

_ASSET_IDS = [
    "press_PR01","press_PR02",
    "conveyor_CV01","conveyor_CV02","conveyor_CV03","conveyor_CV04",
    "robot_R1","robot_R2","robot_R3",
    "sprayer_SP01","sprayer_SP02",
    "oven_OV01",
    "vision_CMM01","leak_test_LT01",
    "compressor_CP01",
]

def _default_health(asset_id: str) -> dict:
    """Randomised initial health scores per component."""
    profiles = {
        "press":     [("HydraulicPump",random.uniform(45,92)),("MainSeal",random.uniform(60,98)),("Accumulator",random.uniform(80,99)),("PressGuide",random.uniform(85,99))],
        "conveyor":  [("DriveMotor",random.uniform(70,99)),("BeltTension",random.uniform(65,99)),("Bearing",random.uniform(55,95))],
        "robot":     [("JointA1",random.uniform(75,99)),("JointA2",random.uniform(75,99)),("WristUnit",random.uniform(70,98))],
        "oven":      [("Zone1Heater",random.uniform(75,99)),("Zone2Heater",random.uniform(75,99)),("FanAssembly",random.uniform(60,95)),("ExhaustSystem",random.uniform(80,99))],
        "sprayer":   [("Nozzle",random.uniform(60,95)),("FluidPump",random.uniform(70,99)),("FilterUnit",random.uniform(55,90))],
        "compressor":[("Piston",random.uniform(75,99)),("Valve",random.uniform(70,99)),("Intercooler",random.uniform(80,99))],
        "vision":    [("CameraA",random.uniform(80,99)),("Lighting",random.uniform(75,99))],
        "leak_test": [("PressureSensor",random.uniform(80,99)),("FixtureSeal",random.uniform(60,95))],
    }
    for prefix, comps in profiles.items():
        if prefix in asset_id:
            return {n: {"score": round(s,1), "rul_days": round(s * 7.5), "deg": round(random.uniform(0.02,0.8),3)} for n,s in comps}
    return {"Overall": {"score": round(random.uniform(70,99),1), "rul_days": 365, "deg": 0.05}}

def _new_batch(seq: int) -> str:
    from datetime import date
    return f"BATCH-{date.today().strftime('%Y-%m%d')}-{seq:03d}"

SIM = _SharedState()


# ─────────────────────────────────────────────────────────────────────────────
# Generator helpers
# ─────────────────────────────────────────────────────────────────────────────
def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")

def jitter(v, pct=0.02):
    return round(v * (1 + random.gauss(0, pct)), 3)

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def _3phase(nom_kw: float, fault_factor: float = 1.0, shared: dict = {}) -> dict:
    """Generate 3-phase power payload. fault_factor < 1 simulates phase imbalance or overload."""
    kw_total = clamp(jitter(nom_kw * fault_factor, 0.03), nom_kw*0.3, nom_kw*1.4)
    v = 400.0
    pf = clamp(jitter(0.91, 0.02), 0.75, 1.0)
    i_per_phase = kw_total * 1000 / (3 * v * pf)

    # Phase imbalance scenario: if fault_factor < 0.8, phase C carries more
    ia = jitter(i_per_phase, 0.015)
    ib = jitter(i_per_phase, 0.015)
    ic = jitter(i_per_phase * (1.0 if fault_factor >= 0.8 else 1.25), 0.015)

    kw_a = round(v * ia * pf / 1000, 2)
    kw_b = round(v * ib * pf / 1000, 2)
    kw_c = round(v * ic * pf / 1000, 2)

    return {
        "timestamp": _now(),
        "total_kw":  round(kw_a + kw_b + kw_c, 2),
        "total_kva": round((kw_a + kw_b + kw_c) / pf, 2),
        "power_factor": round(pf, 3),
        "phases": {
            "A": {"voltage_v": round(v,1), "current_a": round(ia,2), "kw": kw_a},
            "B": {"voltage_v": round(v,1), "current_a": round(ib,2), "kw": kw_b},
            "C": {"voltage_v": round(v,1), "current_a": round(ic,2), "kw": kw_c},
        },
        "thd_pct": round(jitter(2.5 if fault_factor >= 0.8 else 8.5, 0.1), 1),
    }

def _energy_rollup(asset_id: str, nom_kw: float, interval_s: float, fault_factor: float = 1.0) -> dict:
    kw = clamp(jitter(nom_kw * fault_factor, 0.03), nom_kw*0.2, nom_kw*1.5)
    SIM.kwh_total[asset_id] = round(SIM.kwh_total.get(asset_id,0) + kw*(interval_s/3600), 2)
    return {
        "timestamp":        _now(),
        "asset_id":         asset_id,
        "current_kw":       round(kw, 2),
        "total_kwh":        SIM.kwh_total[asset_id],
        "energy_per_cycle_wh": round(kw * 3600 / max(1, _cycle_rate(asset_id)), 1),
        "co2_kg_per_kwh":   0.233,
        "co2_total_kg":     round(SIM.kwh_total[asset_id] * 0.233, 1),
    }

def _cycle_rate(asset_id: str) -> float:
    defaults = {"press_PR01":450,"press_PR02":450,"oven_OV01":3,"vision_CMM01":80,"leak_test_LT01":60}
    for k,v in defaults.items():
        if k in asset_id: return v
    return 100

def _health(asset_id: str, shared: dict) -> dict:
    h = SIM.health.get(asset_id, {})
    # Degrade slowly over time; scenario can accelerate specific components
    scenario_deg = shared.get("health_degrade", {}).get(asset_id, {})
    components = {}
    for name, c in h.items():
        extra_deg = scenario_deg.get(name, 0)
        c["score"] = round(clamp(c["score"] - (c["deg"] + extra_deg) / 288, 0, 100), 1)
        c["rul_days"] = round(max(0, c["score"] * 7.5))
        components[name] = {"score": c["score"], "rul_days": c["rul_days"], "degradation_rate_pct_per_day": round(c["deg"] + extra_deg, 3)}
    return {"timestamp": _now(), "asset_id": asset_id, "overall_score": round(sum(c["score"] for c in components.values())/max(1,len(components)),1), "components": components}


# ─────────────────────────────────────────────────────────────────────────────
# Asset-specific generators
# ─────────────────────────────────────────────────────────────────────────────

def _press_telemetry(asset_id: str, nom_pressure: float, nom_force: float, nom_temp: float, shared: dict) -> dict:
    fault = shared.get("fault")
    pressure_offset = -30 if fault == f"{asset_id}_pressure_low" else (-15 if fault == f"{asset_id}_seal_leak" else 0)
    temp_offset     = +30 if fault == f"{asset_id}_overtemp" else 0
    force_offset    = +80 if fault == f"{asset_id}_force_dev" else 0
    return {
        "timestamp":        _now(),
        "asset_id":         asset_id,
        "hydraulic_pressure_bar": clamp(jitter(nom_pressure + pressure_offset, 0.02), 140, 230),
        "oil_temperature_c":     clamp(jitter(nom_temp + temp_offset, 0.025), 35, 90),
        "press_force_kn":        clamp(jitter(nom_force + force_offset, 0.035), 550, 950),
        "stroke_position_mm":    round(random.uniform(50, 480)),
        "stroke_count":          SIM.cycle_count.get(asset_id, 0),
        "lube_pressure_bar":     clamp(jitter(4.2, 0.03), 2.5, 6.0),
        "vibration_mm_s":        clamp(jitter(1.8 if not fault else 5.2, 0.15), 0.1, 20),
        "status":                "fault" if fault and asset_id in fault else "normal",
    }

def _press_performance(asset_id: str, nom_ct: float, shared: dict) -> dict:
    fault = shared.get("fault")
    ct = nom_ct * (1.25 if fault and asset_id in fault else random.uniform(0.95, 1.12))
    SIM.cycle_count[asset_id] = SIM.cycle_count.get(asset_id, 0) + 1
    oee = clamp(jitter(72 if fault and asset_id in fault else 79, 0.04), 40, 95)
    return {
        "timestamp":          _now(),
        "asset_id":           asset_id,
        "operational_status": "Faulted" if fault and asset_id in fault else "Running",
        "oee":                round(oee, 1),
        "availability":       round(oee / random.uniform(0.93, 0.98), 1),
        "performance_kpi":    round(random.uniform(88, 98), 1),
        "quality":            round(random.uniform(95, 99.5), 1),
        "cycle_time_s":       round(ct, 2),
        "cycle_time_target_s":nom_ct,
        "cycle_count":        SIM.cycle_count[asset_id],
        "production_rate_hr": round(3600 / ct),
        "current_product":    SIM.current_product,
        "current_batch":      SIM.current_batch,
        "shift":              shared.get("shift","A"),
    }

def _oven_telemetry(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    zone_offsets = [0,0,0,0]
    if fault == "oven_OV01_zone2_fail": zone_offsets[1] = -110
    if fault == "oven_OV01_overshoot":  zone_offsets = [+22,+25,+24,+18]
    nom = [180, 200, 200, 170]
    temps = [round(clamp(jitter(nom[i] + zone_offsets[i], 0.008), 50, 270), 1) for i in range(4)]
    fan_fault = fault == "oven_OV01_fan_fail"
    fan_rpm   = clamp(jitter(1450 if not fan_fault else 380, 0.03), 200, 1600)
    exhaust   = clamp(jitter(88 + (10 if "overshoot" in fault else 0), 0.03), 40, 160)
    return {
        "timestamp":    _now(),
        "asset_id":     "oven_OV01",
        "zone1_temp_c": temps[0], "zone2_temp_c": temps[1],
        "zone3_temp_c": temps[2], "zone4_temp_c": temps[3],
        "zone_setpoints_c":  [180, 200, 200, 170],
        "zone_deviations_c": [round(temps[i]-nom[i],1) for i in range(4)],
        "fan_speed_rpm":     round(fan_rpm),
        "exhaust_temp_c":    round(exhaust, 1),
        "chamber_pressure_pa": round(jitter(-5.0, 0.05), 2),
        "conveyor_speed_mpm":  round(jitter(0.5, 0.02), 3),
        "status":       "fault" if fault and "oven" in fault else "normal",
    }

def _conveyor_telemetry(asset_id: str, nom_speed: float, shared: dict) -> dict:
    fault = shared.get("fault","")
    speed_factor = 0.0 if fault == f"{asset_id}_jam" else (0.55 if fault == f"{asset_id}_slip" else 1.0)
    speed = clamp(jitter(nom_speed * speed_factor, 0.025), 0, nom_speed * 1.1)
    return {
        "timestamp":     _now(),
        "asset_id":      asset_id,
        "speed_ms":      round(speed, 3),
        "speed_setpoint_ms": nom_speed,
        "belt_tension_n":   round(clamp(jitter(850 if speed_factor > 0 else 200, 0.04), 100, 1500)),
        "bearing_temp_c":   round(clamp(jitter(38 if speed_factor > 0 else 72, 0.05), 20, 95), 1),
        "jam_detected":     speed_factor == 0.0,
        "units_on_belt":    random.randint(3, 12),
    }

def _robot_telemetry(asset_id: str, task: str, shared: dict) -> dict:
    fault = shared.get("fault","")
    faulted = fault == f"{asset_id}_position_error" or fault == f"{asset_id}_collision"
    return {
        "timestamp":       _now(),
        "asset_id":        asset_id,
        "state":           "Faulted" if faulted else "Running",
        "task":            task,
        "position_error_mm": round(jitter(0.05 if not faulted else 12.5, 0.2), 3),
        "joint_temps_c":   [round(clamp(jitter(42, 0.03), 25, 85), 1) for _ in range(6)],
        "cycle_time_s":    round(jitter(4.2 if not faulted else 0, 0.05), 2),
        "parts_per_hour":  round(3600 / 4.2) if not faulted else 0,
        "teach_point_offset_mm": round(jitter(0.02 if not faulted else 0.85, 0.3), 3),
    }

def _sprayer_telemetry(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault","")
    blocked   = fault == f"{asset_id}_filter_blocked"
    nozzle_clog = fault == f"{asset_id}_nozzle_clog"
    pressure  = clamp(jitter(3.5 * (0.55 if blocked else (0.75 if nozzle_clog else 1.0)), 0.03), 0.5, 6.0)
    return {
        "timestamp":          _now(),
        "asset_id":           asset_id,
        "supply_pressure_bar":round(pressure, 2),
        "atomisation_pressure_bar": round(pressure * 0.85, 2),
        "fluid_flow_lpm":     round(clamp(jitter(1.8 * (0.6 if nozzle_clog else 1.0), 0.03), 0.1, 4.0), 3),
        "paint_temp_c":       round(clamp(jitter(22.5, 0.02), 18, 32), 1),
        "filter_dp_bar":      round(clamp(jitter(0.12 if not blocked else 0.68, 0.05), 0.02, 1.0), 3),
        "filter_status":      "BLOCKED" if blocked else "OK",
        "coat_thickness_um":  round(clamp(jitter(80 if not nozzle_clog else 45, 0.05), 20, 140), 1),
        "gun_voltage_kv":     round(clamp(jitter(70, 0.02), 50, 90), 1),
    }

def _compressor_telemetry(shared: dict) -> dict:
    fault = shared.get("fault","")
    overload = fault == "compressor_CP01_overload"
    return {
        "timestamp":           _now(),
        "asset_id":            "compressor_CP01",
        "outlet_pressure_bar": round(clamp(jitter(7.5 if not overload else 5.8, 0.02), 4, 10), 2),
        "inlet_temp_c":        round(clamp(jitter(22, 0.02), 10, 40), 1),
        "outlet_temp_c":       round(clamp(jitter(78 if not overload else 105, 0.03), 50, 130), 1),
        "flow_rate_m3h":       round(clamp(jitter(15.5, 0.03), 5, 25), 2),
        "vibration_mm_s":      round(clamp(jitter(2.1 if not overload else 9.8, 0.1), 0.1, 20), 2),
        "oil_level_pct":       round(clamp(jitter(78, 0.01), 10, 100), 1),
        "run_hours":           round(random.uniform(4500, 25000)),
        "status":              "Overload" if overload else "Running",
    }

def _inspection_result(asset_id: str, method: str, pass_rate: float, shared: dict) -> dict:
    fault = shared.get("fault","")
    degraded = fault == f"{asset_id}_sensor_fault"
    actual_pass_rate = pass_rate * (0.85 if degraded else 1.0)
    passed = random.random() < actual_pass_rate
    SIM.unit_seq += 1
    return {
        "timestamp":   _now(),
        "asset_id":    asset_id,
        "method":      method,
        "unit_id":     f"UNIT-{SIM.unit_seq:06d}",
        "batch_id":    SIM.current_batch,
        "result":      "PASS" if passed else "FAIL",
        "confidence":  round(random.uniform(0.92, 0.999), 3),
        "cycle_time_s":round(jitter(45 if "vision" in asset_id else 60, 0.04), 1),
        "sensor_status": "degraded" if degraded else "ok",
    }

def _alarm(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    alarms = []
    if fault and (asset_id.split("_")[0] in fault or asset_id in fault):
        fault_meta = _FAULT_META.get(fault, {"code":"E-GENERIC","name":fault,"severity":"warning","description":f"Active fault: {fault}"})
        alarms.append({
            "alarm_id":    f"ALM-{asset_id.upper()[:8]}-001",
            "alarm_code":  fault_meta["code"],
            "alarm_name":  fault_meta["name"],
            "severity":    fault_meta["severity"],
            "raised_at":   _now(),
            "acknowledged":False,
            "description": fault_meta["description"],
        })
    return {"timestamp": _now(), "asset_id": asset_id, "active_alarms": alarms, "alarm_count": len(alarms)}

def _analytics_anomaly(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault","")
    is_faulted = bool(fault and (asset_id.split("_")[0] in fault or asset_id in fault))
    score = clamp(jitter(0.72 if is_faulted else 0.08, 0.3), 0, 1.0)
    return {
        "timestamp":    _now(),
        "asset_id":     asset_id,
        "anomaly_score":round(score, 3),
        "anomaly_level":"HIGH" if score > 0.6 else ("MEDIUM" if score > 0.3 else "LOW"),
        "contributing_signals": ["hydraulic_pressure","oil_temperature","vibration"] if is_faulted else [],
        "recommended_action":   "Inspect hydraulic system" if is_faulted else "No action required",
        "model_version":        "aurora-anomaly-v2.1",
    }

def _predictive_maintenance(asset_id: str, shared: dict) -> dict:
    h = SIM.health.get(asset_id, {})
    min_score = min((c["score"] for c in h.values()), default=80)
    min_rul   = min((c["rul_days"] for c in h.values()), default=365)
    fault     = shared.get("fault","")
    if fault and (asset_id.split("_")[0] in fault or asset_id in fault):
        min_rul = max(1, min_rul // 3)
    urgency = "IMMEDIATE" if min_rul < 7 else ("SOON" if min_rul < 30 else ("PLANNED" if min_rul < 90 else "OK"))
    return {
        "timestamp":        _now(),
        "asset_id":         asset_id,
        "min_health_score": round(min_score, 1),
        "min_rul_days":     min_rul,
        "maintenance_urgency": urgency,
        "next_recommended_date": _rul_date(min_rul),
        "estimated_downtime_h": round(random.uniform(2, 12), 1) if urgency != "OK" else 0,
        "cost_if_ignored_eur":  round(min_rul * random.uniform(100, 500)) if urgency != "OK" else 0,
    }

def _rul_date(days: int) -> str:
    from datetime import date, timedelta
    return (date.today() + timedelta(days=days)).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Energy rollup topics (cell + line + plant level)
# ─────────────────────────────────────────────────────────────────────────────
_CELL_ASSETS = {
    "line_01_assembly/cell_01": ["press_PR01","conveyor_CV01","robot_R1"],
    "line_01_assembly/cell_02": ["press_PR02","conveyor_CV02","robot_R2"],
    "line_02_painting/cell_01": ["sprayer_SP01","sprayer_SP02","conveyor_CV03","robot_R3"],
    "line_03_curing/cell_01":   ["oven_OV01","conveyor_CV04"],
    "line_04_inspection/cell_01":["vision_CMM01"],
    "line_04_inspection/cell_02":["leak_test_LT01"],
}
_ASSET_NOM_KW = {
    "press_PR01":16.8,"press_PR02":16.8,"conveyor_CV01":3.5,"conveyor_CV02":3.5,
    "conveyor_CV03":2.2,"conveyor_CV04":1.8,"robot_R1":5.5,"robot_R2":5.5,"robot_R3":4.2,
    "sprayer_SP01":2.8,"sprayer_SP02":2.8,"oven_OV01":45.0,"vision_CMM01":1.2,
    "leak_test_LT01":0.8,"compressor_CP01":22.0,
}
_ASSET_LINE = {
    "press_PR01":"line_01_assembly","press_PR02":"line_01_assembly",
    "conveyor_CV01":"line_01_assembly","conveyor_CV02":"line_01_assembly",
    "robot_R1":"line_01_assembly","robot_R2":"line_01_assembly",
    "sprayer_SP01":"line_02_painting","sprayer_SP02":"line_02_painting",
    "conveyor_CV03":"line_02_painting","robot_R3":"line_02_painting",
    "oven_OV01":"line_03_curing","conveyor_CV04":"line_03_curing",
    "vision_CMM01":"line_04_inspection","leak_test_LT01":"line_04_inspection",
    "compressor_CP01":"utilities",
}

def _fault_factor(asset_id: str, shared: dict) -> float:
    fault = shared.get("fault","")
    if fault and (asset_id in fault or asset_id.split("_")[0] in fault):
        return random.uniform(0.4, 0.75)
    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Fault metadata (for alarm payloads)
# ─────────────────────────────────────────────────────────────────────────────
_FAULT_META = {
    "press_PR01_pressure_low":  {"code":"E-PRESS-002","name":"Hydraulic Pressure Low","severity":"critical","description":"PR01 hydraulic pressure dropped below 192 bar — possible pump wear or seal failure"},
    "press_PR01_overtemp":      {"code":"E-PRESS-003","name":"Oil Overtemperature","severity":"critical","description":"PR01 hydraulic oil temperature exceeded 75°C — check cooler and oil level"},
    "press_PR01_seal_leak":     {"code":"E-PRESS-004","name":"Hydraulic Seal Leak","severity":"warning","description":"PR01 oil leak detected on main cylinder seal — early sign of failure"},
    "press_PR01_force_dev":     {"code":"E-PRESS-005","name":"Press Force Deviation","severity":"warning","description":"PR01 press force deviates >5% from setpoint — check tool wear"},
    "press_PR02_pressure_low":  {"code":"E-PRESS-012","name":"Hydraulic Pressure Low","severity":"critical","description":"PR02 hydraulic pressure dropped below 192 bar"},
    "press_PR02_overtemp":      {"code":"E-PRESS-013","name":"Oil Overtemperature","severity":"critical","description":"PR02 hydraulic oil overtemperature"},
    "press_PR02_seal_leak":     {"code":"E-PRESS-014","name":"Hydraulic Seal Leak","severity":"warning","description":"PR02 oil leak on main cylinder seal"},
    "oven_OV01_zone2_fail":     {"code":"E-OVEN-001","name":"Zone 2 Heater Failure","severity":"critical","description":"OV01 zone 2 heater element failure — cure quality at risk"},
    "oven_OV01_overshoot":      {"code":"E-OVEN-002","name":"Temperature Overshoot","severity":"critical","description":"OV01 all zones above setpoint — thermal runaway risk"},
    "oven_OV01_fan_fail":       {"code":"E-OVEN-003","name":"Circulation Fan Failure","severity":"critical","description":"OV01 air circulation fan stopped — thermal uniformity lost"},
    "conveyor_CV01_jam":        {"code":"E-CV-001","name":"Belt Jam","severity":"critical","description":"CV01 belt stopped — obstruction detected"},
    "conveyor_CV01_slip":       {"code":"E-CV-002","name":"Belt Slip","severity":"warning","description":"CV01 belt speed below setpoint — check tension"},
    "conveyor_CV03_jam":        {"code":"E-CV-011","name":"Belt Jam","severity":"critical","description":"CV03 belt stopped — paint line blocked"},
    "robot_R1_position_error":  {"code":"E-ROB-001","name":"Position Error","severity":"critical","description":"R1 end-effector position error > 0.5mm — weld quality at risk"},
    "robot_R1_collision":       {"code":"E-ROB-002","name":"Collision Detected","severity":"critical","description":"R1 collision sensor triggered — emergency stop"},
    "robot_R3_position_error":  {"code":"E-ROB-011","name":"Spray Robot Position Error","severity":"critical","description":"R3 spray head position error — coat uniformity at risk"},
    "sprayer_SP02_filter_blocked":{"code":"E-SP-001","name":"Paint Filter Blocked","severity":"warning","description":"SP02 filter differential pressure exceeded — replace filter"},
    "sprayer_SP02_nozzle_clog": {"code":"E-SP-002","name":"Nozzle Clog","severity":"warning","description":"SP02 nozzle partial blockage — flow rate reduced 40%"},
    "compressor_CP01_overload": {"code":"E-CP-001","name":"Compressor Overload","severity":"critical","description":"CP01 outlet pressure below 6 bar — check plant air demand"},
    "vision_CMM01_sensor_fault":{"code":"E-INS-001","name":"Vision Sensor Fault","severity":"warning","description":"CMM01 calibration drift detected — dimensional accuracy reduced"},
}


# ─────────────────────────────────────────────────────────────────────────────
# FAULT SCENARIOS  (AI-demo rich scenarios)
# ─────────────────────────────────────────────────────────────────────────────
FAULT_SCENARIOS = {
    "normal": {
        "id": "normal", "label": "Normal Operation",
        "description": "All assets operating within normal parameters.",
        "fault_key": None, "affected": [],
        "ai_hint": "No anomalies. Plant OEE ~79%. Energy consumption nominal.",
    },
    "press_PR01_hydraulic_degradation": {
        "id": "press_PR01_hydraulic_degradation",
        "label": "PR01 — Hydraulic Pump Wear (Early Stage)",
        "description": "PR01 hydraulic pressure slowly declining. Oil temp rising. Pump efficiency dropping. Classic early-stage hydraulic pump wear — AI should detect before alarm threshold is hit.",
        "fault_key": "press_PR01_pressure_low",
        "affected": ["press_PR01"],
        "stop_publishing": False,
        "health_degrade": {"press_PR01": {"HydraulicPump": 0.8}},
        "ai_hint": "Pressure trending down -0.8 bar/day over 3 days. Oil temp +3°C. Pump efficiency -12%. Recommend hydraulic pump inspection within 5 days.",
    },
    "oven_zone2_heater_failure": {
        "id": "oven_zone2_heater_failure",
        "label": "OV01 — Zone 2 Heater Element Failure",
        "description": "Zone 2 temperature dropped 110°C below setpoint. Parts curing in zone 2 will be undercured. Downstream quality risk. AI should flag batch for hold and recommend maintenance.",
        "fault_key": "oven_OV01_zone2_fail",
        "affected": ["oven_OV01"],
        "stop_publishing": False,
        "ai_hint": "Zone 2 temp = 90°C vs 200°C setpoint. Zones 1/3/4 normal. Heater element failure. All parts in current batch (BATCH-2026-XXXX) should be placed on quality hold. Estimated cure deficiency: 55% of required dwell time at temperature.",
    },
    "paint_filter_blockage": {
        "id": "paint_filter_blockage",
        "label": "SP02 — Paint Filter Progressive Blockage",
        "description": "SP02 paint filter differential pressure rising over 2 hours. Atomisation pressure dropping. Coat thickness falling below 60µm minimum. AI should detect correlation between filter DP and coat thickness before visual inspection would catch it.",
        "fault_key": "sprayer_SP02_filter_blocked",
        "affected": ["sprayer_SP02"],
        "stop_publishing": False,
        "ai_hint": "Filter DP: 0.68 bar (limit 0.5 bar). Coat thickness: 45µm (min 60µm). Atomisation pressure: 1.9 bar (setpoint 3.0 bar). Recommend: replace filter immediately, quality hold on last 45 min of production.",
    },
    "conveyor_cv01_jam": {
        "id": "conveyor_cv01_jam",
        "label": "CV01 — Belt Jam (Line 1 Cell 1 Blocked)",
        "description": "CV01 belt stopped. Press PR01 starved of parts. Line 1 Cell 1 production halted. AI should calculate throughput loss, identify root cause, and suggest recovery sequence.",
        "fault_key": "conveyor_CV01_jam",
        "affected": ["conveyor_CV01","press_PR01"],
        "stop_publishing": False,
        "ai_hint": "CV01 speed = 0 m/s. Press PR01 cycle count frozen. Estimated production loss: 7.5 units/min. Recovery: check belt tension, clear jam, restart in sequence CV01 → PR01. ETA to recovery: 15-20 min.",
    },
    "energy_anomaly_night_shift": {
        "id": "energy_anomaly_night_shift",
        "label": "Energy Anomaly — Compressor Off-Hours Overconsumption",
        "description": "Compressor CP01 drawing 35% more power than baseline during night shift. Phase C current imbalance detected. AI should identify energy waste and recommend investigation.",
        "fault_key": "compressor_CP01_overload",
        "affected": ["compressor_CP01"],
        "stop_publishing": False,
        "ai_hint": "CP01 consuming 29.7 kW vs 22 kW baseline (+35%). Phase C current 18A vs 12A nominal (50% imbalance). THD: 8.5% (limit 5%). Power factor: 0.73 (expected 0.91). Likely cause: valve wear or intercooler fouling. Annual excess cost if unaddressed: ~€8,400.",
    },
    "multi_asset_cascade": {
        "id": "multi_asset_cascade",
        "label": "Cascade Failure — Hydraulic + Downstream Quality",
        "description": "PR01 hydraulic seal leak → reduced press force → underdimensioned casings → CMM vision system catching failures. AI should trace root cause through the causal chain.",
        "fault_key": "press_PR01_seal_leak",
        "affected": ["press_PR01","vision_CMM01"],
        "stop_publishing": False,
        "health_degrade": {"press_PR01": {"MainSeal": 1.5, "HydraulicPump": 0.4}},
        "ai_hint": "Causal chain: PR01 seal leak (-15 bar) → press force deviation (+80 kN) → case wall thickness out of tolerance (+0.3mm) → CMM fail rate 18% (vs 3% baseline). Root cause: PR01 MainSeal (health: 42). Fix: replace seal → quality returns to baseline.",
    },
    "oven_thermal_runaway": {
        "id": "oven_thermal_runaway",
        "label": "OV01 — Thermal Runaway (All Zones Overshoot)",
        "description": "OV01 temperature controller fault — all zones overshooting setpoint by 20-25°C. Paint on casings may be scorched. Emergency scenario for AI to recommend immediate stop and quality assessment.",
        "fault_key": "oven_OV01_overshoot",
        "affected": ["oven_OV01"],
        "stop_publishing": False,
        "ai_hint": "All zones 20-25°C above setpoint. Exhaust temp: 98°C (normal: 85°C). Conveyor speed normal. Recommended action: STOP line immediately, hold all parts from last 20 min, inspect controller PID tuning, check thermocouple calibration.",
    },
    "robot_R1_weld_drift": {
        "id": "robot_R1_weld_drift",
        "label": "R1 — Weld Robot Teach-Point Drift",
        "description": "Robot R1 weld positions drifting 0.8mm from teach points. Weld quality degrading gradually. AI should detect pattern before weld failures cause scrap.",
        "fault_key": "robot_R1_position_error",
        "affected": ["robot_R1"],
        "stop_publishing": False,
        "health_degrade": {"robot_R1": {"JointA1": 0.6, "WristUnit": 0.9}},
        "ai_hint": "R1 position error: 0.85mm (limit 0.5mm). JointA1 health: 71% (degrading 0.6%/day). WristUnit health: 68%. Teach-point drift increasing over 72h. Recommend: recalibrate teach points, check joint backlash, schedule bearing inspection JointA1.",
    },
}

# Add scenario to dict values for API listing
for _k, _v in FAULT_SCENARIOS.items():
    _v.setdefault("id", _k)


# ─────────────────────────────────────────────────────────────────────────────
# STREAM DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────
def _s(sid, label, topic, area, source, source_detail, unit, interval, location, asset_id, asset_type, gen_fn):
    return {
        "id": sid, "label": label, "topic": topic, "area": area,
        "source": source, "source_detail": source_detail, "unit": unit,
        "interval": interval, "location": location,
        "asset_id": asset_id, "asset_type": asset_type, "gen": gen_fn,
    }

_BASE = "aurora"

def _make_streams():
    s = []

    # ── PRESS PR01 ──────────────────────────────────────────────────────────
    s.append(_s("pr01_telem","PR01 Process Telemetry",f"{_BASE}/line_01_assembly/cell_01/assets/press_PR01/telemetry",
        "Line 01","PLC","Hydraulic Press Controller","multi",5,"Cell 01","press_PR01","press",
        lambda sh: _press_telemetry("press_PR01",210,750,50,sh)))
    s.append(_s("pr01_power","PR01 3-Phase Power",f"{_BASE}/line_01_assembly/cell_01/assets/press_PR01/power",
        "Line 01","PLC","Power Meter PM-PR01","kW",5,"Cell 01","press_PR01","press",
        lambda sh: _3phase(16.8, _fault_factor("press_PR01",sh), sh)))
    s.append(_s("pr01_energy","PR01 Energy Rollup",f"{_BASE}/line_01_assembly/cell_01/assets/press_PR01/energy",
        "Line 01","MES","Energy Manager","kWh",30,"Cell 01","press_PR01","press",
        lambda sh: _energy_rollup("press_PR01",16.8,30,_fault_factor("press_PR01",sh))))
    s.append(_s("pr01_perf","PR01 Performance KPIs",f"{_BASE}/line_01_assembly/cell_01/assets/press_PR01/performance",
        "Line 01","MES","OEE Module","multi",30,"Cell 01","press_PR01","press",
        lambda sh: _press_performance("press_PR01",8.0,sh)))
    s.append(_s("pr01_health","PR01 Health Monitoring",f"{_BASE}/line_01_assembly/cell_01/assets/press_PR01/health",
        "Line 01","SCADA","Condition Monitor","score",30,"Cell 01","press_PR01","press",
        lambda sh: _health("press_PR01",sh)))
    s.append(_s("pr01_alarms","PR01 Alarms",f"{_BASE}/line_01_assembly/cell_01/assets/press_PR01/alarms",
        "Line 01","PLC","Alarm Manager","",60,"Cell 01","press_PR01","press",
        lambda sh: _alarm("press_PR01",sh)))
    s.append(_s("pr01_anomaly","PR01 Anomaly Score",f"{_BASE}/line_01_assembly/analytics/anomaly/press_PR01",
        "Line 01","AI","Aurora-AI Anomaly Engine","score",30,"Cell 01","press_PR01","press",
        lambda sh: _analytics_anomaly("press_PR01",sh)))
    s.append(_s("pr01_pdm","PR01 Predictive Maintenance",f"{_BASE}/line_01_assembly/analytics/pdm/press_PR01",
        "Line 01","AI","Aurora-AI PdM Engine","days",60,"Cell 01","press_PR01","press",
        lambda sh: _predictive_maintenance("press_PR01",sh)))

    # ── PRESS PR02 ──────────────────────────────────────────────────────────
    s.append(_s("pr02_telem","PR02 Process Telemetry",f"{_BASE}/line_01_assembly/cell_02/assets/press_PR02/telemetry",
        "Line 01","PLC","Hydraulic Press Controller","multi",5,"Cell 02","press_PR02","press",
        lambda sh: _press_telemetry("press_PR02",210,750,50,sh)))
    s.append(_s("pr02_power","PR02 3-Phase Power",f"{_BASE}/line_01_assembly/cell_02/assets/press_PR02/power",
        "Line 01","PLC","Power Meter PM-PR02","kW",5,"Cell 02","press_PR02","press",
        lambda sh: _3phase(16.8, _fault_factor("press_PR02",sh), sh)))
    s.append(_s("pr02_energy","PR02 Energy Rollup",f"{_BASE}/line_01_assembly/cell_02/assets/press_PR02/energy",
        "Line 01","MES","Energy Manager","kWh",30,"Cell 02","press_PR02","press",
        lambda sh: _energy_rollup("press_PR02",16.8,30,_fault_factor("press_PR02",sh))))
    s.append(_s("pr02_perf","PR02 Performance KPIs",f"{_BASE}/line_01_assembly/cell_02/assets/press_PR02/performance",
        "Line 01","MES","OEE Module","multi",30,"Cell 02","press_PR02","press",
        lambda sh: _press_performance("press_PR02",8.0,sh)))
    s.append(_s("pr02_health","PR02 Health Monitoring",f"{_BASE}/line_01_assembly/cell_02/assets/press_PR02/health",
        "Line 01","SCADA","Condition Monitor","score",30,"Cell 02","press_PR02","press",
        lambda sh: _health("press_PR02",sh)))
    s.append(_s("pr02_alarms","PR02 Alarms",f"{_BASE}/line_01_assembly/cell_02/assets/press_PR02/alarms",
        "Line 01","PLC","Alarm Manager","",60,"Cell 02","press_PR02","press",
        lambda sh: _alarm("press_PR02",sh)))

    # ── CONVEYORS ────────────────────────────────────────────────────────────
    for cid,nom,line,cell,label in [
        ("conveyor_CV01",2.0,"line_01_assembly","cell_01","CV01 Assembly L1C1"),
        ("conveyor_CV02",1.5,"line_01_assembly","cell_02","CV02 Assembly L1C2"),
        ("conveyor_CV03",0.8,"line_02_painting","cell_01","CV03 Paint Line"),
        ("conveyor_CV04",0.2,"line_03_curing","cell_01","CV04 Curing Line"),
    ]:
        sid = cid.replace("conveyor_","cv").lower()
        s.append(_s(f"{sid}_telem",f"{label} Telemetry",f"{_BASE}/{line}/{cell}/assets/{cid}/telemetry",
            line,"PLC","Belt Drive Controller","multi",5,cell,cid,"conveyor",
            lambda sh,c=cid,n=nom: _conveyor_telemetry(c,n,sh)))
        s.append(_s(f"{sid}_power",f"{label} 3-Phase Power",f"{_BASE}/{line}/{cell}/assets/{cid}/power",
            line,"PLC","Power Meter","kW",5,cell,cid,"conveyor",
            lambda sh,c=cid: _3phase(_ASSET_NOM_KW[c], _fault_factor(c,sh), sh)))
        s.append(_s(f"{sid}_energy",f"{label} Energy",f"{_BASE}/{line}/{cell}/assets/{cid}/energy",
            line,"MES","Energy Manager","kWh",30,cell,cid,"conveyor",
            lambda sh,c=cid: _energy_rollup(c,_ASSET_NOM_KW[c],30,_fault_factor(c,sh))))
        s.append(_s(f"{sid}_health",f"{label} Health",f"{_BASE}/{line}/{cell}/assets/{cid}/health",
            line,"SCADA","Condition Monitor","score",60,cell,cid,"conveyor",
            lambda sh,c=cid: _health(c,sh)))
        s.append(_s(f"{sid}_alarms",f"{label} Alarms",f"{_BASE}/{line}/{cell}/assets/{cid}/alarms",
            line,"PLC","Alarm Manager","",60,cell,cid,"conveyor",
            lambda sh,c=cid: _alarm(c,sh)))

    # ── ROBOTS ───────────────────────────────────────────────────────────────
    for rid,task,line,cell,nom_kw in [
        ("robot_R1","Welding","line_01_assembly","cell_01",5.5),
        ("robot_R2","MaterialHandling","line_01_assembly","cell_02",5.5),
        ("robot_R3","SprayPositioning","line_02_painting","cell_01",4.2),
    ]:
        sid = rid.lower().replace("_","")
        s.append(_s(f"{sid}_telem",f"{rid} Telemetry",f"{_BASE}/{line}/{cell}/assets/{rid}/telemetry",
            line,"PLC","Robot Controller","multi",5,cell,rid,"robot",
            lambda sh,r=rid,t=task: _robot_telemetry(r,t,sh)))
        s.append(_s(f"{sid}_power",f"{rid} 3-Phase Power",f"{_BASE}/{line}/{cell}/assets/{rid}/power",
            line,"PLC","Power Meter","kW",5,cell,rid,"robot",
            lambda sh,r=rid,k=nom_kw: _3phase(k,_fault_factor(r,sh),sh)))
        s.append(_s(f"{sid}_health",f"{rid} Health",f"{_BASE}/{line}/{cell}/assets/{rid}/health",
            line,"SCADA","Condition Monitor","score",60,cell,rid,"robot",
            lambda sh,r=rid: _health(r,sh)))
        s.append(_s(f"{sid}_alarms",f"{rid} Alarms",f"{_BASE}/{line}/{cell}/assets/{rid}/alarms",
            line,"PLC","Alarm Manager","",60,cell,rid,"robot",
            lambda sh,r=rid: _alarm(r,sh)))

    # ── SPRAYERS ─────────────────────────────────────────────────────────────
    for spid,nom_kw in [("sprayer_SP01",2.8),("sprayer_SP02",2.8)]:
        sid = spid.lower().replace("_","")
        s.append(_s(f"{sid}_telem",f"{spid} Telemetry",f"{_BASE}/line_02_painting/cell_01/assets/{spid}/telemetry",
            "line_02_painting","PLC","Sprayer Controller","multi",5,"cell_01",spid,"sprayer",
            lambda sh,sp=spid: _sprayer_telemetry(sp,sh)))
        s.append(_s(f"{sid}_power",f"{spid} 3-Phase Power",f"{_BASE}/line_02_painting/cell_01/assets/{spid}/power",
            "line_02_painting","PLC","Power Meter","kW",5,"cell_01",spid,"sprayer",
            lambda sh,sp=spid,k=nom_kw: _3phase(k,_fault_factor(sp,sh),sh)))
        s.append(_s(f"{sid}_health",f"{spid} Health",f"{_BASE}/line_02_painting/cell_01/assets/{spid}/health",
            "line_02_painting","SCADA","Condition Monitor","score",60,"cell_01",spid,"sprayer",
            lambda sh,sp=spid: _health(sp,sh)))
        s.append(_s(f"{sid}_alarms",f"{spid} Alarms",f"{_BASE}/line_02_painting/cell_01/assets/{spid}/alarms",
            "line_02_painting","PLC","Alarm Manager","",60,"cell_01",spid,"sprayer",
            lambda sh,sp=spid: _alarm(sp,sh)))

    # ── OVEN OV01 ────────────────────────────────────────────────────────────
    s.append(_s("ov01_telem","OV01 Oven Telemetry",f"{_BASE}/line_03_curing/cell_01/assets/oven_OV01/telemetry",
        "line_03_curing","PLC","Oven Controller","multi",5,"cell_01","oven_OV01","oven",
        lambda sh: _oven_telemetry(sh)))
    s.append(_s("ov01_power","OV01 3-Phase Power",f"{_BASE}/line_03_curing/cell_01/assets/oven_OV01/power",
        "line_03_curing","PLC","Power Meter PM-OV01","kW",5,"cell_01","oven_OV01","oven",
        lambda sh: _3phase(45.0,_fault_factor("oven_OV01",sh),sh)))
    s.append(_s("ov01_energy","OV01 Energy Rollup",f"{_BASE}/line_03_curing/cell_01/assets/oven_OV01/energy",
        "line_03_curing","MES","Energy Manager","kWh",30,"cell_01","oven_OV01","oven",
        lambda sh: _energy_rollup("oven_OV01",45.0,30,_fault_factor("oven_OV01",sh))))
    s.append(_s("ov01_health","OV01 Health Monitoring",f"{_BASE}/line_03_curing/cell_01/assets/oven_OV01/health",
        "line_03_curing","SCADA","Condition Monitor","score",30,"cell_01","oven_OV01","oven",
        lambda sh: _health("oven_OV01",sh)))
    s.append(_s("ov01_perf","OV01 Performance KPIs",f"{_BASE}/line_03_curing/cell_01/assets/oven_OV01/performance",
        "line_03_curing","MES","OEE Module","multi",30,"cell_01","oven_OV01","oven",
        lambda sh: {"timestamp":_now(),"asset_id":"oven_OV01","oee":round(jitter(82,0.03),1),"zone_temps":[_oven_telemetry(sh)[f"zone{i+1}_temp_c"] for i in range(4)],"status":"fault" if sh.get("fault") and "oven" in (sh.get("fault") or "") else "normal"}))
    s.append(_s("ov01_alarms","OV01 Alarms",f"{_BASE}/line_03_curing/cell_01/assets/oven_OV01/alarms",
        "line_03_curing","PLC","Alarm Manager","",60,"cell_01","oven_OV01","oven",
        lambda sh: _alarm("oven_OV01",sh)))
    s.append(_s("ov01_anomaly","OV01 Anomaly Score",f"{_BASE}/line_03_curing/analytics/anomaly/oven_OV01",
        "line_03_curing","AI","Aurora-AI Anomaly Engine","score",30,"cell_01","oven_OV01","oven",
        lambda sh: _analytics_anomaly("oven_OV01",sh)))

    # ── COMPRESSOR ───────────────────────────────────────────────────────────
    s.append(_s("cp01_telem","CP01 Compressor Telemetry",f"{_BASE}/utilities/assets/compressor_CP01/telemetry",
        "utilities","PLC","Compressor Controller","multi",10,"Utilities","compressor_CP01","compressor",
        lambda sh: _compressor_telemetry(sh)))
    s.append(_s("cp01_power","CP01 3-Phase Power",f"{_BASE}/utilities/assets/compressor_CP01/power",
        "utilities","PLC","Power Meter PM-CP01","kW",5,"Utilities","compressor_CP01","compressor",
        lambda sh: _3phase(22.0,_fault_factor("compressor_CP01",sh),sh)))
    s.append(_s("cp01_energy","CP01 Energy Rollup",f"{_BASE}/utilities/assets/compressor_CP01/energy",
        "utilities","MES","Energy Manager","kWh",30,"Utilities","compressor_CP01","compressor",
        lambda sh: _energy_rollup("compressor_CP01",22.0,30,_fault_factor("compressor_CP01",sh))))
    s.append(_s("cp01_health","CP01 Health",f"{_BASE}/utilities/assets/compressor_CP01/health",
        "utilities","SCADA","Condition Monitor","score",60,"Utilities","compressor_CP01","compressor",
        lambda sh: _health("compressor_CP01",sh)))
    s.append(_s("cp01_alarms","CP01 Alarms",f"{_BASE}/utilities/assets/compressor_CP01/alarms",
        "utilities","PLC","Alarm Manager","",60,"Utilities","compressor_CP01","compressor",
        lambda sh: _alarm("compressor_CP01",sh)))
    s.append(_s("cp01_anomaly","CP01 Energy Anomaly",f"{_BASE}/utilities/analytics/anomaly/compressor_CP01",
        "utilities","AI","Aurora-AI Energy Anomaly","score",30,"Utilities","compressor_CP01","compressor",
        lambda sh: _analytics_anomaly("compressor_CP01",sh)))

    # ── INSPECTION ───────────────────────────────────────────────────────────
    s.append(_s("cmm01_result","CMM01 Inspection Result",f"{_BASE}/line_04_inspection/cell_01/assets/vision_CMM01/result",
        "line_04_inspection","PLC","Vision CMM Controller","",15,"cell_01","vision_CMM01","inspection",
        lambda sh: _inspection_result("vision_CMM01","dimensional_vision",0.97,sh)))
    s.append(_s("cmm01_power","CMM01 Power",f"{_BASE}/line_04_inspection/cell_01/assets/vision_CMM01/power",
        "line_04_inspection","PLC","Power Meter","kW",30,"cell_01","vision_CMM01","inspection",
        lambda sh: _3phase(1.2,1.0,sh)))
    s.append(_s("lt01_result","LT01 Leak Test Result",f"{_BASE}/line_04_inspection/cell_02/assets/leak_test_LT01/result",
        "line_04_inspection","PLC","Leak Test Controller","",20,"cell_02","leak_test_LT01","inspection",
        lambda sh: _inspection_result("leak_test_LT01","pressure_leak_test",0.99,sh)))
    s.append(_s("lt01_power","LT01 Power",f"{_BASE}/line_04_inspection/cell_02/assets/leak_test_LT01/power",
        "line_04_inspection","PLC","Power Meter","kW",30,"cell_02","leak_test_LT01","inspection",
        lambda sh: _3phase(0.8,1.0,sh)))

    # ── PLANT-LEVEL ROLLUPS ───────────────────────────────────────────────────
    s.append(_s("plant_energy","Plant Total Energy",f"{_BASE}/plant/energy/total",
        "plant","SCADA","Plant Energy Manager","kWh",30,"Plant","plant","plant",
        lambda sh: {"timestamp":_now(),"total_kwh":round(sum(SIM.kwh_total.values()),1),
                    "current_kw":round(sum(_ASSET_NOM_KW.values())*random.uniform(0.7,0.95),1),
                    "energy_intensity_kwh_per_unit":round(jitter(0.185,0.04),3),
                    "co2_kg_today":round(sum(SIM.kwh_total.values())*0.233,1)}))
    s.append(_s("plant_oee","Plant OEE",f"{_BASE}/plant/kpi/oee",
        "plant","MES","OEE Dashboard","pct",30,"Plant","plant","plant",
        lambda sh: {"timestamp":_now(),"oee_pct":round(jitter(79 if not sh.get("fault") else 65,0.03),1),
                    "availability_pct":round(jitter(88,0.02),1),"performance_pct":round(jitter(92,0.02),1),
                    "quality_pct":round(jitter(98,0.01),1),"units_produced_shift":SIM.unit_seq,
                    "shift":sh.get("shift","A")}))
    s.append(_s("plant_process","Plant Process Status",f"{_BASE}/process/unit_id",
        "plant","MES","MES Production","",10,"Plant","plant","plant",
        lambda sh: {"timestamp":_now(),"current_unit":f"UNIT-{SIM.unit_seq:06d}",
                    "batch_id":SIM.current_batch,"product":SIM.current_product,
                    "line_01_status":"Running","line_02_status":"Running",
                    "line_03_status":"Running","line_04_status":"Running"}))

    # ── LINE-LEVEL ENERGY ROLLUPS ─────────────────────────────────────────────
    for line_id, asset_ids in [
        ("line_01_assembly",["press_PR01","press_PR02","conveyor_CV01","conveyor_CV02","robot_R1","robot_R2"]),
        ("line_02_painting", ["sprayer_SP01","sprayer_SP02","conveyor_CV03","robot_R3"]),
        ("line_03_curing",   ["oven_OV01","conveyor_CV04"]),
        ("line_04_inspection",["vision_CMM01","leak_test_LT01"]),
    ]:
        nom_kw = sum(_ASSET_NOM_KW.get(a,0) for a in asset_ids)
        s.append(_s(f"{line_id}_energy",f"{line_id} Line Energy Rollup",f"{_BASE}/{line_id}/energy/total",
            line_id,"SCADA","Line Energy Rollup","kWh",30,line_id,line_id,"line",
            lambda sh,k=nom_kw: {"timestamp":_now(),"total_kw":round(jitter(k,0.04),1),"period_kwh":round(jitter(k*30/3600,0.04),3)}))

    return s

STREAMS     = _make_streams()
STREAM_BY_ID = {s["id"]: s for s in STREAMS}

