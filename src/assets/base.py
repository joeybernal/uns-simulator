"""
Base asset class — shared state machine and publish helpers.
Every asset type (press, oven, conveyor, robot, sprayer, inspection)
inherits from AssetBase.
"""
from __future__ import annotations
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

log = logging.getLogger("simulator.asset")


class AssetState(str, Enum):
    IDLE        = "Idle"
    RUNNING     = "Running"
    FAULT       = "Faulted"
    MAINTENANCE = "Maintenance"
    WARMUP      = "WarmUp"


@dataclass
class ActiveAlarm:
    alarm_id:    str
    alarm_code:  str
    alarm_name:  str
    severity:    str          # info | warning | critical
    raised_at:   str
    acknowledged: bool = False
    description: str = ""


class AssetBase:
    """
    Base class for all simulated Aurora assets.

    Subclasses must implement:
      - telemetry_messages() → list[(topic_suffix, payload_dict)]
      - performance_message() → (topic_suffix, payload_dict) | None
      - energy_message()      → (topic_suffix, payload_dict) | None
      - health_message()      → (topic_suffix, payload_dict) | None
      - apply_fault(fault_name)
      - recover_fault(fault_name)
    """

    ASSET_TYPE = "generic"

    def __init__(self, asset_id: str, line: str, cell: str, cfg: dict, sim_cfg: dict):
        self.asset_id   = asset_id
        self.line       = line
        self.cell       = cell
        self.cfg        = cfg
        self.sim_cfg    = sim_cfg

        self.state: AssetState = AssetState.IDLE
        self.active_alarms: list[ActiveAlarm] = []
        self.fault_start: float | None = None
        self.active_fault_name: str | None = None

        self._alarm_counter = 0
        self._cycle_count   = random.randint(100_000, 600_000)
        self._health_scores: dict[str, float] = {}

        self._base_topic = f"aurora/{line}/{cell}/assets/{asset_id}"

    # ── State helpers ─────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self.state == AssetState.RUNNING

    def start(self):
        if self.state == AssetState.IDLE:
            self.state = AssetState.RUNNING
            log.info(f"[{self.asset_id}] started")

    def stop(self):
        if self.state == AssetState.RUNNING:
            self.state = AssetState.IDLE
            log.info(f"[{self.asset_id}] stopped")

    # ── Fault injection ───────────────────────────────────────────────────────

    def inject_fault(self, fault_name: str):
        """Transition to FAULT state and raise an alarm."""
        if self.state == AssetState.FAULT:
            return   # already faulted
        log.warning(f"[{self.asset_id}] FAULT injected: {fault_name}")
        self.state = AssetState.FAULT
        self.active_fault_name = fault_name
        self.fault_start = time.time()
        self._raise_alarm(fault_name)
        self.apply_fault(fault_name)

    def tick_recovery(self):
        """Called every tick — auto-recover after recovery_time_s."""
        if self.state != AssetState.FAULT:
            return
        recovery_s = self.sim_cfg.get("recovery_time_s", 300)
        if self.fault_start and (time.time() - self.fault_start) >= recovery_s:
            log.info(f"[{self.asset_id}] recovering from {self.active_fault_name}")
            if self.active_fault_name:
                self.recover_fault(self.active_fault_name)
                self._clear_alarms()
            self.state = AssetState.RUNNING
            self.active_fault_name = None
            self.fault_start = None

    def _raise_alarm(self, fault_name: str):
        self._alarm_counter += 1
        fault_meta = self._fault_meta(fault_name)
        alarm = ActiveAlarm(
            alarm_id    = f"ALM-{self.asset_id.upper()}-{self._alarm_counter:03d}",
            alarm_code  = fault_meta["code"],
            alarm_name  = fault_meta["name"],
            severity    = fault_meta["severity"],
            raised_at   = _now(),
            description = fault_meta["description"],
        )
        self.active_alarms.append(alarm)

    def _clear_alarms(self):
        self.active_alarms.clear()

    def _fault_meta(self, fault_name: str) -> dict:
        """Subclasses override to provide alarm metadata per fault."""
        return {
            "code": f"E-GENERIC-001",
            "name": fault_name.replace("_", " ").title(),
            "severity": "warning",
            "description": f"Fault: {fault_name}",
        }

    # ── Message builders ──────────────────────────────────────────────────────

    def alarms_message(self) -> tuple[str, dict]:
        topic = f"{self._base_topic}/alarms"
        payload = {
            "timestamp": _now(),
            "asset_id": self.asset_id,
            "active_alarms": [
                {
                    "alarm_id":    a.alarm_id,
                    "alarm_code":  a.alarm_code,
                    "alarm_name":  a.alarm_name,
                    "severity":    a.severity,
                    "raised_at":   a.raised_at,
                    "acknowledged": a.acknowledged,
                    "description": a.description,
                }
                for a in self.active_alarms
            ],
        }
        return topic, payload

    # ── Abstract interface ────────────────────────────────────────────────────

    def telemetry_messages(self) -> list[tuple[str, Any]]:
        return []

    def performance_message(self) -> tuple[str, dict] | None:
        return None

    def energy_message(self) -> tuple[str, dict] | None:
        return None

    def health_message(self) -> tuple[str, dict] | None:
        return None

    def apply_fault(self, fault_name: str):
        pass

    def recover_fault(self, fault_name: str):
        pass


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def jitter(value: float, pct: float = 0.03) -> float:
    """Add ±pct Gaussian jitter to a value."""
    return value * (1 + random.gauss(0, pct))


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
