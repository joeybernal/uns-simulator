"""Aurora Industries UNS Simulator — FastAPI server (port 8081).
Mirrors the IoTAuto simulator pattern exactly so both can run side-by-side.
"""
import asyncio, contextlib, json, os, random, threading, time
from collections import deque
from typing import Dict, Optional, Set
import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from aurora_model import STREAMS, FAULT_SCENARIOS, STREAM_BY_ID, SIM, BATCH, BATCH_STAGES

MQTT_HOST   = os.getenv("MQTT_HOST",   "mqtt.iotdemozone.com")
MQTT_PORT   = int(os.getenv("MQTT_PORT",   "1883"))
MQTT_USER   = os.getenv("MQTT_USER",   "admin")
MQTT_PASS   = os.getenv("MQTT_PASS",   "28luXF7q")
SERVER_PORT = int(os.getenv("AURORA_PORT", "8081"))
_raw_api_key = os.getenv("AURORA_API_KEY", "").strip()
try:
    import json as _json
    SIM_API_KEY = _json.loads(_raw_api_key).get("api_key", _raw_api_key) if _raw_api_key.startswith("{") else _raw_api_key
except Exception:
    SIM_API_KEY = _raw_api_key
INFLUX_URL  = os.getenv("INFLUX_URL",  "").strip()
INFLUX_TOKEN= os.getenv("INFLUX_TOKEN","").strip()
INFLUX_ORG  = os.getenv("INFLUX_ORG",  "Deloitte").strip()
INFLUX_BUCKET=os.getenv("INFLUX_BUCKET","Aurora").strip()

TERMINUS_URL  = os.getenv("TERMINUS_URL",  "").strip()
TERMINUS_USER = os.getenv("TERMINUS_USER", "admin").strip()
TERMINUS_PASS = os.getenv("TERMINUS_PASS", "").strip()
TERMINUS_TEAM = os.getenv("TERMINUS_TEAM", "admin").strip()
TERMINUS_DB   = os.getenv("TERMINUS_DB",   "aurora").strip()

class SimulatorState:
    def __init__(self):
        self.running = True
        self.mqtt_connected = False
        self.active_scenario = "normal"
        self.total_published = 0
        self.start_time = time.time()
        self.dpp_pending = False          # set by /api/trigger_dpp
        self.dpp_history: list = []
        self.stream_running: Dict[str,bool] = {s["id"]: True for s in STREAMS}
        self.stream_values:  Dict[str,str]  = {}
        self.stream_last_ts: Dict[str,float]= {}
        self.stream_pub_count: Dict[str,int]= {s["id"]: 0 for s in STREAMS}
        self.recent_messages: deque = deque(maxlen=300)
        self._rate_window:    deque = deque(maxlen=300)

    def get_rate(self):
        now=time.time(); recent=[t for t in self._rate_window if t>now-10]
        return round(len(recent)/10.0,1)

    def get_shared(self):
        sc = FAULT_SCENARIOS.get(self.active_scenario,{})
        hour = int(time.strftime("%H"))
        self.shift = "A" if hour<8 else ("B" if hour<16 else "C")
        SIM.shift = self.shift
        return {"fault": sc.get("fault_key"), "shift": self.shift,
                "health_degrade": sc.get("health_degrade",{})}

    def record(self, sid, payload):
        now=time.time(); self.total_published+=1; self._rate_window.append(now)
        self.stream_pub_count[sid]=self.stream_pub_count.get(sid,0)+1
        self.stream_last_ts[sid]=now
        v=payload.get("value",payload.get("total_kw",payload.get("result",payload.get("oee_pct","—"))))
        self.stream_values[sid]=str(v)
        stream=STREAM_BY_ID.get(sid,{})
        self.recent_messages.append({"ts":time.strftime("%H:%M:%S",time.localtime(now)),
            "topic":stream.get("topic",""),"label":stream.get("label",sid),
            "source":stream.get("source",""),"asset_id":stream.get("asset_id",""),
            "asset_type":stream.get("asset_type",""),"value":str(v),"payload":json.dumps(payload)[:200]})

    def reset_for_demo(self):
        self.total_published=0; self.start_time=time.time()
        self.active_scenario="normal"; self.stream_values={}
        self.stream_last_ts={}; self.stream_pub_count={s["id"]:0 for s in STREAMS}
        self.stream_running={s["id"]:True for s in STREAMS}
        self.recent_messages.clear(); self._rate_window.clear()
        SIM.reset()

