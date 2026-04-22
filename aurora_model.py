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

# ─────────────────────────────────────────────────────────────────────────────
# Batch lifecycle state machine
# ─────────────────────────────────────────────────────────────────────────────
# Stages a batch progresses through in real plant sequence:
#   PLANNED → RELEASED → PRESSING → PAINTING → CURING → INSPECTING → COMPLETE
#
# Each stage has:
#   - name        human-readable step
#   - line        which production line is active
#   - duration_s  simulated wall-clock seconds per stage (compressed for demo)
#   - target_pct  what % of batch_target_qty should be done by end of stage
#   - topic_hint  MES/ERP UNS topic prefix that fires events in this stage

BATCH_STAGES = [
    {"name": "PLANNED",    "line": "erp",          "duration_s":  30, "target_pct":   0},
    {"name": "RELEASED",   "line": "erp",          "duration_s":  20, "target_pct":   0},
    {"name": "PRESSING",   "line": "line_01_assembly", "duration_s": 120, "target_pct": 35},
    {"name": "PAINTING",   "line": "line_02_painting", "duration_s":  90, "target_pct": 65},
    {"name": "CURING",     "line": "line_03_curing",   "duration_s":  60, "target_pct": 85},
    {"name": "INSPECTING", "line": "line_04_inspection","duration_s": 50, "target_pct":100},
    {"name": "COMPLETE",   "line": "erp",          "duration_s":  30, "target_pct": 100},
]

BATCH_TARGET_QTY = 200  # units per demo batch (compressed from real 1000)

