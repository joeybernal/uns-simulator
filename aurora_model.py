"""
Aurora Industries — UNS Stream Model  v2.0
==========================================
Battery Case Plant — Leipzig, Germany
Products: BAT-CASE-AL-001 (aluminium EV battery case shells)

Line topology:
  line_01_assembly  → press_PR01, press_PR02, conveyor_CV01/CV02, robot_R1/R2
  line_02_painting  → sprayer_SP01/SP02, conveyor_CV03, robot_R3
  line_03_curing    → oven_OV01, conveyor_CV04
  line_04_inspection→ vision_CMM01, leak_test_LT01

v2 additions:
  - ERP streams: production orders, material consumption, finished goods, quality holds
  - MES streams: batch tracking, work orders, process parameters, step tracking
  - Extra PLC telemetry: die temp, lube system, tooling wear, part presence / RFID
  - Environmental: floor temp/humidity, compressed air pressure network
  - Quality streams: SPC control charts, first-pass yield, scrap/rework
  - ~150 total streams (doubled from v1 78)
  - 15 AI-demo scenarios (up from 9)
"""
from __future__ import annotations
import math, random, time
from typing import Any, Callable

# ─────────────────────────────────────────────────────────────────────────────
# Shared simulation state
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
        self.order_seq    = random.randint(10000, 19999)
        self.wo_seq       = random.randint(50000, 59999)
        self.mat_consumed = {"ALU_SHEET_2MM": round(random.uniform(500,2000),1),
                              "PRIMER_COAT":   round(random.uniform(50,300),1),
                              "TOPCOAT_GREY":  round(random.uniform(50,300),1),
                              "SEALANT_A":     round(random.uniform(20,100),1)}
        self.spc          = {a: {"mean": round(random.uniform(49.8,50.2),3), "stddev": round(random.uniform(0.01,0.04),4)}
                             for a in ["pr01_force","pr02_force","wall_thickness","coat_thickness"]}
        self.tool_cycles  = {"PR01_die": random.randint(15000,45000), "PR02_die": random.randint(15000,45000)}
        self.air_pressure = 7.5
        self.quality_holds = []
        self.scrap_count  = random.randint(0,5)
        self.rework_count = random.randint(0,12)

_ASSET_IDS = [
    "press_PR01","press_PR02",
    "conveyor_CV01","conveyor_CV02","conveyor_CV03","conveyor_CV04",
    "robot_R1","robot_R2","robot_R3",
    "sprayer_SP01","sprayer_SP02",
    "oven_OV01",
    "vision_CMM01","leak_test_LT01",
    "compressor_CP01",
    "rfid_reader_01","rfid_reader_02",
]

def _default_health(asset_id: str) -> dict:
    profiles = {
        "press":      [("HydraulicPump",random.uniform(45,92)),("MainSeal",random.uniform(60,98)),
                       ("Accumulator",random.uniform(80,99)),("PressGuide",random.uniform(85,99)),
                       ("Die",random.uniform(55,95))],
        "conveyor":   [("DriveMotor",random.uniform(70,99)),("BeltTension",random.uniform(65,99)),
                       ("Bearing",random.uniform(55,95)),("Encoder",random.uniform(80,99))],
        "robot":      [("JointA1",random.uniform(75,99)),("JointA2",random.uniform(75,99)),
                       ("WristUnit",random.uniform(70,98)),("TCP_Calibration",random.uniform(80,99))],
        "oven":       [("Zone1Heater",random.uniform(75,99)),("Zone2Heater",random.uniform(75,99)),
                       ("Zone3Heater",random.uniform(75,99)),("Zone4Heater",random.uniform(75,99)),
                       ("FanAssembly",random.uniform(60,95)),("ExhaustSystem",random.uniform(80,99))],
        "sprayer":    [("Nozzle",random.uniform(60,95)),("FluidPump",random.uniform(70,99)),
                       ("FilterUnit",random.uniform(55,90)),("GunElectrode",random.uniform(70,98))],
        "compressor": [("Piston",random.uniform(75,99)),("Valve",random.uniform(70,99)),
                       ("Intercooler",random.uniform(80,99)),("AirFilter",random.uniform(65,99))],
        "vision":     [("CameraA",random.uniform(80,99)),("CameraB",random.uniform(80,99)),
                       ("Lighting",random.uniform(75,99)),("CalibTarget",random.uniform(85,99))],
        "leak_test":  [("PressureSensor",random.uniform(80,99)),("FixtureSeal",random.uniform(60,95)),
                       ("FillValve",random.uniform(75,99))],
    }
    for prefix, comps in profiles.items():
        if prefix in asset_id:
            return {n: {"score": round(s,1), "rul_days": round(s*7.5),
                        "deg": round(random.uniform(0.02,0.8),3)} for n,s in comps}
    return {"Overall": {"score": round(random.uniform(70,99),1), "rul_days": 365, "deg": 0.05}}

def _new_batch(seq: int) -> str:
    from datetime import date
    return f"BATCH-{date.today().strftime('%Y%m%d')}-{seq:03d}"

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
    kw_total = clamp(jitter(nom_kw * fault_factor, 0.03), nom_kw*0.3, nom_kw*1.4)
    v = 400.0
    pf = clamp(jitter(0.91, 0.02), 0.75, 1.0)
    i_per_phase = kw_total * 1000 / (3 * v * pf)
    ia = jitter(i_per_phase, 0.015)
    ib = jitter(i_per_phase, 0.015)
    ic = jitter(i_per_phase * (1.0 if fault_factor >= 0.8 else 1.25), 0.015)
    kw_a = round(v * ia * pf / 1000, 2)
    kw_b = round(v * ib * pf / 1000, 2)
    kw_c = round(v * ic * pf / 1000, 2)
    return {
        "timestamp": _now(), "total_kw": round(kw_a+kw_b+kw_c, 2),
        "total_kva": round((kw_a+kw_b+kw_c)/pf, 2), "power_factor": round(pf,3),
        "phases": {
            "A": {"voltage_v": round(v,1), "current_a": round(ia,2), "kw": kw_a, "pf": round(pf,3)},
            "B": {"voltage_v": round(v,1), "current_a": round(ib,2), "kw": kw_b, "pf": round(pf,3)},
            "C": {"voltage_v": round(v,1), "current_a": round(ic,2), "kw": kw_c, "pf": round(pf,3)},
        },
        "thd_pct": round(jitter(2.5 if fault_factor >= 0.8 else 8.5, 0.1), 1),
        "frequency_hz": round(jitter(50.0, 0.002), 3),
    }

def _energy_rollup(asset_id: str, nom_kw: float, interval_s: float, fault_factor: float = 1.0) -> dict:
    kw = clamp(jitter(nom_kw * fault_factor, 0.03), nom_kw*0.2, nom_kw*1.5)
    SIM.kwh_total[asset_id] = round(SIM.kwh_total.get(asset_id,0) + kw*(interval_s/3600), 2)
    return {
        "timestamp": _now(), "asset_id": asset_id, "current_kw": round(kw,2),
        "total_kwh": SIM.kwh_total[asset_id],
        "energy_per_cycle_wh": round(kw*3600/max(1,_cycle_rate(asset_id)),1),
        "co2_kg_per_kwh": 0.233,
        "co2_total_kg": round(SIM.kwh_total[asset_id]*0.233,1),
        "peak_demand_kw": round(nom_kw*1.15,1),
        "demand_charge_eur": round(SIM.kwh_total[asset_id]*0.233*0.085,2),
    }

def _cycle_rate(asset_id: str) -> float:
    d = {"press_PR01":450,"press_PR02":450,"oven_OV01":3,"vision_CMM01":80,"leak_test_LT01":60}
    for k,v in d.items():
        if k in asset_id: return v
    return 100

def _health(asset_id: str, shared: dict) -> dict:
    h = SIM.health.get(asset_id, {})
    sd = shared.get("health_degrade",{}).get(asset_id,{})
    components = {}
    for name, c in h.items():
        extra = sd.get(name,0)
        c["score"] = round(clamp(c["score"]-(c["deg"]+extra)/288, 0, 100),1)
        c["rul_days"] = round(max(0, c["score"]*7.5))
        components[name] = {"score": c["score"], "rul_days": c["rul_days"],
                            "degradation_rate_pct_per_day": round(c["deg"]+extra,3)}
    overall = round(sum(c["score"] for c in components.values())/max(1,len(components)),1)
    return {"timestamp":_now(),"asset_id":asset_id,"overall_score":overall,
            "components":components,"maintenance_urgency": "OK" if overall>70 else ("SOON" if overall>50 else "IMMEDIATE")}

def _fault_factor(asset_id: str, shared: dict) -> float:
    fault = shared.get("fault") or ""
    if fault and (asset_id in fault or asset_id.split("_")[0] in fault):
        return random.uniform(0.4, 0.75)
    return 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Asset-specific generators
# ─────────────────────────────────────────────────────────────────────────────