STATE=SimulatorState()
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop]=None

class ConnectionManager:
    def __init__(self): self._clients: Set[WebSocket]=set()
    async def connect(self,ws):
        await ws.accept(); self._clients.add(ws)
    def disconnect(self,ws): self._clients.discard(ws)
    async def broadcast(self,data):
        dead=set(); msg=json.dumps(data)
        for ws in list(self._clients):
            try: await ws.send_text(msg)
            except: dead.add(ws)
        for ws in dead: self._clients.discard(ws)
    @property
    def count(self): return len(self._clients)

WS_MGR=ConnectionManager(); EVENT_QUEUE: Optional[asyncio.Queue]=None

def _make_mqtt():
    c=mqtt.Client(client_id=f"aurora-sim-{int(time.time())}",clean_session=True)
    c.username_pw_set(MQTT_USER,MQTT_PASS); c.reconnect_delay_set(3,60)
    def _on_conn(c,_u,_f,rc):
        STATE.mqtt_connected=(rc==0)
        if _MAIN_LOOP and EVENT_QUEUE:
            asyncio.run_coroutine_threadsafe(EVENT_QUEUE.put({"type":"mqtt_status","connected":rc==0}),_MAIN_LOOP)
    def _on_disc(c,_u,rc): STATE.mqtt_connected=False
    c.on_connect=_on_conn; c.on_disconnect=_on_disc; return c

mqtt_client=_make_mqtt()

def _start_mqtt():
    def _run():
        while True:
            try:
                mqtt_client.connect(MQTT_HOST,MQTT_PORT,keepalive=60)
                mqtt_client.loop_forever(retry_first_connection=True)
            except Exception as e: print(f"MQTT err: {e}")
            STATE.mqtt_connected=False; time.sleep(5)
    threading.Thread(target=_run,daemon=True,name="mqtt-aurora").start()

_next_pub: Dict[str,float]={}

def _publisher(loop):
    global _next_pub
    now=time.time(); _next_pub={s["id"]:now+i*0.08 for i,s in enumerate(STREAMS)}
    while True:
        if not STATE.running: time.sleep(0.25); continue
        now=time.time(); shared=STATE.get_shared()
        for stream in STREAMS:
            sid=stream["id"]
            if not STATE.stream_running.get(sid,True): continue
            if now<_next_pub.get(sid,0): continue
            try: payload=stream["gen"](shared)
            except Exception as e: _next_pub[sid]=now+stream["interval"]; continue
            if STATE.mqtt_connected:
                try: mqtt_client.publish(stream["topic"],json.dumps(payload),qos=0)
                except: pass
            # InfluxDB write (fire-and-forget)
            if INFLUX_URL and INFLUX_TOKEN:
                _write_influx(stream, payload)
            STATE.record(sid,payload)
            if loop and EVENT_QUEUE:
                asyncio.run_coroutine_threadsafe(EVENT_QUEUE.put({
                    "type":"message","stream_id":sid,"label":stream["label"],
                    "topic":stream["topic"],"source":stream["source"],
                    "asset_id":stream.get("asset_id",""),"asset_type":stream.get("asset_type",""),
                    "value":STATE.stream_values.get(sid,""),"ts":time.strftime("%H:%M:%S")}),loop)
            _next_pub[sid]=now+stream["interval"]+random.uniform(-0.2,0.2)
        # Tick batch lifecycle every cycle
        fault = STATE.get_shared().get("fault") or ""
        BATCH.tick(fault, SIM.unit_seq, SIM.scrap_count, SIM.rework_count)
        # DPP manual trigger — fire rich batch-complete event
        if STATE.dpp_pending:
            STATE.dpp_pending=False
            import datetime as _dt
            dpp_payload={
                "timestamp": _dt.datetime.utcnow().isoformat()+"Z",
                "event":     "batch_complete_dpp",
                "triggered_by": "manual_demo",
                # Batch identity
                "batch_id":       BATCH.batch_id,
                "batch_seq":      BATCH.batch_seq,
                "order_id":       BATCH.order_id,
                "work_order_id":  BATCH.work_order_id,
                "product":        SIM.current_product,
                "customer_id":    "BMW-GROUP-DE",
                # Batch statistics
                "units_started":  BATCH.units_started,
                "units_passed":   BATCH.units_passed,
                "units_rework":   BATCH.units_rework,
                "units_scrap":    BATCH.units_scrap,
                "fpy_pct":        round(BATCH.units_passed / max(1,BATCH.units_started)*100,1),
                # Manufacturing provenance
                "manufacturing_plant": "DE-LEIPZIG-01",
                "production_line":     "line_01_to_04",
                "shift":               SIM.shift,
                # Compliance & traceability
                "standard":            "ISO 27553 / EU Battery Regulation 2023/1542",
                "material_cert":       f"CERT-ALU-{SIM.unit_seq:06d}",
                "process_params_hash": f"sha256:{SIM.unit_seq:08x}",
                "traceability_url":    f"https://dpp.aurora-industries.de/batch/{BATCH.batch_id}",
                # Completed batches today
                "batches_completed_today": len(BATCH.completed_batches),
            }
            # Publish to DPP topic
            if STATE.mqtt_connected:
                mqtt_client.publish(
                    f"aurora/line_04_inspection/cell_02/process/batch_complete",
                    json.dumps(dpp_payload), qos=1)
                # Also fire step_status for each line stage
                for stage in ["PRESSING","PAINTING","CURING","INSPECTING"]:
                    mqtt_client.publish(
                        f"aurora/line_04_inspection/cell_02/process/step_status",
                        json.dumps({**dpp_payload, "step": stage.lower(), "status": "complete"}),
                        qos=0)
            STATE.dpp_history.append(dpp_payload)
            if loop and EVENT_QUEUE:
                asyncio.run_coroutine_threadsafe(EVENT_QUEUE.put({"type":"dpp_triggered",**dpp_payload}),loop)
            # Advance batch to next cycle after DPP
            BATCH.advance()
        time.sleep(0.04)

