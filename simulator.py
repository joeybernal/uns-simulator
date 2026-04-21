"""
UNS Simulator — IoTAuto GmbH
FastAPI + WebSocket live feed + MQTT publisher

Three plants: Frankfurt Paint Shop | Munich Assembly | Ingolstadt Press+Body Shop
91 streams | ISA-95 hierarchy | PLC / MES / ERP / SCADA sources
"""
import asyncio
import contextlib
import json
import os
import random
import threading
import time
from collections import deque
from typing import Dict, Optional, Set

import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from uns_model import STREAMS, FAULT_SCENARIOS, STREAM_BY_ID

# ─────────────────────────────────────────────────────────────────────────────
# Config  (all overridable via env vars in the ECS task definition)
# ─────────────────────────────────────────────────────────────────────────────
MQTT_HOST   = os.getenv("MQTT_HOST",   "mqtt.iotdemozone.com")
MQTT_PORT   = int(os.getenv("MQTT_PORT",   "1883"))
MQTT_USER   = os.getenv("MQTT_USER",   "admin")
MQTT_PASS   = os.getenv("MQTT_PASS",   "28luXF7q")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))
# If SIM_API_KEY is set, all non-health requests must supply it as X-API-Key.
# Leave unset (or empty) to run without auth (local dev default).
SIM_API_KEY = os.getenv("SIM_API_KEY", "").strip()

# TerminusDB — optional graph context layer
TERMINUS_URL  = os.getenv("TERMINUS_URL",  "").strip()
TERMINUS_USER = os.getenv("TERMINUS_USER", "admin").strip()
TERMINUS_PASS = os.getenv("TERMINUS_PASS", "").strip()
TERMINUS_TEAM = os.getenv("TERMINUS_TEAM", "admin").strip()
TERMINUS_DB   = os.getenv("TERMINUS_DB",   "aurora").strip()

# ─────────────────────────────────────────────────────────────────────────────
# Simulator state
# ─────────────────────────────────────────────────────────────────────────────
class SimulatorState:
    def __init__(self):
        self.running          = True        # auto-start on boot
        self.mqtt_connected   = False
        self.active_scenario  = "normal"
        self.total_published  = 0
        self.start_time       = time.time()
        self.shift            = "A"

        self.stream_running:   Dict[str, bool]  = {s["id"]: True for s in STREAMS}
        self.stream_values:    Dict[str, str]   = {}
        self.stream_last_ts:   Dict[str, float] = {}
        self.stream_pub_count: Dict[str, int]   = {s["id"]: 0 for s in STREAMS}

        self.recent_messages: deque = deque(maxlen=200)
        self._rate_window:    deque = deque(maxlen=200)

    # ── helpers ───────────────────────────────────────────────────────────────
    def get_rate(self) -> float:
        now    = time.time()
        cutoff = now - 10.0
        recent = [t for t in self._rate_window if t > cutoff]
        return round(len(recent) / 10.0, 1)

    def get_shared(self) -> dict:
        fault = FAULT_SCENARIOS.get(self.active_scenario, {}).get("fault_key")
        return {"fault": fault, "shift": self.shift}

    def record(self, sid: str, payload: dict):
        now = time.time()
        self.total_published += 1
        self._rate_window.append(now)
        self.stream_pub_count[sid] = self.stream_pub_count.get(sid, 0) + 1
        self.stream_last_ts[sid]   = now

        v = payload.get("value", payload.get("status", ""))
        u = payload.get("unit", "")
        self.stream_values[sid] = f"{v} {u}".strip()

        stream = STREAM_BY_ID.get(sid, {})
        self.recent_messages.append({
            "ts":      time.strftime("%H:%M:%S", time.localtime(now)),
            "topic":   stream.get("topic", ""),
            "label":   stream.get("label", sid),
            "source":  stream.get("source", ""),
            "value":   f"{v} {u}".strip(),
            "status":  payload.get("status", "OK"),
            "payload": json.dumps(payload),
        })

    def reset_for_demo(self):
        """Reset counters + clear stale values — call before a fresh demo."""
        self.total_published  = 0
        self.start_time       = time.time()
        self.active_scenario  = "normal"
        self.stream_values    = {}
        self.stream_last_ts   = {}
        self.stream_pub_count = {s["id"]: 0 for s in STREAMS}
        self.stream_running   = {s["id"]: True for s in STREAMS}
        self.recent_messages.clear()
        self._rate_window.clear()
        # Reset sensor generator internals so drift/wear start fresh
        for s in STREAMS:
            gen = s["gen"]
            # _wrap_gen wraps the original; reach through to reset
            orig = getattr(gen, "__wrapped__", None) or gen
            if hasattr(orig, "_reset"):
                orig._reset()


