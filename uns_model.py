"""
UNS Data Model -- IoTAuto GmbH
Three plants: Frankfurt Paint Shop, Munich Assembly, Ingolstadt Press+Body Shop
ISA-95 hierarchy | PLC / MES / ERP / SCADA sources
"""
import math, random, time
from collections import deque

# ── Shared colour maps used by the UI ────────────────────────────────────────
LOCATION_COLORS = {"Frankfurt": "#3b82f6", "Munich": "#8b5cf6", "Ingolstadt": "#f59e0b"}
SOURCE_COLORS   = {"PLC": "#3b82f6", "MES": "#8b5cf6", "ERP": "#f59e0b", "SCADA": "#10b981"}

# ── Stateful sensor generator ─────────────────────────────────────────────────
class SensorGen:
    """Gaussian noise + Brownian drift + sinusoidal thermal + wear index + fault injection."""
    def __init__(self, nominal, noise, drift_rate=0.0, thermal_amp=0.0,
                 thermal_period=3600, spec_min=None, spec_max=None,
                 alarm_lo=None, alarm_hi=None, unit="", source="PLC",
                 source_hw="", plc_tag="", scan_ms=100, fault_key=None,
                 fault_value=None, fault_bias=0.0, wear_rate=0.0):
        self.nominal = nominal
        self.noise = noise
        self.drift_rate = drift_rate
        self.thermal_amp = thermal_amp
        self.thermal_period = thermal_period
        self.spec_min = spec_min if spec_min is not None else nominal * 0.8
        self.spec_max = spec_max if spec_max is not None else nominal * 1.2
        self.alarm_lo = alarm_lo if alarm_lo is not None else self.spec_min * 0.9
        self.alarm_hi = alarm_hi if alarm_hi is not None else self.spec_max * 1.1
        self.unit = unit
        self.source = source
        self.source_hw = source_hw
        self.plc_tag = plc_tag
        self.scan_ms = scan_ms
        self.fault_key = fault_key
        self.fault_value = fault_value
        self.fault_bias = fault_bias
        self.wear_rate = wear_rate
        self._nominal0 = nominal          # keep original for reset
        self._val = nominal
        self._drift = 0.0
        self._wear = 0.0
        self._samples = deque(maxlen=60)   # O(1) append+pop, bounded
        self._start = time.time()

    def _reset(self):
        """Restore generator to fresh state so each demo starts clean."""
        self._val     = self._nominal0
        self._drift   = 0.0
        self._wear    = 0.0
        self._samples.clear()
        self._start   = time.time()

    def __call__(self, shared):
        now = time.time()
        fault = shared.get("fault")
        shift = shared.get("shift", "A")
        active_fault = self.fault_key and fault == self.fault_key

        # Wear accumulation
        self._wear = min(1.0, self._wear + self.wear_rate * 0.001)

        # Brownian drift
        self._drift += random.gauss(0, self.drift_rate * 0.1)
        self._drift *= 0.995  # mean-revert

        # Thermal cycle
        thermal = self.thermal_amp * math.sin(
            2 * math.pi * (now % self.thermal_period) / self.thermal_period
        )

        # Shift warmup
        warmup = 1.0 + (0.03 if shift == "A" else 0.0)

        # Fault bias
        bias = self.fault_bias if active_fault else 0.0

        prev = self._val
        raw = (self.nominal * warmup + self._drift + thermal + bias
               + random.gauss(0, self.noise + self._wear * self.noise * 2))

        if active_fault and self.fault_value is not None:
            raw = self.fault_value + random.gauss(0, self.noise * 0.3)

        self._val = raw
        self._samples.append(raw)   # deque(maxlen=60) auto-evicts oldest

        mean   = sum(self._samples) / len(self._samples)
        stddev = (sum((x - mean) ** 2 for x in self._samples) / len(self._samples)) ** 0.5
        smin   = min(self._samples)
        smax   = max(self._samples)
        sigma  = (raw - mean) / stddev if stddev > 0 else 0

        v = round(raw, 3)

        # Status
        if   v > self.alarm_hi or v < self.alarm_lo: status = "ALARM"
        elif v > self.spec_max or v < self.spec_min:  status = "WARN"
        else:                                          status = "OK"

        delta      = round(raw - prev, 4)
        rate_pm    = round(delta / (self.scan_ms / 1000 / 60), 4) if self.scan_ms else 0
        trend      = "RISING" if delta > 0.05 else ("FALLING" if delta < -0.05 else "STABLE")
        drift_v    = round(abs(self._drift) / self.nominal, 4) if self.nominal else 0
        maint      = round(self._wear * 0.8 + drift_v * 0.2, 4)

        return {
            "tag": self.plc_tag.split(".")[-1] if self.plc_tag else "",
            "value": v, "unit": self.unit,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(now*1000)%1000:03d}Z",
            "spec_min": self.spec_min, "spec_max": self.spec_max,
            "alarm_low": round(self.alarm_lo, 3), "alarm_high": round(self.alarm_hi, 3),
            "status": status, "quality": "Good" if status != "ALARM" else "Uncertain",
            "source": self.source, "source_hw": self.source_hw,
            "plc_tag": self.plc_tag, "scan_interval_ms": self.scan_ms,
            "shift": shift, "prev_value": round(prev, 3),
            "change_delta": delta, "change_rate_per_min": rate_pm, "trend": trend,
            "stats": {"mean": round(mean, 3), "stddev": round(stddev, 4),
                      "min_session": round(smin, 3), "max_session": round(smax, 3),
                      "samples": len(self._samples), "deviation_sigma": round(sigma, 3)},
            "health": {"drift": drift_v, "wear_index": round(self._wear, 4),
                       "outlier_count": int(abs(sigma) > 2),
                       "variance_trend": "INCREASING" if stddev > self.noise * 1.5 else "DECREASING",
                       "maintenance_score": maint},
        }