# ── InfluxDB line-protocol writer ─────────────────────────────────────────────
# Measurement naming convention:
#   aurora_telemetry   — PLC sensor data (temperature, pressure, speed, …)
#   aurora_power       — 3-phase power readings (kW, PF, THD)
#   aurora_energy      — energy rollups (kWh, CO₂, cost)
#   aurora_health      — health scores and RUL
#   aurora_performance — OEE, cycle time, production rate
#   aurora_quality     — SPC charts, CMM inspection, leak test
#   aurora_alarms      — alarm counts
#   aurora_erp         — ERP production order / materials / holds
#   aurora_mes         — MES batch / work order / shift
#   aurora_plant       — plant-level KPIs and environment
#   aurora_analytics   — AI anomaly scores and PdM predictions
#   aurora_dpp         — Digital Product Passport events
#   aurora_rfid        — RFID tracking events

def _influx_measurement(stream_id: str) -> str:
    """Map stream ID suffix to a clean measurement name."""
    sid = stream_id.lower()
    if any(x in sid for x in ("telemetry","lube","process_params","air_network","dimensions","result")):
        return "aurora_telemetry"
    if "power" in sid:
        return "aurora_power"
    if "energy" in sid:
        return "aurora_energy"
    if "health" in sid:
        return "aurora_health"
    if "performance" in sid:
        return "aurora_performance"
    if "spc" in sid or "cmm" in sid or "leak" in sid or "quality" in sid:
        return "aurora_quality"
    if "alarm" in sid:
        return "aurora_alarms"
    if sid.startswith("erp_"):
        return "aurora_erp"
    if sid.startswith("mes_"):
        return "aurora_mes"
    if "plant" in sid or "environment" in sid or "kpi" in sid:
        return "aurora_plant"
    if "anomaly" in sid or "pdm" in sid:
        return "aurora_analytics"
    if "dpp" in sid or "step_status" in sid:
        return "aurora_dpp"
    if "rfid" in sid:
        return "aurora_rfid"
    return "aurora_data"

def _escape_tag(s: str) -> str:
    return str(s).replace(" ", "\\ ").replace(",", "\\,").replace("=", "\\=")

