"""Oven asset — 4-zone convection curing oven (OV01)."""
from __future__ import annotations
import random
from .base import AssetBase, AssetState, _now, jitter, clamp

FAULT_META = {
    "zone_heater_failure":  {"code":"E-OVEN-001","name":"Zone Heater Failure","severity":"critical","description":"Zone heater element failure detected"},
    "fan_bearing_wear":     {"code":"E-OVEN-002","name":"Fan Bearing Wear","severity":"warning","description":"Air circulation fan bearing vibration elevated"},
    "exhaust_blockage":     {"code":"E-OVEN-003","name":"Exhaust Blockage","severity":"warning","description":"Exhaust duct partial blockage detected"},
    "temperature_overshoot":{"code":"E-OVEN-004","name":"Temperature Overshoot","severity":"critical","description":"Zone temperature exceeded safe limit"},
}

class OvenAsset(AssetBase):
    ASSET_TYPE = "oven"
    def __init__(self, asset_id, line, cell, cfg, sim_cfg):
        super().__init__(asset_id, line, cell, cfg, sim_cfg)
        self._n_zones   = cfg.get("zones", 4)
        self._nom_temps = cfg.get("nominal_zone_temp_c", [180,200,200,170])
        self._nom_fan   = cfg.get("nominal_fan_rpm", 1450)
        self._temps     = list(self._nom_temps)
        self._fan_rpm   = float(self._nom_fan)
        self._exhaust   = 85.0
        self._power_kw  = 45.0
        self._kwh_total = random.randint(5000, 50000)
        self._fault_zone = None
        self._fault_fan_offset = 0
        self._fault_temp_offset = 0
        self._components = {
            "Zone1Heater": {"score":random.uniform(70,99),"rul_days":random.randint(200,1000),"deg":0.02},
            "Zone2Heater": {"score":random.uniform(70,99),"rul_days":random.randint(200,1000),"deg":0.02},
            "FanAssembly":  {"score":random.uniform(60,95),"rul_days":random.randint(90,500),"deg":0.05},
            "ExhaustSystem":{"score":random.uniform(75,99),"rul_days":random.randint(300,800),"deg":0.01},
        }

    def _fault_meta(self, f): return FAULT_META.get(f, super()._fault_meta(f))
    def apply_fault(self, f):
        if f == "zone_heater_failure": self._fault_zone = random.randint(0,3)
        elif f == "fan_bearing_wear":  self._fault_fan_offset = -300
        elif f == "exhaust_blockage":  self._fault_temp_offset = +15
        elif f == "temperature_overshoot": self._fault_temp_offset = +25
    def recover_fault(self, f):
        self._fault_zone=None; self._fault_fan_offset=0; self._fault_temp_offset=0

    def telemetry_messages(self):
        if not self.is_running: return []
        msgs = []
        for i, nom in enumerate(self._nom_temps):
            t = nom + self._fault_temp_offset if self._fault_zone is None or self._fault_zone != i else nom * 0.4
            self._temps[i] = round(clamp(jitter(t, 0.01), 50, 260), 1)
            msgs.append((f"{self._base_topic}/telemetry/zone{i+1}_temperature",
                         {"timestamp":_now(),"asset_id":self.asset_id,"unit":"degC","value":self._temps[i]}))
        fan = clamp(jitter(self._nom_fan + self._fault_fan_offset, 0.02), 200, 1600)
        self._fan_rpm = round(fan)
        msgs.append((f"{self._base_topic}/telemetry/fan_speed",
                     {"timestamp":_now(),"asset_id":self.asset_id,"unit":"RPM","value":self._fan_rpm}))
        exhaust = clamp(jitter(85 + self._fault_temp_offset*0.5, 0.03), 40, 150)
        msgs.append((f"{self._base_topic}/telemetry/exhaust_temperature",
                     {"timestamp":_now(),"asset_id":self.asset_id,"unit":"degC","value":round(exhaust,1)}))
        power = clamp(jitter(45 if self._fault_zone is None else 38, 0.04), 20, 65)
        msgs.append((f"{self._base_topic}/telemetry/power_consumption",
                     {"timestamp":_now(),"asset_id":self.asset_id,"unit":"kW","value":round(power,1)}))
        return msgs

    def performance_message(self):
        if not self.is_running: return None
        ct = self.cfg.get("cycle_time_s", 1200)
        return (f"{self._base_topic}/performance",
                {"timestamp":_now(),"asset_id":self.asset_id,
                 "operational_status":self.state.value,
                 "oee":round(random.uniform(72,88),1),
                 "cycle_time_s":round(ct*random.uniform(0.97,1.05)),
                 "cycle_time_target_s":ct,
                 "zone_temps":self._temps,
                 "current_product":"BAT-CASE-AL-001"})

    def energy_message(self):
        if not self.is_running: return None
        kw = round(jitter(45.0, 0.05), 1)
        self._kwh_total = round(self._kwh_total + kw*(30/3600), 1)
        return (f"{self._base_topic}/energy",
                {"timestamp":_now(),"asset_id":self.asset_id,
                 "current_power_kw":kw,"total_energy_kwh":self._kwh_total,
                 "power_factor":round(jitter(0.92,0.02),2),"voltage_v":400})

    def health_message(self):
        components = {}
        for name, c in self._components.items():
            c["score"] = round(clamp(c["score"]-c["deg"]/288, 0, 100), 1)
            c["rul_days"] = max(0, c["rul_days"]-1/288)
            components[name] = {"score":c["score"],"rul_days":round(c["rul_days"]),"degradation_rate_pct_per_day":c["deg"]}
        return (f"{self._base_topic}/health",
                {"timestamp":_now(),"asset_id":self.asset_id,"components":components})
