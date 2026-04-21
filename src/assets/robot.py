"""Robot asset — welding / material handling / spray robots."""
from __future__ import annotations
import random
from .base import AssetBase, AssetState, _now

FAULT_META = {
    "position_error":    {"code":"E-ROB-001","name":"Position Error","severity":"critical","description":"End-effector position error exceeds tolerance"},
    "teach_point_drift": {"code":"E-ROB-002","name":"Teach Point Drift","severity":"warning","description":"Teach point offset detected — calibration required"},
    "collision":         {"code":"E-ROB-003","name":"Collision Detected","severity":"critical","description":"Collision sensor triggered — emergency stop"},
}

class RobotAsset(AssetBase):
    ASSET_TYPE = "robot"
    def __init__(self, asset_id, line, cell, cfg, sim_cfg):
        super().__init__(asset_id, line, cell, cfg, sim_cfg)
        self._task = cfg.get("task", "Generic")

    def _fault_meta(self, f): return FAULT_META.get(f, super()._fault_meta(f))

    def telemetry_messages(self):
        state = "Faulted" if self.state == AssetState.FAULT else self.state.value
        return [(f"{self._base_topic}/status",
                 {"state":state,"task":self._task,"timestamp":int(random.uniform(1.77e12,1.78e12))})]