def _influx_field(k: str, v) -> str | None:
    """Convert a payload field to InfluxDB line-protocol field format."""
    if isinstance(v, bool):
        return f'{k}={"true" if v else "false"}'
    if isinstance(v, int):
        return f"{k}={v}i"
    if isinstance(v, float):
        return f"{k}={v}"
    if isinstance(v, str) and v not in ("", "—"):
        escaped = v.replace('"', '\\"')
        return f'{k}="{escaped}"'
    return None

# ── TerminusDB scenario sync ──────────────────────────────────────────────────

async def _update_terminus_scenario(old_id: str, new_id: str) -> None:
    """Fire-and-forget: record ScenarioEvent + update PlantState in TerminusDB."""
    if not TERMINUS_URL or not TERMINUS_PASS:
        return
    try:
        import base64, datetime as _dt, urllib.request as _ur, urllib.error as _ue
        auth = "Basic " + base64.b64encode(f"{TERMINUS_USER}:{TERMINUS_PASS}".encode()).decode()
        base = f"{TERMINUS_URL}/api/document/{TERMINUS_TEAM}/{TERMINUS_DB}"
        headers = {"Content-Type": "application/json", "Authorization": auth}
        now_iso = _dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        def _post(url, body):
            data = json.dumps(body).encode()
            req = _ur.Request(url, data=data, method="POST", headers=headers)
            with _ur.urlopen(req, timeout=5) as r:
                return r.status

        def _put(url, body):
            data = json.dumps(body).encode()
            req = _ur.Request(url, data=data, method="PUT", headers=headers)
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

        # 1. Close previous open ScenarioEvent (set deactivated_at + duration_s)
        try:
            events_raw = _get(f"{base}?type=ScenarioEvent&count=50")
            open_events = [
                e for e in events_raw
                if e.get("scenario", "").endswith(f"/{old_id}")
                and "deactivated_at" not in e
            ]
            for ev in open_events:
                ev_id = ev["@id"]
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
                _put(f"{base}?author=aurora-sim&message=scenario+deactivated+{old_id}", closed)
        except Exception as ce:
            print(f"[terminus] could not close old events: {ce}")

        # 2. Create new ScenarioEvent document
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
        _post(f"{base}?author=aurora-sim&message=scenario+activated+{new_id}", event_doc)

        # 2. Update PlantState singleton
        plant_state = {
            "@type": "PlantState",
            "@id": "PlantState/aurora",
            "plant_id": "aurora",
            "active_scenario": {"@type": "@id", "@id": f"FaultScenario/{new_id}"},
            "last_updated": now_iso,
            "mqtt_connected": STATE.mqtt_connected,
        }
        _put(f"{base}?author=aurora-sim&message=plantstate+update", plant_state)

        print(f"[terminus] scenario event + PlantState updated → {new_id}")
    except Exception as e:
        print(f"[terminus] sync failed (non-critical): {e}")


def _write_influx(stream: dict, payload: dict) -> None:
    """Best-effort InfluxDB write — runs in the publisher thread, no blocking."""
    try:
        import urllib.request
        asset_id  = _escape_tag(stream.get("asset_id", "plant"))
        asset_type= _escape_tag(stream.get("asset_type", "generic"))
        area      = _escape_tag(stream.get("area", "plant"))
        source    = _escape_tag(stream.get("source", ""))
        scenario  = _escape_tag(STATE.active_scenario)
        measurement = _influx_measurement(stream["id"])

        # Build tag set (low-cardinality identifiers)
        tags = (f"asset_id={asset_id}"
                f",asset_type={asset_type}"
                f",area={area}"
                f",source={source}"
                f",scenario={scenario}")

        # Build field set — flatten numeric + string scalars; skip dicts/lists
        fields = []
        for k, v in payload.items():
            if k == "timestamp":
                continue
            if isinstance(v, (dict, list)):
                # Flatten one level: e.g. phases.A.current_a
                if isinstance(v, dict):
                    for sk, sv in v.items():
                        f = _influx_field(f"{k}_{sk}", sv)
                        if f:
                            fields.append(f)
                continue
            f = _influx_field(k, v)
            if f:
                fields.append(f)

        if not fields:
            return

        ts = int(time.time())
        line = f"{measurement},{tags} {','.join(fields)} {ts}"
        data = line.encode()
        url  = (f"{INFLUX_URL}/api/v2/write"
                f"?org={INFLUX_ORG}&bucket={INFLUX_BUCKET}&precision=s")
        req  = urllib.request.Request(
            url, data=data, method="POST",
            headers={
                "Authorization": f"Token {INFLUX_TOKEN}",
                "Content-Type":  "text/plain; charset=utf-8",
            }
        )
        urllib.request.urlopen(req, timeout=2)
    except Exception:
        pass

