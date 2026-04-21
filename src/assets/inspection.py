"""Inspection asset — vision CMM + leak/pressure test."""
from __future__ import annotations
import random
from .base import AssetBase, _now

FAULT_META = {
    "camera_calibration_drift": {"code":"E-INS-001","name":"Camera Calibration Drift","severity":"warning","description":"Vision system calibration drift — accuracy reduced"},
    "lighting_failure":          {"code":"E-INS-002","name":"Lighting Failure","severity":"critical","description":"Inspection lighting array failure"},
    "pressure_decay_sensor_fault":{"code":"E-INS-003","name":"Pressure Decay Sensor Fault","severity":"critical","description":"Leak test pressure sensor out of range"},
    "fixture_seal_wear":          {"code":"E-INS-004","name":"Fixture Seal Wear","severity":"warning","description":"Test fixture seal degraded — false pass risk"},
}

class InspectionAsset(AssetBase):
    ASSET_TYPE = "inspection"
    def __init__(self, asset_id, line, cell, cfg, sim_cfg):
        super().__init__(asset_id, line, cell, cfg, sim_cfg)
        self._pass_rate     = cfg.get("pass_rate", 0.97)
        self._triggers_dpp  = cfg.get("triggers_dpp", False)
        self._method        = cfg.get("method", "generic")
        self._units_tested  = 0
        self._units_passed  = 0

    def _fault_meta(self, f): return FAULT_META.get(f, super()._fault_meta(f))

    def inspect_unit(self, product_id: str, lot_id: str) -> bool:
        """Return True if unit passes inspection."""
        self._units_tested += 1
        passed = random.random() < self._pass_rate
        if passed: self._units_passed += 1
        return passed

    def telemetry_messages(self):
        if not self.is_running: return []
        return [(f"{self._base_topic}/status",
                 {"timestamp":_now(),"asset_id":self.asset_id,
                  "state":self.state.value,"method":self._method,
                  "units_tested":self._units_tested,"units_passed":self._units_passed,
                  "pass_rate":round(self._units_passed/max(1,self._units_tested),3)})]