class BatchLifecycle:
    """Tracks the current batch through the manufacturing stages."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.stage_idx      = 0          # index into BATCH_STAGES
        self.stage_entered  = time.time()
        self.batch_id       = _new_batch(1)
        self.batch_seq      = 1
        self.order_id       = "PO-010001"
        self.work_order_id  = "WO-050001"
        self.wo_seq         = 50001
        self.order_seq      = 10001
        self.target_qty     = BATCH_TARGET_QTY
        self.units_started  = 0
        self.units_passed   = 0
        self.units_rework   = 0
        self.units_scrap    = 0
        self.dpp_triggered  = False       # set True when DPP button pressed
        self.completed_batches: list = []  # history

    @property
    def stage(self) -> dict:
        return BATCH_STAGES[self.stage_idx]

    @property
    def stage_name(self) -> str:
        return self.stage["name"]

    @property
    def elapsed_in_stage(self) -> float:
        return time.time() - self.stage_entered

    @property
    def stage_progress_pct(self) -> float:
        return min(100.0, self.elapsed_in_stage / max(1, self.stage["duration_s"]) * 100)

    @property
    def completion_pct(self) -> float:
        """Overall batch completion based on units vs target."""
        return round(min(100.0, self.units_started / max(1, self.target_qty) * 100), 1)

    @property
    def batch_status(self) -> str:
        if self.stage_name == "COMPLETE":
            return "COMPLETE"
        if self.stage_name in ("PLANNED", "RELEASED"):
            return self.stage_name
        return "IN_PROGRESS"

    @property
    def active_line(self) -> str:
        return self.stage["line"]

    def advance(self):
        """Move to the next stage. Called automatically by the publisher loop."""
        if self.stage_idx >= len(BATCH_STAGES) - 1:
            self._complete_batch()
            return
        self.stage_idx += 1
        self.stage_entered = time.time()

    def _complete_batch(self):
        """Archive current batch and start a fresh one."""
        self.completed_batches.append({
            "batch_id":      self.batch_id,
            "order_id":      self.order_id,
            "work_order_id": self.work_order_id,
            "units_started": self.units_started,
            "units_passed":  self.units_passed,
            "units_rework":  self.units_rework,
            "units_scrap":   self.units_scrap,
            "completed_at":  _now(),
            "fpy_pct":       round(self.units_passed / max(1, self.units_started) * 100, 1),
        })
        # Roll to next batch
        self.batch_seq     += 1
        self.order_seq     += 1
        self.wo_seq        += 1
        self.batch_id       = _new_batch(self.batch_seq)
        self.order_id       = f"PO-{self.order_seq:06d}"
        self.work_order_id  = f"WO-{self.wo_seq:06d}"
        self.units_started  = 0
        self.units_passed   = 0
        self.units_rework   = 0
        self.units_scrap    = 0
        self.dpp_triggered  = False
        self.stage_idx      = 0          # back to PLANNED
        self.stage_entered  = time.time()

    def tick(self, fault: str, unit_seq: int, scrap_count: int, rework_count: int):
        """Called every publisher cycle. Advances stage if duration elapsed."""
        # Update unit counts from global SIM (only during active production stages)
        if self.stage_name in ("PRESSING", "PAINTING", "CURING", "INSPECTING"):
            self.units_started = min(unit_seq, self.target_qty)
            pct = self.stage["target_pct"] / 100.0
            self.units_passed  = max(0, int(self.units_started - scrap_count - rework_count))
            self.units_rework  = rework_count
            self.units_scrap   = scrap_count
        # Auto-advance unless a fault holds us in INSPECTING or PRESSING
        if fault in ("oven_OV01_zone2_fail", "batch_quality_hold", "oven_OV01_overshoot"):
            return  # stage frozen during quality hold
        if self.elapsed_in_stage >= self.stage["duration_s"]:
            self.advance()

BATCH = BatchLifecycle()

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
    # Use live BATCH lifecycle state
    on_hold = fault in ("oven_OV01_zone2_fail", "batch_quality_hold", "oven_OV01_overshoot")
    status = "ON_HOLD" if on_hold else BATCH.batch_status
    stage  = BATCH.stage_name

    # Stage-specific active line context
    line_activity = {
        "PLANNED":    {"active_line": "erp",              "active_operation": "ORDER_PLANNING"},
        "RELEASED":   {"active_line": "erp",              "active_operation": "MATERIAL_STAGING"},
        "PRESSING":   {"active_line": "line_01_assembly", "active_operation": "PRESS_STAMP"},
        "PAINTING":   {"active_line": "line_02_painting", "active_operation": "SPRAY_COAT"},
        "CURING":     {"active_line": "line_03_curing",   "active_operation": "OVEN_CURE"},
        "INSPECTING": {"active_line": "line_04_inspection","active_operation": "CMM_INSPECT"},
        "COMPLETE":   {"active_line": "erp",              "active_operation": "FINISHED_GOODS"},
    }.get(stage, {"active_line": "unknown", "active_operation": "UNKNOWN"})

    fpy = round(BATCH.units_passed / max(1, BATCH.units_started) * 100, 1)
    return {
        "timestamp":         _now(), "source": "MES",
        "batch_id":          BATCH.batch_id,
        "batch_seq":         BATCH.batch_seq,
        "product":           SIM.current_product,
        "order_id":          BATCH.order_id,
        "work_order_id":     BATCH.work_order_id,
        "shift":             shared.get("shift","A"),
        "current_stage":     stage,
        "stage_progress_pct": round(BATCH.stage_progress_pct, 1),
        "active_line":       line_activity["active_line"],
        "active_operation":  line_activity["active_operation"],
        "units_started":     BATCH.units_started,
        "units_passed":      BATCH.units_passed,
        "units_rework":      BATCH.units_rework,
        "units_scrap":       BATCH.units_scrap,
        "first_pass_yield_pct": fpy,
        "batch_status":      status,
        "target_qty":        BATCH.target_qty,
        "completion_pct":    BATCH.completion_pct,
        "oee_batch":         round(jitter(79 if not fault else 65, 0.03), 1),
        "batches_completed_today": len(BATCH.completed_batches),
    }

def _mes_work_order(shared: dict) -> dict:
    fault = shared.get("fault") or ""
    mat_shortage = fault == "erp_material_shortage"
    stage = BATCH.stage_name
    # Map stage → operation and machine
    op_map = {
        "PRESSING":   ("PRESS_STAMP",   "press_PR01"),
        "PAINTING":   ("SPRAY_COAT",    "robot_R3"),
        "CURING":     ("OVEN_CURE",     "oven_OV01"),
        "INSPECTING": ("CMM_INSPECT",   "vision_CMM01"),
    }
    operation, machine_id = op_map.get(stage, ("PRESS_STAMP", "press_PR01"))
    downtime = round(jitter(0 if not fault else 22.5, 0.2), 1)
    return {
        "timestamp":       _now(), "source": "MES",
        "work_order_id":   BATCH.work_order_id,
        "batch_id":        BATCH.batch_id,
        "operation":       operation,
        "machine_id":      machine_id,
        "operator_id":     f"OP-{random.randint(100,120):03d}",
        "status":          "WAITING_MATERIAL" if mat_shortage else ("ON_HOLD" if fault in ("oven_OV01_zone2_fail","batch_quality_hold") else "IN_PROGRESS"),
        "current_stage":   stage,
        "start_time":      _now(),
        "setup_time_min":  round(jitter(12.0, 0.05), 1),
        "run_time_min":    round(jitter(480.0, 0.01), 1),
        "downtime_min":    downtime,
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
        "what_it_shows": "Healthy baseline: all 111 UNS streams within expected ranges, OEE 79%, energy at nominal, zero active alarms. Every asset health score ≥ 90%. This is the reference state against which AI detects every other scenario.",
        "how_to_demo": "1. Start here before showing any fault. 2. Open Streams tab — filter to any asset (e.g. PR01) and show all readings in green/nominal. 3. Open Energy tab — plant kW matches expected shift load, 3-phase currents balanced, THD < 3%. 4. Open Health tab — all bars above 90%. 5. Show the AI hint at top: 'No anomalies'. 6. Say: 'This is what the AI sees as normal. Every scenario after this deviates from this baseline.'",
        "ai_answer": "Normal plant state: PR01 hydraulic_pressure 210 bar, cycle_time 4.2 s, OEE 79.3%. OV01 all zone temps within ±2°C of setpoint. CP01 power 22 kW, PF 0.91, THD 2.1%. All robot position errors < 0.2mm. No health scores below 85%. Rolling 24h FPY: 98.2%. AI anomaly scores all LOW (< 0.1). Energy cost rate: €18.4/hr.",
        "root_cause": "No fault. All systems nominal.",
        "affected_streams": ["aurora/plant/L01/press_PR01/telemetry", "aurora/plant/L03/oven_OV01/telemetry", "aurora/plant/energy/CP01/power", "aurora/plant/health/*/pdm"],
        "visual_indicators": "All stream values green. Health bars > 90%. AI hint shows 'No anomalies'. OEE 79% in header. Plant Power reading matches expected shift load.",
        "steps": ["Open Streams tab", "Filter by label 'press_PR01' — show hydraulic_pressure_bar = 210, cycle_time_s = 4.2", "Switch to Energy tab — show CP01 total_kw = 22, PF = 0.91", "Switch to Health tab — all assets green", "Point to AI Hint: 'No anomalies'"],
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":79,"energy":"nominal","quality":98},
    },
    "press_PR01_hydraulic_degradation": {
        "label": "PR01 — Hydraulic Pump Wear (Early Stage)",
        "description": "PR01 hydraulic pressure slowly declining. Oil temp rising. Pump efficiency dropping. Classic early-stage hydraulic pump wear — catches before alarm threshold.",
        "fault_key": "press_PR01_pressure_low", "affected": ["press_PR01"],
        "health_degrade": {"press_PR01": {"HydraulicPump": 0.8}},
        "ai_hint": "Pressure trending down -0.8 bar/day over 3 days. Oil temp +3°C. Pump efficiency -12%. Recommend hydraulic pump inspection within 5 days.",
        "what_it_shows": "Sub-threshold degradation that rules-based SCADA alarms completely miss. The SCADA alarm limit is 192 bar — pressure is at 196 bar so no alarm fires. But the AI detects a 3-day downward trend of -0.8 bar/day. Without AI, this pump fails unplanned in ~5 days. With AI, maintenance is scheduled proactively during next planned stop.",
        "how_to_demo": "1. Switch to this scenario. 2. Open Streams tab, filter 'press_PR01'. 3. Point to hydraulic_pressure_bar = 196 (alarm limit 192 — no alarm). 4. Point to oil_temperature_c = 53 (nominal 50°C). 5. Point to pump_efficiency_pct = 74 (nominal 85%). 6. Switch to Health tab — HydraulicPump bar at 78%. 7. Show PdM stream — RUL 5 days, urgency SOON. 8. Ask the AI the question below and show the answer.",
        "ai_answer": "Root cause: Progressive internal wear of the hydraulic pump piston seals. Evidence: pressure 196 bar (nominal 210, alarm 192) trending -0.8 bar/day for 3 days; oil temp +3°C above baseline (heat generated by internal leakage); pump efficiency -12% (measuring output flow vs motor input power). SCADA alarm will not fire until 192 bar — estimated 5 days at current trend. Recommended action: Schedule pump inspection at next planned stop (within 48h). Check suction strainer, measure volumetric efficiency, replace if < 88%. If ignored: pump failure causes unplanned downtime of ~4h + €2,800 repair cost + 180 units lost production. Preventive action cost: €420 (2h labour + filter).",
        "root_cause": "Hydraulic pump piston seal wear causing internal leakage. Oil temp rise confirms energy lost to heat rather than hydraulic work.",
        "affected_streams": ["aurora/plant/L01/press_PR01/telemetry → hydraulic_pressure_bar, oil_temperature_c, pump_efficiency_pct", "aurora/plant/health/press_PR01/pdm → HydraulicPump RUL", "aurora/plant/L01/press_PR01/performance → cycle_time_s (slightly elevated)"],
        "visual_indicators": "Streams tab: hydraulic_pressure_bar just above alarm threshold (196 vs 192 limit). Health tab: HydraulicPump component bar yellow at ~78%. PdM tab: RUL = 5 days, urgency = SOON. No active alarms — this is the point.",
        "steps": ["Switch scenario → 'PR01 Hydraulic Pump Wear'", "Streams tab → filter 'press_PR01' → show hydraulic_pressure_bar, oil_temperature_c, pump_efficiency_pct", "Health tab → HydraulicPump = 78% (yellow)", "PdM row: RUL 5d, SOON badge", "Ask AI the question → show answer with €-impact"],
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":76,"energy":"nominal","quality":97},
    },
    "oven_zone2_heater_failure": {
        "label": "OV01 — Zone 2 Heater Element Failure",
        "description": "Zone 2 temperature dropped 110°C below setpoint. Parts curing in zone 2 will be undercured. Downstream quality risk. MES triggers batch hold.",
        "fault_key": "oven_OV01_zone2_fail", "affected": ["oven_OV01"],
        "health_degrade": {"oven_OV01": {"Zone2Heater": 2.5}},
        "ai_hint": "Zone 2 temp = 90°C vs 200°C setpoint. Zones 1/3/4 normal. Heater element failure. All parts in current batch should be placed on quality hold. Estimated cure deficiency: 55% of required dwell time at temperature.",
        "what_it_shows": "Multi-system correlation across four data layers: OV01 PLC telemetry (zone temp drop), MES batch system (automatic batch hold triggered), ERP SAP (quality hold document created), DPP (every unit that passed through zone 2 flagged). No human action required — the integration does it automatically. AI calculates cure deficiency and quantifies how many units are at risk.",
        "how_to_demo": "1. Switch to this scenario. 2. Streams tab → filter 'oven_OV01' → show zone_1_temp=182°C, zone_2_temp=90°C (setpoint 200), zone_3_temp=171°C, zone_4_temp=201°C. 3. ERP/MES tab → show batch_status = ON_HOLD, quality_hold_active = true. 4. DPP tab / Feed → show units flagged. 5. Ask AI the question → it calculates cure deficiency and recommends disposition.",
        "ai_answer": "Zone 2 heater element has failed (resistance open-circuit, confirmed by zero current draw on zone 2 SSR). Zone 2 temp 90°C vs 200°C setpoint — a 110°C shortfall. Cure specification: 200°C for minimum 6.4 min per zone. At 90°C, curing reaction rate (Arrhenius) is ~8% of nominal — effectively no cure in zone 2. Impact on current batch BATCH-20260417-001: 234 units produced since fault onset, all have ~55% cure deficiency. Recommendation: (1) STOP line immediately, (2) Place full batch on quality hold, (3) Destructive test 5 units — measure cross-link density, (4) If < 60% of spec: scrap batch (cost ~€14,000), (5) If 60-80%: re-cure at 210°C for 8 min in secondary oven. Heater repair: replace element (30 min, €85 part). Root cause: Element fatigue — check replacement schedule (expected life 8,000h, current age 7,200h).",
        "root_cause": "Zone 2 heating element open-circuit failure. Element fatigue at 90% of rated life. Power SSR shows no current draw on zone 2 circuit.",
        "affected_streams": ["aurora/plant/L03/oven_OV01/telemetry → zone_2_temp_c (90 vs 200°C)", "aurora/mes/batch/BATCH-20260417-001 → batch_status=ON_HOLD", "aurora/erp/quality/holds → hold_id, batch_ref, units_affected", "aurora/plant/L04/inspection_CMM01/dpp → units flagged in window"],
        "visual_indicators": "Streams tab: zone_2_temp_c = 90 (red, setpoint 200). ERP/MES tab: batch_status = ON_HOLD, quality_hold_active = true. Product flow bar: Curing node turns red. AI hint: cure deficiency warning.",
        "steps": ["Switch scenario → 'OV01 Zone 2 Heater Failure'", "Streams tab → filter 'oven_OV01' → zone_2_temp_c = 90 (red)", "ERP/MES tab → batch status = ON_HOLD", "Quality tab → FPY dropped to 72%", "Ask AI → cure deficiency + disposition logic"],
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":71,"energy":"reduced_zone2","quality":72},
    },
    "paint_filter_blockage": {
        "label": "SP02 — Paint Filter Progressive Blockage",
        "description": "SP02 paint filter differential pressure rising over 2 hours. Atomisation pressure dropping. Coat thickness falling below 60µm minimum. AI correlates filter DP → coat thickness.",
        "fault_key": "sprayer_SP02_filter_blocked", "affected": ["sprayer_SP02"],
        "health_degrade": {"sprayer_SP02": {"FilterUnit": 1.2}},
        "ai_hint": "Filter DP: 0.68 bar (limit 0.5 bar). Coat thickness: 45µm (min 60µm). Atomisation pressure: 1.9 bar (setpoint 3.0 bar). Replace filter immediately, quality hold on last 45 min of production.",
        "what_it_shows": "Gradual drift detected by correlating two separate streams that neither individually would alarm on fast enough. The filter_dp stream shows slow rise (0.12 → 0.68 bar over 2 hours). The coat_thickness stream shows slow fall (80 → 45µm over same window). AI computes correlation coefficient (r = -0.94) and issues diagnosis. A traditional threshold alarm on coat_thickness would only fire after 30 min of out-of-spec production.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'sprayer_SP02' → show filter_dp_bar = 0.68 (rising), coat_thickness_um = 45 (minimum 60). 3. Health tab → FilterUnit at 32% (red). 4. Quality tab → FPY falling, coat_uniformity_pct declining. 5. Ask AI the question → shows correlated root cause and affected time window.",
        "ai_answer": "Root cause: SP02 paint filter blocked by accumulated paint solids and pigment agglomeration. Evidence: Filter DP rose from 0.12 bar (clean) to 0.68 bar (blocked limit 0.5 bar) over 127 minutes — a 467% increase. This restricted atomisation air pressure from 3.0 bar setpoint to 1.9 bar, reducing paint atomisation quality (larger droplet size → thinner, uneven coat). Coat thickness correlation: r = -0.94 between filter_dp and coat_thickness — highly causal. Affected production window: last 45 minutes (approx 338 parts). Parts in window have coat_thickness 45-58µm vs minimum 60µm spec — 100% of window is non-conforming. Rework cost estimate: €2.4k (re-spray + cure cycle). Action: (1) Replace SP02 filter now (5 min, €12 part), (2) Quality hold on last 45-min batch window, (3) Visual inspection + re-spray at thickness gauge. Filter replacement interval: every 8h at current paint throughput (current interval was 14h — halve it).",
        "root_cause": "Paint filter clogged with pigment solids. Root cause of rapid blocking: filter replacement interval too long for current paint throughput rate.",
        "affected_streams": ["aurora/plant/L02/sprayer_SP02/telemetry → filter_dp_bar (0.68), coat_thickness_um (45), atomisation_pressure_bar (1.9)", "aurora/plant/health/sprayer_SP02/pdm → FilterUnit health 32%", "aurora/plant/qms/spc → coat_thickness SPC chart out of control"],
        "visual_indicators": "Streams tab: filter_dp_bar = 0.68 (orange/red), coat_thickness_um = 45 (below 60 min, red). Health tab: FilterUnit bar red at 32%. Quality tab: FPY dipping, coat thickness SPC out of control. AI hint: filter blockage + quality hold.",
        "steps": ["Switch scenario → 'SP02 Filter Blockage'", "Streams tab → filter 'sprayer_SP02' → filter_dp_bar high, coat_thickness_um low", "Health tab → FilterUnit = 32% (red)", "Quality tab → SPC out of control on coat_thickness", "Ask AI → correlation r=-0.94, 338 parts affected, rework cost"],
        "data_sources": ["PLC","QMS","MES","AI"],
        "kpi_impact": {"oee":77,"energy":"nominal","quality":81},
    },
    "conveyor_cv01_jam": {
        "label": "CV01 — Belt Jam (Line 1 Cell 1 Blocked)",
        "description": "CV01 belt stopped. Press PR01 starved of parts. Line 1 Cell 1 production halted. Shows cascading throughput impact and AI recovery sequencing.",
        "fault_key": "conveyor_CV01_jam", "affected": ["conveyor_CV01","press_PR01"],
        "health_degrade": {},
        "ai_hint": "CV01 speed = 0 m/s. Press PR01 cycle count frozen. Estimated production loss: 7.5 units/min. Recovery: check belt tension, clear jam, restart in sequence CV01 → PR01. ETA to recovery: 15-20 min.",
        "what_it_shows": "Hard fault with immediate cascading throughput impact across two assets. CV01 jam stops part flow → PR01 enters 'Starved' state → cycle count stops → MES work order accumulates downtime minutes → ERP production order completion % freezes. Shows AI-driven recovery planning that gives the operator a prioritised LOTO + restart sequence rather than leaving them to figure it out.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'conveyor_CV01' → speed_m_s = 0, jam_detected = true, belt_tension_n = 200. 3. Filter 'press_PR01' → operational_status = 'Starved', cycle_count frozen. 4. ERP/MES tab → downtime_min increasing, work order status = DOWNTIME. 5. Ask AI the question → get full LOTO + restart sequence with time estimate.",
        "ai_answer": "CV01 belt jam confirmed: speed = 0 m/s, jam_detected = true, belt_tension_n = 200N (normal 120N — part wedged in return section). Cascade: PR01 parts buffer emptied in ~90 sec after jam → PR01 operational_status = Starved → PR01 OEE contribution = 0. Current production loss rate: 7.5 units/min × €28/unit = €210/min or €12,600/hr. Recovery sequence: (1) LOTO CV01 isolator (Panel A, Switch 3) — 2 min. (2) Inspect belt at return roller zone (most common jam point) — 3 min. (3) Remove jammed part manually — 2 min. (4) Check belt alignment (re-tension if > 180N after clearing). (5) Release LOTO, start CV01 at 20% speed for 30 sec (test run) — 3 min. (6) Resume normal speed, confirm PR01 restarts auto from Starved → Running. (7) Log downtime in MES WO. Total estimated recovery: 15-18 min = €2,625-€3,150 production loss. Remaining batch (156 units): achievable if recovered within 21 min — shift OEE recoverable to ~71%.",
        "root_cause": "Foreign object or part misalignment in CV01 belt return section. Belt tension at 200N (normal 120N) confirms lodged object pulling belt tight.",
        "affected_streams": ["aurora/plant/L01/conveyor_CV01/telemetry → speed_m_s=0, jam_detected=true, belt_tension_n=200", "aurora/plant/L01/press_PR01/performance → operational_status=Starved, cycle_count frozen", "aurora/mes/workorder/WO-2026-0417 → downtime_min incrementing", "aurora/erp/production/order_completion_pct → frozen"],
        "visual_indicators": "Streams tab: CV01 speed_m_s = 0 (red), jam_detected = true. PR01 operational_status = Starved. ERP/MES tab: downtime_min increasing. OEE in header dropped to 58%. Product flow bar: Pressing node red.",
        "steps": ["Switch scenario → 'CV01 Belt Jam'", "Streams tab → CV01: speed=0, jam_detected=true, belt_tension=200N", "Streams tab → PR01: operational_status=Starved", "ERP/MES tab → WO downtime_min counting up", "Ask AI → LOTO sequence + recovery time + €/min impact"],
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":58,"energy":"reduced_line1","quality":99},
    },
    "energy_anomaly_night_shift": {
        "label": "Energy Anomaly — Compressor Off-Hours Overconsumption",
        "description": "Compressor CP01 drawing 35% more power than baseline during night shift. Phase C current imbalance. THD elevated. Annual cost impact quantified.",
        "fault_key": "compressor_CP01_overload", "affected": ["compressor_CP01"],
        "health_degrade": {"compressor_CP01": {"Valve": 0.5, "Intercooler": 0.3}},
        "ai_hint": "CP01 consuming 29.7 kW vs 22 kW baseline (+35%). Phase C current 18A vs 12A nominal (50% imbalance). THD: 8.5% (limit 5%). Power factor: 0.73 (expected 0.91). Likely: valve wear or intercooler fouling. Annual excess cost: ~€8,400.",
        "what_it_shows": "Energy intelligence that goes far beyond basic kWh monitoring. The 3-phase current imbalance (Phase C at 150% of A and B) combined with elevated THD points specifically to a valve or intercooler fault — not a motor or VFD issue. This distinction saves hours of diagnostic time. The AI then calculates the annual €-impact, making the business case for immediate repair obvious.",
        "how_to_demo": "1. Switch scenario. 2. Energy tab → CP01 row: total_kw = 29.7 (vs 22 baseline), Phase C current = 18A vs 12A for A and B. 3. Show THD = 8.5% (limit 5%), PF = 0.73 (expected 0.91). 4. Health tab → Valve = 68%, Intercooler = 72%. 5. Energy tab → show cost_eur_hr trending up. 6. Ask AI → it quantifies the fault and annual impact.",
        "ai_answer": "Root cause: CP01 discharge valve wear causing inefficient compression cycle, compounded by partial intercooler fouling. Evidence: Phase C current 18A vs 12A (50% imbalance) — this rules out motor winding issue (which would affect all phases equally) and points to mechanical load asymmetry in the compressor cylinder. THD 8.5% (limit 5%) indicates non-sinusoidal current draw — consistent with valve flutter causing intermittent loading. PF 0.73 vs expected 0.91: reactive power waste. Power excess: 7.7 kW × €0.14/kWh × 8,760 hrs = €9,440/year. However compressor runs ~70% of time so actual excess: ~€6,600/year. Additional cost: accelerated bearing wear from vibration (estimated €1,800 bearing replacement in 6 months if not fixed). Total annual impact: ~€8,400. Repair: (1) Replace discharge valve set (4h, €380 parts), (2) Clean intercooler (2h, €120 chemical clean). ROI: repair cost €1,200 vs annual saving €8,400 = 7-week payback.",
        "root_cause": "CP01 discharge valve wear + intercooler fouling. Valve wear creates load asymmetry (Phase C imbalance) and flutter (THD elevation). Intercooler fouling reduces cooling efficiency, increasing compression work.",
        "affected_streams": ["aurora/plant/energy/CP01/power → total_kw=29.7, phase_c_current=18A, thd_pct=8.5, power_factor=0.73", "aurora/plant/health/compressor_CP01/pdm → Valve=68%, Intercooler=72%", "aurora/plant/energy/plant/rollup → cost_eur_hr elevated"],
        "visual_indicators": "Energy tab: CP01 row shows total_kw elevated (29.7 vs 22), Phase C current higher than A and B, THD 8.5% (red), PF 0.73. Health tab: Valve and Intercooler bars yellow. AI hint: energy anomaly with € impact.",
        "steps": ["Switch scenario → 'Energy Anomaly'", "Energy tab → CP01: total_kw=29.7, phase_a=12A, phase_b=12A, phase_c=18A (imbalance)", "Show THD=8.5% (red), PF=0.73", "Health tab → Valve=68%, Intercooler=72%", "Ask AI → valve/intercooler diagnosis + €8,400/year impact + 7-week payback"],
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":79,"energy":"+35%_compressor","quality":99},
    },
    "multi_asset_cascade": {
        "label": "Cascade Failure — Hydraulic Leak → Quality Escape",
        "description": "PR01 hydraulic seal leak → reduced press force → underdimensioned casings → CMM vision catching 18% failure rate. AI traces the full causal chain across 4 systems.",
        "fault_key": "press_PR01_seal_leak", "affected": ["press_PR01","vision_CMM01"],
        "health_degrade": {"press_PR01": {"MainSeal": 1.5, "HydraulicPump": 0.4}},
        "ai_hint": "Causal chain: PR01 seal leak (-15 bar) → press force deviation (+80 kN) → case wall thickness out of tolerance (+0.3mm) → CMM fail rate 18% (vs 3% baseline). Root cause: PR01 MainSeal (health: 42). Fix seal → quality returns to baseline.",
        "what_it_shows": "The most powerful scenario for demonstrating AI root cause analysis across system boundaries. Quality team sees CMM failures and doesn't know why. Maintenance team sees PR01 health declining but no alarm. AI connects the dots: mechanical fault in a press → dimensional quality failure at inspection 50m down the line, 8 minutes later. Neither team would find this without cross-system AI analysis.",
        "how_to_demo": "1. Switch scenario. 2. Quality tab → CMM fail rate = 18% (baseline 3%). 3. Streams tab → filter 'press_PR01' → hydraulic_pressure_bar = 195, oil_leak_detected = true, press_force_deviation_kn = +82. 4. Health tab → MainSeal = 42% (red), HydraulicPump = 74%. 5. ERP/MES tab → quality hold active, batch hold triggered. 6. Ask AI → it traces the full causal chain from seal → force → dimension → CMM.",
        "ai_answer": "Full causal chain: (1) PR01 MainSeal degraded to 42% health → internal hydraulic leak rate ~2.1 L/min → hydraulic pressure drops from 210 to 195 bar (-15 bar = -7.1%). (2) Reduced hydraulic pressure → actuator force falls proportionally → press force at lower punch = 820 kN vs nominal 900 kN (-80 kN = -8.9% deviation). (3) Insufficient press force → incomplete material deformation → case wall thickness = 2.3mm vs nominal 2.0mm spec (+0.3mm = +15%) and corner radii out of tolerance. (4) CMM inspection catches dimensional failures: fail rate 18% vs 3% baseline. Batches affected: all units produced in last 94 minutes (approx 705 units). Affected batches: BATCH-20260417-001 units 156-861. Cost: 705 units × 15% scrap rate × €42/unit = €4,441 scrap + €8,200 rework. Total: €12,641. Fix: Replace PR01 MainSeal (4h planned stop, €280 seal kit). After fix, CMM fail rate will return to baseline within 15 min.",
        "root_cause": "PR01 MainSeal internal leakage causing insufficient press force → dimensional non-conformance propagating through production to CMM inspection.",
        "affected_streams": ["aurora/plant/L01/press_PR01/telemetry → hydraulic_pressure_bar=195, oil_leak_detected=true, press_force_deviation_kn=+82", "aurora/plant/health/press_PR01/pdm → MainSeal=42% (red)", "aurora/plant/L04/inspection_CMM01/results → fail_rate_pct=18, wall_thickness_mm=2.3", "aurora/erp/quality/holds → batch hold, 705 units affected"],
        "visual_indicators": "Quality tab: CMM fail_rate = 18% (red). Streams: PR01 hydraulic_pressure = 195, oil_leak_detected = true. Health: MainSeal red at 42%. ERP/MES: quality hold active. AI hint shows full causal chain.",
        "steps": ["Switch scenario → 'Cascade Failure'", "Quality tab → CMM fail_rate = 18%", "Streams tab → PR01: hydraulic_pressure=195, oil_leak=true, force_deviation=+82kN", "Health tab → MainSeal = 42% (red)", "ERP/MES tab → quality hold + batch hold", "Ask AI → full causal chain + €12,641 cost + fix procedure"],
        "data_sources": ["PLC","QMS","MES","ERP","AI"],
        "kpi_impact": {"oee":72,"energy":"nominal","quality":82},
    },
    "oven_thermal_runaway": {
        "label": "OV01 — Thermal Runaway (All Zones Overshoot)",
        "description": "OV01 temperature controller fault — all zones overshooting by 20-25°C. Paint on casings will be scorched. AI recommends immediate STOP and full quality assessment.",
        "fault_key": "oven_OV01_overshoot", "affected": ["oven_OV01"],
        "health_degrade": {"oven_OV01": {"Zone1Heater": 0.3, "Zone2Heater": 0.3, "Zone3Heater": 0.3}},
        "ai_hint": "All zones 20-25°C above setpoint. Exhaust temp: 98°C (normal: 85°C). STOP line immediately — paint scorch threshold exceeded. Hold all parts from last 20 min. Inspect PID controller.",
        "what_it_shows": "Safety-critical scenario demonstrating AI as a decision-support system for STOP vs CONTINUE decisions. Shows how AI can give a definitive recommendation with material science rationale — not just an alarm. MES auto-triggers batch hold, ERP fires quality hold, DPP flags every unit. AI calculates the time window of affected parts and estimates scorch damage using temperature-time exposure.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'oven_OV01' → zone_1_temp=202°C (setpoint 180), zone_2_temp=224°C (setpoint 200), zone_3_temp=193°C (setpoint 170), zone_4_temp=227°C (setpoint 200). 3. ERP/MES tab → batch_status = ON_HOLD. 4. Ask AI → immediate STOP recommendation with scorch damage calculation and PID diagnosis.",
        "ai_answer": "STOP LINE IMMEDIATELY. All four oven zones are overshooting setpoint by 20-25°C. Explanation: PID controller integral windup — likely caused by a setpoint step-change followed by sensor lag, causing I-term to accumulate. Current temps: Zone 1: 202°C (set 180, +22°C), Zone 2: 224°C (set 200, +24°C), Zone 3: 193°C (set 170, +23°C), Zone 4: 227°C (set 200, +27°C). Material impact (BAT-CASE-AL-001 with primer coat): Epoxy primer scorches at 210°C. Zone 2 and 4 are above 210°C — surface scorching confirmed. At 224°C for 6.4 min, adhesion strength of primer coat drops ~35% from baseline. Parts produced in last 18 minutes are at risk. Affected units: approx 135 units. Recommended action: (1) STOP line now, (2) Reduce all zone setpoints by 30°C immediately, (3) Wait for temp to stabilise (8 min), (4) Re-tune PID (reduce I-gain by 40%), (5) Quality hold on last 135 units, (6) Adhesion test 5 units from window. If adhesion > 85% of spec: pass. If < 85%: scrap. Estimated scrap cost: €5,670 (135 units × €42). PID fix: 20 min, no parts cost.",
        "root_cause": "PID controller integral windup on all zones simultaneously — indicates a common controller module issue, not individual heater faults. Check controller firmware or shared I/O module.",
        "affected_streams": ["aurora/plant/L03/oven_OV01/telemetry → zone_1_temp=202, zone_2_temp=224, zone_3_temp=193, zone_4_temp=227 (all above setpoint)", "aurora/mes/batch → batch_status=ON_HOLD", "aurora/erp/quality/holds → quality hold fired", "aurora/plant/L04/inspection/dpp → 135 units flagged"],
        "visual_indicators": "Streams tab: all OV01 zone temps above setpoint (red). Product flow: Curing node red. ERP/MES tab: batch ON_HOLD. AI hint: STOP recommendation with scorch threshold. OEE dropped to 68%.",
        "steps": ["Switch scenario → 'OV01 Thermal Runaway'", "Streams tab → OV01: all 4 zones above setpoint (202, 224, 193, 227°C)", "ERP/MES tab → batch ON_HOLD", "Ask AI → STOP + PID windup diagnosis + scorch damage calc + 135 units at risk"],
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":68,"energy":"+18%_oven","quality":71},
    },
    "robot_R1_weld_drift": {
        "label": "R1 — Weld Robot Teach-Point Drift",
        "description": "Robot R1 weld positions drifting 0.8mm from teach points. JointA1 and WristUnit degrading. AI detects pattern before weld failures cause scrap.",
        "fault_key": "robot_R1_position_error", "affected": ["robot_R1"],
        "health_degrade": {"robot_R1": {"JointA1": 0.6, "WristUnit": 0.9}},
        "ai_hint": "R1 position error: 0.85mm (limit 0.5mm). JointA1 health: 71% (degrading 0.6%/day). WristUnit health: 68%. Teach-point drift increasing over 72h. Recommend: recalibrate, check joint backlash, schedule bearing inspection.",
        "what_it_shows": "Slow geometric drift from mechanical wear that accumulates over days — invisible to any snapshot-based check but clearly visible in trend data. Shows predictive maintenance (PdM) in action: RUL calculated from degradation rate, specific joints identified, maintenance scheduled before weld quality degrades to causing visible defects. At 0.85mm offset, weld quality is marginal. At 1.2mm (projected 5 days), 100% of welds will be out-of-position.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'robot_R1' → position_error_mm = 0.85 (limit 0.5), joint_a1_temp elevated, path_accuracy_mm = 0.91. 3. Health tab → JointA1 = 71%, WristUnit = 68% — both declining. 4. PdM rows → R1 RUL 35 days, urgency SOON. 5. Ask AI the question → get projected failure date + quality threshold.",
        "ai_answer": "R1 teach-point drift root cause: JointA1 bearing backlash increasing due to wear (health 71%, degrading 0.6%/day) combined with WristUnit harmonic drive wear (health 68%, degrading 0.7%/day). Geometric error model: JointA1 backlash contributes ~60% of observed 0.85mm TCP error; WristUnit contributes ~40%. Current trajectory: position error increasing 0.018mm/day. Quality thresholds: (1) Weld quality marginal above 0.5mm (already exceeded — currently 70% of welds within spec). (2) Weld failures visible/scrapped above 1.2mm (projected to reach in 19 days). (3) Structural weld failure risk above 1.8mm (projected 47 days). Recommended maintenance window: within 14 days (before next planned stop). Actions: (1) Recalibrate R1 to teach points (1h, immediate improvement to 0.3mm). (2) Replace JointA1 bearings (4h, €320). (3) Replace WristUnit harmonic drive (8h, €1,850). Total: 12h + €2,170. If ignored until failure: unplanned stop 16h + scrap from 19 days of marginal welds (~€8,400). Preventive ROI: 4:1.",
        "root_cause": "JointA1 bearing backlash + WristUnit harmonic drive wear causing cumulative TCP offset. 72-hour trend confirms progressive mechanical degradation, not electrical/calibration issue.",
        "affected_streams": ["aurora/plant/L01/robot_R1/telemetry → position_error_mm=0.85, path_accuracy_mm=0.91, joint_a1_temp elevated", "aurora/plant/health/robot_R1/pdm → JointA1=71%, WristUnit=68%, RUL=35days", "aurora/plant/qms/weld_inspection → pass_rate declining"],
        "visual_indicators": "Streams tab: R1 position_error_mm = 0.85 (above 0.5 limit, orange). Health tab: JointA1 and WristUnit bars yellow/declining. PdM table: R1 RUL = 35 days, urgency = SOON. Quality tab: weld pass rate trending down.",
        "steps": ["Switch scenario → 'R1 Weld Robot Drift'", "Streams tab → R1: position_error_mm=0.85, path_accuracy=0.91", "Health tab → JointA1=71%, WristUnit=68%", "PdM table → R1 RUL 35d, SOON", "Ask AI → bearing backlash + harmonic drive diagnosis + 19-day quality failure window + 4:1 ROI"],
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":78,"energy":"nominal","quality":94},
    },
    "compressed_air_leak": {
        "label": "Compressed Air Leak — Network Pressure Drop",
        "description": "Air network pressure drop 15% detected. Compressor running at 95% load continuously to compensate. Estimated leak 4.2 m³/h. Energy waste and quality risk to pneumatic tools.",
        "fault_key": "compressed_air_leak", "affected": ["compressor_CP01"],
        "health_degrade": {"compressor_CP01": {"AirFilter": 0.4}},
        "ai_hint": "Header pressure: 6.38 bar vs 7.5 nominal (-15%). Compressor loaded 95% (normal 72%). Leak estimated 4.2 m³/h. Annual energy cost: ~€3,200. Compressor RUL reduced 40% from continuous operation. Locate with ultrasonic detector in Zone A.",
        "what_it_shows": "Invisible utility waste that standard monitoring completely misses. Compressed air leaks are the #1 energy waste in manufacturing — typically 20-30% of compressed air is lost to leaks. AI correlates: CP01 load% increase + Zone A pressure differential + flow imbalance to pinpoint the leak location and quantify the financial and equipment impact. The compressor running at 95% vs 72% is silently destroying bearing life.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'compressor_CP01' → loaded_pct = 95 (normal 72), outlet_pressure_bar = 6.38 (normal 7.5). 3. Filter 'air_network' → zone_a_press = 6.1 bar vs zone_b_press = 7.1, zone_c_press = 7.2, leak_detected = true. 4. Energy tab → CP01 excess kW visible. 5. Health tab → CP01 AirFilter at 48%. 6. Ask AI → leak location + annual cost + compressor life impact.",
        "ai_answer": "Compressed air leak confirmed in Zone A. Evidence: Zone A pressure 6.1 bar vs Zone B 7.1 bar and Zone C 7.2 bar — 1.0 bar differential pointing to a downstream Zone A leak. Compressor CP01 loaded 95% vs baseline 72% to compensate, consuming 4.2 kW excess power. Leak flow rate estimate: using compressor excess capacity vs pressure drop model → 4.2 m³/h leak. Annual energy cost: 4.2 kW × 8,760h × €0.14/kWh = €5,148 but applying compressor efficiency factor (75%): actual = 4.2 m³/h ÷ 4.8 m³/kWh = 0.875 kW compressor extra × 8,760 × €0.14 = €1,073 electricity + compressor maintenance uplift (95% load vs 72% reduces MTBF by ~40%: if next bearing service was 18 months away, now 11 months: cost brings forward ~€2,100). Total annual impact: ~€3,200. Leak location: Zone A, most likely at a push-fit connector or valve bank (highest frequency in pneumatic distribution). Detection: walk Zone A piping with ultrasonic detector (Fluke ii910) — leak signature 40 kHz. Typical repair: replace Ø8mm push-fit connector, 15 min, €2.80. ROI: immediate.",
        "root_cause": "Compressed air leak in Zone A distribution network — most likely push-fit connector or solenoid valve exhaust port failure. Compressor overloading to compensate.",
        "affected_streams": ["aurora/plant/energy/CP01/power → loaded_pct=95, outlet_pressure_bar=6.38", "aurora/plant/air_network → zone_a_press=6.1 (low vs B=7.1, C=7.2), leak_detected=true, total_flow_m3h=37 (vs 28.5 nominal)", "aurora/plant/health/compressor_CP01/pdm → AirFilter=48%, CP01 RUL reduced"],
        "visual_indicators": "Streams tab: CP01 loaded_pct = 95 (orange), outlet_pressure = 6.38 (below 7.5 nominal). Air network: zone_a_press lower than B and C (red differential). Energy tab: CP01 excess kW. AI hint: leak location Zone A + annual cost.",
        "steps": ["Switch scenario → 'Compressed Air Leak'", "Streams tab → CP01: loaded_pct=95, outlet_pressure=6.38", "Air network streams: zone_a=6.1 vs zone_b=7.1 (pressure differential)", "Energy tab → CP01 excess kW visible", "Ask AI → Zone A leak, 4.2 m³/h, €3,200/year, ultrasonic detection procedure"],
        "data_sources": ["PLC","SCADA","AI"],
        "kpi_impact": {"oee":79,"energy":"+22%_compressor","quality":99},
    },
    "tooling_die_wear": {
        "label": "PR01 Die Wear — Dimensional Drift from Tooling",
        "description": "PR01 die at 420,000 cycles (70% of 600,000 limit). Die temp rising, press force deviation increasing. SPC Cpk falling. AI predicts quality escape intersection point.",
        "fault_key": "press_PR01_die_wear", "affected": ["press_PR01","vision_CMM01"],
        "health_degrade": {"press_PR01": {"Die": 1.8}},
        "ai_hint": "PR01 die at 70% life (420K/600K cycles). Die temp: 63°C vs 38°C nominal (+66%). Press force deviation: +3.2%. Wall thickness SPC Cpk 0.82 (limit 1.33). Schedule die change within 24h to prevent quality escape.",
        "what_it_shows": "Planned maintenance vs reactive repair — and the AI's ability to predict exactly when preventive action is needed before quality goes out of spec. Classic predictive tooling lifecycle management: cycle count, temperature, force deviation, and SPC Cpk all feeding an AI model that calculates the remaining useful life in hours, not vague percentages. The insight: Cpk = 1.33 is the quality escape boundary — AI finds exactly when the die wear curve intersects it.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'press_PR01' → die_wear_pct = 70%, die_temp_c = 63 (nominal 38), press_force_deviation_pct = +3.2. 3. Quality tab → SPC chart for wall_thickness — Cpk = 0.82 (limit 1.33), trending upward. 4. Health tab → Die component bar at 30% (red). 5. Ask AI → intersection point and recommended die change window.",
        "ai_answer": "PR01 die wear analysis: Current state: 420,000 cycles completed (70% of 600,000 limit). Die temperature 63°C vs 38°C nominal (+66%) — elevated temp indicates reduced clearance from thermal expansion due to die surface oxidation and micro-cracking. Press force deviation +3.2%: as die wears, more force required to achieve same deformation. SPC trajectory: wall_thickness Cpk = 0.82 currently, decreasing at -0.028 Cpk per 10,000 cycles over last 60,000 cycles. Quality escape threshold: Cpk < 1.33 means process is marginally capable; Cpk < 1.0 means defects are likely. Current Cpk 0.82 means ~2.3% of parts are already outside ±3σ (but within tolerance). Quality escape (Cpk < 0.67, 4.5% defect rate) projected at: ~470,000 cycles (50,000 cycles away at 7.5 cycles/min = 111 hours = 4.6 production shifts). Recommended die change window: within next 2 shifts (before 460,000 cycles). Die change: 2h planned stop, €4,200 die set. Cost of reactive failure (CMM catching 4.5%+ defects, scrap/rework, unplanned stop): €18,000+. Preventive ROI: >4:1.",
        "root_cause": "Normal die wear at 70% of service life. Elevated temperature indicates surface oxidation accelerating wear. SPC Cpk declining confirms dimensional drift toward tolerance limit.",
        "affected_streams": ["aurora/plant/L01/press_PR01/telemetry → die_wear_pct=70, die_temp_c=63, press_force_deviation_pct=+3.2, cycle_count=420000", "aurora/plant/qms/spc → wall_thickness Cpk=0.82 (trending down)", "aurora/plant/health/press_PR01/pdm → Die=30% (red), RUL=111h"],
        "visual_indicators": "Streams tab: PR01 die_wear_pct = 70%, die_temp = 63°C (orange). Quality tab: wall_thickness SPC Cpk = 0.82 (below 1.33 limit, red). Health tab: Die bar red at 30%. AI hint: die change within 24h.",
        "steps": ["Switch scenario → 'PR01 Die Wear'", "Streams tab → PR01: die_wear_pct=70, die_temp=63°C, force_deviation=+3.2%", "Quality tab → wall_thickness SPC: Cpk=0.82 (red, below 1.33)", "Health tab → Die = 30% (red)", "Ask AI → quality escape at 470K cycles = 111 hours, schedule die change within 2 shifts"],
        "data_sources": ["PLC","QMS","MES","AI"],
        "kpi_impact": {"oee":77,"energy":"nominal","quality":95},
    },
    "robot_R3_spray_drift": {
        "label": "R3 — Spray Robot TCP Drift (Paint Quality Impact)",
        "description": "Paint robot R3 tool-centre-point drifting 0.72mm. Coat thickness falling from 80µm to 52µm. Coat uniformity 72% (min 90%). MES catching yield drop.",
        "fault_key": "robot_R3_spray_drift", "affected": ["robot_R3","sprayer_SP01","sprayer_SP02"],
        "health_degrade": {"robot_R3": {"TCP_Calibration": 2.0, "JointA2": 0.5}},
        "ai_hint": "R3 TCP offset: 0.72mm (limit 0.3mm). Coat thickness: 52µm (min 60µm). Uniformity: 72% (min 90%). Spray overlap incorrect. Recalibrate R3 TCP, verify gun-to-part distance. Quality hold on last 35 min.",
        "what_it_shows": "Process quality monitoring beyond threshold alarms — AI correlating robot kinematics with coating quality outcomes. The TCP drift is invisible unless you measure position accuracy. The coat thickness drop is measurable but its cause isn't obvious from the coating data alone. AI connects: R3 JointA2 wear → TCP drift → spray pattern offset → coat thickness thin zones → uniformity failure. Quantifies the affected production window and gives a step-by-step recalibration procedure.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'robot_R3' → position_error_mm = 0.72 (limit 0.3), path_accuracy = 0.65, joint_a2_temp elevated. 3. Filter 'sprayer' → coat_thickness_um = 52 (minimum 60), coat_uniformity_pct = 72 (minimum 90). 4. Health tab → R3 TCP_Calibration = 45% (red), JointA2 = 78%. 5. Ask AI → root cause + affected parts count + recalibration steps.",
        "ai_answer": "Root cause: R3 JointA2 harmonic drive backlash (health 78%) causing TCP offset of 0.72mm (limit 0.3mm). With TCP offset, the spray gun is not maintaining constant gun-to-part distance. At 0.72mm offset and typical gun-to-part distance 250mm, the offset represents a 0.29% angle change — which shifts the spray centre by 3.2mm at the part surface. This moves ~20% of spray pattern off the target zone, creating thin coating areas. Effect: coat thickness drops from 80µm nominal to 52µm average in offset zones. Coat uniformity 72% (min 90%) because half the surface receives correct thickness but offset zones are thin. Affected production window: last 35 minutes (R3 TCP drift gradual, reached limit 35 min ago). Affected parts: 263 units. All have thin-coat zones on the battery casing lid panel — this area is exposed to humidity cycling, so thin coat = corrosion risk. Quality hold recommendation: last 35 min of output. Disposition: re-spray at 30µm build coat + cure (30 min). Cost: 263 units × €8 rework = €2,104 vs €11,046 scrap. Recalibration procedure: (1) Run R3 TCP calibration routine from teach pendant (menu: Utilities → TCP Calibration → Auto), 8 min. (2) Verify with calibration sphere measurement — target < 0.15mm. (3) If > 0.15mm after auto-cal, replace JointA2 harmonic drive (6h, €1,420). Current TCP cal procedure will reduce to 0.18mm — borderline, schedule JointA2 replacement within 5 days.",
        "root_cause": "R3 JointA2 harmonic drive backlash causing TCP drift. TCP offset of 0.72mm shifts spray pattern 3.2mm at part surface, creating thin-coat zones.",
        "affected_streams": ["aurora/plant/L02/robot_R3/telemetry → position_error_mm=0.72, path_accuracy=0.65, joint_a2_temp elevated", "aurora/plant/L02/sprayer_SP01/telemetry → coat_thickness_um=52, coat_uniformity_pct=72", "aurora/plant/health/robot_R3/pdm → TCP_Calibration=45% (red), JointA2=78%"],
        "visual_indicators": "Streams tab: R3 position_error_mm = 0.72 (red, above 0.3 limit). Sprayer streams: coat_thickness_um = 52 (below 60 min, red), coat_uniformity = 72% (below 90%, red). Health tab: TCP_Calibration bar red at 45%.",
        "steps": ["Switch scenario → 'R3 Spray Robot TCP Drift'", "Streams tab → R3: position_error=0.72, path_accuracy=0.65", "Sprayer streams: coat_thickness=52µm (min 60), uniformity=72% (min 90%)", "Health tab → TCP_Calibration=45% (red)", "Ask AI → JointA2 backlash diagnosis + 263 parts affected + TCP recal steps + €2,104 rework vs €11,046 scrap"],
        "data_sources": ["PLC","QMS","MES","AI"],
        "kpi_impact": {"oee":76,"energy":"nominal","quality":83},
    },
    "erp_material_shortage": {
        "label": "ERP Alert — ALU Sheet Material Shortage",
        "description": "SAP ERP signals ALU_SHEET_2MM below safety stock (500 kg). MES halts new work orders. Press lines will be starved in ~47 min. Shows ERP-to-MES-to-OT integration.",
        "fault_key": "erp_material_shortage", "affected": ["press_PR01","press_PR02"],
        "health_degrade": {},
        "ai_hint": "ALU_SHEET_2MM: 387 kg (safety stock 500 kg). Consumption: 8.25 kg/min. Starvation in 47 min. Options: (1) Expedite PO — 4h lead time. (2) Reduce line rate to 3.7 units/min — extends window to 95 min. (3) Switch to PR02 only — doubles window.",
        "what_it_shows": "ISA-95 integration from L4 (ERP/SAP) down through L3 (MES) to L2 (PLC production rates) — visible in real-time in the UNS. Shows that a business planning event (stock below safety level) immediately ripples into shopfloor visibility: MES halts new work orders, press lines see their operational_status change, and the AI calculates exactly how many minutes remain before physical starvation. Most factories don't have this integration — showing it live is impactful.",
        "how_to_demo": "1. Switch scenario. 2. ERP/MES tab → ERP: ALU_SHEET_2MM = 387 kg (safety stock 500 kg), alert_active = true. 3. MES work orders → status = WAITING_MATERIAL for next WO. 4. Streams tab → filter 'press_PR01' → operational_status = 'Running' (currently OK), show consumption rate. 5. Ask AI → starvation time + 3 options with time/cost impact.",
        "ai_answer": "Material shortage analysis: ALU_SHEET_2MM current stock = 387 kg vs safety stock level 500 kg (ERP trigger at 500 kg, physical starvation at 0 kg). Consumption rate: 1.1 kg/unit × 7.5 units/min = 8.25 kg/min total (both press lines). Time to physical starvation: 387 kg ÷ 8.25 kg/min = 46.9 minutes from now. MES has already blocked new work order creation — current WO will complete before starvation, but no subsequent WO can start. Option analysis: (1) EXPEDITE PO: Supplier Franz Metals lead time 4 hours. Gap = 4h × 8.25 kg/min × 60 = 1,980 kg gap. Not viable without alternative source. (2) REDUCE LINE RATE to 3.7 units/min (50% production rate): consumption drops to 4.07 kg/min, extends window to 95 min. Lost production: 217 units × €42 = €9,114 (opportunity cost). (3) RUN PR02 ONLY (shut down PR01): consumption 4.07 kg/min (one press), extends to 95 min, PR02 can produce 3.7 units/min. PR01 downtime cost: €210/min for 48 min = €10,080. (4) CHECK ALTERNATIVE MATERIAL: ALU_SHEET_2.2MM in stock (680 kg) — compatible with 94% of order items, requires PR01 tooling adjustment (25 min). Recommended: Option 4 — switch to ALU_SHEET_2.2MM immediately, schedule express delivery for ALU_SHEET_2MM. Call supplier contact: Franz Metals logistics +49 89 4521-0, ref PO-2026-0312.",
        "root_cause": "Material stock fell below safety level due to consumption spike from BMW-GROUP-DE order (150% of normal volume) combined with supplier delivery delay (expected yesterday, now 4h late).",
        "affected_streams": ["aurora/erp/materials/ALU_SHEET_2MM → stock_kg=387, safety_stock=500, alert_active=true", "aurora/mes/workorder → status=WAITING_MATERIAL, next WO blocked", "aurora/erp/production/production_order → material_alert=true, completion_pct frozen", "aurora/plant/L01/press_PR01/performance → operational_status=Running (countdown active)"],
        "visual_indicators": "ERP/MES tab: ALU_SHEET_2MM = 387 kg (below safety 500 kg, orange alert). MES work order: status = WAITING_MATERIAL. OEE header: dropping as lines slow. AI hint: 47 min to starvation + 4 options.",
        "steps": ["Switch scenario → 'ERP Material Shortage'", "ERP/MES tab → ALU_SHEET_2MM: 387 kg, alert active, safety stock 500 kg", "MES WO status = WAITING_MATERIAL", "Streams tab → PR01/PR02 operational_status (still Running, countdown active)", "Ask AI → 47-min window + 4 options with costs + recommend ALU_SHEET_2.2MM substitution"],
        "data_sources": ["ERP","MES","PLC","AI"],
        "kpi_impact": {"oee":62,"energy":"reduced_presses","quality":99},
    },
    "quality_escape": {
        "label": "Quality Escape — CMM Defect Rate 18% (Multi-Variate Root Cause)",
        "description": "CMM inspection defect rate jumped from 3% to 18%. No single alarm fired. AI correlates press force, die wear, and oven data to find the multi-variate root cause. MES triggers batch hold.",
        "fault_key": "quality_escape", "affected": ["press_PR01","vision_CMM01"],
        "health_degrade": {"press_PR01": {"Die": 1.2}, "vision_CMM01": {"CalibTarget": 0.8}},
        "ai_hint": "CMM fail rate 18% (baseline 3%). No single alarm fired. PR01 force deviation +4.1%, oven zone 3 +8°C, die wear 72%. Combined effect exceeds tolerance. Hold batch, adjust PR01 force and oven zone 3 setpoint.",
        "what_it_shows": "The best scenario for demonstrating AI reasoning value vs SCADA alarm rules. No single sensor is alarming. Quality team sees 18% CMM failures and has no explanation from the SCADA system. AI analyses 111 streams and finds three contributing factors that individually are within limits but collectively push quality out of spec. This is exactly where AI delivers value that no rule-based system can replicate.",
        "how_to_demo": "1. Switch scenario. 2. Quality tab → CMM fail_rate = 18% (baseline 3%). 3. Streams tab → PR01: press_force_deviation = +4.1% (alarm limit 8% — no alarm). 4. Oven streams → zone_3_temp = +8°C above setpoint (alarm limit 15°C — no alarm). 5. Health tab → PR01 Die = 28% (red), CMM01 CalibTarget = 72%. 6. Ask AI → multi-variate root cause analysis. This is the key scenario for showing AI > SCADA.",
        "ai_answer": "Multi-variate root cause analysis: Three sub-threshold factors combining to cause quality escape. Factor 1 — PR01 die wear (72% life, health 28%): Die dimensional increase of +0.15mm from wear = wall thickness bias of +0.15mm. Individually within tolerance band (±0.3mm). Factor 2 — PR01 press force deviation +4.1%: Force deviation adds compressive variability. At +4.1% force, spring-back variation increases by ±0.08mm. Adds to die wear effect. Factor 3 — OV01 zone 3 +8°C overshoot: Elevated cure temperature reduces material hardness slightly (+0.4% elongation), increasing dimensional variability during ejection by ±0.07mm. Combined effect: +0.15mm (die) + ±0.08mm (force) + ±0.07mm (oven) = worst case +0.30mm bias plus ±0.15mm variability. Nominal tolerance ±0.25mm, so cumulative effect = Cpk 0.79, defect rate 18%. Each factor alone: Cpk 1.35, 1.42, 1.45 (all acceptable). Combined: Cpk 0.79 (unacceptable). Fix: (1) Adjust PR01 force -2% (corrects spring-back), (2) Reduce OV01 zone 3 setpoint by 6°C, (3) Schedule die change within 2 shifts (as per tooling scenario). After adjustments 1 and 2: Cpk returns to ~1.1 (defect rate ~0.8%). Die change restores to 1.33 baseline. Hold current batch (BATCH-20260417-001). Recommend CMM 100% inspection of last 4 hours production (~1,800 units) — expect ~324 failures for rework.",
        "root_cause": "Three sub-threshold factors combining: PR01 die wear (+0.15mm bias) + force deviation (+4.1%, adds variability) + oven zone 3 overshoot (+8°C, increases ejection variation). No single factor would cause quality escape alone.",
        "affected_streams": ["aurora/plant/L04/inspection_CMM01/results → fail_rate_pct=18 (baseline 3%)", "aurora/plant/L01/press_PR01/telemetry → press_force_deviation_pct=+4.1 (below 8% alarm)", "aurora/plant/L03/oven_OV01/telemetry → zone_3_temp = +8°C above setpoint (below 15°C alarm)", "aurora/plant/health/press_PR01/pdm → Die=28%", "aurora/mes/batch → batch_status=ON_HOLD"],
        "visual_indicators": "Quality tab: CMM fail_rate = 18% (red). Streams: PR01 force +4.1% (below alarm, no red!). OV01 zone 3 +8°C (below alarm, no red!). Health: Die=28% (red). ERP/MES: batch ON_HOLD. This is the key visual: nothing individual is alarming, but quality is failing.",
        "steps": ["Switch scenario → 'Quality Escape'", "Quality tab → CMM fail_rate = 18% (nobody knows why)", "Streams tab → PR01 force deviation = +4.1% (no alarm), oven zone 3 = +8°C (no alarm)", "Health tab → PR01 Die = 28% (red)", "Ask AI → 3-factor root cause + Cpk calculation + fix: -2% force + -6°C oven + die change"],
        "data_sources": ["PLC","QMS","MES","ERP","AI"],
        "kpi_impact": {"oee":71,"energy":"nominal","quality":82},
    },
    "agv_charging_fault": {
        "label": "AGV Fleet — Battery Low / Charging Station Fault",
        "description": "AGV-04 battery critically low (8%). Charging station CS-02 offline (contactor fault). Nearest available station CS-01 is in use. Line 2 material delivery at risk in 12 min.",
        "fault_key": "compressor_CP01_overload", "affected": ["conveyor_CV03"],
        "health_degrade": {},
        "ai_hint": "AGV-04 SoC = 8% (min 15%). CS-02 offline (contactor fault E-CHRG-002). CS-01 occupied by AGV-02. Reroute AGV-03 to cover paint line delivery. Estimated line starvation: 12 min.",
        "what_it_shows": "Fleet coordination logic: a single charging station fault triggers a cascading availability problem across the AGV fleet. Shows how UNS visibility of both equipment state (charging stations) and logistics assets (AGVs) allows AI to compute the shortest reroute path before a physical starvation event occurs. Without this integration, the operator discovers the problem only when Line 2 stops.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → filter 'rfid' → show AGV-04 last RFID ping at Line 2 entry. 3. ERP/MES tab → show material delivery schedule — Line 2 paint supply overdue 8 min. 4. Ask AI → reroute recommendation with time-to-starvation and charging sequence.",
        "ai_answer": "AGV-04 SoC critically low at 8% (operational minimum 15%). Route analysis: AGV-04 is 340m from CS-01 (2.4 min at 2.4 m/s) but CS-01 is occupied by AGV-02 (charging since 08:12, expected free at 08:31 — 14 min from now). CS-02 offline: contactor E-CHRG-002 fault (requires maintenance, ETA unknown). Starvation risk: Line 2 paint supply (SP01/SP02) requires material replenishment in 12 min. AGV-04 has exactly 8% SoC = ~6 min remaining runtime at 80% load — will stop before completing delivery. Recommended reroute: dispatch AGV-03 (SoC 67%, currently idle at staging) to Line 2 paint supply route immediately. AGV-03 ETA to pick-up: 3.1 min, ETA to Line 2 delivery: 8.4 min — within the 12-min window. Sequence: (1) Dispatch AGV-03 to Line 2 paint route now. (2) Direct AGV-04 to CS-01 queue (wait 14 min) — low priority as AGV-03 covers the route. (3) Raise maintenance WO for CS-02 contactor fault (2h, €85 part). (4) Schedule AGV-02 off-charge at CS-01 in 6 min (SoC will be 78%, sufficient for 4 delivery cycles) — free CS-01 for AGV-04. Production impact: zero if AGV-03 dispatched within next 90 seconds.",
        "root_cause": "CS-02 contactor fault (electrical failure) coinciding with AGV-04 low battery at peak delivery demand. AGV-02 occupying CS-01 creating simultaneous station unavailability.",
        "affected_streams": ["aurora/plant/L02/conveyor_CV03/telemetry → material_level_pct dropping", "aurora/plant/rfid → AGV-04 last seen Line 2 entry 8 min ago", "aurora/erp/materials → paint supply delivery overdue"],
        "visual_indicators": "Feed tab: RFID last AGV-04 ping >8 min ago. ERP/MES: material delivery overdue. Conveyor CV03 speed nominal but material buffer timer counting down. AI hint: 12-min starvation window.",
        "steps": ["Switch scenario", "Feed tab → AGV-04 RFID last seen 8 min ago", "ERP/MES → paint delivery overdue", "Ask AI → reroute AGV-03 in <90s to avoid zero production impact"],
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":75,"energy":"nominal","quality":99},
    },
    "product_changeover": {
        "label": "Product Changeover — BAT-CASE-AL-001 → BAT-CASE-AL-002 (XL)",
        "description": "Planned changeover from standard EV case to XL variant. PR01/PR02 tooling change, oven ramp to 210°C, paint recipe swap, CMM program change. MES sequences all steps. Shows ISA-95 L3/L4 coordination.",
        "fault_key": None, "affected": ["press_PR01","press_PR02","oven_OV01","sprayer_SP01","sprayer_SP02","vision_CMM01"],
        "health_degrade": {},
        "ai_hint": "Changeover in progress: BAT-CASE-AL-001 → BAT-CASE-AL-002. Estimated OTIF: 47 min (target 40 min). Critical path: oven zone 3 ramp (18 min remaining). PR01/PR02 tooling complete. Paint recipe loaded. CMM program change pending.",
        "what_it_shows": "ISA-95 Level 3→2 coordination for product changeover — ERP releases a new production order, MES creates work orders and sequences changeover steps, PLC assets execute parameter changes. Shows the UNS as the integration fabric that makes every changeover step visible to every system simultaneously. The AI optimises the changeover sequence and tracks against the target OTIF (On-Time-In-Full) changeover time.",
        "how_to_demo": "1. Switch scenario. 2. ERP/MES tab → show new production order BAT-CASE-AL-002 released, changeover work order WO-CO-001 active. 3. Streams tab → PR01: operational_status = CHANGEOVER, die_change_complete = true. 4. OV01 → zone_3_setpoint changing from 200°C to 210°C, ramp_in_progress = true. 5. Ask AI → critical path analysis + OEE impact of changeover duration.",
        "ai_answer": "Changeover sequence analysis: BAT-CASE-AL-001 → BAT-CASE-AL-002 (XL case, 15% larger draw depth). Parallel sequence status: (1) PR01 die change: COMPLETE (18 min, target 15 min, +3 min late). (2) PR02 die change: COMPLETE (16 min, on time). (3) PR01/PR02 force setpoint update: COMPLETE (2 min automated via MES). (4) Paint recipe: COMPLETE — SP01/SP02 flushed and loaded Recipe R-002 (8 min). (5) OV01 zone temperature ramp: IN PROGRESS — Zone 1 180→190°C (12 of 18 min), Zone 2 200°C (no change), Zone 3 170→210°C (12 of 24 min — CRITICAL PATH). Zone 3 ramp rate: 2.1°C/min, remaining delta: 21°C ÷ 2.1°C/min = 10 min remaining. (6) CMM program change: PENDING — requires operator confirmation (currently unassigned — AI flag). Bottleneck: Zone 3 ramp (10 min) is critical path. CMM program change not started — if not started in next 3 min, will extend changeover by 7 min. Projected changeover completion: 57 min vs 40-min target (17 min overrun). OEE impact: 57 min downtime ÷ 480 min shift = -11.9% OEE. Each minute saved in changeover = +0.2% shift OEE = +€42 value. Immediate actions: (1) Assign operator to CMM program change NOW — saves 7 min. (2) Notify supervisor of 17-min overrun vs target. (3) After changeover complete, MES auto-releases first production job for BAT-CASE-AL-002 (100 unit qualification run).",
        "root_cause": "Planned changeover event. Overrun caused by PR01 die change +3 min late + CMM program change unassigned. Zone 3 oven ramp is expected critical path.",
        "affected_streams": ["aurora/mes/batch → changeover WO active, product=BAT-CASE-AL-002", "aurora/plant/L01/press_PR01/telemetry → operational_status=CHANGEOVER", "aurora/plant/L03/oven_OV01/telemetry → zone_3 ramp in progress", "aurora/erp/production_orders → new order released"],
        "visual_indicators": "ERP/MES tab: changeover WO active. Streams: PR01 operational_status=CHANGEOVER. OV01 zone 3 setpoint changing. Product flow shows changeover in progress. AI hint: critical path + overrun warning.",
        "steps": ["Switch scenario → 'Product Changeover'", "ERP/MES tab → changeover WO, new product order", "Streams tab → PR01: operational_status=CHANGEOVER, OV01: zone_3 ramp", "Ask AI → critical path (zone 3 ramp + CMM unassigned) + 17-min overrun + assign CMM operator now"],
        "data_sources": ["PLC","MES","ERP","AI"],
        "kpi_impact": {"oee":68,"energy":"transition","quality":100},
    },
    "batch_quality_hold": {
        "label": "Batch Quality Hold — Automated MES + ERP + DPP Integration",
        "description": "MES automatically places batch on hold due to oven zone 2 deviation. ERP updates production order. DPP flags all 156 units. Shows full integration stack working automatically.",
        "fault_key": "batch_quality_hold", "affected": ["oven_OV01"],
        "health_degrade": {"oven_OV01": {"Zone2Heater": 1.0}},
        "ai_hint": "Batch BATCH-20260417-001 on hold. 156 units in affected window. Zone 2 deviated -45°C for 22 min. Cure deficiency 23%. Recommend: destructive test 3 units, then decide scrap vs re-cure.",
        "what_it_shows": "The integration story: a single OT sensor event (zone 2 temp deviation) automatically cascades through MES → ERP → DPP with zero human intervention. Every system is updated. Every affected unit is digitally flagged. The AI then provides the disposition recommendation that would normally take a quality engineer 2 hours to compute. Shows the full value of a connected, integrated manufacturing stack.",
        "how_to_demo": "1. Switch scenario. 2. Streams tab → OV01 → zone_2_temp_c = 155°C (setpoint 200, deviation -45°C). 3. ERP/MES tab → batch_status = ON_HOLD, quality_hold_active = true, hold_units = 156. 4. Feed tab (Messages) → show automatic events: MES batch hold, ERP quality document, DPP unit flags all firing in sequence. 5. Ask AI → cure deficiency calculation + disposition recommendation.",
        "ai_answer": "Batch disposition analysis for BATCH-20260417-001: Zone 2 temperature deviation: -45°C from setpoint (200°C → 155°C) for estimated 22 minutes. Cure chemistry analysis (epoxy-based primer, BAT-CASE-AL-001): Minimum cure temperature 180°C. Zone 2 was at 155°C — 25°C below minimum. Using Arrhenius kinetics with activation energy Ea = 75 kJ/mol, cure rate at 155°C is 42% of rate at 200°C. Effective cure time at 155°C: 22 min × 42% = 9.2 equivalent minutes vs required 6.4 min per zone. Wait — 9.2 > 6.4: parts actually PASSED the minimum cure requirement, but with only 44% margin vs normal 100% margin. Revised assessment: parts are cured but with reduced margin. Actual risk: reduced adhesion strength (estimated -15% vs spec). Recommendation: (1) Destructive test 3 units from affected window: peel adhesion test (EN ISO 2409) — accept if result ≥ Grade 1. (2) If pass: release batch with notation in DPP. (3) If fail: re-cure at 210°C for 4 min in secondary oven. Cost of re-cure: 156 units × €3.50/unit = €546. Cost of scrap: 156 × €42 = €6,552. Recommendation: re-cure is cost-effective. Complete repair and update DPP unit records to show secondary cure operation.",
        "root_cause": "OV01 Zone 2 heater element at end of life (health 48%). Partial failure causing temperature to drop to 155°C from 200°C setpoint. Element approaching open-circuit failure.",
        "affected_streams": ["aurora/plant/L03/oven_OV01/telemetry → zone_2_temp_c=155 (setpoint 200, deviation -45°C)", "aurora/mes/batch/BATCH-20260417-001 → batch_status=ON_HOLD, units_held=156", "aurora/erp/quality/holds → hold_id active, production_order updated", "aurora/plant/L04/inspection/dpp → 156 units flagged with hold_reason"],
        "visual_indicators": "Streams: OV01 zone_2_temp = 155°C (below 200 setpoint, yellow-red). ERP/MES tab: batch ON_HOLD, 156 units. Feed tab: automatic integration events firing in sequence. DPP / Product Flow: Curing node shows hold status. AI hint: cure analysis + re-cure recommendation.",
        "steps": ["Switch scenario → 'Batch Quality Hold'", "Streams tab → OV01: zone_2_temp=155°C (deviation -45°C from 200°C setpoint)", "ERP/MES tab → batch ON_HOLD, 156 units affected", "Feed tab → watch automatic MES→ERP→DPP event cascade", "Ask AI → Arrhenius cure calc → parts are technically cured → re-cure at 210°C for €546 vs scrap €6,552"],
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