@contextlib.asynccontextmanager
async def lifespan(_app):
    global EVENT_QUEUE,_MAIN_LOOP
    EVENT_QUEUE=asyncio.Queue(); _MAIN_LOOP=asyncio.get_event_loop()
    _start_mqtt()
    loop=asyncio.get_event_loop()
    threading.Thread(target=_publisher,args=(loop,),daemon=True,name="aurora-publisher").start()
    asyncio.create_task(_broadcast_loop()); asyncio.create_task(_watchdog()); asyncio.create_task(_announce_state())
    print(f"Aurora Simulator  port={SERVER_PORT}  streams={len(STREAMS)}  scenarios={len(FAULT_SCENARIOS)}")
    yield
    STATE.running=False
    with contextlib.suppress(Exception): mqtt_client.disconnect()

app=FastAPI(title="Aurora UNS Simulator",lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["*"],allow_headers=["*"])

if SIM_API_KEY:
    class _AuthMW(BaseHTTPMiddleware):
        async def dispatch(self,req,call_next):
            if req.url.path in("/health","/","/api/config") or req.method=="OPTIONS": return await call_next(req)
            key=req.query_params.get("api_key","") if req.url.path=="/ws" else req.headers.get("X-API-Key","")
            if key!=SIM_API_KEY: return Response('{"detail":"Unauthorized"}',status_code=401,media_type="application/json")
            return await call_next(req)
    app.add_middleware(_AuthMW)

async def _broadcast_loop():
    while True:
        try:
            event=await asyncio.wait_for(EVENT_QUEUE.get(),timeout=2.0)
            await WS_MGR.broadcast(event)
        except asyncio.TimeoutError:
            await WS_MGR.broadcast({"type":"stats","running":STATE.running,"mqtt_connected":STATE.mqtt_connected,
                "total_published":STATE.total_published,"rate":STATE.get_rate(),
                "scenario":STATE.active_scenario,"ws_clients":WS_MGR.count,"uptime":round(time.time()-STATE.start_time)})
        except Exception as e: await asyncio.sleep(0.1)

async def _announce_state():
    await asyncio.sleep(3); await WS_MGR.broadcast({"type":"control","running":STATE.running})

async def _watchdog():
    last=0
    while True:
        await asyncio.sleep(30); total=STATE.total_published; delta=total-last; last=total
        print(f"[aurora-wd] running={STATE.running} mqtt={STATE.mqtt_connected} ws={WS_MGR.count} +{delta}/30s total={total:,}")

def _status_dict():
    sc=FAULT_SCENARIOS.get(STATE.active_scenario,{})
    return {"running":STATE.running,"mqtt_connected":STATE.mqtt_connected,
        "total_published":STATE.total_published,"rate":STATE.get_rate(),
        "scenario":STATE.active_scenario,"uptime":round(time.time()-STATE.start_time),
        "ws_clients":WS_MGR.count,"dpp_history":STATE.dpp_history[-10:],
        "current_batch":SIM.current_batch,"current_product":SIM.current_product,
        "unit_seq":SIM.unit_seq,"shift":SIM.shift,
        "ai_hint":sc.get("ai_hint",""),
        "streams":[{"id":s["id"],"label":s["label"],"topic":s["topic"],"area":s["area"],
            "source":s["source"],"unit":s.get("unit",""),"interval":s["interval"],
            "asset_id":s.get("asset_id",""),"asset_type":s.get("asset_type",""),
            "running":STATE.stream_running.get(s["id"],True),
            "value":STATE.stream_values.get(s["id"],"—"),
            "last_ts":STATE.stream_last_ts.get(s["id"]),
            "pub_count":STATE.stream_pub_count.get(s["id"],0)} for s in STREAMS],
        "scenarios":[{"id":k,"label":v["label"],"description":v["description"],
            "affected":v.get("affected",[]),"ai_hint":v.get("ai_hint",""),
            "data_sources":v.get("data_sources",[]),"kpi_impact":v.get("kpi_impact",{}),
            "what_it_shows":v.get("what_it_shows",""),"how_to_demo":v.get("how_to_demo",""),
            "steps":v.get("steps",[]),"visual_indicators":v.get("visual_indicators",""),
            "root_cause":v.get("root_cause",""),"ai_answer":v.get("ai_answer",""),
            "affected_streams":v.get("affected_streams",[])} for k,v in FAULT_SCENARIOS.items()],
        "recent_messages":list(STATE.recent_messages)[-50:]}

