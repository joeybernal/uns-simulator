"""Sprayer asset — electrostatic paint sprayer SP02."""
from __future__ import annotations
import random
from .base import AssetBase, _now, jitter, clamp

FAULT_META = {
    "filter_blocked": {"code":"E-SP-001","name":"Filter Blocked","severity":"warning","description":"Paint filter pressure drop exceeds limit"},
    "pressure_drop":  {"code":"E-SP-002","name":"Pressure Drop","severity":"critical","description":"Supply pressure below minimum for atomisation"},
    "nozzle_clog":    {"code":"E-SP-003","name":"Nozzle Clog","severity":"warning","description":"Nozzle partial blockage detected"},
}

class SprayerAsset(AssetBase):
    ASSET_TYPE = "sprayer"
    def __init__(self, asset_id, line, cell, cfg, sim_cfg):
        super().__init__(asset_id, line, cell, cfg, sim_cfg)
        self._nom_pressure = cfg.get("nominal_pressure_bar", 3.5)
        self._fault_pressure_factor = 1.0
        self._filter_ok = True

    def _fault_meta(self, f): return FAULT_META.get(f, super()._fault_meta(f))
    def apply_fault(self, f):
        if f == "filter_blocked": self._filter_ok = False
        elif f == "pressure_drop": self._fault_pressure_factor = 0.5
        elif f == "nozzle_clog":   self._fault_pressure_factor = 0.75
    def recover_fault(self, f): self._fault_pressure_factor=1.0; self._filter_ok=True

    def telemetry_messages(self):
        if not self.is_running: return []
        p = round(clamp(jitter(self._nom_pressure * self._fault_pressure_factor, 0.03), 0.5, 6.0), 2)
        filter_status = "OK" if self._filter_ok else "BLOCKED"
        return [
            (f"{self._base_topic}/telemetry/Transducer_PT01", {"value":p,"unit":"bar","timestamp":_now()}),
            (f"{self._base_topic}/telemetry/FilterStatus",    {"status":filter_status,"timestamp":_now()}),
        ]