STATE = SimulatorState()

# asyncio event loop reference — set once in lifespan, used by MQTT thread
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None

# ─────────────────────────────────────────────────────────────────────────────
# WebSocket manager
# ─────────────────────────────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self._clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)

    async def broadcast(self, data: dict):
        dead = set()
        msg  = json.dumps(data)
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._clients.discard(ws)

    @property
    def count(self) -> int:
        return len(self._clients)


WS_MGR      = ConnectionManager()
EVENT_QUEUE: Optional[asyncio.Queue] = None  # set in lifespan

# ─────────────────────────────────────────────────────────────────────────────
# MQTT — loop_forever in its own thread for reliable auto-reconnect
# ─────────────────────────────────────────────────────────────────────────────
def _make_mqtt_client() -> mqtt.Client:
    client = mqtt.Client(
        client_id=f"uns-simulator-{int(time.time())}",
        clean_session=True,
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.reconnect_delay_set(min_delay=3, max_delay=60)

    def _on_connect(c, _u, _f, rc):
        STATE.mqtt_connected = (rc == 0)
        print(f"MQTT {'connected' if rc == 0 else f'error rc={rc}'}")
        if _MAIN_LOOP and EVENT_QUEUE:
            asyncio.run_coroutine_threadsafe(
                EVENT_QUEUE.put({"type": "mqtt_status", "connected": rc == 0}),
                _MAIN_LOOP,
            )

    def _on_disconnect(c, _u, rc):
        STATE.mqtt_connected = False
        print(f"MQTT disconnected rc={rc} — auto-reconnecting")

    client.on_connect    = _on_connect
    client.on_disconnect = _on_disconnect
    return client


mqtt_client = _make_mqtt_client()


def _start_mqtt():
    """Start the paho network loop in a dedicated daemon thread.
    loop_forever() + retry_first_connection=True is the most robust reconnect
    strategy for a long-running process.
    """
    def _run():
        while True:
            try:
                print(f"MQTT → {MQTT_HOST}:{MQTT_PORT}")
                mqtt_client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
                mqtt_client.loop_forever(retry_first_connection=True)
            except Exception as exc:
                print(f"MQTT loop exception: {exc} — retrying in 5s")
                STATE.mqtt_connected = False
            time.sleep(5)

    threading.Thread(target=_run, daemon=True, name="mqtt-loop").start()


# ─────────────────────────────────────────────────────────────────────────────
# Publisher thread
# ─────────────────────────────────────────────────────────────────────────────
_next_pub: Dict[str, float] = {}


def _publisher(loop: asyncio.AbstractEventLoop):
    """Background thread: generates and publishes MQTT messages."""
    global _next_pub

    # Stagger initial publish times to avoid burst on startup
    now = time.time()
    _next_pub = {s["id"]: now + i * 0.12 for i, s in enumerate(STREAMS)}

    while True:
        if not STATE.running:
            time.sleep(0.25)
            continue

        now  = time.time()
        hour = int(time.strftime("%H"))
        STATE.shift = "A" if hour < 8 else ("B" if hour < 16 else "C")

        scenario = FAULT_SCENARIOS.get(STATE.active_scenario, {})
        stop_ids = (
            set(scenario.get("affected", []))
            if scenario.get("stop_publishing")
            else set()
        )
        shared = STATE.get_shared()

        for stream in STREAMS:
            sid = stream["id"]

            if not STATE.stream_running.get(sid, True):
                continue
            if sid in stop_ids:
                continue
            if now < _next_pub.get(sid, 0):
                continue

            try:
                payload = stream["gen"](shared)
            except Exception as exc:
                print(f"[gen error] {sid}: {exc}")
                _next_pub[sid] = now + stream["interval"]
                continue

            # Only publish when MQTT is up; still record locally so UI stays live
            if STATE.mqtt_connected:
                try:
                    mqtt_client.publish(stream["topic"], json.dumps(payload), qos=0)
                except Exception as exc:
                    print(f"[publish error] {sid}: {exc}")

            STATE.record(sid, payload)

            if loop and EVENT_QUEUE:
                asyncio.run_coroutine_threadsafe(
                    EVENT_QUEUE.put({
                        "type":      "message",
                        "stream_id": sid,
                        "label":     stream["label"],
                        "topic":     stream["topic"],
                        "source":    stream["source"],
                        "value":     STATE.stream_values.get(sid, ""),
                        "status":    payload.get("status", "OK"),
                        "ts":        time.strftime("%H:%M:%S"),
                    }),
                    loop,
                )

            _next_pub[sid] = now + stream["interval"] + random.uniform(-0.3, 0.3)

        time.sleep(0.04)


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI — lifespan (replaces deprecated @app.on_event)
# ─────────────────────────────────────────────────────────────────────────────
@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    global EVENT_QUEUE, _MAIN_LOOP

    EVENT_QUEUE = asyncio.Queue()
    _MAIN_LOOP  = asyncio.get_event_loop()

    _start_mqtt()

    loop = asyncio.get_event_loop()
    threading.Thread(target=_publisher, args=(loop,), daemon=True, name="publisher").start()

    asyncio.create_task(_broadcast_loop())
    asyncio.create_task(_watchdog())
    asyncio.create_task(_announce_state())

    print(f"UNS Simulator  port={SERVER_PORT}  streams={len(STREAMS)}  "
          f"scenarios={len(FAULT_SCENARIOS)}")

    yield  # ── running ──

    # Graceful shutdown: stop publishing, disconnect MQTT
    STATE.running = False
    with contextlib.suppress(Exception):
        mqtt_client.disconnect()
    print("UNS Simulator shut down")


app = FastAPI(title="UNS Simulator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "https://simulator.iotdemozone.com",
        os.getenv("CORS_ORIGIN", ""),
    ],
    allow_origin_regex=r"https://.*\.cloudfront\.net",
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# API-key authentication middleware
# Enabled only when SIM_API_KEY env var is set.
# /health is always exempt so ECS health checks continue to work.
# WebSocket (/ws) passes the key as a query parameter: /ws?api_key=<key>
# ─────────────────────────────────────────────────────────────────────────────
if SIM_API_KEY:
    class APIKeyMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            path = request.url.path
            # Always allow health check and preflight
            if path in ("/health", "/") or request.method == "OPTIONS":
                return await call_next(request)
            # WebSocket — key comes as query param
            if path == "/ws":
                key = request.query_params.get("api_key", "")
            else:
                key = request.headers.get("X-API-Key", "")
            if key != SIM_API_KEY:
                return Response(
                    content='{"detail":"Unauthorized"}',
                    status_code=401,
                    media_type="application/json",
                )
            return await call_next(request)

    app.add_middleware(APIKeyMiddleware)
    print(f"API-key auth enabled (SIM_API_KEY is set)")
else:
    print("WARNING: SIM_API_KEY not set — running without authentication")


# ─────────────────────────────────────────────────────────────────────────────
# Background tasks
# ─────────────────────────────────────────────────────────────────────────────
async def _broadcast_loop():
    """Forward events from publisher thread → WebSocket clients.
    Falls back to a heartbeat stats frame every 2 s when the queue is idle.
    """
    while True:
        try:
            event = await asyncio.wait_for(EVENT_QUEUE.get(), timeout=2.0)
            await WS_MGR.broadcast(event)
        except asyncio.TimeoutError:
            await WS_MGR.broadcast({
                "type":            "stats",
                "running":         STATE.running,
                "mqtt_connected":  STATE.mqtt_connected,
                "total_published": STATE.total_published,
                "rate":            STATE.get_rate(),
                "scenario":        STATE.active_scenario,
                "ws_clients":      WS_MGR.count,
                "uptime":          round(time.time() - STATE.start_time),
            })
        except Exception as exc:
            print(f"[broadcast] {exc}")
            await asyncio.sleep(0.1)


async def _announce_state():
    """Send running=True to the UI a couple of seconds after boot so the
    Start button reflects reality without requiring a page refresh.
    """
    await asyncio.sleep(3)
    await WS_MGR.broadcast({"type": "control", "running": STATE.running})


async def _watchdog():
    """Log health every 30 s and warn if publishing has stalled."""
    last = 0
    while True:
        await asyncio.sleep(30)
        total = STATE.total_published
        delta = total - last
        last  = total
        print(
            f"[wd] running={STATE.running} mqtt={STATE.mqtt_connected} "
            f"ws={WS_MGR.count} +{delta}/30s total={total:,}"
        )
        if STATE.running and STATE.mqtt_connected and delta == 0:
            print("[wd] WARNING: publishing stalled — check publisher thread")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _status_dict() -> dict:
    streams_out = []
    for s in STREAMS:
        sid = s["id"]
        streams_out.append({
            "id":           sid,
            "label":        s["label"],
            "topic":        s["topic"],
            "area":         s["area"],
            "source":       s["source"],
            "source_detail":s.get("source_detail", ""),
            "unit":         s.get("unit", ""),
            "interval":     s["interval"],
            "location":     s.get("location", ""),
            "asset_id":     s.get("asset_id", ""),
            "asset_type":   s.get("asset_type", ""),
            "running":      STATE.stream_running.get(sid, True),
            "value":        STATE.stream_values.get(sid, "—"),
            "last_ts":      STATE.stream_last_ts.get(sid),
            "pub_count":    STATE.stream_pub_count.get(sid, 0),
        })
    return {
        "running":         STATE.running,
        "mqtt_connected":  STATE.mqtt_connected,
        "total_published": STATE.total_published,
        "rate":            STATE.get_rate(),
        "scenario":        STATE.active_scenario,
        "uptime":          round(time.time() - STATE.start_time),
        "ws_clients":      WS_MGR.count,
        "streams":         streams_out,
        "scenarios":       list(FAULT_SCENARIOS.values()),
        "recent_messages": list(STATE.recent_messages)[-50:],
    }


# ─────────────────────────────────────────────────────────────────────────────
# REST API
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status":  "ok",
        "running": STATE.running,
        "mqtt":    STATE.mqtt_connected,
        "streams": len(STREAMS),
        "uptime":  round(time.time() - STATE.start_time),
    }


