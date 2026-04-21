"""
Factory Orchestrator — loads config, builds assets, runs tick loops.
"""
from __future__ import annotations
import json, logging, math, os, random, time
from datetime import datetime, timezone
from pathlib import Path
import yaml
import paho.mqtt.client as mqtt

from ..assets.base  import AssetState, _now
from ..assets.press      import PressAsset
from ..assets.oven       import OvenAsset
from ..assets.conveyor   import ConveyorAsset
from ..assets.robot      import RobotAsset
from ..assets.sprayer    import SprayerAsset
from ..assets.inspection import InspectionAsset

log = logging.getLogger("simulator.factory")

ASSET_CLASSES = {
    "press":      PressAsset,
    "oven":       OvenAsset,
    "conveyor":   ConveyorAsset,
    "robot":      RobotAsset,
    "sprayer":    SprayerAsset,
    "inspection": InspectionAsset,
}

_PROCESS_STEPS = [
    "press_cycle", "conveyor_transfer", "paint_cycle",
    "oven_dwell", "cool_down", "inspection_vision", "inspection_leak",
]


class FactoryOrchestrator:
    def __init__(self, config_path: str | Path):
        self._cfg  = self._load_config(config_path)
        self._fcfg = self._cfg["factory"]
        self._mcfg = self._cfg["mqtt"]
        self._scfg = self._cfg["simulation"]

        self._assets: list = []          # flat list of all assets
        self._inspection_assets: list = []  # assets with triggers_dpp=True
        self._client: mqtt.Client | None = None
        self._running = False
        self._batch_seq   = 1
        self._unit_seq    = 1
        self._energy_total = 0.0
        self._tick_count   = 0

        self._build_assets()

    # ── Config loading ─────────────────────────────────────────────────────────

    @staticmethod
    def _load_config(path) -> dict:
        raw = Path(path).read_text()
        # simple env-var substitution: ${VAR:default}
        import re
        def _sub(m):
            var, default = m.group(1), m.group(2)
            return os.environ.get(var, default)
        raw = re.sub(r'\$\{(\w+):([^}]*)\}', _sub, raw)
        return yaml.safe_load(raw)

    # ── Asset factory ──────────────────────────────────────────────────────────

    def _build_assets(self):
        sim_cfg = self._scfg
        for line_name, line_data in self._cfg["lines"].items():
            for cell_name, cell_data in (line_data.get("cells") or {}).items():
                for asset_id, asset_cfg in (cell_data.get("assets") or {}).items():
                    atype = asset_cfg.get("type", "generic")
                    cls   = ASSET_CLASSES.get(atype)
                    if not cls:
                        log.warning(f"Unknown asset type '{atype}' for {asset_id}")
                        continue
                    asset = cls(asset_id, line_name, cell_name, asset_cfg, sim_cfg)
                    asset.start()
                    self._assets.append(asset)
                    if getattr(asset, "_triggers_dpp", False):
                        self._inspection_assets.append(asset)
                    log.info(f"  + {asset_id:30s} [{atype}]  {line_name}/{cell_name}")

    # ── MQTT ───────────────────────────────────────────────────────────────────

    def _connect(self):
        host = self._mcfg.get("host", "localhost")
        port = int(self._mcfg.get("port", 1883))
        user = self._mcfg.get("username", "")
        pw   = self._mcfg.get("password", "")
        cid  = self._mcfg.get("client_id", "aurora-simulator")

        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=cid,
            protocol=mqtt.MQTTv5,
        )
        if user:
            self._client.username_pw_set(user, pw)

        def on_connect(c, ud, flags, rc, props=None):
            if rc == 0:
                log.info(f"Connected to Mosquitto at {host}:{port}")
                # Subscribe to MES commands
                c.subscribe("aurora/+/mes/commands/#", qos=0)
            else:
                log.error(f"MQTT connection refused rc={rc}")

        def on_message(c, ud, msg):
            self._handle_mes_command(msg.topic, msg.payload)

        self._client.on_connect = on_connect
        self._client.on_message = on_message
        self._client.connect(host, port, keepalive=60)
        self._client.loop_start()

    def _pub(self, topic: str, payload):
        if self._client is None:
            return
        if isinstance(payload, (dict, list)):
            data = json.dumps(payload)
        else:
            data = str(payload)
        self._client.publish(topic, data, qos=self._mcfg.get("qos", 0))

    # ── MES command handler ────────────────────────────────────────────────────

    def _handle_mes_command(self, topic: str, raw: bytes):
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
        cmd_id = f"cmd-{int(time.time()*1000)}"
        parts  = topic.split("/")
        line   = parts[1] if len(parts) > 1 else "unknown"

        if topic.endswith("/line_start"):
            log.info(f"[MES] line_start on {line}")
            for a in self._assets:
                if a.line == line and a.state == AssetState.IDLE:
                    a.start()
            ack_topic = f"aurora/{line}/mes/ack/{cmd_id}"
            self._pub(ack_topic, {"cmd_id": cmd_id, "status": "accepted", "timestamp": _now()})

        elif topic.endswith("/line_stop"):
            log.info(f"[MES] line_stop on {line}")
            for a in self._assets:
                if a.line == line and a.state == AssetState.RUNNING:
                    a.stop()
            ack_topic = f"aurora/{line}/mes/ack/{cmd_id}"
            self._pub(ack_topic, {"cmd_id": cmd_id, "status": "accepted", "timestamp": _now()})

    # ── Process flow ───────────────────────────────────────────────────────────

    def _emit_step_status(self, line: str, cell: str, step: str, status: str):
        product_id = f"SKU-{self._unit_seq % 100}"
        lot_id     = f"LOT-{(self._unit_seq // 100) + 1}"
        self._pub(
            f"aurora/{line}/{cell}/process/step_status",
            {"timestamp": _now(), "product_id": product_id,
             "lot_id": lot_id, "step": step, "status": status},
        )

    def _emit_batch_complete(self):
        batch_id   = f"BATCH-{datetime.now().strftime('%Y-%m%d')}-{self._batch_seq:03d}"
        lot_id     = f"LOT-{self._batch_seq}"
        batch_size = self._fcfg.get("batch_size", 50)
        self._batch_seq += 1
        log.info(f"[BATCH] {batch_id} inspection PASS → DPP trigger")
        self._pub("aurora/line_04_inspection/cell_02/process/step_status", {
            "timestamp":  _now(),
            "event":      "batch_complete",
            "batch_id":   batch_id,
            "lot_id":     lot_id,
            "product":    self._fcfg.get("product", "BAT-CASE-AL-001"),
            "qty_passed": batch_size,
            "step":       "inspection",
            "status":     "complete",
            "result":     "pass",
        })

    # ── Fault injection scheduler ──────────────────────────────────────────────

    def _maybe_inject_fault(self):
        fph  = self._scfg.get("fault_probability_per_hour", 0.15)
        tick = self._scfg.get("tick_s", 5)
        # probability per tick  =  fph / (3600 / tick_s)
        prob_per_tick = fph / (3600 / tick)
        for asset in self._assets:
            if asset.state == AssetState.RUNNING and random.random() < prob_per_tick:
                faults = asset.cfg.get("faults", [])
                if faults:
                    asset.inject_fault(random.choice(faults))

    # ── Main loop ──────────────────────────────────────────────────────────────

    def run(self):
        log.info("=" * 60)
        log.info(f"  Aurora UNS Simulator  —  {self._fcfg.get('name')}")
        log.info(f"  Assets: {len(self._assets)}  |  Lines: {len(self._cfg['lines'])}")
        log.info("=" * 60)

        self._connect()
        self._running = True

        tick_s      = self._scfg.get("tick_s", 5)
        slow_tick_s = self._scfg.get("slow_tick_s", 30)
        alarm_tick_s= self._scfg.get("alarm_tick_s", 60)

        last_slow  = 0.0
        last_alarm = 0.0
        last_step  = 0.0
        last_batch = 0.0
        last_stats = 0.0

        msgs_published = 0

        try:
            while self._running:
                t0  = time.time()
                now = t0
                self._tick_count += 1

                # ── Telemetry tick (every tick_s) ──────────────────────────
                for asset in self._assets:
                    asset.tick_recovery()
                    for topic, payload in asset.telemetry_messages():
                        self._pub(topic, payload)
                        msgs_published += 1

                # ── Fault injection ────────────────────────────────────────
                self._maybe_inject_fault()

                # ── Slow tick: performance / energy / health ───────────────
                if now - last_slow >= slow_tick_s:
                    last_slow = now
                    for asset in self._assets:
                        for fn in [asset.performance_message, asset.energy_message, asset.health_message]:
                            result = fn()
                            if result:
                                self._pub(result[0], result[1])
                                msgs_published += 1
                    # Cell-level energy rollup
                    for line_name in self._cfg["lines"]:
                        for cell_name in (self._cfg["lines"][line_name].get("cells") or {}):
                            self._pub(f"aurora/{line_name}/{cell_name}/energy/power",
                                      {"value": round(random.uniform(3,8),2),
                                       "unit":"kWh","timestamp":_now(),
                                       "unit_id":f"UNIT{self._tick_count}"})
                            self._pub(f"aurora/{line_name}/{cell_name}/process/cycle_time",
                                      {"value": random.randint(45,75),"unit":"s",
                                       "timestamp":_now(),"unit_id":f"UNIT{self._tick_count}"})
                            msgs_published += 2
                    # Plant energy total
                    self._energy_total += round(random.uniform(9,13),2)
                    self._pub("aurora/energy/energy_total",
                              {"value":str(round(self._energy_total,2)),"unit":"kWh",
                               "timestamp":_now(),"unit_id":f"UNIT{self._tick_count}"})
                    # Plant-level process
                    self._pub("aurora/process/cycle_time",
                              {"value":random.randint(45,75),"unit":"s","timestamp":_now(),"unit_id":f"UNIT{self._tick_count}"})
                    self._pub("aurora/process/unit_id",
                              {"value":f"SKU-{self._unit_seq}","timestamp":_now()})
                    msgs_published += 3

                # ── Alarm tick ─────────────────────────────────────────────
                if now - last_alarm >= alarm_tick_s:
                    last_alarm = now
                    for asset in self._assets:
                        topic, payload = asset.alarms_message()
                        self._pub(topic, payload)
                        msgs_published += 1
                    # Line-level alarm summary
                    alarms_with_active = [a for a in self._assets if a.active_alarms]
                    if alarms_with_active:
                        a = random.choice(alarms_with_active)
                        al = a.active_alarms[0]
                        self._pub("aurora/line_01_assembly/alarms/current",
                                  {"timestamp":_now(),"asset":a.asset_id,
                                   "alarm":al.alarm_code,"severity":al.severity})

                # ── Process step events (every ~15s) ──────────────────────
                if now - last_step >= 15:
                    last_step = now
                    self._unit_seq += 1
                    step = random.choice(_PROCESS_STEPS)
                    status = random.choice(["start","complete"])
                    self._emit_step_status("line_01_assembly","cell_01", step, status)
                    self._emit_step_status("line_02_painting","cell_01","paint_cycle",status)
                    self._emit_step_status("line_03_curing","cell_01","oven_dwell",status)

                # ── Batch complete (every ~5 min) ─────────────────────────
                if now - last_batch >= 300:
                    last_batch = now
                    self._emit_batch_complete()

                # ── Stats log ──────────────────────────────────────────────
                if now - last_stats >= 60:
                    last_stats = now
                    log.info(f"Tick {self._tick_count:6d}  |  msgs published: {msgs_published}")

                # ── Sleep remainder of tick ────────────────────────────────
                elapsed = time.time() - t0
                if elapsed < tick_s:
                    time.sleep(tick_s - elapsed)

        except KeyboardInterrupt:
            log.info("Simulator stopped by user.")
        finally:
            if self._client:
                self._client.loop_stop()
                self._client.disconnect()
