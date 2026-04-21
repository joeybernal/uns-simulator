"""Conveyor asset — belt conveyors CV01–CV04."""
from __future__ import annotations
import random
from .base import AssetBase, _now, jitter, clamp

FAULT_META = {
    "belt_slip":     {"code":"E-CV-001","name":"Belt Slip","severity":"warning","description":"Belt slip detected — speed below setpoint"},
    "motor_overload":{"code":"E-CV-002","name":"Motor Overload","severity":"critical","description":"Drive motor current exceeds rated limit"},
    "jam":           {"code":"E-CV-003","name":"Conveyor Jam","severity":"critical","description":"Obstruction detected — belt stopped"},
}

class ConveyorAsset(AssetBase):
    ASSET_TYPE = "conveyor"
    def __init__(self, asset_id, line, cell, cfg, sim_cfg):
        super().__init__(asset_id, line, cell, cfg, sim_cfg)
        self._nom_speed  = cfg.get("nominal_speed_ms", 2.0)
        self._speed      = self._nom_speed
        self._fault_speed_factor = 1.0
        self._phase_v    = 400
        self._phase_a    = 10.0
        self._pf         = 0.95

    def _fault_meta(self, f): return FAULT_META.get(f, super()._fault_meta(f))
    def apply_fault(self, f):
        if f == "belt_slip":      self._fault_speed_factor = 0.6
        elif f == "motor_overload": self._fault_speed_factor = 0.3
        elif f == "jam":            self._fault_speed_factor = 0.0
    def recover_fault(self, f): self._fault_speed_factor = 1.0

    def telemetry_messages(self):
        if not self.is_running: return []
        speed = round(clamp(jitter(self._nom_speed * self._fault_speed_factor, 0.03), 0, self._nom_speed*1.1), 2)
        msgs = [(f"{self._base_topic}/telemetry/speed",
                 {"speed":speed,"unit":"m/s","timestamp":int(random.uniform(1.77e12,1.78e12))})]
        for ph in ["phaseA","phaseB","phaseC"]:
            msgs.append((f"{self._base_topic}/telemetry/power/{ph}/voltage", round(jitter(400,0.01))))
            msgs.append((f"{self._base_topic}/telemetry/power/{ph}/current", round(jitter(10*self._fault_speed_factor,0.05),1)))
        msgs.append((f"{self._base_topic}/telemetry/power/powerFactor", round(jitter(0.95,0.02),2)))
        return msgs