@app.get("/")
async def root():
    return JSONResponse({
        "service":  "UNS Simulator",
        "streams":  len(STREAMS),
        "running":  STATE.running,
        "health":   "/health",
        "api":      "/api/status",
        "ws":       "/ws",
    })


@app.get("/api/status")
async def get_status():
    return _status_dict()


@app.post("/api/start")
async def start_all():
    STATE.running    = True
    STATE.start_time = time.time()
    await WS_MGR.broadcast({"type": "control", "running": True})
    print("[api] started")
    return {"ok": True, "running": True}


@app.post("/api/stop")
async def stop_all():
    STATE.running = False
    await WS_MGR.broadcast({"type": "control", "running": False})
    print("[api] stopped")
    return {"ok": True, "running": False}


@app.post("/api/reset")
async def reset_demo():
    """Reset all counters and sensor state for a clean demo start.
    Call this from the UI or CLI before a presentation.
    """
    STATE.reset_for_demo()
    STATE.running = True
    await WS_MGR.broadcast({"type": "control", "running": True})
    await WS_MGR.broadcast({"type": "reset"})
    print("[api] reset — demo ready")
    return {"ok": True, "running": True, "message": "Demo reset complete"}


@app.post("/api/streams/{stream_id}/start")
async def start_stream(stream_id: str):
    if stream_id not in STREAM_BY_ID:
        return JSONResponse({"ok": False, "error": "Unknown stream"}, status_code=404)
    STATE.stream_running[stream_id] = True
    await WS_MGR.broadcast({"type": "stream_update", "id": stream_id, "running": True})
    return {"ok": True}