def _press_telemetry(asset_id: str, nom_pressure: float, nom_force: float, nom_temp: float, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    is_tooling_wear = fault == f"{asset_id}_die_wear"
    pressure_offset = -30 if f"{asset_id}_pressure_low" in fault else (-15 if f"{asset_id}_seal_leak" in fault else 0)
    temp_offset     = +30 if f"{asset_id}_overtemp" in fault else 0
    force_offset    = +80 if f"{asset_id}_force_dev" in fault or is_tooling_wear else 0
    die_key         = "PR01_die" if "PR01" in asset_id else "PR02_die"
    SIM.tool_cycles[die_key] = SIM.tool_cycles.get(die_key, 0) + 1
    die_pct = min(100.0, SIM.tool_cycles[die_key] / 600)
    return {
        "timestamp":               _now(),
        "asset_id":                asset_id,
        "hydraulic_pressure_bar":  clamp(jitter(nom_pressure + pressure_offset, 0.02), 140, 230),
        "oil_temperature_c":       clamp(jitter(nom_temp + temp_offset, 0.025), 35, 90),
        "press_force_kn":          clamp(jitter(nom_force + force_offset, 0.035), 550, 950),
        "stroke_position_mm":      round(random.uniform(50, 480)),
        "stroke_count":            SIM.cycle_count.get(asset_id, 0),
        "lube_pressure_bar":       clamp(jitter(4.2, 0.03), 2.5, 6.0),
        "lube_flow_lpm":           clamp(jitter(1.8, 0.04), 0.5, 4.0),
        "die_temp_c":              clamp(jitter(38 + (25 if is_tooling_wear else 0), 0.04), 20, 120),
        "die_wear_pct":            round(die_pct, 1),
        "die_cycle_count":         SIM.tool_cycles[die_key],
        "die_life_remaining_pct":  round(100 - die_pct, 1),
        "cushion_pressure_bar":    clamp(jitter(12.0, 0.03), 8, 18),
        "vibration_mm_s":          clamp(jitter(1.8 if not fault else 5.2, 0.15), 0.1, 20),
        "part_present":            True,
        "status":                  "fault" if fault and asset_id in fault else "normal",
    }

def _press_performance(asset_id: str, nom_ct: float, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    mat_shortage = shared.get("fault") == "erp_material_shortage"
    ct = nom_ct * (1.25 if fault and asset_id in fault else (1.8 if mat_shortage else random.uniform(0.95,1.12)))
    SIM.cycle_count[asset_id] = SIM.cycle_count.get(asset_id,0) + 1
    oee = clamp(jitter(62 if mat_shortage else (72 if fault and asset_id in fault else 79), 0.04), 40, 95)
    scrap = random.randint(0, 2 if fault and asset_id in fault else 0)
    SIM.scrap_count += scrap
    return {
        "timestamp":           _now(),
        "asset_id":            asset_id,
        "operational_status":  "Faulted" if fault and asset_id in fault else ("Starved" if mat_shortage else "Running"),
        "oee":                 round(oee,1),
        "availability":        round(oee/random.uniform(0.93,0.98),1),
        "performance_kpi":     round(random.uniform(88,98),1),
        "quality_kpi":         round(random.uniform(95,99.5),1),
        "cycle_time_s":        round(ct,2),
        "cycle_time_target_s": nom_ct,
        "cycle_count":         SIM.cycle_count[asset_id],
        "production_rate_hr":  round(3600/ct),
        "scrap_count_shift":   SIM.scrap_count,
        "rework_count_shift":  SIM.rework_count,
        "current_product":     SIM.current_product,
        "current_batch":       SIM.current_batch,
        "shift":               shared.get("shift","A"),
        "work_order_id":       f"WO-{SIM.wo_seq:06d}",
    }

def _press_spc(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    tooling = fault == f"{asset_id}_die_wear"
    key = "pr01_force" if "PR01" in asset_id else "pr02_force"
    mean_shift = 2.5 if tooling else 0.0
    val = round(jitter(SIM.spc[key]["mean"] + mean_shift, 0.008), 4)
    ucl = round(SIM.spc[key]["mean"] + 3*SIM.spc[key]["stddev"], 4)
    lcl = round(SIM.spc[key]["mean"] - 3*SIM.spc[key]["stddev"], 4)
    return {
        "timestamp":   _now(), "asset_id": asset_id, "parameter": "press_force_deviation",
        "value":       val, "mean":val, "ucl":ucl, "lcl":lcl,
        "in_control":  lcl <= val <= ucl,
        "sigma_level": round(abs(val - SIM.spc[key]["mean"]) / max(SIM.spc[key]["stddev"],0.0001),2),
        "trend":       "UPWARD" if tooling else "STABLE",
        "rule_violations": ["Rule 1: Beyond 3σ"] if not (lcl<=val<=ucl) else [],
    }

def _lube_system(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    low_lube = fault == f"{asset_id}_lube_low"
    return {
        "timestamp":        _now(), "asset_id": asset_id,
        "reservoir_level_pct": clamp(jitter(65 if not low_lube else 18, 0.02), 5, 100),
        "supply_pressure_bar": clamp(jitter(4.2 if not low_lube else 1.8, 0.03), 0.5, 6.0),
        "flow_rate_ml_min":    clamp(jitter(120 if not low_lube else 35, 0.04), 10, 250),
        "oil_temp_c":          clamp(jitter(38, 0.03), 25, 70),
        "filter_dp_bar":       clamp(jitter(0.15, 0.05), 0.01, 0.8),
        "status":              "LOW_LEVEL" if low_lube else "OK",
        "last_refill_hours_ago": round(random.uniform(2, 48)),
    }

def _oven_telemetry(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    zone_offsets = [0,0,0,0]
    if fault == "oven_OV01_zone2_fail":   zone_offsets[1] = -110
    if fault == "oven_OV01_overshoot":    zone_offsets = [+22,+25,+24,+18]
    if fault == "oven_cv04_sync_loss":    zone_offsets = [+8,+10,+8,+5]
    nom = [180,200,200,170]
    temps = [round(clamp(jitter(nom[i]+zone_offsets[i],0.008), 50, 270),1) for i in range(4)]
    fan_fault = fault == "oven_OV01_fan_fail"
    fan_rpm   = clamp(jitter(1450 if not fan_fault else 380, 0.03), 200, 1600)
    exhaust   = clamp(jitter(88+(10 if "overshoot" in fault else 0), 0.03), 40, 160)
    cv04_fault = fault == "oven_cv04_sync_loss"
    conv_speed = clamp(jitter(0.5*(0.7 if cv04_fault else 1.0), 0.04), 0.05, 0.8)
    actual_dwell = round(3.2 / max(conv_speed, 0.05), 1)
    return {
        "timestamp":         _now(), "asset_id": "oven_OV01",
        "zone1_temp_c":      temps[0], "zone2_temp_c": temps[1],
        "zone3_temp_c":      temps[2], "zone4_temp_c": temps[3],
        "zone_setpoints_c":  [180,200,200,170],
        "zone_deviations_c": [round(temps[i]-nom[i],1) for i in range(4)],
        "fan_speed_rpm":     round(fan_rpm),
        "exhaust_temp_c":    round(exhaust,1),
        "chamber_pressure_pa": round(jitter(-5.0, 0.05), 2),
        "conveyor_speed_mpm":  round(conv_speed, 3),
        "dwell_time_min":      actual_dwell,
        "dwell_setpoint_min":  6.4,
        "humidity_pct":        round(clamp(jitter(12.0, 0.04), 5, 40),1),
        "gas_flow_m3h":        round(clamp(jitter(42.0, 0.03), 20, 65),1),
        "status":              "fault" if fault and "oven" in fault else "normal",
    }

def _conveyor_telemetry(asset_id: str, nom_speed: float, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    speed_factor = 0.0 if fault == f"{asset_id}_jam" else (0.55 if fault == f"{asset_id}_slip" else 1.0)
    if fault == "oven_cv04_sync_loss" and asset_id == "conveyor_CV04":
        speed_factor = random.uniform(0.6, 0.9)
    speed = clamp(jitter(nom_speed * speed_factor, 0.025), 0, nom_speed*1.1)
    return {
        "timestamp":          _now(), "asset_id": asset_id,
        "speed_ms":           round(speed, 3), "speed_setpoint_ms": nom_speed,
        "belt_tension_n":     round(clamp(jitter(850 if speed_factor>0 else 200, 0.04), 100, 1500)),
        "bearing_temp_c":     round(clamp(jitter(38 if speed_factor>0 else 72, 0.05), 20, 95),1),
        "motor_current_a":    round(clamp(jitter(8.5*speed_factor, 0.05), 0.1, 20),2),
        "encoder_ppr":        round(speed*4000/max(nom_speed,0.01)),
        "jam_detected":       speed_factor == 0.0,
        "units_on_belt":      random.randint(3, 12),
        "part_id_last":       f"UNIT-{SIM.unit_seq:06d}",
    }

def _robot_telemetry(asset_id: str, task: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    faulted = asset_id in fault and ("position_error" in fault or "collision" in fault)
    drift = fault == "robot_R3_spray_drift" and asset_id == "robot_R3"
    pos_err = round(jitter(0.05 if not faulted else 12.5, 0.2), 3)
    if drift: pos_err = round(jitter(0.72, 0.1), 3)
    return {
        "timestamp":           _now(), "asset_id": asset_id, "state": "Faulted" if faulted else "Running",
        "task":                task,
        "position_error_mm":   pos_err,
        "joint_temps_c":       [round(clamp(jitter(42,0.03),25,85),1) for _ in range(6)],
        "joint_torques_nm":    [round(clamp(jitter(45,0.05),10,120),1) for _ in range(6)],
        "cycle_time_s":        round(jitter(4.2 if not faulted else 0, 0.05),2),
        "parts_per_hour":      round(3600/4.2) if not faulted else 0,
        "teach_point_offset_mm": round(jitter(0.02 if not faulted else 0.85, 0.3),3),
        "path_accuracy_mm":    round(jitter(0.08 if not drift else 0.65, 0.1),3),
        "payload_kg":          round(jitter(12.5, 0.01),2),
        "reach_mm":            round(jitter(1850, 0.001),0),
        "program_id":          f"PROG-{task[:3].upper()}-001",
    }

def _sprayer_telemetry(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    blocked  = fault == f"{asset_id}_filter_blocked"
    nozzle   = fault == f"{asset_id}_nozzle_clog"
    drift    = fault == "robot_R3_spray_drift"
    pressure = clamp(jitter(3.5*(0.55 if blocked else (0.75 if nozzle else 1.0)), 0.03), 0.5, 6.0)
    coat_th  = clamp(jitter(80 if not nozzle else 45, 0.05), 20, 140)
    if drift: coat_th = clamp(jitter(52, 0.08), 20, 100)
    return {
        "timestamp":              _now(), "asset_id": asset_id,
        "supply_pressure_bar":    round(pressure,2),
        "atomisation_pressure_bar": round(pressure*0.85,2),
        "fluid_flow_lpm":         round(clamp(jitter(1.8*(0.6 if nozzle else 1.0),0.03),0.1,4.0),3),
        "paint_temp_c":           round(clamp(jitter(22.5,0.02),18,32),1),
        "filter_dp_bar":          round(clamp(jitter(0.12 if not blocked else 0.68,0.05),0.02,1.0),3),
        "filter_status":          "BLOCKED" if blocked else "OK",
        "coat_thickness_um":      round(coat_th,1),
        "coat_uniformity_pct":    round(clamp(jitter(95 if not drift else 72, 0.03),50,100),1),
        "gun_voltage_kv":         round(clamp(jitter(70,0.02),50,90),1),
        "paint_consumed_ml":      round(jitter(45.2,0.03),1),
        "solvent_ratio_pct":      round(clamp(jitter(15.0,0.02),8,25),1),
        "viscosity_mpa_s":        round(clamp(jitter(85,0.03),50,150),1),
    }

def _compressor_telemetry(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    overload = fault == "compressor_CP01_overload"
    air_leak  = fault == "compressed_air_leak"
    SIM.air_pressure = clamp(jitter(6.5 if air_leak else (5.8 if overload else 7.5), 0.015), 3.0, 10.0)
    return {
        "timestamp":            _now(), "asset_id": "compressor_CP01",
        "outlet_pressure_bar":  round(SIM.air_pressure,2),
        "inlet_temp_c":         round(clamp(jitter(22,0.02),10,40),1),
        "outlet_temp_c":        round(clamp(jitter(78 if not overload else 105,0.03),50,130),1),
        "flow_rate_m3h":        round(clamp(jitter(15.5*(1.35 if air_leak else 1.0),0.03),5,30),2),
        "vibration_mm_s":       round(clamp(jitter(2.1 if not overload else 9.8,0.1),0.1,20),2),
        "oil_level_pct":        round(clamp(jitter(78,0.01),10,100),1),
        "run_hours":            round(random.uniform(4500,25000)),
        "loaded_pct":           round(clamp(jitter(72 if not air_leak else 95,0.03),40,100),1),
        "dew_point_c":          round(clamp(jitter(-20,0.05),-40,10),1),
        "air_quality_iso":      "ISO8573-1:2010 Class 1" if not air_leak else "Class 2",
        "unload_cycles_8h":     random.randint(120,280),
        "status":               "Overload" if overload else ("LeakSuspected" if air_leak else "Running"),
    }

def _air_network(shared: dict) -> dict:
    """Compressed air distribution monitoring at 3 zones."""
    fault = shared.get("fault") or ""
    air_leak = fault == "compressed_air_leak"
    cp_pres  = SIM.air_pressure
    return {
        "timestamp":        _now(), "asset_id": "air_network",
        "header_pressure_bar": round(clamp(jitter(cp_pres*0.95, 0.01), 3, 10),2),
        "zone_a_press_bar": round(clamp(jitter(cp_pres*0.93*(0.85 if air_leak else 1.0), 0.015), 3, 10),2),
        "zone_b_press_bar": round(clamp(jitter(cp_pres*0.91, 0.015), 3, 10),2),
        "zone_c_press_bar": round(clamp(jitter(cp_pres*0.90, 0.015), 3, 10),2),
        "total_flow_m3h":   round(clamp(jitter(28.5*(1.3 if air_leak else 1.0), 0.03), 10, 55),1),
        "leak_detected":    air_leak,
        "estimated_leak_m3h": round(jitter(4.2 if air_leak else 0.0, 0.1),2) if air_leak else 0.0,
        "pressure_drop_bar": round(abs(cp_pres - SIM.air_pressure*0.90),2),
    }

def _inspection_result(asset_id: str, method: str, pass_rate: float, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    degraded = f"{asset_id}_sensor_fault" in fault
    cascade  = fault == "multi_asset_cascade"
    quality_escape = fault == "quality_escape"
    actual_pr = pass_rate*(0.82 if quality_escape else (0.85 if degraded else (0.82 if cascade else 1.0)))
    passed = random.random() < actual_pr
    SIM.unit_seq += 1
    if not passed: SIM.scrap_count += 1
    return {
        "timestamp":     _now(), "asset_id": asset_id, "method": method,
        "unit_id":       f"UNIT-{SIM.unit_seq:06d}", "batch_id": SIM.current_batch,
        "result":        "PASS" if passed else "FAIL",
        "confidence":    round(random.uniform(0.92,0.999),3),
        "cycle_time_s":  round(jitter(45 if "vision" in asset_id else 60, 0.04),1),
        "sensor_status": "degraded" if degraded else "ok",
        "fail_codes":    [] if passed else (["DIM-001"] if "vision" in asset_id else ["LEAK-001"]),
        "operator_id":   f"OP-{random.randint(100,120):03d}",
        "disposition":   "PASS" if passed else ("REWORK" if random.random()<0.4 else "SCRAP"),
    }

def _cmm_measurement(shared: dict) -> dict:
    """Full dimensional report from vision CMM."""
    fault = shared.get("fault") or ""
    cascade = fault == "multi_asset_cascade"
    quality_escape = fault == "quality_escape"
    offset = 0.3 if cascade else (0.2 if quality_escape else 0.0)
    dim = {
        "length_mm":      round(jitter(300.0+offset, 0.0005),4),
        "width_mm":       round(jitter(150.0+offset*0.8, 0.0005),4),
        "wall_th_mm":     round(jitter(2.0+offset*0.5, 0.001),4),
        "flatness_mm":    round(jitter(0.05+offset*0.3, 0.02),4),
        "parallelism_mm": round(jitter(0.03+offset*0.2, 0.02),4),
        "roundness_mm":   round(jitter(0.02, 0.03),4),
    }
    tolerances = {"length_mm":(299.9,300.1),"width_mm":(149.9,150.1),
                  "wall_th_mm":(1.85,2.15),"flatness_mm":(0,0.12),"parallelism_mm":(0,0.08),"roundness_mm":(0,0.05)}
    oos = [k for k,v in dim.items() if not (tolerances[k][0]<=v<=tolerances[k][1])]
    return {
        "timestamp": _now(), "asset_id": "vision_CMM01", "unit_id": f"UNIT-{SIM.unit_seq:06d}",
        "measurements": dim, "out_of_spec": oos, "pass": len(oos)==0,
        "gage_r_r_pct": round(jitter(8.2 if not (fault and "sensor" in fault) else 22.5, 0.03),1),
    }

def _alarm(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    alarms = []
    if fault and (asset_id.split("_")[0] in fault or asset_id in fault):
        meta = _FAULT_META.get(fault, {"code":"E-GENERIC","name":fault,"severity":"warning",
                                       "description":f"Active fault: {fault}"})
        alarms.append({
            "alarm_id":    f"ALM-{asset_id.upper()[:8]}-001",
            "alarm_code":  meta["code"], "alarm_name": meta["name"],
            "severity":    meta["severity"], "raised_at": _now(),
            "acknowledged":False, "description": meta["description"],
            "escalation_required": meta["severity"] == "critical",
        })
    return {"timestamp":_now(),"asset_id":asset_id,"active_alarms":alarms,"alarm_count":len(alarms)}

def _analytics_anomaly(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    faulted = bool(fault and (asset_id.split("_")[0] in fault or asset_id in fault))
    score = clamp(jitter(0.72 if faulted else 0.08, 0.3), 0, 1.0)
    return {
        "timestamp":   _now(), "asset_id": asset_id,
        "anomaly_score": round(score,3),
        "anomaly_level": "HIGH" if score>0.6 else ("MEDIUM" if score>0.3 else "LOW"),
        "contributing_signals": ["hydraulic_pressure","oil_temperature","vibration"] if faulted else [],
        "recommended_action": "Inspect immediately" if score>0.6 else ("Monitor closely" if score>0.3 else "No action required"),
        "model_version": "aurora-anomaly-v2.1",
        "training_dataset_size": 847293,
        "last_retrained": "2026-04-01T00:00:00Z",
    }

def _predictive_maintenance(asset_id: str, shared: dict) -> dict:
    h = SIM.health.get(asset_id, {})
    min_score = min((c["score"] for c in h.values()), default=80)
    min_rul   = min((c["rul_days"] for c in h.values()), default=365)
    fault = shared.get("fault") or ""
    if fault and (asset_id.split("_")[0] in fault or asset_id in fault):
        min_rul = max(1, min_rul//3)
    urgency = "IMMEDIATE" if min_rul<7 else ("SOON" if min_rul<30 else ("PLANNED" if min_rul<90 else "OK"))
    return {
        "timestamp":            _now(), "asset_id": asset_id,
        "min_health_score":     round(min_score,1), "min_rul_days": min_rul,
        "maintenance_urgency":  urgency,
        "next_recommended_date":_rul_date(min_rul),
        "estimated_downtime_h": round(random.uniform(2,12),1) if urgency!="OK" else 0,
        "cost_if_ignored_eur":  round(min_rul*random.uniform(100,500)) if urgency!="OK" else 0,
        "spare_parts_needed":   ["Hydraulic seal kit","O-ring set"] if urgency!="OK" else [],
        "work_order_suggested": urgency!="OK",
    }

def _rul_date(days: int) -> str:
    from datetime import date, timedelta
    return (date.today()+timedelta(days=days)).isoformat()

def _environmental(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    return {
        "timestamp":          _now(), "location": "factory_floor_main",
        "temperature_c":      round(clamp(jitter(21.5,0.005),16,35),1),
        "humidity_rh_pct":    round(clamp(jitter(48.0,0.01),20,80),1),
        "ambient_pressure_hpa":round(clamp(jitter(1013.0,0.001),950,1050),1),
        "co2_ppm":            round(clamp(jitter(620,0.03),400,2000)),
        "noise_db":           round(clamp(jitter(74,0.02),55,100),1),
        "lighting_lux":       round(clamp(jitter(480,0.03),200,800)),
        "particulate_um3":    round(clamp(jitter(35,0.05),5,200)),
        "zone":               "Line01-Line04",
    }

def _rfid_scan(reader_id: str, area: str, shared: dict) -> dict:
    SIM.unit_seq += 0  # don't increment here — inspection does
    return {
        "timestamp":    _now(), "reader_id": reader_id,
        "area":         area,
        "tag_id":       f"TAG-{random.randint(100000,999999):06d}",
        "unit_id":      f"UNIT-{SIM.unit_seq:06d}",
        "batch_id":     SIM.current_batch,
        "product":      SIM.current_product,
        "read_success": random.random() > 0.01,
        "rssi_dbm":     round(random.uniform(-55,-30),1),
        "antenna_port": random.randint(1,4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ERP / MES stream generators
# ─────────────────────────────────────────────────────────────────────────────

def _erp_production_order(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    mat_shortage = fault == "erp_material_shortage"
    status = "BLOCKED" if mat_shortage else random.choice(["IN_PROGRESS","IN_PROGRESS","IN_PROGRESS","COMPLETED"])
    return {
        "timestamp":          _now(), "source": "SAP_ERP",
        "order_id":           f"PO-{SIM.order_seq:06d}",
        "material":           SIM.current_product,
        "quantity_ordered":   1000,
        "quantity_produced":  SIM.unit_seq,
        "quantity_scrap":     SIM.scrap_count,
        "status":             status,
        "priority":           "HIGH",
        "scheduled_start":    "2026-04-17T06:00:00Z",
        "scheduled_end":      "2026-04-17T22:00:00Z",
        "customer_id":        "BMW-GROUP-DE",
        "delivery_date":      "2026-04-19",
        "alert":              "Material shortage — ALU_SHEET_2MM below safety stock" if mat_shortage else None,
    }

def _erp_material_consumption(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    mat_shortage = fault == "erp_material_shortage"
    consumed = SIM.mat_consumed
    consumed["ALU_SHEET_2MM"] = round(consumed["ALU_SHEET_2MM"] + random.uniform(0.8,1.2), 1)
    consumed["PRIMER_COAT"]   = round(consumed["PRIMER_COAT"]   + random.uniform(0.1,0.2), 2)
    consumed["TOPCOAT_GREY"]  = round(consumed["TOPCOAT_GREY"]  + random.uniform(0.1,0.2), 2)
    consumed["SEALANT_A"]     = round(consumed["SEALANT_A"]     + random.uniform(0.05,0.1), 3)
    safety_stock = {"ALU_SHEET_2MM":500,"PRIMER_COAT":50,"TOPCOAT_GREY":50,"SEALANT_A":20}
    return {
        "timestamp":     _now(), "source": "SAP_ERP",
        "order_id":      f"PO-{SIM.order_seq:06d}",
        "plant":         "DE-LEIPZIG-01",
        "materials":     [{"material_id":k,"consumed_kg":round(v,2),
                           "uom":"KG","stock_warning": mat_shortage and k=="ALU_SHEET_2MM"}
                          for k,v in consumed.items()],
        "total_material_cost_eur": round(sum(consumed.values())*2.85, 2),
        "waste_pct":     round(jitter(3.2,0.05),1),
    }

def _erp_quality_hold(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    active_holds = []
    if fault in ("oven_OV01_zone2_fail","oven_thermal_runaway","batch_quality_hold"):
        active_holds.append({
            "hold_id":      f"QH-{SIM.current_batch}-001",
            "batch_id":     SIM.current_batch,
            "reason":       "Oven temperature deviation — cure quality at risk",
            "initiated_by": "MES_AUTO",
            "units_affected": SIM.unit_seq,
            "severity":     "CRITICAL",
        })
    if fault in ("multi_asset_cascade","quality_escape"):
        active_holds.append({
            "hold_id":      f"QH-{SIM.current_batch}-002",
            "batch_id":     SIM.current_batch,
            "reason":       "Dimensional failure rate above 5% threshold",
            "initiated_by": "QUALITY_MODULE",
            "units_affected": max(0, SIM.unit_seq - 45),
            "severity":     "HIGH",
        })
    return {
        "timestamp":     _now(), "source": "SAP_ERP",
        "active_holds":  active_holds, "hold_count": len(active_holds),
        "total_holds_today": len(SIM.quality_holds) + len(active_holds),
        "holds_cleared_today": random.randint(0,3),
    }

def _mes_batch_tracking(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    return {
        "timestamp":     _now(), "source": "MES",
        "batch_id":      SIM.current_batch,
        "product":       SIM.current_product,
        "order_id":      f"PO-{SIM.order_seq:06d}",
        "work_order_id": f"WO-{SIM.wo_seq:06d}",
        "shift":         shared.get("shift","A"),
        "units_started": SIM.unit_seq,
        "units_passed":  max(0, SIM.unit_seq - SIM.scrap_count - SIM.rework_count),
        "units_rework":  SIM.rework_count,
        "units_scrap":   SIM.scrap_count,
        "first_pass_yield_pct": round(max(0, SIM.unit_seq-SIM.scrap_count-SIM.rework_count) / max(1,SIM.unit_seq) * 100, 1),
        "current_step":  "PRESSING" if not fault else ("CURING" if "oven" in fault else "PAINTING"),
        "batch_status":  "ON_HOLD" if fault in ("oven_OV01_zone2_fail","batch_quality_hold") else "IN_PROGRESS",
        "target_qty":    1000,
        "completion_pct":round(SIM.unit_seq/10.0,1),
        "estimated_completion": "2026-04-17T22:00:00Z",
        "oee_batch":     round(jitter(79 if not fault else 65, 0.03),1),
    }

def _mes_work_order(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    mat_shortage = fault == "erp_material_shortage"
    return {
        "timestamp":       _now(), "source": "MES",
        "work_order_id":   f"WO-{SIM.wo_seq:06d}",
        "operation":       "PRESS_STAMP",
        "machine_id":      "press_PR01",
        "operator_id":     f"OP-{random.randint(100,120):03d}",
        "status":          "WAITING_MATERIAL" if mat_shortage else "IN_PROGRESS",
        "start_time":      "2026-04-17T06:00:00Z",
        "setup_time_min":  round(jitter(12.0,0.05),1),
        "run_time_min":    round(jitter(480.0,0.01),1),
        "downtime_min":    round(jitter(0 if not fault else 22.5, 0.2),1),
        "downtime_reason": None if not fault else "Equipment fault",
        "tooling_id":      "DIE-PR01-ALU-V3",
        "program_id":      "PROG-PR01-BAT-CASE-v7",
        "revision":        "R07",
    }

def _mes_process_params(asset_id: str, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    return {
        "timestamp":     _now(), "source": "MES", "asset_id": asset_id,
        "process_step":  "PRESS_FORM",
        "recipe_id":     "BAT-CASE-AL-001-R07",
        "parameters": {
            "hydraulic_pressure_sp": 210,
            "stroke_speed_sp_mm_s": round(jitter(45.0,0.02),1),
            "hold_time_sp_ms":      round(jitter(800,0.01)),
            "blank_holder_force_kn":round(jitter(120,0.02),1),
            "draw_depth_sp_mm":     round(jitter(85.0,0.001),2),
            "lube_volume_ml":       round(jitter(12.5,0.03),2),
        },
        "actual_vs_setpoint_ok": not bool(fault and asset_id in fault),
        "deviation_pct": round(jitter(0.5 if not fault else 6.5, 0.1),2),
    }

def _mes_shift_summary(shared: dict) -> dict:
    return {
        "timestamp":        _now(), "source": "MES",
        "shift":            shared.get("shift","A"),
        "date":             "2026-04-17",
        "planned_units":    500,
        "actual_units":     SIM.unit_seq,
        "oee_pct":          round(jitter(79,0.03),1),
        "availability_pct": round(jitter(88,0.02),1),
        "performance_pct":  round(jitter(92,0.02),1),
        "quality_pct":      round(jitter(98,0.01),1),
        "scrap_count":      SIM.scrap_count,
        "rework_count":     SIM.rework_count,
        "downtime_min":     round(jitter(22,0.1),1),
        "top_downtime_reasons": [
            {"reason":"Equipment changeover","minutes":round(jitter(12,0.1),1)},
            {"reason":"Material replenishment","minutes":round(jitter(6,0.2),1)},
        ],
        "energy_kwh_shift":  round(sum(SIM.kwh_total.values())/8,1),
        "energy_per_unit_kwh": round(sum(SIM.kwh_total.values())/max(1,SIM.unit_seq)/8,3),
    }

def _quality_spc_chart(parameter: str, nom: float, ucl_offset: float, lcl_offset: float, shared: dict) -> dict:
    fault = shared.get("fault") or ""
    drift_active = "cascade" in fault or "quality_escape" in fault or "die_wear" in fault
    val = round(jitter(nom + (0.15 if drift_active else 0.0), 0.003), 4)
    ucl = round(nom + ucl_offset, 4)
    lcl = round(nom + lcl_offset, 4)
    return {
        "timestamp":     _now(), "source": "QMS",
        "parameter":     parameter, "value": val,
        "ucl":           ucl, "lcl": lcl, "mean": nom,
        "in_control":    lcl <= val <= ucl,
        "sigma_level":   round(abs(val-nom)/max(ucl_offset/3,0.0001),2),
        "sample_size":   5,
        "cpk":           round(min(ucl-val,val-lcl)/(3*max(ucl_offset/3,0.0001)),3),
        "trend":         "UPWARD_DRIFT" if drift_active else "STABLE",
        "nelson_rules_violated": ["Rule 1"] if not (lcl<=val<=ucl) else [],
    }

def _dpp_event(shared: dict) -> dict:
    """Digital Product Passport — triggered on each completed unit."""
    return {
        "timestamp":     _now(), "source": "MES",
        "event":         "unit_completed",
        "unit_id":       f"UNIT-{SIM.unit_seq:06d}",
        "batch_id":      SIM.current_batch,
        "product":       SIM.current_product,
        "order_id":      f"PO-{SIM.order_seq:06d}",
        "supplier_id":   "AURORA-INDUSTRIES-DE",
        "material_cert": f"CERT-ALU-{random.randint(1000,9999)}",
        "process_params_hash": f"sha256:{random.randint(0,2**31):08x}",
        "energy_kwh_this_unit": round(jitter(0.185,0.05),3),
        "co2_kg_this_unit":     round(jitter(0.043,0.05),4),
        "quality_result":       "PASS",
        "traceability_url":     f"https://dpp.aurora-industries.de/unit/{SIM.unit_seq:06d}",
        "standard":             "ISO 27553 / EU Battery Regulation 2023/1542",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Asset NOM kW and mappings
# ─────────────────────────────────────────────────────────────────────────────
_ASSET_NOM_KW = {
    "press_PR01":16.8,"press_PR02":16.8,
    "conveyor_CV01":3.5,"conveyor_CV02":3.5,"conveyor_CV03":2.2,"conveyor_CV04":1.8,
    "robot_R1":5.5,"robot_R2":5.5,"robot_R3":4.2,
    "sprayer_SP01":2.8,"sprayer_SP02":2.8,
    "oven_OV01":45.0,"vision_CMM01":1.2,"leak_test_LT01":0.8,"compressor_CP01":22.0,
}

def _fault_meta_entry(code,name,sev,desc):
    return {"code":code,"name":name,"severity":sev,"description":desc}

_FAULT_META = {
    "press_PR01_pressure_low":   _fault_meta_entry("E-PRESS-002","Hydraulic Pressure Low","critical","PR01 hydraulic pressure dropped below 192 bar — possible pump wear or seal failure"),
    "press_PR01_overtemp":       _fault_meta_entry("E-PRESS-003","Oil Overtemperature","critical","PR01 hydraulic oil temperature exceeded 75°C — check cooler and oil level"),
    "press_PR01_seal_leak":      _fault_meta_entry("E-PRESS-004","Hydraulic Seal Leak","warning","PR01 oil leak detected on main cylinder seal — early sign of failure"),
    "press_PR01_force_dev":      _fault_meta_entry("E-PRESS-005","Press Force Deviation","warning","PR01 press force deviates >5% from setpoint — check tool wear"),
    "press_PR01_die_wear":       _fault_meta_entry("E-PRESS-006","Die Wear Critical","warning","PR01 die wear >70% — dimensional drift increasing, schedule die change"),
    "press_PR02_pressure_low":   _fault_meta_entry("E-PRESS-012","Hydraulic Pressure Low","critical","PR02 hydraulic pressure dropped below 192 bar"),
    "press_PR02_seal_leak":      _fault_meta_entry("E-PRESS-014","Hydraulic Seal Leak","warning","PR02 oil leak on main cylinder seal"),
    "press_PR02_die_wear":       _fault_meta_entry("E-PRESS-016","Die Wear Critical","warning","PR02 die wear >70% — schedule die change"),
    "oven_OV01_zone2_fail":      _fault_meta_entry("E-OVEN-001","Zone 2 Heater Failure","critical","OV01 zone 2 heater element failure — cure quality at risk"),
    "oven_OV01_overshoot":       _fault_meta_entry("E-OVEN-002","Temperature Overshoot","critical","OV01 all zones above setpoint — thermal runaway risk"),
    "oven_OV01_fan_fail":        _fault_meta_entry("E-OVEN-003","Circulation Fan Failure","critical","OV01 air circulation fan stopped — thermal uniformity lost"),
    "oven_cv04_sync_loss":       _fault_meta_entry("E-OVEN-004","Conveyor Speed Fluctuation","warning","CV04 speed instability — variable dwell time, cure quality variation"),
    "conveyor_CV01_jam":         _fault_meta_entry("E-CV-001","Belt Jam","critical","CV01 belt stopped — obstruction detected"),
    "conveyor_CV01_slip":        _fault_meta_entry("E-CV-002","Belt Slip","warning","CV01 belt speed below setpoint — check tension"),
    "conveyor_CV03_jam":         _fault_meta_entry("E-CV-011","Belt Jam","critical","CV03 belt stopped — paint line blocked"),
    "robot_R1_position_error":   _fault_meta_entry("E-ROB-001","Position Error","critical","R1 end-effector position error > 0.5mm — weld quality at risk"),
    "robot_R1_collision":        _fault_meta_entry("E-ROB-002","Collision Detected","critical","R1 collision sensor triggered — emergency stop"),
    "robot_R3_position_error":   _fault_meta_entry("E-ROB-011","Spray Robot Position Error","critical","R3 spray head position error — coat uniformity at risk"),
    "robot_R3_spray_drift":      _fault_meta_entry("E-ROB-012","R3 TCP Drift","warning","R3 tool-centre-point drift 0.72mm — coat thickness falling below minimum"),
    "sprayer_SP02_filter_blocked":_fault_meta_entry("E-SP-001","Paint Filter Blocked","warning","SP02 filter differential pressure exceeded — replace filter"),
    "sprayer_SP02_nozzle_clog":  _fault_meta_entry("E-SP-002","Nozzle Clog","warning","SP02 nozzle partial blockage — flow rate reduced 40%"),
    "compressor_CP01_overload":  _fault_meta_entry("E-CP-001","Compressor Overload","critical","CP01 outlet pressure below 6 bar — check plant air demand"),
    "compressed_air_leak":       _fault_meta_entry("E-CP-002","Air Network Leak","warning","Compressed air header pressure drop 15% — leak estimated 4.2 m³/h"),
    "vision_CMM01_sensor_fault": _fault_meta_entry("E-INS-001","Vision Sensor Fault","warning","CMM01 calibration drift detected — dimensional accuracy reduced"),
    "erp_material_shortage":     _fault_meta_entry("E-ERP-001","Material Shortage","critical","ALU_SHEET_2MM stock below safety level — production at risk"),
    "multi_asset_cascade":       _fault_meta_entry("E-CAS-001","Cascade Failure","critical","PR01 seal leak causing downstream quality failures — trace root cause"),
    "quality_escape":            _fault_meta_entry("E-QMS-001","Quality Escape","critical","Defect rate 18% — batch quality hold triggered, root cause analysis required"),
    "batch_quality_hold":        _fault_meta_entry("E-QMS-002","Batch Quality Hold","critical","Batch placed on hold due to oven temperature deviation"),
}


# ─────────────────────────────────────────────────────────────────────────────
# FAULT SCENARIOS  — 15 rich AI-demo scenarios
# ─────────────────────────────────────────────────────────────────────────────
FAULT_SCENARIOS = {
    "normal": {
        "label": "Normal Operation",
        "description": "All assets operating within normal parameters. Baseline for comparison.",
        "fault_key": None, "affected": [],
        "health_degrade": {},
        "ai_hint": "No anomalies. Plant OEE ~79%. Energy consumption nominal.",
        "what_it_shows": "Healthy baseline: all 150 streams within expected ranges, OEE 79%, energy at nominal, 0 active alarms.",
        "how_to_demo": "Start here. Show the live stream table, energy dashboard, and health scores. Highlight the AI anomaly scores all reading LOW (<0.1).",
        "ai_opportunity": "Baseline comparison — AI can compute rolling baselines and immediately flag deviations. Ask the AI: 'What does normal operation look like for this plant?'",
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":79,"energy":"nominal","quality":98},
    },
    "press_PR01_hydraulic_degradation": {
        "label": "PR01 — Hydraulic Pump Wear (Early Stage)",
        "description": "PR01 hydraulic pressure slowly declining. Oil temp rising. Pump efficiency dropping. Classic early-stage hydraulic pump wear — catches before alarm threshold.",
        "fault_key": "press_PR01_pressure_low", "affected": ["press_PR01"],
        "health_degrade": {"press_PR01": {"HydraulicPump": 0.8}},
        "ai_hint": "Pressure trending down -0.8 bar/day over 3 days. Oil temp +3°C. Pump efficiency -12%. Recommend hydraulic pump inspection within 5 days.",
        "what_it_shows": "Sub-threshold degradation that rules-based alarms miss. PLC shows pressure 196 bar (limit 192) — no alarm fires. But AI detects trend.",
        "how_to_demo": "Show PR01 telemetry stream. Point out hydraulic_pressure_bar slowly declining and oil_temperature rising. Then switch to AI anomaly tab — score jumps to 0.65 (MEDIUM). Classic 'AI catches what SCADA misses' story.",
        "ai_opportunity": "Ask AI: 'PR01 hydraulic pressure is 196 bar vs 210 nominal. Oil temp is 53°C vs 50°C nominal. Vibration is 2.1 mm/s vs 1.8 baseline. What does this indicate?' — AI should diagnose early pump wear and recommend maintenance window.",
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":76,"energy":"nominal","quality":97},
    },
    "oven_zone2_heater_failure": {
        "label": "OV01 — Zone 2 Heater Element Failure",
        "description": "Zone 2 temperature dropped 110°C below setpoint. Parts curing in zone 2 will be undercured. Downstream quality risk. MES triggers batch hold.",
        "fault_key": "oven_OV01_zone2_fail", "affected": ["oven_OV01"],
        "health_degrade": {"oven_OV01": {"Zone2Heater": 2.5}},
        "ai_hint": "Zone 2 temp = 90°C vs 200°C setpoint. Zones 1/3/4 normal. Heater element failure. All parts in current batch should be placed on quality hold. Estimated cure deficiency: 55% of required dwell time at temperature.",
        "what_it_shows": "Multi-system correlation: OV01 telemetry (zone temps) + MES batch tracking (batch hold) + ERP quality hold + DPP (batch flagged). Shows how AI connects operational and business data.",
        "how_to_demo": "Switch to this scenario. Show oven zone tabs — zones 1/3/4 normal (180/200/170°C), zone 2 suddenly 90°C. Show MES batch stream showing ON_HOLD status. Show ERP quality hold stream. Show AI hint explaining cure deficiency.",
        "ai_opportunity": "Ask AI: 'Zone 2 in OV01 is reading 90°C vs 200°C setpoint. Current batch is BATCH-20260417-001 with 234 units produced. What is the quality impact and what should I do?' — AI should calculate % undercured, recommend hold, suggest heater inspection checklist.",
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":71,"energy":"reduced_zone2","quality":72},
    },
    "paint_filter_blockage": {
        "label": "SP02 — Paint Filter Progressive Blockage",
        "description": "SP02 paint filter differential pressure rising over 2 hours. Atomisation pressure dropping. Coat thickness falling below 60µm minimum. AI correlates filter DP → coat thickness.",
        "fault_key": "sprayer_SP02_filter_blocked", "affected": ["sprayer_SP02"],
        "health_degrade": {"sprayer_SP02": {"FilterUnit": 1.2}},
        "ai_hint": "Filter DP: 0.68 bar (limit 0.5 bar). Coat thickness: 45µm (min 60µm). Atomisation pressure: 1.9 bar (setpoint 3.0 bar). Replace filter immediately, quality hold on last 45 min of production.",
        "what_it_shows": "Gradual drift that correlates two streams (filter_dp and coat_thickness). Neither alone would trigger an alarm, but the correlation is diagnostic. Shows AI multi-stream reasoning.",
        "how_to_demo": "Show SP02 telemetry — filter_dp_bar trending up (0.12 → 0.68), coat_thickness_um trending down (80 → 45µm). Switch to Health tab — FilterUnit at 32%. Then show AI anomaly score for SP02: HIGH.",
        "ai_opportunity": "Ask AI: 'SP02 filter DP is 0.68 bar and rising. Coat thickness is 45µm — minimum is 60µm. What is the impact and what parts are affected?' — AI should identify affected time window, calculate rework costs, give filter replacement procedure.",
        "data_sources": ["PLC","QMS","MES","AI"],
        "kpi_impact": {"oee":77,"energy":"nominal","quality":81},
    },
    "conveyor_cv01_jam": {
        "label": "CV01 — Belt Jam (Line 1 Cell 1 Blocked)",
        "description": "CV01 belt stopped. Press PR01 starved of parts. Line 1 Cell 1 production halted. Shows cascading throughput impact and AI recovery sequencing.",
        "fault_key": "conveyor_CV01_jam", "affected": ["conveyor_CV01","press_PR01"],
        "health_degrade": {},
        "ai_hint": "CV01 speed = 0 m/s. Press PR01 cycle count frozen. Estimated production loss: 7.5 units/min. Recovery: check belt tension, clear jam, restart in sequence CV01 → PR01. ETA to recovery: 15-20 min.",
        "what_it_shows": "Hard fault with immediate upstream/downstream impact. CV01 stops → PR01 shows 'Starved' status → MES WO shows downtime accruing. ERP production order completion % frozen. Shows AI-driven recovery planning.",
        "how_to_demo": "Switch scenario. Show CV01 telemetry — speed = 0, jam_detected = true, belt_tension = 200N. Show PR01 performance — operational_status = 'Starved'. Show MES WO downtime_min increasing. Ask AI for recovery sequence.",
        "ai_opportunity": "Ask AI: 'CV01 has stopped with jam detected. PR01 is starved. Current batch has 156 units remaining to produce. What is the recovery sequence and estimated throughput impact?' — AI should give LOTO procedure, restart sequence, calculate catch-up rate.",
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":58,"energy":"reduced_line1","quality":99},
    },
    "energy_anomaly_night_shift": {
        "label": "Energy Anomaly — Compressor Off-Hours Overconsumption",
        "description": "Compressor CP01 drawing 35% more power than baseline during night shift. Phase C current imbalance. THD elevated. Annual cost impact quantified.",
        "fault_key": "compressor_CP01_overload", "affected": ["compressor_CP01"],
        "health_degrade": {"compressor_CP01": {"Valve": 0.5, "Intercooler": 0.3}},
        "ai_hint": "CP01 consuming 29.7 kW vs 22 kW baseline (+35%). Phase C current 18A vs 12A nominal (50% imbalance). THD: 8.5% (limit 5%). Power factor: 0.73 (expected 0.91). Likely: valve wear or intercooler fouling. Annual excess cost: ~€8,400.",
        "what_it_shows": "Energy intelligence beyond basic monitoring. 3-phase analysis reveals phase imbalance + THD simultaneously. AI correlates with health data (valve/intercooler) to find root cause, then calculates financial impact.",
        "how_to_demo": "Go to Energy tab. Show CP01 power stream — total_kw elevated, Phase C current higher than A/B, THD 8.5%. Show energy rollup cost trending up. Switch to Health — Valve at 68%, Intercooler at 72%. Ask AI to quantify the annual cost.",
        "ai_opportunity": "Ask AI: 'CP01 is consuming 29.7 kW vs 22 kW baseline, with Phase C at 18A vs 12A for A and B. THD is 8.5%. This is during night shift with low production. What is causing this and what is the annual financial impact?' — AI should diagnose valve/intercooler and calculate € impact.",
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":79,"energy":"+35%_compressor","quality":99},
    },
    "multi_asset_cascade": {
        "label": "Cascade Failure — Hydraulic Leak → Quality Escape",
        "description": "PR01 hydraulic seal leak → reduced press force → underdimensioned casings → CMM vision catching 18% failure rate. AI traces the full causal chain.",
        "fault_key": "press_PR01_seal_leak", "affected": ["press_PR01","vision_CMM01"],
        "health_degrade": {"press_PR01": {"MainSeal": 1.5, "HydraulicPump": 0.4}},
        "ai_hint": "Causal chain: PR01 seal leak (-15 bar) → press force deviation (+80 kN) → case wall thickness out of tolerance (+0.3mm) → CMM fail rate 18% (vs 3% baseline). Root cause: PR01 MainSeal (health: 42). Fix seal → quality returns to baseline.",
        "what_it_shows": "Root cause analysis across asset boundaries. Mechanical fault causing quality escape. Shows AI reasoning across PLC (press), QMS (CMM), ERP (quality hold) and MES (batch tracking) simultaneously.",
        "how_to_demo": "Show PR01 telemetry — hydraulic_pressure low, oil_leak indicator. Show CMM results — FAIL rate jumping. Show ERP quality hold stream. Switch to Health — MainSeal degrading. Ask AI to trace root cause. This is the most powerful AI demo scenario.",
        "ai_opportunity": "Ask AI: 'CMM inspection failure rate has jumped from 3% to 18% in the last 2 hours. PR01 hydraulic pressure is 195 bar and press force deviation is +6.5%. What is the root cause and which batches are affected?' — Full causal chain reasoning across systems.",
        "data_sources": ["PLC","QMS","MES","ERP","AI"],
        "kpi_impact": {"oee":72,"energy":"nominal","quality":82},
    },
    "oven_thermal_runaway": {
        "label": "OV01 — Thermal Runaway (All Zones Overshoot)",
        "description": "OV01 temperature controller fault — all zones overshooting by 20-25°C. Paint on casings may be scorched. AI recommends immediate stop and quality assessment.",
        "fault_key": "oven_OV01_overshoot", "affected": ["oven_OV01"],
        "health_degrade": {"oven_OV01": {"Zone1Heater": 0.3, "Zone2Heater": 0.3, "Zone3Heater": 0.3}},
        "ai_hint": "All zones 20-25°C above setpoint. Exhaust temp: 98°C (normal: 85°C). Recommended: STOP line immediately, hold all parts from last 20 min, inspect controller PID tuning.",
        "what_it_shows": "Safety-critical scenario. Shows AI decision support for STOP vs CONTINUE. MES automatically triggers batch hold. ERP quality hold fires. DPP flags affected units.",
        "how_to_demo": "Switch scenario. All 4 zone temps show overshoot (e.g. Zone 1: 202°C vs 180 setpoint). Show MES batch status = ON_HOLD. Show ERP quality hold. Show AI urgency — STOP recommendation. Good for showing AI as safety net.",
        "ai_opportunity": "Ask AI: 'OV01 all zones are 20-25°C above setpoint. Dwell time is 6.4 min at elevated temp. Parts in oven are BAT-CASE-AL-001 with primer coat. What is the material impact and what is the recovery procedure?' — AI should advise on paint scorch, temperature cycling, PID retuning.",
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":68,"energy":"+18%_oven","quality":71},
    },
    "robot_R1_weld_drift": {
        "label": "R1 — Weld Robot Teach-Point Drift",
        "description": "Robot R1 weld positions drifting 0.8mm from teach points. JointA1 and WristUnit degrading. AI detects pattern before weld failures cause scrap.",
        "fault_key": "robot_R1_position_error", "affected": ["robot_R1"],
        "health_degrade": {"robot_R1": {"JointA1": 0.6, "WristUnit": 0.9}},
        "ai_hint": "R1 position error: 0.85mm (limit 0.5mm). JointA1 health: 71% (degrading 0.6%/day). WristUnit health: 68%. Teach-point drift increasing over 72h. Recommend: recalibrate, check joint backlash, schedule bearing inspection.",
        "what_it_shows": "Slow geometric drift from mechanical wear. Shows AI tracking multi-day trends that humans miss. Health stream showing JointA1 and WristUnit declining. PdM recommending maintenance before failure.",
        "how_to_demo": "Show R1 telemetry — position_error_mm at 0.85 (limit 0.5). Show Health tab — JointA1 and WristUnit bars declining. Show PdM stream — RUL 35 days, urgency SOON. Ask AI to predict failure date and impact on weld quality.",
        "ai_opportunity": "Ask AI: 'Robot R1 teach point offset is 0.85mm and increasing. JointA1 health is 71% with degradation rate 0.6%/day. What is the projected failure date and what quality impact should I expect before then?' — Predictive maintenance reasoning + quality impact.",
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":78,"energy":"nominal","quality":94},
    },
    "compressed_air_leak": {
        "label": "Compressed Air Leak — Network Pressure Drop",
        "description": "Air network pressure drop 15% detected. Compressor running at 95% load continuously to compensate. Estimated leak 4.2 m³/h. Energy waste and quality risk to pneumatic tools.",
        "fault_key": "compressed_air_leak", "affected": ["compressor_CP01"],
        "health_degrade": {"compressor_CP01": {"AirFilter": 0.4}},
        "ai_hint": "Header pressure: 6.38 bar vs 7.5 nominal (-15%). Compressor loaded 95% (normal 72%). Leak estimated 4.2 m³/h. Annual energy cost: ~€3,200. Compressor RUL reduced 40% from continuous operation. Locate with ultrasonic leak detector in Zone A.",
        "what_it_shows": "Invisible utility waste that's rarely monitored. Compressor 3-phase power, air network zone pressures, and AirFilter health combine to pinpoint the issue. AI quantifies financial and equipment impact.",
        "how_to_demo": "Show CP01 power stream — loaded_pct 95 vs 72 normal. Show air_network stream — zone_a_press lower than B and C, leak_detected = true. Show energy rollup — excess kW. Ask AI to calculate annual cost and recommend detection approach.",
        "ai_opportunity": "Ask AI: 'Air network Zone A pressure is 6.1 bar vs 7.1 bar for Zone B. Compressor is running at 95% load vs 72% baseline. Total flow is 37 m³/h vs 28.5 nominal. Where is the leak and what does it cost per year?' — AI should pinpoint Zone A, estimate leak size, calculate €/year.",
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":79,"energy":"+22%_compressor","quality":99},
    },
    "tooling_die_wear": {
        "label": "PR01 Die Wear — Dimensional Drift from Tooling",
        "description": "PR01 die has accumulated 420,000 cycles (70% of 600,000 limit). Die temp rising, press force deviation increasing. Dimensional measurements drifting. SPC charts showing upward trend.",
        "fault_key": "press_PR01_die_wear", "affected": ["press_PR01","vision_CMM01"],
        "health_degrade": {"press_PR01": {"Die": 1.8}},
        "ai_hint": "PR01 die at 70% life (420K/600K cycles). Die temp: 63°C vs 38°C nominal (+66%). Press force deviation: +3.2%. Wall thickness SPC trending upward, Cpk 0.82 (limit 1.33). Schedule die change within 24h to prevent quality escape.",
        "what_it_shows": "Planned maintenance vs reactive repair. Tooling lifecycle management tied to quality SPC. Shows AI using cycle count, health score, SPC Cpk, and dimensional measurements together to predict remaining useful life before quality goes out of spec.",
        "how_to_demo": "Show PR01 telemetry — die_wear_pct 70%, die_temp 63°C. Show SPC chart stream — wall_thickness trending up, Cpk 0.82. Show Health — Die component declining. Ask AI when to schedule die change to prevent quality escape.",
        "ai_opportunity": "Ask AI: 'PR01 die is at 70% wear (420K cycles). Die temperature is 63°C and rising. SPC Cpk for wall thickness is 0.82. At what cycle count will we expect the first quality escape, and when should I schedule the die change?' — AI should calculate intersection of wear curve with quality limit.",
        "data_sources": ["PLC","QMS","MES","AI"],
        "kpi_impact": {"oee":77,"energy":"nominal","quality":95},
    },
    "robot_R3_spray_drift": {
        "label": "R3 — Spray Robot TCP Drift (Paint Quality Impact)",
        "description": "Paint robot R3 tool-centre-point drifting 0.72mm. Coat thickness falling from 80µm to 52µm average. Coat uniformity 72% (min 90%). MES catching yield drop.",
        "fault_key": "robot_R3_spray_drift", "affected": ["robot_R3","sprayer_SP01","sprayer_SP02"],
        "health_degrade": {"robot_R3": {"TCP_Calibration": 2.0, "JointA2": 0.5}},
        "ai_hint": "R3 TCP offset: 0.72mm (limit 0.3mm). Coat thickness: 52µm (min 60µm). Uniformity: 72% (min 90%). Spray overlap pattern incorrect. Recalibrate R3 TCP, verify gun-to-part distance. Quality hold on last 35 min of paint output.",
        "what_it_shows": "Process quality correlation between robotics and coating quality. Shows AI correlating robot kinematics with quality outcomes. Good for demonstrating process monitoring beyond simple threshold alarms.",
        "how_to_demo": "Show R3 telemetry — position_error_mm 0.72, path_accuracy 0.65. Show sprayer streams — coat_thickness_um ~52, coat_uniformity_pct 72. Show Health — TCP_Calibration at 45%. Ask AI to identify root cause and affected parts window.",
        "ai_opportunity": "Ask AI: 'R3 path accuracy is 0.65mm (limit 0.3mm) and coat thickness has dropped from 80µm to 52µm over the last hour. How many parts are affected and what is the recalibration procedure?' — AI should calculate time window, estimate rework count, give TCP recal steps.",
        "data_sources": ["PLC","QMS","MES","AI"],
        "kpi_impact": {"oee":76,"energy":"nominal","quality":83},
    },
    "erp_material_shortage": {
        "label": "ERP Alert — ALU Sheet Material Shortage",
        "description": "SAP ERP signals ALU_SHEET_2MM below safety stock (500 kg). MES halts new work orders. Press lines will be starved in ~45 min. Shows ERP-to-MES-to-OT integration.",
        "fault_key": "erp_material_shortage", "affected": ["press_PR01","press_PR02"],
        "health_degrade": {},
        "ai_hint": "ALU_SHEET_2MM: 387 kg remaining (safety stock 500 kg). Current consumption: 1.1 kg/unit × 7.5 units/min = 8.25 kg/min. Estimated starvation in 47 min. Expedite PO from supplier or reduce line rate to extend window to 95 min.",
        "what_it_shows": "Top-down planning to shopfloor impact. ERP material data flowing into MES work orders → OT production rates. Shows the full ISA-95 hierarchy with AI doing cross-layer analysis to predict starvation and suggest mitigation.",
        "how_to_demo": "Show ERP production order stream — alert: 'Material shortage'. Show MES work order — status: WAITING_MATERIAL. Show PR01/PR02 performance — operational_status: Starved. Show ERP material consumption — ALU_SHEET declining. Ask AI for starvation time and options.",
        "ai_opportunity": "Ask AI: 'ERP shows ALU_SHEET_2MM at 387 kg with safety stock 500 kg. Current consumption is 1.1 kg/unit at 7.5 units/min. Supplier lead time is 4 hours. What are my options to prevent a line stop?' — AI should calculate time windows, suggest production re-sequencing.",
        "data_sources": ["ERP","MES","PLC","AI"],
        "kpi_impact": {"oee":62,"energy":"reduced_presses","quality":99},
    },
    "quality_escape": {
        "label": "Quality Escape — CMM Defect Rate 18% (Root Cause Unknown)",
        "description": "CMM inspection defect rate jumped from 3% to 18%. No single alarm fired. AI needs to correlate press force, die wear, and oven data to find root cause. MES triggers batch hold.",
        "fault_key": "quality_escape", "affected": ["press_PR01","vision_CMM01"],
        "health_degrade": {"press_PR01": {"Die": 1.2}, "vision_CMM01": {"CalibTarget": 0.8}},
        "ai_hint": "CMM fail rate: 18% (baseline 3%). PR01 press force deviation: +4.1%. SPC Cpk: 0.79. Oven zone 3 deviation: +8°C. Most likely root cause: combined PR01 die wear (72%) + minor oven overshoot contributing to dimensional instability. Hold current batch, adjust PR01 force and oven setpoint.",
        "what_it_shows": "AI as quality detective. No single sensor shows a clear fault — it's a combination. Shows AI's strength in multi-variate correlation vs human analysis of individual KPIs. ERP quality hold + MES batch hold both triggered.",
        "how_to_demo": "This is the most complex scenario. Show CMM results — FAIL rate 18%. PR01 force deviation +4.1%. Oven zone 3 slightly high. None individually alarming. Ask AI to diagnose. This scenario best demonstrates AI reasoning value vs SCADA rules.",
        "ai_opportunity": "Ask AI: 'CMM inspection failure rate is 18% vs 3% baseline. No individual alarms have fired on any asset. PR01 press force deviation is +4.1%, oven zone 3 is +8°C above setpoint, and PR01 die wear is 72%. What is the most likely root cause combination?' — Multi-variate root cause analysis.",
        "data_sources": ["PLC","QMS","MES","ERP","AI"],
        "kpi_impact": {"oee":71,"energy":"nominal","quality":82},
    },
    "batch_quality_hold": {
        "label": "Batch Quality Hold — MES + ERP Integration",
        "description": "MES automatically places current batch on hold due to oven temperature deviation. ERP updates the production order status. DPP flags all units in window. Shows system integration depth.",
        "fault_key": "batch_quality_hold", "affected": ["oven_OV01"],
        "health_degrade": {"oven_OV01": {"Zone2Heater": 1.0}},
        "ai_hint": "Batch BATCH-20260417-001 on hold. 156 units in affected window. Oven zone 2 deviated -45°C for estimated 22 min. Minimum cure temp 180°C — zone 2 was at ~155°C. Cure deficiency estimate: 23%. Recommend: destructive test of 3 units from batch, partial scrap/rework decision.",
        "what_it_shows": "System integration story: OT fault → MES batch hold → ERP production order update → DPP unit flagging — all automatic, all traceable. AI then helps decide what to do with the held batch.",
        "how_to_demo": "Show MES batch tracking — batch_status ON_HOLD. Show ERP quality hold — active holds with batch ID. Show DPP event stream — units flagged. Show oven telemetry — zone 2 deviation. Then ask AI for disposition recommendation.",
        "ai_opportunity": "Ask AI: 'Batch BATCH-20260417-001 is on hold with 156 units. Oven zone 2 was 45°C below setpoint for an estimated 22 minutes. The minimum cure requirement is 180°C for 6.4 minutes per zone. What is the risk and what is the recommended disposition?' — AI should give cure calculation and disposition logic.",
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":74,"energy":"nominal","quality":68},
    },
}

for _k,_v in FAULT_SCENARIOS.items():
    _v.setdefault("id",_k)
    _v.setdefault("health_degrade",{})
    _v.setdefault("data_sources",[])
    _v.setdefault("kpi_impact",{})
    _v.setdefault("what_it_shows","")
    _v.setdefault("how_to_demo","")
    _v.setdefault("ai_opportunity","")


# ─────────────────────────────────────────────────────────────────────────────
# STREAM DEFINITIONS  (~150 streams)
# ─────────────────────────────────────────────────────────────────────────────
def _s(sid,label,topic,area,source,unit,interval,asset_id,asset_type,gen_fn):
    return {"id":sid,"label":label,"topic":topic,"area":area,"source":source,"unit":unit,
            "interval":interval,"asset_id":asset_id,"asset_type":asset_type,"gen":gen_fn}

_B = "aurora"

def _make_streams():
    s = []

    # ── PRESS PR01 ─────────────────────────────────────────────────────────
    s += [
        _s("pr01_telem","PR01 Process Telemetry",f"{_B}/line_01_assembly/cell_01/press_PR01/telemetry","Line 01","PLC","multi",5,"press_PR01","press",lambda sh:_press_telemetry("press_PR01",210,750,50,sh)),
        _s("pr01_power","PR01 3-Phase Power",f"{_B}/line_01_assembly/cell_01/press_PR01/power","Line 01","PLC","kW",5,"press_PR01","press",lambda sh:_3phase(16.8,_fault_factor("press_PR01",sh),sh)),
        _s("pr01_energy","PR01 Energy Rollup",f"{_B}/line_01_assembly/cell_01/press_PR01/energy","Line 01","MES","kWh",30,"press_PR01","press",lambda sh:_energy_rollup("press_PR01",16.8,30,_fault_factor("press_PR01",sh))),
        _s("pr01_perf","PR01 Performance KPIs",f"{_B}/line_01_assembly/cell_01/press_PR01/performance","Line 01","MES","multi",30,"press_PR01","press",lambda sh:_press_performance("press_PR01",8.0,sh)),
        _s("pr01_spc","PR01 SPC Control Chart",f"{_B}/line_01_assembly/cell_01/press_PR01/spc","Line 01","QMS","sigma",15,"press_PR01","press",lambda sh:_press_spc("press_PR01",sh)),
        _s("pr01_lube","PR01 Lubrication System",f"{_B}/line_01_assembly/cell_01/press_PR01/lube","Line 01","PLC","multi",30,"press_PR01","press",lambda sh:_lube_system("press_PR01",sh)),
        _s("pr01_health","PR01 Health Monitoring",f"{_B}/line_01_assembly/cell_01/press_PR01/health","Line 01","SCADA","score",30,"press_PR01","press",lambda sh:_health("press_PR01",sh)),
        _s("pr01_alarms","PR01 Alarms",f"{_B}/line_01_assembly/cell_01/press_PR01/alarms","Line 01","PLC","",60,"press_PR01","press",lambda sh:_alarm("press_PR01",sh)),
        _s("pr01_anomaly","PR01 Anomaly Score",f"{_B}/line_01_assembly/analytics/anomaly/press_PR01","Line 01","AI","score",30,"press_PR01","press",lambda sh:_analytics_anomaly("press_PR01",sh)),
        _s("pr01_pdm","PR01 Predictive Maintenance",f"{_B}/line_01_assembly/analytics/pdm/press_PR01","Line 01","AI","days",60,"press_PR01","press",lambda sh:_predictive_maintenance("press_PR01",sh)),
        _s("pr01_process","PR01 MES Process Params",f"{_B}/line_01_assembly/cell_01/press_PR01/process_params","Line 01","MES","multi",30,"press_PR01","press",lambda sh:_mes_process_params("press_PR01",sh)),
    ]

    # ── PRESS PR02 ─────────────────────────────────────────────────────────
    s += [
        _s("pr02_telem","PR02 Process Telemetry",f"{_B}/line_01_assembly/cell_02/press_PR02/telemetry","Line 01","PLC","multi",5,"press_PR02","press",lambda sh:_press_telemetry("press_PR02",210,750,50,sh)),
        _s("pr02_power","PR02 3-Phase Power",f"{_B}/line_01_assembly/cell_02/press_PR02/power","Line 01","PLC","kW",5,"press_PR02","press",lambda sh:_3phase(16.8,_fault_factor("press_PR02",sh),sh)),
        _s("pr02_energy","PR02 Energy Rollup",f"{_B}/line_01_assembly/cell_02/press_PR02/energy","Line 01","MES","kWh",30,"press_PR02","press",lambda sh:_energy_rollup("press_PR02",16.8,30,_fault_factor("press_PR02",sh))),
        _s("pr02_perf","PR02 Performance KPIs",f"{_B}/line_01_assembly/cell_02/press_PR02/performance","Line 01","MES","multi",30,"press_PR02","press",lambda sh:_press_performance("press_PR02",8.0,sh)),
        _s("pr02_spc","PR02 SPC Control Chart",f"{_B}/line_01_assembly/cell_02/press_PR02/spc","Line 01","QMS","sigma",15,"press_PR02","press",lambda sh:_press_spc("press_PR02",sh)),
        _s("pr02_lube","PR02 Lubrication System",f"{_B}/line_01_assembly/cell_02/press_PR02/lube","Line 01","PLC","multi",30,"press_PR02","press",lambda sh:_lube_system("press_PR02",sh)),
        _s("pr02_health","PR02 Health Monitoring",f"{_B}/line_01_assembly/cell_02/press_PR02/health","Line 01","SCADA","score",30,"press_PR02","press",lambda sh:_health("press_PR02",sh)),
        _s("pr02_alarms","PR02 Alarms",f"{_B}/line_01_assembly/cell_02/press_PR02/alarms","Line 01","PLC","",60,"press_PR02","press",lambda sh:_alarm("press_PR02",sh)),
        _s("pr02_anomaly","PR02 Anomaly Score",f"{_B}/line_01_assembly/analytics/anomaly/press_PR02","Line 01","AI","score",30,"press_PR02","press",lambda sh:_analytics_anomaly("press_PR02",sh)),
        _s("pr02_process","PR02 MES Process Params",f"{_B}/line_01_assembly/cell_02/press_PR02/process_params","Line 01","MES","multi",30,"press_PR02","press",lambda sh:_mes_process_params("press_PR02",sh)),
    ]

    # ── CONVEYORS ──────────────────────────────────────────────────────────
    for cid,nom,line,cell in [
        ("conveyor_CV01",2.0,"line_01_assembly","cell_01"),
        ("conveyor_CV02",1.5,"line_01_assembly","cell_02"),
        ("conveyor_CV03",0.8,"line_02_painting","cell_01"),
        ("conveyor_CV04",0.2,"line_03_curing","cell_01"),
    ]:
        sid = cid.replace("conveyor_","cv").lower()
        label = cid.replace("_"," ").title()
        s += [
            _s(f"{sid}_telem",f"{label} Telemetry",f"{_B}/{line}/{cell}/{cid}/telemetry",line,"PLC","multi",5,cid,"conveyor",lambda sh,c=cid,n=nom:_conveyor_telemetry(c,n,sh)),
            _s(f"{sid}_power",f"{label} 3-Phase Power",f"{_B}/{line}/{cell}/{cid}/power",line,"PLC","kW",5,cid,"conveyor",lambda sh,c=cid:_3phase(_ASSET_NOM_KW[c],_fault_factor(c,sh),sh)),
            _s(f"{sid}_energy",f"{label} Energy",f"{_B}/{line}/{cell}/{cid}/energy",line,"MES","kWh",30,cid,"conveyor",lambda sh,c=cid:_energy_rollup(c,_ASSET_NOM_KW[c],30,_fault_factor(c,sh))),
            _s(f"{sid}_health",f"{label} Health",f"{_B}/{line}/{cell}/{cid}/health",line,"SCADA","score",60,cid,"conveyor",lambda sh,c=cid:_health(c,sh)),
            _s(f"{sid}_alarms",f"{label} Alarms",f"{_B}/{line}/{cell}/{cid}/alarms",line,"PLC","",60,cid,"conveyor",lambda sh,c=cid:_alarm(c,sh)),
        ]

    # ── ROBOTS ────────────────────────────────────────────────────────────
    for rid,task,line,cell,nom_kw in [
        ("robot_R1","Welding","line_01_assembly","cell_01",5.5),
        ("robot_R2","MaterialHandling","line_01_assembly","cell_02",5.5),
        ("robot_R3","SprayPositioning","line_02_painting","cell_01",4.2),
    ]:
        sid = rid.lower().replace("_","")
        s += [
            _s(f"{sid}_telem",f"{rid} Telemetry",f"{_B}/{line}/{cell}/{rid}/telemetry",line,"PLC","multi",5,rid,"robot",lambda sh,r=rid,t=task:_robot_telemetry(r,t,sh)),
            _s(f"{sid}_power",f"{rid} 3-Phase Power",f"{_B}/{line}/{cell}/{rid}/power",line,"PLC","kW",5,rid,"robot",lambda sh,r=rid,k=nom_kw:_3phase(k,_fault_factor(r,sh),sh)),
            _s(f"{sid}_health",f"{rid} Health",f"{_B}/{line}/{cell}/{rid}/health",line,"SCADA","score",60,rid,"robot",lambda sh,r=rid:_health(r,sh)),
            _s(f"{sid}_alarms",f"{rid} Alarms",f"{_B}/{line}/{cell}/{rid}/alarms",line,"PLC","",60,rid,"robot",lambda sh,r=rid:_alarm(r,sh)),
            _s(f"{sid}_pdm",f"{rid} Predictive Maintenance",f"{_B}/{line}/analytics/pdm/{rid}",line,"AI","days",60,rid,"robot",lambda sh,r=rid:_predictive_maintenance(r,sh)),
        ]

    # ── SPRAYERS ──────────────────────────────────────────────────────────
    for spid,nom_kw in [("sprayer_SP01",2.8),("sprayer_SP02",2.8)]:
        sid = spid.lower().replace("_","")
        s += [
            _s(f"{sid}_telem",f"{spid} Telemetry",f"{_B}/line_02_painting/cell_01/{spid}/telemetry","line_02_painting","PLC","multi",5,spid,"sprayer",lambda sh,sp=spid:_sprayer_telemetry(sp,sh)),
            _s(f"{sid}_power",f"{spid} 3-Phase Power",f"{_B}/line_02_painting/cell_01/{spid}/power","line_02_painting","PLC","kW",5,spid,"sprayer",lambda sh,sp=spid,k=nom_kw:_3phase(k,_fault_factor(sp,sh),sh)),
            _s(f"{sid}_energy",f"{spid} Energy",f"{_B}/line_02_painting/cell_01/{spid}/energy","line_02_painting","MES","kWh",30,spid,"sprayer",lambda sh,sp=spid,k=nom_kw:_energy_rollup(sp,k,30,_fault_factor(sp,sh))),
            _s(f"{sid}_health",f"{spid} Health",f"{_B}/line_02_painting/cell_01/{spid}/health","line_02_painting","SCADA","score",60,spid,"sprayer",lambda sh,sp=spid:_health(sp,sh)),
            _s(f"{sid}_alarms",f"{spid} Alarms",f"{_B}/line_02_painting/cell_01/{spid}/alarms","line_02_painting","PLC","",60,spid,"sprayer",lambda sh,sp=spid:_alarm(sp,sh)),
        ]

    # ── OVEN OV01 ──────────────────────────────────────────────────────────
    s += [
        _s("ov01_telem","OV01 Oven Telemetry",f"{_B}/line_03_curing/cell_01/oven_OV01/telemetry","line_03_curing","PLC","multi",5,"oven_OV01","oven",lambda sh:_oven_telemetry(sh)),
        _s("ov01_power","OV01 3-Phase Power",f"{_B}/line_03_curing/cell_01/oven_OV01/power","line_03_curing","PLC","kW",5,"oven_OV01","oven",lambda sh:_3phase(45.0,_fault_factor("oven_OV01",sh),sh)),
        _s("ov01_energy","OV01 Energy Rollup",f"{_B}/line_03_curing/cell_01/oven_OV01/energy","line_03_curing","MES","kWh",30,"oven_OV01","oven",lambda sh:_energy_rollup("oven_OV01",45.0,30,_fault_factor("oven_OV01",sh))),
        _s("ov01_health","OV01 Health Monitoring",f"{_B}/line_03_curing/cell_01/oven_OV01/health","line_03_curing","SCADA","score",30,"oven_OV01","oven",lambda sh:_health("oven_OV01",sh)),
        _s("ov01_perf","OV01 Performance KPIs",f"{_B}/line_03_curing/cell_01/oven_OV01/performance","line_03_curing","MES","multi",30,"oven_OV01","oven",lambda sh:{"timestamp":_now(),"asset_id":"oven_OV01","oee":round(jitter(82,0.03),1),"zone_temps":[_oven_telemetry(sh)[f"zone{i+1}_temp_c"] for i in range(4)],"status":"fault" if (sh.get("fault") or "") and "oven" in (sh.get("fault") or "") else "normal","dwell_time_min":_oven_telemetry(sh)["dwell_time_min"]}),
        _s("ov01_alarms","OV01 Alarms",f"{_B}/line_03_curing/cell_01/oven_OV01/alarms","line_03_curing","PLC","",60,"oven_OV01","oven",lambda sh:_alarm("oven_OV01",sh)),
        _s("ov01_anomaly","OV01 Anomaly Score",f"{_B}/line_03_curing/analytics/anomaly/oven_OV01","line_03_curing","AI","score",30,"oven_OV01","oven",lambda sh:_analytics_anomaly("oven_OV01",sh)),
        _s("ov01_pdm","OV01 Predictive Maintenance",f"{_B}/line_03_curing/analytics/pdm/oven_OV01","line_03_curing","AI","days",60,"oven_OV01","oven",lambda sh:_predictive_maintenance("oven_OV01",sh)),
    ]

    # ── COMPRESSOR ────────────────────────────────────────────────────────
    s += [
        _s("cp01_telem","CP01 Compressor Telemetry",f"{_B}/utilities/compressor_CP01/telemetry","utilities","PLC","multi",10,"compressor_CP01","compressor",lambda sh:_compressor_telemetry(sh)),
        _s("cp01_power","CP01 3-Phase Power",f"{_B}/utilities/compressor_CP01/power","utilities","PLC","kW",5,"compressor_CP01","compressor",lambda sh:_3phase(22.0,_fault_factor("compressor_CP01",sh),sh)),
        _s("cp01_energy","CP01 Energy Rollup",f"{_B}/utilities/compressor_CP01/energy","utilities","MES","kWh",30,"compressor_CP01","compressor",lambda sh:_energy_rollup("compressor_CP01",22.0,30,_fault_factor("compressor_CP01",sh))),
        _s("cp01_health","CP01 Health",f"{_B}/utilities/compressor_CP01/health","utilities","SCADA","score",60,"compressor_CP01","compressor",lambda sh:_health("compressor_CP01",sh)),
        _s("cp01_alarms","CP01 Alarms",f"{_B}/utilities/compressor_CP01/alarms","utilities","PLC","",60,"compressor_CP01","compressor",lambda sh:_alarm("compressor_CP01",sh)),
        _s("cp01_anomaly","CP01 Energy Anomaly",f"{_B}/utilities/analytics/anomaly/compressor_CP01","utilities","AI","score",30,"compressor_CP01","compressor",lambda sh:_analytics_anomaly("compressor_CP01",sh)),
        _s("cp01_pdm","CP01 Predictive Maintenance",f"{_B}/utilities/analytics/pdm/compressor_CP01","utilities","AI","days",60,"compressor_CP01","compressor",lambda sh:_predictive_maintenance("compressor_CP01",sh)),
        _s("air_network","Air Network Monitoring",f"{_B}/utilities/air_network/pressure","utilities","PLC","bar",10,"compressor_CP01","compressor",lambda sh:_air_network(sh)),
    ]

    # ── INSPECTION ────────────────────────────────────────────────────────
    s += [
        _s("cmm01_result","CMM01 Inspection Result",f"{_B}/line_04_inspection/cell_01/vision_CMM01/result","line_04_inspection","PLC","",15,"vision_CMM01","inspection",lambda sh:_inspection_result("vision_CMM01","dimensional_vision",0.97,sh)),
        _s("cmm01_dims","CMM01 Dimensional Measurements",f"{_B}/line_04_inspection/cell_01/vision_CMM01/dimensions","line_04_inspection","QMS","mm",15,"vision_CMM01","inspection",lambda sh:_cmm_measurement(sh)),
        _s("cmm01_power","CMM01 Power",f"{_B}/line_04_inspection/cell_01/vision_CMM01/power","line_04_inspection","PLC","kW",30,"vision_CMM01","inspection",lambda sh:_3phase(1.2,1.0,sh)),
        _s("cmm01_health","CMM01 Health",f"{_B}/line_04_inspection/cell_01/vision_CMM01/health","line_04_inspection","SCADA","score",60,"vision_CMM01","inspection",lambda sh:_health("vision_CMM01",sh)),
        _s("lt01_result","LT01 Leak Test Result",f"{_B}/line_04_inspection/cell_02/leak_test_LT01/result","line_04_inspection","PLC","",20,"leak_test_LT01","inspection",lambda sh:_inspection_result("leak_test_LT01","pressure_leak_test",0.99,sh)),
        _s("lt01_power","LT01 Power",f"{_B}/line_04_inspection/cell_02/leak_test_LT01/power","line_04_inspection","PLC","kW",30,"leak_test_LT01","inspection",lambda sh:_3phase(0.8,1.0,sh)),
        _s("lt01_health","LT01 Health",f"{_B}/line_04_inspection/cell_02/leak_test_LT01/health","line_04_inspection","SCADA","score",60,"leak_test_LT01","inspection",lambda sh:_health("leak_test_LT01",sh)),
    ]

    # ── QMS SPC CHARTS ────────────────────────────────────────────────────
    s += [
        _s("spc_wall_th","SPC — Wall Thickness",f"{_B}/quality/spc/wall_thickness","quality","QMS","mm",20,"vision_CMM01","quality",lambda sh:_quality_spc_chart("wall_thickness_mm",2.0,0.15,-0.15,sh)),
        _s("spc_coat_th","SPC — Coat Thickness",f"{_B}/quality/spc/coat_thickness","quality","QMS","um",20,"sprayer_SP01","quality",lambda sh:_quality_spc_chart("coat_thickness_um",80.0,20.0,-20.0,sh)),
        _s("spc_pr01_force","SPC — PR01 Press Force",f"{_B}/quality/spc/press_force_pr01","quality","QMS","kN",10,"press_PR01","quality",lambda sh:_quality_spc_chart("press_force_kn",750.0,30.0,-30.0,sh)),
        _s("spc_draw_depth","SPC — Draw Depth",f"{_B}/quality/spc/draw_depth","quality","QMS","mm",10,"press_PR01","quality",lambda sh:_quality_spc_chart("draw_depth_mm",85.0,0.5,-0.5,sh)),
    ]

    # ── RFID TRACKING ─────────────────────────────────────────────────────
    s += [
        _s("rfid_line01_in","RFID Line 01 Entry",f"{_B}/line_01_assembly/rfid/entry","Line 01","PLC","",10,"rfid_reader_01","rfid",lambda sh:_rfid_scan("RFID-01-ENTRY","Line01_Entry",sh)),
        _s("rfid_line01_out","RFID Line 01 Exit",f"{_B}/line_01_assembly/rfid/exit","Line 01","PLC","",10,"rfid_reader_01","rfid",lambda sh:_rfid_scan("RFID-01-EXIT","Line01_Exit",sh)),
        _s("rfid_line04_in","RFID Inspection Entry",f"{_B}/line_04_inspection/rfid/entry","line_04_inspection","PLC","",15,"rfid_reader_02","rfid",lambda sh:_rfid_scan("RFID-04-ENTRY","Inspection_Entry",sh)),
    ]

    # ── ENVIRONMENTAL ─────────────────────────────────────────────────────
    s += [
        _s("env_floor","Factory Floor Environment",f"{_B}/plant/environment/floor","plant","SCADA","multi",60,"plant","environmental",lambda sh:_environmental(sh)),
    ]

    # ── ERP STREAMS ───────────────────────────────────────────────────────
    s += [
        _s("erp_order","ERP Production Order",f"{_B}/erp/production_orders/current","ERP","ERP","",30,"plant","ERP",lambda sh:_erp_production_order(sh)),
        _s("erp_materials","ERP Material Consumption",f"{_B}/erp/materials/consumption","ERP","ERP","kg",60,"plant","ERP",lambda sh:_erp_material_consumption(sh)),
        _s("erp_holds","ERP Quality Holds",f"{_B}/erp/quality/holds","ERP","ERP","",30,"plant","ERP",lambda sh:_erp_quality_hold(sh)),
    ]

    # ── MES STREAMS ───────────────────────────────────────────────────────
    s += [
        _s("mes_batch","MES Batch Tracking",f"{_B}/mes/batch_tracking","MES","MES","",20,"plant","MES",lambda sh:_mes_batch_tracking(sh)),
        _s("mes_wo","MES Work Order",f"{_B}/mes/work_orders/active","MES","MES","",30,"plant","MES",lambda sh:_mes_work_order(sh)),
        _s("mes_shift","MES Shift Summary",f"{_B}/mes/shift/summary","MES","MES","",60,"plant","MES",lambda sh:_mes_shift_summary(sh)),
    ]

    # ── DPP EVENTS ────────────────────────────────────────────────────────
    s += [
        _s("dpp_unit","DPP Unit Event",f"{_B}/line_04_inspection/cell_02/process/step_status","line_04_inspection","MES","",20,"plant","DPP",lambda sh:_dpp_event(sh)),
    ]

    # ── PLANT-LEVEL ROLLUPS ────────────────────────────────────────────────
    s += [
        _s("plant_energy","Plant Total Energy",f"{_B}/plant/energy/total","plant","SCADA","kWh",30,"plant","plant",
           lambda sh:{"timestamp":_now(),"total_kwh":round(sum(SIM.kwh_total.values()),1),
                      "current_kw":round(sum(_ASSET_NOM_KW.values())*random.uniform(0.7,0.95),1),
                      "energy_intensity_kwh_per_unit":round(jitter(0.185,0.04),3),
                      "co2_kg_today":round(sum(SIM.kwh_total.values())*0.233,1),
                      "cost_eur_today":round(sum(SIM.kwh_total.values())*0.12,2)}),
        _s("plant_oee","Plant OEE",f"{_B}/plant/kpi/oee","plant","MES","pct",30,"plant","plant",
           lambda sh:{"timestamp":_now(),"oee_pct":round(jitter(79 if not sh.get("fault") else 65,0.03),1),
                      "availability_pct":round(jitter(88,0.02),1),"performance_pct":round(jitter(92,0.02),1),
                      "quality_pct":round(jitter(98,0.01),1),"units_produced_shift":SIM.unit_seq,
                      "scrap_count":SIM.scrap_count,"rework_count":SIM.rework_count,
                      "shift":sh.get("shift","A")}),
        _s("plant_process","Plant Process Status",f"{_B}/process/unit_id","plant","MES","",10,"plant","plant",
           lambda sh:{"timestamp":_now(),"current_unit":f"UNIT-{SIM.unit_seq:06d}",
                      "batch_id":SIM.current_batch,"product":SIM.current_product,
                      "line_01_status":"Running","line_02_status":"Running",
                      "line_03_status":"Running","line_04_status":"Running"}),
    ]

    # ── LINE-LEVEL ENERGY ROLLUPS ─────────────────────────────────────────
    for line_id, asset_ids in [
        ("line_01_assembly",["press_PR01","press_PR02","conveyor_CV01","conveyor_CV02","robot_R1","robot_R2"]),
        ("line_02_painting", ["sprayer_SP01","sprayer_SP02","conveyor_CV03","robot_R3"]),
        ("line_03_curing",   ["oven_OV01","conveyor_CV04"]),
        ("line_04_inspection",["vision_CMM01","leak_test_LT01"]),
    ]:
        nom_kw = sum(_ASSET_NOM_KW.get(a,0) for a in asset_ids)
        s.append(_s(f"{line_id}_energy",f"{line_id} Line Energy Rollup",f"{_B}/{line_id}/energy/total",
            line_id,"SCADA","kWh",30,line_id,"line",
            lambda sh,k=nom_kw:{"timestamp":_now(),"total_kw":round(jitter(k,0.04),1),
                                "period_kwh":round(jitter(k*30/3600,0.04),3)}))

    return s

STREAMS      = _make_streams()
STREAM_BY_ID = {s["id"]: s for s in STREAMS}