@app.get("/health")
async def health(): return {"status":"ok","running":STATE.running,"mqtt":STATE.mqtt_connected,"streams":len(STREAMS),"uptime":round(time.time()-STATE.start_time)}

@app.get("/api/config")
async def get_config(): return {"api_key": SIM_API_KEY if SIM_API_KEY else ""}

@app.get("/")
async def root():
    html_path=__import__('pathlib').Path(__file__).parent/"static"/"aurora.html"
    if html_path.exists(): return HTMLResponse(html_path.read_text())
    return JSONResponse({"service":"Aurora UNS Simulator","streams":len(STREAMS),"api":"/api/status","ws":"/ws"})

@app.get("/api/status")
async def get_status(): return _status_dict()

@app.post("/api/start")
async def start_all():
    STATE.running=True; STATE.start_time=time.time()
    await WS_MGR.broadcast({"type":"control","running":True})
    return {"ok":True,"running":True}

@app.post("/api/stop")
async def stop_all():
    STATE.running=False; await WS_MGR.broadcast({"type":"control","running":False})
    return {"ok":True,"running":False}

@app.post("/api/reset")
async def reset_demo():
    STATE.reset_for_demo(); STATE.running=True
    await WS_MGR.broadcast({"type":"control","running":True}); await WS_MGR.broadcast({"type":"reset"})
    return {"ok":True,"running":True,"message":"Aurora demo reset complete"}

@app.post("/api/scenario/{scenario_id}")
async def set_scenario(scenario_id:str):
    if scenario_id not in FAULT_SCENARIOS: return JSONResponse({"ok":False,"error":"Unknown scenario"},status_code=404)
    old_scenario = STATE.active_scenario
    STATE.active_scenario=scenario_id; sc=FAULT_SCENARIOS[scenario_id]
    await WS_MGR.broadcast({"type":"scenario_change","scenario":scenario_id,
        "label":sc["label"],"affected":sc.get("affected",[]),"ai_hint":sc.get("ai_hint","")})
    # Sync to TerminusDB (non-blocking, best-effort)
    asyncio.create_task(_update_terminus_scenario(old_scenario, scenario_id))
    return {"ok":True,"scenario":scenario_id,"ai_hint":sc.get("ai_hint","")}

@app.post("/api/trigger_dpp")
async def trigger_dpp():
    """Manual DPP trigger — fires rich batch-complete + DPP passport event."""
    STATE.dpp_pending=True
    return {"ok":True,"message":f"DPP trigger queued for batch {BATCH.batch_id}",
            "batch_id":BATCH.batch_id,"order_id":BATCH.order_id,
            "work_order_id":BATCH.work_order_id,"current_stage":BATCH.stage_name,
            "units_started":BATCH.units_started,"units_passed":BATCH.units_passed,
            "fpy_pct":round(BATCH.units_passed/max(1,BATCH.units_started)*100,1),
            "product":SIM.current_product}