@app.post("/api/streams/{stream_id}/stop")
async def stop_stream(stream_id: str):
    if stream_id not in STREAM_BY_ID:
        return JSONResponse({"ok": False, "error": "Unknown stream"}, status_code=404)
    STATE.stream_running[stream_id] = False
    await WS_MGR.broadcast({"type": "stream_update", "id": stream_id, "running": False})
    return {"ok": True}


async def _update_terminus_scenario(old_id: str, new_id: str) -> None:
    """Fire-and-forget: record ScenarioEvent + update PlantState in TerminusDB."""
    if not TERMINUS_URL or not TERMINUS_PASS:
        return
    try:
        import base64, datetime as _dt, urllib.request as _ur
        auth = "Basic " + base64.b64encode(f"{TERMINUS_USER}:{TERMINUS_PASS}".encode()).decode()
        base = f"{TERMINUS_URL}/api/document/{TERMINUS_TEAM}/{TERMINUS_DB}"
        hdrs = {"Content-Type": "application/json", "Authorization": auth}
        now_iso = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        def _post(url, body):
            data = json.dumps(body).encode()
            req = _ur.Request(url, data=data, method="POST", headers=hdrs)
            with _ur.urlopen(req, timeout=5) as r:
                return r.status

        def _put(url, body):
            data = json.dumps(body).encode()
            req = _ur.Request(url, data=data, method="PUT", headers=hdrs)
            with _ur.urlopen(req, timeout=5) as r:
                return r.status

        def _get(url):
            req = _ur.Request(url, headers={"Authorization": auth})
            with _ur.urlopen(req, timeout=5) as r:
                raw = r.read().decode()
            result = []
            for line in raw.strip().split("\n"):
                if line.strip():
                    try: result.append(json.loads(line))
                    except Exception: pass
            return result

        # 1. Close previous open ScenarioEvent
        try:
            events_raw = _get(f"{base}?type=ScenarioEvent&count=50")
            open_events = [
                e for e in events_raw
                if e.get("scenario", "").endswith(f"/{old_id}")
                and "deactivated_at" not in e
            ]
            for ev in open_events:
                activated = ev.get("activated_at", now_iso)
                try:
                    import datetime as _dt2
                    t0 = _dt2.datetime.fromisoformat(activated.replace("Z", "+00:00"))
                    t1 = _dt2.datetime.now(_dt2.timezone.utc)
                    dur = int((t1 - t0).total_seconds())
                except Exception:
                    dur = None
                closed = dict(ev)
                closed["deactivated_at"] = now_iso
                if dur is not None:
                    closed["duration_s"] = dur
                _put(f"{base}?author=uns-sim&message=scenario+deactivated+{old_id}", closed)
        except Exception as ce:
            print(f"[terminus] could not close old events: {ce}")

        # 2. Create new ScenarioEvent
        event_doc = {
            "@type": "ScenarioEvent",
            "scenario": {"@type": "@id", "@id": f"FaultScenario/{new_id}"},
            "activated_at": now_iso,
            "triggered_by": "api",
            "influx_query_hint": (
                f'from(bucket:"Aurora") |> range(start: -1h) '
                f'|> filter(fn:(r) => r.scenario == "{new_id}")'
            ),
        }
        _post(f"{base}?author=uns-sim&message=scenario+activated+{new_id}", event_doc)

        # 3. Update PlantState singleton
        plant_state = {
            "@type": "PlantState",
            "@id": "PlantState/aurora",
            "plant_id": "aurora",
            "active_scenario": {"@type": "@id", "@id": f"FaultScenario/{new_id}"},
            "last_updated": now_iso,
            "mqtt_connected": STATE.mqtt_connected,
        }
        _put(f"{base}?author=uns-sim&message=plantstate+update", plant_state)

        print(f"[terminus] scenario event + PlantState updated → {new_id}")
    except Exception as e:
        print(f"[terminus] sync failed (non-critical): {e}")