class StatusGen:
    def __init__(self, states, weights=None, cycle_time=60, source="MES",
                 source_hw="", asset_id="", fault_key=None, fault_state=None):
        self.states = states
        self.weights = weights or [1] * len(states)
        self.cycle_time = cycle_time
        self.source = source
        self.source_hw = source_hw
        self.asset_id = asset_id
        self.fault_key = fault_key
        self.fault_state = fault_state
        self._cycles = 0
        self._ct_samples = []

    def _reset(self):
        self._cycles = 0
        self._ct_samples.clear()

    def _reset(self):
        self._cycles = 0
        self._ct_samples.clear()

    def __call__(self, shared):
        fault = shared.get("fault")
        active = self.fault_key and fault == self.fault_key
        if active and self.fault_state:
            state = self.fault_state
        else:
            state = random.choices(self.states, weights=self.weights, k=1)[0]
        ct = self.cycle_time + random.gauss(0, self.cycle_time * 0.05)
        self._cycles += 1
        self._ct_samples.append(ct)
        if len(self._ct_samples) > 20: self._ct_samples.pop(0)
        mean_ct = sum(self._ct_samples) / len(self._ct_samples)
        return {
            "status": state, "cycle_time_s": round(ct, 2),
            "cycle_time_mean_s": round(mean_ct, 2), "cycle_count": self._cycles,
            "asset_id": self.asset_id, "source": self.source, "source_hw": self.source_hw,
            "quality": "Good",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

class KPIGen:
    def __init__(self, oee_target=0.82, source="MES", source_hw="", asset_id="",
                 fault_key=None, fault_oee=None):
        self.oee_target = oee_target
        self.source = source
        self.source_hw = source_hw
        self.asset_id = asset_id
        self.fault_key = fault_key
        self.fault_oee = fault_oee
        self._shift_count = 0

    def _reset(self):
        self._shift_count = 0

    def _reset(self):
        self._shift_count = 0

    def __call__(self, shared):
        fault = shared.get("fault")
        active = self.fault_key and fault == self.fault_key
        base = self.fault_oee if active and self.fault_oee else self.oee_target
        avail = min(1.0, max(0.0, base + random.gauss(0, 0.015)))
        perf  = min(1.0, max(0.0, base + random.gauss(0, 0.012)))
        qual  = min(1.0, max(0.0, base + random.gauss(0, 0.008) + 0.05))
        oee   = avail * perf * qual
        fpy   = min(1.0, max(0.0, qual + random.gauss(0, 0.01)))
        tph   = round(60 / max(0.1, 60 + random.gauss(0, 3)), 2)
        self._shift_count += 1
        return {
            "OEE":           {"value": round(oee * 100, 2),   "unit": "%"},
            "FirstPassYield":{"value": round(fpy * 100, 2),   "unit": "%"},
            "Availability":  {"value": round(avail * 100, 2), "unit": "%"},
            "Performance":   {"value": round(perf * 100, 2),  "unit": "%"},
            "Quality":       {"value": round(qual * 100, 2),  "unit": "%"},
            "ThroughputRate":{"value": tph,                   "unit": "JPH"},
            "source": self.source, "source_hw": self.source_hw,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

# ── Helper to build stream dicts ──────────────────────────────────────────────
def _s(sid, topic, label, area, source, sd, unit, interval, gen, loc="", asset_id="", asset_type=""):
    return {"id": sid, "topic": topic, "label": label, "area": area,
            "source": source, "source_detail": sd, "unit": unit,
            "interval": interval, "gen": gen, "location": loc,
            "asset_id": asset_id, "asset_type": asset_type}

# ═══════════════════════════════════════════════════════════════════════════════
# FRANKFURT — Paint Shop Line 1
# ═══════════════════════════════════════════════════════════════════════════════
_FR = "Frankfurt"
_FR_PLC = "SIEMENS S7-1500"
_FR_PLC2= "SIEMENS S7-1200"
_FR_ABB = "ABB IRC5"
_FR_FAN = "FANUC R-30iB"
_FR_KUK = "KUKA KRC4"
_FR_SCN = "Ignition SCADA v8.1"

STREAMS_FR = [
    # ── Pretreatment ──────────────────────────────────────────────────────────
    _s("FR-PT-TANK01-TEMP","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Pretreatment/Tank01/Temperature",
       "Tank01 Temperature","Frankfurt/PaintShop/Line1/Pretreatment","PLC",
       f"Pretreatment_PLC ({_FR_PLC}) DB10.DBD0","C",1,
       SensorGen(67,1.2,drift_rate=0.1,thermal_amp=3,spec_min=60,spec_max=75,
                 alarm_lo=52,alarm_hi=82,unit="C",source="PLC",source_hw=_FR_PLC,
                 plc_tag="DB10.DBD0",scan_ms=100,fault_key="pretreatment_tank_overheat",
                 fault_value=89,fault_bias=15),_FR,"Tank01","ChemicalTank"),

    _s("FR-PT-TANK01-PH","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Pretreatment/Tank01/pH",
       "Tank01 pH","Frankfurt/PaintShop/Line1/Pretreatment","PLC",
       f"Pretreatment_PLC ({_FR_PLC}) DB10.DBD4","pH",2,
       SensorGen(7.2,0.08,drift_rate=0.02,spec_min=6.8,spec_max=7.6,
                 alarm_lo=6.2,alarm_hi=8.1,unit="pH",source="PLC",source_hw=_FR_PLC,
                 plc_tag="DB10.DBD4",scan_ms=500),_FR,"Tank01","ChemicalTank"),

    _s("FR-PT-TANK01-COND","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Pretreatment/Tank01/Conductivity",
       "Tank01 Conductivity","Frankfurt/PaintShop/Line1/Pretreatment","PLC",
       f"Pretreatment_PLC ({_FR_PLC}) DB10.DBD8","mS/cm",3,
       SensorGen(1.8,0.05,spec_min=1.2,spec_max=2.4,alarm_lo=0.8,alarm_hi=3.0,
                 unit="mS/cm",source="PLC",source_hw=_FR_PLC,
                 plc_tag="DB10.DBD8",scan_ms=500),_FR,"Tank01","ChemicalTank"),

    _s("FR-PT-PUMP01-FLOW","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Pretreatment/Pump01/FlowRate",
       "Pump01 Flow Rate","Frankfurt/PaintShop/Line1/Pretreatment","PLC",
       f"Pretreatment_PLC ({_FR_PLC}) DB10.DBD12","L/min",1,
       SensorGen(120,3,drift_rate=0.3,spec_min=100,spec_max=140,alarm_lo=80,alarm_hi=160,
                 unit="L/min",source="PLC",source_hw=_FR_PLC,plc_tag="DB10.DBD12",
                 fault_key="pretreatment_filter_clog",fault_value=55,fault_bias=-50),_FR,"Pump01","Pump"),

    _s("FR-PT-FILTER-DP","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Pretreatment/Filter01/DiffPressure",
       "Filter01 Differential Pressure","Frankfurt/PaintShop/Line1/Pretreatment","PLC",
       f"Pretreatment_PLC ({_FR_PLC}) DB10.DBD16","bar",5,
       SensorGen(0.3,0.02,drift_rate=0.05,wear_rate=0.8,spec_min=0.1,spec_max=0.8,
                 alarm_lo=0.05,alarm_hi=1.2,unit="bar",source="PLC",source_hw=_FR_PLC,
                 plc_tag="DB10.DBD16",fault_key="pretreatment_filter_clog",
                 fault_value=1.4,fault_bias=1.0),_FR,"Filter01","Filter"),

    _s("FR-PT-STATUS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Pretreatment/Status",
       "Pretreatment Line Status","Frankfurt/PaintShop/Line1/Pretreatment","MES",
       "SAP ME REST API","",10,
       StatusGen(["RUNNING","RUNNING","RUNNING","IDLE","MAINTENANCE"],
                 weights=[60,60,60,15,5],cycle_time=45,source="MES",
                 source_hw="SAP ME 2.0",asset_id="PT_LINE1",
                 fault_key="pretreatment_filter_clog",fault_state="MAINTENANCE"),_FR,"PT_LINE1","ProcessLine"),

    _s("FR-PT-KPI","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Pretreatment/KPI",
       "Pretreatment KPIs","Frankfurt/PaintShop/Line1/Pretreatment","MES",
       "SAP ME REST API","",30,
       KPIGen(0.84,source="MES",source_hw="SAP ME 2.0",asset_id="PT_LINE1",
              fault_key="pretreatment_filter_clog",fault_oee=0.52),_FR,"PT_LINE1","ProcessLine"),

    # ── ECoat ─────────────────────────────────────────────────────────────────
    _s("FR-EC-BATH-TEMP","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/ECoat/Bath/Temperature",
       "ECoat Bath Temperature","Frankfurt/PaintShop/Line1/ECoat","PLC",
       f"ECoat_PLC ({_FR_PLC2}) DB20.DBD0","C",1,
       SensorGen(32,0.4,drift_rate=0.05,thermal_amp=1.5,spec_min=28,spec_max=36,
                 alarm_lo=24,alarm_hi=42,unit="C",source="PLC",source_hw=_FR_PLC2,
                 plc_tag="DB20.DBD0",scan_ms=100,fault_key="ecoat_bath_contamination",
                 fault_value=41,fault_bias=8),_FR,"ECoatBath","ECoatTank"),

    _s("FR-EC-BATH-VOLT","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/ECoat/Bath/Voltage",
       "ECoat Bath Voltage","Frankfurt/PaintShop/Line1/ECoat","PLC",
       f"ECoat_PLC ({_FR_PLC2}) DB20.DBD4","V",1,
       SensorGen(280,4,spec_min=240,spec_max=320,alarm_lo=200,alarm_hi=360,
                 unit="V",source="PLC",source_hw=_FR_PLC2,plc_tag="DB20.DBD4"),_FR,"ECoatBath","ECoatTank"),

    _s("FR-EC-BATH-COND","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/ECoat/Bath/Conductivity",
       "ECoat Bath Conductivity","Frankfurt/PaintShop/Line1/ECoat","PLC",
       f"ECoat_PLC ({_FR_PLC2}) DB20.DBD8","uS/cm",2,
       SensorGen(1400,20,drift_rate=0.1,spec_min=1200,spec_max=1600,alarm_lo=1000,alarm_hi=1800,
                 unit="uS/cm",source="PLC",source_hw=_FR_PLC2,plc_tag="DB20.DBD8",
                 fault_key="ecoat_bath_contamination",fault_value=1900,fault_bias=400),_FR,"ECoatBath","ECoatTank"),

    _s("FR-EC-STATUS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/ECoat/Status",
       "ECoat Station Status","Frankfurt/PaintShop/Line1/ECoat","MES",
       "SAP ME REST API","",10,
       StatusGen(["RUNNING","RUNNING","RUNNING","IDLE"],weights=[70,70,70,10],
                 cycle_time=180,source="MES",source_hw="SAP ME 2.0",asset_id="EC_STATION1",
                 fault_key="ecoat_bath_contamination",fault_state="FAULT"),_FR,"EC_STATION1","ECoatStation"),

    _s("FR-EC-KPI","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/ECoat/KPI",
       "ECoat KPIs","Frankfurt/PaintShop/Line1/ECoat","MES","SAP ME REST API","",30,
       KPIGen(0.87,source="MES",source_hw="SAP ME 2.0",asset_id="EC_STATION1",
              fault_key="ecoat_bath_contamination",fault_oee=0.45),_FR,"EC_STATION1","ECoatStation"),

    # ── Primer Robot (ABB IRC5) ───────────────────────────────────────────────
    _s("FR-PR-ROB-CURRENT","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Primer/Robot01/MotorCurrent",
       "Primer Robot01 Motor Current","Frankfurt/PaintShop/Line1/Primer","PLC",
       f"Primer_Robot ({_FR_ABB}) J3_CURRENT","A",1,
       SensorGen(18,0.8,drift_rate=0.2,wear_rate=0.4,spec_min=12,spec_max=26,
                 alarm_lo=8,alarm_hi=32,unit="A",source="PLC",source_hw=_FR_ABB,
                 plc_tag="J3_CURRENT",scan_ms=50,fault_key="primer_robot_bearing",
                 fault_value=29,fault_bias=8),_FR,"PrimerRobot01","PaintRobot"),

    _s("FR-PR-ROB-VIBRATION","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Primer/Robot01/Vibration",
       "Primer Robot01 Vibration","Frankfurt/PaintShop/Line1/Primer","PLC",
       f"Primer_Robot ({_FR_ABB}) J3_VIB","mm/s",0.5,
       SensorGen(1.2,0.15,drift_rate=0.1,wear_rate=0.6,spec_min=0,spec_max=3.5,
                 alarm_lo=0,alarm_hi=7.1,unit="mm/s",source="PLC",source_hw=_FR_ABB,
                 plc_tag="J3_VIB",scan_ms=50,fault_key="primer_robot_bearing",
                 fault_value=6.8,fault_bias=5.0),_FR,"PrimerRobot01","PaintRobot"),

    _s("FR-PR-ATOMIZER-RPM","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Primer/Atomizer01/RPM",
       "Primer Atomizer RPM","Frankfurt/PaintShop/Line1/Primer","PLC",
       f"Primer_Robot ({_FR_ABB}) ATM_RPM","RPM",0.5,
       SensorGen(40000,500,spec_min=35000,spec_max=45000,alarm_lo=30000,alarm_hi=50000,
                 unit="RPM",source="PLC",source_hw=_FR_ABB,plc_tag="ATM_RPM"),_FR,"Atomizer01","Atomizer"),

    _s("FR-PR-PAINT-PRESS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Primer/Paint/Pressure",
       "Primer Paint Pressure","Frankfurt/PaintShop/Line1/Primer","PLC",
       f"Primer_Robot ({_FR_ABB}) PAINT_PRESS","bar",0.5,
       SensorGen(2.8,0.08,spec_min=2.2,spec_max=3.4,alarm_lo=1.8,alarm_hi=4.0,
                 unit="bar",source="PLC",source_hw=_FR_ABB,plc_tag="PAINT_PRESS"),_FR,"PrimerRobot01","PaintRobot"),

    _s("FR-PR-STATUS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Primer/Status",
       "Primer Station Status","Frankfurt/PaintShop/Line1/Primer","MES",
       "SAP ME REST API","",10,
       StatusGen(["RUNNING","RUNNING","IDLE","MAINTENANCE"],weights=[70,70,15,5],
                 cycle_time=90,source="MES",source_hw="SAP ME 2.0",asset_id="PR_STATION1",
                 fault_key="primer_robot_bearing",fault_state="FAULT"),_FR,"PR_STATION1","PrimerStation"),

    _s("FR-PR-KPI","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Primer/KPI",
       "Primer KPIs","Frankfurt/PaintShop/Line1/Primer","MES","SAP ME REST API","",30,
       KPIGen(0.85,source="MES",source_hw="SAP ME 2.0",asset_id="PR_STATION1",
              fault_key="primer_robot_bearing",fault_oee=0.48),_FR,"PR_STATION1","PrimerStation"),

    # ── Basecoat (FANUC) ─────────────────────────────────────────────────────
    _s("FR-BC-ROB1-CURR","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Basecoat/Robot01/MotorCurrent",
       "Basecoat Robot01 Motor Current","Frankfurt/PaintShop/Line1/Basecoat","PLC",
       f"Basecoat_Robot ({_FR_FAN}) J1_CURRENT","A",1,
       SensorGen(22,0.9,drift_rate=0.2,wear_rate=0.3,spec_min=15,spec_max=30,
                 alarm_lo=10,alarm_hi=36,unit="A",source="PLC",source_hw=_FR_FAN,
                 plc_tag="J1_CURRENT",scan_ms=50),_FR,"BasecoatRobot01","PaintRobot"),

    _s("FR-BC-ROB1-TEMP","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Basecoat/Robot01/ControllerTemp",
       "Basecoat Robot01 Controller Temp","Frankfurt/PaintShop/Line1/Basecoat","PLC",
       f"Basecoat_Robot ({_FR_FAN}) CTRL_TEMP","C",5,
       SensorGen(45,1.5,thermal_amp=5,spec_min=30,spec_max=60,alarm_lo=20,alarm_hi=75,
                 unit="C",source="PLC",source_hw=_FR_FAN,plc_tag="CTRL_TEMP"),_FR,"BasecoatRobot01","PaintRobot"),

    _s("FR-BC-STATUS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Basecoat/Status",
       "Basecoat Station Status","Frankfurt/PaintShop/Line1/Basecoat","MES",
       "SAP ME REST API","",10,
       StatusGen(["RUNNING","RUNNING","RUNNING","IDLE"],weights=[75,75,75,10],
                 cycle_time=110,source="MES",source_hw="SAP ME 2.0",asset_id="BC_STATION1"),_FR,"BC_STATION1","BasecoatStation"),

    _s("FR-BC-KPI","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Basecoat/KPI",
       "Basecoat KPIs","Frankfurt/PaintShop/Line1/Basecoat","MES","SAP ME REST API","",30,
       KPIGen(0.86,source="MES",source_hw="SAP ME 2.0",asset_id="BC_STATION1"),_FR,"BC_STATION1","BasecoatStation"),

    # ── Clearcoat (KUKA) ─────────────────────────────────────────────────────
    _s("FR-CC-ROB1-CURR","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Clearcoat/Robot01/MotorCurrent",
       "Clearcoat Robot01 Motor Current","Frankfurt/PaintShop/Line1/Clearcoat","PLC",
       f"Clearcoat_Robot ({_FR_KUK}) A1_CURRENT","A",1,
       SensorGen(20,0.8,wear_rate=0.3,spec_min=14,spec_max=28,alarm_lo=10,alarm_hi=34,
                 unit="A",source="PLC",source_hw=_FR_KUK,plc_tag="A1_CURRENT",scan_ms=50),_FR,"ClearcoatRobot01","PaintRobot"),

    _s("FR-CC-ELECTRODE-WEAR","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Clearcoat/Electrode01/WearIndex",
       "Clearcoat Electrode Wear Index","Frankfurt/PaintShop/Line1/Clearcoat","SCADA",
       f"Ignition SCADA ({_FR_SCN}) ClearcoatElectrode","",60,
       SensorGen(0.05,0.005,drift_rate=0.01,wear_rate=1.5,spec_min=0,spec_max=0.6,
                 alarm_lo=0,alarm_hi=0.85,unit="",source="SCADA",source_hw=_FR_SCN,
                 plc_tag="ClearcoatElectrode",fault_key="clearcoat_electrode_wear",
                 fault_value=0.9,fault_bias=0.7),_FR,"Electrode01","Electrode"),

    _s("FR-CC-STATUS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Clearcoat/Status",
       "Clearcoat Station Status","Frankfurt/PaintShop/Line1/Clearcoat","MES",
       "SAP ME REST API","",10,
       StatusGen(["RUNNING","RUNNING","RUNNING","IDLE","MAINTENANCE"],weights=[70,70,70,12,5],
                 cycle_time=95,source="MES",source_hw="SAP ME 2.0",asset_id="CC_STATION1",
                 fault_key="clearcoat_electrode_wear",fault_state="MAINTENANCE"),_FR,"CC_STATION1","ClearcoatStation"),

    _s("FR-CC-KPI","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Clearcoat/KPI",
       "Clearcoat KPIs","Frankfurt/PaintShop/Line1/Clearcoat","MES","SAP ME REST API","",30,
       KPIGen(0.83,source="MES",source_hw="SAP ME 2.0",asset_id="CC_STATION1",
              fault_key="clearcoat_electrode_wear",fault_oee=0.44),_FR,"CC_STATION1","ClearcoatStation"),

    # ── Curing Oven ──────────────────────────────────────────────────────────
    _s("FR-OV-ZONE1-TEMP","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/CuringOven/Zone1/Temperature",
       "Oven Zone1 Temperature","Frankfurt/PaintShop/Line1/CuringOven","PLC",
       f"Oven_PLC ({_FR_PLC}) DB30.DBD0","C",2,
       SensorGen(160,2,thermal_amp=8,spec_min=150,spec_max=170,alarm_lo=140,alarm_hi=185,
                 unit="C",source="PLC",source_hw=_FR_PLC,plc_tag="DB30.DBD0",
                 fault_key="curing_oven_temp_runaway",fault_value=195,fault_bias=30),_FR,"Oven_Zone1","OvenZone"),

    _s("FR-OV-ZONE2-TEMP","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/CuringOven/Zone2/Temperature",
       "Oven Zone2 Temperature","Frankfurt/PaintShop/Line1/CuringOven","PLC",
       f"Oven_PLC ({_FR_PLC}) DB30.DBD4","C",2,
       SensorGen(175,2,thermal_amp=8,spec_min=165,spec_max=185,alarm_lo=150,alarm_hi=200,
                 unit="C",source="PLC",source_hw=_FR_PLC,plc_tag="DB30.DBD4",
                 fault_key="curing_oven_temp_runaway",fault_value=210,fault_bias=30),_FR,"Oven_Zone2","OvenZone"),

    _s("FR-OV-ZONE3-TEMP","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/CuringOven/Zone3/Temperature",
       "Oven Zone3 Temperature","Frankfurt/PaintShop/Line1/CuringOven","PLC",
       f"Oven_PLC ({_FR_PLC}) DB30.DBD8","C",2,
       SensorGen(165,2,thermal_amp=8,spec_min=155,spec_max=175,alarm_lo=140,alarm_hi=190,
                 unit="C",source="PLC",source_hw=_FR_PLC,plc_tag="DB30.DBD8"),_FR,"Oven_Zone3","OvenZone"),

    _s("FR-OV-CONVEYOR-SPD","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/CuringOven/Conveyor/Speed",
       "Oven Conveyor Speed","Frankfurt/PaintShop/Line1/CuringOven","PLC",
       f"Oven_PLC ({_FR_PLC}) DB30.DBD12","m/min",1,
       SensorGen(1.4,0.03,spec_min=1.2,spec_max=1.6,alarm_lo=0.9,alarm_hi=1.9,
                 unit="m/min",source="PLC",source_hw=_FR_PLC,plc_tag="DB30.DBD12"),_FR,"OvenConveyor","Conveyor"),

    _s("FR-OV-STATUS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/CuringOven/Status",
       "Curing Oven Status","Frankfurt/PaintShop/Line1/CuringOven","SCADA",
       f"Ignition SCADA ({_FR_SCN})","",15,
       StatusGen(["HEATING","HEATING","RUNNING","RUNNING","COOLING","IDLE"],
                 weights=[20,20,80,80,15,5],cycle_time=3600,source="SCADA",
                 source_hw=_FR_SCN,asset_id="OVEN1",
                 fault_key="curing_oven_temp_runaway",fault_state="ALARM"),_FR,"OVEN1","CuringOven"),

    _s("FR-OV-KPI","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/CuringOven/KPI",
       "Curing Oven KPIs","Frankfurt/PaintShop/Line1/CuringOven","MES","SAP ME REST API","",60,
       KPIGen(0.91,source="MES",source_hw="SAP ME 2.0",asset_id="OVEN1",
              fault_key="curing_oven_temp_runaway",fault_oee=0.20),_FR,"OVEN1","CuringOven"),

    # ── Quality Inspection ────────────────────────────────────────────────────
    _s("FR-QI-GLOSS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Inspection/GlossMeter",
       "Gloss Measurement","Frankfurt/PaintShop/Line1/Inspection","SCADA",
       f"Ignition SCADA ({_FR_SCN}) GlossMeter","GU",5,
       SensorGen(87,1.5,spec_min=82,spec_max=95,alarm_lo=78,alarm_hi=99,
                 unit="GU",source="SCADA",source_hw=_FR_SCN,plc_tag="GlossMeter"),_FR,"GlossMeter01","Measurement"),

    _s("FR-QI-THICKNESS","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Inspection/ThicknessMeter",
       "Paint Film Thickness","Frankfurt/PaintShop/Line1/Inspection","SCADA",
       f"Ignition SCADA ({_FR_SCN}) ThicknessMeter","um",5,
       SensorGen(120,3,spec_min=100,spec_max=140,alarm_lo=85,alarm_hi=160,
                 unit="um",source="SCADA",source_hw=_FR_SCN,plc_tag="ThicknessMeter"),_FR,"ThicknessMeter01","Measurement"),

    _s("FR-QI-KPI","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/Inspection/KPI",
       "Inspection KPIs","Frankfurt/PaintShop/Line1/Inspection","ERP",
       "SAP S/4HANA IBM MQ","",60,
       KPIGen(0.96,source="ERP",source_hw="SAP S/4HANA",asset_id="INSP1"),_FR,"INSP1","InspectionStation"),

    # ── Production Orders (ERP) ───────────────────────────────────────────────
    _s("FR-ERP-ORDER","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/ERP/ProductionOrder",
       "Production Order Status","Frankfurt/PaintShop/Line1/ERP","ERP",
       "SAP S/4HANA IBM MQ","",30,
       StatusGen(["IN_PROCESS","IN_PROCESS","COMPLETED","RELEASED"],weights=[60,60,20,15],
                 cycle_time=3600,source="ERP",source_hw="SAP S/4HANA",asset_id="LINE1"),_FR,"LINE1","ProductionLine"),

    _s("FR-ERP-MATERIAL","IoTAuto_GmbH/Frankfurt/PaintShop/Line1/ERP/MaterialConsumption",
       "Material Consumption","Frankfurt/PaintShop/Line1/ERP","ERP","SAP S/4HANA IBM MQ","",60,
       SensorGen(45,2,spec_min=38,spec_max=55,alarm_lo=30,alarm_hi=65,
                 unit="kg/h",source="ERP",source_hw="SAP S/4HANA",plc_tag="MATCONS_L1"),_FR,"LINE1","ProductionLine"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# MUNICH — Assembly Plant (BIW + Final Assembly)
# ═══════════════════════════════════════════════════════════════════════════════
_MU = "Munich"
_MU_FAN = "FANUC R-2000iC"
_MU_ATC = "Atlas Copco ICS"
_MU_KMR = "KUKA KMR iiwa"
_MU_SCN = "Ignition SCADA v8.1"

STREAMS_MU = [
    # ── BIW Welding Robots (3x FANUC) ─────────────────────────────────────────
    _s("MU-BIW-ROB1-CURR","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot01/MotorCurrent",
       "BIW WeldRobot01 Motor Current","Munich/Assembly/BIW","PLC",
       f"WeldRobot01 ({_MU_FAN}) J2_CURRENT","A",1,
       SensorGen(24,1.0,wear_rate=0.3,spec_min=16,spec_max=34,alarm_lo=10,alarm_hi=40,
                 unit="A",source="PLC",source_hw=_MU_FAN,plc_tag="J2_CURRENT",scan_ms=50,
                 fault_key="biw_weld_robot1_fault",fault_value=38,fault_bias=12),_MU,"WeldRobot01","WeldRobot"),

    _s("MU-BIW-ROB1-WELD-CURR","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot01/WeldCurrent",
       "BIW WeldRobot01 Weld Current","Munich/Assembly/BIW","PLC",
       f"WeldRobot01 ({_MU_FAN}) WELD_CURR","A",0.5,
       SensorGen(8500,150,spec_min=7500,spec_max=9500,alarm_lo=6500,alarm_hi=11000,
                 unit="A",source="PLC",source_hw=_MU_FAN,plc_tag="WELD_CURR",scan_ms=10,
                 fault_key="biw_weld_robot1_fault",fault_value=10800,fault_bias=1800),_MU,"WeldRobot01","WeldRobot"),

    _s("MU-BIW-ROB1-STATUS","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot01/Status",
       "BIW WeldRobot01 Status","Munich/Assembly/BIW","MES",
       "SAP ME REST API","",5,
       StatusGen(["WELDING","WELDING","WELDING","IDLE","HOMING"],weights=[60,60,60,15,5],
                 cycle_time=12,source="MES",source_hw="SAP ME 2.0",asset_id="WELDROBOT01",
                 fault_key="biw_weld_robot1_fault",fault_state="FAULT"),_MU,"WeldRobot01","WeldRobot"),

    _s("MU-BIW-ROB2-CURR","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot02/MotorCurrent",
       "BIW WeldRobot02 Motor Current","Munich/Assembly/BIW","PLC",
       f"WeldRobot02 ({_MU_FAN}) J2_CURRENT","A",1,
       SensorGen(23,1.0,wear_rate=0.25,spec_min=16,spec_max=32,alarm_lo=10,alarm_hi=38,
                 unit="A",source="PLC",source_hw=_MU_FAN,plc_tag="J2_CURRENT",scan_ms=50),_MU,"WeldRobot02","WeldRobot"),

    _s("MU-BIW-ROB2-WELD-CURR","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot02/WeldCurrent",
       "BIW WeldRobot02 Weld Current","Munich/Assembly/BIW","PLC",
       f"WeldRobot02 ({_MU_FAN}) WELD_CURR","A",0.5,
       SensorGen(8400,160,spec_min=7400,spec_max=9400,alarm_lo=6400,alarm_hi=10800,
                 unit="A",source="PLC",source_hw=_MU_FAN,plc_tag="WELD_CURR",scan_ms=10),_MU,"WeldRobot02","WeldRobot"),

    _s("MU-BIW-ROB2-STATUS","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot02/Status",
       "BIW WeldRobot02 Status","Munich/Assembly/BIW","MES",
       "SAP ME REST API","",5,
       StatusGen(["WELDING","WELDING","WELDING","IDLE"],weights=[65,65,65,10],
                 cycle_time=12,source="MES",source_hw="SAP ME 2.0",asset_id="WELDROBOT02"),_MU,"WeldRobot02","WeldRobot"),

    _s("MU-BIW-ROB3-CURR","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot03/MotorCurrent",
       "BIW WeldRobot03 Motor Current","Munich/Assembly/BIW","PLC",
       f"WeldRobot03 ({_MU_FAN}) J2_CURRENT","A",1,
       SensorGen(25,1.1,wear_rate=0.35,spec_min=17,spec_max=34,alarm_lo=11,alarm_hi=40,
                 unit="A",source="PLC",source_hw=_MU_FAN,plc_tag="J2_CURRENT",scan_ms=50),_MU,"WeldRobot03","WeldRobot"),

    _s("MU-BIW-ROB3-STATUS","IoTAuto_GmbH/Munich/Assembly/BIW/WeldRobot03/Status",
       "BIW WeldRobot03 Status","Munich/Assembly/BIW","MES",
       "SAP ME REST API","",5,
       StatusGen(["WELDING","WELDING","WELDING","IDLE","MAINTENANCE"],weights=[60,60,60,12,3],
                 cycle_time=12,source="MES",source_hw="SAP ME 2.0",asset_id="WELDROBOT03"),_MU,"WeldRobot03","WeldRobot"),

    _s("MU-BIW-KPI","IoTAuto_GmbH/Munich/Assembly/BIW/KPI",
       "BIW Welding KPIs","Munich/Assembly/BIW","MES","SAP ME REST API","",30,
       KPIGen(0.88,source="MES",source_hw="SAP ME 2.0",asset_id="BIW_CELL1",
              fault_key="biw_weld_robot1_fault",fault_oee=0.50),_MU,"BIW_CELL1","WeldCell"),

    # ── Final Assembly Bolt Stations (Atlas Copco) ─────────────────────────────
    _s("MU-FA-BOLT1-TORQUE","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/BoltStation01/Torque",
       "Bolt Station01 Torque","Munich/Assembly/FinalAssembly","PLC",
       f"BoltStation01 ({_MU_ATC}) CH1_TORQUE","Nm",1,
       SensorGen(22,0.5,spec_min=20,spec_max=24,alarm_lo=17,alarm_hi=27,
                 unit="Nm",source="PLC",source_hw=_MU_ATC,plc_tag="CH1_TORQUE",scan_ms=100,
                 fault_key="fa_bolt_station1_overtorque",fault_value=26.5,fault_bias=4),_MU,"BoltStation01","BoltStation"),

    _s("MU-FA-BOLT1-ANGLE","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/BoltStation01/Angle",
       "Bolt Station01 Angle","Munich/Assembly/FinalAssembly","PLC",
       f"BoltStation01 ({_MU_ATC}) CH1_ANGLE","deg",1,
       SensorGen(185,3,spec_min=175,spec_max=195,alarm_lo=165,alarm_hi=210,
                 unit="deg",source="PLC",source_hw=_MU_ATC,plc_tag="CH1_ANGLE",scan_ms=100),_MU,"BoltStation01","BoltStation"),

    _s("MU-FA-BOLT1-STATUS","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/BoltStation01/Status",
       "Bolt Station01 Status","Munich/Assembly/FinalAssembly","MES",
       "SAP ME REST API","",3,
       StatusGen(["OK","OK","OK","NOK","IDLE"],weights=[80,80,80,5,15],
                 cycle_time=8,source="MES",source_hw="SAP ME 2.0",asset_id="BOLT01",
                 fault_key="fa_bolt_station1_overtorque",fault_state="FAULT"),_MU,"BoltStation01","BoltStation"),

    _s("MU-FA-BOLT2-TORQUE","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/BoltStation02/Torque",
       "Bolt Station02 Torque","Munich/Assembly/FinalAssembly","PLC",
       f"BoltStation02 ({_MU_ATC}) CH1_TORQUE","Nm",1,
       SensorGen(35,0.7,spec_min=32,spec_max=38,alarm_lo=28,alarm_hi=43,
                 unit="Nm",source="PLC",source_hw=_MU_ATC,plc_tag="CH1_TORQUE",scan_ms=100),_MU,"BoltStation02","BoltStation"),

    _s("MU-FA-BOLT2-STATUS","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/BoltStation02/Status",
       "Bolt Station02 Status","Munich/Assembly/FinalAssembly","MES",
       "SAP ME REST API","",3,
       StatusGen(["OK","OK","OK","NOK","IDLE"],weights=[82,82,82,4,12],
                 cycle_time=8,source="MES",source_hw="SAP ME 2.0",asset_id="BOLT02"),_MU,"BoltStation02","BoltStation"),

    _s("MU-FA-BOLT3-TORQUE","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/BoltStation03/Torque",
       "Bolt Station03 Torque","Munich/Assembly/FinalAssembly","PLC",
       f"BoltStation03 ({_MU_ATC}) CH1_TORQUE","Nm",1,
       SensorGen(18,0.4,spec_min=16,spec_max=20,alarm_lo=13,alarm_hi=23,
                 unit="Nm",source="PLC",source_hw=_MU_ATC,plc_tag="CH1_TORQUE",scan_ms=100),_MU,"BoltStation03","BoltStation"),

    _s("MU-FA-BOLT3-STATUS","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/BoltStation03/Status",
       "Bolt Station03 Status","Munich/Assembly/FinalAssembly","MES",
       "SAP ME REST API","",3,
       StatusGen(["OK","OK","OK","NOK","IDLE"],weights=[80,80,80,5,15],
                 cycle_time=8,source="MES",source_hw="SAP ME 2.0",asset_id="BOLT03"),_MU,"BoltStation03","BoltStation"),

    _s("MU-FA-KPI","IoTAuto_GmbH/Munich/Assembly/FinalAssembly/KPI",
       "Final Assembly KPIs","Munich/Assembly/FinalAssembly","MES","SAP ME REST API","",30,
       KPIGen(0.89,source="MES",source_hw="SAP ME 2.0",asset_id="FA_LINE1",
              fault_key="fa_bolt_station1_overtorque",fault_oee=0.62),_MU,"FA_LINE1","AssemblyLine"),

    # ── AGV Fleet (KUKA KMR) ──────────────────────────────────────────────────
    _s("MU-AGV1-BATTERY","IoTAuto_GmbH/Munich/Assembly/Logistics/AGV01/BatteryLevel",
       "AGV01 Battery Level","Munich/Assembly/Logistics","PLC",
       f"AGV01 ({_MU_KMR}) BATT_LEVEL","%",10,
       SensorGen(75,2,drift_rate=-0.5,spec_min=20,spec_max=100,alarm_lo=10,alarm_hi=100,
                 unit="%",source="PLC",source_hw=_MU_KMR,plc_tag="BATT_LEVEL"),_MU,"AGV01","AGV"),

    _s("MU-AGV1-SPEED","IoTAuto_GmbH/Munich/Assembly/Logistics/AGV01/Speed",
       "AGV01 Speed","Munich/Assembly/Logistics","PLC",
       f"AGV01 ({_MU_KMR}) SPEED","m/s",2,
       SensorGen(1.2,0.15,spec_min=0,spec_max=1.8,alarm_lo=0,alarm_hi=2.2,
                 unit="m/s",source="PLC",source_hw=_MU_KMR,plc_tag="SPEED"),_MU,"AGV01","AGV"),

    _s("MU-AGV1-STATUS","IoTAuto_GmbH/Munich/Assembly/Logistics/AGV01/Status",
       "AGV01 Status","Munich/Assembly/Logistics","MES","SAP ME REST API","",5,
       StatusGen(["MOVING","MOVING","LOADING","UNLOADING","CHARGING","IDLE"],
                 weights=[50,50,20,20,15,10],cycle_time=60,source="MES",
                 source_hw="SAP ME 2.0",asset_id="AGV01",
                 fault_key="agv_fleet_battery_low",fault_state="CHARGING"),_MU,"AGV01","AGV"),

    _s("MU-AGV2-BATTERY","IoTAuto_GmbH/Munich/Assembly/Logistics/AGV02/BatteryLevel",
       "AGV02 Battery Level","Munich/Assembly/Logistics","PLC",
       f"AGV02 ({_MU_KMR}) BATT_LEVEL","%",10,
       SensorGen(60,2,drift_rate=-0.4,spec_min=20,spec_max=100,alarm_lo=10,alarm_hi=100,
                 unit="%",source="PLC",source_hw=_MU_KMR,plc_tag="BATT_LEVEL",
                 fault_key="agv_fleet_battery_low",fault_value=8,fault_bias=-50),_MU,"AGV02","AGV"),

    _s("MU-AGV2-STATUS","IoTAuto_GmbH/Munich/Assembly/Logistics/AGV02/Status",
       "AGV02 Status","Munich/Assembly/Logistics","MES","SAP ME REST API","",5,
       StatusGen(["MOVING","MOVING","LOADING","UNLOADING","IDLE"],weights=[50,50,20,20,15],
                 cycle_time=60,source="MES",source_hw="SAP ME 2.0",asset_id="AGV02",
                 fault_key="agv_fleet_battery_low",fault_state="ALARM"),_MU,"AGV02","AGV"),

    _s("MU-AGV3-BATTERY","IoTAuto_GmbH/Munich/Assembly/Logistics/AGV03/BatteryLevel",
       "AGV03 Battery Level","Munich/Assembly/Logistics","PLC",
       f"AGV03 ({_MU_KMR}) BATT_LEVEL","%",10,
       SensorGen(88,2,drift_rate=-0.3,spec_min=20,spec_max=100,alarm_lo=10,alarm_hi=100,
                 unit="%",source="PLC",source_hw=_MU_KMR,plc_tag="BATT_LEVEL"),_MU,"AGV03","AGV"),

    _s("MU-AGV3-STATUS","IoTAuto_GmbH/Munich/Assembly/Logistics/AGV03/Status",
       "AGV03 Status","Munich/Assembly/Logistics","MES","SAP ME REST API","",5,
       StatusGen(["MOVING","MOVING","LOADING","UNLOADING","CHARGING","IDLE"],
                 weights=[50,50,20,20,10,10],cycle_time=60,source="MES",
                 source_hw="SAP ME 2.0",asset_id="AGV03"),_MU,"AGV03","AGV"),

    # ── Conveyor + Adhesive ───────────────────────────────────────────────────
    _s("MU-CONV-SPEED","IoTAuto_GmbH/Munich/Assembly/Conveyor/Main/Speed",
       "Main Conveyor Speed","Munich/Assembly/Conveyor","PLC",
       f"Conveyor_PLC ({_MU_KMR}) CONV_SPD","m/min",1,
       SensorGen(4.5,0.1,spec_min=3.8,spec_max=5.2,alarm_lo=2.5,alarm_hi=6.5,
                 unit="m/min",source="PLC",source_hw="SIEMENS S7-1500",plc_tag="CONV_SPD"),_MU,"MainConveyor","Conveyor"),

    _s("MU-ADH-TEMP","IoTAuto_GmbH/Munich/Assembly/Adhesive/Dispenser01/Temperature",
       "Adhesive Dispenser Temperature","Munich/Assembly/Adhesive","PLC",
       f"Adhesive_PLC ({_MU_KMR}) ADH_TEMP","C",2,
       SensorGen(185,3,spec_min=175,spec_max=195,alarm_lo=160,alarm_hi=210,
                 unit="C",source="PLC",source_hw="SIEMENS S7-1200",plc_tag="ADH_TEMP"),_MU,"AdhDispenser01","Dispenser"),

    _s("MU-ADH-PRESSURE","IoTAuto_GmbH/Munich/Assembly/Adhesive/Dispenser01/Pressure",
       "Adhesive Dispenser Pressure","Munich/Assembly/Adhesive","PLC",
       f"Adhesive_PLC ({_MU_KMR}) ADH_PRESS","bar",2,
       SensorGen(6.5,0.2,spec_min=5.8,spec_max=7.2,alarm_lo=4.5,alarm_hi=8.5,
                 unit="bar",source="PLC",source_hw="SIEMENS S7-1200",plc_tag="ADH_PRESS"),_MU,"AdhDispenser01","Dispenser"),

    # ── Geometry Scanner (ZEISS ATOS) ─────────────────────────────────────────
    _s("MU-GEOM-DEVIATION","IoTAuto_GmbH/Munich/Assembly/Inspection/ATOS/MeanDeviation",
       "Geometry Mean Deviation","Munich/Assembly/Inspection","SCADA",
       f"Ignition SCADA ({_MU_SCN}) ATOS_DEV","mm",10,
       SensorGen(0.12,0.02,spec_min=0,spec_max=0.3,alarm_lo=0,alarm_hi=0.5,
                 unit="mm",source="SCADA",source_hw="ZEISS ATOS 5X",plc_tag="ATOS_DEV"),_MU,"ATOS_Scanner","Scanner"),

    _s("MU-GEOM-KPI","IoTAuto_GmbH/Munich/Assembly/Inspection/KPI",
       "Assembly Inspection KPIs","Munich/Assembly/Inspection","ERP",
       "SAP S/4HANA IBM MQ","",60,
       KPIGen(0.97,source="ERP",source_hw="SAP S/4HANA",asset_id="INSP_ASSEMBLY"),_MU,"INSP_ASSEMBLY","InspectionStation"),

    _s("MU-ERP-ORDER","IoTAuto_GmbH/Munich/Assembly/ERP/ProductionOrder",
       "Assembly Production Order","Munich/Assembly/ERP","ERP",
       "SAP S/4HANA IBM MQ","",30,
       StatusGen(["IN_PROCESS","IN_PROCESS","COMPLETED","RELEASED"],weights=[60,60,20,15],
                 cycle_time=7200,source="ERP",source_hw="SAP S/4HANA",asset_id="ASSEMBLY1"),_MU,"ASSEMBLY1","ProductionLine"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# INGOLSTADT — Press Shop + Body Shop
# ═══════════════════════════════════════════════════════════════════════════════
_IN = "Ingolstadt"
_IN_SCH = "Schuler MSP 800"
_IN_KUK = "KUKA KRC5"
_IN_BEC = "Beckhoff CX2040"
_IN_SCN = "Ignition SCADA v8.1"

STREAMS_IN = [
    # ── Press Shop (2x Schuler) ───────────────────────────────────────────────
    _s("IN-PS-PRESS1-FORCE","IoTAuto_GmbH/Ingolstadt/PressShop/Press01/StampingForce",
       "Press01 Stamping Force","Ingolstadt/PressShop","PLC",
       f"Press01 ({_IN_SCH}) PRESS_FORCE","kN",0.5,
       SensorGen(3200,40,drift_rate=0.5,wear_rate=0.2,spec_min=2800,spec_max=3600,
                 alarm_lo=2400,alarm_hi=4000,unit="kN",source="PLC",source_hw=_IN_SCH,
                 plc_tag="PRESS_FORCE",scan_ms=10,fault_key="press_shop_die_wear",
                 fault_value=3750,fault_bias=400),_IN,"Press01","StampingPress"),

    _s("IN-PS-PRESS1-VIB","IoTAuto_GmbH/Ingolstadt/PressShop/Press01/Vibration",
       "Press01 Vibration (SKF)","Ingolstadt/PressShop","SCADA",
       f"Ignition SCADA ({_IN_SCN}) P1_VIB","mm/s",1,
       SensorGen(2.5,0.3,drift_rate=0.2,wear_rate=0.8,spec_min=0,spec_max=7.1,
                 alarm_lo=0,alarm_hi=11.2,unit="mm/s",source="SCADA",source_hw="SKF Enlight",
                 plc_tag="P1_VIB",fault_key="press_shop_die_wear",
                 fault_value=9.5,fault_bias=6.0),_IN,"Press01","StampingPress"),

    _s("IN-PS-PRESS1-SPM","IoTAuto_GmbH/Ingolstadt/PressShop/Press01/StrokesPerMin",
       "Press01 Strokes/min","Ingolstadt/PressShop","PLC",
       f"Press01 ({_IN_SCH}) SPM","spm",1,
       SensorGen(22,0.5,spec_min=18,spec_max=26,alarm_lo=14,alarm_hi=30,
                 unit="spm",source="PLC",source_hw=_IN_SCH,plc_tag="SPM"),_IN,"Press01","StampingPress"),

    _s("IN-PS-PRESS1-STATUS","IoTAuto_GmbH/Ingolstadt/PressShop/Press01/Status",
       "Press01 Status","Ingolstadt/PressShop","MES","SAP ME REST API","",5,
       StatusGen(["STAMPING","STAMPING","STAMPING","IDLE","DIE_CHANGE"],
                 weights=[70,70,70,15,5],cycle_time=3,source="MES",
                 source_hw="SAP ME 2.0",asset_id="PRESS01",
                 fault_key="press_shop_die_wear",fault_state="FAULT"),_IN,"Press01","StampingPress"),

    _s("IN-PS-PRESS2-FORCE","IoTAuto_GmbH/Ingolstadt/PressShop/Press02/StampingForce",
       "Press02 Stamping Force","Ingolstadt/PressShop","PLC",
       f"Press02 ({_IN_SCH}) PRESS_FORCE","kN",0.5,
       SensorGen(2800,35,drift_rate=0.4,wear_rate=0.15,spec_min=2400,spec_max=3200,
                 alarm_lo=2000,alarm_hi=3600,unit="kN",source="PLC",source_hw=_IN_SCH,
                 plc_tag="PRESS_FORCE",scan_ms=10),_IN,"Press02","StampingPress"),

    _s("IN-PS-PRESS2-VIB","IoTAuto_GmbH/Ingolstadt/PressShop/Press02/Vibration",
       "Press02 Vibration (SKF)","Ingolstadt/PressShop","SCADA",
       f"Ignition SCADA ({_IN_SCN}) P2_VIB","mm/s",1,
       SensorGen(2.2,0.25,wear_rate=0.6,spec_min=0,spec_max=7.1,alarm_lo=0,alarm_hi=11.2,
                 unit="mm/s",source="SCADA",source_hw="SKF Enlight",plc_tag="P2_VIB"),_IN,"Press02","StampingPress"),

    _s("IN-PS-PRESS2-STATUS","IoTAuto_GmbH/Ingolstadt/PressShop/Press02/Status",
       "Press02 Status","Ingolstadt/PressShop","MES","SAP ME REST API","",5,
       StatusGen(["STAMPING","STAMPING","STAMPING","IDLE"],weights=[72,72,72,12],
                 cycle_time=3,source="MES",source_hw="SAP ME 2.0",asset_id="PRESS02"),_IN,"Press02","StampingPress"),

    _s("IN-PS-KPI","IoTAuto_GmbH/Ingolstadt/PressShop/KPI",
       "Press Shop KPIs","Ingolstadt/PressShop","MES","SAP ME REST API","",30,
       KPIGen(0.86,source="MES",source_hw="SAP ME 2.0",asset_id="PRESS_SHOP",
              fault_key="press_shop_die_wear",fault_oee=0.40),_IN,"PRESS_SHOP","PressShop"),

    # ── Body Shop Welding (3x KUKA KRC5) ──────────────────────────────────────
    _s("IN-BS-ROB1-CURR","IoTAuto_GmbH/Ingolstadt/BodyShop/WeldRobot01/MotorCurrent",
       "Body WeldRobot01 Motor Current","Ingolstadt/BodyShop","PLC",
       f"BodyWeldRobot01 ({_IN_KUK}) A1_CURR","A",1,
       SensorGen(26,1.1,wear_rate=0.28,spec_min=18,spec_max=35,alarm_lo=12,alarm_hi=42,
                 unit="A",source="PLC",source_hw=_IN_KUK,plc_tag="A1_CURR",scan_ms=50,
                 fault_key="body_shop_robot1_collision",fault_value=41,fault_bias=13),_IN,"BodyWeldRobot01","WeldRobot"),

    _s("IN-BS-ROB1-WELD-FORCE","IoTAuto_GmbH/Ingolstadt/BodyShop/WeldRobot01/WeldForce",
       "Body WeldRobot01 Weld Force","Ingolstadt/BodyShop","PLC",
       f"BodyWeldRobot01 ({_IN_KUK}) WELD_FORCE","kN",0.5,
       SensorGen(4.5,0.15,spec_min=3.8,spec_max=5.2,alarm_lo=3.0,alarm_hi=6.5,
                 unit="kN",source="PLC",source_hw=_IN_KUK,plc_tag="WELD_FORCE",scan_ms=20,
                 fault_key="body_shop_robot1_collision",fault_value=6.2,fault_bias=1.5),_IN,"BodyWeldRobot01","WeldRobot"),

    _s("IN-BS-ROB1-STATUS","IoTAuto_GmbH/Ingolstadt/BodyShop/WeldRobot01/Status",
       "Body WeldRobot01 Status","Ingolstadt/BodyShop","MES","SAP ME REST API","",5,
       StatusGen(["WELDING","WELDING","WELDING","IDLE","HOMING"],weights=[62,62,62,14,4],
                 cycle_time=8,source="MES",source_hw="SAP ME 2.0",asset_id="BS_ROBOT01",
                 fault_key="body_shop_robot1_collision",fault_state="ESTOP"),_IN,"BodyWeldRobot01","WeldRobot"),

    _s("IN-BS-ROB2-CURR","IoTAuto_GmbH/Ingolstadt/BodyShop/WeldRobot02/MotorCurrent",
       "Body WeldRobot02 Motor Current","Ingolstadt/BodyShop","PLC",
       f"BodyWeldRobot02 ({_IN_KUK}) A1_CURR","A",1,
       SensorGen(24,1.0,wear_rate=0.22,spec_min=17,spec_max=33,alarm_lo=11,alarm_hi=40,
                 unit="A",source="PLC",source_hw=_IN_KUK,plc_tag="A1_CURR",scan_ms=50),_IN,"BodyWeldRobot02","WeldRobot"),

    _s("IN-BS-ROB2-STATUS","IoTAuto_GmbH/Ingolstadt/BodyShop/WeldRobot02/Status",
       "Body WeldRobot02 Status","Ingolstadt/BodyShop","MES","SAP ME REST API","",5,
       StatusGen(["WELDING","WELDING","WELDING","IDLE"],weights=[65,65,65,12],
                 cycle_time=8,source="MES",source_hw="SAP ME 2.0",asset_id="BS_ROBOT02"),_IN,"BodyWeldRobot02","WeldRobot"),

    _s("IN-BS-ROB3-CURR","IoTAuto_GmbH/Ingolstadt/BodyShop/WeldRobot03/MotorCurrent",
       "Body WeldRobot03 Motor Current","Ingolstadt/BodyShop","PLC",
       f"BodyWeldRobot03 ({_IN_KUK}) A1_CURR","A",1,
       SensorGen(25,1.0,wear_rate=0.30,spec_min=17,spec_max=34,alarm_lo=11,alarm_hi=41,
                 unit="A",source="PLC",source_hw=_IN_KUK,plc_tag="A1_CURR",scan_ms=50),_IN,"BodyWeldRobot03","WeldRobot"),

    _s("IN-BS-ROB3-STATUS","IoTAuto_GmbH/Ingolstadt/BodyShop/WeldRobot03/Status",
       "Body WeldRobot03 Status","Ingolstadt/BodyShop","MES","SAP ME REST API","",5,
       StatusGen(["WELDING","WELDING","WELDING","IDLE","MAINTENANCE"],weights=[62,62,62,12,3],
                 cycle_time=8,source="MES",source_hw="SAP ME 2.0",asset_id="BS_ROBOT03"),_IN,"BodyWeldRobot03","WeldRobot"),

    _s("IN-BS-KPI","IoTAuto_GmbH/Ingolstadt/BodyShop/KPI",
       "Body Shop KPIs","Ingolstadt/BodyShop","MES","SAP ME REST API","",30,
       KPIGen(0.87,source="MES",source_hw="SAP ME 2.0",asset_id="BS_CELL1",
              fault_key="body_shop_robot1_collision",fault_oee=0.15),_IN,"BS_CELL1","WeldCell"),

    # ── Hemming Station (Beckhoff) ─────────────────────────────────────────────
    _s("IN-HEM-FORCE","IoTAuto_GmbH/Ingolstadt/BodyShop/Hemming/Station01/Force",
       "Hemming Station01 Force","Ingolstadt/BodyShop/Hemming","PLC",
       f"Hemming_PLC ({_IN_BEC}) HEM_FORCE","kN",1,
       SensorGen(85,2,spec_min=75,spec_max=95,alarm_lo=60,alarm_hi=110,
                 unit="kN",source="PLC",source_hw=_IN_BEC,plc_tag="HEM_FORCE"),_IN,"HemmingStation01","HemmingStation"),

    _s("IN-HEM-POSITION","IoTAuto_GmbH/Ingolstadt/BodyShop/Hemming/Station01/Position",
       "Hemming Station01 Z-Position","Ingolstadt/BodyShop/Hemming","PLC",
       f"Hemming_PLC ({_IN_BEC}) HEM_POS","mm",1,
       SensorGen(0.0,0.02,spec_min=-0.1,spec_max=0.1,alarm_lo=-0.5,alarm_hi=0.5,
                 unit="mm",source="PLC",source_hw=_IN_BEC,plc_tag="HEM_POS"),_IN,"HemmingStation01","HemmingStation"),

    _s("IN-HEM-STATUS","IoTAuto_GmbH/Ingolstadt/BodyShop/Hemming/Station01/Status",
       "Hemming Station01 Status","Ingolstadt/BodyShop/Hemming","MES","SAP ME REST API","",5,
       StatusGen(["HEMMING","HEMMING","IDLE","SETUP"],weights=[65,65,20,5],
                 cycle_time=25,source="MES",source_hw="SAP ME 2.0",asset_id="HEM01"),_IN,"HemmingStation01","HemmingStation"),

    # ── Geometry Measurement (ISRA VISION) ─────────────────────────────────────
    _s("IN-GEO-DEVIATION","IoTAuto_GmbH/Ingolstadt/BodyShop/Inspection/ISRA/Deviation",
       "Body Geometry Deviation","Ingolstadt/BodyShop/Inspection","SCADA",
       f"Ignition SCADA ({_IN_SCN}) ISRA_DEV","mm",15,
       SensorGen(0.18,0.03,spec_min=0,spec_max=0.4,alarm_lo=0,alarm_hi=0.7,
                 unit="mm",source="SCADA",source_hw="ISRA VISION BodyScan3D",plc_tag="ISRA_DEV"),_IN,"ISRA_Scanner","Scanner"),

    _s("IN-GEO-KPI","IoTAuto_GmbH/Ingolstadt/BodyShop/Inspection/KPI",
       "Body Inspection KPIs","Ingolstadt/BodyShop/Inspection","ERP",
       "SAP S/4HANA IBM MQ","",60,
       KPIGen(0.95,source="ERP",source_hw="SAP S/4HANA",asset_id="INSP_BODY"),_IN,"INSP_BODY","InspectionStation"),

    # ── Environmental ─────────────────────────────────────────────────────────
    _s("IN-ENV-TEMP","IoTAuto_GmbH/Ingolstadt/Environment/ShopFloor/Temperature",
       "Shop Floor Temperature","Ingolstadt/Environment","SCADA",
       f"Ignition SCADA ({_IN_SCN}) ENV_TEMP","C",30,
       SensorGen(22,1,thermal_amp=4,thermal_period=86400,spec_min=16,spec_max=30,
                 alarm_lo=10,alarm_hi=38,unit="C",source="SCADA",source_hw=_IN_SCN,
                 plc_tag="ENV_TEMP"),_IN,"ShopFloor","Environment"),

    _s("IN-ENV-HUMIDITY","IoTAuto_GmbH/Ingolstadt/Environment/ShopFloor/Humidity",
       "Shop Floor Humidity","Ingolstadt/Environment","SCADA",
       f"Ignition SCADA ({_IN_SCN}) ENV_HUM","%RH",30,
       SensorGen(48,2,spec_min=35,spec_max=65,alarm_lo=20,alarm_hi=80,
                 unit="%RH",source="SCADA",source_hw=_IN_SCN,plc_tag="ENV_HUM"),_IN,"ShopFloor","Environment"),

    _s("IN-ERP-ORDER","IoTAuto_GmbH/Ingolstadt/PressShop/ERP/ProductionOrder",
       "Press Shop Production Order","Ingolstadt/ERP","ERP",
       "SAP S/4HANA IBM MQ","",30,
       StatusGen(["IN_PROCESS","IN_PROCESS","COMPLETED","RELEASED"],weights=[60,60,20,15],
                 cycle_time=7200,source="ERP",source_hw="SAP S/4HANA",asset_id="PRESS_SHOP"),_IN,"PRESS_SHOP","ProductionLine"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# Fault scenario config to enrich payloads
# ═══════════════════════════════════════════════════════════════════════════════

# ── Wrap generators so they include stream-level metadata ────────────────────
def _wrap_gen(stream):
    """Wrap a generator to stamp stream-level metadata onto every payload.
    Exposes _reset() so SimulatorState.reset_for_demo() can reach it.
    """
    orig = stream["gen"]
    def wrapped(shared):
        p = orig(shared)
        p.setdefault("asset_id",   stream.get("asset_id",""))
        p.setdefault("asset_type", stream.get("asset_type",""))
        p.setdefault("location",   stream.get("location",""))
        p.setdefault("area",       stream.get("area",""))
        p.setdefault("label",      stream.get("label",""))
        return p
    # expose reset so the simulator can call wrapped._reset()
    wrapped._reset = getattr(orig, "_reset", lambda: None)
    wrapped._reset = getattr(orig, "_reset", lambda: None)
    return wrapped

STREAMS_RAW = STREAMS_FR + STREAMS_MU + STREAMS_IN
STREAMS = []
for s in STREAMS_RAW:
    s = dict(s)
    s["gen"] = _wrap_gen(s)
    STREAMS.append(s)

STREAM_BY_ID = {s["id"]: s for s in STREAMS}

# ═══════════════════════════════════════════════════════════════════════════════
# Fault scenarios
# ═══════════════════════════════════════════════════════════════════════════════
FAULT_SCENARIOS = {
    "normal": {
        "id":"normal","label":"Normal Operation","description":"All systems nominal",
        "color":"emerald","fault_key":None,"affected":[],"location":"all",
    },
    "pretreatment_filter_clog": {
        "id":"pretreatment_filter_clog","label":"FR: Filter Clog",
        "description":"Pretreatment Filter01 differential pressure rising. Flow drop detected.",
        "color":"amber","fault_key":"pretreatment_filter_clog","location":"Frankfurt",
        "affected":["FR-PT-FILTER-DP","FR-PT-PUMP01-FLOW","FR-PT-STATUS","FR-PT-KPI"],
        "stop_publishing":False,
    },
    "pretreatment_tank_overheat": {
        "id":"pretreatment_tank_overheat","label":"FR: Tank Overheat",
        "description":"Tank01 temperature exceeding spec. Alarm condition active.",
        "color":"red","fault_key":"pretreatment_tank_overheat","location":"Frankfurt",
        "affected":["FR-PT-TANK01-TEMP","FR-PT-STATUS","FR-PT-KPI"],
        "stop_publishing":False,
    },
    "ecoat_bath_contamination": {
        "id":"ecoat_bath_contamination","label":"FR: ECoat Contamination",
        "description":"ECoat bath conductivity anomaly. Possible contamination event.",
        "color":"red","fault_key":"ecoat_bath_contamination","location":"Frankfurt",
        "affected":["FR-EC-BATH-TEMP","FR-EC-BATH-COND","FR-EC-STATUS","FR-EC-KPI"],
        "stop_publishing":False,
    },
    "primer_robot_bearing": {
        "id":"primer_robot_bearing","label":"FR: Primer Robot Bearing",
        "description":"Primer Robot01 J3 bearing wear. Elevated current and vibration.",
        "color":"amber","fault_key":"primer_robot_bearing","location":"Frankfurt",
        "affected":["FR-PR-ROB-CURRENT","FR-PR-ROB-VIBRATION","FR-PR-STATUS","FR-PR-KPI"],
        "stop_publishing":False,
    },
    "clearcoat_electrode_wear": {
        "id":"clearcoat_electrode_wear","label":"FR: Electrode Wear",
        "description":"Clearcoat Electrode01 wear index above threshold. Maintenance required.",
        "color":"amber","fault_key":"clearcoat_electrode_wear","location":"Frankfurt",
        "affected":["FR-CC-ELECTRODE-WEAR","FR-CC-STATUS","FR-CC-KPI"],
        "stop_publishing":False,
    },
    "curing_oven_temp_runaway": {
        "id":"curing_oven_temp_runaway","label":"FR: Oven Runaway",
        "description":"Curing oven zone temperature runaway. Emergency shutdown imminent.",
        "color":"red","fault_key":"curing_oven_temp_runaway","location":"Frankfurt",
        "affected":["FR-OV-ZONE1-TEMP","FR-OV-ZONE2-TEMP","FR-OV-STATUS","FR-OV-KPI"],
        "stop_publishing":False,
    },
    "biw_weld_robot1_fault": {
        "id":"biw_weld_robot1_fault","label":"MU: BIW Robot1 Fault",
        "description":"Munich BIW WeldRobot01 overcurrent fault. Weld current spike detected.",
        "color":"red","fault_key":"biw_weld_robot1_fault","location":"Munich",
        "affected":["MU-BIW-ROB1-CURR","MU-BIW-ROB1-WELD-CURR","MU-BIW-ROB1-STATUS","MU-BIW-KPI"],
        "stop_publishing":False,
    },
    "fa_bolt_station1_overtorque": {
        "id":"fa_bolt_station1_overtorque","label":"MU: Bolt Overtorque",
        "description":"Munich Final Assembly BoltStation01 torque exceeding limit.",
        "color":"amber","fault_key":"fa_bolt_station1_overtorque","location":"Munich",
        "affected":["MU-FA-BOLT1-TORQUE","MU-FA-BOLT1-STATUS","MU-FA-KPI"],
        "stop_publishing":False,
    },
    "agv_fleet_battery_low": {
        "id":"agv_fleet_battery_low","label":"MU: AGV Battery Low",
        "description":"Munich AGV02 battery critically low. Fleet coverage reduced.",
        "color":"amber","fault_key":"agv_fleet_battery_low","location":"Munich",
        "affected":["MU-AGV2-BATTERY","MU-AGV2-STATUS","MU-AGV1-STATUS"],
        "stop_publishing":False,
    },
    "press_shop_die_wear": {
        "id":"press_shop_die_wear","label":"IN: Die Wear",
        "description":"Ingolstadt Press01 die wear detected. Force and vibration anomaly.",
        "color":"amber","fault_key":"press_shop_die_wear","location":"Ingolstadt",
        "affected":["IN-PS-PRESS1-FORCE","IN-PS-PRESS1-VIB","IN-PS-PRESS1-STATUS","IN-PS-KPI"],
        "stop_publishing":False,
    },
    "body_shop_robot1_collision": {
        "id":"body_shop_robot1_collision","label":"IN: Robot E-Stop",
        "description":"Ingolstadt BodyShop WeldRobot01 E-Stop. Collision protection triggered.",
        "color":"red","fault_key":"body_shop_robot1_collision","location":"Ingolstadt",
        "affected":["IN-BS-ROB1-CURR","IN-BS-ROB1-WELD-FORCE","IN-BS-ROB1-STATUS","IN-BS-KPI"],
        "stop_publishing":False,
    },
    "cross_site_erp_disruption": {
        "id":"cross_site_erp_disruption","label":"ALL: ERP Disruption",
        "description":"SAP S/4HANA disruption. Production orders delayed across all sites.",
        "color":"red","fault_key":None,"location":"all",
        "affected":["FR-ERP-ORDER","FR-ERP-MATERIAL","MU-ERP-ORDER","IN-ERP-ORDER"],
        "stop_publishing":True,
    },
}
