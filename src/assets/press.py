"""Press asset — hydraulic press (PR01, PR02)."""
from __future__ import annotations
import random
from .base import AssetBase, AssetState, _now, jitter, clamp

FAULT_META = {
    "hydraulic_pressure_low": {"code":"E-PRESS-002","name":"Hydraulic Pressure Low","severity":"critical","description":"System hydraulic pressure dropped below minimum"},
    "oil_overtemperature":     {"code":"E-PRESS-003","name":"Oil Overtemperature","severity":"critical","description":"Hydraulic oil temperature exceeds 75°C limit"},
    "seal_leak":               {"code":"E-PRESS-004","name":"Hydraulic Seal Leak","severity":"warning","description":"Oil leak detected on main cylinder seal"},
    "press_force_deviation":   {"code":"E-PRESS-005","name":"Press Force Deviation","severity":"warning","description":"Press force deviates more than 5% from setpoint"},
}

class PressAsset(AssetBase):
    ASSET_TYPE = "press"

    def __init__(self, asset_id, line, cell, cfg, sim_cfg):
        super().__init__(asset_id, line, cell, cfg, sim_cfg)
        self._pressure   = cfg.get("nominal_pressure_bar", 210)
        self._oil_temp   = cfg.get("nominal_oil_temp_c", 50)
        self._force      = cfg.get("nominal_force_kn", 750)
        self._stroke     = 250.0
        self._oee        = round(random.uniform(68, 82), 1)
        self._kwh_total  = random.randint(10000, 20000)
        self._components = {
            "HydraulicPump": {"score": random.uniform(50,95), "rul_days": random.randint(30,600), "deg": random.uniform(0.02,1.0)},
            "MainSeal":      {"score": random.uniform(60,98), "rul_days": random.randint(90,400), "deg": random.uniform(0.05,0.5)},
            "Accumulator":   {"score": random.uniform(75,99), "rul_days": random.randint(200,700), "deg": random.uniform(0.01,0.1)},
            "PressGuide":    {"score": random.uniform(80,99), "rul_days": random.randint(300,800), "deg": random.uniform(0.01,0.05)},
        }
        self._fault_pressure_offset = 0
        self._fault_temp_offset     = 0
        self._fault_force_offset    = 0
        self._seq = random.randint(100,200)

    def _fault_meta(self, fault_name):
        return FAULT_META.get(fault_name, super()._fault_meta(fault_name))

    def apply_fault(self, fault_name):
        if fault_name == "hydraulic_pressure_low": self._fault_pressure_offset = -30
        elif fault_name == "oil_overtemperature":   self._fault_temp_offset     = +30
        elif fault_name == "seal_leak":             self._fault_pressure_offset = -15
        elif fault_name == "press_force_deviation": self._fault_force_offset    = +80

    def recover_fault(self, fault_name):
        self._fault_pressure_offset = 0
        self._fault_temp_offset     = 0
        self._fault_force_offset    = 0

    def _live_pressure(self):
        nom = self.cfg.get("nominal_pressure_bar", 210)
        return round(clamp(jitter(nom + self._fault_pressure_offset, 0.02), 150, 230))

    def _live_temp(self):
        nom = self.cfg.get("nominal_oil_temp_c", 50)
        return round(clamp(jitter(nom + self._fault_temp_offset, 0.03), 35, 90))

    def _live_force(self):
        nom = self.cfg.get("nominal_force_kn", 750)
        return round(clamp(jitter(nom + self._fault_force_offset, 0.04), 600, 900))

    def _live_stroke(self):
        self._stroke = (self._stroke + random.uniform(-50, 50)) % 500
        return round(self._stroke)

    def telemetry_messages(self):
        if not self.is_running:
            return []
        self._seq += 1
        status = "fault" if self.state == AssetState.FAULT else "normal"
        msgs = []
        for metric, value, unit in [
            ("hydraulic_pressure", self._live_pressure(), "bar"),
            ("oil_temperature",    self._live_temp(),     "degC"),
            ("press_force",        self._live_force(),    "kN"),
            ("stroke_position",    self._live_stroke(),   "mm"),
        ]:
            msgs.append((
                f"{self._base_topic}/telemetry/{metric}",
                {"timestamp":_now(),"asset_id":self.asset_id,"unit":unit,"value":value,
                 "status":status,"quality":"good","seq":self._seq}
            ))
        return msgs

    def performance_message(self):
        if not self.is_running: return None
        self._cycle_count += random.randint(1,3)
        self._kwh_total   += round(random.uniform(0.05, 0.2), 2)
        ct = self.cfg.get("cycle_time_s", 8)
        ct_actual = round(ct * random.uniform(0.95, 1.15), 1)
        return (
            f"{self._base_topic}/performance",
            {"timestamp":_now(),"asset_id":self.asset_id,
             "operational_status": self.state.value,
             "oee": self._oee,"availability": round(self._oee/random.uniform(0.92,0.98),1),
             "performance_kpi": round(random.uniform(90,98),1),
             "quality": round(random.uniform(94,99),1),
             "cycle_time_s": ct_actual,"cycle_time_target_s": ct,
             "cycle_count": self._cycle_count,
             "production_rate_per_hr": round(3600/ct_actual),
             "fault_code": self.active_alarms[0].alarm_code if self.active_alarms else "",
             "fault_description": self.active_alarms[0].description if self.active_alarms else "",
             "fault_count_24h": len(self.active_alarms),
             "fault_count_7d": len(self.active_alarms)*3,
             "current_product":"BAT-CASE-AL-001","current_batch":"BATCH-AUTO","current_shift":"Shift A"}
        )

    def energy_message(self):
        if not self.is_running: return None
        kw = round(jitter(16.8, 0.05), 1)
        self._kwh_total = round(self._kwh_total + kw * (30/3600), 1)
        return (
            f"{self._base_topic}/energy",
            {"timestamp":_now(),"asset_id":self.asset_id,
             "current_power_kw":kw,"total_energy_kwh":self._kwh_total,
             "power_factor":round(jitter(0.85,0.02),2),
             "voltage_v":400,"energy_per_cycle_wh":round(jitter(55.5,0.04),1)}
        )

    def health_message(self):
        components = {}
        for name, c in self._components.items():
            c["score"] = round(clamp(c["score"] - c["deg"]/288, 0, 100), 1)
            c["rul_days"] = max(0, c["rul_days"] - 1/288)
            components[name] = {"score":round(c["score"],1),"rul_days":round(c["rul_days"]),"degradation_rate_pct_per_day":c["deg"]}
        return (f"{self._base_topic}/health",
                {"timestamp":_now(),"asset_id":self.asset_id,"components":components})