@app.post("/api/scenario/{scenario_id}")
async def set_scenario(scenario_id: str):
    if scenario_id not in FAULT_SCENARIOS:
        return JSONResponse({"ok": False, "error": "Unknown scenario"}, status_code=404)
    old_scenario = STATE.active_scenario
    STATE.active_scenario = scenario_id
    sc = FAULT_SCENARIOS[scenario_id]
    await WS_MGR.broadcast({
        "type":     "scenario_change",
        "scenario": scenario_id,
        "label":    sc["label"],
        "affected": sc.get("affected", []),
    })
    print(f"[api] scenario → {scenario_id}")
    # Sync to TerminusDB (non-blocking, best-effort)
    asyncio.create_task(_update_terminus_scenario(old_scenario, scenario_id))
    return {"ok": True, "scenario": scenario_id}


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket
# ─────────────────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await WS_MGR.connect(ws)
    try:
        # Send full state immediately so UI has data before the first heartbeat
        await ws.send_text(json.dumps({"type": "init", **_status_dict()}))
        # Keep the connection alive; handle any incoming pings
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a ping to detect dead connections
                await ws.send_text(json.dumps({"type": "ping"}))
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        WS_MGR.disconnect(ws)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (local dev only — ECS uses the Dockerfile CMD)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=SERVER_PORT, log_level="info")