@app.get("/api/batch_status")
async def batch_status():
    """Live batch lifecycle — stage, progress, unit counts, completed history."""
    return {
        "batch_id":           BATCH.batch_id,
        "batch_seq":          BATCH.batch_seq,
        "order_id":           BATCH.order_id,
        "work_order_id":      BATCH.work_order_id,
        "current_stage":      BATCH.stage_name,
        "stage_progress_pct": round(BATCH.stage_progress_pct,1),
        "active_line":        BATCH.active_line,
        "batch_status":       BATCH.batch_status,
        "units_started":      BATCH.units_started,
        "units_passed":       BATCH.units_passed,
        "units_rework":       BATCH.units_rework,
        "units_scrap":        BATCH.units_scrap,
        "target_qty":         BATCH.target_qty,
        "completion_pct":     BATCH.completion_pct,
        "fpy_pct":            round(BATCH.units_passed/max(1,BATCH.units_started)*100,1),
        "dpp_triggered":      BATCH.dpp_triggered,
        "product":            SIM.current_product,
        "stages":             [{"name":s["name"],"line":s["line"],"duration_s":s["duration_s"]} for s in BATCH_STAGES],
        "completed_batches":  BATCH.completed_batches[-5:],
    }

@app.get("/api/dpp_history")
async def dpp_history(): return {"history":STATE.dpp_history}

@app.get("/api/predemo")
async def predemo_check():
    """Run pre-demo health check: verify all 4 systems and reset scenario to normal."""
    results = {}

    # 1. Simulator self-check (always passes if we're here)
    results["simulator"] = {
        "ok":     STATE.running and STATE.mqtt_connected,
        "detail": f"running={STATE.running} mqtt={STATE.mqtt_connected} streams={len(STREAMS)}",
    }

    # 2. TerminusDB PlantState
    if TERMINUS_URL and TERMINUS_PASS:
        try:
            loop = asyncio.get_event_loop()
            def _check_terminus():
                import urllib.request, urllib.error, base64, json as _json
                url = f"{TERMINUS_URL}/api/document/{TERMINUS_TEAM}/{TERMINUS_DB}?type=PlantState"
                req = urllib.request.Request(url)
                creds = base64.b64encode(f"{TERMINUS_USER}:{TERMINUS_PASS}".encode()).decode()
                req.add_header("Authorization", f"Basic {creds}")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    text = resp.read().decode()
                for line in text.strip().split("\n"):
                    if line.strip().startswith("{"):
                        d = _json.loads(line)
                        return {"ok": True, "detail": f"active_scenario={d.get('active_scenario','?').split('/')[-1]}"}
                return {"ok": False, "detail": "no PlantState document found"}
            results["terminusdb"] = await loop.run_in_executor(None, _check_terminus)
        except Exception as e:
            results["terminusdb"] = {"ok": False, "detail": str(e)[:120]}
    else:
        results["terminusdb"] = {"ok": None, "detail": "not configured (TERMINUS_URL not set)"}

    # 3. Grafana health
    try:
        loop = asyncio.get_event_loop()
        def _check_grafana():
            import urllib.request, json as _json
            req = urllib.request.Request("https://grafana.iotdemozone.com/api/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                d = _json.loads(resp.read().decode())
                return {"ok": d.get("database") == "ok", "detail": f"database={d.get('database')} version={d.get('version','')}"}
        results["grafana"] = await loop.run_in_executor(None, _check_grafana)
    except Exception as e:
        results["grafana"] = {"ok": False, "detail": str(e)[:120]}

    # 4. Reset scenario to normal
    old = STATE.active_scenario
    STATE.active_scenario = "normal"
    sc = FAULT_SCENARIOS.get("normal", {})
    await WS_MGR.broadcast({"type": "scenario_change", "scenario": "normal", "label": sc.get("label","Normal"), "affected": []})
    asyncio.create_task(_update_terminus_scenario(old, "normal"))
    results["reset"] = {"ok": True, "detail": "scenario reset to normal"}

    all_ok = all(v["ok"] for v in results.values() if v["ok"] is not None)
    return {"ready": all_ok, "checks": results}

@app.websocket("/ws")
async def ws_endpoint(ws:WebSocket):
    await WS_MGR.connect(ws)
    try:
        await ws.send_text(json.dumps({"type":"init",**_status_dict()}))
        while True:
            try: await asyncio.wait_for(ws.receive_text(),timeout=30.0)
            except asyncio.TimeoutError: await ws.send_text(json.dumps({"type":"ping"}))
    except (WebSocketDisconnect,Exception): pass
    finally: WS_MGR.disconnect(ws)

if __name__=="__main__":
    uvicorn.run(app,host="0.0.0.0",port=SERVER_PORT,log_level="info")
